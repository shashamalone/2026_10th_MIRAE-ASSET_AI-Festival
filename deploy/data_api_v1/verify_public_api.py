# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_RELEASE = "financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38"
EXPECTED_API_VERSION = "4.3.0"
EXPECTED_VECTOR_RUN = "t108-7902db9a58d66b7f"
EXPECTED_VECTOR_MODEL = "BAAI/bge-m3"
EXPECTED_VECTOR_DIMENSION = 1024
EXPECTED_VECTOR_HNSW_INDEXES = 3
EXPECTED_VECTOR_SEARCH_FUNCTIONS = 2
EXPECTED_VECTOR_BASE_COUNTS = {
    "vec.bond_schema_terms": 130,
    "vec.schema_terms_all": 189,
    "vec.source_document": 974,
    "vec.document_product": 1_019,
    "vec.product_coverage": 15_951,
    "vec.chunk_embedding": 5_664,
    "vec.document_chunk": 9_055,
}
EXPECTED_VECTOR_SUPPLEMENTAL_COUNTS = {
    "vec.bond_schema_terms": 0,
    "vec.schema_terms_all": 0,
    "vec.source_document": 63,
    "vec.document_product": 203,
    "vec.product_coverage": 182,
    "vec.chunk_embedding": 916,
    "vec.document_chunk": 916,
}
EXPECTED_VECTOR_COUNTS = {
    name: EXPECTED_VECTOR_BASE_COUNTS[name] + EXPECTED_VECTOR_SUPPLEMENTAL_COUNTS[name]
    for name in EXPECTED_VECTOR_BASE_COUNTS
}
VECTOR_COUNT_KEYS = {
    "bond_schema_terms": "bond_schema_terms.jsonl",
    "schema_terms_all": "schema_terms_all.jsonl",
    "source_document": "source_documents.jsonl",
    "document_product": "product_documents.jsonl",
    "product_coverage": "prospectus_coverage.jsonl",
    "chunk_embedding": "chunk_embeddings.jsonl",
    "document_chunk": "document_chunks.jsonl",
}
EXPECTED_NAMED_GRAPHS = {
    "http://mafest.ai/graph/abox/bond_kr": 264_465,
    "http://mafest.ai/graph/abox/company": 321_366,
    "http://mafest.ai/graph/abox/etf_gl": 56_541,
    "http://mafest.ai/graph/abox/etf_kr": 353_849,
    "http://mafest.ai/graph/abox/fund_pub": 227_934,
    "http://mafest.ai/graph/tbox/bond_kr": 351,
    "http://mafest.ai/graph/tbox/common": 1_033,
    "http://mafest.ai/graph/tbox/etf_gl": 122,
    "http://mafest.ai/graph/tbox/etf_kr": 790,
    "http://mafest.ai/graph/tbox/fund_pub": 247,
}
EXPECTED_ROUTES = {
    "/health": {"GET"},
    "/db/sql": {"POST"},
    "/db/sparql": {"POST"},
    "/db/version": {"GET"},
    "/db/stats": {"GET"},
    "/db/tables": {"GET"},
    "/db/columns": {"GET"},
    "/db/catalog": {"GET"},
    "/answer": {"GET"},
}


def request(
    url: str,
    path: str,
    statement: str | None = None,
    *,
    content_type: str = "text/plain; charset=utf-8",
) -> tuple[int, dict]:
    body = None if statement is None else statement.encode("utf-8")
    headers = {} if body is None else {"Content-Type": content_type}
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=body,
        headers=headers,
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def as_int(value: Any, label: str) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{label} is not an integer") from exc


def expected_table_counts(
    mapping: Any, label: str, expected: dict[str, int] = EXPECTED_VECTOR_COUNTS
) -> dict[str, int]:
    require(isinstance(mapping, dict), f"{label} is not an object")
    counts = {
        f"vec.{table}": as_int(mapping.get(table), f"{label}.{table}")
        for table in VECTOR_COUNT_KEYS
    }
    require(counts == expected, f"{label} mismatch")
    return counts


def expected_file_counts(mapping: Any, label: str) -> dict[str, int]:
    require(isinstance(mapping, dict), f"{label} is not an object")
    counts = {
        f"vec.{table}": as_int(mapping.get(filename), f"{label}.{filename}")
        for table, filename in VECTOR_COUNT_KEYS.items()
    }
    require(counts == EXPECTED_VECTOR_BASE_COUNTS, f"{label} mismatch")
    return counts


def validate_vector(vector: Any) -> dict[str, Any]:
    require(isinstance(vector, dict), "VECTOR HEALTH FAIL: missing vector object")
    require(vector.get("status") == "active", "VECTOR HEALTH FAIL: status")
    require(vector.get("ready") is True, "VECTOR HEALTH FAIL: readiness")
    require(vector.get("run_id") == EXPECTED_VECTOR_RUN, "VECTOR HEALTH FAIL: run")
    require(vector.get("release_id") == EXPECTED_RELEASE, "VECTOR HEALTH FAIL: release")
    require(vector.get("model_id") == EXPECTED_VECTOR_MODEL, "VECTOR HEALTH FAIL: model")
    require(
        as_int(vector.get("embedding_dim"), "vector.embedding_dim")
        == EXPECTED_VECTOR_DIMENSION,
        "VECTOR HEALTH FAIL: dimension",
    )
    require(
        as_int(vector.get("hnsw_indexes"), "vector.hnsw_indexes")
        == EXPECTED_VECTOR_HNSW_INDEXES,
        "VECTOR HEALTH FAIL: HNSW indexes",
    )
    require(
        as_int(vector.get("search_functions"), "vector.search_functions")
        == EXPECTED_VECTOR_SEARCH_FUNCTIONS,
        "VECTOR HEALTH FAIL: search functions",
    )
    expected_file_counts(vector.get("expected_counts"), "vector.expected_counts")
    expected_table_counts(
        vector.get("observed_counts"),
        "vector.observed_counts",
        EXPECTED_VECTOR_BASE_COUNTS,
    )
    live_counts = expected_table_counts(vector.get("table_counts"), "vector.table_counts")
    return {
        "run_id": vector["run_id"],
        "release_id": vector["release_id"],
        "model_id": vector["model_id"],
        "model_revision": vector.get("model_revision"),
        "embedding_dim": EXPECTED_VECTOR_DIMENSION,
        "status": vector["status"],
        "expected_counts": EXPECTED_VECTOR_BASE_COUNTS,
        "observed_counts": EXPECTED_VECTOR_BASE_COUNTS,
        "supplemental_counts": EXPECTED_VECTOR_SUPPLEMENTAL_COUNTS,
        "live_counts": live_counts,
        "hnsw_indexes": EXPECTED_VECTOR_HNSW_INDEXES,
        "search_functions": EXPECTED_VECTOR_SEARCH_FUNCTIONS,
    }


def validate_health(health: Any, expected_graph_triples: int) -> dict[str, Any]:
    require(isinstance(health, dict), "HEALTH FAIL: payload")
    require(health.get("api_version") == EXPECTED_API_VERSION, "HEALTH FAIL: API version")
    require(health.get("release_id") == EXPECTED_RELEASE, "HEALTH FAIL: release")
    require(health.get("readiness") is True, "HEALTH FAIL: readiness")
    require(health.get("vector_status") == "active", "HEALTH FAIL: vector status")
    require(health.get("clova_configured") is True, "HEALTH FAIL: Clova credential")
    require(health.get("answer_pipeline_loaded") is True, "HEALTH FAIL: answer pipeline")
    rdb = health.get("rdb") or {}
    graph = health.get("graph") or {}
    require(rdb.get("release_id") == EXPECTED_RELEASE, "HEALTH FAIL: RDB release")
    require(graph.get("release_id") == EXPECTED_RELEASE, "HEALTH FAIL: Graph release")
    require(
        as_int(graph.get("triples"), "health.graph.triples") == expected_graph_triples,
        "HEALTH FAIL: Graph triples",
    )
    require(
        as_int(graph.get("expected_triples"), "health.graph.expected_triples")
        == expected_graph_triples,
        "HEALTH FAIL: Graph expectation",
    )
    return validate_vector(health.get("vector"))


def wait_for_health(
    url: str,
    expected_graph_triples: int = 1_226_698,
    attempts: int = 30,
    interval_seconds: float = 2,
) -> dict:
    last_error = "no response"
    for attempt in range(attempts):
        try:
            status, health = request(url, "/health")
            if (
                status == 200
                and health.get("release_id") == EXPECTED_RELEASE
                and health.get("api_version") == EXPECTED_API_VERSION
                and health.get("readiness") is True
            ):
                validate_health(health, expected_graph_triples)
                return health
            last_error = f"status={status} contract_not_ready"
        except (OSError, urllib.error.URLError, json.JSONDecodeError, SystemExit) as exc:
            last_error = f"{type(exc).__name__}: contract_not_ready"
        if attempt + 1 < attempts:
            time.sleep(interval_seconds)
    raise SystemExit(f"HEALTH FAIL after {attempts} attempts: {last_error}")


def exact_named_graphs(payload: dict) -> dict[str, int]:
    rows = payload.get("rows") or []
    actual = {row["g"]: as_int(row["triples"], "named_graph.triples") for row in rows}
    require(actual == EXPECTED_NAMED_GRAPHS, "NAMED GRAPH CONTRACT FAIL")
    return actual


def exact_openapi_routes(payload: dict) -> dict[str, set[str]]:
    paths = payload.get("paths") or {}
    actual = {
        path: {
            method.upper()
            for method in definition
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        }
        for path, definition in paths.items()
    }
    require(actual == EXPECTED_ROUTES, "ROUTE CONTRACT FAIL: OpenAPI surface")
    return actual


def vector_metadata_query() -> str:
    return (
        "SELECT run_id,release_id,model_id,model_revision,embedding_dim,status,"
        "expected_counts,observed_counts FROM vec.vector_deploy_run "
        "ORDER BY cutover_at DESC NULLS LAST,updated_at DESC LIMIT 1"
    )


def vector_counts_query() -> str:
    return (
        "SELECT 'bond_schema_terms' table_name,count(*) row_count FROM vec.bond_schema_terms "
        "UNION ALL SELECT 'schema_terms_all',count(*) FROM vec.schema_terms_all "
        "UNION ALL SELECT 'source_document',count(*) FROM vec.source_document "
        "UNION ALL SELECT 'document_product',count(*) FROM vec.document_product "
        "UNION ALL SELECT 'product_coverage',count(*) FROM vec.product_coverage "
        "UNION ALL SELECT 'chunk_embedding',count(*) FROM vec.chunk_embedding "
        "UNION ALL SELECT 'document_chunk',count(*) FROM vec.document_chunk ORDER BY 1"
    )


def vector_runtime_query() -> str:
    return (
        "SELECT (SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_am a ON a.oid=c.relam "
        "WHERE n.nspname='vec' AND a.amname='hnsw') hnsw_indexes,"
        "(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='vec' AND p.proname IN "
        "('search_schema_terms','search_document_chunks') "
        "AND has_function_privilege(current_user,p.oid,'EXECUTE')) search_functions"
    )


SCHEMA_SELF_SEARCH = (
    "WITH q AS (SELECT embedding FROM vec.schema_terms_all ORDER BY term_uri LIMIT 1) "
    "SELECT r.term_uri,r.label,r.domain_file,r.score FROM q CROSS JOIN LATERAL "
    "vec.search_schema_terms(q.embedding,1,NULL,NULL) r"
)
DOCUMENT_SELF_SEARCH = (
    "WITH q AS (SELECT embedding FROM vec.chunk_embedding ORDER BY content_hash LIMIT 1) "
    "SELECT r.product_id,r.chunk_id,r.document_id,r.section_type,r.score "
    "FROM q CROSS JOIN LATERAL "
    "vec.search_document_chunks(q.embedding,NULL,NULL,1,NULL) r"
)


def collect_preflight(url: str, expected_graph_triples: int) -> dict[str, Any]:
    require(expected_graph_triples == 1_226_698, "PREFLIGHT FAIL: non-canonical Graph input")
    status, health = request(url, "/health")
    require(status == 200, "PREFLIGHT FAIL: health status")
    require(health.get("api_version") in {"4.0.0", EXPECTED_API_VERSION}, "PREFLIGHT FAIL: API version")
    require(health.get("release_id") == EXPECTED_RELEASE, "PREFLIGHT FAIL: release")
    # API 4.0 predates the SEC incremental-vector contract and can report
    # degraded despite healthy immutable stores. The probes below validate all
    # live RDB, Graph, vector counts and search functions before any mutation.
    rdb_health = health.get("rdb") or {}
    graph_health = health.get("graph") or {}
    require(rdb_health.get("release_id") == EXPECTED_RELEASE, "PREFLIGHT FAIL: RDB release")
    require(graph_health.get("release_id") == EXPECTED_RELEASE, "PREFLIGHT FAIL: Graph release")
    require(
        as_int(graph_health.get("triples"), "preflight.graph.triples")
        == expected_graph_triples,
        "PREFLIGHT FAIL: health Graph triples",
    )

    version_status, version = request(url, "/db/version")
    metadata_status, metadata = request(url, "/db/sql", vector_metadata_query())
    counts_status, counts = request(url, "/db/sql", vector_counts_query())
    runtime_status, runtime = request(url, "/db/sql", vector_runtime_query())
    sparql_status, sparql = request(
        url, "/db/sparql", "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }"
    )
    named_status, named = request(
        url,
        "/db/sparql",
        "SELECT ?g (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } } "
        "GROUP BY ?g ORDER BY ?g",
    )
    schema_status, schema_search = request(url, "/db/sql", SCHEMA_SELF_SEARCH)
    document_status, document_search = request(url, "/db/sql", DOCUMENT_SELF_SEARCH)
    require(
        all(
            code == 200
            for code in (
                version_status,
                metadata_status,
                counts_status,
                runtime_status,
                sparql_status,
                named_status,
                schema_status,
                document_status,
            )
        ),
        "PREFLIGHT FAIL: read-only probe status",
    )
    require(
        (version.get("rows") or [{}])[0].get("release_id") == EXPECTED_RELEASE,
        "PREFLIGHT FAIL: version release",
    )
    require(
        as_int((sparql.get("rows") or [{}])[0].get("triples"), "preflight.sparql.triples")
        == expected_graph_triples,
        "PREFLIGHT FAIL: SPARQL Graph triples",
    )
    named_graphs = exact_named_graphs(named)

    metadata_row = (metadata.get("rows") or [{}])[0]
    require(metadata_row.get("run_id") == EXPECTED_VECTOR_RUN, "PREFLIGHT FAIL: vector run")
    require(metadata_row.get("release_id") == EXPECTED_RELEASE, "PREFLIGHT FAIL: vector release")
    require(metadata_row.get("model_id") == EXPECTED_VECTOR_MODEL, "PREFLIGHT FAIL: vector model")
    require(metadata_row.get("status") == "active", "PREFLIGHT FAIL: vector status")
    require(
        as_int(metadata_row.get("embedding_dim"), "preflight.vector.embedding_dim")
        == EXPECTED_VECTOR_DIMENSION,
        "PREFLIGHT FAIL: vector dimension",
    )
    expected_file_counts(metadata_row.get("expected_counts"), "preflight.expected_counts")
    expected_table_counts(
        metadata_row.get("observed_counts"),
        "preflight.observed_counts",
        EXPECTED_VECTOR_BASE_COUNTS,
    )
    live_counts = {
        f"vec.{row['table_name']}": as_int(row.get("row_count"), "preflight.live_count")
        for row in counts.get("rows") or []
    }
    require(live_counts == EXPECTED_VECTOR_COUNTS, "PREFLIGHT FAIL: live vector counts")
    runtime_row = (runtime.get("rows") or [{}])[0]
    require(
        as_int(runtime_row.get("hnsw_indexes"), "preflight.hnsw_indexes")
        == EXPECTED_VECTOR_HNSW_INDEXES,
        "PREFLIGHT FAIL: HNSW indexes",
    )
    require(
        as_int(runtime_row.get("search_functions"), "preflight.search_functions")
        == EXPECTED_VECTOR_SEARCH_FUNCTIONS,
        "PREFLIGHT FAIL: search functions",
    )
    self_search: dict[str, dict[str, Any]] = {}
    for label, result in (("schema", schema_search), ("document", document_search)):
        rows = result.get("rows") or []
        require(result.get("row_count") == 1 and len(rows) == 1, f"PREFLIGHT FAIL: {label} self-search rows")
        score = float(rows[0].get("score") or 0)
        require(score >= 0.999, f"PREFLIGHT FAIL: {label} self-search score")
        self_search[label] = {"row_count": 1, "score": score}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_predeploy",
        "contract_pass": True,
        "deployment_executed": False,
        "api": {
            "version": health.get("api_version"),
            "release_id": health.get("release_id"),
            "readiness": health.get("readiness"),
        },
        "rdb": {"release_id": rdb_health.get("release_id")},
        "graph": {
            "release_id": graph_health.get("release_id"),
            "triples": expected_graph_triples,
            "named_graphs": named_graphs,
        },
        "vector": {
            "run_id": metadata_row.get("run_id"),
            "release_id": metadata_row.get("release_id"),
            "model_id": metadata_row.get("model_id"),
            "model_revision": metadata_row.get("model_revision"),
            "embedding_dim": EXPECTED_VECTOR_DIMENSION,
            "status": metadata_row.get("status"),
            "expected_counts": EXPECTED_VECTOR_BASE_COUNTS,
            "observed_counts": EXPECTED_VECTOR_BASE_COUNTS,
            "supplemental_counts": EXPECTED_VECTOR_SUPPLEMENTAL_COUNTS,
            "live_counts": live_counts,
            "hnsw_indexes": EXPECTED_VECTOR_HNSW_INDEXES,
            "search_functions": EXPECTED_VECTOR_SEARCH_FUNCTIONS,
            "self_search": self_search,
        },
    }


def render_preflight_markdown(receipt: dict[str, Any]) -> str:
    vector = receipt["vector"]
    lines = [
        "# API-only deployment preflight",
        "",
        "- Mode: `read_only_predeploy`",
        "- Contract: **PASS**",
        "- Deployment executed: **NO**",
        f"- Live API: `{receipt['api']['version']}`",
        f"- Release: `{receipt['api']['release_id']}`",
        f"- Graph triples: `{receipt['graph']['triples']:,}`",
        f"- Vector run: `{vector['run_id']}` (`{vector['status']}`)",
        f"- Vector model: `{vector['model_id']}` / `{vector['embedding_dim']}` dimensions",
        f"- HNSW indexes / search functions: `{vector['hnsw_indexes']}` / `{vector['search_functions']}`",
        "",
        "## Live vector counts",
        "",
        "| Object | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| `{name}` | {count:,} |" for name, count in vector["live_counts"].items())
    lines.extend(
        [
            "",
            "The receipt is allowlisted and excludes environment variables, credentials, DSNs, headers, and raw error payloads.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_preflight(receipt: dict[str, Any], artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "api_only_preflight.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "api_only_preflight.md").write_text(
        render_preflight_markdown(receipt),
        encoding="utf-8",
    )


def run_post_deploy(url: str, expected_graph_triples: int, health_only: bool) -> None:
    health = wait_for_health(url, expected_graph_triples)
    if health_only:
        print("RAW QUERY API HEALTH PASS")
        return

    version_status, version = request(url, "/db/version")
    stats_status, stats = request(url, "/db/stats")
    tables_status, tables = request(url, "/db/tables")
    columns_status, columns = request(
        url, "/db/columns?table_schema=enriched&table_name=product_master"
    )
    catalog_status, catalog = request(
        url, "/db/catalog?table_schema=enriched&table_name=product_master"
    )
    sql_status, sql = request(
        url,
        "/db/sql",
        "SELECT (SELECT count(*) FROM raw.bond_kr_master)+"
        "(SELECT count(*) FROM raw.etf_kr_master)+"
        "(SELECT count(*) FROM raw.etf_gl_master)+"
        "(SELECT count(*) FROM raw.fund_pub_master) AS official,"
        "(SELECT count(*) FROM relations.product_holding) AS holdings,"
        "(SELECT count(*) FROM relations.company_subsidiary) AS subsidiaries",
    )
    cap_status, capped = request(
        url,
        "/db/sql",
        "SELECT product_id FROM enriched.product_master ORDER BY product_id LIMIT 101",
    )
    sparql_status, sparql = request(
        url, "/db/sparql", "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }"
    )
    named_status, named = request(
        url,
        "/db/sparql",
        "SELECT ?g (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } } "
        "GROUP BY ?g ORDER BY ?g",
    )
    vector_schema_status, vector_schema = request(url, "/db/sql", SCHEMA_SELF_SEARCH)
    vector_document_status, vector_document = request(url, "/db/sql", DOCUMENT_SELF_SEARCH)
    openapi_status, openapi = request(url, "/openapi.json")
    json_status, _ = request(
        url,
        "/db/sql",
        '{"sql":"SELECT 1"}',
        content_type="application/json",
    )
    generic_status, _ = request(url, "/db", "SELECT 1")
    v1_status, _ = request(url, "/v1/release")

    read_statuses = (
        version_status,
        stats_status,
        tables_status,
        columns_status,
        catalog_status,
        sql_status,
        cap_status,
        sparql_status,
        named_status,
        vector_schema_status,
        vector_document_status,
        openapi_status,
    )
    require(all(status == 200 for status in read_statuses), "RAW QUERY READ FAIL")
    require(version["rows"][0].get("release_id") == EXPECTED_RELEASE, "VERSION FAIL")
    table_names = {(row["table_schema"], row["table_name"]) for row in tables["rows"]}
    require(("enriched", "product_master") in table_names, "TABLE FAIL")
    require(bool(stats.get("rows") and columns.get("rows") and catalog.get("rows")), "METADATA FAIL")
    counts = sql["rows"][0]
    require(
        tuple(as_int(counts[key], f"rdb.{key}") for key in ("official", "holdings", "subsidiaries"))
        == (53_375, 46_951, 8_866),
        "RDB COUNT FAIL",
    )
    stats_by_name = {
        row["object_name"]: as_int(row["row_count"], f"stats.{row['object_name']}")
        for row in stats.get("rows", [])
    }
    require(
        {name: stats_by_name.get(name) for name in EXPECTED_VECTOR_COUNTS}
        == EXPECTED_VECTOR_COUNTS,
        "VECTOR COUNT FAIL",
    )
    require(
        capped.get("row_count") == 100 and capped.get("truncated") is True,
        "ROW CAP FAIL",
    )
    require(
        as_int(sparql["rows"][0]["triples"], "sparql.triples") == expected_graph_triples,
        "UNION DEFAULT GRAPH FAIL",
    )
    exact_named_graphs(named)
    for label, result in (("schema", vector_schema), ("document", vector_document)):
        rows = result.get("rows") or []
        require(
            result.get("row_count") == 1
            and len(rows) == 1
            and float(rows[0].get("score") or 0) >= 0.999,
            f"VECTOR {label.upper()} SEARCH FAIL",
        )
    exact_openapi_routes(openapi)
    answer_status, answer_payload = request(
        url, "/answer?question_id=contract-probe&question="
    )
    require(answer_status == 200, "ANSWER CONTRACT FAIL: status")
    require(
        set(answer_payload) == {
            "question_id", "question", "retrieved_context", "think_trace", "answer"
        }
        and all(isinstance(value, str) for value in answer_payload.values()),
        "ANSWER CONTRACT FAIL: exact five-string-field envelope",
    )
    require(
        json_status == 415 and generic_status == 404 and v1_status == 404,
        "ROUTE CONTRACT FAIL: removed routes",
    )
    print(
        "FINANCIAL AGENT API PASS: API=4.3.0 exact routes=9; /answer five-field contract; "
        "text/plain SQL/SPARQL readonly; "
        "official=53375 holdings=46951 subsidiaries=8866 "
        f"vector_run={EXPECTED_VECTOR_RUN} vector_search=2/2 "
        f"graph={expected_graph_triples} union_default=on"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument("--expected-graph-triples", type=int, required=True)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    require(args.expected_graph_triples == 1_226_698, "Non-canonical Graph expectation")
    if args.preflight:
        require(args.artifact_dir is not None, "--artifact-dir is required for preflight")
        receipt = collect_preflight(args.url, args.expected_graph_triples)
        write_preflight(receipt, args.artifact_dir)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return
    require(args.artifact_dir is None, "--artifact-dir is preflight-only")
    run_post_deploy(args.url, args.expected_graph_triples, args.health_only)


if __name__ == "__main__":
    main()
