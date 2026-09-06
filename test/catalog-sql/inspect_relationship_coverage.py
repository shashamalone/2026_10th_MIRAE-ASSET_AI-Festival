"""Read-only evidence coverage diagnostics. No embedding/model calls or DB writes."""
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
    args = parser.parse_args()
    out = args.out.resolve()
    if (ROOT / "artifacts/runs").resolve() not in out.parents or "codex-t139-sql-0905" not in out.parts:
        parser.error("agent-scoped output required")
    out.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    from agent import utils
    from agent.graph_logic import graph_engine
    queries = {
        "holdings_by_source": "SELECT p.source_table,p.product_type,p.market_scope,count(*) holding_rows,count(DISTINCT h.product_id) products,count(DISTINCT h.as_of) dates,min(h.as_of) first_date,max(h.as_of) last_date,count(h.weight) weights,count(DISTINCT h.source_document_id) documents FROM relations.product_holding h JOIN enriched.product_master p USING(product_id) GROUP BY 1,2,3",
        "holdings_dates": "SELECT as_of,unit,count(*) holding_rows,count(DISTINCT product_id) products FROM relations.product_holding GROUP BY 1,2 ORDER BY 1",
        "named_overlap_targets": "SELECT p.product_id,p.source_key,p.source_table,p.name,count(h.holding_id) holding_rows,count(h.weight) weights,min(h.as_of) first_date,max(h.as_of) last_date FROM enriched.product_master p LEFT JOIN relations.product_holding h USING(product_id) WHERE p.source_key IN ('VOO','IVV','SPY') OR REPLACE(p.name,' ','') LIKE '%우리반도체BIG2%' GROUP BY 1,2,3,4 ORDER BY 4",
        "subsidiary_coverage": "SELECT count(*) relations,count(DISTINCT parent_security_id) parents,count(DISTINCT as_of) dates,min(as_of) first_date,max(as_of) last_date FROM relations.company_subsidiary",
        "theme_dates": "SELECT as_of,count(*) relations,count(DISTINCT product_id) products FROM relations.product_classification GROUP BY 1 ORDER BY 1",
        "document_coverage": "SELECT source_type,count(*) documents,min(published_at) first_published,max(published_at) last_published FROM vec.source_document GROUP BY 1",
        "chunk_coverage": "SELECT section_type,count(*) chunks,count(DISTINCT document_id) documents,count(page_number) pages,count(source_url) urls FROM vec.document_chunk GROUP BY 1",
        "ecopro_children": "SELECT a.display_name parent,b.display_name child,r.ownership_pct,r.as_of,d.title,d.url FROM relations.company_subsidiary r JOIN enriched.security_master a ON a.security_id=r.parent_security_id JOIN enriched.security_master b ON b.security_id=r.child_security_id JOIN relations.source_document d ON d.document_id=r.source_document_id WHERE a.display_name ILIKE '%에코프로%' OR a.display_name ILIKE '%ecopro%'",
    }
    result = {}
    with (out / "coverage.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
        conn = utils.get_pg_connection()
        try:
            for name, sql in queries.items():
                try:
                    result[name] = {"sql": sql, "rows": utils.run_sql(conn, sql)}
                except Exception as exc:
                    result[name] = {"sql": sql, "error": str(exc)}
        finally:
            conn.close()
        try:
            result["graph_triples"] = graph_engine.triple_count()
            result["graph_predicate_coverage"] = graph_engine.sparql("SELECT ?p (COUNT(*) AS ?count) WHERE { ?s ?p ?o FILTER(?p IN (<http://mafest.ai/product#holds>,<http://mafest.ai/product#hasHolding>,<http://mafest.ai/product#hasSubsidiary>,<http://mafest.ai/product#supportedBy>)) } GROUP BY ?p")
        except Exception as exc:
            result["graph_error"] = str(exc)
    (out / "coverage.json").write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print(json.dumps({k: v if not isinstance(v, dict) else {"rows": len(v.get("rows", [])), "error": v.get("error")} for k, v in result.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
