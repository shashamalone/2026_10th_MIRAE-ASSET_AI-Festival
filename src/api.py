# -*- coding: utf-8 -*-
"""PostgreSQL·Oxigraph·pgvector 읽기전용 호환 API."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from typing import Any, Literal

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from data_api.contracts import (
    EvidenceSearchRequest,
    OntologyValidateRequest,
    ProductCompareRequest,
    ProductQueryRequest,
    ProductSearchRequest,
    RelationTraverseRequest,
)
from data_api.service import (
    QUESTION_CAPABILITY_MAP,
    DataApiError,
    compare_statement,
    domain_detail_statement,
    holdings_statement,
    metric_evidence,
    product_query_statement,
    product_search_statement,
    relation_statement,
    same_vehicle_sparql,
    validate_ontology_request,
)
from kb.v2_manifest import (
    EXPECTED_ABOX_TRIPLES,
    EXPECTED_SNAPSHOT_HASH,
    EXTERNAL_CUTOFF,
    RELEASE_ID,
)
from tools.sql_guard import ensure_read_only_sparql, ensure_read_only_sql

APP_VERSION = "3.0.0"
MAX_ROWS = int(os.environ.get("API_MAX_ROWS", "100"))
# 운영 계약의 2초 상한은 환경변수로 완화할 수 없다. 필요하면 더 짧게만 조정한다.
STATEMENT_TIMEOUT_MS = min(2000, max(1, int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "2000"))))
GRAPH_QUERY_TIMEOUT_SECONDS = min(
    10.0, max(2.0, float(os.environ.get("GRAPH_QUERY_TIMEOUT_SECONDS", "10")))
)
OXIGRAPH_URL = os.environ.get("OXIGRAPH_URL", "http://graph:7878").rstrip("/")
PUBLIC_CURATED_ONLY = os.environ.get("API_PUBLIC_CURATED_ONLY", "0").lower() in {"1", "true", "yes"}
PUBLIC_TEST_MODE = os.environ.get("PUBLIC_TEST_MODE", "0").lower() in {"1", "true", "yes"}
PUBLIC_TEST_EXPIRES_AT = os.environ.get("PUBLIC_TEST_EXPIRES_AT", "").strip()
PUBLIC_RATE_LIMIT_PER_MINUTE = min(
    600, max(1, int(os.environ.get("PUBLIC_RATE_LIMIT_PER_MINUTE", "60")))
)
MAX_BODY_BYTES = min(1_048_576, max(1024, int(os.environ.get("API_MAX_BODY_BYTES", "1048576"))))
EXPECTED_ABOX_GRAPHS = {
    "http://mafest.ai/graph/abox/bond_kr",
    "http://mafest.ai/graph/abox/etf_kr",
    "http://mafest.ai/graph/abox/etf_gl",
    "http://mafest.ai/graph/abox/fund_pub",
    "http://mafest.ai/graph/abox/company",
}

app = FastAPI(
    title="금융상품 데이터 플랫폼",
    version=APP_VERSION,
    docs_url=None if PUBLIC_CURATED_ONLY else "/docs",
    redoc_url=None if PUBLIC_CURATED_ONLY else "/redoc",
)
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCK = threading.Lock()


class DbRequest(BaseModel):
    query: str | None = Field(default=None, min_length=1, max_length=100_000)
    sql: str | None = Field(default=None, min_length=1, max_length=100_000)
    sparql: str | None = Field(default=None, min_length=1, max_length=100_000)
    params: dict[str, Any] = Field(default_factory=dict)


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
    if PUBLIC_CURATED_ONLY and (request.url.path == "/db" or request.url.path.startswith("/db/")):
        return JSONResponse(
            status_code=404,
            content=_problem("ROUTE_NOT_PUBLIC", "임의 SQL/SPARQL 경로는 공개 프로필에서 사용할 수 없습니다"),
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


@app.exception_handler(DataApiError)
async def data_api_error_handler(_request: Request, exc: DataApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(_problem(exc.code, exc.message, exc.details)),
    )


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


def v1_envelope(
    data: Any,
    *,
    started: float,
    evidence: list[dict[str, Any]] | None = None,
    coverage: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "release_id": RELEASE_ID,
        "snapshot_hash": EXPECTED_SNAPSHOT_HASH,
        "data": data,
        "coverage": coverage,
        "evidence": evidence or [],
        "elapsed_ms": elapsed_ms(started),
        "truncated": bool((meta or {}).get("truncated", False)),
        "meta": meta or {},
    }


def _rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(result.get("rows") or [])


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
    result["public_profile"] = {
        "curated_only": PUBLIC_CURATED_ONLY,
        "temporary_public_test": PUBLIC_TEST_MODE,
        "expires_at": PUBLIC_TEST_EXPIRES_AT or None,
    }
    return result


@app.get("/v1/release")
def v1_release() -> dict[str, Any]:
    started = time.perf_counter()
    rows = _rows(
        run_sql(
            """
            SELECT d.dataset_version,d.release_date,d.cutoff_date,d.domain_as_of,
                   d.source_hash,d.built_at,l.run_id,l.status AS run_status,l.phase,
                   COALESCE(l.validation_result->>'vector_status','pending') AS canonical_vector_status
            FROM meta.dataset_snapshot d
            LEFT JOIN LATERAL (
              SELECT run_id,status,phase,validation_result FROM meta.load_run
              WHERE snapshot_id=d.snapshot_id ORDER BY started_at DESC LIMIT 1
            ) l ON true
            ORDER BY d.built_at DESC LIMIT 1
            """
        )
    )
    if not rows:
        raise DataApiError(503, "RELEASE_NOT_READY", "활성 dataset snapshot이 없습니다")
    relation = _rows(run_sql("SELECT to_regclass('vec_demo.document_chunk')::text AS table_name"))[0]
    demo_count = 0
    if relation.get("table_name"):
        demo_count = int(_rows(run_sql("SELECT count(*) AS row_count FROM vec_demo.document_chunk"))[0]["row_count"])
    data = {
        **rows[0],
        "release_id": RELEASE_ID,
        "demo_vector": {
            "index_status": "demo" if demo_count == 2 else "not_ready",
            "production_ready": False,
            "seed_count": demo_count,
            "embedding_model": "bge-m3",
            "embedding_dim": 1024,
        },
    }
    return v1_envelope(
        data,
        started=started,
        evidence=[{"source": "meta.dataset_snapshot", "value": rows[0]["source_hash"]}],
    )


@app.get("/v1/capabilities")
def v1_capabilities() -> dict[str, Any]:
    started = time.perf_counter()
    data = [QUESTION_CAPABILITY_MAP[question_id] for question_id in range(1, 36)]
    counts = {
        status: sum(item["status"] == status for item in data)
        for status in ("ready", "partial", "gap")
    }
    return v1_envelope(
        data,
        started=started,
        coverage={"question_count": 35, "status_counts": counts},
        meta={"submission_ready": False, "reason": "known evidence gaps remain"},
    )


@app.post("/v1/products/search")
def v1_product_search(request: ProductSearchRequest) -> dict[str, Any]:
    started = time.perf_counter()
    statement, params = product_search_statement(request)
    result = run_sql(statement, params)
    rows = _rows(result)
    evidence = [
        {
            "subject": row["product_id"],
            "source": row["source_table"],
            "source_column": "source_key",
            "as_of": row["effective_as_of"],
            "value": row["source_key"],
            "match_type": row["match_type"],
        }
        for row in rows
    ]
    return v1_envelope(
        rows,
        started=started,
        evidence=evidence,
        coverage={"status": "available" if rows else "entity_not_found"},
        meta={"truncated": result["truncated"], "requested_match": request.match},
    )


@app.post("/v1/products/query")
def v1_product_query(request: ProductQueryRequest) -> dict[str, Any]:
    started = time.perf_counter()
    statement, params = product_query_statement(request)
    result = run_sql(statement, params)
    rows = _rows(result)
    evidence = []
    for row in rows:
        evidence.append(
            {
                "subject": row["product_id"],
                "source": row["source_table"],
                "source_column": "source_key",
                "as_of": row["effective_as_of"],
                "value": row["source_key"],
            }
        )
        evidence.extend(metric_evidence(row))
    return v1_envelope(
        rows,
        started=started,
        evidence=evidence,
        coverage={"status": "available", "returned_products": len(rows)},
        meta={"truncated": result["truncated"], "sort_by": request.sort_by},
    )


@app.get("/v1/products/{product_id}")
def v1_product_detail(product_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    master_rows = _rows(
        run_sql(
            """
            SELECT p.*,c.holdings_status,c.holdings_reason,c.document_status,c.document_reason,
                   c.performance_status,c.performance_reason,c.as_of AS coverage_as_of,
                   c.source_document_id AS coverage_document_id
            FROM enriched.product_master p
            LEFT JOIN meta.product_coverage c USING(product_id)
            WHERE p.product_id=%(product_id)s
            """,
            {"product_id": product_id},
        )
    )
    if not master_rows:
        raise DataApiError(404, "ENTITY_NOT_FOUND", "product_id를 찾을 수 없습니다", {"product_id": product_id})
    product = master_rows[0]
    domain_rows = _rows(
        run_sql(domain_detail_statement(product["product_type"]), {"product_id": product_id})
    )
    metrics = _rows(
        run_sql(
            """
            SELECT DISTINCT ON (metric_code) metric_code,value,unit,as_of,source,source_column,
                   method,is_available,unavailable_reason,source_priority
            FROM enriched.product_metric WHERE product_id=%(product_id)s
            ORDER BY metric_code,is_available DESC,source_priority,as_of DESC NULLS LAST,metric_id
            """,
            {"product_id": product_id},
        )
    )
    coverage = {
        "holdings_status": product.pop("holdings_status", None),
        "holdings_reason": product.pop("holdings_reason", None),
        "document_status": product.pop("document_status", None),
        "document_reason": product.pop("document_reason", None),
        "performance_status": product.pop("performance_status", None),
        "performance_reason": product.pop("performance_reason", None),
        "as_of": product.pop("coverage_as_of", None),
        "source_document_id": product.pop("coverage_document_id", None),
    }
    evidence = [
        {
            "subject": product_id,
            "source": product["source_table"],
            "source_column": "source_key",
            "as_of": product["effective_as_of"],
            "value": product["source_key"],
        }
    ]
    evidence.extend(
        {
            "subject": product_id,
            "metric_code": metric["metric_code"],
            "value": metric["value"],
            "unit": metric["unit"],
            "as_of": metric["as_of"],
            "source": metric["source"],
            "source_column": metric["source_column"],
            "is_available": metric["is_available"],
            "unavailable_reason": metric["unavailable_reason"],
        }
        for metric in metrics
    )
    return v1_envelope(
        {
            "product": product,
            "attributes": domain_rows[0]["attributes"] if domain_rows else {},
            "metrics": metrics,
        },
        started=started,
        evidence=evidence,
        coverage=coverage,
    )


@app.post("/v1/products/compare")
def v1_product_compare(request: ProductCompareRequest) -> dict[str, Any]:
    started = time.perf_counter()
    statement, params = compare_statement(request.product_ids, request.metric_codes)
    rows = _rows(run_sql(statement, params))
    missing = sorted({row["product_id"] for row in rows if row.get("name") is None})
    if missing:
        raise DataApiError(404, "ENTITY_NOT_FOUND", "일부 product_id를 찾을 수 없습니다", {"product_ids": missing})
    for metric_code in request.metric_codes:
        units = {
            row["unit"]
            for row in rows
            if row["metric_code"] == metric_code and row.get("is_available") and row.get("unit")
        }
        if len(units) > 1:
            raise DataApiError(
                422,
                "UNIT_MISMATCH",
                f"{metric_code}는 서로 다른 단위를 직접 비교할 수 없습니다",
                {"metric_code": metric_code, "units": sorted(units)},
            )
    evidence = [
        {
            "subject": row["product_id"],
            "metric_code": row["metric_code"],
            "value": row["value"],
            "unit": row["unit"],
            "as_of": row["as_of"],
            "source": row["source"],
            "source_column": row["source_column"],
            "is_available": row["is_available"],
            "unavailable_reason": row["unavailable_reason"],
        }
        for row in rows
    ]
    return v1_envelope(rows, started=started, evidence=evidence, coverage={"status": "available"})


@app.get("/v1/products/{product_id}/holdings")
def v1_product_holdings(
    product_id: str,
    as_of: str = "latest",
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    started = time.perf_counter()
    coverage_rows = _rows(
        run_sql(
            """
            SELECT p.product_id,p.product_type,p.name,c.holdings_status,c.holdings_reason,
                   c.as_of,c.source_document_id
            FROM enriched.product_master p LEFT JOIN meta.product_coverage c USING(product_id)
            WHERE p.product_id=%(product_id)s
            """,
            {"product_id": product_id},
        )
    )
    if not coverage_rows:
        raise DataApiError(404, "ENTITY_NOT_FOUND", "product_id를 찾을 수 없습니다", {"product_id": product_id})
    coverage = coverage_rows[0]
    if coverage.get("holdings_status") != "available":
        return v1_envelope([], started=started, evidence=[], coverage=coverage)
    parsed_as_of: str | date = as_of
    if as_of != "latest":
        try:
            parsed_as_of = date.fromisoformat(as_of)
        except ValueError as exc:
            raise DataApiError(422, "INVALID_AS_OF", "as_of는 latest 또는 YYYY-MM-DD여야 합니다") from exc
    statement, params = holdings_statement(product_id, parsed_as_of, limit)
    result = run_sql(statement, params)
    rows = _rows(result)
    evidence = [
        {
            "subject": row["holding_id"],
            "product_id": row["product_id"],
            "security_id": row["security_id"],
            "value": row["weight"],
            "unit": row["unit"],
            "as_of": row["as_of"],
            "source": row["source"],
            "document_id": row["source_document_id"],
            "document_title": row["document_title"],
            "published_at": row["published_at"],
            "source_url": row["source_url"],
        }
        for row in rows
    ]
    return v1_envelope(
        rows,
        started=started,
        evidence=evidence,
        coverage=coverage,
        meta={"truncated": result["truncated"], "requested_as_of": as_of},
    )


@app.post("/v1/relations/traverse")
async def v1_relation_traverse(request: RelationTraverseRequest) -> dict[str, Any]:
    started = time.perf_counter()
    built = relation_statement(request)
    if built is None:
        result = await run_sparql(same_vehicle_sparql(request.start_entity_id, request.limit))
        rows = [
            {
                "relation_type": "same_vehicle_as",
                "start_entity_id": request.start_entity_id,
                "end_entity_id": row.get("related", "").removeprefix("http://mafest.ai/instance/"),
            }
            for row in _rows(result)
        ]
        evidence = [
            {"subject": request.start_entity_id, "source": "GraphDB", "predicate": "fp:sameVehicleAs"}
            for _row in rows
        ]
        return v1_envelope(
            rows,
            started=started,
            evidence=evidence,
            coverage={
                "status": "available" if rows else "unavailable",
                "reason": None if rows else "sameVehicleAs ABox 관계 미확보",
            },
            meta={"truncated": result["truncated"], "path": request.path},
        )
    statement, params = built
    result = run_sql(statement, params)
    rows = _rows(result)
    evidence = [
        {
            "subject": row.get("start_entity_id") or request.start_entity_id,
            "relation": row.get("relation_type") or "/".join(request.path),
            "object": row.get("end_entity_id") or row.get("security_id"),
            "source": row.get("source") or row.get("relation_source"),
            "as_of": row.get("as_of") or row.get("relation_as_of"),
            "document_id": row.get("source_document_id") or row.get("relation_document_id"),
            "source_column": row.get("source_column"),
        }
        for row in rows
    ]
    return v1_envelope(
        rows,
        started=started,
        evidence=evidence,
        coverage={"status": "available" if rows else "unavailable"},
        meta={"truncated": result["truncated"], "path": request.path},
    )


@app.post("/v1/ontology/validate")
def v1_ontology_validate(request: OntologyValidateRequest) -> dict[str, Any]:
    started = time.perf_counter()
    product_type = None
    if request.validation_type == "relation_domain" and request.subject_product_id:
        rows = _rows(
            run_sql(
                "SELECT product_type FROM enriched.product_master WHERE product_id=%(product_id)s",
                {"product_id": request.subject_product_id},
            )
        )
        product_type = rows[0]["product_type"] if rows else None
    data = validate_ontology_request(request, product_type)
    evidence = [data["evidence"]] if data.get("evidence") else []
    return v1_envelope(data, started=started, evidence=evidence)


@app.post("/v1/evidence/semantic-search")
def v1_evidence_semantic_search(request: EvidenceSearchRequest) -> dict[str, Any]:
    started = time.perf_counter()
    relation = _rows(run_sql("SELECT to_regclass('vec_demo.document_chunk')::text AS table_name"))[0]
    if not relation.get("table_name"):
        raise DataApiError(503, "VECTOR_NOT_READY", "데모 문서 벡터 테이블이 아직 적재되지 않았습니다")
    seed_count = int(_rows(run_sql("SELECT count(*) AS row_count FROM vec_demo.document_chunk"))[0]["row_count"])
    if seed_count != 2:
        raise DataApiError(
            503,
            "VECTOR_NOT_READY",
            "데모 인덱스는 정확히 2개 청크여야 합니다",
            {"seed_count": seed_count},
        )
    vector = "[" + ",".join(format(value, ".10g") for value in request.query_embedding) + "]"
    result = run_sql(
        """
        SELECT c.chunk_id,c.document_id,c.product_id,c.page_number,c.locator,c.citation_text,
               c.published_at,c.source_url,c.content_hash,d.title,d.publisher,d.source_type,
               d.source_hash,1-(c.embedding <=> %(embedding)s::vector) AS score
        FROM vec_demo.document_chunk c
        JOIN vec_demo.source_document d USING(document_id)
        WHERE c.published_at<=%(cutoff)s::date
          AND (%(product_ids)s::text[] IS NULL OR c.product_id=ANY(%(product_ids)s::text[]))
        ORDER BY c.embedding <=> %(embedding)s::vector,c.chunk_id
        LIMIT %(top_k)s
        """,
        {
            "embedding": vector,
            "cutoff": EXTERNAL_CUTOFF,
            "product_ids": request.candidate_product_ids,
            "top_k": request.top_k,
        },
    )
    rows = _rows(result)
    evidence = [
        {
            "subject": row.get("product_id") or row["document_id"],
            "document_id": row["document_id"],
            "document_title": row["title"],
            "source": row["publisher"],
            "published_at": row["published_at"],
            "source_url": row["source_url"],
            "locator": row["locator"],
            "citation_text": row["citation_text"],
            "content_hash": row["content_hash"],
            "score": row["score"],
        }
        for row in rows
    ]
    return v1_envelope(
        rows,
        started=started,
        evidence=evidence,
        coverage={"status": "available" if rows else "no_match"},
        meta={
            "truncated": result["truncated"],
            "index_status": "demo",
            "production_ready": False,
            "seed_count": seed_count,
            "embedding_model": "bge-m3",
            "embedding_dim": 1024,
        },
    )


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
        "ORDER BY p.product_id LIMIT %(fetch_limit)s",
        {"product_id": product_id, "status": status, "fetch_limit": MAX_ROWS + 1},
    )


@app.get("/db/version")
def db_version() -> dict[str, Any]:
    return run_sql(
        "SELECT dataset_version,release_date,cutoff_date,domain_as_of,source_files,"
        "source_hash,built_at,%(release_id)s::text AS release_id "
        "FROM meta.dataset_snapshot ORDER BY built_at DESC LIMIT 1",
        {"release_id": RELEASE_ID},
    )
