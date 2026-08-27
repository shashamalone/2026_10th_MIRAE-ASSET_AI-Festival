# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import api  # noqa: E402
from data_api.contracts import (  # noqa: E402
    EvidenceSearchRequest,
    OntologyValidateRequest,
    ProductQueryRequest,
    ProductSearchRequest,
    RelationTraverseRequest,
)
from data_api.service import (  # noqa: E402
    QUESTION_CAPABILITY_MAP,
    DataApiError,
    product_query_statement,
    product_search_statement,
    relation_statement,
    validate_ontology_request,
)
from kb.build_demo_vectors_v2 import validate_manifest, vector_literal  # noqa: E402
from kb.v2_manifest import RELEASE_ID  # noqa: E402
from tools.data_api import DataApiClientError, FinancialDataClient  # noqa: E402


class CuratedQueryContractTest(unittest.TestCase):
    def test_product_search_keeps_user_text_in_parameters(self):
        request = ProductSearchRequest(name="KODEX 200' OR true --", match="contains")
        statement, params = product_search_statement(request)
        self.assertNotIn(request.name, statement)
        self.assertEqual(params["name"], request.name)
        self.assertIn("LIMIT %(limit)s", statement)

    def test_aum_query_requires_explicit_currency(self):
        with self.assertRaises(ValidationError):
            ProductQueryRequest(sort_by="AUM")
        request = ProductQueryRequest(sort_by="AUM", currency="krw", limit=5)
        statement, params = product_query_statement(request)
        self.assertEqual(params["currency"], "KRW")
        self.assertIn("m.is_available", statement)
        self.assertNotIn("buyable_quantity", statement.lower())

    def test_boolean_filter_only_allows_eq(self):
        request = ProductQueryRequest(
            product_types=["BOND"],
            filters=[{"field": "ASSUMED_PURCHASABLE", "op": "gt", "value": True}],
        )
        with self.assertRaises(DataApiError) as caught:
            product_query_statement(request)
        self.assertEqual(caught.exception.code, "INVALID_FILTER_OPERATOR")

    def test_relation_paths_are_allowlisted(self):
        allowed = RelationTraverseRequest(
            start_entity_id="dart:00536541",
            path=["parent_of", "held_by_product"],
        )
        statement, params = relation_statement(allowed) or (None, None)
        self.assertIn("company_subsidiary", statement)
        self.assertEqual(params["start"], "dart:00536541")
        rejected = RelationTraverseRequest(
            start_entity_id="dart:00536541",
            path=["held_by_product", "parent_of"],
        )
        with self.assertRaises(DataApiError) as caught:
            relation_statement(rejected)
        self.assertEqual(caught.exception.code, "UNSUPPORTED_RELATION_PATH")

    def test_ontology_abstain_codes_are_deterministic(self):
        rating = validate_ontology_request(
            OntologyValidateRequest(validation_type="credit_rating", value="AAAA")
        )
        self.assertFalse(rating["valid"])
        self.assertEqual(rating["code"], "ABSTAIN_INVALID_TAXONOMY")
        domain = validate_ontology_request(
            OntologyValidateRequest(
                validation_type="relation_domain",
                relation="issued_bond",
                subject_product_id="etf_gl:VOO",
            ),
            product_type="ETF_GL",
        )
        self.assertEqual(domain["code"], "ABSTAIN_DOMAIN_MISMATCH")

    def test_capability_map_has_exactly_35_questions(self):
        self.assertEqual(sorted(QUESTION_CAPABILITY_MAP), list(range(1, 36)))
        self.assertEqual(QUESTION_CAPABILITY_MAP[31]["status"], "ready")
        self.assertEqual(QUESTION_CAPABILITY_MAP[29]["status"], "gap")


class DemoVectorContractTest(unittest.TestCase):
    def make_manifest(self, root: Path) -> Path:
        records = []
        definitions = [
            (
                "official_policy",
                "https://www.fsc.go.kr/no010101/00000",
                "정책자료 원문",
                "국민성장펀드의 구조와 운용 원칙",
            ),
            (
                "official_risk",
                "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=TEST",
                "위험자료 원문",
                "투자자는 시장가격 변동에 따른 손실 위험을 부담합니다",
            ),
        ]
        for index, (source_type, url, source_text, chunk_text) in enumerate(definitions, 1):
            source = root / f"source-{index}.txt"
            source.write_text(source_text, encoding="utf-8")
            extracted = root / f"source-{index}-extracted.txt"
            extracted.write_text(f"앞 문단\n{chunk_text}\n뒤 문단", encoding="utf-8")
            records.append(
                {
                    "source_type": source_type,
                    "title": f"공식 문서 {index}",
                    "publisher": "공식 기관",
                    "published_at": "2026-08-20",
                    "source_url": url,
                    "source_file": source.name,
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "extracted_text_file": extracted.name,
                    "extracted_text_sha256": hashlib.sha256(extracted.read_bytes()).hexdigest(),
                    "product_id": None if index == 1 else "etf_kr:TEST",
                    "page_number": index,
                    "locator": f"p.{index}",
                    "citation_text": chunk_text.split()[0],
                    "chunk_text": chunk_text,
                    "chunk_sha256": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                }
            )
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps({"schema_version": 1, "release_id": RELEASE_ID, "documents": records}, ensure_ascii=False),
            encoding="utf-8",
        )
        return manifest

    def test_manifest_requires_exact_policy_and_risk_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            records = validate_manifest(self.make_manifest(Path(directory)))
        self.assertEqual(len(records), 2)
        self.assertEqual({record["source_type"] for record in records}, {"official_policy", "official_risk"})
        self.assertTrue(all(record["document_id"].startswith("doc:demo:") for record in records))

    def test_manifest_rejects_cutoff_violation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_manifest(Path(directory))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["documents"][0]["published_at"] = "2026-08-25"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_manifest(path)

    def test_vector_contract_is_exactly_1024_and_nonzero(self):
        self.assertTrue(vector_literal([0.1] * 1024).startswith("["))
        with self.assertRaises(ValueError):
            vector_literal([0.1] * 2)
        with self.assertRaises(ValueError):
            vector_literal([0.0] * 1024)
        with self.assertRaises(ValidationError):
            EvidenceSearchRequest(query_embedding=[0.1] * 2)


class ApiRouteContractTest(unittest.TestCase):
    def test_search_route_has_release_evidence_and_coverage(self):
        fake = {
            "rows": [
                {
                    "product_id": "etf_kr:TEST",
                    "product_type": "ETF_KR",
                    "market_scope": "KR",
                    "name": "KODEX 200",
                    "short_name": "KODEX 200",
                    "currency": "KRW",
                    "is_active": True,
                    "effective_as_of": "2026-08-21",
                    "source_table": "PREF01N001",
                    "source_key": "TEST",
                    "holdings_status": "available",
                    "holdings_reason": "근거 확보",
                    "document_status": "available",
                    "document_reason": "근거 확보",
                    "performance_status": "available",
                    "performance_reason": "근거 확보",
                    "match_type": "exact",
                }
            ],
            "truncated": False,
        }
        with patch.object(api, "run_sql", return_value=fake):
            result = api.v1_product_search(ProductSearchRequest(name="KODEX 200"))
        self.assertEqual(result["release_id"], RELEASE_ID)
        self.assertEqual(result["coverage"]["status"], "available")
        self.assertEqual(result["evidence"][0]["source"], "PREF01N001")

    def test_source_contains_all_curated_routes_and_public_guard(self):
        source = (ROOT / "src" / "api.py").read_text(encoding="utf-8")
        for route in (
            "/v1/release",
            "/v1/capabilities",
            "/v1/products/search",
            "/v1/products/query",
            "/v1/products/compare",
            "/v1/products/{product_id}/holdings",
            "/v1/relations/traverse",
            "/v1/ontology/validate",
            "/v1/evidence/semantic-search",
        ):
            self.assertIn(route, source)
        self.assertIn("API_PUBLIC_CURATED_ONLY", source)
        self.assertIn("PUBLIC_TEST_EXPIRES_AT", source)
        self.assertEqual(api.STATEMENT_TIMEOUT_MS, 2000)
        self.assertEqual(api.GRAPH_QUERY_TIMEOUT_SECONDS, 10.0)
        self.assertIn("ORDER BY p.product_id LIMIT %(fetch_limit)s", source)
        paths = set(api.app.openapi()["paths"])
        self.assertTrue(
            {
                "/v1/release",
                "/v1/capabilities",
                "/v1/products/search",
                "/v1/products/query",
                "/v1/products/{product_id}",
                "/v1/products/{product_id}/holdings",
                "/v1/relations/traverse",
                "/v1/ontology/validate",
                "/v1/evidence/semantic-search",
            }.issubset(paths)
        )

    def test_validation_errors_use_machine_readable_problem(self):
        response = TestClient(api.app).post(
            "/v1/evidence/semantic-search",
            json={"query_embedding": [0.1, 0.2], "top_k": 2},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_REQUEST")

    def test_legacy_coverage_query_is_index_ordered_and_capped(self):
        with patch.object(api, "run_sql", return_value={"rows": []}) as run_sql:
            api.db_coverage()
        statement, params = run_sql.call_args.args
        self.assertIn("ORDER BY p.product_id LIMIT %(fetch_limit)s", statement)
        self.assertEqual(params["fetch_limit"], api.MAX_ROWS + 1)

    def test_deployment_profile_separates_public_and_debug_routes(self):
        overlay = (ROOT / "deploy" / "data_api_v1" / "compose.public-test.yaml").read_text(encoding="utf-8")
        team_overlay = (ROOT / "deploy" / "data_api_v1" / "compose.team-db-test.yaml").read_text(encoding="utf-8")
        deploy = (ROOT / "deploy" / "data_api_v1" / "deploy_public_test.sh").read_text(encoding="utf-8")
        install = (ROOT / "deploy" / "data_api_v1" / "install_vm_release.sh").read_text(encoding="utf-8")
        verify = (ROOT / "deploy" / "data_api_v1" / "verify_public_api.py").read_text(encoding="utf-8")
        windows = (ROOT / "deploy" / "data_api_v1" / "deploy_vm.ps1").read_text(encoding="utf-8")
        full_windows = (ROOT / "deploy" / "data_api_v1" / "deploy_vm_full.ps1").read_text(encoding="utf-8")
        retry = (ROOT / "deploy" / "data_api_v1" / "prepare_t105_retry.sh").read_text(encoding="utf-8")
        retry_windows = (ROOT / "deploy" / "data_api_v1" / "prepare_t105_retry.ps1").read_text(encoding="utf-8")
        restore_old = (ROOT / "deploy" / "data_api_v1" / "restore_old_api_now.ps1").read_text(encoding="utf-8")
        diagnose = (ROOT / "deploy" / "data_api_v1" / "diagnose_t105_failure.ps1").read_text(encoding="utf-8")
        resume = (ROOT / "deploy" / "data_api_v1" / "resume_t105_partial.sh").read_text(encoding="utf-8")
        resume_windows = (ROOT / "deploy" / "data_api_v1" / "resume_t105_partial.ps1").read_text(encoding="utf-8")
        seed = (ROOT / "deploy" / "data_api_v1" / "seed_demo_vectors.sh").read_text(encoding="utf-8")
        self.assertIn('API_PUBLIC_CURATED_ONLY: "1"', overlay)
        self.assertIn('API_PUBLIC_CURATED_ONLY: "0"', team_overlay)
        self.assertIn("127.0.0.1:${API_DEBUG_PORT:-8001}:8000", overlay)
        self.assertIn("V2_CUTOVER_CONFIRMED", deploy)
        self.assertIn("PUBLIC_TEST_EXPIRES_AT", deploy)
        self.assertIn("deploy/compose.graph-pointer.yaml", deploy)
        self.assertIn('up -d --no-deps "${services[@]}"', deploy)
        self.assertIn("python3 deploy/data_api_v1/verify_public_api.py", deploy)
        self.assertIn("I_ACCEPT_TEMPORARY_GUARDED_READ_ONLY_DB", deploy)
        self.assertIn("TEAM_DB_PUBLIC_MODE", deploy)
        self.assertIn("financial-agent-prep_oxigraph-next-2026-08-24-57c4edc", install)
        self.assertIn("relations.product_holding", install)
        self.assertIn("relations.company_subsidiary", install)
        self.assertIn("raw_status=", install)
        self.assertIn("access_mode", install)
        self.assertIn("public test exposure cannot exceed 7 days", install)
        self.assertIn("KeepPublicReadOnlyDbForTeamTest", windows)
        self.assertIn("KeepPublicReadOnlyDbForTeamTest", full_windows)
        self.assertIn('"sql": "DELETE FROM enriched.product_master"', verify)
        self.assertIn('"sparql": "INSERT DATA { <a> <b> <c> }"', verify)
        self.assertIn("TEAM DB API PASS", verify)
        self.assertIn("Get-FileHash", windows)
        self.assertIn("Refuse dirty tracked worktree", windows)
        self.assertIn("AcceptExistingPublicReadOnlyDbRisk", full_windows)
        self.assertIn("SELECT 1 AS probe", full_windows)
        self.assertIn("guarded-readonly", full_windows)
        self.assertIn("t105-default-graph-fix", full_windows)
        self.assertIn("UNION { GRAPH ?g", full_windows)
        self.assertIn("data_api_rollback.sh", full_windows)
        self.assertNotIn("docker commit --pause=true", full_windows)
        self.assertIn("old-api-image.tar", full_windows)
        self.assertIn("OLD_API_IMAGE_RELOAD", full_windows)
        self.assertIn("OLD_ABSENT_SCHEMAS", full_windows)
        self.assertIn("DROP SCHEMA %I RESTRICT", full_windows)
        self.assertIn("GRAPH_BIND=127.0.0.1", full_windows)
        self.assertIn("dbapi-c007-g10cov", full_windows)
        self.assertIn("timeout=10.0", full_windows)
        self.assertIn("LIMIT 101", full_windows)
        self.assertIn("/artifacts/runtime", full_windows)
        self.assertIn('chown -R "$TARGET_UID:$TARGET_GID"', full_windows)
        self.assertIn('2>&1 </dev/null 9>&- &', full_windows)
        self.assertIn('exec 9>&- 2>/dev/null || true', full_windows)
        self.assertIn("prepare_t105_retry.ps1", full_windows)
        self.assertIn("bash deploy/backup_v2.sh", retry)
        self.assertIn("scratch-schema-roundtrip", retry)
        self.assertIn("SCRATCH_VERIFY_HTTP", retry)
        self.assertIn("optimize -l /data", retry)
        self.assertIn("health_queries_under_2s=passed", retry)
        self.assertIn("dbapi-c007-g10cov", retry)
        self.assertIn("secure_backup_files", retry)
        self.assertIn('chown "$TARGET_UID:$TARGET_GID" "$path"', retry)
        self.assertIn("T105 RETRY READY PASS", retry)
        self.assertIn("'3|0|0|6'", retry)
        self.assertIn("drop_retry_placeholders", retry)
        self.assertIn("Get-FileHash", retry_windows)
        self.assertIn("financial-agent-prep-api-rollback:", restore_old)
        self.assertIn("[0-9]{8}t[0-9]{6}z", restore_old)
        self.assertNotIn("20260827t032046z", restore_old)
        self.assertIn("SAFE JOURNAL STATE", diagnose)
        self.assertNotIn("OLD_READER_VERIFIER)=", diagnose)
        self.assertIn("empty rollback placeholder", resume)
        self.assertIn("resume_cutover_complete", resume)
        self.assertIn("CUTOVER_LOCK_HELD=1", resume)
        self.assertIn('2>&1 </dev/null 9>&- &', resume)
        self.assertIn("T-105 PARTIAL RECOVERY PASS", resume_windows)
        self.assertIn("APPLY_TWO_OFFICIAL_DOCUMENTS", seed)


class DataApiClientContractTest(unittest.TestCase):
    def test_client_uses_http_and_checks_release(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"release_id": RELEASE_ID, "snapshot_hash": "hash", "data": [], "evidence": []},
                request=request,
            )

        transport = httpx.MockTransport(handler)
        raw_client = httpx.Client(base_url="https://data-api.test", transport=transport)
        client = FinancialDataClient(
            "https://data-api.test", expected_release_id=RELEASE_ID, _client=raw_client
        )
        self.assertEqual(client.search_products("KODEX 200")["release_id"], RELEASE_ID)
        client.close()

    def test_client_rejects_release_mismatch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"release_id": "wrong"}, request=request)

        client = FinancialDataClient(
            "https://data-api.test",
            expected_release_id=RELEASE_ID,
            _client=httpx.Client(base_url="https://data-api.test", transport=httpx.MockTransport(handler)),
        )
        with self.assertRaises(DataApiClientError) as caught:
            client.release()
        self.assertEqual(caught.exception.code, "RELEASE_MISMATCH")
        client.close()

    def test_client_pins_raw_release_then_uses_catalog_sql_and_sparql(self):
        requests: list[tuple[str, str, dict | None]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content) if request.content else None
            requests.append((request.method, request.url.path, payload))
            if request.url.path == "/db/version":
                return httpx.Response(
                    200,
                    json={"rows": [{"release_id": RELEASE_ID}]},
                    request=request,
                )
            if request.url.path == "/db/catalog":
                return httpx.Response(200, json={"rows": [{"table_name": "product_master"}]}, request=request)
            if request.url.path == "/db/sql":
                return httpx.Response(200, json={"rows": [{"probe": 1}]}, request=request)
            if request.url.path == "/db/sparql":
                return httpx.Response(200, json={"rows": [{"triples": "655388"}]}, request=request)
            raise AssertionError(request.url)

        raw_client = httpx.Client(base_url="https://data-api.test", transport=httpx.MockTransport(handler))
        client = FinancialDataClient(
            "https://data-api.test",
            expected_release_id=RELEASE_ID,
            _client=raw_client,
        )
        self.assertEqual(client.catalog(table_schema="enriched")["rows"][0]["table_name"], "product_master")
        self.assertEqual(client.sql("SELECT %(value)s AS probe", {"value": 1})["rows"][0]["probe"], 1)
        self.assertEqual(client.sparql("SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }")["rows"][0]["triples"], "655388")
        self.assertEqual(sum(path == "/db/version" for _method, path, _payload in requests), 1)
        sql_payload = next(payload for method, path, payload in requests if method == "POST" and path == "/db/sql")
        sparql_payload = next(payload for method, path, payload in requests if method == "POST" and path == "/db/sparql")
        self.assertEqual(sql_payload, {"sql": "SELECT %(value)s AS probe", "params": {"value": 1}})
        self.assertEqual(
            sparql_payload,
            {"sparql": "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }"},
        )
        client.close()


if __name__ == "__main__":
    unittest.main()
