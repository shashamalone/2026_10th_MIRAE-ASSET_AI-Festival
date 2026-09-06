"""Paced single paid attempts. Stop on quota errors; never repeat a question."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--snapshot-seed", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--ids", required=True)
    parser.add_argument("--gap", type=float, default=65)
    args = parser.parse_args()
    ids = args.ids.split(",")
    if args.gap < 65 or len(set(ids)) != len(ids):
        parser.error("unique IDs and at least 65 seconds gap required")
    out = args.run.resolve()
    if (ROOT / "artifacts/runs").resolve() not in out.parents or "codex-t139-sql-0905" not in out.parts:
        parser.error("agent-scoped output required")
    if any((out / "live" / qid).exists() for qid in ids):
        parser.error("question output already exists; refusing any repeated attempt")
    for index, qid in enumerate(ids):
        if index:
            time.sleep(args.gap)
        case_out = out / "live" / qid
        subprocess.check_call([sys.executable, str(ROOT / "test/catalog-sql/run_checks.py"), "pipeline",
                               "--env-file", args.env_file, "--snapshot-seed", str(args.snapshot_seed),
                               "--out", str(case_out), "--ids", qid, "--rounds", "1", "--single-attempt"], cwd=ROOT)
        trace = json.loads((case_out / "traces.jsonl").read_text(encoding="utf-8"))
        print(f"{qid}: {trace['status']}; e2e_ms={trace['e2e_ms']}; calls={trace.get('rate_limit', {})}", flush=True)
        if trace["status"] == "rate_limited" or trace.get("rate_limit", {}).get("status_429_count", 0):
            raise SystemExit("Quota error: stopped without retrying this or subsequent questions.")


if __name__ == "__main__":
    main()
