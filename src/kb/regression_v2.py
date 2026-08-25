# -*- coding: utf-8 -*-
"""35문항 fixture 계약과 배포된 Agent의 근거/기권 동작을 회귀 검사한다."""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "expected_question" / "2026_expected_queries.csv"
ABSTAIN_PREFIX = "ABSTAIN_"
MAX_CASE_SECONDS = 15.0


def load_cases() -> list[dict[str, str]]:
    with FIXTURE.open(encoding="utf-8-sig", newline="") as handle:
        cases = list(csv.DictReader(handle))
    required = {"id", "question", "required_evidence", "expected_behavior"}
    if len(cases) != 35:
        raise ValueError(f"회귀 문항 수 불일치: {len(cases)} != 35")
    if set(cases[0]) < required:
        raise ValueError(f"회귀 fixture 필드 누락: {sorted(required - set(cases[0]))}")
    if [row["id"] for row in cases] != [str(number) for number in range(1, 36)]:
        raise ValueError("회귀 문항 id는 1..35 순서여야 합니다")
    for row in cases:
        if not all(row.get(field, "").strip() for field in required):
            raise ValueError(f"회귀 문항 {row.get('id')} 필수값 누락")
        behavior = row["expected_behavior"]
        if behavior != "ANSWER" and not behavior.startswith(ABSTAIN_PREFIX):
            raise ValueError(f"회귀 문항 {row['id']} 알 수 없는 expected_behavior={behavior}")
    return cases


def find_value(payload: Any, names: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in names and value not in (None, "", [], {}):
                return value
        for value in payload.values():
            found = find_value(value, names)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_value(value, names)
            if found not in (None, "", [], {}):
                return found
    return None


def required_evidence(case: dict[str, str]) -> list[dict[str, str]]:
    labels = [item.strip() for item in case["required_evidence"].split(";") if item.strip()]
    return [
        {"code": f"Q{int(case['id']):02d}_E{index:02d}", "label": label}
        for index, label in enumerate(labels, 1)
    ]


def evidence_records(payload: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if "requirement_code" in payload or "requirement_codes" in payload:
            records.append(payload)
        for value in payload.values():
            records.extend(evidence_records(value))
    elif isinstance(payload, list):
        for value in payload:
            records.extend(evidence_records(value))
    return records


def validate_required_evidence(case: dict[str, str], evidence: Any) -> None:
    requirements = required_evidence(case)
    records = evidence_records(evidence)
    by_code: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        codes = record.get("requirement_codes", record.get("requirement_code", []))
        if isinstance(codes, str):
            codes = [codes]
        if not isinstance(codes, list):
            continue
        for code in codes:
            by_code.setdefault(str(code), []).append(record)
    missing = [item for item in requirements if item["code"] not in by_code]
    if missing:
        detail = ", ".join(f"{item['code']}({item['label']})" for item in missing)
        raise ValueError(f"문항별 필수 evidence 누락: {detail}")
    locator_fields = {
        "source_column",
        "source_columns",
        "ontology_predicate",
        "ontology_predicates",
        "document_id",
        "field",
        "path",
        "column",
    }
    value_fields = {"value", "evidence_value", "claim", "result", "status", "exists"}
    for requirement in requirements:
        valid = False
        for record in by_code[requirement["code"]]:
            has_label = record.get("requirement_label") == requirement["label"]
            has_subject = any(record.get(key) not in (None, "", [], {}) for key in ("subject", "product_id", "entity_id"))
            has_source = record.get("source") not in (None, "", [], {})
            has_date = any(record.get(key) not in (None, "", [], {}) for key in ("as_of", "published_at"))
            has_locator = any(record.get(key) not in (None, "", [], {}) for key in locator_fields)
            has_value = any(record.get(key) not in (None, "", [], {}) for key in value_fields)
            if has_label and has_subject and has_source and has_date and has_locator and has_value:
                valid = True
                break
        if not valid:
            raise ValueError(
                f"{requirement['code']}({requirement['label']}): "
                "label/subject/source/date/locator/value 구조 불충족"
            )


def enforce_case_deadline(case_id: str, elapsed: float) -> None:
    if elapsed > MAX_CASE_SECONDS:
        raise TimeoutError(f"문항 {case_id}: {elapsed:.3f}초 > {MAX_CASE_SECONDS:.1f}초")


def validate_answer(case: dict[str, str], payload: Any) -> None:
    expected = case["expected_behavior"]
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    evidence = find_value(payload, {"evidence", "sources", "citations", "retrieved_context"})
    if expected.startswith(ABSTAIN_PREFIX):
        if expected not in serialized:
            raise ValueError(f"expected {expected}, response에 동일한 기권 코드 없음")
        if not evidence:
            raise ValueError("ABSTAIN 응답에 검증 evidence/retrieved_context 없음")
        validate_required_evidence(case, evidence)
        return
    answer = find_value(payload, {"answer", "final_answer", "content", "text"})
    if not answer:
        raise ValueError("ANSWER 응답에 answer/content 없음")
    if not evidence:
        raise ValueError("ANSWER 응답에 evidence/sources/citations 없음")
    evidence_text = json.dumps(evidence, ensure_ascii=False, default=str).lower()
    if not any(key in evidence_text for key in ("source", "출처", "document", "table")):
        raise ValueError("근거에 출처 식별자가 없음")
    if not any(key in evidence_text for key in ("as_of", "published_at", "기준일", "발행일")):
        raise ValueError("근거에 실질 기준일/발행일이 없음")
    validate_required_evidence(case, evidence)


def run_live(cases: list[dict[str, str]], endpoint: str, timeout: float) -> dict[str, Any]:
    token = os.environ.get("AGENT_API_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout, headers=headers) as client:
        for case in cases:
            started = time.perf_counter()
            try:
                response = client.post(endpoint, json={"question": case["question"]})
            except httpx.TimeoutException as exc:
                raise TimeoutError(f"문항 {case['id']}: {MAX_CASE_SECONDS:.1f}초 제한 내 응답 없음") from exc
            elapsed = time.perf_counter() - started
            enforce_case_deadline(case["id"], elapsed)
            response.raise_for_status()
            payload = response.json()
            validate_answer(case, payload)
            results.append({"id": case["id"], "expected": case["expected_behavior"], "seconds": round(elapsed, 3)})
    return {"mode": "live", "endpoint": endpoint, "passed": len(results), "cases": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="금융상품 Agent v2 35문항 회귀")
    parser.add_argument("--check", action="store_true", help="네트워크 호출 없이 fixture 계약만 검사")
    parser.add_argument("--endpoint", default=os.environ.get("AGENT_QUERY_URL"))
    parser.add_argument("--timeout", type=float, default=MAX_CASE_SECONDS)
    args = parser.parse_args()
    cases = load_cases()
    if not 0 < args.timeout <= MAX_CASE_SECONDS:
        parser.error(f"--timeout은 0초 초과 {MAX_CASE_SECONDS:.1f}초 이하여야 합니다")
    if args.check:
        result = {"mode": "check", "mutated_files": False, "network_calls": 0, "cases": len(cases)}
    else:
        if not args.endpoint:
            parser.error("live 회귀에는 --endpoint 또는 AGENT_QUERY_URL이 필요합니다")
        result = run_live(cases, args.endpoint, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
