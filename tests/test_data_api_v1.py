# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import api  # noqa: E402
from deploy.data_api_v1 import verify_public_api  # noqa: E402
from kb.v2_manifest import RELEASE_ID  # noqa: E402
from tools.data_api import DataApiClientError, FinancialDataClient  # noqa: E402


class RawApiRouteContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(api.app)

    def test_only_raw_query_and_metadata_routes_remain(self):
        paths = set(api.app.openapi()["paths"])
        self.assertTrue(
            {
                "/health",
                "/db/sql",
                "/db/sparql",
                "/db/version",
                "/db/stats",
                "/db/tables",
                "/db/columns",
                "/db/catalog",
            }.issubset(paths)
        )
        self.assertFalse(any(path == "/v1" or path.startswith("/v1/") for path in paths))
        self.assertNotIn("/db", paths)
        self.assertNotIn("/db/coverage", paths)
        self.assertNotIn("/db/columns/{table_schema}/{table_name}", paths)

    def test_openapi_exposes_plain_text_body(self):
        paths = api.app.openapi()["paths"]
        for path in ("/db/sql", "/db/sparql"):
            content = paths[path]["post"]["requestBody"]["content"]
            self.assertEqual(set(content), {"text/plain"})
            self.assertEqual(content["text/plain"]["schema"]["type"], "string")

    def test_sql_accepts_exact_plain_text_statement(self):
        expected = {
            "columns": ["probe"],
            "rows": [{"probe": 1}],
            "row_count": 1,
            "truncated": False,
            "elapsed_ms": 0.1,
        }
        statement = "SELECT 1 AS probe"
        with patch.object(api, "run_sql", return_value=expected) as run_sql:
            response = self.client.post(
                "/db/sql",
                content=statement.encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        run_sql.assert_called_once_with(statement)

    def test_sparql_accepts_exact_plain_text_statement(self):
        expected = {
            "columns": ["triples"],
            "rows": [{"triples": "1628311"}],
            "row_count": 1,
            "truncated": False,
            "elapsed_ms": 0.1,
        }
        statement = "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }"
        with patch.object(api, "run_sparql", new=AsyncMock(return_value=expected)) as run_sparql:
            response = self.client.post(
                "/db/sparql",
                content=statement.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        run_sparql.assert_awaited_once_with(statement)

    def test_json_body_is_rejected(self):
        response = self.client.post("/db/sql", json={"sql": "SELECT 1"})
        self.assertEqual(response.status_code, 415)

    def test_non_utf8_empty_nul_and_long_bodies_are_rejected(self):
        invalid_utf8 = self.client.post(
            "/db/sql",
            content=b"\xff",
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        empty = self.client.post(
            "/db/sql",
            content=b" \r\n\t",
            headers={"Content-Type": "text/plain"},
        )
        nul = self.client.post(
            "/db/sql",
            content=b"SELECT\x00 1",
            headers={"Content-Type": "text/plain"},
        )
        long_query = self.client.post(
            "/db/sql",
            content=("x" * (api.MAX_QUERY_CHARS + 1)).encode(),
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(invalid_utf8.status_code, 400)
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(nul.status_code, 400)
        self.assertEqual(long_query.status_code, 413)

    def test_read_only_guards_remain(self):
        sql = self.client.post(
            "/db/sql",
            content=b"DELETE FROM enriched.product_master",
            headers={"Content-Type": "text/plain"},
        )
        sparql = self.client.post(
            "/db/sparql",
            content=b"INSERT DATA { <a> <b> <c> }",
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(sql.status_code, 400)
        self.assertEqual(sparql.status_code, 400)

    def test_generic_db_and_v1_are_not_found(self):
        generic = self.client.post(
            "/db",
            content=b"SELECT 1",
            headers={"Content-Type": "text/plain"},
        )
        v1 = self.client.get("/v1/release")
        self.assertEqual(generic.status_code, 404)
        self.assertEqual(v1.status_code, 404)

    def test_limits_and_union_graph_contract_are_fixed(self):
        self.assertEqual(api.STATEMENT_TIMEOUT_MS, 2000)
        self.assertEqual(api.GRAPH_QUERY_TIMEOUT_SECONDS, 10.0)
        self.assertEqual(api.MAX_ROWS, 100)
        self.assertEqual(api.MAX_BODY_BYTES, 1_048_576)
        self.assertEqual(api.EXPECTED_GRAPH_TRIPLES, 1_628_311)
        source = (ROOT / "src" / "api.py").read_text(encoding="utf-8")
        self.assertIn("SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }", source)
        self.assertNotIn("API_PUBLIC_CURATED_ONLY", source)

    def test_vm_verifier_retries_transient_container_start_reset(self):
        health = {"release_id": RELEASE_ID, "readiness": True}
        with (
            patch.object(
                verify_public_api,
                "request",
                side_effect=[ConnectionResetError("starting"), (200, health)],
            ) as request,
            patch.object(verify_public_api.time, "sleep") as sleep,
        ):
            result = verify_public_api.wait_for_health("http://127.0.0.1:8000")
        self.assertEqual(result, health)
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_deployment_enables_union_default_graph(self):
        compose = (
            ROOT / "deploy" / "data_api_v1" / "compose.graph-union-default.yaml"
        ).read_text(encoding="utf-8")
        deploy = (
            ROOT / "deploy" / "data_api_v1" / "deploy_public_test.sh"
        ).read_text(encoding="utf-8")
        verify = (
            ROOT / "deploy" / "data_api_v1" / "verify_public_api.py"
        ).read_text(encoding="utf-8")
        stage = (
            ROOT / "deploy" / "data_api_v1" / "stage_graph_union.sh"
        ).read_text(encoding="utf-8")
        install = (
            ROOT / "deploy" / "data_api_v1" / "install_vm_release.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--union-default-graph", compose)
        self.assertIn("sha256:e68b3625743db4a4b18129a907ae36766f89bb6d", compose)
        self.assertIn("compose.graph-union-default.yaml", deploy)
        self.assertIn("GRAPH_1628311_IS_ACTIVE", deploy)
        self.assertIn("REFUSE_ROLLBACK_IMAGE", deploy)
        self.assertIn("text/plain; charset=utf-8", verify)
        self.assertIn("WHERE { ?s ?p ?o }", verify)
        self.assertIn("1_628_311", verify)
        self.assertIn("EXPECTED_AUGMENT_UNION_TRIPLES=1628311", stage)
        self.assertIn("--union-default-graph", stage)
        self.assertIn("REFUSE_UNION_COUNT", stage)
        self.assertIn("INVESTMENT_REPORT_VECTOR_ACTIVE", install)
        self.assertIn('receipt["union_default_triples"] == 1_628_311', install)


class DataApiClientContractTest(unittest.TestCase):
    def test_client_pins_release_and_sends_raw_text(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/db/version":
                return httpx.Response(
                    200,
                    json={"rows": [{"release_id": RELEASE_ID}]},
                    request=request,
                )
            if request.url.path == "/db/sql":
                return httpx.Response(200, json={"rows": [{"probe": 1}]}, request=request)
            if request.url.path == "/db/sparql":
                return httpx.Response(
                    200,
                    json={"rows": [{"triples": "1628311"}]},
                    request=request,
                )
            raise AssertionError(request.url)

        raw_client = httpx.Client(
            base_url="https://data-api.test",
            transport=httpx.MockTransport(handler),
        )
        client = FinancialDataClient(
            "https://data-api.test",
            expected_release_id=RELEASE_ID,
            _client=raw_client,
        )
        self.assertEqual(client.sql("SELECT 1 AS probe")["rows"][0]["probe"], 1)
        self.assertEqual(
            client.sparql("SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }")[
                "rows"
            ][0]["triples"],
            "1628311",
        )
        self.assertEqual(sum(req.url.path == "/db/version" for req in requests), 1)
        sql_request = next(req for req in requests if req.url.path == "/db/sql")
        sparql_request = next(req for req in requests if req.url.path == "/db/sparql")
        self.assertEqual(sql_request.content.decode(), "SELECT 1 AS probe")
        self.assertEqual(
            sparql_request.content.decode(),
            "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }",
        )
        self.assertEqual(sql_request.headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(sparql_request.headers["content-type"], "text/plain; charset=utf-8")
        client.close()

    def test_client_surfaces_fastapi_detail(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(415, json={"detail": "text/plain required"}, request=request)

        client = FinancialDataClient(
            "https://data-api.test",
            _client=httpx.Client(
                base_url="https://data-api.test",
                transport=httpx.MockTransport(handler),
            ),
        )
        with self.assertRaises(DataApiClientError) as caught:
            client.sql("SELECT 1")
        self.assertEqual(caught.exception.status_code, 415)
        self.assertEqual(caught.exception.message, "text/plain required")
        client.close()


if __name__ == "__main__":
    unittest.main()
