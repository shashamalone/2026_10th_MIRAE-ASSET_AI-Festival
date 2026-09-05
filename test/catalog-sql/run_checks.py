"""Read-only integration checks; all generated output stays in the run directory."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["live", "pipeline"])
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--snapshot-seed", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ids", default="Q2,Q4")
    parser.add_argument("--rounds", type=int, default=1)
    args = parser.parse_args()
    out = args.out.resolve()
    run_root = (ROOT / "artifacts" / "runs").resolve()
    if run_root not in out.parents or "codex-t139-sql-0905" not in out.parts:
        parser.error("--out must be inside this worktree's agent-scoped artifacts/runs path")
    out.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=False)
    os.environ["RDB_SCHEMA_SNAPSHOT_PATH"] = str(out / "schema_snapshot.json")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    from tools import schema_snapshot, catalog_sql, rdb_schema
    from agent import utils
    if args.snapshot_seed:
        seed = schema_snapshot.load_snapshot(args.snapshot_seed)
        if seed:
            schema_snapshot.save_snapshot(seed)
    manifest = {"mode": args.mode, "commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)),
        "python": sys.version, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ids": args.ids, "rounds": args.rounds}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    snap = schema_snapshot.get_snapshot()
    rdb_schema.assert_schema_contract(snap)
    if args.mode == "pipeline":
        sys.argv = ["run_latency.py", "--rounds", str(args.rounds), "--ids", args.ids,
                    "--out", str(out / "traces.jsonl")]
        with (out / "pipeline.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            runpy.run_path(str(ROOT / "test/pipline-test/latency/run_latency.py"), run_name="__main__")
        print(f"Pipeline complete: {out}", flush=True)
        return
    report = {"release_id": schema_snapshot.snapshot_release_id(snap), "tables": len(snap["tables"]),
              "schema_contract": "pass", "metadata": {}, "queries": {}}
    for domain in rdb_schema.DOMAIN_TABLE_INFO:
        metadata = catalog_sql.domain_metadata(domain, snap)
        aliases = catalog_sql.description_aliases(domain, metadata)
        report["metadata"][domain] = {"rows": len(metadata), "additional_aliases": len(aliases)}
        (out / f"metadata-{domain}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(1.1)
    scenarios = {
        "Q2_columns": {"domain": "채권", "entities": ["국고채권 02000-3106(21-5)"],
                       "fields": ["상품번호", "발행일", "만기일", "잔존기간", "표면금리", "개인 세후 운용수익률"]},
        "Q4_columns": {"domain": "국내ETF", "entities": ["KODEX 200"],
                       "fields": ["상품번호", "운용사", "기초지수", "AUM", "NAV", "종가", "괴리율", "1년수익률"]},
        "aum_sort": {"domain": "국내ETF", "sort": {"attribute": "AUM", "order": "desc", "limit": "3"}},
        "fee_join": {"domain": "국내ETF", "entities": ["KODEX 200"], "fields": ["총보수율"]},
        "credit_rank": {"domain": "채권", "sort": {"attribute": "신용등급", "order": "desc", "limit": "3"}},
    }
    conn = utils.get_pg_connection()
    try:
        for name, scenario in scenarios.items():
            step = {"domain": scenario["domain"], "fields": scenario.get("fields", []), "conditions": [],
                    "sort": scenario.get("sort"), "role": "target",
                    "product_name_entities": [{"surface_form": e} for e in scenario.get("entities", [])]}
            mapping = dict(rdb_schema.get_attribute_catalog(step["domain"]))
            aliases = catalog_sql.description_aliases(step["domain"], catalog_sql.domain_metadata(step["domain"], snap))
            for field in step["fields"]:
                if field not in mapping and catalog_sql.normalize(field) in aliases:
                    mapping[field] = aliases[catalog_sql.normalize(field)]
            resolved = utils.build_resolved_schema(step, mapping, [])
            sql = catalog_sql.compile_select(resolved, snapshot=snap)["sql"]
            start = time.monotonic()
            try:
                rows = utils.run_sql(conn, sql)
                report["queries"][name] = {"sql": sql, "count": len(rows), "rows": rows,
                                           "elapsed_ms": round((time.monotonic()-start)*1000, 1)}
            except Exception as exc:
                report["queries"][name] = {"sql": sql, "error": str(exc)}
            time.sleep(1.1)
    finally:
        conn.close()
    (out / "live-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report, "queries": {k: {a: b for a, b in v.items() if a not in {"sql", "rows"}}
                                           for k, v in report["queries"].items()}}, ensure_ascii=False, indent=2))
    if any("error" in result for result in report["queries"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
