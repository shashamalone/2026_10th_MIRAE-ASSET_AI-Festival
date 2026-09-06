"""Read-only source checks, no paid model calls; never writes outside run output."""
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
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--snapshot-seed", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if (ROOT / "artifacts/runs").resolve() not in out.parents or "codex-t139-sql-0905" not in out.parts:
        parser.error("agent-scoped artifact path required")
    out.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    os.environ["RDB_SCHEMA_SNAPSHOT_PATH"] = str(out / "schema_snapshot.json")
    from tools import schema_snapshot, catalog_sql
    from agent import utils
    schema_snapshot.save_snapshot(schema_snapshot.load_snapshot(args.snapshot_seed))
    snap = schema_snapshot.get_snapshot()
    result = {"release_id": schema_snapshot.snapshot_release_id(snap)}
    with (out / "source-check.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
        result["identities"] = utils.lookup_product_identities(["BND", "VOO", "IVV", "SPY"])
        conn = utils.get_pg_connection()
        queries = {
            "fund_classes": "SELECT itm_nm,itm_no,ksd_itm_no,mtco_itm_no,rptt_ksd_itm_no FROM raw.prfd01n001 WHERE REPLACE(itm_nm,' ','') LIKE '%우리반도체BIG2%' LIMIT 30",
            "dual_records": "SELECT f.itm_nm,f.itm_no,f.ksd_itm_no,f.mtco_itm_no,f.rptt_ksd_itm_no,e.pd_itm_no,e.pd_nm,e.pd_lstg_dt FROM raw.prfd01n001 f LEFT JOIN raw.pref01n001 e ON f.ksd_itm_no=e.pd_itm_no WHERE REPLACE(f.itm_nm,' ','') LIKE '%KODEX200%' LIMIT 30",
            "vector_tables": "SELECT table_schema,table_name,column_name FROM information_schema.columns WHERE table_schema='vec' AND table_name IN ('documents','document_chunks') ORDER BY table_name,ordinal_position",
            "bond_availability": "SELECT COUNT(*) total, COUNT(buyable_quantity) quantity_not_null, COUNT(buy_yield) yield_not_null FROM raw.prbd01n001",
        }
        try:
            for name, sql in queries.items():
                try:
                    result[name] = {"sql": sql, "rows": utils.run_sql(conn, sql)}
                except Exception as exc:
                    result[name] = {"sql": sql, "error": str(exc)}
            result["metadata"] = {d: catalog_sql.domain_metadata(d, snap) for d in ("채권", "국내ETF", "해외ETF", "펀드")}
        finally:
            conn.close()
    (out / "source-evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"metadata", "vector_tables"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
