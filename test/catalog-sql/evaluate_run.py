"""Reuse the team's unchanged claim evaluator without overwriting baseline files."""
import argparse
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "test/pipline-test/latency"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if (ROOT / "artifacts/runs").resolve() not in out.parents or "codex-t139-sql-0905" not in out.parts:
        parser.error("Output must be inside this worktree's agent-scoped artifacts/runs directory")
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("team_claim_evaluator", LEGACY / "analyze.py")
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    golden = {row["question_id"]: row for row in [json.loads(line) for line in
              (LEGACY / "golden_eval.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]}
    with (ROOT / "goldset/golden_answers_20260824.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            case = golden[f"Q{int(row['id'])}"]
            case["question"] = row["question"]
            case["expected_domains"] = evaluator.expected_domains(row["product_category"])
    raw = [json.loads(line) for line in args.traces.read_text(encoding="utf-8").splitlines() if line.strip()]
    traces = [trace for trace in raw if not trace.get("superseded")]
    results = [evaluator.evaluate(golden[trace["question_id"]], trace) for trace in traces]
    (out / "per_run_eval.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results), encoding="utf-8")

    def summarize(selected):
        indices = [i for i, trace in enumerate(traces) if selected(trace)]
        ts, es = [traces[i] for i in indices], [results[i] for i in indices]
        scoreable = [e for e in es if e.get("overall_pass") is not None]
        normal = [t for t in ts if t.get("status") == "ok"]
        codes = Counter(code for e in es for code in e.get("failure_codes", []))
        rdb = [r for t in ts for r in t.get("step_results", {}).values() if r.get("engine") == "rdb"]
        executed = [r for r in rdb if r.get("sql") and r.get("sql_attempts", 0) > 0]
        return {"runs": len(ts), "scoreable": len(scoreable),
                "strict_pass": sum(bool(e.get("overall_pass")) for e in scoreable),
                "status": dict(Counter(t.get("status") for t in ts)), "failure_codes": dict(codes),
                "generation_omission_run_rate": codes["GENERATION_OMISSION"] / len(scoreable) if scoreable else None,
                "latency_ok_p50_s": statistics.median(t["e2e_ms"] for t in normal)/1000 if normal else None,
                "latency_ok_p95_s": evaluator.pct([t["e2e_ms"] for t in normal], .95)/1000 if normal else None,
                "llm_calls_mean": statistics.mean(t["rate_limit"]["llm_calls"] for t in normal) if normal else None,
                "tokens_total": sum(t.get("rate_limit", {}).get("total_tokens", 0) for t in ts),
                "rdb_steps": len(rdb), "rdb_executed": len(executed),
                "rdb_success": sum(not r.get("error") for r in executed),
                "rdb_blocked_or_skipped": sum(bool(r.get("skipped_reason")) for r in rdb),
                "rdb_errors": sum(bool(r.get("error")) for r in rdb),
                "sql_llm_calls": dict(Counter(call["name"] for t in ts for call in t.get("timing", {}).get("rdb_llm", [])))}

    summary = {"raw_attempts": len(raw), "superseded_attempts": len(raw)-len(traces),
               "all": summarize(lambda _: True), "cold": summarize(lambda t: t["round"] == 1),
               "warm": summarize(lambda t: t["round"] >= 2),
               "diagnostic_only": "Unchanged team token/claim heuristic; not the competition's final score.",
               "questions": {qid: summarize(lambda t, q=qid: t["question_id"] == q)
                             for qid in sorted({t["question_id"] for t in traces}, key=lambda q: int(q[1:]))}}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "questions"}, ensure_ascii=False, indent=2))
    for result in results:
        if result["question_id"] in {"Q2", "Q4"}:
            claims = result.get("claim_results", [])
            print(result["question_id"], "r"+str(result["round"]),
                  sum(c["diagnosis"] in evaluator.POSITIVE for c in claims), "/", len(claims), result["failure_codes"])


if __name__ == "__main__":
    main()
