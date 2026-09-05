"""Offline contracts for the selected remote-dev Graph/index integration."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from agent.graph_logic import graph_entity
from infrastructure.graph_db.client import MAX_ROWS, OxigraphClient


class _Variable:
    def __init__(self, value):
        self.value = value


class _Solutions:
    variables = [_Variable("entity")]

    def __iter__(self):
        for value in ("one", "two"):
            yield {"entity": _Variable(value)}


class RemoteGraphMergeTests(unittest.TestCase):
    def test_store_row_limit_and_explicit_unbounded_internal_read(self):
        client = OxigraphClient(local_store_path=Path("unused"))
        store = Mock()
        store.query.return_value = _Solutions()
        with patch.object(client, "_store", return_value=store):
            with self.assertRaisesRegex(ValueError, "상한 1행"):
                client._query_store(Path("unused"), "SELECT * WHERE {?s ?p ?o}", "SELECT", max_rows=1)
            self.assertEqual(client._query_store(Path("unused"), "SELECT * WHERE {?s ?p ?o}", "SELECT", max_rows=None),
                             [{"entity": "one"}, {"entity": "two"}])

    def test_default_public_graph_limit_is_unchanged(self):
        self.assertEqual(MAX_ROWS, 10_000)
        self.assertEqual(OxigraphClient.query.__kwdefaults__["max_rows"], MAX_ROWS)

    def test_index_hit_still_runs_original_query_scoped_by_values(self):
        uri = "http://mafest.ai/instance/etf-one"
        row = {"entity": uri, "name": "KODEX200", "label": None, "alt": None, "code": "069500"}
        with patch.object(graph_entity, "_entity_index", return_value={"ETF": {"kodex200": frozenset({uri})}}), \
             patch.object(graph_entity.graph_engine, "sparql", return_value=[row]) as sparql, \
             patch.object(graph_entity, "_INDEX_FAILURE", None):
            candidates = graph_entity._normalized_literal_candidates("KODEX 200", "ETF")
        self.assertEqual(candidates[0]["uri"], uri)
        self.assertIn(f"VALUES ?entity {{ <{uri}> }}", sparql.call_args.args[0])
        self.assertIn("FILTER(", sparql.call_args.args[0])

    def test_index_failure_uses_previous_sparql_scan(self):
        fixture = [{"uri": "fallback"}]
        with patch.object(graph_entity, "_entity_index", side_effect=RuntimeError("offline fixture")), \
             patch.object(graph_entity, "_normalized_literal_candidates_sparql", return_value=fixture) as fallback, \
             patch.object(graph_entity, "_INDEX_FAILURE", None):
            self.assertEqual(graph_entity._normalized_literal_candidates("상품", "ETF"), fixture)
        fallback.assert_called_once_with("상품", "ETF")

    def test_company_master_was_moved_to_the_path_runtime_reads(self):
        expected = graph_entity.ROOT / "data/enriched/company_master.csv"
        self.assertTrue(expected.is_file())
        self.assertFalse((graph_entity.ROOT / "src/data/enriched/company_master.csv").exists())


if __name__ == "__main__":
    unittest.main()
