"""Read-only ETF source diagnostics. No model calls or shared output writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--aum-code", required=True)
    parser.add_argument("--fee-code", required=True)
    parser.add_argument("--snapshot-seed", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if (ROOT / "artifacts/runs").resolve() not in out.parents or "codex-t139-sql-0905" not in out.parts:
        parser.error("Output must be in this worktree's own agent-scoped run directory")
    out.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=False)
    os.environ["RDB_SCHEMA_SNAPSHOT_PATH"] = str(out / "schema_snapshot.json")
    from tools import catalog_sql as c, rdb_schema as r, schema_snapshot as physical
    from agent import utils
    if args.snapshot_seed:
        seed = physical.load_snapshot(args.snapshot_seed)
        if seed:
            physical.save_snapshot(seed)
    snap = physical.get_snapshot()
    metadata = c.domain_metadata("국내ETF", snap)
    queries = {
        "aum_source": "SELECT pd_itm_no, pd_nm, pd_net_tamt, du_last_aum, du_upt_dt "
                      "FROM raw.pref01n001 WHERE pd_itm_no = " + c.literal(args.aum_code),
        "classification_dates": "SELECT pd_itm_no, pd_nm, wu_inv_ast_type, wu_inv_rgn, "
                                "cu_strtegy, cu_charge_rt, du_er_1m, du_er_3m, du_er_6m, "
                                "cu_upt_dt, du_upt_dt, wu_upt_dt, ref_base_dt, fn_base_dt "
                                "FROM raw.pref01n001 WHERE pd_itm_no = " + c.literal(args.fee_code),
        "fee_metric": "SELECT e.pd_itm_no, m.value, m.unit, m.as_of, m.source, m.source_column, "
                      "m.method, m.is_available, m.unavailable_reason, m.source_priority "
                      "FROM enriched.etf_kr e JOIN enriched.product_metric m ON m.product_id=e.product_id "
                      "WHERE m.metric_code='EXPENSE_RATIO' AND e.pd_itm_no=" + c.literal(args.fee_code),
    }
    report = {"release_id": physical.snapshot_release_id(snap), "python": sys.version,
              "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "rdb_schema_sha256": hashlib.sha256((ROOT / "src/tools/rdb_schema.py").read_bytes()).hexdigest(),
              "paid_llm_calls": 0, "queries": {}, "metadata": {
                  name: metadata[name] for name in ["pd_net_tamt", "du_last_aum", "wu_inv_ast_type",
                  "wu_inv_rgn", "cu_strtegy", "cu_charge_rt", "du_er_1m", "du_er_3m", "du_er_6m"]}}
    conn = utils.get_pg_connection()
    try:
        for key, sql in queries.items():
            rows = utils.run_sql(conn, sql)
            report["queries"][key] = {"sql": sql, "rows": rows, "count": len(rows)}
    finally:
        conn.close()
    known = {c.normalize(name): spec for name, spec in r.get_attribute_catalog("국내ETF").items()}
    known.update(c.description_aliases("국내ETF", metadata))
    report["reviewed_output_resolution"] = {
        name: {"column": known[c.normalize(name)].column if c.normalize(name) in known else None,
               "provenance_handler": c.normalize(name) in utils.PROVENANCE_CONCEPTS,
               "output_view": r.get_output_view("국내ETF", name)}
        for name in ["AUM", "현재 AUM", "최종 AUM", "순자산", "총보수", "복제방식", "분류 근거", "수치 갱신일"]}
    (out / "source-evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "metadata"}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
