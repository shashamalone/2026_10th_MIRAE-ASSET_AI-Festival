# -*- coding: utf-8 -*-
"""질문 원문 + guarded Query Frame → verified LogicalPlan 후보.

Query Frame은 후보를 주지만 권위가 아니다. 모든 항목은 metadata binding에 다시
연결하고, 한국어 큰 수·등급 방향·단위는 결정적으로 재해석한다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from config import ROOT

_CLEAN = re.compile(r"[\s()\[\]{}·・,'\"’“”._/\-]")


def norm(value) -> str:
    return _CLEAN.sub("", str(value or "")).lower()


@lru_cache(maxsize=1)
def metadata() -> tuple[dict, dict, dict[str, dict]]:
    schema = json.loads((ROOT / "metadata/schema_bindings.json").read_text(encoding="utf-8"))
    rules = json.loads((ROOT / "metadata/business_rules.json").read_text(encoding="utf-8"))
    return schema, rules, {b["id"]: b for b in schema["bindings"]}


def _matches(text: str, alias: str) -> bool:
    a, t = norm(alias), norm(text)
    return bool(a and t and (a == t or a in t or t in a))


def best_binding(text: str, domain: str, usage: str) -> str | None:
    _, _, bindings = metadata()
    choices = []
    for position, b in enumerate(bindings.values()):
        if b["domain"] != domain or usage not in b["usage"]:
            continue
        for alias in b["aliases"]:
            if _matches(text, alias):
                exact = int(norm(text) == norm(alias))
                choices.append((exact, len(norm(alias)), -position, b["id"]))
    return max(choices)[3] if choices else None


def _domain(question: str, frame: dict) -> tuple[str | None, list[str]]:
    entities = frame.get("entities") or []
    if any(e.get("role") == "ticker" and re.fullmatch(r"[A-Za-z.]{1,8}", e.get("text", ""))
           for e in entities):
        return "etf_gl", []
    q = norm(question)
    if "해외etf" in q or "미국주식형etf" in q or "해외채권etf" in q:
        return "etf_gl", []
    lexical = []
    if "공모펀드" in q or "투자신탁" in q or "mmf" in q:
        lexical.append("fund_pub")
    if "국내etf" in q or "연금거래" in q:
        lexical.append("etf_kr")
    if "채권" in q or "국채" in q:
        lexical.append("bond_kr")
    candidates = list(dict.fromkeys(lexical + list(frame.get("domain_candidates") or [])))
    if len(lexical) == 1:
        return lexical[0], []
    if len(candidates) == 1:
        return candidates[0], []
    return None, [f"domain 후보를 하나로 확정할 수 없음: {candidates or '없음'}"]


def _number(raw: str, fallback) -> float | int | None:
    text = str(raw or "").replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(천억|조|억|만)", text)
    if m:
        scale = {"만": 10_000, "억": 100_000_000, "천억": 100_000_000_000,
                 "조": 1_000_000_000_000}[m.group(2)]
        out = float(m.group(1)) * scale
        return int(out) if out.is_integer() else out
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m and fallback is None:
        out = float(m.group(1))
        return int(out) if out.is_integer() else out
    return fallback


def _append_unique(items: list, item: dict, keys=("binding", "operator", "value")) -> None:
    sig = tuple(item.get(k) for k in keys)
    if not any(tuple(x.get(k) for k in keys) == sig for x in items):
        items.append(item)


def _constraint(c: dict, domain: str) -> tuple[dict | None, str | None]:
    raw = c.get("raw") or ""
    if "최신" in raw and ("갱신" in raw or "기준" in raw):
        return None, None
    # 08-24 배포분의 buyable_quantity는 무효다. 기존 평가 문항의 명시적
    # '매수가능수량 > 0' 표현도 값을 조회하지 않고 만기 미도래 정의로 치환한다.
    compact = norm(raw)
    if domain == "bond_kr" and any(
            x in compact for x in ("매수가능", "매수할수있는", "구매가능")):
        return {"binding": "bond.remaining_days", "operator": ">", "value": 0,
                "unit": "day", "raw": raw}, None
    binding_id = best_binding(c.get("field_text") or raw, domain, "filter")
    if not binding_id:
        binding_id = best_binding(raw, domain, "filter")
    if not binding_id:
        return None, f"조건 binding 미확정: {raw or c.get('field_text')}"
    _, rules, bindings = metadata()
    binding = bindings[binding_id]
    op = c.get("operator") or "=="
    value = _number(raw, c.get("value_num"))
    if value is None:
        value = c.get("value_text")

    if binding_id == "bond.rating_rank":
        rank = rules["rating_rank"].get(str(c.get("value_text") or "").upper())
        if rank is None:
            return None, f"허용되지 않은 신용등급: {c.get('value_text')}"
        value = rank
        op = {">=": "<=", ">": "<", "<=": ">=", "<": ">"}.get(op, op)
    elif binding_id == "bond.remaining_days" and c.get("unit") == "년":
        value = int(value * 365)
    elif binding_id in rules.get("categorical_values", {}):
        mapped = rules["categorical_values"][binding_id].get(str(value))
        if mapped is None:
            return None, f"허용되지 않은 범주값: {binding_id}={value}"
        value = mapped
        if binding_id == "etf_kr.trading_suspended" and op == "!=":
            op, value = "==", "0"
        else:
            op = "=="
    if op not in {"==", "!=", ">", ">=", "<", "<=", "in", "contains"}:
        return None, f"허용되지 않은 연산자: {op}"
    return {"binding": binding_id, "operator": op, "value": value,
            "unit": binding.get("unit"), "raw": raw}, None


def ground(question: str, frame: dict) -> dict:
    schema, rules, bindings = metadata()
    if frame.get("_error"):
        return {"domain": None, "entities": [], "select": [], "filters": [], "order": [],
                "limit": None, "unresolved": ["Query Frame 추출 실패"], "concepts": []}
    domain, unresolved = _domain(question, frame)
    if not domain:
        return {"domain": None, "entities": [], "select": [], "filters": [], "order": [],
                "limit": None, "unresolved": unresolved, "concepts": []}
    spec = schema["domains"][domain]
    selected = [spec["id"], spec["name"]]
    texts = [x.get("text", "") for x in frame.get("requested_fields") or []]
    texts += list(frame.get("evidence_requirements") or [])
    for text in texts:
        hit = best_binding(text, domain, "select")
        if hit and hit not in selected:
            selected.append(hit)
        nt = norm(text)
        if domain == "etf_gl" and "기준일" in nt and any(x in nt for x in ("가격", "현재가", "거래량")) \
                and "etf_gl.close_date" not in selected:
            selected.append("etf_gl.close_date")
    if domain == "etf_kr" and "etf_kr.expense_ratio" in selected \
            and "etf_kr.expense_source" not in selected:
        selected.append("etf_kr.expense_source")
    if domain == "bond_kr" and "원본등급값" in norm(question) and "온톨로지분류값" in norm(question):
        for item in ("bond.credit_rating", "bond.rating_norm"):
            if item not in selected:
                selected.append(item)
    if domain == "fund_pub" and frame.get("task") == "comparison":
        for item in ("fund.manager_code", "fund.representative_code"):
            if item not in selected:
                selected.append(item)

    filters = []
    for item in rules.get("mandatory_filters", {}).get(domain, []):
        _append_unique(filters, dict(item))
    qn = norm(question)
    purchase_redefined = domain == "bond_kr" and any(
        x in qn for x in ("매수가능", "매수할수있는", "구매가능"))
    if purchase_redefined:
        selected = [x for x in selected if x != "bond.buyable_quantity"]
        if frame.get("task") != "lookup":
            selected = ["bond.applied_yield" if x == "bond.buy_yield" else x
                        for x in selected]
    for target in rules.get("target_filters", []):
        if target["domain"] == domain and any(norm(p) in qn for p in target["phrases"]):
            for item in target["filters"]:
                _append_unique(filters, dict(item))

    raw_entities = frame.get("entities") or []
    entities = []
    if domain == "fund_pub" and len(raw_entities) > 1 \
            and any(e.get("role") == "share_class" for e in raw_entities):
        stem = next((e["text"] for e in raw_entities if e.get("role") != "share_class"), "")
        classes = [e["text"] for e in raw_entities if e.get("role") == "share_class"]
        entities.append({"mode": "fund_classes", "stem": stem, "classes": classes})
    elif raw_entities:
        entity = raw_entities[0]
        field = spec["name"]
        if domain == "etf_gl" and entity.get("role") == "ticker":
            field = "etf_gl.ticker"
        elif domain == "etf_kr":
            field = "etf_kr.short_name"
        entities.append({"mode": "exact", "binding": field, "value": entity.get("text", "")})

    for c in frame.get("constraints") or []:
        # 엔티티 문자열을 상품번호 constraint로 중복 생성한 모델 출력은 사용하지 않는다.
        if entities and c.get("value_text") and any(
                norm(c["value_text"]) == norm(e.get("value")) for e in entities):
            continue
        item, error = _constraint(c, domain)
        if item:
            _append_unique(filters, item)
        elif error:
            unresolved.append(error)
    if "bond.rating_rank" in selected and "bond.credit_rating" not in selected:
        selected.insert(selected.index("bond.rating_rank"), "bond.credit_rating")

    order = []
    for item in frame.get("ordering") or []:
        hit = best_binding(item.get("field_text", ""), domain, "sort")
        if hit:
            grounded_order = {"binding": hit, "direction": item.get("direction", "desc")}
            default = next((x for x in rules.get("default_order", {}).get(domain, [])
                            if x["binding"] == hit), None)
            if default and default.get("nulls"):
                grounded_order["nulls"] = default["nulls"]
            order.append(grounded_order)
        else:
            unresolved.append(f"정렬 binding 미확정: {item.get('field_text')}")
    if not order and frame.get("task") in {"filter_rank", "comparison"}:
        order = [dict(x) for x in rules.get("default_order", {}).get(domain, [])]
    elif order:
        # 같은 값일 때 결과를 결정적으로 만들기 위한 ID tie-breaker.
        if not any(x["binding"] == spec["id"] for x in order):
            order.append({"binding": spec["id"], "direction": "asc"})
    if purchase_redefined and frame.get("task") != "lookup":
        for item in order:
            if item["binding"] == "bond.buy_yield":
                item["binding"] = "bond.applied_yield"

    referenced = selected + [x.get("binding") for x in filters + order]
    concepts = list(dict.fromkeys(bindings[x]["concept_uri"] for x in referenced
                                  if x in bindings and bindings[x].get("concept_uri")))
    return {"domain": domain, "task": frame.get("task"), "entities": entities,
            "select": selected, "filters": filters, "order": order,
            "limit": frame.get("limit"), "unresolved": unresolved, "concepts": concepts,
            "as_of": rules["domain_as_of"][domain]}
