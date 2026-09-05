"""Re-use saved intent and execute only read-only SQL; no Clova/embedding calls.

This is NOT a new end-to-end attempt, and must not count as answer accuracy.
Unresolved concepts remain unresolved; no stored expected answers are injected.
"""
import argparse
import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--snapshot-seed", type=Path, required=True)
    parser.add_argument("--ids", required=True)
    parser.add_argument("--label", default="rdb-replay")
    parser.add_argument("--intent-stage", choices=["verified_intent", "intent"], default="verified_intent")
    args = parser.parse_args()
    run = args.run.resolve()
    if (ROOT / "artifacts/runs").resolve() not in run.parents or "codex-t139-sql-0905" not in run.parts:
        parser.error("agent-scoped output required")
    if not args.label.replace("-", "").isalnum():
        parser.error("simple replay label required")
    out = run / args.label
    out.mkdir(exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    os.environ["RDB_SCHEMA_SNAPSHOT_PATH"] = str(out / "schema_snapshot.json")
    from agent import nodes, utils, evidence_contract, plan_query_db
    from tools import schema_snapshot
    schema_snapshot.save_snapshot(schema_snapshot.load_snapshot(args.snapshot_seed))
    snap = schema_snapshot.get_snapshot()
    cases = {c["id"]: c for c in json.loads(args.audit.read_text(encoding="utf-8"))["cases"]}
    forbidden = Mock()
    forbidden.invoke.side_effect = AssertionError("paid call prohibited in replay")
    forbidden.with_structured_output.return_value = forbidden
    reports = []
    for qid in args.ids.split(","):
        if (out / f"{qid}.json").exists():
            raise ValueError(f"Existing replay {qid}; preserve it and use a separate run")
        trace_path = run / "live" / qid / "traces.jsonl"
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        original = trace.get(args.intent_stage) or cases[qid].get(args.intent_stage) or trace.get("intent") or cases[qid].get("intent")
        if not original:
            raise ValueError(f"No saved intent: {qid}")
        question = trace["question"]
        state = {"question_id": qid, "question": question, "intent": copy.deepcopy(original), "step_results": {}}
        with (out / f"{qid}.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), \
             patch.object(nodes, "_llm_plan", forbidden), patch.object(nodes, "_llm_answer", forbidden), \
             patch.object(utils, "_resolve_unknown_concepts_via_llm", return_value={}):
            for restore in (evidence_contract.restore_explicit_comparators, evidence_contract.restore_class_comparison, evidence_contract.restore_cross_market_identity,
                            utils.preserve_explicit_investment_region, utils.preserve_explicit_output_requests):
                state["intent"], _ = restore(state["intent"], question)
            state["intent"], _ = utils.preserve_overseas_exposure_scope(state["intent"], question)
            state["intent"], _ = utils.resolve_named_product_domains(state["intent"])
            state["intent"], _ = utils.prune_inferred_named_subtypes(state["intent"], question)
            state.update(plan_query_db.plan_query_node(state))
            if any(s["engine"] == "graph" for s in state["plan"]):
                raise ValueError(f"RDB-only replay cannot bypass Graph dependencies: {qid}")
            conn = utils.get_pg_connection()
            try:
                for step in state["plan"]:
                    if step["engine"] == "rdb":
                        state["step_results"][step["step_id"]] = nodes._execute_target_step(step, question, conn, True, 1)
            finally:
                conn.close()
            # Keep narrative unavailable, not falsely replayed or paid again.
            for step in state["plan"]:
                if step["engine"] == "vector":
                    state["step_results"][step["step_id"]] = {"engine": "vector", "status": "not_replayed", "chunks": [], "note": "SQL 전용 검증이므로 문서 검색·설명 모델을 실행하지 않았습니다."}
            state.update(nodes.merge_results_node(state))
            response = nodes.generate_answer_node(state)
            state["answer"] = json.loads(response["answer"])
        state["verification"] = {"mode": "saved-intent-read-only-sql", "paid_calls": 0,
                                 "intent_source": "single_trace" if trace.get("verified_intent") else "previous_audit",
                                 "intent_stage": args.intent_stage,
                                 "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                                 "release_id": schema_snapshot.snapshot_release_id(snap),
                                 "limitation": "의도 재분석·Vector·Graph·설명 LLM 없이 검증. 새 단회 정답률로 계산하지 않음."}
        (out / f"{qid}.json").write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        reports.append({"id": qid, "rows": {sid: len(r.get("rows") or []) for sid, r in state["step_results"].items()},
                        "blockers": state["route"].get("blocking_reasons"), "paid_calls": 0})
    print(json.dumps(reports, ensure_ascii=False))


if __name__ == "__main__":
    main()
