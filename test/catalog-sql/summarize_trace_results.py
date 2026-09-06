"""Operational metrics only. Never equate nonempty answers with correctness."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    if (ROOT / "artifacts/runs").resolve() not in run.parents or "codex-t139-sql-0905" not in run.parts:
        parser.error("agent-scoped output required")
    ids = ["Q5"] + [f"Q{i}" for i in range(7, 36)]
    traces, manifests = {}, {}
    for qid in ids:
        path = run / "live" / qid / "traces.jsonl"
        if not path.exists():
            continue
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(lines) != 1:
            raise ValueError(f"Expected exactly one attempt for {qid}")
        traces[qid] = lines[0]
        manifests[qid] = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
    steps = [r for t in traces.values() for r in (t.get("step_results") or {}).values()]
    rdb = [r for r in steps if r.get("engine") == "rdb"]
    durations = [t["e2e_ms"] / 1000 for t in traces.values() if t.get("status") == "ok"]
    replays = {p.parent.name + "/" + p.stem: json.loads(p.read_text(encoding="utf-8")) for p in run.glob("*replay*/Q*.json")}
    report = {
        "requested": len(ids), "attempts": len(traces), "missing": [q for q in ids if q not in traces],
        "status": dict(Counter(t.get("status") for t in traces.values())),
        "blank_answers": [q for q, t in traces.items() if not (t.get("answer") or {}).get("answer")],
        "quota_affected": [q for q, t in traces.items() if t.get("rate_limit", {}).get("status_429_count", 0)],
        "llm_calls": sum(t.get("rate_limit", {}).get("llm_calls", 0) for t in traces.values()),
        "embed_calls": sum(t.get("rate_limit", {}).get("embed_calls", 0) for t in traces.values()),
        "reported_total_tokens": sum(t.get("rate_limit", {}).get("total_tokens", 0) for t in traces.values()),
        "ok_latency_median_s": statistics.median(durations) if durations else None,
        "rdb_steps": len(rdb), "rdb_sql_present": sum(bool(r.get("sql")) for r in rdb),
        "rdb_errors": sum(bool(r.get("error")) for r in rdb),
        "rdb_blocked": sum(bool(r.get("skipped_reason")) for r in rdb),
        "vector_with_chunks": sum(r.get("engine") == "vector" and bool(r.get("chunks")) for r in steps),
        "commits": dict(Counter(m["commit"] for m in manifests.values())),
        "saved_intent_replays": len(replays),
        "replay_paid_calls": sum(r.get("verification", {}).get("paid_calls", 0) for r in replays.values()),
        "limitations": ["Operational statuses, not strict accuracy or official score.",
                        "Different commits were used while diagnosing; not a final frozen-build evaluation.",
                        "Original answers are preserved; saved-intent replay does not replace failed paid attempts.",
                        "Q30 hit an API timeout before intent. A trace-only patch overlapped its process: not a clean-build benchmark.",
                        "No deployment, ingestion, or repeated paid question attempts."],
    }
    (run / "operational-summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
