# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VERIFIER_PATH = ROOT / "deploy" / "data_api_v1" / "verify_public_api.py"
SPEC = importlib.util.spec_from_file_location("verify_public_api_t132", VERIFIER_PATH)
assert SPEC and SPEC.loader
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def preflight_responses() -> list[tuple[int, dict]]:
    table_counts = {
        name.removeprefix("vec."): count
        for name, count in VERIFIER.EXPECTED_VECTOR_COUNTS.items()
    }
    base_counts = {
        name.removeprefix("vec."): count
        for name, count in VERIFIER.EXPECTED_VECTOR_BASE_COUNTS.items()
    }
    metadata = {
        "run_id": VERIFIER.EXPECTED_VECTOR_RUN,
        "release_id": VERIFIER.EXPECTED_RELEASE,
        "model_id": VERIFIER.EXPECTED_VECTOR_MODEL,
        "model_revision": "b28ce2a6fcc9c75ef1c0619575d0ec19af760082",
        "embedding_dim": VERIFIER.EXPECTED_VECTOR_DIMENSION,
        "status": "active",
        "expected_counts": {
            filename: base_counts[table]
            for table, filename in VERIFIER.VECTOR_COUNT_KEYS.items()
        },
        "observed_counts": base_counts,
    }
    health = {
        "api_version": "4.0.0",
        "release_id": VERIFIER.EXPECTED_RELEASE,
        "readiness": True,
        "rdb": {"release_id": VERIFIER.EXPECTED_RELEASE},
        "graph": {
            "release_id": VERIFIER.EXPECTED_RELEASE,
            "triples": 1_226_698,
        },
    }
    return [
        (200, health),
        (200, {"rows": [{"release_id": VERIFIER.EXPECTED_RELEASE}]}),
        (200, {"rows": [metadata]}),
        (
            200,
            {
                "rows": [
                    {"table_name": table, "row_count": count}
                    for table, count in table_counts.items()
                ]
            },
        ),
        (
            200,
            {
                "rows": [
                    {
                        "hnsw_indexes": VERIFIER.EXPECTED_VECTOR_HNSW_INDEXES,
                        "search_functions": VERIFIER.EXPECTED_VECTOR_SEARCH_FUNCTIONS,
                    }
                ]
            },
        ),
        (200, {"rows": [{"triples": "1226698"}]}),
        (
            200,
            {
                "rows": [
                    {"g": name, "triples": count}
                    for name, count in VERIFIER.EXPECTED_NAMED_GRAPHS.items()
                ]
            },
        ),
        (200, {"row_count": 1, "rows": [{"score": 1.0}]}),
        (200, {"row_count": 1, "rows": [{"score": 1.0}]}),
    ]


class ApiOnlyDeploySourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.local = (
            ROOT / "deploy" / "data_api_v1" / "deploy_api_only.ps1"
        ).read_text(encoding="utf-8")
        cls.remote = (
            ROOT / "deploy" / "data_api_v1" / "install_api_only_release.sh"
        ).read_text(encoding="utf-8")
        cls.verifier = VERIFIER_PATH.read_text(encoding="utf-8")

    def test_default_mode_stops_after_read_only_preflight(self):
        self.assertIn("[switch]$Execute", self.local)
        self.assertLess(self.local.index("--preflight"), self.local.index("if (-not $Execute)"))
        self.assertLess(self.local.index("if (-not $Execute)"), self.local.index("& scp"))
        self.assertIn("artifacts\\runs\\$runId\\codex-t154-answer-deploy-0906", self.local)
        self.assertIn("$expectedGraphTriples = 1226698", self.local)
        self.assertIn("$installerUpload", self.local)
        self.assertIn('.Replace("`r`n", "`n")', self.local)
        self.assertIn("[Text.UTF8Encoding]::new($false)", self.local)

    def test_forward_and_rollback_touch_only_api(self):
        self.assertIn('compose_release "${release_dir}" up -d --no-deps api', self.remote)
        self.assertIn(
            'compose_release "${current_release}" up -d --no-deps --no-build api',
            self.remote,
        )
        self.assertNotIn("up -d --no-deps db", self.remote)
        self.assertNotIn("up -d --no-deps graph", self.remote)
        self.assertIn('test "$(compose_release "${release_dir}" ps -q db)" = "${old_db_container}"', self.remote)
        self.assertIn('test "$(compose_release "${release_dir}" ps -q graph)" = "${old_graph_container}"', self.remote)

    def test_rollback_uses_previous_release_and_pointer_is_atomic(self):
        self.assertIn('current_release=$(realpath -e -- "${pointer_value}")', self.remote)
        self.assertIn('compose_release "${current_release}" config', self.remote)
        self.assertIn("restoring previous release", self.remote)
        self.assertIn('docker image tag "${old_api_image}" "${api_image}"', self.remote)
        verifier_call = 'python3 "${release_dir}/deploy/data_api_v1/verify_public_api.py"'
        pointer_update = 'pointer_tmp=$(mktemp "${pointer}.tmp.XXXXXX")'
        self.assertLess(self.remote.index(verifier_call), self.remote.index(pointer_update))
        self.assertIn('mv -f -- "${pointer_tmp}" "${pointer}"', self.remote)

    def test_verifier_is_exact_and_has_no_write_probe(self):
        self.assertEqual(VERIFIER.EXPECTED_API_VERSION, "4.3.0")
        self.assertEqual(VERIFIER.EXPECTED_VECTOR_RUN, "t108-7902db9a58d66b7f")
        self.assertEqual(len(VERIFIER.EXPECTED_VECTOR_COUNTS), 7)
        self.assertEqual(len(VERIFIER.EXPECTED_ROUTES), 9)
        self.assertIn("/answer", VERIFIER.EXPECTED_ROUTES)
        self.assertIn('parser.add_argument("--expected-graph-triples", type=int, required=True)', self.verifier)
        for mutation in ("DELETE FROM", "INSERT INTO", "UPDATE ", "ALTER ", "DROP "):
            self.assertNotIn(mutation, self.local + self.remote + self.verifier)
        for statement in (
            VERIFIER.vector_metadata_query(),
            VERIFIER.vector_counts_query(),
            VERIFIER.vector_runtime_query(),
            VERIFIER.SCHEMA_SELF_SEARCH,
            VERIFIER.DOCUMENT_SELF_SEARCH,
        ):
            self.assertTrue(statement.lstrip().upper().startswith(("SELECT", "WITH")))


class ReadOnlyPreflightTest(unittest.TestCase):
    def test_allowlisted_receipt_is_written_without_sensitive_fields(self):
        responses = preflight_responses()
        with patch.object(VERIFIER, "request", side_effect=responses) as request:
            receipt = VERIFIER.collect_preflight("https://data-api.test", 1_226_698)
        self.assertEqual(request.call_count, len(responses))
        self.assertEqual(
            set(receipt),
            {
                "generated_at",
                "mode",
                "contract_pass",
                "deployment_executed",
                "api",
                "rdb",
                "graph",
                "vector",
            },
        )
        self.assertEqual(
            set(receipt["api"]),
            {"version", "release_id", "readiness"},
        )
        self.assertTrue(receipt["contract_pass"])
        self.assertFalse(receipt["deployment_executed"])
        self.assertEqual(receipt["api"]["version"], "4.0.0")
        self.assertEqual(receipt["graph"]["triples"], 1_226_698)
        self.assertEqual(receipt["vector"]["live_counts"], VERIFIER.EXPECTED_VECTOR_COUNTS)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            VERIFIER.write_preflight(receipt, output)
            json_text = (output / "api_only_preflight.json").read_text(encoding="utf-8")
            markdown = (output / "api_only_preflight.md").read_text(encoding="utf-8")
        payload = json.loads(json_text)
        self.assertTrue(payload["contract_pass"])
        combined = (json_text + markdown).lower()
        for sensitive in (
            "clova_api_key",
            "clova_studio_api_key",
            "database_url",
            "authorization:",
            "password=",
        ):
            self.assertNotIn(sensitive, combined)
        self.assertIn("Deployment executed: **NO**", markdown)

    def test_preflight_rejects_live_count_drift(self):
        responses = preflight_responses()
        responses[3][1]["rows"][0]["row_count"] -= 1
        with patch.object(VERIFIER, "request", side_effect=responses), self.assertRaises(SystemExit):
            VERIFIER.collect_preflight("https://data-api.test", 1_226_698)


if __name__ == "__main__":
    unittest.main()
