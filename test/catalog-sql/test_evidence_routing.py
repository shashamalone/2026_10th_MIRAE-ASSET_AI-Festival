"""General identity/provenance invariants, with no paid model or database calls."""
import copy
import json
import os
import unittest
from unittest.mock import Mock, patch

from test_catalog_sql import snapshot, resolved
from agent import utils
from tools import catalog_sql, rdb_schema, schema_snapshot


class IdentityTests(unittest.TestCase):
    def intent(self, names=("XYZ",)):
        return {"product_domain": [{"domain": "펀드", "subtype": ["인덱스형"]}],
                "target_entities": [{"entity_type": "product_name", "surface_form": n} for n in names],
                "conditions": [], "relations": [], "sort": {}, "output_requirements": {"fields": ["총보수"]}}

    def test_verified_domain_corrects_model_guess_without_changing_request(self):
        intent = self.intent()
        before = copy.deepcopy(intent)
        with patch.object(utils, "lookup_product_identities", return_value=[{"query_name": "XYZ", "domain": "해외ETF"}]):
            fixed, notes = utils.resolve_named_product_domains(intent)
        self.assertEqual(fixed["product_domain"], [{"domain": "해외ETF", "subtype": []}])
        self.assertEqual(intent, before)
        self.assertEqual(fixed["output_requirements"], intent["output_requirements"])
        self.assertTrue(notes)

    def test_ambiguous_or_missing_identity_never_guesses_domain(self):
        for rows in [[], [{"query_name": "XYZ", "domain": d} for d in ("펀드", "해외ETF")]]:
            intent = self.intent()
            with patch.object(utils, "lookup_product_identities", return_value=rows):
                self.assertEqual(utils.resolve_named_product_domains(intent)[0], intent)

    def test_relational_company_is_not_retyped_as_target_product(self):
        intent = self.intent()
        intent["relations"] = [{"relation": "issued_by"}]
        with patch.object(utils, "lookup_product_identities") as lookup:
            self.assertEqual(utils.resolve_named_product_domains(intent)[0], intent)
        lookup.assert_not_called()

    def test_identity_sql_is_exact_readonly_and_escaped(self):
        connection = Mock()
        with patch.object(schema_snapshot, "get_snapshot", return_value=snapshot()), \
             patch.object(utils, "get_pg_connection", return_value=connection), \
             patch.object(utils, "run_sql", return_value=[]) as run:
            utils.lookup_product_identities(["NEW'TICKER"])
        sql = run.call_args.args[1]
        self.assertIn("new''ticker", sql)
        self.assertNotIn("LIKE", sql)
        self.assertEqual(sql.count("LIMIT 2"), 4)
        connection.close.assert_called_once()


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "offline-test-key"}):
            from agent import nodes
        cls.nodes = nodes

    def chunk(self):
        return {"chunk_id": "chunk-example", "document_id": "doc-example", "score": .8,
                "source_url": "https://example.org/prospectus", "published_at": "2026-08-01",
                "effective_as_of": "2026-07-31", "page_number": 9, "heading_path": "투자전략",
                "citation_text": "가상 상품 투자설명서", "chunk_text": "문서 원문에 기재된 전략입니다."}

    def test_normalization_keeps_page_and_two_distinct_dates(self):
        chunk = self.nodes._normalize_chunk(self.chunk())
        answer = self.nodes._render_vector_sources({"v1": {"engine": "vector", "status": "ok", "chunks": [chunk]}})
        for token in ["chunk-example", "doc-example", "https://example.org/prospectus", "2026-08-01", "2026-07-31", "페이지: 9"]:
            self.assertIn(token, answer)
        self.assertIn("발표기관: 미확보", answer)

    def test_missing_metadata_and_unsafe_url_are_not_fabricated(self):
        chunk = {"chunk_id": "c", "source_url": "javascript:alert(1)"}
        answer = self.nodes._render_vector_sources({"v": {"engine": "vector", "status": "ok", "chunks": [chunk]}})
        self.assertIn("원문 URL: 미확보", answer)
        self.assertNotIn("javascript", answer)
        self.assertIn("문서명 미확보", answer)

    def test_failed_scope_cannot_trigger_global_search(self):
        state = {"intent": {}, "step_results": {"g": {"engine": "graph", "status": "missing_evidence", "rows": []}}}
        with patch.object(self.nodes, "embed") as embed, patch.object(self.nodes, "search_documents") as search:
            result = self.nodes._run_vector_step(state, {"depends_on": ["g"]}, "어떤 회사의 편입 상품인가?")
        self.assertEqual(result["status"], "unresolved_product_scope")
        embed.assert_not_called()
        search.assert_not_called()

    def test_abstention_row_is_not_a_fact(self):
        state = {"step_results": {"g": {"engine": "graph", "status": "missing_evidence", "rows": [{"status": "abstain"}]}}}
        self.assertEqual(self.nodes.merge_results_node(state)["merged_rows"], [])
        self.assertIn("관계 근거 미확보", self.nodes._render_execution_limits(state))

    def test_vector_source_survives_blank_answer_model(self):
        state = {"question": "전략 원문을 알려줘", "intent": {}, "step_results": {
            "v": {"engine": "vector", "status": "ok", "chunks": [self.chunk()]}}}
        state.update(self.nodes.merge_results_node(state))
        with patch.object(self.nodes, "_llm_answer") as llm:
            llm.with_structured_output.return_value.invoke.return_value = {"answer": "", "think_trace": ""}
            answer = json.loads(self.nodes.generate_answer_node(state)["answer"])["answer"]
        self.assertIn("https://example.org/prospectus", answer)

    def test_classification_retains_raw_values_and_missing_axis(self):
        schema = resolved("국내ETF", fields=["분류 근거"])
        row = utils.derive_output_views([{"wu_inv_ast_type": "주식", "wu_inv_rgn": None, "cu_strtegy": "실물복제"}], schema["output_views"])[0]
        item = row["_derived_fields"]["분류근거"]
        self.assertIn("Strategy_Passive", item["value"])
        self.assertIn("실물복제", item["value"])
        self.assertIn("InvestmentRegion: wu_inv_rgn 원천값 미확보", item["value"])
        self.assertIn("raw.pref01n001.cu_strtegy", item["source_columns"])
        self.assertNotIn("prbd", " ".join(item["source_columns"]))

    def test_new_date_request_is_not_guessed_as_a_physical_column(self):
        step = {"domain": "국내ETF", "fields": ["수치 갱신일"]}
        self.assertNotIn("수치 갱신일", utils.collect_needed_concepts(step))

    def test_source_field_request_is_not_guessed_as_a_physical_column(self):
        step = {"domain": "해외ETF", "fields": ["전략 원문의 출처 필드"]}
        self.assertNotIn("전략 원문의 출처 필드", utils.collect_needed_concepts(step))


class CategoryAndUnitTests(unittest.TestCase):
    def compile(self, step, mapping=None):
        schema = utils.build_resolved_schema(step, mapping or rdb_schema.get_attribute_catalog(step["domain"]), [])
        return catalog_sql.compile_select(schema, snapshot=snapshot(), metadata={})

    def test_english_source_category_uses_ontology_not_llm_translation(self):
        result = self.compile({"domain": "해외ETF", "conditions": [
            {"attribute": "투자자산유형", "operator": "eq", "value": "주식"},
            {"attribute": "투자지역", "operator": "eq", "value": "미국"}]})
        self.assertIn("base.wu_inv_ast_type IN (E'Equity')", result["sql"])
        self.assertIn("United States of America", result["sql"])

    def test_passive_strategy_is_or_not_impossible_and(self):
        result = self.compile({"domain": "국내ETF", "subtype": ["패시브"]})
        self.assertIn(" OR ", result["sql"])
        self.assertIn("실물복제", result["sql"])
        self.assertIn("합성복제", result["sql"])
        self.assertNotIn("액티브", result["sql"])

    def test_asset_subtype_is_source_backed(self):
        sql = self.compile({"domain": "해외ETF", "subtype": ["채권형"]})["sql"]
        self.assertIn("base.wu_inv_ast_type::text = E'Bond'", sql)

    def test_negative_suspension_uses_known_zero_not_arbitrary_not_one(self):
        spec = rdb_schema.AttributeSpec(column="pd_tr_yn", value_type="numeric")
        result = self.compile({"domain": "국내ETF", "conditions": [
            {"attribute": "거래정지여부", "operator": "eq", "value": "거래정지 아님"}]},
            {**rdb_schema.get_attribute_catalog("국내ETF"), "거래정지여부": spec})
        self.assertIn("END) = 0", result["sql"])
        self.assertNotIn("<> 1", result["sql"])
        self.assertTrue(any(b["key"] == "pd_tr_yn" for b in result["output_fields"]))

    def test_pension_boolean_uses_yn_contract(self):
        sql = self.compile({"domain": "국내ETF", "conditions": [
            {"attribute": "연금거래가능여부", "operator": "eq", "value": "true"}]})["sql"]
        self.assertIn("BTRIM(base.pd_pen_tr_yn::text) = E'Y'", sql)

    def test_usd_threshold_also_requires_verified_currency(self):
        result = self.compile({"domain": "해외ETF", "conditions": [
            {"attribute": "AUM", "operator": "gte", "value": "1천억 달러"}]})
        self.assertIn("100000000000", result["sql"])
        self.assertIn("base.pd_trd_ccy = E'USD'", result["sql"])
        self.assertTrue(any(b["attribute"] == "AUM통화" for b in result["output_fields"]))
        self.assertEqual(catalog_sql.numeric_value("5천억원", "pd_net_tamt", "국내ETF"), "500000000000")

    def test_incompatible_currency_is_not_implicitly_converted(self):
        with self.assertRaises(catalog_sql.CompileError):
            catalog_sql.numeric_value("100억 원", "du_last_aum", "해외ETF")


if __name__ == "__main__":
    unittest.main()
