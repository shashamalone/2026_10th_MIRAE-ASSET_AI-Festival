"""
analyze_intent_node의 LLM 구조화 출력에 대한 결정론적 후처리(guard).

LLM이 enum 값을 정확히 지키지 못하거나(HCX-007 구조화 출력에서 실측된 문제 -
schemas.py 모듈 docstring 참고), 필드 간에 서로 모순되는 값을 낼 때가 있다.
이 값들을 plan_query_db.py/utils.py에 넘기기 전에 결정론적으로 교정한다.
LLM을 다시 부르지 않는다 - 전부 문자열 매칭/치환 규칙이다.
"""
from __future__ import annotations

import re

_OPERATOR_ALIASES = {
    "eq": "eq", "=": "eq", "==": "eq", "인": "eq",
    "gte": "gte", ">=": "gte", "이상": "gte",
    "lte": "lte", "<=": "lte", "이하": "lte",
    "gt": "gt", ">": "gt", "초과": "gt",
    "lt": "lt", "<": "lt", "미만": "lt",
    "ne": "ne", "!=": "ne", "<>": "ne",
    "between": "between", "사이": "between",
    "contains": "contains", "포함": "contains", "관련": "contains",
}
_ALLOWED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "between", "contains"}

_EXPLICIT_OVERSEAS_ETF_SCOPE = re.compile(
    r"(?:해외\s*ETF|(?:해외|미국|중국|홍콩|일본|유럽)\s*(?:증시|거래소)?\s*(?:상장|거래)|"
    r"NYSE|NASDAQ|AMEX|HKEX|SSE|SZSE)",
    re.IGNORECASE,
)

_ORDER_ALIASES = {"asc": "asc", "오름차순": "asc", "desc": "desc", "내림차순": "desc"}


def _fix_condition(c: dict) -> tuple[dict, list[str]]:
    notes: list[str] = []
    c = dict(c)
    if re.sub(r"\s+", "", c.get("attribute", "")) in {"매수가능여부", "구매가능여부"}:
        c["attribute"] = "판매가능여부"
        notes.append("매수/구매 가능 여부를 판매가능여부 정책 개념으로 정규화 (수량의 true 비교 금지)")
    operator = (c.get("operator") or "").strip()

    if operator and operator not in _ALLOWED_OPERATORS:
        # 값이 콤마 없는 단일 값이면서 operator가 "in"이면 "eq"로 정규화한다.
        # 그 외 enum 밖 값은 별칭 매핑으로 되돌리고, 매핑도 없으면 건드리지
        # 않는다(다음 단계가 unresolved 개념으로 안전하게 처리하게 둔다).
        value = c.get("value") or ""
        if operator.lower() == "in" and "," not in value:
            c["operator"] = "eq"
            notes.append(f"조건 '{c.get('attribute')}': operator 'in'(단일값) -> 'eq' 정규화")
        elif operator.lower() in _OPERATOR_ALIASES:
            fixed = _OPERATOR_ALIASES[operator.lower()]
            c["operator"] = fixed
            notes.append(f"조건 '{c.get('attribute')}': operator '{operator}' -> '{fixed}' 정규화")

    if c.get("kind") == "qualitative" and c.get("grounding_status") == "resolved":
        c["grounding_status"] = "unresolved"
        notes.append(
            f"조건 '{c.get('attribute')}': kind=qualitative인데 grounding_status=resolved로 "
            f"옴 -> unresolved로 정정"
        )

    return c, notes


def _fix_sort(sort: dict) -> tuple[dict, list[str]]:
    notes: list[str] = []
    sort = dict(sort)
    order = (sort.get("order") or "").strip()
    if order and order not in ("asc", "desc"):
        fixed = _ORDER_ALIASES.get(order.lower())
        if fixed:
            sort["order"] = fixed
            notes.append(f"sort.order '{order}' -> '{fixed}' 정규화")
    return sort, notes


def _fix_relation(r: dict) -> tuple[dict, list[str]]:
    notes: list[str] = []
    r = dict(r)
    if (r.get("object_ref") or "").strip() and (r.get("object_entity") or "").strip():
        notes.append(
            f"relation '{r.get('id')}': object_entity='{r['object_entity']}'와 "
            f"object_ref='{r['object_ref']}'가 동시에 채워짐 -> object_entity 비움"
        )
        r["object_entity"] = ""
    return r, notes


def _strip_blank_strings(values: list) -> list:
    """리스트 필드에서 공백/빈 문자열 원소만 걷어낸다. "" != []이므로
    output_requirements.fields: [""]는 `not fields`로 안 걸러진다 - 이
    경우 collect_needed_concepts(utils.py)가 ""를 개념명으로 취급해
    카탈로그/LLM 폴백 둘 다 당연히 못 찾고, RDB 단계 전체가 "미해결
    개념: ['']"으로 건너뛰어진다(2026-09-02 실측, "캠브리콘이 편입된
    중국 반도체 ETF" 질문에서 발견 - 이 질문은 Graph 쪽이 먼저 막혀서
    결과에 영향은 없었지만, Graph가 성공하는 질문에서는 이 때문에 RDB만
    조용히 스킵될 수 있다)."""
    return [v for v in values if str(v or "").strip()]


_DOMAIN_LABEL_WORDS = {"채권", "국내ETF", "해외ETF", "펀드", "ETF", "ETN", "공모펀드"}

_OUTPUT_FIELD_ALIASES = {
    "ETF명": "상품명",
    "ETN명": "상품명",
}


def _fix_output_requirements(output_req: dict, domain_names: set[str]) -> tuple[dict, list[str]]:
    """output_requirements.fields/narrative_topics에서 빈 문자열과
    "도메인 이름 자체"를 걸러낸다.

    "SK하이닉스가 발행한 채권과 SK하이닉스를 편입한 ETF 알려줘"처럼 두
    상품군을 나란히 요청하는 복합 문장에서, LLM이 product_domain에 이미
    담은 "채권"/"ETF"를 output_requirements.fields에도 그대로 중복해서
    넣는 사례가 실측됐다(2026-09-02). "채권"·"ETF"는 실제 컬럼 개념이
    아니라서 collect_needed_concepts(utils.py)가 카탈로그/LLM 폴백 둘 다
    못 찾거나(그 도메인엔 존재하지 않는 개념) 엉뚱한 컬럼에 잘못
    매칭시켜서(예: "ETF"가 발행사 컬럼에 매칭됨) RDB 단계가 조용히
    스킵되거나 의미 없는 필드를 SELECT하게 된다."""
    notes: list[str] = []
    output_req = dict(output_req)
    blocked = _DOMAIN_LABEL_WORDS | domain_names
    for key in ("fields", "narrative_topics"):
        original = output_req.get(key) or []
        cleaned = _strip_blank_strings(original)
        dropped = [v for v in cleaned if v in blocked]
        cleaned = [v for v in cleaned if v not in blocked]
        normalized = [_OUTPUT_FIELD_ALIASES.get(v, v) for v in cleaned]
        if normalized != cleaned:
            notes.append(
                f"output_requirements.{key}: 사용자 별칭 정규화 {cleaned!r} -> {normalized!r}"
            )
        cleaned = list(dict.fromkeys(normalized))
        if cleaned != original:
            output_req[key] = cleaned
            notes.append(f"output_requirements.{key}: 무효 원소 제거 {original!r} -> {cleaned!r}"
                         + (f" (도메인 이름: {dropped})" if dropped else ""))
    return output_req, notes


# attribute가 이 표의 키와 정확히 일치하는 조건만 relations로 재분류한다 -
# 새 관계 이름을 추측하지 않는다(아래 _extract_relation_conditions 참고).
_RELATION_WORDS = {
    "편입": "holds", "보유": "holds", "포함": "holds", "편입종목": "holds",
    "자회사": "subsidiary_of", "계열사": "subsidiary_of", "출자": "subsidiary_of",
}


def _extract_relation_conditions(intent: dict) -> tuple[list[dict], list[dict], list[str]]:
    """attribute가 관계를 나타내는 동사/명사(예: "편입", "보유", "자회사")인
    조건을 relations로 재분류한다.

    이런 표현은 RDB 컬럼이 아니라 두 엔티티 사이의 관계인데, LLM이
    "SK하이닉스가 발행한 채권과 SK하이닉스를 편입한 ETF"류 복합 문장에서
    "발행사"(실제 RDB 컬럼 개념)와 "편입"(관계, RDB 컬럼 없음)을 구분하지
    못하고 둘 다 conditions로 뽑는 사례가 실측됐다(2026-09-02). 그 결과
    RDB 쪽엔 애초에 존재하지 않는 "편입" 개념을 카탈로그에서 못 찾고
    SQL 생성 LLM이 되는대로 조건을 지어냈다 - 정작 GraphDB에는 이 관계
    데이터가 이미 있었다(직접 SPARQL로 확인, 해당 사례에서 ETF 10건
    이상 실재).

    이 표에 있는 단어와 정확히 일치할 때만 변환한다 - 없는 단어에 대해
    관계 이름을 추측하지 않는다. subject_domain은 조건의 domain을 그대로
    물려받는다(비어 있으면 여러 도메인에 공통 적용된다는 기존 관례를
    그대로 따른다). object의 entity_role은 "company"로 둔다 - 이 표의
    관계들은 전부 대상이 회사(피편입·피출자 대상)인 경우가 압도적이다."""
    conditions = intent.get("conditions") or []
    remaining: list[dict] = []
    new_relations: list[dict] = []
    notes: list[str] = []
    existing_ids = {r.get("id") for r in intent.get("relations") or []}
    counter = 0

    for c in conditions:
        attribute = (c.get("attribute") or "").strip()
        predicate = _RELATION_WORDS.get(attribute)
        value = (c.get("value") or "").strip()
        if predicate and value and (c.get("applies_to") or "target") == "target":
            counter += 1
            new_id = f"RG{counter}"
            while new_id in existing_ids:
                counter += 1
                new_id = f"RG{counter}"
            existing_ids.add(new_id)
            new_relations.append({
                "id": new_id,
                "subject_domain": c.get("domain", ""),
                "relation": predicate,
                "object_entity": value,
                "object_ref": "",
                "time_window_relative": c.get("time_window_relative", ""),
                "entity_role": "company",
                "path": [],
            })
            notes.append(
                f"조건 '{attribute}'={value!r} -> relations로 재분류 "
                f"(subject_domain={c.get('domain') or '(공통)'}, relation={predicate})"
            )
        else:
            remaining.append(c)

    return remaining, new_relations, notes


_THEME_PATTERN = re.compile(r"([가-힣A-Za-z0-9]+)\s*(?:테마|섹터)")


def _extract_theme_relations(intent: dict) -> tuple[list[dict], list[str]]:
    """"OOO 테마"/"OOO 섹터"류 표현이 relations 어디에도(entity_role="theme")
    안 잡혔으면 raw_question에서 직접 뽑아 relations에 추가한다.

    2026-09-02 실측: "미래에셋에서 운용하는 반도체 테마 국내ETF..." 질문에서
    LLM이 relations를 완전히 빈 배열로 반환하고 "반도체"를 어디에도
    구조화된 형태로 안 남겼다(product_domain.subtype엔 "테마형"이라는
    두루뭉술한 값만 있었다). 그런데도 최종 답은 우연히 맞았는데, SQL 생성
    LLM이 원본 질문 텍스트를 보고 즉흥적으로 `pd_nm LIKE '%반도체%'`를
    끼워 넣은 것이지 검증된 개념 처리가 아니었다 - ontology/common.ttl의
    fp:relatedToTheme 주석도 "상품명에 테마어가 있다는 사실만으로 관계를
    확정하지 않는다"고 명시한다. 상품명에 테마 단어가 없는 경우(영문/지수
    기반 브랜드 등)엔 이 즉흥 SQL 방식이 조용히 틀리거나 불완전한 답을
    낼 수 있다. 이 사례 이후 prompts.py의 few-shot 예시도 "테마는
    conditions가 아니라 relations"로 함께 고쳤다 - 이 함수는 LLM이 그래도
    놓쳤을 때의 안전망이다.

    한 질문에 테마 키워드가 여러 개(예: "반도체와 2차전지 테마 ETF") 있을
    수 있어 첫 매치만 찾는 re.search 대신 re.finditer로 전부 찾는다.
    "관련"처럼 테마 외의 뜻으로도 흔히 쓰이는 일반 단어는 오탐(false
    positive)이 잦을 위험이 커서 패턴에 넣지 않았다 - "테마"/"섹터"만큼
    이 맥락에서 뜻이 좁고 분명한 단어로 제한한다.

    이미 relations에 entity_role="theme"인 항목이 있으면(LLM이 제대로
    뽑은 경우) 아무것도 안 한다 - 이 함수는 순수 안전망이다. subject_domain은
    product_domain의 첫 도메인을 물려받는다(비어 있으면 여러 도메인에 공통
    적용된다는 기존 relations 관례를 따른다)."""
    relations = intent.get("relations") or []
    if any(r.get("entity_role") == "theme" for r in relations):
        return [], []
    keywords = list(dict.fromkeys(
        m.group(1) for m in _THEME_PATTERN.finditer(intent.get("raw_question") or "")
    ))
    if not keywords:
        return [], []
    domains = [d.get("domain", "") for d in (intent.get("product_domain") or [])
               if isinstance(d, dict)]
    subject_domain = domains[0] if domains else ""
    existing_ids = {r.get("id") for r in relations}
    new_relations, notes = [], []
    counter = 0
    for keyword in keywords:
        counter += 1
        new_id = f"RT{counter}"
        while new_id in existing_ids:
            counter += 1
            new_id = f"RT{counter}"
        existing_ids.add(new_id)
        new_relations.append({
            "id": new_id, "subject_domain": subject_domain,
            "relation": "tagged_with", "object_entity": keyword, "object_ref": "",
            "time_window_relative": "", "entity_role": "theme", "path": [],
        })
        notes.append(f"'{keyword} 테마/섹터' 표현 -> relations로 재분류 (entity_role=theme, relation=tagged_with)")
    return new_relations, notes


_ETF_SCOPE_WORDS = {"국내", "해외", "상장", "주식", "실제", "관련", "편입된", "보유한"}


def _extract_compound_etf_theme_relations(intent: dict) -> tuple[list[dict], list[str]]:
    """Recover an explicit two-token ETF descriptor omitted as a theme relation.

    A holdings question such as ``중국 반도체 ETF`` can be returned by the
    intent model with ``subtype=["반도체"]`` and no theme relation.  ``반도체``
    is not an RDB product subtype, while the complete phrase is two independent
    Graph taxonomy facets.  Only recover the phrase when all of these facts are
    explicit in the model output and question: a holdings relation, a domestic
    ETF domain, the reported subtype, and exactly one adjacent descriptor token
    before that subtype and ``ETF``/``ETN``.  The Graph resolver still has to
    verify both facets; this guard never invents a product list or answer value.
    """
    relations = list(intent.get("relations") or [])
    if any(relation.get("entity_role") == "theme" for relation in relations):
        return [], []
    if not any(relation.get("relation") in {"holds", "holding", "held_by", "편입", "보유"}
               for relation in relations):
        return [], []

    raw_question = str(intent.get("raw_question") or "")
    new_relations, notes = [], []
    existing_ids = {relation.get("id") for relation in relations}
    counter = 0
    seen_themes: set[str] = set()
    for domain_item in intent.get("product_domain") or []:
        domain = str(domain_item.get("domain") or "")
        if domain != "국내ETF":
            continue
        for subtype in _strip_blank_strings(domain_item.get("subtype") or []):
            subtype_text = str(subtype).strip()
            pattern = re.compile(
                rf"(?<![가-힣A-Za-z0-9])([가-힣A-Za-z0-9]+)\s+"
                rf"{re.escape(subtype_text)}\s*(?:ETF|ETN|상장지수(?:펀드|상품)?)",
                re.IGNORECASE,
            )
            for match in pattern.finditer(raw_question):
                descriptor = match.group(1).strip()
                if descriptor.casefold() in {word.casefold() for word in _ETF_SCOPE_WORDS}:
                    continue
                theme = f"{descriptor} {subtype_text}"
                normalized = re.sub(r"\s+", "", theme).casefold()
                if normalized in seen_themes:
                    continue
                seen_themes.add(normalized)
                counter += 1
                relation_id = f"RT{counter}"
                while relation_id in existing_ids:
                    counter += 1
                    relation_id = f"RT{counter}"
                existing_ids.add(relation_id)
                new_relations.append({
                    "id": relation_id, "subject_domain": domain,
                    "relation": "tagged_with", "object_entity": theme, "object_ref": "",
                    "time_window_relative": "", "entity_role": "theme", "path": [],
                })
                notes.append(
                    f"질문에 명시된 '{theme} ETF/ETN' 표현을 Graph 테마 관계로 복원했습니다."
                )
    return new_relations, notes


def _drop_redundant_theme_conditions(conditions: list[dict], relations: list[dict]) -> tuple[list[dict], list[str]]:
    """"테마"는 RDB 컬럼이 아니라 GraphDB의 fp:relatedToTheme 관계로만
    표현 가능한 개념이다(ontology/common.ttl 주석: "상품명에 테마어가
    있다는 사실만으로 관계를 확정하지 않는다"). 그런데도 LLM(특히
    verify_intent_node의 judge 재검토 패스)이 relations에 이미
    entity_role="theme" 관계가 있는데도 conditions에 "테마"=값 조건을
    중복으로 남기는 사례가 실측됐다(2026-09-02, "미래에셋에서 운용하는
    반도체 테마 국내ETF..." 질문 - analyze_intent_node 직후엔
    _extract_theme_relations가 relations만 정확히 채웠는데, 그 뒤
    verify_intent_node가 같은 스키마로 다시 호출되면서 relations는 그대로
    둔 채 conditions에 "테마"="반도체"를 추가로 만들어냈다). 이 조건은
    어떤 도메인 카탈로그에도 실제 컬럼이 없어 build_resolved_schema가
    "미해결 개념"으로 판단해 RDB 단계 전체를 스킵시킨다 - Graph 쪽은 이미
    정확히 63건을 찾아 §8 핸드오프까지 끝냈는데도 이 중복 조건 하나
    때문에 최종 SQL이 아예 안 만들어지는 구조였다. theme relation과 같은
    값을 가리키는 "테마" 조건만 제거한다 - 다른 조건(운용사 등)은
    건드리지 않는다."""
    theme_values = {
        (r.get("object_entity") or "").strip()
        for r in relations if r.get("entity_role") == "theme"
    }
    kept, notes = [], []
    for c in conditions:
        attribute = (c.get("attribute") or "").strip()
        value = (c.get("value") or "").strip()
        if attribute == "테마" and value in theme_values:
            notes.append(f"조건 '테마'={value!r}: 이미 relations에 동일 테마 관계가 있어 중복 제거")
            continue
        kept.append(c)
    return kept, notes

def _drop_redundant_superlative_conditions(conditions: list[dict], sort: dict) -> tuple[list[dict], list[str]]:
    """"가장 큰/가장 작은/최고/최소" 같은 최상급 표현은 sort(attribute+order+limit)
    로만 표현해야 하는데, analyze_intent_node(또는 verify_intent_node의 재검토
    패스)가 같은 attribute를 conditions에도 값 없이(value="") 중복으로 남기는
    사례가 실측됐다(2026-09-06, "국내 상장 ETF 중 총보수율이 가장 낮은 상품은?"
    질문 - sort는 {attribute:"총보수율", order:"asc", limit:"1"}로 정확히
    들어갔는데 conditions에 {attribute:"총보수율", operator:"lte", value:""}가
    그대로 남아 있었다).

    INTENT_VERIFICATION_SYSTEM_PROMPT(prompts.py)에 "이런 조건은 지우고 sort로
    옮기라"는 규칙이 이미 있지만, LLM 검수가 매번 그 규칙을 지키는 건 아니다.
    utils.build_resolved_schema는 값이 빈 조건을 발견하면(SQL이 깨지는 걸
    막으려고) invalid_conditions로 등록해 RDB 단계 전체를 차단한다 - sort가
    이미 같은 attribute를 정확히 담고 있다면 그 빈 조건은 100% 잉여물이므로,
    LLM 재검토에만 기대지 않고 여기서 확정적으로 제거한다.

    sort.attribute와 다른 attribute, 값이 채워진 조건, sort 자체가 없는 경우는
    전혀 건드리지 않는다 - "sort와 정확히 같은 attribute + 빈 값"이라는 좁은
    신호만 보고, 진짜 유효하지 않은 조건(예: 오타)까지 여기서 삼키지 않는다.
    도메인이 다르게 지정된 조건(예: 비교형 질문에서 sort.domains에 없는
    도메인의 조건)도 건드리지 않는다."""
    sort_attribute = ((sort or {}).get("attribute") or "").strip()
    if not sort_attribute:
        return conditions, []

    sort_domains = {d for d in ((sort or {}).get("domains") or []) if d}

    kept, notes = [], []
    for c in conditions:
        attribute = (c.get("attribute") or "").strip()
        value = (c.get("value") or "").strip()
        condition_domain = (c.get("domain") or "").strip()
        same_scope = not sort_domains or not condition_domain or condition_domain in sort_domains
        if attribute == sort_attribute and not value and same_scope:
            notes.append(
                f"조건 '{attribute}'=''(빈 값): sort.attribute와 동일한 최상급 "
                f"표현의 잔여물로 판단해 제거 (정렬 limit={sort.get('limit') or '?'}로 이미 표현됨)"
            )
            continue
        kept.append(c)
    return kept, notes

def _drop_redundant_theme_subtypes(product_domains: list[dict],
                                    relations: list[dict]) -> tuple[list[dict], list[str]]:
    """Graph 테마와 같은 상품 subtype을 RDB 가상 필터로 중복 실행하지 않는다."""
    themes_by_domain: dict[str, list[str]] = {}
    for relation in relations:
        if relation.get("entity_role") != "theme":
            continue
        domain = str(relation.get("subject_domain") or "")
        value = re.sub(r"\s+", "", str(relation.get("object_entity") or "")).casefold()
        if value:
            themes_by_domain.setdefault(domain, []).append(value)

    fixed, notes = [], []
    for item in product_domains:
        domain = str(item.get("domain") or "")
        theme_values = themes_by_domain.get(domain, [])
        kept = []
        for subtype in item.get("subtype") or []:
            key = re.sub(r"\s+", "", str(subtype)).casefold()
            if key and any(key in theme for theme in theme_values):
                notes.append(
                    f"{domain} 하위유형 {subtype!r}: 동일 값이 Graph 테마 관계에 있어 RDB 중복 필터에서 제거"
                )
            else:
                kept.append(subtype)
        fixed.append({**item, "subtype": kept})
    return fixed, notes


def _normalize_product_relations(intent: dict) -> tuple[dict, list[str]]:
    """Use explicit path endpoints, never unrelated question clauses, as scope.

    A Company -> Holding -> Product path returns products, not companies.
    A named company issuing bonds is already a catalogue-backed issuer filter.
    Only redundant positive holding flags with a bound relation are removed.
    """
    domains = [d.get("domain") for d in intent.get("product_domain") or []]
    conditions = list(intent.get("conditions") or [])
    relations, notes = [], []
    referenced = {r.get("object_ref") for r in intent.get("relations") or []}
    companies = {e.get("surface_form") for e in intent.get("target_entities") or []
                 if e.get("entity_type", "").casefold() in {"company", "organization", "issuer"}}
    used_ids = {r.get("id") for r in intent.get("relations") or []}
    for original in intent.get("relations") or []:
        relation = dict(original)
        predicate = relation.get("relation", "").casefold()
        path = " ".join(str(p) for p in relation.get("path") or []).casefold()
        name = relation.get("object_entity")
        if (predicate in {"발행", "issued_by", "issuedby", "issues"} and name in companies
                and "채권" in domains and ("채권" in path or "bond" in path)
                and not relation.get("object_ref") and relation.get("id") not in referenced):
            condition = {"domain": "채권", "attribute": "발행사", "operator": "eq", "value": name,
                         "value_2": "", "kind": "categorical", "applies_to": "target", "grounding_status": "resolved"}
            if not any(c.get("domain") == "채권" and c.get("attribute") in {"발행사", "발행기관"} and c.get("value") == name for c in conditions):
                conditions.append(condition)
            notes.append("명시된 회사→채권 발행 경로를 원본 발행사 컬럼 조건으로 연결했습니다.")
            continue
        if predicate in {"편입", "보유", "holding", "held_by", "holds"}:
            relation["relation"] = "holds"
            if name in companies:
                relation["entity_role"] = "company"
            if (relation.get("subject_domain", "").casefold() in {"company", "기업", "회사"}
                    and re.search(r"상품|product|etf|펀드", path)):
                targets = [d for d in domains if d in {"국내ETF", "해외ETF", "펀드"}]
                # Do not split an intermediate referenced node: its successors
                # need a single explicit result identity.
                if targets and relation.get("id") not in referenced:
                    for index, domain in enumerate(targets):
                        rid = relation.get("id") if index == 0 else f"{relation.get('id')}_scope{index}"
                        while index and rid in used_ids:
                            rid += "x"
                        used_ids.add(rid)
                        relations.append({**relation, "id": rid, "subject_domain": domain})
                    notes.append(f"회사→편입→상품 경로의 반환 범위를 {targets}로 정정했습니다.")
                    continue
        relations.append(relation)
    held_domains = {r.get("subject_domain") for r in relations if r.get("relation") == "holds"
                    and (r.get("object_entity") or r.get("object_ref"))}
    kept = []
    for c in conditions:
        if (re.sub(r"\s+", "", c.get("attribute", "")) in {"편입여부", "보유여부"}
                and str(c.get("value", "")).lower() in {"true", "1", "y"}
                and c.get("operator") == "eq" and c.get("domain") in held_domains):
            notes.append(f"{c.get('domain')} 편입 여부는 명시된 Graph 관계로 검증하므로 중복 가상 컬럼을 제거했습니다.")
        else:
            kept.append(c)
    product_domains = [dict(item) for item in intent.get("product_domain") or []]
    raw_question = str(intent.get("raw_question") or "")
    has_holding_relation = any(r.get("relation") == "holds" for r in relations)
    unqualified_etf = (
        has_holding_relation
        and re.search(r"(?:ETF|상장지수)", raw_question, re.IGNORECASE)
        and not _EXPLICIT_OVERSEAS_ETF_SCOPE.search(raw_question)
    )
    # "중국 반도체 ETF"의 중국은 투자지역/테마이지 상장 시장 지정이 아니다.
    # 적재된 보유관계가 국내 상장 ETF productCode를 반환하는데 분석기가
    # 해외ETF로 잡으면 Graph 성공 뒤 RDB에서 전부 0건이 된다. 해외 상장·
    # 거래소를 명시하지 않은 편입 ETF 질문만 국내ETF로 안전하게 교정한다.
    if unqualified_etf and any(item.get("domain") == "해외ETF" for item in product_domains):
        product_domains = [
            {**item, "domain": "국내ETF"} if item.get("domain") == "해외ETF" else item
            for item in product_domains
        ]
        relations = [
            {**relation, "subject_domain": "국내ETF"}
            if relation.get("subject_domain") in {"ETF", "해외ETF"} else relation
            for relation in relations
        ]
        notes.append("상장 시장을 명시하지 않은 편입 ETF 질문의 해외ETF 오분류를 국내ETF로 교정했습니다.")

    fixed = {**intent, "product_domain": product_domains,
             "relations": relations, "conditions": kept}
    if not relations and intent.get("relations") and intent.get("task") == "relation":
        fixed["task"] = "filter_rank"
    return fixed, notes


def guard_intent(intent: dict) -> tuple[dict, list[str]]:
    """analyze_intent_node의 구조화 출력을 결정론적으로 교정한다.
    (교정된 intent, 변경 로그) 튜플을 돌려준다. 변경이 없으면 로그는 빈
    리스트다."""
    notes: list[str] = []
    intent, relation_notes = _normalize_product_relations(intent)
    notes.extend(relation_notes)
    fixed = dict(intent)
    fixed["product_domain"] = [{**d, "subtype": _strip_blank_strings(d.get("subtype") or [])}
                               for d in intent.get("product_domain") or []]

    # 조건으로 잘못 들어온 관계 표현을 relations로 먼저 옮긴 뒤, 남은
    # conditions와 relations(새로 옮겨진 것 포함) 각각을 마저 교정한다.
    raw_conditions, extracted_relations, extract_notes = _extract_relation_conditions(intent)
    notes.extend(extract_notes)

    fixed_conditions = []
    for c in raw_conditions:
        fc, cnotes = _fix_condition(c)
        fixed_conditions.append(fc)
        notes.extend(cnotes)
    fixed["conditions"] = fixed_conditions

    sort = intent.get("sort") or {}
    if sort:
        fixed_sort, snotes = _fix_sort(sort)
        fixed["sort"] = fixed_sort
        notes.extend(snotes)

    theme_relations, theme_notes = _extract_theme_relations(intent)
    notes.extend(theme_notes)
    compound_theme_relations, compound_theme_notes = _extract_compound_etf_theme_relations({
        **intent,
        "relations": list(intent.get("relations") or []) + theme_relations,
    })
    theme_relations.extend(compound_theme_relations)
    notes.extend(compound_theme_notes)

    fixed_relations = []
    for r in list(intent.get("relations") or []) + extracted_relations + theme_relations:
        fr, rnotes = _fix_relation(r)
        fixed_relations.append(fr)
        notes.extend(rnotes)
    fixed["relations"] = fixed_relations

    fixed_domains, subtype_notes = _drop_redundant_theme_subtypes(
        fixed.get("product_domain") or [], fixed_relations
    )
    fixed["product_domain"] = fixed_domains
    notes.extend(subtype_notes)

    fixed_conditions, drop_notes = _drop_redundant_theme_conditions(fixed_conditions, fixed_relations)
    notes.extend(drop_notes)

    fixed_conditions, superlative_drop_notes = _drop_redundant_superlative_conditions(
        fixed_conditions, fixed.get("sort") or {}
    )
    notes.extend(superlative_drop_notes)

    fixed["conditions"] = fixed_conditions

    output_req = intent.get("output_requirements") or {}
    if output_req:
        domain_names = {
            d.get("domain", "") for d in (intent.get("product_domain") or [])
            if isinstance(d, dict)
        }
        fixed_output_req, onotes = _fix_output_requirements(output_req, domain_names)
        fixed["output_requirements"] = fixed_output_req
        notes.extend(onotes)

    relations = fixed_relations
    task = intent.get("task", "")
    # relations가 있으면 이 질문은 정의상 관계형이다. comparison(관계를 낀
    # 비교)만 예외로 허용하고, 그 외 값(lookup/filter_rank/explanation/
    # recommendation 등 - 실측으로 LLM이 이 중 아무거나 잘못 낼 수 있음을
    # 확인했다)은 전부 relation으로 재분류한다.
    if relations and task not in ("relation", "comparison"):
        fixed["task"] = "relation"
        notes.append(f"relations가 있는데 task='{task}' -> 'relation'으로 재분류")

    return fixed, notes
