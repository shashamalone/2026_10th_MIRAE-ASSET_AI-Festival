# -*- coding: utf-8 -*-
"""PostgreSQL·Oxigraph·pgvector 읽기전용 호환 API."""
from __future__ import annotations

import os
import time
from typing import Any, Literal

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from kb.build_data_platform_v2 import dsn
from kb.v2_manifest import (
    DATASET_VERSION,
    EXPECTED_ABOX_TRIPLES,
    EXPECTED_SNAPSHOT_HASH,
    RELEASE_ID,
)
from tools.sql_guard import ensure_read_only_sparql, ensure_read_only_sql

APP_VERSION = "2.1.0"
MAX_ROWS = int(os.environ.get("API_MAX_ROWS", "100"))
# 운영 계약의 2초 상한은 환경변수로 완화할 수 없다. 필요하면 더 짧게만 조정한다.
STATEMENT_TIMEOUT_MS = min(2000, max(1, int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "2000"))))
OXIGRAPH_URL = os.environ.get("OXIGRAPH_URL", "http://graph:7878").rstrip("/")
EXPECTED_ABOX_GRAPHS = {
    "http://mafest.ai/graph/abox/bond_kr",
    "http://mafest.ai/graph/abox/etf_kr",
    "http://mafest.ai/graph/abox/etf_gl",
    "http://mafest.ai/graph/abox/fund_pub",
    "http://mafest.ai/graph/abox/company",
}

app = FastAPI(title="금융상품 데이터 플랫폼", version=APP_VERSION)


class DbRequest(BaseModel):
    query: str | None = Field(default=None, min_length=1, max_length=100_000)
    sql: str | None = Field(default=None, min_length=1, max_length=100_000)
    sparql: str | None = Field(default=None, min_length=1, max_length=100_000)
    params: dict[str, Any] = Field(default_factory=dict)


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def query_for(request: DbRequest, kind: Literal["sql", "sparql"]) -> str:
    direct = request.sql if kind == "sql" else request.sparql
    other = request.sparql if kind == "sql" else request.sql
    if other is not None:
        raise HTTPException(status_code=422, detail=f"{kind} endpoint에 다른 query 종류를 보낼 수 없습니다")
    if direct is not None and request.query is not None and direct != request.query:
        raise HTTPException(status_code=422, detail=f"{kind}과 query 별칭 값이 서로 다릅니다")
    statement = direct or request.query
    if statement is None:
        raise HTTPException(status_code=422, detail=f"{kind} 또는 query 필드가 필요합니다")
    return statement


def run_sql(query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        statement = ensure_read_only_sql(query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        with psycopg.connect(dsn(), row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(STATEMENT_TIMEOUT_MS),),
            )
            with conn.cursor() as cursor:
                cursor.execute(statement, params or {})
                columns = [column.name for column in cursor.description] if cursor.description else []
                records = cursor.fetchmany(MAX_ROWS + 1) if cursor.description else []
        truncated = len(records) > MAX_ROWS
        rows = records[:MAX_ROWS]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms(started),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"SQL 실행 실패: {type(exc).__name__}: {str(exc)[:300]}",
        ) from exc


async def run_sparql(query: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        statement = ensure_read_only_sparql(query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        async with httpx.AsyncClient(timeout=STATEMENT_TIMEOUT_MS / 1000) as client:
            response = await client.post(
                f"{OXIGRAPH_URL}/query",
                content=statement.encode("utf-8"),
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": "application/sparql-results+json, text/turtle",
                },
            )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            payload = response.json()
            if "boolean" in payload:
                columns = ["boolean"]
                rows = [{"boolean": bool(payload["boolean"])}]
            else:
                columns = list(payload.get("head", {}).get("vars", []))
                bindings = payload.get("results", {}).get("bindings", [])
                rows = [
                    {
                        column: binding.get(column, {}).get("value")
                        for column in columns
                    }
                    for binding in bindings[: MAX_ROWS + 1]
                ]
        else:
            columns = ["content_type", "body"]
            rows = [{"content_type": content_type, "body": response.text}]
        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms(started),
        }
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Oxigraph 질의 실패: {str(exc)[:300]}"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Oxigraph 응답 처리 실패: {type(exc).__name__}: {str(exc)[:300]}",
        ) from exc


@app.get("/health")
async def health() -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "degraded",
        "api_version": APP_VERSION,
        "release_id": RELEASE_ID,
        "snapshot_hash": EXPECTED_SNAPSHOT_HASH,
        "clova_configured": bool(
            os.environ.get("CLOVA_API_KEY") or os.environ.get("CLOVA_STUDIO_API_KEY")
        ),
        "clova_embedding_model": "bge-m3",
        "readiness": False,
    }
    rdb_hash = None
    rdb_release = None
    run_status = None
    run_phase = None
    vector_status = "pending"
    try:
        version_rows = run_sql(
            """
            SELECT d.dataset_version,d.release_date,d.cutoff_date,d.domain_as_of,
                   d.source_hash,d.built_at,l.run_id,l.status AS run_status,
                   l.phase AS run_phase,
                   COALESCE(l.validation_result->>'vector_status','pending') AS vector_status
            FROM meta.dataset_snapshot d
            LEFT JOIN LATERAL (
              SELECT run_id,status,phase,validation_result
              FROM meta.load_run WHERE snapshot_id=d.snapshot_id
              ORDER BY started_at DESC LIMIT 1
            ) l ON true
            ORDER BY d.built_at DESC LIMIT 1
            """
        )["rows"]
        rdb_rows = run_sql(
            "SELECT 'bond_kr_master' table_name,count(*) row_count FROM raw.bond_kr_master "
            "UNION ALL SELECT 'etf_kr_master',count(*) FROM raw.etf_kr_master "
            "UNION ALL SELECT 'etf_gl_master',count(*) FROM raw.etf_gl_master "
            "UNION ALL SELECT 'fund_pub_master',count(*) FROM raw.fund_pub_master"
        )["rows"]
        vector_rows = run_sql(
            "SELECT 'bond_schema_terms' table_name,count(*) row_count FROM vec.bond_schema_terms "
            "UNION ALL SELECT 'schema_terms_all',count(*) FROM vec.schema_terms_all "
            "UNION ALL SELECT 'document_chunk',count(*) FROM vec.document_chunk"
        )["rows"]
        data = version_rows[0] if version_rows else None
        if data:
            rdb_hash = data["source_hash"]
            rdb_release = f"{data['dataset_version']}@{rdb_hash}"
            run_status = data.get("run_status")
            run_phase = data.get("run_phase")
            vector_status = data.get("vector_status") or "pending"
        result.update(
            {
                "data": data,
                "rdb_rows": rdb_rows,
                "vector_rows": vector_rows,
                "vector_status": vector_status,
                "rdb": {
                    "release_id": rdb_release,
                    "snapshot_hash": rdb_hash,
                    "run_status": run_status,
                    "phase": run_phase,
                },
            }
        )
    except HTTPException as exc:
        result["database_error"] = exc.detail

    graph_hash = None
    graph_release = None
    graph_triples = None
    graph_names: set[str] = set()
    try:
        count_result = await run_sparql(
            "SELECT (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } "
            "FILTER(STRSTARTS(STR(?g), 'http://mafest.ai/graph/abox/')) }"
        )
        graph_triples = (
            int(count_result["rows"][0]["triples"]) if count_result["rows"] else None
        )
        graph_result = await run_sparql(
            "SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } "
            "FILTER(STRSTARTS(STR(?g), 'http://mafest.ai/graph/abox/')) }"
        )
        graph_names = {row["g"] for row in graph_result["rows"]}
        if graph_triples == EXPECTED_ABOX_TRIPLES and graph_names == EXPECTED_ABOX_GRAPHS:
            graph_hash = EXPECTED_SNAPSHOT_HASH
            graph_release = RELEASE_ID
        result.update(
            {
                "graph_triples": graph_triples,
                "graph": {
                    "release_id": graph_release,
                    "snapshot_hash": graph_hash,
                    "triples": graph_triples,
                    "named_graphs": sorted(graph_names),
                },
            }
        )
    except HTTPException as exc:
        result.update(
            {
                "graph_error": exc.detail,
                "graph_triples": None,
                "graph": {
                    "release_id": None,
                    "snapshot_hash": None,
                    "triples": None,
                    "named_graphs": [],
                },
            }
        )

    result["readiness"] = bool(
        "database_error" not in result
        and "graph_error" not in result
        and rdb_hash == graph_hash == EXPECTED_SNAPSHOT_HASH
        and rdb_release == graph_release == RELEASE_ID
        and run_status == "passed"
        and run_phase == "cutover_ready"
        and vector_status in {"pending", "ready"}
    )
    result["status"] = "ok" if result["readiness"] else "degraded"
    return result


@app.post("/db")
async def db_legacy(request: DbRequest) -> dict[str, Any]:
    if request.sql is not None and request.sparql is not None:
        raise HTTPException(status_code=422, detail="sql과 sparql을 동시에 보낼 수 없습니다")
    if request.sparql is not None:
        return await run_sparql(query_for(request, "sparql"))
    return run_sql(query_for(request, "sql"), request.params)


@app.post("/db/sql")
def db_sql(request: DbRequest) -> dict[str, Any]:
    return run_sql(query_for(request, "sql"), request.params)


@app.post("/db/sparql")
async def db_sparql(request: DbRequest) -> dict[str, Any]:
    return await run_sparql(query_for(request, "sparql"))


@app.get("/db/stats")
def db_stats() -> dict[str, Any]:
    return run_sql(
        """
        SELECT 'raw.bond_kr_master' object_name,count(*) row_count FROM raw.bond_kr_master
        UNION ALL SELECT 'raw.etf_kr_master',count(*) FROM raw.etf_kr_master
        UNION ALL SELECT 'raw.etf_gl_master',count(*) FROM raw.etf_gl_master
        UNION ALL SELECT 'raw.fund_pub_master',count(*) FROM raw.fund_pub_master
        UNION ALL SELECT 'enriched.product_master',count(*) FROM enriched.product_master
        UNION ALL SELECT 'relations.product_holding',count(*) FROM relations.product_holding
        UNION ALL SELECT 'relations.company_subsidiary',count(*) FROM relations.company_subsidiary
        UNION ALL SELECT 'vec.bond_schema_terms',count(*) FROM vec.bond_schema_terms
        UNION ALL SELECT 'vec.schema_terms_all',count(*) FROM vec.schema_terms_all
        UNION ALL SELECT 'vec.document_chunk',count(*) FROM vec.document_chunk
        ORDER BY 1
        """
    )


@app.get("/db/tables")
def db_tables() -> dict[str, Any]:
    return run_sql(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_schema IN ('meta','raw','enriched','relations','vec','core') "
        "ORDER BY table_schema,table_name"
    )


def columns_query(table_schema: str | None, table_name: str | None) -> dict[str, Any]:
    return run_sql(
        "SELECT table_schema,table_name,ordinal_position,column_name,data_type,is_nullable "
        "FROM information_schema.columns "
        "WHERE table_schema IN ('meta','raw','enriched','relations','vec','core') "
        "AND (%(schema)s::text IS NULL OR table_schema=%(schema)s::text) "
        "AND (%(table)s::text IS NULL OR table_name=%(table)s::text) "
        "ORDER BY table_schema,table_name,ordinal_position",
        {"schema": table_schema, "table": table_name},
    )


@app.get("/db/columns/{table_schema}/{table_name}")
def db_columns_legacy(table_schema: str, table_name: str) -> dict[str, Any]:
    return columns_query(table_schema, table_name)


@app.get("/db/columns")
def db_columns(
    table_schema: str | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    return columns_query(table_schema, table_name)


@app.get("/db/catalog")
def db_catalog(
    table_schema: str | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    return run_sql(
        "SELECT table_schema,table_name,ordinal_position,column_name,data_type,is_nullable,"
        "description,unit,as_of_column,zero_null_rule,source_priority,transform_expression,"
        "implementation_status,deployment_status,pk_ordinal,fk_target,grain "
        "FROM meta.column_catalog "
        "WHERE (%(schema)s::text IS NULL OR table_schema=%(schema)s::text) "
        "AND (%(table)s::text IS NULL OR table_name=%(table)s::text) "
        "ORDER BY table_schema,table_name,ordinal_position",
        {"schema": table_schema, "table": table_name},
    )


@app.get("/db/coverage")
def db_coverage(
    product_id: str | None = None,
    status: str | None = Query(
        default=None, pattern="^(available|unavailable|not_applicable)$"
    ),
) -> dict[str, Any]:
    return run_sql(
        "SELECT p.product_id,p.product_type,p.name,c.holdings_status,c.holdings_reason,"
        "c.document_status,c.document_reason,c.performance_status,c.performance_reason,"
        "c.as_of,c.source_document_id FROM meta.product_coverage c "
        "JOIN enriched.product_master p USING(product_id) "
        "WHERE (%(product_id)s::text IS NULL OR p.product_id=%(product_id)s::text) "
        "AND (%(status)s::text IS NULL OR c.holdings_status=%(status)s::text "
        "OR c.document_status=%(status)s::text OR c.performance_status=%(status)s::text) "
        "ORDER BY p.product_type,p.name",
        {"product_id": product_id, "status": status},
    )


@app.get("/db/version")
def db_version() -> dict[str, Any]:
    return run_sql(
        "SELECT dataset_version,release_date,cutoff_date,domain_as_of,source_files,"
        "source_hash,built_at,%(release_id)s::text AS release_id "
        "FROM meta.dataset_snapshot ORDER BY built_at DESC LIMIT 1",
        {"release_id": RELEASE_ID},
    )
