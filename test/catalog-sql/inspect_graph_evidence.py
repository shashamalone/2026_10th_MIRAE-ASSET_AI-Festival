"""Inspect actual RDF evidence and alias vocabulary, without model calls."""
import argparse
import contextlib
import json
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
    from agent.graph_logic import graph_engine
    prefix = "PREFIX fp: <http://mafest.ai/product#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
    queries = {
        "holding_vocabulary": "SELECT ?p (COUNT(*) AS ?count) WHERE {?s a fp:Holding; ?p ?o} GROUP BY ?p",
        "subsidiary_vocabulary": "SELECT ?p (COUNT(*) AS ?count) WHERE {?s a fp:SubsidiaryRelation; ?p ?o} GROUP BY ?p",
        "document_vocabulary": "SELECT ?p (COUNT(*) AS ?count) WHERE {?s a fp:Document; ?p ?o} GROUP BY ?p",
        "holding_sample": "SELECT ?h ?p ?o WHERE { {SELECT ?h WHERE {?h a fp:Holding} LIMIT 2} ?h ?p ?o }",
        "subsidiary_sample": "SELECT ?h ?p ?o WHERE { {SELECT ?h WHERE {?h a fp:SubsidiaryRelation} LIMIT 2} ?h ?p ?o }",
        "cambricon_names": "SELECT ?entity ?p ?name WHERE {?entity ?p ?name FILTER(isLiteral(?name) && (CONTAINS(LCASE(STR(?name)), 'cambricon') || CONTAINS(STR(?name), '캠브리콘'))) } LIMIT 40",
        "nvidia_names": "SELECT ?entity ?p ?name WHERE {?entity ?p ?name FILTER(isLiteral(?name) && (CONTAINS(LCASE(STR(?name)), 'nvidia') || CONTAINS(STR(?name), '엔비디아'))) } LIMIT 40",
    }
    result = {}
    with (out / "graph-evidence.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
        for key, query in queries.items():
            try:
                result[key] = {"query": prefix + query, "rows": graph_engine.sparql(prefix + query)}
            except Exception as exc:
                result[key] = {"query": prefix + query, "error": str(exc)}
    (out / "graph-evidence.json").write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print(json.dumps({k: v.get("rows", v.get("error")) for k, v in result.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
