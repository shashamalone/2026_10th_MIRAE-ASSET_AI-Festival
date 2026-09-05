"""Offline regressions: python -m unittest discover -s test/catalog-sql -v."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from agent import utils
from tools import catalog_sql as c, rdb_schema as r, schema_snapshot as physical


def snapshot():
    tables = {}
    for domain, entry in r.RDB_SCHEMA.items():
        table = r.get_domain_entry(domain)["table"]
        columns = {col: {"data_type": "text"} for col in entry["properties"]}
        tables[table] = {"columns": columns}
        tables[c.MASTER_TABLES[table]] = {"columns": dict(columns)}
    for decl in r.DERIVED_JOIN_PHYSICAL_REFS.values():
        for table, column in decl["columns"]:
            tables.setdefault(table, {"columns": {}})["columns"][column] = {"data_type": "text"}
    return {"tables": tables, "source_url": "http://offline.invalid", "fetched_at": "offline", "version": {"rows": [{"release_id": "offline"}]}}


def resolved(domain="국내ETF", fields=None, conditions=None, sort=None, entities=None):
    step = {"domain": domain, "role": "target", "fields": fields or ["상품명"],
            "conditions": conditions or [], "sort": sort,
            "product_name_entities": [{"surface_form": x} for x in entities or []]}
    return utils.build_resolved_schema(step, r.get_attribute_catalog(domain), [])


class CompilerTests(unittest.TestCase):
    def setUp(self):
        self.snap = snapshot()

    def compile(self, schema=None, **kwargs):
        return c.compile_select(schema or resolved(), snapshot=self.snap, metadata={}, **kwargs)["sql"]

    def test_curated_columns_cannot_drift(self):
        sql = self.compile(resolved(fields=["AUM", "기초지수", "NAV"]))
        self.assertIn("base.pd_net_tamt AS pd_net_tamt", sql)
        self.assertIn("base.ref_base_index AS ref_base_index", sql)
        self.assertNotIn("du_last_aum", sql)
        self.assertNotIn("cu_base_index", sql)

    def test_identity_and_provenance_are_not_optional(self):
        schema = resolved(fields=["AUM"])
        sql = c.compile_select(schema, snapshot=self.snap, metadata={
            "pd_net_tamt": {"as_of_column": "du_upt_dt,ref_base_dt"}})["sql"]
        for column in ["pd_itm_no", "du_upt_dt", "ref_base_dt"]:
            self.assertIn(f"base.{column} AS {column}", sql)

    def test_composite_provenance_is_not_mapped_to_one_column(self):
        step = {"domain": "국내ETF", "fields": ["각 수치의 기준일"], "conditions": []}
        self.assertNotIn("각 수치의 기준일", utils.collect_needed_concepts(step))
        schema = utils.build_resolved_schema(step, r.get_attribute_catalog("국내ETF"), [])
        self.compile(schema)

    def test_default_domain_filters(self):
        self.assertIn("base.pd_grp_no = E'ETF'", self.compile())
        # Reviewed fund caveat is conditional, not permission to add a filter.
        self.assertNotIn("base.prvo_pbff_desc =", self.compile(resolved("펀드")))

    def test_explicit_etn_overrides_default(self):
        schema = resolved()
        schema["subtype"] = ["ETN"]
        self.assertIn("base.pd_grp_no = E'ETN'", self.compile(schema))

    def test_unmapped_subtype_is_not_silently_discarded(self):
        schema = utils.build_resolved_schema({"domain": "국내ETF", "subtype": ["반도체"]}, r.get_attribute_catalog("국내ETF"), [])
        with self.assertRaises(c.CompileError):
            self.compile(schema)

    def test_named_lookup_retains_unverified_classification_caveat(self):
        step = {"domain": "국내ETF", "subtype": ["인덱스"], "product_name_entities": [{"surface_form": "KODEX 200"}]}
        schema = utils.build_resolved_schema(step, r.get_attribute_catalog("국내ETF"), [])
        self.assertEqual(schema["unverified_subtypes"], ["인덱스"])
        self.assertTrue(any("충족한다고 판단하면 안" in note for note in schema["notes"]))
        self.assertIn("POSITION(E'kodex200'", self.compile(schema))

    def test_named_ranking_does_not_drop_unverified_subtype(self):
        step = {"domain": "국내ETF", "subtype": ["인덱스"], "product_name_entities": [{"surface_form": "KODEX"}], "sort": {"attribute": "순자산"}}
        schema = utils.build_resolved_schema(step, r.get_attribute_catalog("국내ETF"), [])
        with self.assertRaises(c.CompileError):
            self.compile(schema)

    def test_ticker_uses_reviewed_identifiers_as_alternatives(self):
        for name in ["VOO", "BND", "VOO.P", "QQQ"]:
            schema = resolved("해외ETF", entities=[name])
            sql = self.compile(schema)
            self.assertIn("UPPER(BTRIM(base.pd_abrv_nm::text)) = " + c.literal(name), sql)
            self.assertIn("UPPER(BTRIM(base.pd_itm_no::text)) = " + c.literal(name), sql)
            self.assertIn(" OR ", sql)

    def test_current_aum_cannot_drift(self):
        with patch.object(c, "domain_metadata", return_value={}):
            mapping, missing = utils.resolve_concepts_for_domain("국내ETF", ["현재 AUM"], "", Mock())
        self.assertEqual(missing, [])
        self.assertEqual(mapping["현재 AUM"].column, "pd_net_tamt")

    def test_explicit_public_fund_subtype_preserved(self):
        schema = utils.build_resolved_schema({"domain": "펀드", "subtype": ["공모펀드"]}, r.get_attribute_catalog("펀드"), [])
        self.assertIn("base.prvo_pbff_desc::text = E'공모'", self.compile(schema))

    def test_limit_surface_forms_preserve_count(self):
        for value in ["1", "top 1", "TOP1", "1개"]:
            self.assertEqual(c.limit_value(value), 1)
        for value in ["all", "0", "-1", "1; SELECT 1"]:
            with self.assertRaises(c.CompileError):
                c.limit_value(value)

    def test_db_zero_missing_policy(self):
        schema = resolved(sort={"attribute": "AUM"})
        sql = c.compile_select(schema, snapshot=self.snap, metadata={"pd_net_tamt": {
            "zero_null_rule": "0은 원본 보존; 측정값 비교·랭킹에서는 값 없음"}})["sql"]
        self.assertIn("NULLIF", sql)

    def test_name_normalizes_both_sides(self):
        for domain, name in [("채권", "국고채권 02000-3106(21-5)"), ("국내ETF", "KODEX 200")]:
            sql = self.compile(resolved(domain, entities=[name]))
            self.assertIn(c.literal(name.replace(" ", "").lower()), sql)
            self.assertIn("REPLACE(base.pd_nm::text, ' ', '')", sql)

    def test_comparison_entities_are_or(self):
        sql = self.compile(resolved(entities=["KODEX 200", "TIGER 200"]))
        self.assertIn(" OR ", sql)
        self.assertEqual(sql.count("POSITION("), 2)

    def test_literal_substrings_not_like_patterns(self):
        sql = self.compile(resolved(entities=["O'Reilly_%\\ETF"]))
        self.assertIn("o''reilly_%\\\\etf", sql)
        self.assertNotIn("LIKE", sql)

    def test_nul_rejected(self):
        with self.assertRaises(c.CompileError):
            self.compile(resolved(entities=["bad\0value"]))

    def test_injected_column_rejected(self):
        schema = resolved()
        schema["fields"][0]["column"] = "pd_nm; DROP TABLE raw.pref01n001"
        with self.assertRaises(c.CompileError):
            self.compile(schema)

    def test_existing_but_uncatalogued_join_rejected(self):
        schema = resolved()
        schema["fields"][0].update(column="evil.pd_nm", spec=r.AttributeSpec(column="evil.pd_nm", value_type="text"))
        with self.assertRaises(c.CompileError):
            self.compile(schema)

    def test_missing_live_column_blocks_before_execution(self):
        del self.snap["tables"]["raw.pref01n001"]["columns"]["pd_nm"]
        with self.assertRaises(physical.SchemaContractError):
            self.compile()

    def test_missing_join_blocks_before_execution(self):
        del self.snap["tables"]["enriched.product_metric"]
        with self.assertRaises(physical.SchemaContractError):
            self.compile(resolved(fields=["총보수율"]))

    def test_only_registered_join_with_availability(self):
        sql = self.compile(resolved(fields=["총보수율"]))
        self.assertIn("CASE WHEN m.is_available THEN m.value END", sql)
        self.assertEqual(sql.count("LEFT JOIN"), 1)

    def test_numeric_sort_casts_text_and_excludes_nulls(self):
        sql = self.compile(resolved(sort={"attribute": "순자산", "order": "desc", "limit": "5"}))
        self.assertIn("::numeric", sql)
        self.assertIn("IS NOT NULL", sql)
        self.assertIn("DESC NULLS LAST\nLIMIT 5", sql)

    def test_all_sort_fields_projected(self):
        self.assertIn("base.pd_net_tamt AS pd_net_tamt", self.compile(resolved(sort={"attribute": "순자산"})))

    def test_ordinal_condition_uses_finite_set(self):
        sql = self.compile(resolved("채권", conditions=[{"attribute": "신용등급", "operator": "gte", "value": "AA-"}]))
        self.assertIn("E'AAA'", sql)
        self.assertNotIn("E'BB+'", sql)
        self.assertNotIn("crd_grd >=", sql)

    def test_ordinal_sort_uses_rank(self):
        sql = self.compile(resolved("채권", sort={"attribute": "신용등급", "order": "desc"}))
        self.assertIn("CASE base.crd_grd WHEN", sql)

    def test_empty_condition_never_dropped(self):
        with self.assertRaises(c.CompileError):
            self.compile(resolved(conditions=[{"attribute": "순자산", "operator": "gte", "value": ""}]))

    def test_ordinal_invalid_between_endpoint_rejected(self):
        for endpoint in ("", "AAAA"):
            with self.subTest(endpoint=endpoint), self.assertRaises(c.CompileError):
                self.compile(resolved("채권", conditions=[{"attribute": "신용등급", "operator": "between", "value": "AA-", "value_2": endpoint}]))

    def test_numeric_zero_is_not_empty(self):
        self.assertIn(">= 0", self.compile(resolved(conditions=[{"attribute": "순자산", "operator": "gte", "value": 0}])))

    def test_date_conversion_validates_calendar(self):
        schema = resolved("채권", conditions=[{"attribute": "만기일", "operator": "lte", "value": "2031-06-10"}])
        self.assertIn("<= 20310610", self.compile(schema))
        schema["conditions"][0]["value"] = "2026-02-30"
        with self.assertRaises(c.CompileError):
            self.compile(schema)

    def test_numeric_injection_rejected(self):
        with self.assertRaises(c.CompileError):
            self.compile(resolved(conditions=[{"attribute": "순자산", "operator": "gte", "value": "0 OR 1=1"}]))

    def test_limit_and_order_injection_rejected(self):
        for sort in ({"attribute": "순자산", "limit": "1; SELECT 1"}, {"attribute": "순자산", "order": "desc; SELECT 1"}):
            with self.assertRaises(c.CompileError):
                self.compile(resolved(sort=sort))

    def test_boolean_sale_policies(self):
        for domain, expected in [("국내ETF", "E'1'"), ("펀드", "E'판매중'")]:
            sql = self.compile(resolved(domain, conditions=[{"attribute": "판매가능여부", "operator": "eq", "value": "true"}]))
            self.assertIn("= " + expected, sql)

    def test_union_projection_is_fixed(self):
        sql = self.compile(resolved(fields=["상품코드"], sort={"attribute": "순자산", "limit": "3"}), union_mode=True)
        self.assertIn(" AS code,", sql)
        self.assertIn(" AS name,", sql)
        self.assertIn(" AS domain,", sql)
        self.assertIn(" AS sort_value", sql)
        self.assertNotIn("ORDER BY", sql)
        self.assertNotIn("LIMIT", sql)

    def test_units_do_not_guess_currency(self):
        self.assertEqual(c.numeric_value("3년", "remaining_days"), "1095")
        self.assertEqual(c.numeric_value("5000억원", "pd_net_tamt"), "500000000000")
        with self.assertRaises(c.CompileError):
            c.numeric_value("1조원", "cu_net_asset")

    def test_unknown_operator_rejected(self):
        with self.assertRaises(c.CompileError):
            self.compile(resolved(conditions=[{"attribute": "순자산", "operator": "select", "value": "1"}]))


class MetadataTests(unittest.TestCase):
    def test_description_aliases_preserve_curated_overrides(self):
        rows = {"cu_base_index": {"description": "기초지수"}, "pd_net_tamt": {"description": "순자산 총액"}}
        aliases = c.description_aliases("국내ETF", rows)
        self.assertNotIn("기초지수", aliases)
        self.assertEqual(aliases["순자산총액"].column, "pd_net_tamt")

    def test_ambiguous_descriptions_not_registered(self):
        self.assertEqual(c.description_aliases("국내ETF", {"cu_base_index": {"description": "새이름"}, "ref_base_index": {"description": "새 이름"}}), {})

    def test_metadata_does_not_become_sql_expression(self):
        spec = c.spec_for_column("국내ETF", "ref_base_index", {"ref_base_index": {"transform_expression": "DELETE FROM raw.pref01n001"}})
        self.assertEqual(spec.column, "ref_base_index")

    def test_alias_resolves_without_llm(self):
        llm = Mock()
        with patch.object(c, "domain_metadata", return_value={"pd_net_tamt": {"description": "순자산 총액"}}):
            mapping, missing = utils.resolve_concepts_for_domain("국내ETF", ["순자산 총액"], "", llm)
        self.assertEqual(mapping["순자산 총액"].column, "pd_net_tamt")
        self.assertEqual(missing, [])
        llm.with_structured_output.assert_not_called()

    def test_hallucinated_column_and_unsolicited_concepts_rejected(self):
        llm = Mock()
        llm.with_structured_output.return_value.invoke.return_value = {"resolutions": [
            {"concept": "새개념", "column": "du_base_dt"},
            {"concept": "AUM", "column": "du_last_aum"}]}
        with patch.object(physical, "get_snapshot", return_value=snapshot()), patch.object(c, "domain_metadata", return_value={}):
            self.assertEqual(utils._resolve_unknown_concepts_via_llm("국내ETF", ["새개념"], "", llm), {})

    def test_conflicting_llm_resolutions_rejected(self):
        llm = Mock()
        llm.with_structured_output.return_value.invoke.return_value = {"resolutions": [
            {"concept": "새개념", "column": "pd_net_tamt"}, {"concept": "새개념", "column": "du_last_aum"}]}
        with patch.object(physical, "get_snapshot", return_value=snapshot()), patch.object(c, "domain_metadata", return_value={}):
            self.assertEqual(utils._resolve_unknown_concepts_via_llm("국내ETF", ["새개념"], "", llm), {})

    def test_metadata_missing_row_fails_closed(self):
        c._SEMANTIC_CACHE.clear()
        with patch.object(physical, "_request", return_value={"rows": []}), self.assertRaises(c.CompileError):
            c.domain_metadata("국내ETF", snapshot())

    def test_view_master_mismatch_fails_closed(self):
        snap = snapshot()
        del snap["tables"]["raw.etf_kr_master"]["columns"]["pd_nm"]
        with self.assertRaises(c.CompileError):
            c.domain_metadata("국내ETF", snap)


class NodeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Construct SDK clients without using a real key or any network calls.
        with patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "offline-test-key"}):
            from agent import nodes
        cls.nodes = nodes

    def setUp(self):
        self.physical = patch.object(physical, "get_snapshot", return_value=snapshot())
        self.meta = patch.object(c, "domain_metadata", return_value={})
        self.physical.start()
        self.meta.start()
        self.addCleanup(self.physical.stop)
        self.addCleanup(self.meta.stop)

    def test_target_does_not_call_sql_llms(self):
        step = {"domain": "국내ETF", "fields": ["AUM", "기초지수"], "conditions": []}
        with patch.object(self.nodes, "_write_sql") as writer, patch.object(self.nodes, "_draft_query_description") as drafter, patch.object(utils, "run_sql", return_value=[{"pd_nm": "ETF"}]) as runner:
            result = self.nodes._execute_target_step(step, "", Mock(), True, 3)
        self.assertEqual(result["count"], 1)
        writer.assert_not_called()
        drafter.assert_not_called()
        runner.assert_called_once()
        self.assertEqual(result["sql_compiler"], "catalog-sql-v1")

    def test_compiled_sql_error_never_rewritten(self):
        with patch.object(utils, "run_sql", side_effect=RuntimeError("invalid input syntax")) as runner, patch.object(self.nodes, "_fix_sql") as fixer:
            result = self.nodes._run_sql_with_retry(Mock(), "国", "", "", {"sql": "SELECT 1", "compiled": True}, 3)
        runner.assert_called_once()
        fixer.assert_not_called()
        self.assertEqual(result["sql"], "SELECT 1")
        self.assertIsNotNone(result["error"])

    def test_compiled_rate_limit_retries_exact_same_sql(self):
        with patch.object(utils, "run_sql", side_effect=[RuntimeError("HTTP 429"), []]) as runner, patch.object(self.nodes.time, "sleep"), patch.object(self.nodes, "_fix_sql") as fixer:
            result = self.nodes._run_sql_with_retry(Mock(), "국내ETF", "", "", {"sql": "SELECT 1", "compiled": True}, 3)
        self.assertIsNone(result["error"])
        self.assertEqual([call.args[1] for call in runner.call_args_list], ["SELECT 1", "SELECT 1"])
        fixer.assert_not_called()

    def test_failed_graph_dependency_blocks_target(self):
        step = {"domain": "채권", "depends_on": ["g1"], "fields": ["상품명"]}
        handoff = self.nodes._apply_graph_handoff(step, {"g1": {"engine": "graph", "entity_codes": []}})
        with patch.object(utils, "run_sql") as runner:
            result = self.nodes._execute_target_step(handoff, "", Mock(), True, 3)
        runner.assert_not_called()
        self.assertIn("skipped_reason", result)

    def test_graph_codes_are_kept_in_compiled_predicate(self):
        step = {"domain": "국내ETF", "depends_on": ["g1"], "fields": ["상품명"]}
        handoff = self.nodes._apply_graph_handoff(step, {"g1": {"engine": "graph", "entity_codes": ["KR7069500007"]}})
        with patch.object(utils, "run_sql", return_value=[]):
            result = self.nodes._execute_target_step(handoff, "", Mock(), True, 3)
        self.assertIn("base.pd_itm_no::text IN (E'KR7069500007')", result["sql"])

    def test_union_does_not_call_sql_writer(self):
        steps = [{"step_id": f"r{i}", "domain": domain, "fields": [], "conditions": [],
                  "sort": {"attribute": "순자산", "order": "desc", "limit": "5"}}
                 for i, domain in enumerate(["국내ETF", "펀드"])]
        with patch.object(utils, "run_sql", return_value=[]), patch.object(self.nodes, "_write_sql") as writer:
            results = self.nodes._execute_merged_target_group(steps, "", Mock(), {"order": "desc"}, "5", 3)
        self.assertIn("UNION ALL", results["r0"]["sql"])
        writer.assert_not_called()

    def test_blocked_graph_excluded_from_union(self):
        step = {"step_id": "r1", "domain": "채권", "graph_handoff_blocked": "empty graph"}
        with patch.object(utils, "run_sql") as runner:
            result = self.nodes._execute_merged_target_group([step], "", Mock(), {}, "5", 3)
        runner.assert_not_called()
        self.assertEqual(result["r1"]["skipped_reason"], "empty graph")


if __name__ == "__main__":
    unittest.main()
