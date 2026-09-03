"""PostgreSQL/pgvector read-only client.

The client prefers a direct PostgreSQL connection when ``DATABASE_URL`` or
the PG* variables are configured.  In team-test environments where the DB
port is private, it falls back to the existing guarded SQL API client.
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


class VectorDBClient:
    """Read-only semantic search over normalized ``vec`` tables."""

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
    ) -> list[dict[str, Any]]:
        """Return evidence chunks ordered by cosine similarity."""
        top_k = max(1, min(int(top_k), 20))
        vector = _vector_literal(query_vector)
        if self._has_direct_dsn:
            return self._search_direct(vector, top_k, product_ids)
        return self._search_api(vector, top_k, product_ids)

    @property
    def _tables(self) -> tuple[str, str, str]:
        return tuple(
            f'"{self.schema}"."{name}"'
            for name in (self.table, self.embedding_table, self.product_table)
        )

    def _api_sql(self, vector: str, top_k: int, product_ids: list[str] | None) -> str:
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

    def _direct_sql(self, product_ids: list[str] | None) -> tuple[str, list[Any]]:
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

    def _search_direct(self, vector: str, top_k: int, product_ids: list[str] | None) -> list[dict[str, Any]]:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:
            raise RuntimeError("direct VectorDB access requires psycopg2-binary") from exc

        sql, filter_params = self._direct_sql(product_ids)
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

    def _search_api(self, vector: str, top_k: int, product_ids: list[str] | None) -> list[dict[str, Any]]:
        from agent import utils

        sql = self._api_sql(vector, top_k, product_ids)
        session = utils.get_pg_connection()
        try:
            return utils.run_sql(session, sql)
        finally:
            session.close()
