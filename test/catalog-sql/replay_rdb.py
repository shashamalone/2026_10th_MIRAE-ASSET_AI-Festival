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
    parser.add_argument("--allow-graph", action="store_true", help="Read-only deterministic Graph execution, still no model/embedding calls")
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
    from agent.intent_guard import guard_intent
    from agent.graph_logic import graph_orchestrator
    from agent.state import ready_step_ids
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
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {"question": cases[qid]["question"]}
        original = trace.get(args.intent_stage) or cases[qid].get(args.intent_stage) or trace.get("intent") or cases[qid].get("intent")
        if not original:
            raise ValueError(f"No saved intent: {qid}")
        question = trace["question"]
        state = {"question_id": qid, "question": question, "intent": copy.deepcopy(original), "step_results": {}, "max_sql_retries": 1}
        with (out / f"{qid}.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), \
             patch.object(nodes, "_llm_plan", forbidden), patch.object(nodes, "_llm_answer", forbidden), \
             patch.object(graph_orchestrator, "_llm_plan", forbidden), \
             patch.object(utils, "_resolve_unknown_concepts_via_llm", return_value={}):
            state["intent"], _ = guard_intent(state["intent"])
            for restore in (evidence_contract.restore_explicit_comparators, evidence_contract.restore_relative_event_window, evidence_contract.restore_class_comparison, evidence_contract.restore_cross_market_identity,
                            utils.preserve_explicit_investment_region, utils.preserve_explicit_output_requests):
                state["intent"], _ = restore(state["intent"], question)
            state["intent"], _ = utils.preserve_overseas_exposure_scope(state["intent"], question)
            state["intent"], _ = utils.restore_shared_theme_scope(state["intent"], question)
            state["intent"], _ = utils.resolve_named_product_domains(state["intent"])
            state["intent"], _ = utils.prune_inferred_named_subtypes(state["intent"], question)
            state["intent"], _ = utils.validate_issuer_subjects(state["intent"], question)
            state.update(plan_query_db.plan_query_node(state))
            if not args.allow_graph and any(s["engine"] == "graph" for s in state["plan"]):
                raise ValueError(f"RDB-only replay cannot bypass Graph dependencies: {qid}")
            while ready_step_ids(state["plan"], set(state["step_results"])):
                previous = len(state["step_results"])
                for engine, execute in (("graph", nodes.graph_search_node), ("rdb", nodes.rdb_search_node)):
                    ready = ready_step_ids(state["plan"], set(state["step_results"]))
                    if any(s["engine"] == engine and s["step_id"] in ready for s in state["plan"]):
                        update = execute(state)
                        state["step_results"].update(update.get("step_results") or {})
                        state.setdefault("trace", []).extend(update.get("trace") or [])
                ready = ready_step_ids(state["plan"], set(state["step_results"]))
                for step in state["plan"]:
                    if step["engine"] == "vector" and step["step_id"] in ready:
                        state["step_results"][step["step_id"]] = {"engine": "vector", "status": "not_replayed", "chunks": [], "note": "무료 조회 검증이므로 문서 임베딩 검색·설명 모델을 실행하지 않았습니다."}
                if len(state["step_results"]) == previous:
                    raise RuntimeError("Replay made no dependency progress")
            state.update(nodes.merge_results_node(state))
            response = nodes.generate_answer_node(state)
            state["answer"] = json.loads(response["answer"])
        state["verification"] = {"mode": "saved-intent-read-only-graph-sql" if args.allow_graph else "saved-intent-read-only-sql", "paid_calls": 0,
                                 "intent_source": "single_trace" if trace.get("verified_intent") else "previous_audit",
                                 "intent_stage": args.intent_stage,
                                 "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                                 "release_id": schema_snapshot.snapshot_release_id(snap),
                                 "limitation": "의도 재분석·Vector·설명 LLM 없이 저장 의도를 재검증. Graph는 allow-graph일 때만 읽기 조회. 새 단회 정답률로 계산하지 않음."}
        (out / f"{qid}.json").write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        reports.append({"id": qid, "rows": {sid: len(r.get("rows") or []) for sid, r in state["step_results"].items()},
                        "blockers": state["route"].get("blocking_reasons"), "paid_calls": 0})
    print(json.dumps(reports, ensure_ascii=False))


if __name__ == "__main__":
    main()
