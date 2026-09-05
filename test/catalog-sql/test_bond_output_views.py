"""Request preservation + raw/TBox output views; no database/LLM network calls."""
import copy
import json
import os
import unittest
from unittest.mock import Mock, patch

from test_catalog_sql import snapshot
from agent import utils
from tools import catalog_sql, graph_schema, rdb_schema, schema_snapshot


QUESTION = "현대해상화재보험7(후)(콜/후)의 채권 종류, 발행사, 신용등급, 만기구분, 듀레이션을 알려줘. 원본 등급값과 온톨로지 분류값을 함께 제시해줘."
ROW = {"pd_nm": "현대해상화재보험7(후)(콜/후)", "pd_no": "KR6001451F34",
       "bd_knd": "보험회사채", "pd_pbcm": "현대해상화재보험(주)", "crd_grd": "AA0",
       "dur": 4.3459, "mat_dt": "20350327", "info_base_dt": "20260821"}


def initial_intent():
    return {"raw_question": QUESTION, "task": "lookup", "product_domain": [{"domain": "채권", "subtype": []}],
            "target_entities": [{"surface_form": ROW["pd_nm"], "entity_type": "product_name"}],
            "conditions": [], "relations": [], "sort": {}, "answer_format": "list",
            "output_requirements": {"fields": ["채권 종류", "발행사", "신용등급", "만기구분", "듀레이션"],
                                    "narrative_topics": []}}


class BondOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "offline-test-key"}):
            from agent import nodes
            from agent.plan_query_db import plan_query_node
        cls.nodes, cls.plan_query = nodes, staticmethod(plan_query_node)

    def setUp(self):
        for target, name, value in [(schema_snapshot, "get_snapshot", snapshot()),
                                    (catalog_sql, "domain_metadata", {})]:
            p = patch.object(target, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        self.llm_patch = patch.object(self.nodes, "_llm_answer")
        self.answer_llm = self.llm_patch.start()
        self.answer_llm.with_structured_output.side_effect = AssertionError("No answer LLM expected")
        self.addCleanup(self.llm_patch.stop)

    def repaired(self):
        return utils.preserve_explicit_output_requests(initial_intent(), QUESTION)[0]

    def resolved(self, fields):
        step = {"domain": "채권", "fields": fields, "conditions": [], "role": "target"}
        return utils.build_resolved_schema(step, rdb_schema.get_attribute_catalog("채권"), [])

    def derived(self, row, fields=None):
        spec = self.resolved(fields or ["만기구분", "신용등급", "온톨로지분류값", "원본등급값"])
        return utils.derive_output_views([row], spec["output_views"])[0]["_derived_fields"]

    def test_second_sentence_requests_restored(self):
        fields = self.repaired()["output_requirements"]["fields"]
        self.assertIn("원본등급값", fields)
        self.assertIn("온톨로지분류값", fields)
        self.assertIn("만기구분", fields)

    def test_repair_is_nonmutating_and_idempotent(self):
        original = initial_intent()
        before = copy.deepcopy(original)
        repaired, _ = utils.preserve_explicit_output_requests(original, QUESTION)
        repeated, notes = utils.preserve_explicit_output_requests(repaired, QUESTION)
        self.assertEqual(original, before)
        self.assertEqual(repaired, repeated)
        self.assertEqual(notes, [])

    def test_condition_mention_is_not_an_output_request(self):
        intent = initial_intent()
        intent["output_requirements"]["fields"] = ["상품명"]
        result, _ = utils.preserve_explicit_output_requests(intent, "신용등급 AA 이상인 채권의 상품명을 알려줘")
        self.assertNotIn("신용등급", result["output_requirements"]["fields"])

    def test_negative_request_not_added(self):
        result, _ = utils.preserve_explicit_output_requests(initial_intent(), "원본 등급값은 제외하고 발행사만 알려줘")
        self.assertNotIn("원본등급값", result["output_requirements"]["fields"])

    def test_separate_negative_line_does_not_hide_positive_request(self):
        result, _ = utils.preserve_explicit_output_requests(
            initial_intent(), "온톨로지 분류값은 제외해줘\n원본 등급값을 보여줘")
        self.assertIn("원본등급값", result["output_requirements"]["fields"])
        self.assertNotIn("온톨로지분류값", result["output_requirements"]["fields"])

    def test_product_surface_is_masked_even_when_spacing_differs(self):
        intent = initial_intent()
        intent["target_entities"] = [{"surface_form": "원본 등급값", "entity_type": "product_name"}]
        result, _ = utils.preserve_explicit_output_requests(intent, "원본등급값을 보여줘")
        self.assertNotIn("원본등급값", result["output_requirements"]["fields"])

    def test_unseen_request_alias(self):
        result, _ = utils.preserve_explicit_output_requests(initial_intent(), "원시 등급값과 정규화 신용등급을 각각 표시해줘")
        self.assertIn("원시등급값", result["output_requirements"]["fields"])
        self.assertIn("정규화신용등급", result["output_requirements"]["fields"])

    def test_analyze_and_verify_both_restore_model_omissions(self):
        with patch.object(self.nodes, "_llm_plan") as llm:
            llm.with_structured_output.return_value.invoke.side_effect = [initial_intent(), initial_intent()]
            state = {"question": QUESTION}
            state.update(self.nodes.analyze_intent_node(state))
            self.assertIn("원본등급값", state["intent"]["output_requirements"]["fields"])
            state.update(self.nodes.verify_intent_node(state))
            self.assertIn("온톨로지분류값", state["intent"]["output_requirements"]["fields"])
            self.assertEqual(llm.with_structured_output.return_value.invoke.call_count, 2)

    def test_plan_to_sql_to_answer_integration(self):
        state = {"question": QUESTION, "question_id": "different-id", "intent": self.repaired()}
        state.update(self.plan_query(state))
        self.assertFalse(state["route"]["needs_graph"])
        step = next(p for p in state["plan"] if p["engine"] == "rdb")
        with patch.object(utils, "run_sql", return_value=[dict(ROW)]) as runner:
            result = self.nodes._execute_target_step(step, QUESTION, Mock(), True, 1)
        runner.assert_called_once()
        for col in ["mat_dt", "info_base_dt", "crd_grd"]:
            self.assertIn(f"base.{col} AS {col}", result["sql"])
        self.assertNotIn("base.만기구분", result["sql"])
        state["step_results"] = {step["step_id"]: result}
        state.update(self.nodes.merge_results_node(state))
        response = json.loads(self.nodes.generate_answer_node(state)["answer"])
        answer = response["answer"]
        for token in ["원본등급값: AA0", "만기구분: 장기", "5-10년", "3140일", "20350327", "20260821", "Rating_AA", "4.3459"]:
            self.assertIn(token, answer)
        self.assertIn("원격 GraphDB 조회 아님", response["retrieved_context"])
        self.answer_llm.with_structured_output.assert_not_called()

    def test_maturity_boundaries(self):
        for days, bucket in [(-1, "만기경과"), (0, "1년미만"), (364, "1년미만"),
                             (365, "1-3년"), (1094, "1-3년"), (1095, "3-5년"),
                             (1824, "3-5년"), (1825, "5-10년"), (3649, "5-10년"), (3650, "10년이상")]:
            with self.subTest(days=days):
                _, actual = utils._maturity_class(days)
                self.assertEqual(actual, bucket)

    def test_maturity_uses_source_dates_not_clock_raw_days_or_duration(self):
        row = {**ROW, "remaining_days": 1, "dur": 0.1}
        item = self.derived(row)["만기구분"]
        self.assertIn("장기", item["value"])
        self.assertIn("3140일", item["detail"])
        self.assertEqual(ROW["crd_grd"], "AA0")

    def test_valid_date_surface_forms(self):
        row = {**ROW, "mat_dt": "20350327.0", "info_base_dt": "2026-08-21"}
        self.assertIn("3140일", self.derived(row)["만기구분"]["detail"])

    def test_missing_null_blank_and_invalid_dates(self):
        for value, status in [(None, "null"), ("", "empty"), ("0", "derivation_unavailable"),
                              ("99991231", "derivation_unavailable"), ("20260230", "derivation_unavailable")]:
            with self.subTest(value=value):
                row = {**ROW, "mat_dt": value}
                items = self.derived(row)
                self.assertEqual(items["만기구분"]["status"], status)
                self.assertEqual(items["온톨로지분류값"]["status"], "available")
        row = dict(ROW)
        del row["info_base_dt"]
        self.assertEqual(self.derived(row)["만기구분"]["status"], "not_selected")

    def test_rating_aliases_come_from_tbox(self):
        for entry in utils._ontology_labels("CreditRating"):
            for alias in entry["aliases"]:
                actual = utils._ontology_match("CreditRating", alias)
                self.assertEqual(actual["uri"], entry["uri"])
        self.assertEqual(utils._ontology_match("CreditRating", "AA0")["label"], "AA")
        self.assertEqual(utils._ontology_match("CreditRating", "BBB0")["label"], "BBB")

    def test_unknown_rating_is_not_guessed(self):
        items = self.derived({**ROW, "crd_grd": "AAAA"})
        self.assertEqual(items["온톨로지분류값"]["status"], "derivation_unavailable")
        self.assertEqual(items["만기구분"]["status"], "available")

    def test_unavailable_tbox_does_not_erase_raw_rows(self):
        with patch.object(graph_schema, "catalog", side_effect=OSError("missing ontology")):
            items = self.derived(ROW)
        self.assertTrue(all(i["status"] == "derivation_unavailable" for i in items.values()))
        self.assertEqual(ROW["crd_grd"], "AA0")

    def test_generic_classification_requires_an_axis(self):
        item = self.derived(ROW, ["온톨로지분류값"])["온톨로지분류값"]
        self.assertEqual(item["status"], "derivation_unavailable")
        item = self.derived(ROW, ["만기구분", "온톨로지분류값"])["온톨로지분류값"]
        self.assertIn("Maturity_LongTerm", item["value"])

    def test_raw_rating_alias_does_not_normalize(self):
        spec = self.resolved(["원본등급값"])
        self.assertEqual(spec["output_views"], [])
        self.assertEqual(next(f for f in spec["fields"] if f["attribute"] == "원본등급값")["column"], "crd_grd")

    def test_output_views_cannot_be_silently_used_as_filters(self):
        for step in [{"conditions": [{"attribute": "만기구분", "operator": "eq", "value": "장기"}]},
                     {"sort": {"attribute": "만기구분", "order": "asc"}}]:
            spec = utils.build_resolved_schema({"domain": "채권", **step}, rdb_schema.get_attribute_catalog("채권"), [])
            with self.assertRaises(catalog_sql.CompileError):
                catalog_sql.compile_select(spec, snapshot=snapshot(), metadata={})

    def test_no_cross_row_classification_or_mutation(self):
        rows = [dict(ROW), {**ROW, "pd_no": "ANOTHER-BOND", "crd_grd": "BBB0", "mat_dt": "20260822"}]
        before = copy.deepcopy(rows)
        result = utils.derive_output_views(rows, self.resolved(["만기구분", "원본등급값", "온톨로지분류값"])["output_views"])
        self.assertIn("Rating_AA)", result[0]["_derived_fields"]["온톨로지분류값"]["value"])
        self.assertIn("Rating_BBB)", result[1]["_derived_fields"]["온톨로지분류값"]["value"])
        self.assertIn("단기", result[1]["_derived_fields"]["만기구분"]["value"])
        self.assertEqual(rows, before)


if __name__ == "__main__":
    unittest.main()
