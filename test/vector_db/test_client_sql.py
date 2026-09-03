"""Normalized pgvector SQL generation tests.

python -m unittest test/vector_db/test_client_sql.py

"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from infrastructure.vector_db.client import (  # noqa: E402
    VECTOR_DIMENSION,
    VectorDBClient,
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


if __name__ == "__main__":
    unittest.main()
