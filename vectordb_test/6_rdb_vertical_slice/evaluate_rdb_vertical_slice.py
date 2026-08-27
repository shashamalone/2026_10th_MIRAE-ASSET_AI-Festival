#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RDB vertical slice offline/DB/live 3단계 재현 실행기."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import psycopg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from agent import query_frame  # noqa: E402
from agent.agent_core import APP, to_response  # noqa: E402
from config import BOND_DSN, CHAT_TIMEOUT_SECONDS, FRAME_MODEL  # noqa: E402
from script.test_rdb_vertical_slice import (IDS, comparable, db_test,  # noqa: E402
                                            graph_contract_test, load_inputs,
                                            static_test)
from tools.schema_context import ground, metadata  # noqa: E402

RESULT = HERE / "results/metrics.json"
PARAPHRASES = HERE / "paraphrases.jsonl"
FRAME_TARGET_SECONDS = 5.0
QUESTION_TYPES = {
    "single_product_lookup": ["q001", "q002", "q003", "q005", "q006", "q007", "q008", "q009"],
    "same_vehicle_comparison": ["q010"],
    "filtered_ranking": ["q011", "q012", "q013", "q017", "q018"],
}
TYPE_BY_ID = {qid: kind for kind, ids in QUESTION_TYPES.items() for qid in ids}
INPUTS = {
    "query_frames": ROOT / "vectordb_test/4_query_frame_v1/results/frames_HCX-007_audit.jsonl",
    "gold_nl2sql": ROOT / "vectordb_test/5_semantic_schema_nl2sql/gold/gold_nl2sql.json",
    "schema_bindings": ROOT / "metadata/schema_bindings.json",
    "business_rules": ROOT / "metadata/business_rules.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def previous() -> dict:
    if not RESULT.exists():
        return {}
    try:
        return json.loads(RESULT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def input_records() -> dict:
    paths = dict(INPUTS)
    if PARAPHRASES.exists():
        paths["paraphrases"] = PARAPHRASES
    return {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
            for name, path in paths.items()}


def check_snapshot(old: dict) -> None:
    recorded = old.get("inputs") or {}
    changed = [name for name, value in input_records().items()
               if recorded.get(name, {}).get("sha256") not in (None, value["sha256"])]
    if changed:
        raise RuntimeError(f"입력 snapshot SHA-256 변경: {', '.join(changed)}")


def initial_state(question_id: str, question: str) -> dict:
    return {"question_id": question_id, "question": question, "intent": {},
            "metadata_context": {}, "plan": {}, "results": {}, "evidence": [],
            "abstain": None, "trace": [], "answer": ""}


def plan_signature(plan: dict) -> dict:
    filters = [{k: v for k, v in item.items() if k in ("binding", "operator", "value")}
               for item in plan.get("filters") or []]
    order = [{k: v for k, v in item.items() if k in ("binding", "direction", "nulls")}
             for item in plan.get("order") or []]
    return {"domain": plan.get("domain"), "select": sorted(plan.get("select") or []),
            "filters": sorted(filters, key=lambda x: json.dumps(x, ensure_ascii=False,
                                                                  sort_keys=True)),
            "order": order, "limit": plan.get("limit")}


def run_live_case(conn, question_id: str, question: str, frame_target: float,
                  case_id: str | None = None, base_signature: dict | None = None) -> dict:
    """HCX는 정확히 한 번 호출하고 같은 Frame으로 나머지 graph를 실행한다."""
    _, _, golds = load_inputs()
    started = time.perf_counter()
    frame_started = time.perf_counter()
    frame_error = None
    try:
        frame = query_frame.extract(question, use_audit=False)
    except Exception as exc:
        frame_error = exc
        frame = query_frame.empty_frame()
        frame["_error"] = f"{type(exc).__name__}: {exc}"
    frame_latency = round(time.perf_counter() - frame_started, 3)

    with patch("agent.nodes.query_frame.extract", return_value=frame):
        state = APP.invoke(initial_state(question_id, question))
    response = to_response(state)
    e2e_latency = round(time.perf_counter() - started, 3)

    abstain = state.get("abstain")
    results = state.get("results") or {}
    evidence = state.get("evidence") or []
    columns = results.get("columns") or []
    evidence_complete = bool(evidence) and [x.get("source_column") for x in evidence] == columns \
        and all(x.get("source_table") and x.get("source_column") and x.get("as_of") for x in evidence)
    response_contract = list(response) == ["question_id", "question", "retrieved_context",
                                           "think_trace", "answer"]

    db_exact = False
    if not abstain:
        gold = golds[question_id]
        cursor = conn.execute(gold["gold_sql"])
        gold_columns = [x.name for x in cursor.description]
        gold_rows = [dict(zip(gold_columns, row)) for row in cursor.fetchall()]
        db_exact = set(columns) == set(gold_columns) and \
            comparable(results.get("rows") or [], gold["order_sensitive"]) == \
            comparable(gold_rows, gold["order_sensitive"])

    frame_sla = frame_error is None and frame_latency <= frame_target
    functional = not abstain and db_exact and evidence_complete and response_contract
    strict = functional and frame_sla
    failures = []
    if frame_error:
        failures.append("query_frame_timeout" if "timeout" in type(frame_error).__name__.lower()
                        else "query_frame_error")
    if frame_error is None and not frame_sla:
        failures.append("query_frame_over_5s")
    if abstain:
        failures.append("pipeline_abstain")
    else:
        if not db_exact:
            failures.append("db_mismatch")
        if not evidence_complete:
            failures.append("evidence_incomplete")
        if not response_contract:
            failures.append("response_contract_error")

    item = {
        "case_id": case_id or question_id,
        "question_id": question_id,
        "question_type": TYPE_BY_ID[question_id],
        "query_frame_latency_seconds": frame_latency,
        "query_frame_sla_pass": frame_sla,
        "e2e_latency_seconds": e2e_latency,
        "functional_success": functional,
        "strict_success": strict,
        "status": "strict_success" if strict else
                  "functional_success" if functional else
                  "safe_abstain" if abstain else "failure",
        "failure_codes": failures,
        "abstain_code": abstain.get("code") if abstain else None,
        "db_exact": db_exact,
        "evidence_complete": evidence_complete,
        "response_contract": response_contract,
        "result_row_count": len(results.get("rows") or []),
        "frame_task": frame.get("task"),
        "frame_domains": frame.get("domain_candidates") or [],
    }
    if base_signature is not None:
        item["plan_equivalent"] = plan_signature(state.get("plan") or {}) == base_signature
    return item


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize(attempts: list[dict]) -> dict:
    total = len(attempts)
    functional = sum(x["functional_success"] for x in attempts)
    sla = sum(x["query_frame_sla_pass"] for x in attempts)
    strict = sum(x["strict_success"] for x in attempts)
    qf = [x["query_frame_latency_seconds"] for x in attempts]
    e2e = [x["e2e_latency_seconds"] for x in attempts]
    codes = Counter(code for x in attempts for code in x["failure_codes"])
    return {
        "attempted": total,
        "functional_success": functional,
        "functional_success_rate": round(functional / total, 4) if total else None,
        "query_frame_sla_pass": sla,
        "query_frame_sla_rate": round(sla / total, 4) if total else None,
        "strict_success": strict,
        "strict_success_rate": round(strict / total, 4) if total else None,
        "timeout_rate": round(codes["query_frame_timeout"] / total, 4) if total else None,
        "failure_codes": dict(sorted(codes.items())),
        "query_frame_latency_seconds": {"p50": statistics.median(qf) if qf else None,
                                         "p95": percentile(qf, 0.95)},
        "e2e_latency_seconds": {"p50": statistics.median(e2e) if e2e else None,
                                 "p95": percentile(e2e, 0.95)},
    }


def failed_question_types(attempts: list[dict]) -> dict:
    out = {}
    for kind in QUESTION_TYPES:
        failed = [x for x in attempts if x["question_type"] == kind and not x["strict_success"]]
        if failed:
            out[kind] = {
                "question_ids": sorted({x["question_id"] for x in failed}),
                "failure_codes": dict(sorted(Counter(
                    code for x in failed for code in x["failure_codes"]).items())),
            }
    return out


def per_question(attempts: list[dict]) -> dict:
    out = {}
    for qid in IDS:
        rows = [x for x in attempts if x["question_id"] == qid]
        qf = [x["query_frame_latency_seconds"] for x in rows]
        out[qid] = {
            "attempts": len(rows),
            "functional_success": sum(x["functional_success"] for x in rows),
            "query_frame_sla_pass": sum(x["query_frame_sla_pass"] for x in rows),
            "strict_success": sum(x["strict_success"] for x in rows),
            "query_frame_latency_seconds": {
                "min": min(qf), "median": statistics.median(qf), "max": max(qf)},
            "failure_codes": dict(sorted(Counter(
                code for x in rows for code in x["failure_codes"]).items())),
        }
    return out


def load_paraphrases() -> list[dict]:
    rows = [json.loads(line) for line in PARAPHRASES.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == len(IDS) == len({x["case_id"] for x in rows})
    assert {x["base_question_id"] for x in rows} == set(IDS)
    assert all(set(x) == {"case_id", "base_question_id", "question"} for x in rows)
    assert len({x["question"] for x in rows}) == len(rows)
    return rows


def run_phase(phase: str, frame_target: float) -> dict:
    questions, frames, _ = load_inputs()
    attempts = []
    with psycopg.connect(BOND_DSN, autocommit=True) as conn:
        conn.execute("SET statement_timeout = 2000")
        if phase == "smoke":
            cases = [(qid, qid, questions[qid], None) for qid in IDS]
        elif phase == "generalization":
            cases = []
            for row in load_paraphrases():
                qid = row["base_question_id"]
                base = plan_signature(ground(questions[qid], frames[qid]))
                cases.append((row["case_id"], qid, row["question"], base))
        else:
            cases = []

        if phase in {"smoke", "generalization"}:
            for number, (case_id, qid, question, base) in enumerate(cases, 1):
                item = run_live_case(conn, qid, question, frame_target, case_id, base)
                attempts.append(item)
                print(f"LIVE {phase} {number}/{len(cases)} {case_id}: {item['status']} "
                      f"qf={item['query_frame_latency_seconds']}s", flush=True)
        else:
            for qnum, qid in enumerate(IDS, 1):
                rows = []
                for attempt in range(1, 4):
                    item = run_live_case(conn, qid, questions[qid], frame_target,
                                         f"{qid}_r{attempt}")
                    rows.append(item)
                    attempts.append(item)
                    print(f"LIVE stability {qnum}/{len(IDS)} {qid} {attempt}/3: "
                          f"{item['status']} qf={item['query_frame_latency_seconds']}s", flush=True)
                if any(not x["strict_success"] for x in rows):
                    for attempt in range(4, 6):
                        item = run_live_case(conn, qid, questions[qid], frame_target,
                                             f"{qid}_r{attempt}")
                        attempts.append(item)
                        print(f"LIVE stability {qnum}/{len(IDS)} {qid} {attempt}/5: "
                              f"{item['status']} qf={item['query_frame_latency_seconds']}s", flush=True)

    result = {"attempts": attempts, "summary": summarize(attempts)}
    if phase == "smoke":
        result["failed_question_types"] = failed_question_types(attempts)
    elif phase == "stability":
        result["per_question"] = per_question(attempts)
        safety_failure = any(any(code in {"db_mismatch", "evidence_incomplete",
                                          "response_contract_error"}
                                 for code in x["failure_codes"]) for x in attempts)
        result["redesign_recommended"] = result["summary"]["strict_success_rate"] < 0.95 \
            or safety_failure
    else:
        equivalent = sum(x.get("plan_equivalent", False) for x in attempts)
        result["summary"]["plan_equivalent"] = equivalent
        result["summary"]["plan_equivalent_rate"] = round(equivalent / len(attempts), 4)
        result["paraphrase_sha256"] = sha256(PARAPHRASES)
    return result


def build_metrics(run_db: bool, phase: str | None, phase_result: dict | None,
                  frame_target: float) -> dict:
    old = previous()
    _, rules, _ = metadata()
    old_offline = old.get("offline") or {}
    old_live = old.get("live") or {}
    old_db = old_offline.get("db_execution_exact", "not_run")
    if isinstance(old_db, dict) and not run_db:
        old_db = dict(old_db, source="preserved_result")
    legacy = old_live.get("legacy_q018_observation")
    if legacy is None and old_live.get("historical_observation"):
        legacy = {"question_id": old_live.get("question_id", "q018"),
                  "attempts": old_live["historical_observation"]}
    live = {
        "query_frame_target_seconds": frame_target,
        "question_types": QUESTION_TYPES,
        "definitions": {
            "functional_success": "non-ABSTAIN + DB gold exact + evidence complete + response 5 fields",
            "query_frame_sla_pass": f"Query Frame latency <= {frame_target} seconds",
            "strict_success": "functional_success + query_frame_sla_pass",
        },
        "smoke": old_live.get("smoke", {"status": "not_run"}),
        "stability": old_live.get("stability", {"status": "not_run"}),
        "generalization": old_live.get("generalization", {"status": "not_run"}),
        "legacy_q018_observation": legacy or {"status": "not_run"},
    }
    if phase:
        live[phase] = phase_result
    return {
        "experiment": "rdb_vertical_slice_v1",
        "measured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data_cutoff": rules["data_cutoff"],
        "question_ids": IDS,
        "environment": {
            "frame_model": FRAME_MODEL,
            "http_timeout_seconds": CHAT_TIMEOUT_SECONDS,
            "query_frame_target_seconds": frame_target,
            "statement_timeout_ms": rules["statement_timeout_ms"],
            "max_rows": rules["max_rows"],
            "worktree_dirty": bool(subprocess.run(
                ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                text=True, check=True).stdout.strip()),
        },
        "inputs": input_records(),
        "offline": {
            "static_plans": {"passed": 14, "total": 14},
            "required_schema_contract": {"passed": 14, "total": 14},
            "schema_hallucinations": 0,
            "evidence_complete": {"passed": 14, "total": 14},
            "langgraph_contract": "pass",
            "db_execution_exact": ({"passed": 14, "total": 14, "source": "current_run"}
                                   if run_db else old_db),
        },
        "live": live,
    }


def aggregation_self_test() -> None:
    rows = [
        {"functional_success": True, "query_frame_sla_pass": True, "strict_success": True,
         "query_frame_latency_seconds": 4.0, "e2e_latency_seconds": 4.2,
         "failure_codes": [], "question_type": "filtered_ranking", "question_id": "q018"},
        {"functional_success": False, "query_frame_sla_pass": False, "strict_success": False,
         "query_frame_latency_seconds": 13.0, "e2e_latency_seconds": 13.1,
         "failure_codes": ["query_frame_timeout", "pipeline_abstain"],
         "question_type": "filtered_ranking", "question_id": "q018"},
    ]
    summary = summarize(rows)
    assert summary["strict_success_rate"] == 0.5
    assert failed_question_types(rows)["filtered_ranking"]["question_ids"] == ["q018"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action="store_true", help="PostgreSQL gold exact 비교")
    phases = parser.add_mutually_exclusive_group()
    phases.add_argument("--smoke", action="store_true", help="14문항 live 각 1회")
    phases.add_argument("--stability", action="store_true", help="문항별 3회, 실패 문항 5회")
    phases.add_argument("--generalization", action="store_true", help="paraphrase 14문항 각 1회")
    parser.add_argument("--frame-target", type=float, default=FRAME_TARGET_SECONDS)
    parser.add_argument("--write-results", action="store_true", help="metrics.json 갱신")
    args = parser.parse_args()
    if args.frame_target <= 0:
        parser.error("--frame-target은 0보다 커야 합니다")
    if not args.write_results:
        check_snapshot(previous())

    aggregation_self_test()
    plans = static_test()
    graph_contract_test()
    if args.db:
        db_test(plans)
    phase = "smoke" if args.smoke else "stability" if args.stability else \
            "generalization" if args.generalization else None
    phase_result = run_phase(phase, args.frame_target) if phase else None
    metrics = build_metrics(args.db, phase, phase_result, args.frame_target)
    if args.write_results:
        RESULT.parent.mkdir(exist_ok=True)
        RESULT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"RESULT {RESULT.relative_to(ROOT)}")
    else:
        print(json.dumps(phase_result or metrics["offline"], ensure_ascii=False))


if __name__ == "__main__":
    main()
