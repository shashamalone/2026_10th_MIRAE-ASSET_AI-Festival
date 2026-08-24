# -*- coding: utf-8 -*-
"""근거가 있는 경우에만 ABSTAIN을 확정하는 결정적 validator."""
from __future__ import annotations

import re
from datetime import date

from tools.schema_context import metadata


def _result(code: str, reason: str, evidence: list[dict] | None = None) -> dict:
    return {"code": code, "reason": reason, "evidence": evidence or []}


def validate_query(question: str, grounded: dict) -> dict | None:
    """실행 전 검증. Query Frame audit 결과를 권위로 사용하지 않는다."""
    _, rules, _ = metadata()
    if not grounded.get("domain"):
        return _result("ABSTAIN_UNRESOLVED_QUERY", "; ".join(grounded.get("unresolved") or ["도메인 미확정"]))
    q = question.upper()
    rating = re.search(r"신용등급(?:이|은|\s)*([A-Z]{1,4}[+-]?)", q)
    if rating and rating.group(1) not in rules["rating_rank"]:
        return _result("ABSTAIN_INVALID_TAXONOMY", f"허용 신용등급에 {rating.group(1)}가 없습니다.",
                       [{"source": "ontology/common.ttl", "rule": "ratingRank 1(AAA)~19(C)"}])
    years = [int(x) for x in re.findall(r"(?<!\d)(20\d{2})년", question)]
    if years and max(years) > date.fromisoformat(rules["data_cutoff"]).year and "확정" in question:
        return _result("ABSTAIN_FUTURE_DATA", f"{max(years)}년 확정 실현값은 기준일 현재 존재하지 않습니다.",
                       [{"as_of": rules["data_cutoff"]}])
    if grounded["domain"] == "etf_gl" and "발행한 회사채" in question:
        return _result("ABSTAIN_DOMAIN_MISMATCH", "ETF는 회사채의 발행 주체가 될 수 없습니다.",
                       [{"source": "ontology/bond_kr.ttl", "rule": "issuedBy domain Bond"}])
    if grounded.get("unresolved"):
        return _result("ABSTAIN_UNRESOLVED_QUERY", "; ".join(grounded["unresolved"]))
    return None


def validate_entity_count(count: int, entity: dict) -> dict | None:
    if count:
        return None
    label = entity.get("value") or entity.get("stem") or "지정 상품"
    return _result("ABSTAIN_ENTITY_NOT_FOUND", f"완전일치 상품을 찾지 못했습니다: {label}")


def validate_rows(rows: list[dict], max_rows: int) -> dict | None:
    if len(rows) > max_rows:
        return _result("ABSTAIN_RESULT_TOO_LARGE", f"결과가 안전 상한 {max_rows:,}행을 초과했습니다.")
    return None
