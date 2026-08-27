#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RDB 단독 14문항 grounding/compiler 회귀 및 선택적 DB execution test.

    python3 script/test_rdb_vertical_slice.py
    python3 script/test_rdb_vertical_slice.py --db
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from config import BOND_DSN  # noqa: E402
from agent.agent_core import APP, to_response  # noqa: E402
from agent.nodes import render_answer  # noqa: E402
from tools import rdb  # noqa: E402
from tools.schema_context import ground, metadata  # noqa: E402
from tools.validate import validate_query  # noqa: E402

QF = ROOT / "test/vectordb_test/4_query_frame_v1/results/frames_HCX-007_audit.jsonl"
GOLD_DIR = ROOT / "test/vectordb_test/5_semantic_schema_nl2sql/gold"
IDS = ["q001", "q002", "q003", "q005", "q006", "q007", "q008", "q009",
       "q010", "q011", "q012", "q013", "q017", "q018"]


def load_inputs():
    questions = json.loads((GOLD_DIR / "expected_queries_35.json").read_text(encoding="utf-8"))["questions"]
    qmap = {f"q{int(x['id']):03d}": x["question"] for x in questions}
    frames = {x["question_id"]: x for x in map(json.loads, QF.read_text(encoding="utf-8").splitlines())}
    golds = {x["question_id"]: x for x in
             json.loads((GOLD_DIR / "gold_nl2sql.json").read_text(encoding="utf-8"))["questions"]}
    return qmap, frames, golds


def resolved_for_compile(plan: dict) -> dict:
    if plan.get("entities") and plan["entities"][0]["mode"] == "fund_classes":
        out = dict(plan)
        out["entities"] = [{"mode": "in", "binding": "fund.product_name", "values": ["A", "B"]}]
        return out
    return plan


def static_test() -> dict[str, dict]:
    qmap, frames, golds = load_inputs()
    schema, _, bindings = metadata()
    plans = {}
    for qid in IDS:
        plan = ground(qmap[qid], frames[qid])
        assert plan["domain"], (qid, plan["unresolved"])
        assert not plan["unresolved"], (qid, plan["unresolved"])
        assert validate_query(qmap[qid], plan) is None, qid
        compiled = rdb.compile_plan(resolved_for_compile(plan))
        assert ";" not in compiled.query.as_string(), qid
        referenced = plan["select"] + [x["binding"] for x in plan["filters"] + plan["order"]]
        referenced += [x["binding"] for x in resolved_for_compile(plan).get("entities") or []
                       if x.get("binding")]
        actual_columns = {bindings[x]["column"] for x in referenced}
        actual_tables = {bindings[x]["table"] for x in referenced}
        for join in schema.get("joins") or []:
            if {join["left"], join["right"]} <= actual_tables:
                actual_columns.update(join.get("left_keys") or [join["left_key"]])
                actual_columns.update(join.get("right_keys") or [join["right_key"]])
        required_columns = set(golds[qid]["required_columns"]["all"])
        assert required_columns <= actual_columns, (qid, required_columns - actual_columns)
        assert actual_tables == set(golds[qid]["required_tables"]), (qid, actual_tables)
        assert len(compiled.evidence) == len(compiled.columns), qid
        assert all(x["source_table"] and x["source_column"] and x["as_of"] for x in compiled.evidence), qid
        plans[qid] = plan

    q017 = plans["q017"]
    assert next(x for x in q017["filters"] if x["binding"] == "etf_gl.net_assets")["value"] == 100_000_000_000
    assert next(x for x in plans["q013"]["filters"]
                if x["binding"] == "bond.remaining_days" and x["operator"] == "<=")["value"] == 1095
    assert next(x for x in plans["q011"]["filters"] if x["binding"] == "bond.rating_rank") == {
        "binding": "bond.rating_rank", "operator": "<=", "value": 4,
        "unit": "rank", "raw": "신용등급이 AA- 이상인"}

    # 정상 30문항에 audit FP를 재사용하지 않으며, 대표 안전 규칙은 원문으로 직접 판정한다.
    invalid = ground("신용등급이 AAAA인 매수 가능 채권", frames["q031"])
    assert validate_query("신용등급이 AAAA인 매수 가능 채권", invalid)["code"] == "ABSTAIN_INVALID_TAXONOMY"
    future = ground("TIGER 미국S&P500의 2027년 확정 연간수익률", frames["q034"])
    assert validate_query("TIGER 미국S&P500의 2027년 확정 연간수익률", future)["code"] == "ABSTAIN_FUTURE_DATA"
    failed_frame = dict(frames["q001"], _error="timeout")
    failed = ground(qmap["q001"], failed_frame)
    assert validate_query(qmap["q001"], failed)["code"] == "ABSTAIN_UNRESOLVED_QUERY"
    print(f"PASS static RDB vertical slice — {len(plans)}/14 plans, schema hallucination 0, evidence 100%")
    return plans


def scalar(value):
    if isinstance(value, decimal.Decimal):
        return str(value.normalize()) if value else "0"
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    return value


def comparable(rows: list[dict], order_sensitive: bool):
    encoded = [json.dumps({k: scalar(v) for k, v in row.items()}, ensure_ascii=False,
                          sort_keys=True, separators=(",", ":")) for row in rows]
    return encoded if order_sensitive else Counter(encoded)


def db_test(plans: dict[str, dict]) -> None:
    _, _, golds = load_inputs()
    passed = 0
    with psycopg.connect(BOND_DSN, autocommit=True) as conn:
        for qid in IDS:
            actual = rdb.execute(plans[qid], conn=conn)
            assert not actual["abstain"], (qid, actual["abstain"])
            cur = conn.execute(golds[qid]["gold_sql"])
            columns = [x.name for x in cur.description]
            gold_rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            assert set(actual["columns"]) == set(columns), {
                "question_id": qid, "actual_columns": actual["columns"],
                "gold_columns": columns,
            }
            actual_cmp = comparable(actual["rows"], golds[qid]["order_sensitive"])
            gold_cmp = comparable(gold_rows, golds[qid]["order_sensitive"])
            assert actual_cmp == gold_cmp, {
                "question_id": qid, "actual_count": len(actual["rows"]),
                "gold_count": len(gold_rows), "actual_first": actual["rows"][:1],
                "gold_first": gold_rows[:1],
            }
            passed += 1
    print(f"PASS DB execution accuracy — {passed}/14")


def graph_contract_test() -> None:
    qmap, frames, _ = load_inputs()

    def initial(qid):
        return {"question_id": qid, "question": qmap[qid], "intent": {},
                "metadata_context": {}, "plan": {}, "results": {}, "evidence": [],
                "abstain": None, "trace": [], "answer": ""}

    def fake_execute(plan):
        compiled = rdb.compile_plan(plan)
        return {"rows": [dict.fromkeys(compiled.columns, "TEST")],
                "columns": compiled.columns, "evidence": compiled.evidence, "abstain": None}

    with patch("agent.nodes.query_frame.extract", return_value=frames["q001"]), \
            patch("agent.nodes.rdb.execute", side_effect=fake_execute):
        response = to_response(APP.invoke(initial("q001")))
    assert list(response) == ["question_id", "question", "retrieved_context", "think_trace", "answer"]
    assert response["retrieved_context"] and "TEST" in response["answer"]

    with patch("agent.nodes.query_frame.extract", return_value=frames["q031"]), \
            patch("agent.nodes.rdb.execute", side_effect=AssertionError("RDB must not run")):
        response = to_response(APP.invoke(initial("q031")))
    assert "확인할 수 없음" in response["answer"] and "AAAA" in response["answer"]
    many = render_answer({
        "abstain": None, "results": {"rows": [{"x": i} for i in range(101)]},
        "evidence": [{"source_column": "x", "label": "값", "source_table": "raw.test",
                      "as_of": "2026-08-24"}],
    })["answer"].splitlines()
    assert len(many) == 6 and many[0] == "총 101건 중 정렬 기준 상위 5건입니다.", many
    print("PASS LangGraph contract — success executes RDB, ABSTAIN skips RDB, response fields 5/5")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true")
    args = ap.parse_args()
    plans = static_test()
    graph_contract_test()
    if args.db:
        db_test(plans)


if __name__ == "__main__":
    main()
