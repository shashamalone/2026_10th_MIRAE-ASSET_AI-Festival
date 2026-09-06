# -*- coding: utf-8 -*-
"""PostgreSQL·Oxigraph·pgvector 읽기 전용 raw query API."""
from __future__ import annotations

import asyncio
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
import serve_answer

APP_VERSION = "4.3.0"
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
EXPECTED_GRAPH_TRIPLES = int(os.environ.get("EXPECTED_GRAPH_TRIPLES", "1226698"))
VECTOR_MODEL_ID = "BAAI/bge-m3"
VECTOR_DIMENSION = 1024
VECTOR_HNSW_INDEXES = 3
VECTOR_SEARCH_FUNCTIONS = 2
VECTOR_COUNT_KEYS = {
    "bond_schema_terms": "bond_schema_terms.jsonl",
    "schema_terms_all": "schema_terms_all.jsonl",
    "source_document": "source_documents.jsonl",
    "document_product": "product_documents.jsonl",
    "product_coverage": "prospectus_coverage.jsonl",
    "chunk_embedding": "chunk_embeddings.jsonl",
    "document_chunk": "document_chunks.jsonl",
}
VECTOR_BASE_COUNTS = {
    "bond_schema_terms": 130,
    "schema_terms_all": 189,
    "source_document": 974,
    "document_product": 1_019,
    "product_coverage": 15_951,
    "chunk_embedding": 5_664,
    "document_chunk": 9_055,
}
# SEC EDGAR 해외ETF 근거를 기존 active 벡터 릴리스에 멱등 증분 적재한 수량.
# vec.vector_deploy_run은 재배포가 아닌 증분 적재이므로 원래 base 수량을 보존한다.
VECTOR_SUPPLEMENTAL_COUNTS = {
    "bond_schema_terms": 0,
    "schema_terms_all": 0,
    "source_document": 63,
    "document_product": 203,
    "product_coverage": 182,
    "chunk_embedding": 916,
    "document_chunk": 916,
}
VECTOR_LIVE_COUNTS = {
    table: VECTOR_BASE_COUNTS[table] + VECTOR_SUPPLEMENTAL_COUNTS[table]
    for table in VECTOR_BASE_COUNTS
}

app = FastAPI(
    title="금융상품 Raw Query API",
    version=APP_VERSION,
)
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCK = threading.Lock()


@app.on_event("startup")
def load_answer_pipeline() -> None:
    """Load the shared LangGraph pipeline once for GET /answer."""
    serve_answer._load_pipeline()


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


def _same_int(*values: Any) -> bool:
    """Compare datastore counters while treating malformed metadata as not ready."""
    try:
        integers = [int(value) for value in values]
    except (TypeError, ValueError):
        return False
    return len(set(integers)) == 1


def vector_health() -> dict[str, Any]:
    """Validate the active vector release against live tables and runtime objects."""
    rows = run_sql(
        """
        WITH latest AS (
          SELECT run_id,release_id,model_id,model_revision,embedding_dim,status,
                 expected_counts,observed_counts,created_at,updated_at,cutover_at
          FROM vec.vector_deploy_run
          ORDER BY cutover_at DESC NULLS LAST,updated_at DESC
          LIMIT 1
        )
        SELECT latest.*,
               jsonb_build_object(
                 'bond_schema_terms',(SELECT count(*) FROM vec.bond_schema_terms),
                 'schema_terms_all',(SELECT count(*) FROM vec.schema_terms_all),
                 'source_document',(SELECT count(*) FROM vec.source_document),
                 'document_product',(SELECT count(*) FROM vec.document_product),
                 'product_coverage',(SELECT count(*) FROM vec.product_coverage),
                 'chunk_embedding',(SELECT count(*) FROM vec.chunk_embedding),
                 'document_chunk',(SELECT count(*) FROM vec.document_chunk)
               ) AS table_counts,
               (SELECT count(*)
                FROM pg_index i
                JOIN pg_class c ON c.oid=i.indexrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_am a ON a.oid=c.relam
                WHERE n.nspname='vec' AND a.amname='hnsw') AS hnsw_indexes,
               (SELECT count(*)
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='vec'
                  AND p.proname IN ('search_schema_terms','search_document_chunks')
                  AND has_function_privilege(current_user,p.oid,'EXECUTE')) AS search_functions
        FROM latest
        """
    )["rows"]
    if not rows:
        return {
            "status": "unavailable",
            "ready": False,
            "table_counts": {},
            "hnsw_indexes": 0,
            "search_functions": 0,
        }

    vector = dict(rows[0])
    expected = vector.get("expected_counts")
    observed = vector.get("observed_counts")
    actual = vector.get("table_counts")
    expected = expected if isinstance(expected, dict) else {}
    observed = observed if isinstance(observed, dict) else {}
    actual = actual if isinstance(actual, dict) else {}
    vector["table_counts"] = actual
    base_counts_match = all(
        _same_int(observed.get(table), VECTOR_BASE_COUNTS[table])
        and _same_int(expected.get(filename), VECTOR_BASE_COUNTS[table])
        for table, filename in VECTOR_COUNT_KEYS.items()
    )
    live_counts_match = all(
        _same_int(actual.get(table), VECTOR_LIVE_COUNTS[table])
        for table in VECTOR_COUNT_KEYS
    )
    vector["base_counts"] = dict(VECTOR_BASE_COUNTS)
    vector["supplemental_counts"] = dict(VECTOR_SUPPLEMENTAL_COUNTS)
    vector["live_expected_counts"] = dict(VECTOR_LIVE_COUNTS)
    vector["ready"] = bool(
        vector.get("status") == "active"
        and vector.get("release_id") == RELEASE_ID
        and vector.get("model_id") == VECTOR_MODEL_ID
        and _same_int(vector.get("embedding_dim"), VECTOR_DIMENSION)
        and base_counts_match
        and live_counts_match
        and _same_int(vector.get("hnsw_indexes"), VECTOR_HNSW_INDEXES)
        and _same_int(vector.get("search_functions"), VECTOR_SEARCH_FUNCTIONS)
    )
    return vector


@app.get("/health")
async def health() -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "degraded",
        "api_version": APP_VERSION,
        "release_id": RELEASE_ID,
        "snapshot_hash": EXPECTED_SNAPSHOT_HASH,
        "clova_configured": bool(
            os.environ.get("CLOVA_API_KEY")
            or os.environ.get("CLOVASTUDIO_API_KEY")
            or os.environ.get("CLOVA_STUDIO_API_KEY")
        ),
        "clova_embedding_model": "bge-m3",
        "answer_pipeline_loaded": serve_answer._APP is not None,
        "answer_pipeline_error": serve_answer._IMPORT_ERROR,
        "answer_timeout_seconds": serve_answer.TIMEOUT_SECONDS,
        "readiness": False,
    }
    rdb_hash = None
    rdb_release = None
    run_status = None
    run_phase = None
    vector: dict[str, Any] = {
        "status": "unavailable",
        "ready": False,
        "table_counts": {},
        "hnsw_indexes": 0,
        "search_functions": 0,
    }
    try:
        version_rows = run_sql(
            """
            SELECT d.dataset_version,d.release_date,d.cutoff_date,d.domain_as_of,
                   d.source_hash,d.built_at,l.run_id,l.status AS run_status,
                   l.phase AS run_phase
            FROM meta.dataset_snapshot d
            LEFT JOIN LATERAL (
              SELECT run_id,status,phase
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
        vector = vector_health()
        data = version_rows[0] if version_rows else None
        if data:
            rdb_hash = data["source_hash"]
            rdb_release = f"{data['dataset_version']}@{rdb_hash}"
            run_status = data.get("run_status")
            run_phase = data.get("run_phase")
        result.update(
            {
                "data": data,
                "rdb_rows": rdb_rows,
                "vector_rows": [
                    {"table_name": table, "row_count": count}
                    for table, count in (vector.get("table_counts") or {}).items()
                ],
                "vector_status": vector.get("status", "unavailable"),
                "vector": vector,
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
                    "expected_triples": EXPECTED_GRAPH_TRIPLES,
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
                    "expected_triples": EXPECTED_GRAPH_TRIPLES,
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
        and vector.get("ready") is True
        and result["clova_configured"] is True
        and result["answer_pipeline_loaded"] is True
    )
    result["status"] = "ok" if result["readiness"] else "degraded"
    result["public_profile"] = {
        "raw_query_only": False,
        "raw_query_available": True,
        "answer_available": True,
        "temporary_public_test": PUBLIC_TEST_MODE,
        "expires_at": PUBLIC_TEST_EXPIRES_AT or None,
    }
    return result


@app.get("/answer")
async def answer(question_id: str = "", question: str = "") -> JSONResponse:
    """Return the competition's exact five-string-field answer envelope.

    Pipeline work runs outside the event loop because it makes blocking LLM and
    Data API calls. Every failure, including timeout, remains HTTP 200 so the
    evaluator can always parse the required response contract.
    """
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(serve_answer.answer, question_id, question),
            timeout=serve_answer.TIMEOUT_SECONDS,
        )
    except TimeoutError:
        payload = serve_answer._envelope(
            question_id,
            question,
            answer="제공된 데이터로는 제한 시간 안에 답변을 완성하지 못했습니다.",
            think_trace=f"제한 시간 {serve_answer.TIMEOUT_SECONDS:.0f}초 초과로 중단",
        )
    except Exception as exc:  # final HTTP contract guard
        payload = serve_answer._envelope(
            question_id,
            question,
            answer="제공된 데이터로는 이 질문에 답변할 수 없습니다. (조회 중 오류가 발생했습니다)",
            think_trace=f"실행 오류: {type(exc).__name__}: {exc}",
        )
    return JSONResponse(
        content=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


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
    if "\x00" in statement:
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
        UNION ALL SELECT 'vec.source_document',count(*) FROM vec.source_document
        UNION ALL SELECT 'vec.document_product',count(*) FROM vec.document_product
        UNION ALL SELECT 'vec.product_coverage',count(*) FROM vec.product_coverage
        UNION ALL SELECT 'vec.chunk_embedding',count(*) FROM vec.chunk_embedding
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
