"""Oxigraph transport ordering and failover tests."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from infrastructure.graph_db.client import (  # noqa: E402
    GraphDBUnavailable,
    GraphStoreUnavailable,
    OxigraphClient,
)


class FakeClient(OxigraphClient):
    def __init__(self, outcomes: dict[str, object], *, endpoint: str = "http://example/query") -> None:
        super().__init__(
            remote_store_path="remote-store",
            local_store_path="local-store",
            endpoint=endpoint,
            timeout=60,
        )
        self.outcomes = outcomes
        self.calls: list[str] = []

    def _query_store(self, path: Path, sparql: str, kind: str):
        name = "remote" if path.name == "remote-store" else "local"
        self.calls.append(name)
        outcome = self.outcomes[name]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _query_http(self, sparql: str, kind: str):
        self.calls.append("endpoint")
        outcome = self.outcomes.get("endpoint", [])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class OxigraphFailoverTest(unittest.TestCase):
    def test_remote_store_is_primary(self):
        client = FakeClient({"remote": [{"source": "remote"}], "local": [], "endpoint": []})
        self.assertEqual(client.query("SELECT * WHERE { ?s ?p ?o }"), [{"source": "remote"}])
        self.assertEqual(client.calls, ["remote"])

    def test_empty_remote_result_does_not_fail_over(self):
        client = FakeClient({"remote": [], "local": [{"source": "local"}], "endpoint": []})
        self.assertEqual(client.query("SELECT * WHERE { ?s ?p ?o }"), [])
        self.assertEqual(client.calls, ["remote"])

    def test_local_store_is_second(self):
        client = FakeClient(
            {
                "remote": GraphStoreUnavailable("mount unavailable"),
                "local": [{"source": "local"}],
                "endpoint": [],
            }
        )
        self.assertEqual(client.query("SELECT * WHERE { ?s ?p ?o }"), [{"source": "local"}])
        self.assertEqual(client.calls, ["remote", "local"])

    def test_endpoint_is_last(self):
        client = FakeClient(
            {
                "remote": GraphStoreUnavailable("mount unavailable"),
                "local": GraphStoreUnavailable("snapshot unavailable"),
                "endpoint": [{"source": "endpoint"}],
            }
        )
        self.assertEqual(client.query("SELECT * WHERE { ?s ?p ?o }"), [{"source": "endpoint"}])
        self.assertEqual(client.calls, ["remote", "local", "endpoint"])

    def test_invalid_query_does_not_touch_any_transport(self):
        client = FakeClient({"remote": [], "local": [], "endpoint": []})
        with self.assertRaises(ValueError):
            client.query("DELETE WHERE { ?s ?p ?o }")
        self.assertEqual(client.calls, [])

    def test_store_query_error_does_not_fail_over(self):
        client = FakeClient({"remote": SyntaxError("invalid SPARQL"), "local": [], "endpoint": []})
        with self.assertRaises(SyntaxError):
            client.query("SELECT * WHERE { ?s ?p ?o }")
        self.assertEqual(client.calls, ["remote"])

    def test_all_transports_unavailable(self):
        client = FakeClient(
            {
                "remote": GraphStoreUnavailable("mount unavailable"),
                "local": GraphStoreUnavailable("snapshot unavailable"),
                "endpoint": RuntimeError("HTTP 503"),
            }
        )
        with self.assertRaises(GraphDBUnavailable):
            client.query("ASK { ?s ?p ?o }")

    def test_default_timeout_is_60_seconds(self):
        with patch.dict(os.environ, {}, clear=True):
            client = OxigraphClient(local_store_path="local-store")
        self.assertEqual(client.timeout, 60.0)


if __name__ == "__main__":
    unittest.main()
