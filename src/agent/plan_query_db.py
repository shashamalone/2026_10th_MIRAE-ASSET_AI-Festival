"""
plan_query_db.py

DB 검색 흐름 결정 노드(Plan & Routing). 질문 분석 노드(analyze_intent_node,
INTENT_ANALYSIS_JSON_SCHEMA)가 만든 intent 하나만 보고, 이 질의를
처리하려면 RDB / GraphDB / VectorDB 중 무엇이 필요한지와 어떤 순서로
조회해야 하는지를 계산한다. 이 노드의 결과물은 "DB 흐름 설계와 검색에
필요한 것"이지 실행 결과가 아니다. 실제로 SQL/SPARQL을 실행하는 코드는
여기 없다(그건 다음 단계의 몫이다).

[규칙 기반 + LLM 폴백 하이브리드]
대부분의 경우는 규칙만으로 100% 결정된다. intent 구조(relations의
object_ref 체인, conditions의 applies_to/domain, product_domain,
output_requirements, sort)만 보면 어떤 엔진을 어떤 순서로 호출해야
하는지가 이미 정해져 있기 때문이다. 이 부분은 LLM을 전혀 쓰지 않는다.

다만 규칙만으로는 못 푸는 경우가 하나 있다. relation의 주체가 구체적인
이름(object_entity)도 아니고 다른 relation의 결과(object_ref)도 아닌
경우다. 예를 들어 "신용등급 A+ 이상인 채권을 발행한 회사의 자회사를
편입한 ETF"에서 "자회사" relation의 주체(발행 회사)는 고정된 이름이
아니라 "신용등급 A+ 이상 채권"이라는 RDB 조건을 만족하는 채권들의
발행사 목록이다. 즉 RDB를 먼저 조회해야 Graph 탐색을 시작할 수 있는
경우인데, 지금 intent 스키마에는 "이 relation의 대상이 RDB 필터링
결과다"를 표현할 필드가 없다. 이런 relation은 intent만 봐서는
object_entity와 object_ref가 둘 다 비어 있는 것으로만 나타난다.

이 경우에만 LLM을 호출한다(_resolve_ambiguous_relation_origins). 나머지
전부는 규칙으로 처리한다. LLM이 여러 개의 애매한 relation을 한 번에
판단하도록 배치로 묶어서 호출한다(노드 3의 컬럼 매칭 폴백과 같은 방식).
LLM을 쓸 수 없거나 호출이 실패하면 "RDB 선행 조회가 필요 없다"는 안전한
기본값으로 대체하고 그 사실을 trace에 남긴다 — 잘못된 RDB 조회를
끼워 넣는 것보다는 relation을 있는 그대로(주체 불명확) 처리하는 편이
안전하다는 판단이다.

[규칙이 커버하는 경우 전부]
- 단일 엔진: RDB만, Graph만
- 두 엔진: Graph->RDB, RDB->Vector, Graph->Vector
- 세 엔진: Graph(체인)->RDB->Vector
- relations의 구조적 변주: 단일 relation, object_ref로 이어진 체인(길이
  제한 없음), 서로 독립인 relation 여러 개(전부 leaf로 취급되어 하나로
  수렴하는 단계가 전부를 기다림), 체인과 독립이 섞인 경우
- product_domain에 도메인이 여러 개(도메인마다 RDB 단계, 서로 독립이라
  병렬 실행 가능)
- Graph 결과가 RDB의 일부 도메인에만 걸리는 경우와, 어떤 도메인과도
  무관한 완전히 독립된 경우를 relation.subject_domain으로 구분한다
  (`_relation_target_domains`, 아래 문단 참고) - "채권 목록 + 별개로
  에코프로 자회사 목록"처럼 relation과 RDB 조건이 서로 무관한 복합질문도
  RDB가 Graph를 기다리지 않고 곧바로 실행되도록 정확히 계획된다.
- 교차질의: 하나의 relation이 여러 product_domain에 공통으로 걸리고
  (예: "삼성전자를 보유한 국내/해외ETF와 공모펀드"), sort.limit으로
  "TOP10"을 표현하면 route.needs_merge_rank/merge_group_step_ids가 그
  사실을 다음 단계(결과 합치기)에 넘긴다
- 비교형 질문: conditions.domain으로 도메인마다 다른 조건을 분리
- 답변 불가 후보: relations 순환/끊긴 참조, RDB 필요한데 도메인 특정
  불가, 아무 조회 대상도 없음 (이 세 가지는 LLM 폴백 대상이 아니다.
  intent 자체가 잘못됐거나 애초에 이 시스템이 다루지 않는 질문이라서,
  플래닝을 다시 시도해도 고쳐지지 않는다)

[Graph -> RDB 의존관계 정밀화: relation.subject_domain 기반 판정]
RDB target 단계의 depends_on을 "relation이 하나라도 있으면 무조건 전부
기다린다"로 뭉뚱그리면, relation과 RDB 조건이 서로 무관한 복합질문에서도
RDB가 Graph를 기다리는 것으로 잘못 계획된다. `_relation_target_domains`
(subject_domain 값 기준)로 이 관계가 실제로 걸리는 product_domain 집합을
계산해서 세 가지로 나눈다:
  1. subject_domain이 기업/기관류(_NON_PRODUCT_SUBJECTS, 예: Company)면
     빈 집합 -> 이 relation은 어떤 RDB 도메인의 depends_on에도 들어가지
     않는다(완전히 독립된 결과. terminal_graph_step_ids에는 남아 있으므로
     결과 합치기 단계에서는 그대로 포함된다).
  2. subject_domain이 "국내ETF"처럼 구체적인 도메인이면 그 도메인의
     depends_on에만 들어간다.
  3. 그 외(빈 문자열, "ETF" 같은 상위개념, 인식 못한 표기)는 이번 질문이
     요청한 product_domain 전부의 depends_on에 들어간다 - 기존 교차질의
     설계("삼성전자를 보유한 국내/해외ETF와 공모펀드")를 그대로 보존한다.

[task 기반 안전망]
intent.task(질문 분석 노드가 채운 필드)가 "relation"인데 계산된 plan에
engine="graph" 단계가 하나도 없으면, relations 추출 자체가 누락됐을
가능성이 있다는 경고를 route.blocking_reasons/trace에 남긴다. task도
LLM 산출물이라 100% 신뢰할 수 없으므로 하드 실패로 만들지 않는다 - plan은
그대로 진행되고(RDB/Vector 단계가 있으면 정상 실행됨), 경고만 남아서
나중에 원인 추적에 쓰인다. 이 안전망은 task 자체가 잘못 분류된
경우(예: relations는 있는데 task가 다른 값으로 나온 경우)는 잡지 못한다
- 그건 analyze_intent_node 뒤의 intent_guard.guard_intent가 별도로
  담당한다(relations가 있는데 task가 relation/comparison이 아니면
  relation으로 재분류).

[sort.domains 기반 merge-rank(UNION) 그룹 계산]
route.needs_merge_rank/merge_group_step_ids는 "정렬 기준을 공유하는 RDB
target 단계들의 결과를 나중에(SQL의 UNION ALL로) 합쳐서 다시 정렬·절단
해야 한다"는 신호다. sort.domains가 비어 있으면(대부분의 질문) 정렬
속성이 있는 도메인 전부가 한 그룹이고, sort.domains에 도메인 일부만
지정되어 있으면 그 목록에 있는 도메인만 한 그룹으로 묶고 나머지 도메인은
독립적으로 실행된다("국내ETF·해외ETF는 수익률 TOP5로 묶고 채권은 따로
보여줘"처럼 일부 도메인만 정렬을 공유하는 경우). sort.attribute가 아예
없으면(정렬 자체가 없는 질문) 도메인이 여러 개여도 needs_merge_rank는
항상 False다 - 합칠 정렬 기준이 없기 때문이다. 실제 UNION ALL SQL 생성과
실행은 이 노드의 몫이 아니라 rdb_search_node(nodes.py)가 담당한다.

[LLM 관련 import는 지연 import]
langchain_naver가 설치되어 있지 않거나 애매한 relation이 아예 없는
질문(대다수)에서는 이 모듈이 그 패키지 없이도 완전히 동작한다.
"""
from __future__ import annotations
from typing import Any
import re
from agent.prompts import RELATION_ORIGIN_SYSTEM_PROMPT
from agent.get_clova import _llm_plan

PipelineState = dict[str, Any]

# 이 시스템이 실제로 테이블을 가진 도메인. rdb_schema.DOMAIN_TABLE_INFO와
# 같은 집합이다. rdb_schema를 직접 import하지 않는 이유는 이 노드가
# "이 도메인이 RDB에 있는가"만 알면 되고 테이블명/컬럼 같은 세부 스키마는
# 필요 없기 때문이다(그건 다음 노드인 select_table_and_columns_node의
# 몫이다).
KNOWN_DOMAINS = {"채권", "국내ETF", "해외ETF", "펀드"}

# ---------------------------------------------------------------------------
# LLM 폴백 전용 스키마/프롬프트 (relation 출발점 판정)
#
# schemas.py/prompts.py에 있는 다른 스키마들과 같은 dict-literal 스타일을
# 따르되, 이 파일 안에 self-contained로 둔다. 이 판정은 plan_query_db.py
# 고유의 필요라서, 노드 2(질문 분석)나 노드 3(컬럼 매칭)이 쓰는 스키마와
# 섞을 이유가 없다.
# ---------------------------------------------------------------------------
RELATION_ORIGIN_JSON_SCHEMA = {
    "title": "relation_origin_resolution",
    "description": "출발점(주체)이 불명확한 relation들이 실제로는 RDB 조회 결과에서 시작하는지 판단",
    "type": "object",
    "properties": {
        "resolutions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "relation_id": {"type": "string", "description": "입력으로 받은 relation의 id 그대로"},
                    "needs_rdb_prestep": {
                        "type": "boolean",
                        "description": "이 relation의 주체를 먼저 RDB에서 조회해야 알 수 있으면 true.",
                    },
                    "rdb_domain": {
                        "type": "string",
                        "enum": ["채권", "국내ETF", "해외ETF", "펀드", ""],
                        "description": "필요하다면 어느 도메인에서 조회해야 하는지. 확실하지 않으면 빈 문자열.",
                    },
                    "rdb_purpose": {
                        "type": "string",
                        "description": "이 RDB 조회가 무엇을 찾아야 하는지 한국어 문장으로 서술. 예: '신용등급 A+ 이상인 채권의 발행사 목록을 찾는다.' needs_rdb_prestep이 false면 빈 문자열.",
                    },
                    "reasoning": {"type": "string", "description": "이렇게 판단한 근거를 한 문장으로."},
                },
                "required": ["relation_id", "needs_rdb_prestep", "rdb_domain", "rdb_purpose", "reasoning"],
            },
        },
    },
    "required": ["resolutions"],
}

def _trace(msg: str) -> list[str]:
    """LangGraph의 state.py에서 trace는 Annotated[list[str], operator.add]
    리듀서를 쓴다. 즉 각 노드는 "지금까지 누적된 전체 trace"가 아니라
    "이번에 새로 추가할 메시지만" 반환해야 하고, LangGraph가 알아서
    기존 trace 뒤에 이어붙인다. 예전(리듀서 없이 매 노드가 직접
    state.get("trace",[])+[msg]로 누적하던) 방식과의 핵심 차이다 — 이제
    이 함수는 state를 받지 않는다."""
    return [msg]


def _topo_sort_relations(relations: list[dict]) -> list[dict]:
    """relations를 object_ref 의존관계 기준으로 위상 정렬한다.

    object_ref로 이어진 relation(예: "에코프로 자회사를 편입한 ETF"에서
    R2가 R1을 참조)은 R1을 먼저 Graph에서 조회해야 R2를 조회할 수 있다는
    뜻이므로, 이 순서를 명시적으로 계산해 둬야 plan 단계들을 그대로
    실행 순서로 쓸 수 있다. 순환 참조나 존재하지 않는 id를 가리키는
    경우는 ValueError를 낸다(relations 체인은 설계상 DAG여야 한다).

    이 함수는 애매한 relation(object_entity와 object_ref가 둘 다 빈
    경우)도 그냥 통과시킨다. object_ref가 없으니 의존관계가 없는
    것으로 취급되어 즉시 resolved 처리된다 — RDB 선행 조회가 필요한지는
    이 함수가 아니라 plan_query_node 본체가 LLM 폴백으로 별도 판단한다.
    """
    ids = {r["id"] for r in relations}
    resolved: list[dict] = []
    resolved_ids: set[str] = set()
    remaining = list(relations)

    while remaining:
        progressed = False
        next_remaining = []
        for r in remaining:
            dep = r.get("object_ref") or ""
            if dep and dep not in ids:
                raise ValueError(f"relation {r['id']}의 object_ref '{dep}'가 relations 목록에 없습니다.")
            if not dep or dep in resolved_ids:
                resolved.append(r)
                resolved_ids.add(r["id"])
                progressed = True
            else:
                next_remaining.append(r)
        if not progressed:
            stuck = [r["id"] for r in next_remaining]
            raise ValueError(f"relations 의존관계가 순환되어 있습니다: {stuck}")
        remaining = next_remaining

    return resolved


def _normalize_domains(intent: dict) -> list[dict]:
    """product_domain을 [{"domain": ..., "subtype": [...]}, ...] 형태로
    정규화한다. 현재 스키마는 원소가 객체({"domain", "subtype"})지만,
    구버전 intent나 LLM이 형식을 벗어나 문자열 배열로 준 경우에도
    죽지 않도록 문자열도 받아들인다.

    같은 domain이 두 번 이상 나오면 하나로 합친다(subtype은 합집합). 이
    중복은 실제로 관측됐다 - verify_intent_node가 relations 복구 같은 다른
    교정을 하면서 product_domain을 통째로 다시 쓰다가 같은 도메인을 두 번
    내는 경우가 있었다. 중복을 그대로 두면 도메인당 RDB 단계를 만드는
    루프(2번)가 같은 step_id("rdb_채권" 등)를 두 번 만들어서 plan에 중복
    단계가 생기고, step_results 딕셔너리 키가 겹쳐 한쪽 실행이 조용히
    버려지는 낭비/혼선으로 이어진다."""
    merged: dict[str, list[str]] = {}
    order: list[str] = []
    for d in intent.get("product_domain") or []:
        if isinstance(d, str):
            domain, subtype = d, []
        elif isinstance(d, dict) and d.get("domain"):
            domain, subtype = d["domain"], list(d.get("subtype") or [])
        else:
            continue
        if domain not in merged:
            merged[domain] = []
            order.append(domain)
        for s in subtype:
            if s not in merged[domain]:
                merged[domain].append(s)
    return [{"domain": domain, "subtype": merged[domain]} for domain in order]


def _is_ambiguous_relation(r: dict) -> bool:
    """object_entity도 object_ref도 없는 relation. 주체가 어디서
    오는지 intent 구조만으로는 알 수 없다는 신호다."""
    return not (r.get("object_entity") or "").strip() and not (r.get("object_ref") or "").strip()


def _resolve_ambiguous_relation_origins(ambiguous_relations: list[dict], intent: dict) -> dict[str, dict]:
    """애매한 relation들을 배치로 LLM에 넘겨 RDB 선행 조회가 필요한지
    판단한다. relation_id -> resolution dict를 돌려준다.

    LLM을 쓸 수 없거나(langchain_naver 미설치) 호출이 실패하면 빈
    dict를 돌려준다. 호출부는 빈 dict를 "이 relation들은 전부 RDB
    선행 조회가 필요 없다"는 안전한 기본값으로 해석한다."""
    if not ambiguous_relations:
        return {}
    try:
        structured_llm = _llm_plan.with_structured_output(RELATION_ORIGIN_JSON_SCHEMA, method="json_schema")
        relations_desc = "\n".join(
            f"- id={r['id']}, subject_domain={r.get('subject_domain','')}, relation={r['relation']}"
            for r in ambiguous_relations
        )
        result = structured_llm.invoke(
            [
                ("system", RELATION_ORIGIN_SYSTEM_PROMPT),
                (
                    "human",
                    f"[원본 질문]\n{intent.get('raw_question','')}\n\n"
                    f"[출발점이 불명확한 relations]\n{relations_desc}",
                ),
            ]
        )
        return {r["relation_id"]: r for r in result["resolutions"]}
    except Exception:
        # langchain_naver 미설치, API 오류, 타임아웃 등. 이 폴백 자체가
        # 실패해도 전체 plan 수립이 죽으면 안 되므로 빈 dict로 degrade한다.
        return {}


# ---------------------------------------------------------------------------
# Graph -> RDB 의존관계 판정 (relation이 실제로 어느 RDB 도메인에 걸리는가)
#
# 예전에는 relation이 하나라도 있으면 모든 RDB target 단계가 무조건 그
# relation을 기다리도록(depends_on) 뭉뚱그려져 있었다. 이러면 "채권 신용등급
# A+ 이상 목록이랑, 별개로 에코프로 자회사 목록도 알려줘"처럼 relation과 RDB
# 조건이 서로 무관한 복합질문도 RDB가 Graph를 기다리는 것으로 잘못 계획된다.
# relation.subject_domain 값으로 세 가지 경우(독립/특정 도메인/전체 공통)를
# 구분해서 이 문제를 해결한다.
# ---------------------------------------------------------------------------
_NON_PRODUCT_SUBJECTS = {
    "company", "organization", "issuer", "assetmanager", "custodian",
    "기업", "회사", "발행사", "발행기관", "운용사", "수탁회사",
}

_EXACT_DOMAIN_ALIASES = {
    "채권": "채권", "bond": "채권",
    "국내etf": "국내ETF", "해외etf": "해외ETF",
    "펀드": "펀드", "fund": "펀드", "publicfund": "펀드",
}


def _relation_target_domains(subject_domain: str, requested_domains: list[str]) -> set[str]:
    """이 relation이 실제로 걸리는 product_domain 집합을 계산한다.

    - 기업류(Company 등)면 빈 집합 -> 어떤 RDB 도메인과도 안 걸리는 독립 결과
      ("채권 목록 + 별개로 에코프로 자회사" 케이스).
    - "국내ETF"처럼 구체적 도메인이면 그 하나만
      ("에코프로 자회사가 편입된 국내ETF top5" 케이스).
    - 그 외(빈 문자열, "ETF" 같은 상위개념, 인식 못한 표기)는 지금 질문이
      요청한 도메인 전부에 공통으로 걸린다고 본다 - "삼성전자를 보유한
      국내/해외ETF와 공모펀드" 같은 기존 교차질의 설계를 그대로 보존한다."""
    key = (subject_domain or "").strip().lower()
    if key in _NON_PRODUCT_SUBJECTS:
        return set()
    exact = _EXACT_DOMAIN_ALIASES.get(key)
    if exact:
        return {exact}
    if key == "etf":
        return {"국내ETF", "해외ETF"} & set(requested_domains)
    return set(requested_domains)


def plan_query_node(state: PipelineState) -> PipelineState:
    """intent만 보고 실행 계획(plan)과 라우팅 요약(route)을 만든다.

    state에 추가되는 키:
      plan  - 단계 목록. 각 원소는 최소 step_id, engine, depends_on을
              갖는다. 계획을 세울 수 없으면 None.
      route - LangGraph add_conditional_edges에서 바로 분기 조건으로 쓸
              요약 플래그(needs_graph / needs_rdb / needs_vector /
              needs_merge_rank / used_llm_fallback 등).
    """
    intent = state["intent"]
    import re
    question = state.get("question") or intent.get("raw_question", "")
    policy_request = ("정책" in question and sum(t in question for t in ("구조", "운용주체", "자금조달", "출자")) >= 2)
    if policy_request:
        terms = [e.get("surface_form", "") for e in intent.get("target_entities") or [] if e.get("surface_form")]
        if not terms:
            subject = re.match(r"\s*([^.!?]+?)의\s", question)
            terms = [subject.group(1)] if subject else []
        req = intent.get("output_requirements") or {}
        return {"plan": [{"step_id": "vector_policy", "engine": "vector", "depends_on": [],
                          "document_scope": "policy", "subject_terms": terms,
                          "topics": req.get("narrative_topics", []), "fields": req.get("fields", [])}],
                "route": {"needs_graph": False, "needs_rdb": False, "needs_vector": True,
                          "needs_merge_rank": False, "blocking_reasons": []},
                "trace": _trace("정책·자금조달 설명: 상품 마스터가 아닌 공식 정책/운용 문서 카탈로그에서 주체를 대조합니다.")}
    from agent.evidence_contract import request_blockers
    blockers = request_blockers(intent, state.get("question") or intent.get("raw_question", ""))
    if blockers:
        return {"plan": [], "route": {"needs_graph": False, "needs_rdb": False, "needs_vector": False,
                "needs_merge_rank": False, "blocking_reasons": blockers},
                "trace": _trace("요청 근거 계약: " + "; ".join(blockers))}

    domains = _normalize_domains(intent)
    domain_names = [d["domain"] for d in domains]
    supported_domains = [d for d in domains if d["domain"] in KNOWN_DOMAINS]
    unsupported_domains = [d["domain"] for d in domains if d["domain"] not in KNOWN_DOMAINS]

    conditions = intent.get("conditions") or []
    relations = intent.get("relations") or []
    sort = intent.get("sort") or {}
    output_req = intent.get("output_requirements") or {}
    fields = output_req.get("fields") or []
    narrative_topics = output_req.get("narrative_topics") or []
    answer_format = intent.get("answer_format") or ""
    target_entities = intent.get("target_entities") or []

    blocking_reasons: list[str] = []

    # -----------------------------------------------------------------
    # 0) relations 위상 정렬. 순환/끊긴 참조는 여기서 걸러진다. 이건
    # intent 자체가 잘못 만들어졌다는 뜻이라 LLM 폴백 대상이 아니다.
    # -----------------------------------------------------------------
    try:
        ordered_relations = _topo_sort_relations(relations)
    except ValueError as e:
        return {"plan": None, "route": None, "trace": _trace(f"Plan 수립 실패: {e}")}

    # -----------------------------------------------------------------
    # 0.5) 출발점이 불명확한 relation만 골라 LLM에 배치로 묻는다. 규칙
    # 기반으로 풀리는 relation(object_entity가 있거나 object_ref로
    # 이어진 것)은 이 단계를 전혀 거치지 않는다.
    # -----------------------------------------------------------------
    ambiguous_relations = [r for r in relations if _is_ambiguous_relation(r)]
    origin_resolutions = _resolve_ambiguous_relation_origins(ambiguous_relations, intent)

    llm_fallback_used: list[dict] = []
    llm_fallback_attempted_but_unavailable = bool(ambiguous_relations) and not origin_resolutions

    # -----------------------------------------------------------------
    # 1) Graph 단계: relation 하나당 한 단계, object_ref 의존 순으로 정렬.
    # 애매한 relation은 LLM 판정 결과에 따라 그 앞에 RDB 선행 조회 단계
    # (role=entity_lookup)가 끼어들 수 있다.
    # -----------------------------------------------------------------
    plan: list[dict] = []
    for r in ordered_relations:
        step_id = f"graph_{r['id']}"
        depends_on = [f"graph_{r['object_ref']}"] if r.get("object_ref") else []

        if _is_ambiguous_relation(r):
            resolution = origin_resolutions.get(r["id"])
            if resolution and resolution.get("needs_rdb_prestep") and resolution.get("rdb_domain") in KNOWN_DOMAINS:
                prestep_id = f"rdb_pre_{r['id']}"
                plan.append(
                    {
                        "step_id": prestep_id,
                        "engine": "rdb",
                        "role": "entity_lookup",  # 최종 답의 일부가 아니라 뒤 Graph 단계의 입력만 만드는 조회
                        "depends_on": [],
                        "domain": resolution["rdb_domain"],
                        "purpose": resolution.get("rdb_purpose", ""),
                        "source": "llm_fallback",
                    }
                )
                depends_on = [prestep_id]
                llm_fallback_used.append(
                    {
                        "relation_id": r["id"],
                        "rdb_domain": resolution["rdb_domain"],
                        "reasoning": resolution.get("reasoning", ""),
                    }
                )

        plan.append(
            {
                "step_id": step_id,
                "engine": "graph",
                "depends_on": depends_on,
                "relation": r,
                # 이 relation에 걸린 조건(예: "매출 1조 이상인 자회사")
                "conditions": [c for c in conditions if c.get("applies_to") == r["id"]],
                "time_window_relative": r.get("time_window_relative", ""),
            }
        )

    # relations가 서로 독립된(체인으로 안 이어진) 여러 개일 수 있다. 예:
    # "우주항공 테마와 연결되어 있으면서 록히드마틴을 편입한 ETF"는 R1(테마
    # 태깅)과 R2(종목 편입)가 서로를 참조하지 않는 별도 조건이다. 이런
    # 경우 RDB/Vector 단계는 "가장 나중에 처리된 relation 하나"가 아니라
    # "다른 relation의 object_ref로도 참조되지 않는 모든 leaf relation"
    # 전부가 끝나야 시작할 수 있다. leaf가 아닌 relation(예: R1이 R2에게
    # object_ref로 참조되는 경우의 R1)은 이미 R2 안에 결과가 녹아들어가
    # 있으므로 중복으로 기다릴 필요가 없다. rdb_pre 단계는 이 계산과
    # 무관하다(그건 relation 체인 자체가 아니라 특정 relation 하나의
    # 입력을 준비하는 보조 단계일 뿐이다).
    referenced_ids = {r["object_ref"] for r in relations if r.get("object_ref")}
    terminal_graph_step_ids = [f"graph_{r['id']}" for r in relations if r["id"] not in referenced_ids]

    # -----------------------------------------------------------------
    # 2) RDB 단계: 최종 조회 대상(target)에 걸리는 게 하나라도 있으면
    # -----------------------------------------------------------------
    target_conditions = [c for c in conditions if (c.get("applies_to") or "target") == "target"]
    sort_attribute = sort.get("attribute") or ""
    sort_limit = sort.get("limit") or ""
    product_name_entities = [e for e in target_entities if e.get("entity_type") == "product_name"]
    has_subtype = any(d["subtype"] for d in domains)

    rdb_triggers: list[str] = []
    if target_conditions:
        rdb_triggers.append(f"target 조건 {len(target_conditions)}건")
    if sort_attribute:
        rdb_triggers.append(f"정렬({sort_attribute})")
    if fields:
        rdb_triggers.append(f"출력 필드({', '.join(fields)})")
    if has_subtype:
        subtypes = [s for d in domains for s in d["subtype"]]
        rdb_triggers.append(f"상품 하위유형({', '.join(subtypes)})")
    if product_name_entities:
        names = [e["surface_form"] for e in product_name_entities]
        rdb_triggers.append(f"상품명 조회({', '.join(names)})")

    needs_rdb = bool(rdb_triggers)
    rdb_step_ids: list[str] = []

    if needs_rdb:
        if not supported_domains:
            # 테이블을 특정할 수 없으면 RDB 단계를 만들 수 없다. 이것도
            # intent가 애초에 이 시스템이 다루지 않는 도메인을 가리키고
            # 있다는 뜻이라 LLM 폴백 대상이 아니다.
            if domain_names:
                blocking_reasons.append(
                    f"RDB 조회가 필요하지만 지원하지 않는 도메인입니다: {unsupported_domains}"
                )
            else:
                blocking_reasons.append(
                    "RDB 조회가 필요하지만 product_domain이 비어 있어 테이블을 특정할 수 없습니다."
                )
        else:
            # 도메인이 여러 개면 테이블이 서로 다르므로 단계를 나눠 만든다.
            # 이 단계들은 서로 의존하지 않고 같은 Graph 결과(있다면)에만
            # 의존하므로 서로 독립이다 — "삼성전자를 보유한 국내/해외ETF와
            # 공모펀드를 1년 수익률 기준 TOP10" 같은 교차질의가 이 경로다.
            for d in supported_domains:
                step_id = f"rdb_{d['domain']}"
                # conditions.domain이 채워져 있으면 그 도메인에만 조건을
                # 적용한다("신용등급 A+ 이상 채권과 위험등급 2등급 이하
                # ETF를 비교"처럼 도메인마다 다른 조건이 걸리는 경우).
                # 비어 있으면(대부분의 경우) 모든 도메인에 똑같이 적용한다.
                domain_conditions = [
                    c for c in target_conditions if not c.get("domain") or c["domain"] == d["domain"]
                ]
                # terminal relation(체인의 마지막, 다른 relation의 object_ref로
                # 참조되지 않는 것) 중 이 도메인에 실제로 걸리는 것만 기다린다
                # (_relation_target_domains). "채권 목록 + 별개로 에코프로
                # 자회사"처럼 무관한 relation은 여기 안 걸려서 depends_on이
                # 비게 되고, "삼성전자를 보유한 국내/해외ETF와 공모펀드"처럼
                # 여러 도메인에 공통으로 걸리는 relation은 그 도메인들 전부의
                # depends_on에 들어간다.
                relevant_graph_steps = [
                    f"graph_{r['id']}" for r in relations
                    if r["id"] not in referenced_ids
                    and d["domain"] in _relation_target_domains(r.get("subject_domain", ""), domain_names)
                ]
                plan.append(
                    {
                        "step_id": step_id,
                        "engine": "rdb",
                        "role": "target",  # 이 단계의 결과가 최종 답의 일부다 (entity_lookup과 구분)
                        "depends_on": relevant_graph_steps,
                        "domain": d["domain"],
                        "subtype": d["subtype"],
                        "conditions": domain_conditions,
                        # sort는 attribute/order/limit을 통째로 넘긴다. 여러
                        # 도메인이 있으면 limit은 이 단계 하나가 아니라
                        # 도메인별 결과를 전부 합친 뒤 결과 합치기 노드가
                        # 적용해야 한다(도메인당 N개가 아니라 합쳐서 N개).
                        "sort": sort if sort_attribute else None,
                        "fields": fields,
                        "product_name_entities": product_name_entities,
                        "class_suffixes": (intent.get("identity_comparison") or {}).get("classes", []),
                        "triggers": rdb_triggers,
                    }
                )
                rdb_step_ids.append(step_id)

    # -----------------------------------------------------------------
    # 3) Vector 단계: 서술형 답변이 필요하면 마지막에 하나
    # -----------------------------------------------------------------
    needs_vector = bool(narrative_topics) or answer_format in ("narrative", "list_with_narrative")
    if intent.get("identity_comparison") and not narrative_topics:
        needs_vector = False
    if needs_vector:
        upstream = rdb_step_ids or terminal_graph_step_ids
        plan.append(
            {
                "step_id": "vector_narrative",
                "engine": "vector",
                "depends_on": list(upstream),
                "topics": narrative_topics,
                # intent가 "투자 위험"/"운용 전략"을 narrative_topics 대신
                # output_requirements.fields에 넣는 경우가 많아 함께 넘긴다.
                "fields": fields,
                "target_entities": target_entities,
            }
        )

    # -----------------------------------------------------------------
    # 3.5) merge-rank(UNION) 그룹 계산. sort.domains가 비어 있으면(대부분의
    # 질문) 정렬 기준이 있는 도메인 전부가 한 그룹이다(기존 동작 그대로).
    # 채워져 있으면 그 목록에 있는 도메인만 한 그룹으로 묶고 나머지 도메인은
    # 독립 실행한다("국내ETF·해외ETF는 수익률 TOP5로 묶고 채권은 따로"처럼
    # 일부 도메인만 공유하는 정렬이 있는 경우). rdb_step_ids와
    # supported_domains는 2)의 같은 루프에서 같은 순서로 채워지므로 zip으로
    # 안전하게 짝지을 수 있다.
    # -----------------------------------------------------------------
    sort_domains = set(sort.get("domains") or [])
    if sort_attribute:
        merge_group_ids = [
            sid for sid, d in zip(rdb_step_ids, supported_domains)
            if not sort_domains or d["domain"] in sort_domains
        ]
    else:
        merge_group_ids = []
    needs_merge_rank = len(merge_group_ids) > 1
    rank_domains = {p.get("domain") for p in plan if p["step_id"] in merge_group_ids}
    if needs_merge_rank and "해외ETF" in rank_domains and len(rank_domains) > 1 and "".join(sort_attribute.split()).casefold() in {"aum", "순자산", "순자산총액", "순자산규모"}:
        needs_merge_rank = False
        blocking_reasons.append("해외ETF의 거래통화 AUM과 국내 상품의 원화 AUM은 환율·환산 기준일 없이 합쳐 순위를 매길 수 없습니다. 각 도메인 안에서만 정렬해 표시합니다.")

    # -----------------------------------------------------------------
    # 4) 라우팅 요약
    # -----------------------------------------------------------------
    route = {
        "needs_graph": any(s["engine"] == "graph" for s in plan),
        "needs_rdb": any(s["engine"] == "rdb" for s in plan),
        "needs_vector": any(s["engine"] == "vector" for s in plan),
        "domains": domain_names,
        "supported_domains": [d["domain"] for d in supported_domains],
        "rdb_required_but_blocked": needs_rdb and not any(s["engine"] == "rdb" for s in plan),
        # RDB 단계가 2개 이상이고 정렬 기준이 있으면(교차질의 + TOP N), 각
        # 단계 결과를 단순히 이어붙이는 게 아니라 합친 뒤 다시 정렬하고
        # limit을 적용해야 한다는 신호. 결과 합치기 노드가 이 플래그를 보고
        # 병합 방식을 결정한다.
        "needs_merge_rank": needs_merge_rank,
        # 실제로 하나의 정렬 기준을 공유하는 RDB 단계 id들. needs_merge_rank가
        # False면 항상 빈 리스트다.
        "merge_group_step_ids": merge_group_ids if needs_merge_rank else [],
        "sort_limit": sort_limit,
        # 이번 질문에서 LLM 폴백을 실제로 썼는지, 썼다면 어떤 relation에
        # 어떤 판단을 했는지. 폴백이 필요했는데(애매한 relation이
        # 있었는데) LLM을 쓸 수 없어서 기본값으로 처리된 경우도 구분한다.
        "used_llm_fallback": bool(llm_fallback_used),
        "llm_fallback_details": llm_fallback_used,
        "llm_fallback_unavailable": llm_fallback_attempted_but_unavailable,
        "blocking_reasons": blocking_reasons,
    }

    # Explicit parent-and-subsidiary enumeration is a union of alternative
    # issuers/holdings, not the intersection used for independent constraints.
    question = state.get("question", "")
    by_id = {r["id"]: r for r in relations}
    for target_step in plan:
        if target_step.get("engine") != "rdb":
            continue
        alternatives = {}
        for sid in target_step.get("depends_on") or []:
            relation = by_id.get(sid.removeprefix("graph_"), {})
            if relation.get("relation") not in {"holds", "holding", "held_by"}:
                continue
            chain, seen, root = [], set(), relation
            while root and root.get("id") not in seen:
                seen.add(root.get("id")); chain.append(root)
                if not root.get("object_ref"):
                    break
                root = by_id.get(root["object_ref"], {})
            name = root.get("object_entity", "")
            if name and re.search(re.escape(name) + r"\s*(?:및|와|과)\s*(?:확인된\s*)?자회사", question):
                alternatives.setdefault(name, []).append((sid, len(chain) > 1))
        target_step["graph_any_groups"] = [[sid for sid, _ in group] for group in alternatives.values()
                                            if {is_child for _, is_child in group} == {True, False}]

    # task 기반 안전망: intent.task가 "relation"인데 plan에 Graph 단계가
    # 하나도 없으면 relations 추출 자체가 누락됐을 가능성이 있다. task도
    # LLM 산출물이라 100% 신뢰할 수 없으므로 하드 실패로 만들지 않고,
    # 조용히 넘어가지 않도록 경고만 남긴다(route_after_plan은 이 값을
    # 보고 라우팅을 바꾸지 않는다 - blocking_reasons는 순수 정보성이다).
    if intent.get("task") == "relation" and not any(s["engine"] == "graph" for s in plan):
        blocking_reasons.append(
            "task=relation인데 plan에 Graph 단계가 없습니다 - relations 추출이 누락됐을 수 있습니다."
        )

    # 계획이 비어 있으면 그 사실을 남겨 둔다. 다음 노드가 답변 불가
    # 후보로 다루게 된다. 단, "애초에 조회할 게 없었다"와 "조회할 건
    # 있었는데 라우팅에 실패했다"는 다른 상황이라 구분한다. 후자는 이미
    # blocking_reasons에 구체적인 이유가 들어 있으므로 덧붙이지 않는다.
    if not plan and not blocking_reasons:
        blocking_reasons.append("조회할 대상이 없습니다(조건, 관계, 서술 요구가 모두 비어 있음).")
    route["blocking_reasons"] = blocking_reasons

    engines_desc = "+".join(
        name for name, flag in (
            ("Graph", route["needs_graph"]),
            ("RDB", route["needs_rdb"]),
            ("Vector", route["needs_vector"]),
        ) if flag
    ) or "없음"

    msg = f"Plan 수립: 엔진={engines_desc}, 단계={[s['step_id'] for s in plan]}"
    if llm_fallback_used:
        msg += f" / LLM 폴백 사용: {[d['relation_id'] for d in llm_fallback_used]}"
    if llm_fallback_attempted_but_unavailable:
        msg += " / 경고: 출발점 불명확한 relation이 있었으나 LLM 폴백을 쓸 수 없어 기본값(선행 조회 없음)으로 처리"
    if blocking_reasons:
        msg += f" / 경고: {'; '.join(blocking_reasons)}"

    return {"plan": plan, "route": route, "trace": _trace(msg)}
