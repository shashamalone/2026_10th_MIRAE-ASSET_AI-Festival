# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kb.build_catalog_v2 import build_outputs  # noqa: E402
from kb.catalog_v2 import build_catalog  # noqa: E402
from kb.v2_manifest import SOURCES, snapshot_hash, validate_source_dir  # noqa: E402
from kb.regression_v2 import load_cases  # noqa: E402
from tools.sql_guard import ensure_read_only_sparql, ensure_read_only_sql  # noqa: E402


class SourceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inspections = validate_source_dir()

    def test_exact_source_shapes_and_primary_keys(self):
        self.assertEqual(
            [(item.row_count, len(item.columns)) for item in self.inspections],
            [(21_882, 58), (1_780, 98), (6_037, 49), (23_676, 75)],
        )
        self.assertEqual(self.inspections[0].spec.primary_key, ("pd_no", "pd_exg_mkt", "info_base_dt", "info_seq"))
        self.assertTrue(any(item.as_dict()["official_nullable_conflicts"] for item in self.inspections))

    def test_catalog_contains_every_raw_column_once(self):
        catalog = build_catalog(self.inspections)
        raw = {table.name: table for table in catalog if table.schema == "raw"}
        for item in self.inspections:
            table = raw[item.spec.raw_table]
            self.assertEqual(len(table.columns), item.spec.expected_columns)
            self.assertEqual(len({column.name for column in table.columns}), len(table.columns))

    def test_generated_agent_catalog_matches_snapshot(self):
        outputs = build_outputs()
        target = ROOT / "metadata" / "schema_catalog.json"
        payload = json.loads(outputs[target])
        self.assertEqual(payload["snapshot_hash"], snapshot_hash(self.inspections))
        self.assertEqual(payload["business_rules"]["buyable_quantity"], "storage_only_never_use_for_purchasability")


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

    def test_zero_metrics_are_never_available(self):
        text = (ROOT / "sql" / "v2" / "010_enrich.sql").read_text(encoding="utf-8").lower()
        self.assertGreaterEqual(text.count("value is not null and value <> 0"), 4)
        self.assertIn("lseg_adjusted_or_total_return_field_unavailable", text)


class RegressionContractTest(unittest.TestCase):
    def test_expected_question_fixture_has_exactly_35_cases(self):
        cases = load_cases()
        self.assertEqual(len(cases), 35)
        self.assertEqual([case["id"] for case in cases], [str(number) for number in range(1, 36)])


if __name__ == "__main__":
    unittest.main()
