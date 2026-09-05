"""Offline contracts for Graph transport selection and project triple counts."""
import os
import unittest
from unittest.mock import patch

from infrastructure.graph_db.client import GraphStoreUnavailable, OxigraphClient, REPO_ROOT


class GraphClientTransportTests(unittest.TestCase):
    def clean_environment(self):
        return patch.dict(os.environ, {
            key: value for key, value in os.environ.items()
            if not key.startswith("OXIGRAPH_")
        }, clear=True)

    def test_endpoint_only_configuration_skips_default_local_store(self):
        with self.clean_environment():
            client = OxigraphClient(endpoint="http://graph.invalid/query")
        self.assertIsNone(client.remote_store_path)
        # Keep the diagnostic path attribute backward-compatible, but do not
        # put it in the active transport chain.
        self.assertEqual(client.local_store_path, REPO_ROOT / "artifacts/oxigraph")
        self.assertFalse(client._local_store_enabled)

        with patch.object(client, "_query_store") as store_query, \
             patch.object(client, "_query_http", return_value=True) as http_query:
            self.assertTrue(client.query("ASK WHERE { ?s ?p ?o }"))
        store_query.assert_not_called()
        http_query.assert_called_once()

    def test_explicit_store_paths_keep_store_first_order(self):
        with self.clean_environment():
            client = OxigraphClient(
                remote_store_path="mounted/remote",
                local_store_path="mounted/local",
                endpoint="http://graph.invalid/query",
            )
        self.assertEqual(client.remote_store_path, REPO_ROOT / "mounted/remote")
        self.assertEqual(client.local_store_path, REPO_ROOT / "mounted/local")
        self.assertTrue(client._local_store_enabled)
        with patch.object(
            client,
            "_query_store",
            side_effect=[GraphStoreUnavailable("remote missing"), True],
        ) as store_query, patch.object(client, "_query_http") as http_query:
            self.assertTrue(client.query("ASK WHERE { ?s ?p ?o }"))
        self.assertEqual(
            [call.args[0] for call in store_query.call_args_list],
            [client.remote_store_path, client.local_store_path],
        )
        http_query.assert_not_called()

    def test_no_configuration_keeps_development_local_default(self):
        with self.clean_environment():
            client = OxigraphClient()
        self.assertEqual(client.local_store_path, REPO_ROOT / "artifacts/oxigraph")
        self.assertTrue(client._local_store_enabled)
        self.assertEqual(client.endpoint, "")

    def test_triple_count_counts_named_graphs_once(self):
        with self.clean_environment():
            client = OxigraphClient(endpoint="http://graph.invalid/query")
        with patch.object(client, "query", return_value=[{"count": "1169374"}]) as query:
            self.assertEqual(client.triple_count(), 1_169_374)
        sparql = query.call_args.args[0]
        self.assertIn("GRAPH ?g", sparql)
        self.assertNotIn("UNION", sparql.upper())


if __name__ == "__main__":
    unittest.main()
