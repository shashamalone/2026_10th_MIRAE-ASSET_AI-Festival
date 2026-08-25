# -*- coding: utf-8 -*-
"""PostgreSQL·Oxigraph·pgvector 읽기전용 팀 API."""
from __future__ import annotations

import os
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from kb.build_data_platform_v2 import dsn
from tools.sql_guard import ensure_read_only_sparql, ensure_read_only_sql

APP_VERSION = "2.0.0"
MAX_ROWS = int(os.environ.get("API_MAX_ROWS", "100"))
STATEMENT_TIMEOUT_MS = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "2000"))
OXIGRAPH_URL = os.environ.get("OXIGRAPH_URL", "http://graph:7878").rstrip("/")

app = FastAPI(title="금융상품 데이터 플랫폼", version=APP_VERSION)


class SqlRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100_000)
    params: dict[str, Any] = Field(default_factory=dict)


class SparqlRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100_000)


def run_sql(query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        statement = ensure_read_only_sql(query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        with psycopg.connect(dsn(), row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (str(STATEMENT_TIMEOUT_MS),))
            with conn.cursor() as cursor:
                cursor.execute(statement, params or {})
                records = cursor.fetchmany(MAX_ROWS + 1) if cursor.description else []
        truncated = len(records) > MAX_ROWS
        return {"rows": records[:MAX_ROWS], "row_count": min(len(records), MAX_ROWS), "truncated": truncated}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"SQL 실행 실패: {type(exc).__name__}: {str(exc)[:300]}") from exc


async def run_sparql(query: str) -> Any:
    try:
        statement = ensure_read_only_sparql(query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        async with httpx.AsyncClient(timeout=STATEMENT_TIMEOUT_MS / 1000) as client:
            response = await client.post(
                f"{OXIGRAPH_URL}/query",
                content=statement.encode("utf-8"),
                headers={"Content-Type": "application/sparql-query", "Accept": "application/sparql-results+json, text/turtle"},
            )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        return response.json() if "json" in content_type else {"content_type": content_type, "body": response.text}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Oxigraph 질의 실패: {str(exc)[:300]}") from exc


@app.get("/health")
async def health() -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "ok",
        "api_version": APP_VERSION,
        "clova_configured": bool(os.environ.get("CLOVA_API_KEY") or os.environ.get("CLOVA_STUDIO_API_KEY")),
        "clova_embedding_model": "bge-m3",
    }
    try:
        version = run_sql(
            "SELECT dataset_version,release_date,cutoff_date,domain_as_of,source_hash,built_at "
            "FROM meta.dataset_snapshot ORDER BY built_at DESC LIMIT 1"
        )["rows"]
        rdb = run_sql(
            "SELECT 'bond_kr_master' table_name,count(*) row_count FROM raw.bond_kr_master "
            "UNION ALL SELECT 'etf_kr_master',count(*) FROM raw.etf_kr_master "
            "UNION ALL SELECT 'etf_gl_master',count(*) FROM raw.etf_gl_master "
            "UNION ALL SELECT 'fund_pub_master',count(*) FROM raw.fund_pub_master"
        )["rows"]
        vectors = run_sql(
            "SELECT 'bond_schema_terms' table_name,count(*) row_count FROM vec.bond_schema_terms "
            "UNION ALL SELECT 'schema_terms_all',count(*) FROM vec.schema_terms_all "
            "UNION ALL SELECT 'document_chunk',count(*) FROM vec.document_chunk"
        )["rows"]
        result.update({"data": version[0] if version else None, "rdb_rows": rdb, "vector_rows": vectors})
    except HTTPException as exc:
        result.update({"status": "degraded", "database_error": exc.detail})
    try:
        graph = await run_sparql("SELECT (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } }")
        bindings = graph.get("results", {}).get("bindings", []) if isinstance(graph, dict) else []
        result["graph_triples"] = int(bindings[0]["triples"]["value"]) if bindings else None
    except HTTPException as exc:
        result.update({"status": "degraded", "graph_error": exc.detail, "graph_triples": None})
    return result


@app.post("/db/sql")
def db_sql(request: SqlRequest) -> dict[str, Any]:
    return run_sql(request.query, request.params)


@app.post("/db/sparql")
async def db_sparql(request: SparqlRequest) -> Any:
    return await run_sparql(request.query)


@app.get("/db/tables")
def db_tables() -> dict[str, Any]:
    return run_sql(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_schema IN ('meta','raw','enriched','relations','vec','core') "
        "ORDER BY table_schema,table_name"
    )


@app.get("/db/columns")
def db_columns(
    table_schema: str | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    return run_sql(
        "SELECT table_schema,table_name,ordinal_position,column_name,data_type,is_nullable "
        "FROM information_schema.columns WHERE table_schema IN ('meta','raw','enriched','relations','vec','core') "
        "AND (%(schema)s::text IS NULL OR table_schema=%(schema)s::text) "
        "AND (%(table)s::text IS NULL OR table_name=%(table)s::text) ORDER BY table_schema,table_name,ordinal_position",
        {"schema": table_schema, "table": table_name},
    )


@app.get("/db/catalog")
def db_catalog(
    table_schema: str | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    return run_sql(
        "SELECT * FROM meta.column_catalog WHERE (%(schema)s::text IS NULL OR table_schema=%(schema)s::text) "
        "AND (%(table)s::text IS NULL OR table_name=%(table)s::text) ORDER BY table_schema,table_name,ordinal_position",
        {"schema": table_schema, "table": table_name},
    )


@app.get("/db/coverage")
def db_coverage(
    product_id: str | None = None,
    status: str | None = Query(default=None, pattern="^(available|unavailable|not_applicable)$"),
) -> dict[str, Any]:
    return run_sql(
        "SELECT p.product_id,p.product_type,p.name,c.* FROM meta.product_coverage c "
        "JOIN enriched.product_master p USING(product_id) "
        "WHERE (%(product_id)s::text IS NULL OR p.product_id=%(product_id)s::text) "
        "AND (%(status)s::text IS NULL OR c.holdings_status=%(status)s::text OR c.document_status=%(status)s::text OR c.performance_status=%(status)s::text) "
        "ORDER BY p.product_type,p.name",
        {"product_id": product_id, "status": status},
    )


@app.get("/db/version")
def db_version() -> dict[str, Any]:
    return run_sql(
        "SELECT * FROM meta.dataset_snapshot ORDER BY built_at DESC LIMIT 1"
    )
