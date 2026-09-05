"""Question-level evidence constraints, independent of evaluation IDs/products."""
from __future__ import annotations

from datetime import date
import calendar
import re


def is_identity_field(label: str) -> bool:
    text = re.sub(r"\s+", "", label)
    return text in {"클래스동일성여부", "클래스동일성", "동일모펀드여부", "동일운용상품여부", "동일상품여부"}


def _non_identity_topics(topics: list[str]) -> list[str]:
    return [t for t in topics if not re.search(r"동일|같은.*펀드|상장\s*클래스|별도\s*상품|동시에\s*나타나는\s*이유", t)]


def restore_explicit_comparators(intent: dict, question: str) -> tuple[dict, list[str]]:
    text = re.sub(r"\s+", "", question).casefold()
    conditions, notes = [], []
    operators = {"큰": "gt", "초과": "gt", "이상": "gte", "작은": "lt", "미만": "lt", "이하": "lte"}
    for original in intent.get("conditions") or []:
        condition = dict(original)
        attribute = re.sub(r"\s+", "", condition.get("attribute", "")).casefold()
        value = re.sub(r"\s+", "", str(condition.get("value", ""))).casefold()
        if attribute and value and condition.get("operator") != "between":
            match = re.search(re.escape(attribute) + r"(?:이|가|은|는)?" + re.escape(value) + r"(?:보다)?(큰|초과|이상|작은|미만|이하)", text)
            if match and condition.get("operator") != operators[match[1]]:
                condition["operator"] = operators[match[1]]
                notes.append(f"원문 경계조건 보존: {attribute} {condition['operator']} {value}; 초과/이상을 바꾸지 않습니다.")
        conditions.append(condition)
    output = dict(intent.get("output_requirements") or {})
    sort_attribute = (intent.get("sort") or {}).get("attribute") or ""
    if sort_attribute.endswith("수익률") and re.sub(r"\s+", "", sort_attribute).casefold() in text:
        fields = list(output.get("fields") or [])
        if "수익률" in fields and sort_attribute != "수익률":
            output["fields"] = [sort_attribute if f == "수익률" else f for f in fields]
            notes.append(f"일반 '수익률' 출력 요청은 원문에 명시된 정렬 지표 '{sort_attribute}'로 구체화했습니다.")
    sort = dict(intent.get("sort") or {})
    if sort.get("limit") and not re.search(r"\d+\s*(?:개(?!월)|종목|종|위)|가장|최대|최소|top\s*\d+", question, re.IGNORECASE):
        sort["limit"] = ""
        notes.append("원문에 개수 제한·최상위 요청이 없어 임의로 추가된 결과 개수 제한을 제거했습니다.")
    return {**intent, "conditions": conditions, "output_requirements": output, "sort": sort}, notes


def restore_relative_event_window(intent: dict, question: str, *, today: date | None = None) -> tuple[dict, list[str]]:
    """Fix invented event dates only for explicit relative-month requests.

    This does not manufacture event history, use a return period as an event
    filter, or override a user-specified absolute reference date.
    """
    match = re.search(r"최근\s*(\d{1,2})\s*개월", question)
    if not match or not re.search(r"이력|사건|뉴스", question) or re.search(r"20\d{2}[-/.년]", question):
        return intent, []
    months = int(match[1])
    if not 1 <= months <= 60:
        return intent, []
    today = today or date.today()
    index = today.year * 12 + today.month - 1 - months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    start = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    conditions, changed = [], False
    for original in intent.get("conditions") or []:
        condition = dict(original)
        if re.sub(r"\s+", "", condition.get("attribute", "")) in {"사건일", "사건발생일"}:
            condition.update(operator="between", value=start.isoformat(), value_2=today.isoformat(),
                             time_window_relative=f"최근 {months}개월")
            changed = True
        conditions.append(condition)
    if not changed:
        return intent, []
    return {**intent, "conditions": conditions}, [f"상대 사건 기간을 실행일 {today} 기준 {start}~{today}로 복구했습니다. 기간 이력 데이터의 존재는 별도로 검증합니다."]


GRAPH_FIELD_CONCEPTS = {"편입비중", "종목별비중", "편입기준일", "편입내역기준일"}
DOCUMENT_EVIDENCE_CONCEPTS = {
    "문서명", "편입내역문서명", "근거문장", "근거원문", "인용문",
    "documentname", "citationtext", "evidencetext",
}


def is_document_evidence_field(label: str) -> bool:
    """Document citations are evidence metadata, never an RDB column guess."""
    normalized = re.sub(r"\s+", "", str(label or "")).casefold()
    return (
        normalized in DOCUMENT_EVIDENCE_CONCEPTS
        or normalized.endswith("문서명")
        or normalized.endswith("근거문장")
    )


def _graph_output_aliases(outputs: list[dict], *property_names: str) -> list[str]:
    """Return declared aliases for exact ontology property local names."""
    suffixes = tuple(
        suffix
        for name in property_names
        for suffix in (f"#{name}", f":{name}")
    )
    return [
        str(output.get("alias"))
        for output in outputs
        if output.get("alias") and str(output.get("property") or "").endswith(suffixes)
    ]


def graph_field_evidence(label: str, product_code: str, results: dict) -> dict | None:
    normalized = re.sub(r"\s+", "", label)
    if normalized not in GRAPH_FIELD_CONCEPTS or not product_code:
        return None
    entries = []
    sources = []
    matched_relation = False
    for _sid, result in results.items():
        if result.get("engine") != "graph" or result.get("status") != "ok":
            continue
        plan = result.get("graph_plan") or {}
        outputs = plan.get("outputs") or []
        codes = _graph_output_aliases(outputs, "productCode")
        weights = _graph_output_aliases(outputs, "weight")
        dates = _graph_output_aliases(outputs, "asOf")
        source_ids = _graph_output_aliases(outputs, "sourceId")
        requested_aliases = weights if "비중" in normalized else dates
        # Theme/product classification queries can return the same productCode,
        # but they are not holdings evidence.  Ignore them instead of appending
        # an empty dict that is later rendered as ``[{}, {}]``.
        if not codes or not requested_aliases:
            continue
        for row in result.get("rows") or []:
            if not any(str(row.get(k, "")) == str(product_code) for k in codes):
                continue
            matched_relation = True
            detail = {
                alias: row.get(alias)
                for alias in requested_aliases
                if row.get(alias) not in (None, "")
            }
            if not detail:
                continue
            entries.append(detail)
            sources.extend(
                f"Graph 편입 원천={row.get(alias)}"
                for alias in source_ids
                if row.get(alias) not in (None, "")
            )
    if not entries:
        if matched_relation:
            return {
                "field": label,
                "column": None,
                "value": None,
                "status": "null",
                "source_columns": list(dict.fromkeys(sources)),
                "detail": "편입 관계는 확인했지만 요청한 편입 수치가 비어 있어 임의 값으로 대체하지 않습니다.",
            }
        return None
    return {"field": label, "column": None, "value": entries, "status": "available",
            "source_columns": list(dict.fromkeys(sources)),
            "detail": "RDB 상품 식별자와 Graph productCode를 정확히 대조한 편입 기록입니다. 기준일이 다른 현재 비중이나 문서 원문으로 대체하지 않습니다."}


def request_blockers(intent: dict, question: str, *, today: date | None = None) -> list[str]:
    blockers = []
    if intent.get("issuer_type_conflict"):
        blockers.append(intent["issuer_type_conflict"])
    today = today or date.today()
    # Completed calendar-year observations cannot be replaced by a rolling rate.
    if "수익률" in question and any(w in question for w in ("연간", "확정", "연도별")):
        for year in re.findall(r"(?<!\d)(20\d{2})\s*년", question):
            if date(int(year), 12, 31) >= today:
                blockers.append(f"{year}년 전체 기간이 아직 끝나지 않아 확정 연간수익률을 확인할 수 없습니다. "
                                "현재의 1년 수익률이나 전망치로 대신하지 않습니다.")
    conditions = intent.get("conditions") or []
    relations = intent.get("relations") or []
    if not relations and not intent.get("identity_comparison"):
        unbound = []
        for entity in intent.get("target_entities") or []:
            text = entity.get("surface_form") or ""
            if entity.get("entity_type") == "product_name" or not text:
                continue
            if not any(text.casefold() in str(c.get("value", "")).casefold() for c in conditions):
                unbound.append(text)
        if intent.get("task") == "relation" or (unbound and re.search(r"관련|연결|편입|보유|자회사", question)):
            blockers.append(f"{', '.join(unbound) or '요청한 개체'}와 상품을 연결하는 관계를 확정하지 못했습니다. "
                            "편입, 발행, 테마, 운용 중 어떤 관계인지 또는 정확한 상품 식별자를 알려주세요. "
                            "조건 없는 전체 상품 목록을 관련 상품으로 제공하지 않습니다.")
    return blockers


def restore_class_comparison(intent: dict, question: str) -> tuple[dict, list[str]]:
    """Recover explicit 'base의 class A와 B' syntax, not a fund-specific list."""
    match = re.search(r"([^.!?]+?)의\s*([A-Za-z][A-Za-z0-9-]*)\s*(?:와|과|및)\s*([A-Za-z][A-Za-z0-9-]*)\s*클래스", question)
    if not match or not any(w in question for w in ("동일", "같은", "비교")):
        return intent, []
    relations = intent.get("relations") or []
    if any(r.get("relation") not in {"has_class", "class_of", "same_fund", "same_as"} for r in relations):
        return intent, []
    base, *classes = match.groups()
    base = base.strip()
    output = dict(intent.get("output_requirements") or {})
    fields = list(output.get("fields") or [])
    fields.extend(f for f in ("운용사종목번호", "대표예탁원종목번호", "예탁원종목번호", "운용회사대외기관코드") if f not in fields)
    output["fields"] = fields
    output["narrative_topics"] = _non_identity_topics(output.get("narrative_topics") or [])
    # A class code alone is not a global product search term. The base name is
    # the scope and suffixes are checked on returned source names, exactly.
    fixed = {**intent, "task": "comparison", "relations": [],
             "target_entities": [{"entity_type": "product_name", "surface_form": base}],
             "identity_comparison": {"base": base, "classes": classes},
             "product_domain": [{"domain": "펀드", "subtype": []}], "output_requirements": output}
    fixed["conditions"] = [c for c in intent.get("conditions") or []
                           if not ("모펀드" in c.get("attribute", "") and str(c.get("value", "")) == base)]
    return fixed, ["명시된 클래스 비교를 원천 종목과 운용사·대표종목 키 대조로 처리합니다. 클래스 코드를 독립 상품명으로 검색하지 않습니다."]


def restore_cross_market_identity(intent: dict, question: str) -> tuple[dict, list[str]]:
    domains = {d.get("domain") for d in intent.get("product_domain") or []}
    if not {"국내ETF", "펀드"} <= domains or not re.search(r"동일|같은|별도\s*상품", question):
        return intent, []
    if not any(e.get("entity_type") == "product_name" for e in intent.get("target_entities") or []):
        return intent, []
    if intent.get("relations"):
        return intent, []
    output = dict(intent.get("output_requirements") or {})
    fields = list(output.get("fields") or [])
    fields.extend(f for f in ("상품동일성키", "상장일") if f not in fields)
    output["fields"] = fields
    output["narrative_topics"] = _non_identity_topics(output.get("narrative_topics") or [])
    return {**intent, "output_requirements": output, "identity_comparison": {"mode": "cross_market"}}, [
        "동일 상품 비교에 원천 식별키를 조회합니다. 펀드 예탁원종목번호와 ETF 종목번호의 일치만 연결 근거로 사용합니다."]


def render_identity_comparison(state: dict) -> str:
    request = (state.get("intent") or {}).get("identity_comparison")
    if not request:
        return ""
    if request.get("mode") == "cross_market":
        fund_rows, etf_rows = [], []
        for result in (state.get("step_results") or {}).values():
            if result.get("engine") != "rdb" or result.get("error") or result.get("skipped_reason"):
                continue
            if result.get("domain") == "펀드":
                fund_rows.extend(result.get("rows") or [])
            elif result.get("domain") == "국내ETF":
                etf_rows.extend(result.get("rows") or [])
        links = [(f, e) for f in fund_rows for e in etf_rows
                 if f.get("ksd_itm_no") and str(f["ksd_itm_no"]).strip() == str(e.get("pd_itm_no", "")).strip()]
        if not links:
            return "동일 상품 관계: 펀드 예탁원종목번호와 ETF 종목번호의 일치 근거를 확보하지 못했습니다. 이름만으로 동일/별도 상품을 확정하지 않습니다."
        return "\n".join("동일 운용상품 관계: 펀드 " + str(f.get("itm_no")) + " ↔ ETF " + str(e.get("pd_itm_no"))
                         + f". raw.prfd01n001.ksd_itm_no={f['ksd_itm_no']}와 raw.pref01n001.pd_itm_no가 일치합니다. "
                           "데이터셋별 별도 레코드이며, 이 연결만으로 클래스 종류나 현재 거래 가능 여부까지 확정하지 않습니다."
                         for f, e in links)
    rows = [r for result in (state.get("step_results") or {}).values()
            if result.get("engine") == "rdb" and result.get("domain") == "펀드"
            and not result.get("error") and not result.get("skipped_reason")
            for r in result.get("rows") or []]
    matched = []
    for suffix in request["classes"]:
        candidates = [r for r in rows if re.search(r"(?:Class|종류)\s*" + re.escape(suffix) + r"$", str(r.get("itm_nm", "")), re.IGNORECASE)]
        if len(candidates) != 1:
            return f"클래스 동일성: {suffix}를 원천 종목 하나로 확정하지 못해 판정할 수 없습니다. 정확한 종목번호가 필요합니다."
        matched.append(candidates[0])
    def valid(value):
        return bool(value and str(value).strip() and not re.fullmatch(r"(?:KR)?0+", str(value).strip()))
    keys = [(r.get("or_co_xtn_itt_cd"), r.get("mtco_itm_no")) for r in matched]
    if any(not all(valid(v) for v in key) for key in keys):
        return "클래스 동일성: 운용회사 코드 또는 운용사종목번호가 미확보여서 동일 모펀드 여부를 확인할 수 없습니다."
    if len(set(keys)) != 1:
        return "클래스 동일성: 운용회사·운용사종목번호가 달라 동일 모펀드라고 확정할 수 없습니다."
    refs = [r.get("rptt_ksd_itm_no") for r in matched]
    return (f"클래스 동일성: 원천 운용회사 코드={keys[0][0]}, 운용사종목번호={keys[0][1]}가 일치하여 "
            "동일 모펀드의 클래스 그룹으로 확인됩니다. 개별 종목번호는 별개입니다. "
            f"대표예탁원종목번호 대조값={refs}. 근거: raw.prfd01n001의 "
            "or_co_xtn_itt_cd, mtco_itm_no, rptt_ksd_itm_no. 이름 유사성만으로 판정한 것이 아닙니다.")
