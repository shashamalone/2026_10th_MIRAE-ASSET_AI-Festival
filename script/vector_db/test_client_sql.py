"""Normalized pgvector SQL generation tests.

python script\vector_db\test_client_sql.py

"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from infrastructure.vector_db.client import (  # noqa: E402
    VECTOR_DIMENSION,
    VectorDBClient,
    _inline,
    _vector_literal,
)


class VectorDBClientSqlTest(unittest.TestCase):
    def setUp(self):
        self.client = VectorDBClient(schema="vec")
        self.vector = _vector_literal([0.1] * VECTOR_DIMENSION)

    def test_rejects_wrong_vector_dimension(self):
        with self.assertRaises(ValueError):
            _vector_literal([0.1] * 10)

    def test_api_sql_joins_normalized_embedding_table(self):
        sql = self.client._api_sql(self.vector, 5, None)
        self.assertIn('JOIN "vec"."chunk_embedding" AS ce', sql)
        self.assertIn("ce.content_hash = dc.content_hash", sql)
        self.assertIn("ce.embedding_model = dc.embedding_model", sql)
        self.assertIn("ce.embedding_dim = 1024", sql)
        self.assertNotIn("dc.embedding <=>", sql)

    def test_api_sql_filters_products_without_duplicating_chunks(self):
        sql = self.client._api_sql(self.vector, 5, ["ETF:001", "O'Reilly"])
        self.assertIn('FROM "vec"."document_product" AS dp_filter', sql)
        self.assertIn("dp_filter.product_id IN ('ETF:001','O''Reilly')", sql)
        self.assertIn("EXISTS", sql)

    def test_direct_sql_keeps_values_parameterized(self):
        sql, params = self.client._direct_sql(["ETF:001"])
        self.assertIn("ce.embedding <=> %s::vector", sql)
        self.assertIn("dp_filter.product_id = ANY(%s)", sql)
        self.assertEqual(params, ["bge-m3", 1024, ["ETF:001"]])

    def test_api_sql_filters_section_types(self):
        sql = self.client._api_sql(self.vector, 5, None, ["risk", "objective_strategy"])
        self.assertIn("dc.section_type IN ('risk','objective_strategy')", sql)

    def test_direct_sql_appends_section_types_after_product_ids(self):
        # 자리표시자 순서 = 파라미터 순서다. 상품 필터 뒤에 와야 한다.
        sql, params = self.client._direct_sql(["ETF:001"], ["risk"])
        self.assertIn("dc.section_type = ANY(%s)", sql)
        self.assertEqual(params, ["bge-m3", 1024, ["ETF:001"], ["risk"]])
        self.assertLess(sql.index("dp_filter.product_id = ANY(%s)"),
                        sql.index("dc.section_type = ANY(%s)"))

    def test_no_section_filter_when_section_types_is_none(self):
        self.assertNotIn("section_type IN", self.client._api_sql(self.vector, 5, None, None))
        sql, params = self.client._direct_sql(None, None)
        self.assertNotIn("section_type = ANY", sql)
        self.assertEqual(params, ["bge-m3", 1024])


class InlineTest(unittest.TestCase):
    def test_inline_substitutes_in_order_and_escapes_quotes(self):
        sql = _inline("SELECT %s, %s, %s", ["O'Reilly", 7, "x"])
        self.assertEqual(sql, "SELECT 'O''Reilly', 7, 'x'")

    def test_inline_rejects_placeholder_count_mismatch(self):
        with self.assertRaises(ValueError):
            _inline("SELECT %s, %s", ["only-one"])


class ReadPathSqlTest(unittest.TestCase):
    """세 읽기 메서드는 실행 함수이므로 _run_read_sql을 가로채 SQL 텍스트를 본다."""

    def setUp(self):
        self.client = VectorDBClient(schema="vec")
        self.captured: list[tuple[str, list]] = []

        def capture(sql, params=None):
            self.captured.append((sql, list(params or [])))
            return []

        self.client._run_read_sql = capture

    def test_resolve_product_ids_queries_product_master_with_both_branches(self):
        self.client.resolve_product_ids(["KR7449690007"], ["O'Reilly ETF"])
        sql, params = self.captured[0]
        self.assertIn("FROM enriched.product_master", sql)
        self.assertIn("source_key IN (%s)", sql)
        self.assertIn("name IN (%s)", sql)
        self.assertIn("LIMIT 50", sql)
        self.assertEqual(params, ["KR7449690007", "O'Reilly ETF"])
        # API transport로 나가는 최종 문자열에서 작은따옴표가 이스케이프되는지.
        self.assertIn("name IN ('O''Reilly ETF')", _inline(sql, params))

    def test_resolve_product_ids_skips_query_when_scope_empty(self):
        self.assertEqual(self.client.resolve_product_ids([], []), [])
        self.assertEqual(self.captured, [])

    def test_resolve_product_ids_builds_only_needed_branch(self):
        self.client.resolve_product_ids([], ["이름만"])
        sql, params = self.captured[0]
        self.assertNotIn("source_key", sql)
        self.assertIn("name IN (%s)", sql)
        self.assertEqual(params, ["이름만"])

    def test_coverage_selects_status_columns(self):
        self.client.coverage(["etf_kr:KR7449690007", "fund:1"])
        sql, params = self.captured[0]
        self.assertIn("SELECT product_id, status, reason, document_id, source_route, as_of", sql)
        self.assertIn('FROM "vec"."product_coverage"', sql)
        self.assertIn("product_id IN (%s,%s)", sql)
        self.assertEqual(params, ["etf_kr:KR7449690007", "fund:1"])

    def test_coverage_skips_query_when_empty(self):
        self.assertEqual(self.client.coverage([]), {})
        self.assertEqual(self.captured, [])

    def test_search_schema_terms_orders_by_cosine_distance(self):
        self.client.search_schema_terms([0.1] * VECTOR_DIMENSION, top_k=3)
        sql, params = self.captured[0]
        self.assertIn('FROM "vec"."schema_terms_all"', sql)
        self.assertIn("term_uri, label, comment, property_type, domain_file", sql)
        self.assertIn("1 - (embedding <=> %s::vector) AS score", sql)
        self.assertIn("ORDER BY embedding <=> %s::vector", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertEqual(params[2], 3)


if __name__ == "__main__":
    unittest.main()
