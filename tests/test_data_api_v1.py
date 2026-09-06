# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import api  # noqa: E402
import serve_answer  # noqa: E402


def active_vector_row() -> dict:
    base = dict(api.VECTOR_BASE_COUNTS)
    return {
        "run_id": "t108-7902db9a58d66b7f",
        "release_id": api.RELEASE_ID,
        "model_id": api.VECTOR_MODEL_ID,
        "model_revision": "b28ce2a6fcc9c75ef1c0619575d0ec19af760082",
        "embedding_dim": api.VECTOR_DIMENSION,
        "status": "active",
        "expected_counts": {
            filename: base[table]
            for table, filename in api.VECTOR_COUNT_KEYS.items()
        },
        "observed_counts": base,
        "table_counts": dict(api.VECTOR_LIVE_COUNTS),
        "hnsw_indexes": api.VECTOR_HNSW_INDEXES,
        "search_functions": api.VECTOR_SEARCH_FUNCTIONS,
    }


class ApiContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(api.app)

    def test_exact_route_surface_includes_answer(self):
        self.assertEqual(
            set(api.app.openapi()["paths"]),
            {
                "/health", "/answer", "/db/sql", "/db/sparql",
                "/db/version", "/db/stats", "/db/tables", "/db/columns",
                "/db/catalog",
            },
        )

    def test_answer_is_exact_five_string_field_utf8_contract(self):
        with patch.object(
            serve_answer,
            "answer",
            return_value=serve_answer._envelope("Q-test", "질문", answer="답변"),
        ):
            response = self.client.get(
                "/answer", params={"question_id": "Q-test", "question": "질문", "extra": "ignored"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json; charset=utf-8")
        payload = response.json()
        self.assertEqual(
            set(payload),
            {"question_id", "question", "retrieved_context", "think_trace", "answer"},
        )
        self.assertTrue(all(isinstance(value, str) for value in payload.values()))

    def test_sql_and_sparql_keep_read_only_plain_text_contract(self):
        sql_payload = {"rows": [{"probe": 1}]}
        with patch.object(api, "run_sql", return_value=sql_payload):
            sql = self.client.post(
                "/db/sql", content=b"SELECT 1", headers={"Content-Type": "text/plain; charset=utf-8"}
            )
        self.assertEqual(sql.status_code, 200)
        self.assertEqual(sql.json(), sql_payload)

        sparql_payload = {"rows": [{"triples": str(api.EXPECTED_GRAPH_TRIPLES)}]}
        with patch.object(api, "run_sparql", new=AsyncMock(return_value=sparql_payload)):
            sparql = self.client.post(
                "/db/sparql",
                content=b"SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }",
                headers={"Content-Type": "text/plain"},
            )
        self.assertEqual(sparql.status_code, 200)
        self.assertEqual(sparql.json(), sparql_payload)
        self.assertEqual(
            self.client.post(
                "/db/sql",
                content=b"DELETE FROM raw.etf_kr_master",
                headers={"Content-Type": "text/plain"},
            ).status_code,
            400,
        )

    def test_limits_and_graph_release_are_current(self):
        self.assertEqual(api.STATEMENT_TIMEOUT_MS, 2_000)
        self.assertEqual(api.GRAPH_QUERY_TIMEOUT_SECONDS, 10.0)
        self.assertEqual(api.MAX_ROWS, 100)
        self.assertEqual(api.EXPECTED_GRAPH_TRIPLES, 1_226_698)
        self.assertEqual(api.APP_VERSION, "4.3.0")


class VectorAndHealthContractTest(unittest.TestCase):
    def test_vector_accepts_base_release_plus_exact_sec_supplement(self):
        with patch.object(api, "run_sql", return_value={"rows": [active_vector_row()]}):
            vector = api.vector_health()
        self.assertTrue(vector["ready"])
        self.assertEqual(vector["base_counts"], api.VECTOR_BASE_COUNTS)
        self.assertEqual(vector["supplemental_counts"], api.VECTOR_SUPPLEMENTAL_COUNTS)
        self.assertEqual(vector["table_counts"], api.VECTOR_LIVE_COUNTS)

    def test_vector_rejects_live_or_base_drift(self):
        live_drift = active_vector_row()
        live_drift["table_counts"] = deepcopy(live_drift["table_counts"])
        live_drift["table_counts"]["document_chunk"] -= 1
        base_drift = active_vector_row()
        base_drift["observed_counts"] = deepcopy(base_drift["observed_counts"])
        base_drift["observed_counts"]["document_chunk"] -= 1
        for row in (live_drift, base_drift):
            with self.subTest(row=row), patch.object(api, "run_sql", return_value={"rows": [row]}):
                self.assertFalse(api.vector_health()["ready"])

    def test_health_requires_rdb_graph_vector_clova_and_pipeline(self):
        vector = active_vector_row()

        def sql_result(statement, _params=None):
            if "FROM meta.dataset_snapshot" in statement:
                return {"rows": [{
                    "dataset_version": "financial-products-2026-08-24",
                    "source_hash": api.EXPECTED_SNAPSHOT_HASH,
                    "run_status": "passed",
                    "run_phase": "cutover_ready",
                }]}
            if "FROM raw.bond_kr_master" in statement:
                return {"rows": []}
            if "FROM vec.vector_deploy_run" in statement:
                return {"rows": [vector]}
            raise AssertionError(statement)

        graph = [
            {"rows": [{"triples": str(api.EXPECTED_GRAPH_TRIPLES)}]},
            {"rows": [{"g": "http://mafest.ai/graph/tbox/common"}]},
        ]
        with (
            patch.dict("os.environ", {"CLOVA_API_KEY": "configured"}),
            patch.object(serve_answer, "_APP", object()),
            patch.object(api, "run_sql", side_effect=sql_result),
            patch.object(api, "run_sparql", new=AsyncMock(side_effect=graph)),
        ):
            payload = TestClient(api.app).get("/health").json()
        self.assertTrue(payload["readiness"])
        self.assertTrue(payload["answer_pipeline_loaded"])
        self.assertTrue(payload["clova_configured"])


class DeploymentSourceContractTest(unittest.TestCase):
    def test_api_only_cutover_never_recreates_datastores(self):
        local = (ROOT / "deploy/data_api_v1/deploy_api_only.ps1").read_text(encoding="utf-8")
        remote = (ROOT / "deploy/data_api_v1/install_api_only_release.sh").read_text(encoding="utf-8")
        self.assertIn('compose_release "${release_dir}" up -d --no-deps api', remote)
        self.assertNotIn("up -d --no-deps db", remote)
        self.assertNotIn("up -d --no-deps graph", remote)
        self.assertIn('test "$(compose_release "${release_dir}" ps -q db)" = "${old_db_container}"', remote)
        self.assertIn('test "$(compose_release "${release_dir}" ps -q graph)" = "${old_graph_container}"', remote)
        self.assertLess(local.index("--preflight"), local.index("& scp"))
        self.assertIn("$installerUpload", local)
        self.assertIn('.Replace("`r`n", "`n")', local)


if __name__ == "__main__":
    unittest.main()
