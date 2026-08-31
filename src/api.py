# -*- coding: utf-8 -*-
"""PostgreSQL·Oxigraph·pgvector 읽기 전용 raw query API."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from kb.v2_manifest import (
    EXPECTED_SNAPSHOT_HASH,
    RELEASE_ID,
)
from tools.sql_guard import ensure_read_only_sparql, ensure_read_only_sql

APP_VERSION = "4.0.0"
MAX_ROWS = int(os.environ.get("API_MAX_ROWS", "100"))
# 운영 계약의 2초 상한은 환경변수로 완화할 수 없다. 필요하면 더 짧게만 조정한다.
STATEMENT_TIMEOUT_MS = min(2000, max(1, int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "2000"))))
GRAPH_QUERY_TIMEOUT_SECONDS = min(
    10.0, max(2.0, float(os.environ.get("GRAPH_QUERY_TIMEOUT_SECONDS", "10")))
)
OXIGRAPH_URL = os.environ.get("OXIGRAPH_URL", "http://graph:7878").rstrip("/")
PUBLIC_TEST_MODE = os.environ.get("PUBLIC_TEST_MODE", "0").lower() in {"1", "true", "yes"}
PUBLIC_TEST_EXPIRES_AT = os.environ.get("PUBLIC_TEST_EXPIRES_AT", "").strip()
PUBLIC_RATE_LIMIT_PER_MINUTE = min(
    600, max(1, int(os.environ.get("PUBLIC_RATE_LIMIT_PER_MINUTE", "60")))
)
MAX_BODY_BYTES = min(1_048_576, max(1024, int(os.environ.get("API_MAX_BODY_BYTES", "1048576"))))
MAX_QUERY_CHARS = 100_000
EXPECTED_GRAPH_TRIPLES = int(os.environ.get("EXPECTED_GRAPH_TRIPLES", "1628311"))

app = FastAPI(
    title="금융상품 Raw Query API",
    version=APP_VERSION,
)
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCK = threading.Lock()


def dsn() -> str:
    """Read-only runtime DSN without importing the build-time pipeline."""
    if value := os.environ.get("DATABASE_URL"):
        return value
    if not os.environ.get("PGDATABASE"):
        raise RuntimeError(
            "DATABASE_URL 또는 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE를 환경변수로 제공하세요"
        )
    values = {
        "host": os.environ.get("PGHOST", "127.0.0.1"),
        "port": os.environ.get("PGPORT", "5432"),
        "user": os.environ.get("PGUSER", "agent_reader"),
        "password": os.environ.get("PGPASSWORD", ""),
        "dbname": os.environ["PGDATABASE"],
    }
    return " ".join(f"{key}={value}" for key, value in values.items())


def _problem(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "release_id": RELEASE_ID,
        "details": details or {},
    }


def _parse_public_expiry() -> datetime | None:
    if not PUBLIC_TEST_EXPIRES_AT:
        return None
    try:
        parsed = datetime.fromisoformat(PUBLIC_TEST_EXPIRES_AT.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@app.middleware("http")
async def public_api_guard(request: Request, call_next):
    if request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content=_problem("REQUEST_TOO_LARGE", "요청 본문이 1MB 제한을 초과했습니다"),
                )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content=_problem("INVALID_CONTENT_LENGTH", "Content-Length가 올바르지 않습니다"),
            )
    if PUBLIC_TEST_MODE and request.url.path != "/health":
        expiry = _parse_public_expiry()
        if expiry is None:
            return JSONResponse(
                status_code=503,
                content=_problem("PUBLIC_TEST_EXPIRY_INVALID", "PUBLIC_TEST_EXPIRES_AT 설정이 필요합니다"),
            )
        if datetime.now(timezone.utc) >= expiry:
            return JSONResponse(
                status_code=503,
                content=_problem("PUBLIC_TEST_EXPIRED", "임시 공개 기간이 만료되었습니다"),
            )
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _RATE_LOCK:
            bucket = _RATE_BUCKETS[client]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= PUBLIC_RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=429,
                    content=_problem("RATE_LIMITED", "분당 요청 한도를 초과했습니다"),
                )
            bucket.append(now)
    response = await call_next(request)
    if PUBLIC_TEST_MODE:
        response.headers["X-Financial-API-Exposure"] = "temporary-public-test"
        response.headers["X-Financial-API-Expires-At"] = PUBLIC_TEST_EXPIRES_AT
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {key: value for key, value in error.items() if key != "ctx"}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            _problem("INVALID_REQUEST", "요청 계약을 충족하지 않습니다", {"errors": errors})
        ),
    )


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


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
        async with httpx.AsyncClient(timeout=GRAPH_QUERY_TIMEOUT_SECONDS) as client:
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
            "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }"
        )
        graph_triples = (
            int(count_result["rows"][0]["triples"]) if count_result["rows"] else None
        )
        graph_result = await run_sparql(
            "SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }"
        )
        graph_names = {row["g"] for row in graph_result["rows"]}
        if graph_triples == EXPECTED_GRAPH_TRIPLES and graph_names:
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
    result["public_profile"] = {
        "raw_query_only": True,
        "temporary_public_test": PUBLIC_TEST_MODE,
        "expires_at": PUBLIC_TEST_EXPIRES_AT or None,
    }
    return result


RAW_QUERY_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "text/plain": {
                "schema": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
                "examples": {
                    "query": {
                        "summary": "쿼리 원문",
                        "value": "SELECT 1 AS probe",
                    }
                },
            }
        },
    }
}


async def read_raw_query(request: Request) -> str:
    """Read one UTF-8 text/plain SQL or SPARQL statement from the request body."""
    content_type = request.headers.get("content-type", "")
    parts = [part.strip() for part in content_type.split(";") if part.strip()]
    media_type = parts[0].lower() if parts else ""
    if media_type != "text/plain":
        raise HTTPException(
            status_code=415,
            detail="Content-Type은 text/plain; charset=utf-8 이어야 합니다",
        )
    for parameter in parts[1:]:
        name, separator, value = parameter.partition("=")
        if name.strip().lower() == "charset" and (
            not separator or value.strip().strip('"').lower() not in {"utf-8", "utf8"}
        ):
            raise HTTPException(status_code=415, detail="쿼리 본문은 UTF-8이어야 합니다")

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="요청 본문이 1MB 제한을 초과했습니다")
    try:
        statement = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="쿼리 본문은 유효한 UTF-8이어야 합니다") from exc
    if not statement.strip():
        raise HTTPException(status_code=400, detail="빈 쿼리는 실행할 수 없습니다")
    if "\\x00" in statement:
        raise HTTPException(status_code=400, detail="쿼리 본문에 NUL 문자를 사용할 수 없습니다")
    if len(statement) > MAX_QUERY_CHARS:
        raise HTTPException(status_code=413, detail="쿼리는 100,000자를 초과할 수 없습니다")
    return statement


@app.post("/db/sql", openapi_extra=RAW_QUERY_OPENAPI)
async def db_sql(request: Request) -> dict[str, Any]:
    return run_sql(await read_raw_query(request))


@app.post("/db/sparql", openapi_extra=RAW_QUERY_OPENAPI)
async def db_sparql(request: Request) -> dict[str, Any]:
    return await run_sparql(await read_raw_query(request))


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


@app.get("/db/version")
def db_version() -> dict[str, Any]:
    return run_sql(
        "SELECT dataset_version,release_date,cutoff_date,domain_as_of,source_files,"
        "source_hash,built_at,%(release_id)s::text AS release_id "
        "FROM meta.dataset_snapshot ORDER BY built_at DESC LIMIT 1",
        {"release_id": RELEASE_ID},
    )
