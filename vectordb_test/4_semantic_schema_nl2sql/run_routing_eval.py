# -*- coding: utf-8 -*-
"""35문항 A/B/C multi-source routing Planner 실행."""
from __future__ import annotations

import argparse
import json

import run_nl2sql_eval as base

RESULT = base.HERE / "results/routing_raw.json"
PLAN_SCHEMA = {
    "type": "object", "properties": {
        "execution_plan": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "engine": {"type": "string", "enum": ["graph", "rdb", "vector"]},
            "query": {"type": "string"},
            "depends_on": {"type": "array", "items": {"type": "string"}},
        }, "required": ["id", "engine", "query", "depends_on"]}},
        "query_type": {"type": "string"},
    }, "required": ["execution_plan", "query_type"]}
RESPONSE_FORMAT = {"type": "json", "schema": PLAN_SCHEMA}
SYSTEM = """당신은 금융상품 multi-source Query Planner다.
질문과 metadata context만 사용해 graph/rdb/vector 실행계획을 만든다.
graph는 관계·온톨로지, rdb는 수치 필터·정렬·집계, vector는 근거 문서 문장 검색에 쓴다.
선행 결과가 필요한 step만 depends_on으로 연결하고 독립 step은 병렬로 둔다.
질의가 허용값·미래값·도메인 위반인 경우 execution_plan을 비우고 유형6 query_type을 반환한다.
설명이나 markdown 없이 지정된 JSON schema만 반환한다."""


def context_for(condition: str, qid: str, contexts: dict) -> dict:
    return base.context_for(condition, qid, contexts)


def run_one(question: dict, condition: str, context: dict) -> dict:
    user = question["question"] + "\n\nmetadata_context:\n" + json.dumps(
        context, ensure_ascii=False, separators=(",", ":"))
    import time
    started = time.perf_counter()
    try:
        response = base.call_clova(SYSTEM, user, RESPONSE_FORMAT)
        plan = base.clova.parse_json_loose(response)
        error = None
    except Exception as e:
        response, plan, error = None, None, f"{type(e).__name__}: {str(e)[:500]}"
    return {"question_id": question["question_id"], "condition": condition,
            "response": response, "plan": plan, "error": error,
            "latency_seconds": round(time.perf_counter() - started, 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question")
    ap.add_argument("--repeat-selected", action="store_true")
    args = ap.parse_args()
    original = base.run_one
    base.run_one = run_one
    try:
        base.execute("gold_routing.json", RESULT, "routing", context_for,
                     args.question, args.repeat_selected)
    finally:
        base.run_one = original


if __name__ == "__main__":
    main()
