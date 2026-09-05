"""Read-only issuer spelling evidence; no model call or production alias edits."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--snapshot-seed", type=Path, required=True)
    args = parser.parse_args()
    out = args.run.resolve() / "issuer-spellings"
    if (ROOT / "artifacts/runs").resolve() not in out.parents or "codex-t139-sql-0905" not in out.parts:
        parser.error("agent-scoped output required")
    out.mkdir(exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    os.environ["RDB_SCHEMA_SNAPSHOT_PATH"] = str(out / "schema_snapshot.json")
    from tools import schema_snapshot
    from agent import utils
    schema_snapshot.save_snapshot(schema_snapshot.load_snapshot(args.snapshot_seed))
    sql = """SELECT pd_pbcm, std_pd_mcls_nm, COUNT(*) AS rows
             FROM raw.prbd01n001
             WHERE pd_pbcm LIKE '%하이닉스%' OR pd_pbcm LIKE '%에너지솔루션%'
             GROUP BY pd_pbcm, std_pd_mcls_nm ORDER BY pd_pbcm, std_pd_mcls_nm"""
    with (out / "read.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
        conn = utils.get_pg_connection()
        try:
            rows = utils.run_sql(conn, sql)
        finally:
            conn.close()
    report = {"sql": sql, "rows": rows, "paid_calls": 0}
    (out / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
