#!/usr/bin/env python3
"""저장 Query Frame으로 RDB/unsupported 경계와 cutoff safety를 회귀 검사한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tools.route import MAX_PLAN_STEPS, QUERY_TYPES, ROUTE_SCHEMA, select_route  # noqa: E402
from tools.schema_context import ground, metadata  # noqa: E402
from tools.validate import validate_query  # noqa: E402

FRAMES = ROOT / "vectordb_test/4_query_frame_v1/results/frames_HCX-007_audit.jsonl"
QUESTIONS = ROOT / "vectordb_test/5_semantic_schema_nl2sql/gold/expected_queries_35.json"
RDB_IDS = {"q001", "q002", "q003", "q005", "q006", "q007", "q008", "q009",
           "q010", "q011", "q012", "q013", "q017", "q018"}
UNSUPPORTED_IDS = {"q020", "q022", "q029"}


def main() -> None:
    frames = {x["question_id"]: x for x in
              map(json.loads, FRAMES.read_text(encoding="utf-8").splitlines())}
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    qmap = {f"q{int(x['id']):03d}": x["question"] for x in questions}
    for qid in RDB_IDS:
        frame = frames[qid]
        plan = ground(qmap[qid], frame)
        assert plan["domain"] and not plan["unresolved"], (qid, plan)
        route = select_route(frame, plan)
        assert route["query_type"] == "rdb_only", (qid, route)
        assert len(route["execution_plan"]) <= MAX_PLAN_STEPS
    for qid in UNSUPPORTED_IDS:
        frame = frames[qid]
        plan = ground(qmap[qid], frame)
        assert select_route(frame, plan)["query_type"] == "unsupported", qid

    assert ROUTE_SCHEMA["properties"]["query_type"]["enum"] == list(QUERY_TYPES)
    assert ROUTE_SCHEMA["properties"]["execution_plan"]["maxItems"] == 3

    metadata.cache_clear()
    safe = {"domain": "etf_gl", "unresolved": [], "as_of": {"value": "2026-06-14"}}
    assert validate_query("2026-08-24 기준 Kimi 관련 상품", safe)["code"] \
        == "ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF"
    assert validate_query("2027년 확정 연간수익률", safe)["code"] \
        == "ABSTAIN_FUTURE_DATA"
    late = {**safe, "as_of": {"value": "2026-08-21"}}
    assert validate_query("VOO를 알려줘", late)["code"] == "ABSTAIN_CUTOFF_VIOLATION"
    assert validate_query("VOO를 알려줘", safe) is None
    print("PASS route guard — RDB 14/14, unsupported 3/3, cutoff safety 4/4")


if __name__ == "__main__":
    main()
