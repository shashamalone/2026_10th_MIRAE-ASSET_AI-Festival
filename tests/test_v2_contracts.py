# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kb.build_catalog_v2 import build_outputs  # noqa: E402
from kb.build_rdb import V2_COMMAND, rejection_message  # noqa: E402
from kb.catalog_v2 import build_catalog  # noqa: E402
from kb.collect_lseg_returns_v2 import adjusted_return  # noqa: E402
from kb.regression_v2 import (  # noqa: E402
    enforce_case_deadline,
    load_cases,
    required_evidence,
    validate_answer,
)
from kb.v2_manifest import (  # noqa: E402
    DATASET_VERSION,
    EXPECTED_ABOX_TRIPLES,
    EXPECTED_RELATION_COUNTS,
    EXPECTED_SNAPSHOT_HASH,
    EXTERNAL_CUTOFF,
    RELEASE_ID,
    WORKSPACE_ROOT,
    snapshot_hash,
    validate_source_dir,
)
from tools.sql_guard import ensure_read_only_sparql, ensure_read_only_sql  # noqa: E402


class SourceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inspections = validate_source_dir()
        cls.outputs = build_outputs()

    def test_exact_source_shapes_and_primary_keys(self):
        self.assertEqual(
            [(item.row_count, len(item.columns)) for item in self.inspections],
            [(21_882, 58), (1_780, 98), (6_037, 49), (23_676, 75)],
        )
        self.assertEqual(
            self.inspections[0].spec.primary_key,
            ("pd_no", "pd_exg_mkt", "info_base_dt", "info_seq"),
        )
        self.assertEqual(self.inspections[3].spec.primary_key, ("itm_no",))
        self.assertTrue(all(item.excluded_rows == 0 for item in self.inspections))
        self.assertEqual(sum(item.row_count for item in self.inspections), 53_375)
        self.assertEqual(sum(len(item.columns) for item in self.inspections), 280)
        self.assertEqual(EXTERNAL_CUTOFF, date(2026, 8, 24))
        self.assertEqual(snapshot_hash(self.inspections), EXPECTED_SNAPSHOT_HASH)
        self.assertEqual(
            [dict(item.partition_counts) for item in self.inspections],
            [{}, {"ETF": 1_235, "ETN": 545}, {"ETF": 5_972, "ETN": 65}, {"공모": 14_716, "사모": 8_960}],
        )

    def test_catalog_contains_every_raw_column_once(self):
        catalog = build_catalog(self.inspections)
        raw = {table.name: table for table in catalog if table.schema == "raw"}
        for item in self.inspections:
            table = raw[item.spec.raw_table]
            self.assertEqual(len(table.columns), item.spec.expected_columns)
            self.assertEqual(len({column.name for column in table.columns}), len(table.columns))

    def test_generated_agent_catalog_matches_snapshot(self):
        target = ROOT / "metadata" / "schema_catalog.json"
        payload = json.loads(self.outputs[target])
        self.assertEqual(payload["dataset_version"], DATASET_VERSION)
        self.assertEqual(payload["release_id"], RELEASE_ID)
        self.assertEqual(payload["snapshot_hash"], snapshot_hash(self.inspections))
        self.assertEqual(payload["business_rules"]["buyable_quantity"], "storage_only_never_use_for_purchasability")
        self.assertIn("never_treat_as_lowest", payload["business_rules"]["bond_missing_credit_rating"])
        self.assertIn("never_filter_or_rank", payload["business_rules"]["dummy_divergence_rate"])
        self.assertIn("normalize", payload["business_rules"]["string_sentinel"])

    def test_three_database_definitions_cover_their_owned_objects(self):
        rdb_path = ROOT / "docs" / "docs_data_layer" / "RDB_DEFINITION_V2_0.md"
        vector_path = ROOT / "docs" / "docs_data_layer" / "VECTORDB_DEFINITION_V2_0.md"
        graph_path = ROOT / "docs" / "docs_data_layer" / "GRAPHDB_DEFINITION_V2_0.md"
        rdb, vector, graph = (self.outputs[path] for path in (rdb_path, vector_path, graph_path))
        catalog = build_catalog(self.inspections)
        for table in catalog:
            owner = vector if table.schema == "vec" else rdb
            other = rdb if table.schema == "vec" else vector
            heading = f"### `{table.fq_name}`"
            self.assertEqual(owner.count(heading), 1, table.fq_name)
            self.assertNotIn(heading, other, table.fq_name)
        for name in ("common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"):
            self.assertIn(f"../../ontology/{name}", graph)
        for required in ("fp:Holding", "fp:SubsidiaryRelation", "fp:hasAssetType", "named graph"):
            self.assertIn(required, graph)
        for required in (
            "식별자와 조인 지도",
            "지표 의미 사전",
            "안전한 SQL 패턴",
            "LLM/Agent evidence 계약",
        ):
            self.assertIn(required, rdb)
        for required in ("라우팅 계약", "근거 반환 계약", "Graph → RDB → Vector 결합 예"):
            self.assertIn(required, vector)
        for required in (
            "namespace와 named graph 질의 계약",
            "관계 부재와 ABSTAIN 계약",
            "LLM/Agent 반환 계약",
        ):
            self.assertIn(required, graph)

    def test_generated_database_definition_links_exist(self):
        paths = [
            ROOT / "docs" / "docs_data_layer" / "RDB_DEFINITION_V2_0.md",
            ROOT / "docs" / "docs_data_layer" / "VECTORDB_DEFINITION_V2_0.md",
            ROOT / "docs" / "docs_data_layer" / "GRAPHDB_DEFINITION_V2_0.md",
        ]
        for path in paths:
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", self.outputs[path]):
                if "://" in target:
                    continue
                self.assertTrue((path.parent / target).resolve().exists(), f"{path.name}: {target}")

    def test_legacy_july_csv_bundle_is_rejected_before_load(self):
        legacy = WORKSPACE_ROOT / "data" / "data" / "csv"
        with self.assertRaises(ValueError):
            validate_source_dir(legacy)

    def test_legacy_rdb_entrypoint_only_points_to_v2(self):
        self.assertIn(V2_COMMAND, rejection_message())
        self.assertIn("금지", rejection_message())


class QueryGuardTest(unittest.TestCase):
    def test_allows_read_only_sql(self):
        self.assertEqual(ensure_read_only_sql("SELECT 1;"), "SELECT 1")
        self.assertEqual(ensure_read_only_sql("WITH x AS (SELECT 1) SELECT * FROM x"), "WITH x AS (SELECT 1) SELECT * FROM x")

    def test_rejects_writes_and_data_modifying_cte(self):
        for query in (
            "DELETE FROM enriched.product_master",
            "WITH gone AS (DELETE FROM raw.bond_kr_master RETURNING *) SELECT * FROM gone",
            "SELECT 1; DROP TABLE raw.bond_kr_master",
            "COPY raw.bond_kr_master TO '/tmp/leak'",
            "SELECT pg_read_file('/etc/passwd')",
        ):
            with self.subTest(query=query), self.assertRaises(ValueError):
                ensure_read_only_sql(query)

    def test_literals_do_not_trigger_false_positive(self):
        self.assertEqual(ensure_read_only_sql("SELECT 'delete' AS word"), "SELECT 'delete' AS word")

    def test_sparql_update_is_rejected(self):
        self.assertEqual(ensure_read_only_sparql("SELECT * WHERE { ?s ?p ?o }"), "SELECT * WHERE { ?s ?p ?o }")
        with self.assertRaises(ValueError):
            ensure_read_only_sparql("INSERT DATA { <a> <b> <c> }")


class SqlPolicyTest(unittest.TestCase):
    def test_buyable_quantity_is_storage_only(self):
        text = (ROOT / "sql" / "v2" / "010_enrich.sql").read_text(encoding="utf-8").lower()
        decision_statements = [statement for statement in text.split(";") if "is_assumed_purchasable" in statement]
        self.assertTrue(decision_statements)
        self.assertTrue(all("buyable_quantity" not in statement.replace("buyable_quantity ignored", "") for statement in decision_statements))

    def test_known_sentinel_and_missing_rating_are_not_rankable(self):
        sql_text = (ROOT / "sql" / "v2" / "010_enrich.sql").read_text(encoding="utf-8").lower()
        self.assertIn("index is not %", sql_text)
        catalog_text = (ROOT / "src" / "kb" / "catalog_v2.py").read_text(encoding="utf-8")
        self.assertIn("국채 무등급을 최저등급으로 간주 금지", catalog_text)
        self.assertIn("비값 문자열은 NULL", catalog_text)

    def test_zero_metrics_are_never_available(self):
        text = (ROOT / "sql" / "v2" / "010_enrich.sql").read_text(encoding="utf-8").lower()
        self.assertGreaterEqual(text.count("value is not null and value <> 0"), 4)
        self.assertIn("lseg_adjusted_or_total_return_field_unavailable", text)

    def test_metric_dates_and_fund_expense_semantics(self):
        text = (ROOT / "sql" / "v2" / "010_enrich.sql").read_text(encoding="utf-8").lower()
        self.assertIn("'aum', du_last_aum::numeric, 'du_last_aum', __meta__.yyyymmdd(du_upt_dt)", text)
        self.assertIn("'expense_ratio', nullif(btrim(cu_charge_rt), '')::numeric, 'cu_charge_rt', __meta__.yyyymmdd(cu_upt_dt)", text)
        self.assertNotIn("'zrin_fd_cmst_rt'", text)
        self.assertIn("ofwk_trus_rwrd_r+or_co_rwrd_r+sale_co_rwrd_r+trusc_rwrd_r", text)
        self.assertIn("incomplete_fee_components", text)

    def test_global_inception_and_asset_type_contracts(self):
        ddl = (ROOT / "sql" / "v2" / "001_platform_schema.sql").read_text(encoding="utf-8")
        graph = (ROOT / "src" / "kb" / "build_graph_v2.py").read_text(encoding="utf-8")
        vectors = (ROOT / "src" / "kb" / "build_vectors_v2.py").read_text(encoding="utf-8")
        self.assertIn("inception_date date", ddl)
        self.assertIn('"asset_type": ("hasAssetType", "AssetType")', graph)
        self.assertIn("domain_file text NOT NULL", ddl)
        self.assertIn("property_type text NOT NULL", ddl)
        self.assertIn('"domain_file":', vectors)
        self.assertIn('"property_type":', vectors)

    def test_builder_image_and_cutover_grants(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        cutover = (ROOT / "deploy" / "cutover_v2.sh").read_text(encoding="utf-8")
        self.assertIn("COPY docs/docs_data_layer /app/docs/docs_data_layer", dockerfile)
        self.assertIn("COPY expected_question /app/expected_question", dockerfile)
        self.assertLess(cutover.index("trap rollback_on_error ERR"), cutover.index("090_cutover.sql"))
        self.assertLess(cutover.index("100_readonly_grants.sql"), cutover.index("verify_v2.sh"))

    def test_explicit_compatibility_views_cover_legacy_names(self):
        compatibility = (ROOT / "src" / "kb" / "compatibility_v2.py").read_text(encoding="utf-8")
        self.assertNotIn("SELECT *", compatibility.upper())
        for name in (
            "prbd01n001",
            "pref01n001",
            "pref02n001",
            "prfd01n001",
            "etf_holding",
            "etf_theme",
            "doc_chunk",
            "schema_index",
        ):
            self.assertIn(f'"{name}"', compatibility)

    def test_vector_release_is_schema_only_or_exact_reuse(self):
        vectors = (ROOT / "src" / "kb" / "build_vectors_v2.py").read_text(encoding="utf-8")
        self.assertNotIn("embed_many(", vectors)
        self.assertNotIn("import clova", vectors)
        self.assertIn('status = "pending"', vectors)
        self.assertIn('"embedding_calls": 0', vectors)
        self.assertIn("vector(1024)", (ROOT / "sql" / "v2" / "001_platform_schema.sql").read_text(encoding="utf-8"))

    def test_graph_and_relation_acceptance_constants_are_fixed(self):
        self.assertEqual(EXPECTED_RELATION_COUNTS, {"product_holdings": 46_951, "company_subsidiaries": 8_866})
        self.assertEqual(EXPECTED_ABOX_TRIPLES, 655_388)
        graph = (ROOT / "src" / "kb" / "build_graph_v2.py").read_text(encoding="utf-8")
        self.assertIn("validate_manifest_files", graph)
        self.assertIn("EXPECTED_ABOX_TRIPLES", graph)

    def test_api_v1_v2_routes_aliases_and_envelope(self):
        api = (ROOT / "src" / "api.py").read_text(encoding="utf-8")
        for route in (
            '@app.post("/db")',
            '@app.post("/db/sql")',
            '@app.post("/db/sparql")',
            '@app.get("/db/stats")',
            '@app.get("/db/columns/{table_schema}/{table_name}")',
            '@app.get("/db/catalog")',
            '@app.get("/db/coverage")',
            '@app.get("/db/version")',
        ):
            self.assertIn(route, api)
        for field in ('"columns"', '"rows"', '"row_count"', '"truncated"', '"elapsed_ms"'):
            self.assertIn(field, api)
        self.assertIn("STATEMENT_TIMEOUT_MS = min(2000", api)
        self.assertIn('rdb_hash == graph_hash == EXPECTED_SNAPSHOT_HASH', api)
        self.assertIn('vector_status in {"pending", "ready"}', api)

    def test_backup_cutover_and_rollback_are_coupled(self):
        backup = (ROOT / "deploy" / "backup_v2.sh").read_text(encoding="utf-8")
        stage = (ROOT / "deploy" / "stage_v2.sh").read_text(encoding="utf-8")
        cutover = (ROOT / "deploy" / "cutover_v2.sh").read_text(encoding="utf-8")
        rollback = (ROOT / "deploy" / "rollback_v2.sh").read_text(encoding="utf-8")
        for token in ("pg_restore --list", "tar -tzf", "SHA256SUMS", "restore-drill"):
            self.assertIn(token, backup)
        self.assertNotIn("CLOVA_API_KEY", stage)
        self.assertLess(stage.index("load_graph_next_v2.sh"), stage.index("validate_data_platform_v2 --stage"))
        self.assertLess(cutover.index("090_cutover.sql"), cutover.index("up -d graph"))
        self.assertNotIn("|| true", cutover)
        self.assertNotIn("|| true", rollback)
        self.assertIn("verify_v2.sh --rollback", rollback)
        self.assertIn("API remains closed", rollback)

    def test_stage_failure_closes_the_running_load_record(self):
        stage = (ROOT / "deploy" / "stage_v2.sh").read_text(encoding="utf-8")
        builder = (ROOT / "src" / "kb" / "build_data_platform_v2.py").read_text(encoding="utf-8")
        self.assertIn("trap mark_stage_failed ERR", stage)
        self.assertIn("--mark-failed stage_command_failed", stage)
        self.assertIn("def mark_latest_run_failed", builder)
        self.assertIn("WHERE status='running'", builder)

    def test_legacy_holdings_document_uses_ddl_enum(self):
        audit = (ROOT / "src" / "kb" / "audit_legacy_evidence_v2.py").read_text(encoding="utf-8")
        self.assertIn('"relation_type": "holdings"', audit)


class LsegWindowTest(unittest.TestCase):
    class FakeLseg:
        def __init__(self, frame):
            self.frame = frame

        def get_history(self, **_kwargs):
            return self.frame

    def test_short_history_is_not_return_1y(self):
        frame = pd.DataFrame(
            {"TRDPRC_1": [100.0, 110.0]},
            index=pd.to_datetime(["2026-01-02", "2026-08-21"]),
        )
        result = adjusted_return(self.FakeLseg(frame), "NEW.RIC")
        self.assertFalse(result["is_available"])
        self.assertEqual(result["unavailable_reason"], "INSUFFICIENT_1Y_OBSERVATION_WINDOW")

    def test_full_window_uses_actual_last_observation(self):
        frame = pd.DataFrame(
            {"TRDPRC_1": [100.0, 110.0]},
            index=pd.to_datetime(["2025-08-24", "2026-08-21"]),
        )
        result = adjusted_return(self.FakeLseg(frame), "FULL.RIC")
        self.assertTrue(result["is_available"])
        self.assertEqual(result["as_of"], "2026-08-21")


class RegressionContractTest(unittest.TestCase):
    def test_expected_question_fixture_has_exactly_35_cases(self):
        cases = load_cases()
        self.assertEqual(len(cases), 35)
        self.assertEqual([case["id"] for case in cases], [str(number) for number in range(1, 36)])

    def test_required_evidence_is_checked_per_question(self):
        case = load_cases()[0]
        records = [
            {
                "requirement_code": item["code"],
                "requirement_label": item["label"],
                "subject": "bond_kr:TEST",
                "source": "PRBD01N001",
                "source_column": "pd_no",
                "as_of": "2026-02-24",
                "evidence_value": "TEST",
            }
            for item in required_evidence(case)
        ]
        validate_answer(case, {"answer": "ok", "retrieved_context": records})
        with self.assertRaises(ValueError):
            validate_answer(case, {"answer": "ok", "retrieved_context": records[:-1]})
        mislabeled = [{**record} for record in records]
        mislabeled[0]["requirement_label"] = "다른 근거"
        with self.assertRaises(ValueError):
            validate_answer(case, {"answer": "ok", "retrieved_context": mislabeled})

    def test_15_second_boundary_is_enforced(self):
        enforce_case_deadline("1", 15.0)
        with self.assertRaises(TimeoutError):
            enforce_case_deadline("1", 15.001)


if __name__ == "__main__":
    unittest.main()
