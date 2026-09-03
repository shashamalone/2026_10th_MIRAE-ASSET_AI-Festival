"""PostgreSQL/pgvector read-only client.

The client prefers a direct PostgreSQL connection when ``DATABASE_URL`` or
the PG* variables are configured.  In team-test environments where the DB
port is private, it falls back to the existing guarded SQL API client.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

VECTOR_DIMENSION = 1024
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
    """Read-only semantic search over ``vec.document_chunk``."""

    def __init__(self, *, schema: str | None = None, table: str = "document_chunk") -> None:
        self.schema = _identifier(schema or os.getenv("VECTOR_SCHEMA", "vec"), "VECTOR_SCHEMA")
        self.table = _identifier(table, "table")
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

    def _sql(self, vector: str, top_k: int, product_ids: list[str] | None) -> tuple[str, tuple[Any, ...]]:
        table = f'"{self.schema}"."{self.table}"'
        where = ["embedding_model = 'bge-m3'", "embedding_dim = 1024"]
        params: list[Any] = []
        if product_ids:
            where.append("product_id = ANY(%s)")
            params.append(product_ids)
        sql = f"""
            SELECT chunk_id, document_id, product_id, page_number,
                   citation_text, chunk_text, published_at, source_url,
                   1 - (embedding <=> %s::vector) AS score
            FROM {table}
            WHERE {' AND '.join(where)}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        # The API transport accepts only SQL text; all values here are either
        # generated vectors, validated integers, or controlled IDs.
        api_sql = sql.replace("%s::vector", f"'{vector}'::vector")
        if product_ids:
            quoted = ",".join("'" + str(pid).replace("'", "''") + "'" for pid in product_ids)
            api_sql = api_sql.replace("product_id = ANY(%s)", f"product_id IN ({quoted})")
        return api_sql.replace("LIMIT %s", f"LIMIT {top_k}"), tuple([vector, vector, *params, top_k])

    def _search_direct(self, vector: str, top_k: int, product_ids: list[str] | None) -> list[dict[str, Any]]:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:
            raise RuntimeError("direct VectorDB access requires psycopg2-binary") from exc

        table = f'"{self.schema}"."{self.table}"'
        clauses = ["embedding_model = %s", "embedding_dim = %s"]
        params: list[Any] = ["bge-m3", VECTOR_DIMENSION]
        if product_ids:
            clauses.append("product_id = ANY(%s)")
            params.append(product_ids)
        sql = f"""
            SELECT chunk_id, document_id, product_id, page_number,
                   citation_text, chunk_text, published_at, source_url,
                   1 - (embedding <=> %s::vector) AS score
            FROM {table}
            WHERE {' AND '.join(clauses)}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with psycopg2.connect(os.getenv("DATABASE_URL") or self._dsn_from_env(), connect_timeout=int(self.timeout)) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, [vector, *params, vector, top_k])
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

        sql, _ = self._sql(vector, top_k, product_ids)
        session = utils.get_pg_connection()
        try:
            return utils.run_sql(session, sql)
        finally:
            session.close()

