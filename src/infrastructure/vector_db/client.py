"""
PostgreSQL/pgvector 기반 VectorDB 읽기 전용 클라이언트.

질의 임베딩과 ``vec`` 스키마의 정규화된 문서·임베딩·상품 연결 테이블을
사용해 근거 청크를 cosine similarity 순서로 반환한다. VectorDB 연결과
검색 SQL을 Agent 노드에서 분리하기 위한 infrastructure adapter다.

[구현 상태]

- 검색 대상: ``vec.document_chunk``의 청크 본문과
  ``vec.chunk_embedding``의 고유 content hash별 pgvector를 조인한다.
- 상품 제한: ``vec.document_product``를 ``EXISTS``로 조회해 상품별 검색을
  지원하며, 문서-상품 다대다 관계 때문에 검색 청크가 중복되지 않게 한다.
- 임베딩 계약: ``embedding_model = bge-m3``, ``embedding_dim = 1024``만
  검색한다. 질의 벡터 차원이 다르면 실행 전에 거부한다.
- 섹션 제한: ``section_types``를 주면 ``document_chunk.section_type``이
  그 목록에 있는 청크만 검색한다(요청 주제와 무관한 섹션 인용 방지).
- 검색 결과: cosine similarity 내림차순으로 정렬하고 top-k는 1~20건으로
  제한한다. 각 결과에 문서·청크·인용·기준일·상품 ID를 함께 반환한다.
- 연결 순서: ``DATABASE_URL`` 또는 ``PG*`` 환경변수가 있으면 직접
  PostgreSQL 연결을 사용한다. DSN이 없으면 기존 read-only SQL API로
  전환한다.
- timeout: 직접 PostgreSQL 연결은 ``VECTOR_DB_TIMEOUT``(기본 3초)을
  사용한다. SQL API 요청 timeout은 ``RDB_API_TIMEOUT`` 설정을 따른다.
- 부가 읽기 경로(``_run_read_sql`` 공용): ``resolve_product_ids``는
  ``enriched.product_master``로 raw 코드/상품명을 product_id로 해소하고,
  ``coverage``는 ``vec.product_coverage``의 문서 확보 상태를,
  ``search_schema_terms``는 ``vec.schema_terms_all`` 온톨로지 용어를 찾는다.

직접 연결 모드에는 ``psycopg2-binary``가 필요하다. 두 transport 모두
  검색 전용으로 사용하며, 이 클라이언트는 VectorDB 적재나 스키마 변경을
  수행하지 않는다.
"""
from __future__ import annotations

import os
import re
from typing import Any

VECTOR_DIMENSION = 1024
EMBEDDING_MODEL = "bge-m3"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(value: str, name: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {name}: {value!r}")
    return value


def _vector_literal(vector: list[float]) -> str:
    if len(vector) != VECTOR_DIMENSION:
        raise ValueError(f"query vector dimension must be {VECTOR_DIMENSION}")
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _sql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _inline(sql: str, params: list[Any]) -> str:
    """``%s`` 자리에 SQL 리터럴을 순서대로 채운다.

    SQL API transport에는 파라미터 바인딩이 없다. 그렇다고 transport마다
    SQL 문자열을 따로 쓰면 두 벌이 조용히 어긋나므로, 한 벌의 ``%s`` SQL을
    쓰고 API 경로에서만 이 함수로 인라인한다. 개수가 어긋나면 잘못된 쿼리를
    보내기 전에 실패시킨다."""
    parts = sql.split("%s")
    if len(parts) - 1 != len(params):
        raise ValueError(f"placeholder count {len(parts) - 1} != params {len(params)}")
    inlined = parts[0]
    for tail, value in zip(parts[1:], params):
        inlined += _sql_literal(value) + tail
    return inlined


class VectorDBClient:

    def __init__(
        self,
        *,
        schema: str | None = None,
        table: str = "document_chunk",
        embedding_table: str = "chunk_embedding",
        product_table: str = "document_product",
    ) -> None:
        self.schema = _identifier(schema or os.getenv("VECTOR_SCHEMA", "vec"), "VECTOR_SCHEMA")
        self.table = _identifier(table, "table")
        self.embedding_table = _identifier(embedding_table, "embedding_table")
        self.product_table = _identifier(product_table, "product_table")
        self.timeout = float(os.getenv("VECTOR_DB_TIMEOUT", "3"))

    @property
    def _has_direct_dsn(self) -> bool:
        return bool(os.getenv("DATABASE_URL") or os.getenv("PGDATABASE"))

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
        product_ids: list[str] | None = None,
        section_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        top_k = max(1, min(int(top_k), 20))
        vector = _vector_literal(query_vector)
        if self._has_direct_dsn:
            return self._search_direct(vector, top_k, product_ids, section_types)
        return self._search_api(vector, top_k, product_ids, section_types)

    @property
    def _tables(self) -> tuple[str, str, str]:
        return tuple(
            f'"{self.schema}"."{name}"'
            for name in (self.table, self.embedding_table, self.product_table)
        )

    def _api_sql(
        self,
        vector: str,
        top_k: int,
        product_ids: list[str] | None,
        section_types: list[str] | None = None,
    ) -> str:
        chunks, embeddings, products = self._tables
        product_filter = ""
        if product_ids:
            quoted = ",".join("'" + str(pid).replace("'", "''") + "'" for pid in product_ids)
            product_filter = f"""
              AND EXISTS (
                    SELECT 1
                    FROM {products} AS dp_filter
                    WHERE dp_filter.document_id = dc.document_id
                      AND dp_filter.product_id IN ({quoted})
              )
            """
        section_filter = ""
        if section_types:
            quoted = ",".join("'" + str(s).replace("'", "''") + "'" for s in section_types)
            section_filter = f"AND dc.section_type IN ({quoted})"
        return f"""
            WITH ranked_chunks AS (
                SELECT dc.chunk_id, dc.document_id, dc.section_type,
                       dc.chunk_ordinal, dc.heading_path, dc.page_number,
                       dc.citation_text, dc.chunk_text, dc.published_at,
                       dc.effective_as_of, dc.source_url, dc.content_hash,
                       dc.embedding_model, dc.model_revision,
                       1 - (ce.embedding <=> '{vector}'::vector) AS score
                FROM {chunks} AS dc
                JOIN {embeddings} AS ce
                  ON ce.content_hash = dc.content_hash
                 AND ce.embedding_model = dc.embedding_model
                 AND ce.model_revision IS NOT DISTINCT FROM dc.model_revision
                WHERE ce.embedding_model = '{EMBEDDING_MODEL}'
                  AND ce.embedding_dim = {VECTOR_DIMENSION}
                  {product_filter}
                  {section_filter}
                ORDER BY ce.embedding <=> '{vector}'::vector
                LIMIT {top_k}
            )
            SELECT rc.*,
                   COALESCE(
                       ARRAY(
                           SELECT DISTINCT dp.product_id
                           FROM {products} AS dp
                           WHERE dp.document_id = rc.document_id
                           ORDER BY dp.product_id
                       ),
                       ARRAY[]::text[]
                   ) AS product_ids
            FROM ranked_chunks AS rc
            ORDER BY rc.score DESC, rc.chunk_id
        """

    def _direct_sql(
        self,
        product_ids: list[str] | None,
        section_types: list[str] | None = None,
    ) -> tuple[str, list[Any]]:
        chunks, embeddings, products = self._tables
        product_filter = ""
        params: list[Any] = [EMBEDDING_MODEL, VECTOR_DIMENSION]
        if product_ids:
            product_filter = f"""
              AND EXISTS (
                    SELECT 1
                    FROM {products} AS dp_filter
                    WHERE dp_filter.document_id = dc.document_id
                      AND dp_filter.product_id = ANY(%s)
              )
            """
            params.append(product_ids)
        section_filter = ""
        if section_types:
            section_filter = "AND dc.section_type = ANY(%s)"
            params.append(list(section_types))
        sql = f"""
            WITH ranked_chunks AS (
                SELECT dc.chunk_id, dc.document_id, dc.section_type,
                       dc.chunk_ordinal, dc.heading_path, dc.page_number,
                       dc.citation_text, dc.chunk_text, dc.published_at,
                       dc.effective_as_of, dc.source_url, dc.content_hash,
                       dc.embedding_model, dc.model_revision,
                       1 - (ce.embedding <=> %s::vector) AS score
                FROM {chunks} AS dc
                JOIN {embeddings} AS ce
                  ON ce.content_hash = dc.content_hash
                 AND ce.embedding_model = dc.embedding_model
                 AND ce.model_revision IS NOT DISTINCT FROM dc.model_revision
                WHERE ce.embedding_model = %s
                  AND ce.embedding_dim = %s
                  {product_filter}
                  {section_filter}
                ORDER BY ce.embedding <=> %s::vector
                LIMIT %s
            )
            SELECT rc.*,
                   COALESCE(
                       ARRAY(
                           SELECT DISTINCT dp.product_id
                           FROM {products} AS dp
                           WHERE dp.document_id = rc.document_id
                           ORDER BY dp.product_id
                       ),
                       ARRAY[]::text[]
                   ) AS product_ids
            FROM ranked_chunks AS rc
            ORDER BY rc.score DESC, rc.chunk_id
        """
        return sql, params

    def _search_direct(
        self,
        vector: str,
        top_k: int,
        product_ids: list[str] | None,
        section_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:
            raise RuntimeError("direct VectorDB access requires psycopg2-binary") from exc

        sql, filter_params = self._direct_sql(product_ids, section_types)
        with psycopg2.connect(os.getenv("DATABASE_URL") or self._dsn_from_env(), connect_timeout=int(self.timeout)) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, [vector, *filter_params, vector, top_k])
                return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _dsn_from_env() -> str:
        keys = ("host", "port", "user", "password", "dbname")
        values = {
            "host": os.getenv("PGHOST", "127.0.0.1"),
            "port": os.getenv("PGPORT", "5432"),
            "user": os.getenv("PGUSER", "agent_reader"),
            "password": os.getenv("PGPASSWORD", ""),
            "dbname": os.getenv("PGDATABASE", "postgres"),
        }
        return " ".join(f"{key}={values[key]}" for key in keys)

    def _search_api(
        self,
        vector: str,
        top_k: int,
        product_ids: list[str] | None,
        section_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        from agent import utils

        sql = self._api_sql(vector, top_k, product_ids, section_types)
        session = utils.get_pg_connection()
        try:
            return utils.run_sql(session, sql)
        finally:
            session.close()

    # -----------------------------------------------------------------
    # 스코프/커버리지/스키마 용어 조회 (검색 SQL과 같은 transport 선택)
    # -----------------------------------------------------------------
    def _run_read_sql(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """``%s`` 자리표시자 SQL 하나를 direct/API 어느 쪽으로든 실행한다."""
        params = list(params or [])
        if self._has_direct_dsn:
            try:
                import psycopg2
                from psycopg2.extras import RealDictCursor
            except ImportError as exc:
                raise RuntimeError("direct VectorDB access requires psycopg2-binary") from exc

            dsn = os.getenv("DATABASE_URL") or self._dsn_from_env()
            with psycopg2.connect(dsn, connect_timeout=int(self.timeout)) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(sql, params)
                    return [dict(row) for row in cursor.fetchall()]

        from agent import utils

        session = utils.get_pg_connection()
        try:
            return utils.run_sql(session, _inline(sql, params))
        finally:
            session.close()

    def resolve_product_ids(self, codes: list[str], names: list[str]) -> list[str]:
        """raw 상품코드/상품명을 ``enriched.product_master``의 product_id로 해소한다.

        RDB 결과 행에는 LLM이 고른 컬럼만 남아 코드가 없을 수 있으므로 이름으로도
        찾는다(두 조건은 OR). 둘 다 비면 질의하지 않는다."""
        codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
        names = [str(n).strip() for n in (names or []) if str(n).strip()]
        if not codes and not names:
            return []

        clauses: list[str] = []
        params: list[Any] = []
        if codes:
            clauses.append("source_key IN (" + ",".join(["%s"] * len(codes)) + ")")
            params.extend(codes)
        if names:
            clauses.append("name IN (" + ",".join(["%s"] * len(names)) + ")")
            params.extend(names)

        sql = (
            "SELECT DISTINCT product_id FROM enriched.product_master"
            f" WHERE {' OR '.join(clauses)} LIMIT 50"
        )
        return [str(row["product_id"]) for row in self._run_read_sql(sql, params)]

    def coverage(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        """상품별 문서 확보 상태. 테이블에 없는 상품은 키 자체가 빠진다(=미상)."""
        product_ids = [str(p).strip() for p in (product_ids or []) if str(p).strip()]
        if not product_ids:
            return {}
        sql = (
            "SELECT product_id, status, reason, document_id, source_route, as_of"
            f' FROM "{self.schema}"."product_coverage"'
            " WHERE product_id IN (" + ",".join(["%s"] * len(product_ids)) + ")"
        )
        return {str(row["product_id"]): dict(row) for row in self._run_read_sql(sql, product_ids)}

    def search_schema_terms(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """온톨로지 용어(``vec.schema_terms_all``)를 cosine similarity 상위로 반환한다."""
        vector = _vector_literal(query_vector)
        top_k = max(1, min(int(top_k), 20))
        sql = f"""
            SELECT term_uri, label, comment, property_type, domain_file,
                   1 - (embedding <=> %s::vector) AS score
            FROM "{self.schema}"."schema_terms_all"
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        return self._run_read_sql(sql, [vector, vector, top_k])
