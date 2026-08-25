# -*- coding: utf-8 -*-
"""1단계 Query Understanding — Semantic Query Frame v1.

자연어 질의를 SQL/Graph/Vector 가 나중에 조합할 수 있는 의미 요소 14개로 쪼갠다.
이 단계는 TBox 도 물리 스키마도 보지 않는다. 따라서 fp: URI 나 실제 컬럼명을
만들어내면 안 된다 — 그건 2·2.5단계의 일이고, 여기서 하면 근거 없는 확정이 된다.

35문항 + 모호질의 12문항 실측으로 확정했다. 근거·전체 수치는
vectordb_test/4_query_frame_v1/4_result_query_frame_v1.md 에 있다. 요약:

  구조 유효성      35/35 (보정 전 스키마 준수)
  계약 등급 슬롯    operator·unit·temporal 100% / task·limit 97.1% / value 95.0%
                   targets R 94.9% / entities P 96.4% / domain P 95.3%
  참고 등급 슬롯    constraints 75.8/78.1 · computation 50/83.3 · entity role 85.2
                   validation 유형 60/60 · relation 경로 양끝 50
  안전 속성        Premature Resolution 0/12 — 모호한 말을 근거 없이 확정하지 않는다

  ★ 참고 등급 슬롯은 Planner 가 힌트로만 써야 한다. 실제 필터·조인은 2.5단계
    metadata_context 와 대조해 다시 확인한다.

두 가지를 특히 조심한다.

1. operator 극성은 **사용자가 말한 축** 기준이다.
   "AA- 이상"  →  {field_text:"신용등급", operator:">=", value_text:"AA-"}
   gold_nl2sql.json 은 같은 조건을 crd_grd_rank <= 4 로 적는데, 그건 등급을
   1=AAA 로 뒤집어 놓은 물리 컬럼이라 부호가 반대다. 그쪽을 베끼면 안 된다.

2. 모호한 표현은 풀지 않고 보존한다.
   "안전한" → kind:"qualitative", grounding_status:"unresolved"
   여기서 신용등급 AAA 로 확정해버리면 premature grounding 이다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import clova  # noqa: E402
from config import FRAME_MODEL  # noqa: E402

SCHEMA_VERSION = "v1"
MODEL = FRAME_MODEL

DOMAINS = ["bond_kr", "etf_kr", "etf_gl", "fund_pub"]
TASKS = ["lookup", "filter_rank", "relation", "comparison", "explanation", "recommendation"]
ENTITY_ROLES = ["product", "share_class", "company", "issuer", "index",
                "theme", "manager", "ticker", "model"]
MATCH_MODES = ["exact", "partial"]
OPERATORS = [">=", "<=", ">", "<", "==", "!=", "in", "contains", "exists"]
CONSTRAINT_KINDS = ["quantitative", "categorical", "boolean", "qualitative"]
GROUNDING = ["resolved", "unresolved"]
DIRECTIONS = ["asc", "desc"]
TEMPORAL_KINDS = ["latest_snapshot", "as_of", "period", "future"]
COMPUTATION_KINDS = ["overlap_ratio", "concentration", "dedup", "compare", "count", "rank"]
AMBIGUITY_TYPES = ["underspecified_criterion", "ambiguous_domain",
                   "ambiguous_entity", "relation_vs_mention"]
VALIDATION_TYPES = ["taxonomy_value", "temporal_existence", "entity_existence",
                    "future_value", "relation_domain_range"]

# validation_targets.type → 최종 ABSTAIN 코드. 1단계는 "무엇을 검증할지"만 뽑고
# 판정은 check_tbox / verify 노드가 한다 (agent-spec-0822.md §13).
# 긴 형식이 정본이다 — 평가 대상 문자열(expected_behavior)이자 ttl 주석 표기다.
ABSTAIN_CODE = {
    "taxonomy_value": "ABSTAIN_INVALID_TAXONOMY",
    "temporal_existence": "ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF",
    "entity_existence": "ABSTAIN_ENTITY_NOT_FOUND",
    "future_value": "ABSTAIN_FUTURE_DATA",
    "relation_domain_range": "ABSTAIN_DOMAIN_MISMATCH",
}

FIELDS = ["domain_candidates", "task", "targets", "entities", "requested_fields",
          "constraints", "relations", "ordering", "limit", "temporal",
          "computation", "evidence_requirements", "ambiguity", "validation_targets"]

# P/R 통과기준이 걸리는 슬롯. requested_fields·evidence_requirements 는 자연어
# 나열이라 exact match 채점이 무의미해 채움률과 누출검사만 본다.
SCORED_SLOTS = ["domain_candidates", "task", "targets", "entities", "constraints",
                "relations", "ordering", "limit", "computation",
                "ambiguity", "validation_targets", "temporal"]


def _s(enum=None, null=False):
    """문자열 스키마. null 허용이면 type 을 배열로 주고 enum 에도 None 을 넣는다."""
    if enum:
        return {"type": ["string", "null"] if null else "string",
                "enum": enum + [None] if null else enum}
    return {"type": ["string", "null"] if null else "string"}


def _obj(props, required=None):
    return {"type": "object", "properties": props, "required": required or list(props)}


QUERY_FRAME_SCHEMA = {
    "type": "object",
    "properties": {
        "domain_candidates": {
            "type": "array", "items": {"type": "string", "enum": DOMAINS},
            "description": "해당 가능성이 있는 상품 도메인 전부. 확실하지 않으면 복수로 넣는다."},
        "task": {"type": "string", "enum": TASKS},
        "targets": {"type": "array", "items": _obj({"text": _s()}),
                    "description": "찾는 대상의 상품군 표현. 예: 회사채, 국내 ETF"},
        "entities": {"type": "array", "items": _obj(
            {"text": _s(), "role": _s(ENTITY_ROLES), "match_mode": _s(MATCH_MODES)}),
            "description": "질의에 나온 고유명. 원문 그대로."},
        "requested_fields": {"type": "array", "items": _obj({"text": _s()}),
                             "description": "보여달라고 한 속성. 자연어 그대로."},
        "constraints": {"type": "array", "items": _obj({
            "raw": _s(), "field_text": _s(), "operator": _s(OPERATORS),
            "value_text": _s(null=True), "value_num": {"type": ["number", "null"]},
            "unit": _s(null=True), "kind": _s(CONSTRAINT_KINDS),
            "grounding_status": _s(GROUNDING)})},
        "relations": {"type": "array", "items": _obj(
            {"raw": _s(), "path": {"type": "array", "items": {"type": "string"}}}),
            "description": '관계 경로. 예: ["ETF","편입증권","기업"]'},
        "ordering": {"type": "array", "items": _obj(
            {"field_text": _s(), "direction": _s(DIRECTIONS)})},
        "limit": {"type": ["integer", "null"]},
        "temporal": _obj({"kind": _s(TEMPORAL_KINDS), "raw": _s(null=True),
                          "as_of_text": _s(null=True), "window_text": _s(null=True)}),
        "computation": {"type": "array", "items": _obj(
            {"kind": _s(COMPUTATION_KINDS), "raw": _s()})},
        "evidence_requirements": {"type": "array", "items": {"type": "string"}},
        "ambiguity": {"type": "array", "items": _obj(
            {"span": _s(), "type": _s(AMBIGUITY_TYPES)})},
        "validation_targets": {"type": "array", "items": _obj({
            "type": _s(VALIDATION_TYPES), "raw": _s(), "entity": _s(null=True),
            "relation": _s(null=True), "as_of": _s(null=True)})},
    },
    "required": FIELDS,
}

RESPONSE_FORMAT = {"type": "json", "schema": QUERY_FRAME_SCHEMA}


FRAME_SYSTEM = """너는 금융상품 질의를 의미 단위로 분해한다. 지정된 JSON 객체 하나만 출력한다. 설명·코드펜스 금지.

너는 데이터베이스도 온톨로지도 보지 않는다. 따라서:
- fp: 로 시작하는 용어나 영문 컬럼명(crd_grd, du_last_aum 등)을 절대 만들지 마라.
- 사용자가 쓴 한국어 표현을 그대로 보존한다. "신용등급"을 "ratingRank" 로 바꾸지 마라.
- 질문에 없는 것을 채우지 마라. 없으면 빈 배열이거나 null 이다.

[domain_candidates]
bond_kr 국내채권 / etf_kr 국내ETF / etf_gl 해외·미국상장ETF / fund_pub 국내공모펀드
해당 가능성이 있는 것 전부 넣는다. 두 도메인을 함께 묻는 질의가 있고, 확실하지 않으면 복수로 둔다.
KODEX·TIGER·ACE·SOL·PLUS·RISE 같은 국내 운용사 브랜드로 시작하면, 이름에 미국·중국·글로벌 같은
해외 지수가 들어 있어도 국내 상장 상품이라 etf_kr 이다. etf_gl 은 VOO·QQQ 처럼 티커로 부르는 해외 상장분이다.
질의가 상품군을 특정하지 않고 "ETF" 라고만 하면 etf_kr 과 etf_gl 을 둘 다 넣는다.

[task] 위에서부터 훑어 먼저 맞는 것 하나
  recommendation 기준을 사용자가 정하지 않고 "추천"·"좋은"·"괜찮은" 을 요구한다
  relation       상품과 다른 개체(기업·자회사·편입종목·테마·지수) 사이 연결을 따라가야 한다
  comparison     둘 이상을 나란히 놓고 비교·중복도·차이를 요구한다
  explanation    사실 조회가 아니라 이유·구조·동향 설명을 요구한다
  filter_rank    조건으로 거르고 정렬하거나 상위 N 을 요구한다
  lookup         지목한 상품 하나의 속성값을 조회한다

[targets] 찾는 대상의 상품군 표현. "회사채" "국내 ETF" "공모펀드". 고유명은 여기 넣지 않는다.
  질문이 상품군을 말하지 않고 상품 하나만 지목했어도, 그 상품이 속한 종류를 적는다.
  ★ targets 에는 상품 종류만 담는다. 그 상품을 걸러내는 성질(투자지역·투자자산·운용전략·복제방식·
    레버리지·테마)은 targets 가 아니라 constraints 다. 상품군 앞에 수식어가 여러 개 붙어 있으면
    하나로 뭉치지 말고 수식어마다 constraint 를 하나씩 만든다.

[entities] 질의에 나온 고유명을 원문 그대로 자른다.
  role  product(상품명·티커) share_class(펀드 클래스) company issuer index theme manager ticker model
  match_mode  exact 가 기본. 사용자가 "비슷한"·"관련" 이라고 명시했을 때만 partial.

[requested_fields] 보여달라고 한 속성을 자연어 그대로. "발행사" "신용등급" "1년 수익률"

[constraints] 대상을 거르는 조건. 조건 하나가 항목 하나.
  raw              질문에서 잘라온 원문
  field_text       무엇에 대한 조건인지, 사용자의 말로. "신용등급" "순자산" "총보수"
                   ★ 사용자가 쓴 표현을 그대로 옮긴다. 뜻이 비슷한 다른 말로 바꾸지 마라
                     ("환매 가능한" 을 "거래 가능 여부" 로 바꾸는 식은 뒤 단계에서 다른 컬럼을 잡는다).
  operator         >= <= > < == != in contains exists
  value_text       비교값이 문자·범주면 여기. "A+" "회사채" "미국"
  value_num        비교값이 숫자면 여기. 숫자만 넣고 단위는 unit 으로 뺀다.
  unit             "년" "원" "조 원" "%" "달러" 등 사용자가 쓴 단위. 없으면 null.
  kind             quantitative 수치 / categorical 범주 / boolean 여부 / qualitative 주관·모호
  grounding_status 조건이 그대로 데이터에 걸리면 resolved. 조금이라도 해석이 필요하면 unresolved.

  ★ operator 는 사용자가 말한 축 기준으로 적는다.
    "A+ 이상"          → field_text 신용등급, operator ">=",  value_text "A+"
    "듀레이션 4년 미만"  → field_text 듀레이션, operator "<",  value_num 4, unit "년"
    "순자산 2조 원 이상" → field_text 순자산,   operator ">=", value_num 2, unit "조 원"
    "총보수 0.20% 이하"  → field_text 총보수,   operator "<=", value_num 0.20, unit "%"
    등급은 숫자가 작을수록 좋다는 식의 내부 규칙을 알고 있어도 부호를 뒤집지 마라.

  ★ 모호한 말은 풀지 마라.
    "안전한" → {"raw":"안전한","field_text":"안전한","operator":"exists","value_text":null,
                "value_num":null,"unit":null,"kind":"qualitative","grounding_status":"unresolved"}
    여기서 "신용등급 >= AAA" 로 바꾸면 틀린 답이다. 무엇이 안전인지는 다음 단계가 정한다.

[relations] 따라가야 하는 관계 경로.
  raw 원문 / path 개체 이름을 순서대로. ["ETF","편입증권","기업"]  ["기업","자회사","편입종목","ETF"]
  path 의 개체 이름도 한국어로 쓴다. parent_company 같은 영문 식별자를 만들지 마라.

[ordering] field_text 는 사용자의 말, direction 은 asc/desc.
  방향을 말하지 않은 "…순으로"·"…순으로 정리해줘" 는 desc 다 — 큰 값이 먼저다.
  asc 는 "낮은 순"·"적은 순"·"작은 순"·"저렴한 순"처럼 명시했을 때만이다.

[limit] "상위 10개"→10, "5개"→5, "가장 큰 상품"→1. 없으면 null. 임의로 만들지 마라.

[temporal]
  kind  latest_snapshot 최신 갱신일 기준(기본값. "현재"·"최신"도 여기)
        as_of  특정 날짜를 지목했다 / period 기간 구간("최근 6개월") / future 기준일보다 뒤("2027년")
  raw·as_of_text·window_text 는 해당 원문. 없으면 null.

[computation] 단순 조회·필터를 넘어 계산이 필요할 때만.
  overlap_ratio 중복도·중복률 / concentration 집중도 / dedup 중복 제거
  compare 항목 비교 / count 개수 / rank 순위
  "비교해줘"·"차이를 설명해줘"·"어느 쪽이" 가 있으면 compare 를 넣는다.
  "중복도"·"중복률"·"겹치는" 은 overlap_ratio, "중복 제거"·"중복은 빼고" 는 dedup 이다.

[evidence_requirements] 근거로 요구한 것들을 문자열로. "상품번호" "기준일" "편입내역 문서명"

[ambiguity] 데이터 컬럼으로 곧장 안 떨어지는 표현.
  underspecified_criterion 기준 없는 형용사("안전한","좋은","큰")
  ambiguous_domain 어느 상품군인지 갈린다 / ambiguous_entity 어느 상품인지 갈린다
  relation_vs_mention 실제 관계인지 단순 언급인지 구분을 요구한다
  "이름에 …가 있다는 이유만으로 확정하지 말라"는 요구는 ambiguous_entity 다.
  "실제 편입과 단순 언급을 구분하라"는 요구는 relation_vs_mention 이다.
  질문이 상품군을 특정하지 않았다는 것만으로 ambiguous_domain 을 달지는 마라.

[validation_targets] 답하기 전에 실재 여부를 확인해야 하는 것만. 평범한 조회에는 만들지 마라.
  taxonomy_value        정해진 목록이 있는 항목에 목록 밖 값을 걸었다 (등급·통화·지역·자산유형 등)
  temporal_existence    그 대상이 데이터 기준일에 이미 나와 있었는지 확인해야 한다
  entity_existence      그런 이름의 상품이 실제로 있는지 확인해야 한다
  future_value          아직 실현되지 않은 값을 요구한다
  relation_domain_range 관계의 주어·목적어 유형이 어긋난다 (상품 종류가 할 수 없는 일을 시킨다)

★ ambiguity 와 validation_targets 를 헷갈리지 마라. 둘은 반대다.
  ambiguity          말에 기준이 없다. "안전한"·"좋은"·"규모가 큰" — 무엇을 뜻하는지 사람마다 다르다.
  validation_targets 말은 명확한데 그런 값·상품·시점이 실재하지 않을 수 있다.
  등급·통화·지역처럼 정해진 목록이 있는 항목에 목록 밖으로 보이는 값이 오면, 그건 모호한 게 아니라
  존재하지 않는 값이다 — ambiguity 가 아니라 validation_targets(taxonomy_value) 로 보낸다.
  값이 진짜 있는지 없는지는 네가 판정하지 마라. "확인이 필요하다"고 표시만 하는 것이 네 일이다.

해당이 없으면 빈 배열이다. 대부분의 질의는 빈 배열이다.
  이때도 constraints·relations 는 평소대로 채운다. validation_targets 는 거기에 덧붙이는 표시다.

[limit·ordering 과 computation 의 경계] "상위 10개"·"수익률 순으로" 는 ordering 과 limit 으로 충분하다.
computation 에 rank 를 넣지 마라. computation 은 중복률·집중도·중복제거처럼 별도 연산이 필요할 때만이다.

예시 — 평가 문항이 아니라 형식을 보이기 위한 가상 질의다.
"판매 중인 특수채 중 BBB 이상이고 듀레이션이 4년 넘는 종목을 표면금리 낮은 순으로 3개 알려줘"
{"domain_candidates":["bond_kr"],"task":"filter_rank",
 "targets":[{"text":"특수채"}],"entities":[],
 "requested_fields":[{"text":"표면금리"}],
 "constraints":[
  {"raw":"판매 중인","field_text":"판매 여부","operator":"==","value_text":"판매중","value_num":null,
   "unit":null,"kind":"boolean","grounding_status":"resolved"},
  {"raw":"특수채","field_text":"채권 종류","operator":"==","value_text":"특수채","value_num":null,
   "unit":null,"kind":"categorical","grounding_status":"resolved"},
  {"raw":"BBB 이상","field_text":"신용등급","operator":">=","value_text":"BBB","value_num":null,
   "unit":null,"kind":"categorical","grounding_status":"resolved"},
  {"raw":"듀레이션이 4년 넘는","field_text":"듀레이션","operator":">","value_text":null,"value_num":4,
   "unit":"년","kind":"quantitative","grounding_status":"resolved"}],
 "relations":[],"ordering":[{"field_text":"표면금리","direction":"asc"}],"limit":3,
 "temporal":{"kind":"latest_snapshot","raw":null,"as_of_text":null,"window_text":null},
 "computation":[],"evidence_requirements":[],
 "ambiguity":[],"validation_targets":[]}"""


def empty_frame() -> dict:
    """모든 질문이 같은 interface 를 갖는다. 해당 없으면 [] 또는 null."""
    return {"domain_candidates": [], "task": "lookup", "targets": [], "entities": [],
            "requested_fields": [], "constraints": [], "relations": [], "ordering": [],
            "limit": None,
            "temporal": {"kind": "latest_snapshot", "raw": None,
                         "as_of_text": None, "window_text": None},
            "computation": [], "evidence_requirements": [], "ambiguity": [],
            "validation_targets": []}


# 프롬프트로는 안 잡히는 표기 흔들림을 코드가 덮는다. 실측 사례: enum 4건 중 2건이
# "용어정의" 같은 자유 문자열로 돌아왔다(agent-bond-mvp-0822.md §6-2). 자유 문자열은
# 어느 분기 조건에도 안 맞아 기본 경로로 흘러가므로 로그를 봐도 정상처럼 보인다.
_OP_ALIAS = {"≥": ">=", "이상": ">=", "gte": ">=", "=>": ">=",
             "≤": "<=", "이하": "<=", "lte": "<=", "=<": "<=",
             "초과": ">", "gt": ">", "미만": "<", "lt": "<",
             "=": "==", "eq": "==", "같음": "==",
             "<>": "!=", "ne": "!=", "!==": "!=",
             "포함": "contains", "존재": "exists", "있음": "exists"}
_DIR_ALIAS = {"내림차순": "desc", "높은순": "desc", "높은 순": "desc", "descending": "desc",
              "오름차순": "asc", "낮은순": "asc", "낮은 순": "asc", "ascending": "asc"}

# D4 검증용. 1단계는 TBox 도 물리 스키마도 안 보므로 이런 토큰이 나오면 누출이다.
_LEAK = re.compile(r"(?:^|[\s(\[])(fp:[A-Za-z]|[a-z][a-z0-9]*(?:_[a-z0-9]+)+)")


def _enum(val, allowed, alias=None, default=None):
    """enum 값을 강제한다. 반환 (값, 고쳤으면 원본)."""
    if isinstance(val, str):
        v = val.strip()
        if v in allowed:
            return v, None
        v2 = (alias or {}).get(v) or (alias or {}).get(v.lower())
        if v2 in allowed:
            return v2, val
    return default, val


def _num(val):
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    try:
        return float(str(val).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def guard(frame: dict) -> dict:
    """결정적 후처리. 고친 내역은 _guard 에 남겨 조용한 오라우팅을 막는다."""
    out, notes = empty_frame(), []
    if not isinstance(frame, dict):
        return {**out, "_guard": ["frame 이 dict 가 아님"]}

    doms = [d for d in frame.get("domain_candidates") or [] if d in DOMAINS]
    if len(doms) != len(frame.get("domain_candidates") or []):
        notes.append(f"domain_candidates 정리: {frame.get('domain_candidates')} → {doms}")
    out["domain_candidates"] = doms

    task, bad = _enum(frame.get("task"), TASKS, default=None)
    if task is None:
        task = "lookup"
        notes.append(f"task enum 밖: {bad!r} → lookup(잠정)")
    out["task"] = task

    out["targets"] = [{"text": str(t.get("text", "")).strip()}
                      for t in frame.get("targets") or [] if isinstance(t, dict) and t.get("text")]
    out["requested_fields"] = [
        {"text": str(t.get("text", "")).strip()}
        for t in frame.get("requested_fields") or [] if isinstance(t, dict) and t.get("text")]

    for e in frame.get("entities") or []:
        if not isinstance(e, dict) or not e.get("text"):
            continue
        role, br = _enum(e.get("role"), ENTITY_ROLES, default="product")
        mode, bm = _enum(e.get("match_mode"), MATCH_MODES, default="exact")
        if br:
            notes.append(f"entity role enum 밖: {br!r} → product")
        if bm:
            notes.append(f"entity match_mode enum 밖: {bm!r} → exact")
        out["entities"].append({"text": str(e["text"]).strip(), "role": role, "match_mode": mode})

    for c in frame.get("constraints") or []:
        if not isinstance(c, dict):
            continue
        op, bo = _enum(c.get("operator"), OPERATORS, _OP_ALIAS, default="exists")
        kind, bk = _enum(c.get("kind"), CONSTRAINT_KINDS, default="categorical")
        gs, bg = _enum(c.get("grounding_status"), GROUNDING, default="resolved")
        if bo:
            notes.append(f"operator enum 밖: {bo!r} → {op}")
        if bk:
            notes.append(f"constraint kind enum 밖: {bk!r} → categorical")
        if bg:
            notes.append(f"grounding_status enum 밖: {bg!r} → resolved")
        # qualitative 는 정의상 아직 데이터에 안 걸린다. resolved 로 왔다면 그 자체가 모순이다.
        if kind == "qualitative" and gs == "resolved":
            gs = "unresolved"
            notes.append(f"qualitative 인데 resolved: {c.get('raw')!r} → unresolved")
        # 값이 하나뿐인 in 은 == 이다. 모델이 범주 조건에 습관적으로 in 을 쓴다.
        vt = c.get("value_text")
        if op == "in" and isinstance(vt, str) and not re.search(r"[,·/]| 또는 | 및 ", vt):
            op = "=="
            notes.append(f"단일값 in → ==: {c.get('field_text')!r}={vt!r}")
        out["constraints"].append({
            "raw": str(c.get("raw") or "").strip(),
            "field_text": str(c.get("field_text") or "").strip(),
            "operator": op,
            "value_text": (str(c["value_text"]).strip() if c.get("value_text") is not None else None),
            "value_num": _num(c.get("value_num")),
            "unit": (str(c["unit"]).strip() if c.get("unit") else None),
            "kind": kind, "grounding_status": gs})

    for r in frame.get("relations") or []:
        if isinstance(r, dict) and r.get("path"):
            out["relations"].append({"raw": str(r.get("raw") or "").strip(),
                                     "path": [str(p).strip() for p in r["path"] if str(p).strip()]})

    for o in frame.get("ordering") or []:
        if not isinstance(o, dict) or not o.get("field_text"):
            continue
        d, bd = _enum(o.get("direction"), DIRECTIONS, _DIR_ALIAS, default="desc")
        if bd:
            notes.append(f"direction enum 밖: {bd!r} → desc")
        out["ordering"].append({"field_text": str(o["field_text"]).strip(), "direction": d})

    lim = _num(frame.get("limit"))
    out["limit"] = int(lim) if lim and lim > 0 else None
    if frame.get("limit") is not None and out["limit"] is None:
        notes.append(f"limit 무효: {frame.get('limit')!r} → null")

    t = frame.get("temporal") if isinstance(frame.get("temporal"), dict) else {}
    kind, bt = _enum(t.get("kind"), TEMPORAL_KINDS, default="latest_snapshot")
    if bt:
        notes.append(f"temporal kind enum 밖: {bt!r} → latest_snapshot")
    # as_of 는 날짜를 지목했다는 뜻이다. 지목한 날짜가 없거나 "현재"·"최신" 이면
    # 그건 최신 스냅샷을 말한 것이지 특정 시점이 아니다.
    _aot = str(t.get("as_of_text") or "").strip()
    if kind == "as_of" and (not _aot or not re.search(r"\d", _aot)):
        kind = "latest_snapshot"
        notes.append(f"as_of 인데 날짜 없음({_aot or '없음'}) → latest_snapshot")
    out["temporal"] = {"kind": kind,
                       "raw": (str(t["raw"]).strip() if t.get("raw") else None),
                       "as_of_text": (str(t["as_of_text"]).strip() if t.get("as_of_text") else None),
                       "window_text": (str(t["window_text"]).strip() if t.get("window_text") else None)}

    for c in frame.get("computation") or []:
        if not isinstance(c, dict):
            continue
        k, bc = _enum(c.get("kind"), COMPUTATION_KINDS, default=None)
        if k is None:
            notes.append(f"computation kind enum 밖 — 버림: {bc!r}")
            continue
        out["computation"].append({"kind": k, "raw": str(c.get("raw") or "").strip()})

    out["evidence_requirements"] = [str(x).strip() for x in frame.get("evidence_requirements") or []
                                    if str(x).strip()]

    for a in frame.get("ambiguity") or []:
        if not isinstance(a, dict) or not a.get("span"):
            continue
        ty, ba = _enum(a.get("type"), AMBIGUITY_TYPES, default="underspecified_criterion")
        if ba:
            notes.append(f"ambiguity type enum 밖: {ba!r} → underspecified_criterion")
        out["ambiguity"].append({"span": str(a["span"]).strip(), "type": ty})

    for v in frame.get("validation_targets") or []:
        if not isinstance(v, dict):
            continue
        ty, bv = _enum(v.get("type"), VALIDATION_TYPES, default=None)
        if ty is None:
            notes.append(f"validation type enum 밖 — 버림: {bv!r}")
            continue
        out["validation_targets"].append({
            "type": ty, "raw": str(v.get("raw") or "").strip(),
            "entity": (str(v["entity"]).strip() if v.get("entity") else None),
            "relation": (str(v["relation"]).strip() if v.get("relation") else None),
            "as_of": (str(v["as_of"]).strip() if v.get("as_of") else None)})

    # 지목한 상품이 없으면 lookup 일 수 없다 — 조회할 대상이 없기 때문이다.
    # 세 모델 모두 "안전한 ETF 추천해줘" 를 단순조회로 분류했다(test_langgraph.py node_guard).
    if out["task"] == "lookup" and not out["entities"]:
        notes.append("entities 없음 → lookup 기각, filter_rank")
        out["task"] = "filter_rank"
    if out["relations"] and out["task"] in ("lookup", "filter_rank"):
        notes.append(f"relations 있음 → task {out['task']} 기각, relation")
        out["task"] = "relation"

    out["_guard"] = notes
    return out


def leaks(frame: dict) -> list[str]:
    """D4 위반 — 1단계가 만들어선 안 되는 fp: URI·물리 컬럼명. enum 필드는 보지 않는다."""
    t = frame.get("temporal") or {}
    texts = ([x["text"] for x in frame.get("targets") or []]
             + [x["text"] for x in frame.get("entities") or []]
             + [x["text"] for x in frame.get("requested_fields") or []]
             + [s for c in frame.get("constraints") or []
                for s in (c.get("raw"), c.get("field_text"), c.get("value_text"), c.get("unit"))]
             + [s for r in frame.get("relations") or [] for s in [r.get("raw")] + (r.get("path") or [])]
             + [o["field_text"] for o in frame.get("ordering") or []]
             + [c.get("raw") for c in frame.get("computation") or []]
             + list(frame.get("evidence_requirements") or [])
             + [a["span"] for a in frame.get("ambiguity") or []]
             + [s for v in frame.get("validation_targets") or []
                for s in (v.get("raw"), v.get("entity"), v.get("relation"))]
             + [t.get("raw"), t.get("as_of_text"), t.get("window_text")])
    return sorted({m.group(1) for s in texts if s for m in _LEAK.finditer(" " + str(s))})


def to_conditions(frame: dict) -> list[str]:
    """3단계 Planner 계약(wanggyu/agent/state.py: decomposed_conditions: list[str]).

    Frame 을 dict 그대로 넘기기로 팀이 합의하면 이 함수만 버리면 된다.
    """
    out = [f"대상: {t['text']}" for t in frame.get("targets") or []]
    out += [f"엔티티: {e['text']} ({e['role']}, {e['match_mode']} 매칭)"
            for e in frame.get("entities") or []]
    for c in frame.get("constraints") or []:
        val = c.get("value_text") if c.get("value_text") is not None else c.get("value_num")
        unit = f" {c['unit']}" if c.get("unit") else ""
        tail = " — 기준 미확정(해석 필요)" if c["grounding_status"] == "unresolved" else ""
        expr = f"{c['field_text']} {c['operator']}" + (f" {val}{unit}" if val is not None else "")
        out.append(f"조건: {expr}  (원문: {c['raw']}){tail}")
    out += [f"관계: {' → '.join(r['path'])}" for r in frame.get("relations") or []]
    out += [f"정렬: {o['field_text']} {o['direction'].upper()}" for o in frame.get("ordering") or []]
    if frame.get("limit"):
        out.append(f"개수: 상위 {frame['limit']}건")
    tp = frame.get("temporal") or {}
    if tp.get("kind") and tp["kind"] != "latest_snapshot":
        out.append(f"시점: {tp['kind']} ({tp.get('raw') or tp.get('window_text') or tp.get('as_of_text')})")
    out += [f"계산: {c['kind']} ({c['raw']})" for c in frame.get("computation") or []]
    out += [f"요청 필드: {f['text']}" for f in frame.get("requested_fields") or []]
    out += [f"근거 요구: {e}" for e in frame.get("evidence_requirements") or []]
    out += [f"모호: '{a['span']}' — {a['type']}" for a in frame.get("ambiguity") or []]
    out += [f"검증 필요: {v['type']} ({v['raw']})" for v in frame.get("validation_targets") or []]
    return out


def extract(question: str, model: str = MODEL, max_tokens: int = 3072, use_audit: bool = False) -> dict:
    """LLM 1회 호출 → guard.

    모델이 실제로 뱉은 값은 _raw 에 남긴다. guard 가 enum 을 덮어쓰기 때문에,
    구조 유효성(영역 1)은 보정 전 원본으로 재야 의미가 있다.
    """
    note = None
    try:
        text = clova.chat(model, FRAME_SYSTEM, question, max_tokens=max_tokens,
                          response_format=RESPONSE_FORMAT, temperature=0.0)
    except RuntimeError as e:
        # 일부 모델은 중첩 스키마를 거부한다(40001). 그 경우에도 측정은 계속돼야 한다.
        if "40001" not in str(e):
            raise
        text = clova.chat(model, FRAME_SYSTEM, question, max_tokens=max_tokens, temperature=0.0)
        note = "responseFormat 거부(40001) — 프롬프트 전용으로 재시도"
    raw = clova.parse_json_loose(text)
    frame = guard(raw)
    frame["_raw"] = raw
    if note:
        frame["_guard"].append(note)
    if use_audit:
        frame["validation_targets"] = audit(question, model=model)
        frame["_guard"].append("validation_targets 는 별도 감사 호출 결과로 대체")
    return frame

# ── 검증 대상 감사 (별도 호출) ──────────────────────────────────────────────
# 분해와 감사를 한 프롬프트에 같이 시키면 서로 밀어낸다. 실측에서 트리거를 늘릴수록
# 다른 항목이 퇴행했고, 감사를 떼어내자 Validation Recall 이 1/5 → 5/5 로 올랐다.
#
# 이 프롬프트는 신용등급 체계(AAA 가 최상단)와 발행 주체 규칙(발행은 기업이 한다)을
# 명시한다. 1단계는 TBox 를 조회하지 않지만 이 두 사실은 프롬프트에 박혀 있다 —
# 그만큼 q031·q035 를 쉽게 만든다는 뜻이므로 결과를 읽을 때 감안해야 한다.
AUDIT_SYSTEM = """너는 금융상품 질의 하나를 보고, 답하기 전에 확인이 필요한 위험이 있는지만 판정한다.
verdict 를 하나만 고른다. 지정된 JSON 객체 하나만 출력한다. 설명 금지.

normal  확인 없이 진행해도 되는 평범한 질의다. 대부분이 여기 해당한다.
        - 상품 하나를 지목해 속성(발행사·등급·만기일·수익률·보수·순자산)을 묻는다
        - 조건으로 걸러 정렬하거나 상위 N개를 뽑는다
        - 편입종목·자회사·테마·기초지수 같은 관계를 따라간다
        - 둘 이상을 비교하거나 중복도를 계산한다
        상품명·종목번호가 낯설어 보인다는 이유만으로 normal 을 벗어나지 마라. 실재하는 상품도 이름이 낯설다.

아래에 확실히 해당할 때만 normal 을 벗어난다.

taxonomy_value        정해진 목록이 있는 항목에 그 체계에 없는 값을 걸었다.
                      신용등급은 AAA 가 최상단이고 그보다 높은 등급은 없다. 위험등급은 1~6 이다.
temporal_existence    질문에 나온 모델·브랜드·기술의 이름 자체가 최근에 생긴 것 같아,
                      기준일에 이미 존재했는지 의심스럽다. 질문이 무엇을 묻든 이름이 먼저다.
entity_existence      지목한 상품명이 그럴듯하지만 실제로는 없는 이름 같다.
future_value          요구한 값의 시점이 기준일 2026-08-24 보다 뒤다. 아직 실현되지 않은 실적·확정치.
                      질문에 2026-08-24 가 적혀 있는 것은 미래가 아니다. 그건 기준 시점을 못박은
                      것이므로 future_value 가 아니다. 기준일보다 뒤의 연도·기간을 요구할 때만이다.
relation_domain_range 발행의 주어가 상품이다. ETF·펀드·채권 같은 상품이 무언가를 발행했다고 전제할 때만이다.
                      주어가 기업·기관이면 정상이다 — 기업이 채권을 발행하는 것은 당연한 일이다.
                      편입·추종·운용도 상품이 하는 정상 행위이므로 여기 해당하지 않는다.

raw 에는 그렇게 판단한 근거가 된 질문의 원문 조각을 넣는다. normal 이면 null 이다."""

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["normal"] + VALIDATION_TYPES},
                   "raw": {"type": ["string", "null"]}},
    "required": ["verdict", "raw"],
}
AUDIT_FORMAT = {"type": "json", "schema": AUDIT_SCHEMA}


def audit(question: str, model: str = MODEL, max_tokens: int = 384) -> list[dict]:
    """확인이 필요한 지점 하나를 고른다. 판정(ABSTAIN)은 여기서 하지 않는다.

    normal 을 enum 의 첫 값으로 둔 이유는 실측 때문이다. validation_targets 배열만
    내게 하면 배열을 채워야 한다는 압력에 눌려 35문항 전부에 무언가를 만들었고
    (relation_domain_range 28건), 정밀도가 8.6% 까지 떨어졌다.
    "정상" 을 고를 수 있는 선택지로 명시해야 안 만든다.
    """
    text = clova.chat(model, AUDIT_SYSTEM, question, max_tokens=max_tokens,
                      response_format=AUDIT_FORMAT, temperature=0.0)
    got = clova.parse_json_loose(text)
    v = got.get("verdict")
    if v not in VALIDATION_TYPES:      # normal · null · enum 밖은 전부 "없음"
        return []
    return guard({"validation_targets": [{"type": v, "raw": got.get("raw") or ""}]})["validation_targets"]
