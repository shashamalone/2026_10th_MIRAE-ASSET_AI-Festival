"""Scope, relation and identity regressions using unseen names and mocked I/O."""
from datetime import date
import json
import os
import unittest
from unittest.mock import Mock, patch

from test_catalog_sql import snapshot, resolved
from agent import evidence_contract, utils
from tools import catalog_sql, rdb_schema, schema_snapshot


class SemanticPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "offline-test-key"}):
            from agent import nodes, plan_query_db
            from agent.graph_logic import graph_orchestrator
        cls.nodes, cls.planner, cls.graph = nodes, plan_query_db, graph_orchestrator

    def test_unbound_theme_does_not_become_all_products(self):
        state = {"question": "임의 모델과 관련 상품을 알려줘", "intent": {
            "task": "lookup", "product_domain": [{"domain": "펀드", "subtype": []}],
            "target_entities": [{"surface_form": "임의 모델", "entity_type": "theme"}],
            "conditions": [], "relations": [], "output_requirements": {"fields": ["순자산"]}}}
        result = self.planner.plan_query_node(state)
        self.assertEqual(result["plan"], [])
        self.assertIn("어떤 관계", result["route"]["blocking_reasons"][0])

    def test_future_calendar_return_is_not_rolling_return(self):
        reasons = evidence_contract.request_blockers({}, "가상 ETF의 2032년 확정 연간수익률", today=date(2031, 9, 1))
        self.assertIn("2032년", reasons[0])
        self.assertFalse(evidence_contract.request_blockers({}, "가상 ETF의 2030년 확정 연간수익률", today=date(2031, 9, 1)))

    def test_policy_structure_routes_to_official_document_subject(self):
        question = "가상성장기금의 구조, 운용주체, 자금조달 방식을 공식 정책자료로 알려줘"
        intent = {"product_domain": [{"domain": "펀드", "subtype": []}], "target_entities": [],
                  "output_requirements": {"fields": ["구조"]}}
        result = self.planner.plan_query_node({"intent": intent, "question": question})
        self.assertFalse(result["route"]["needs_rdb"])
        self.assertEqual(result["plan"][0]["subject_terms"], ["가상성장기금"])
        self.assertEqual(result["plan"][0]["depends_on"], [])

    def test_explicit_classes_are_scoped_to_parent_name(self):
        question = "가상글로벌펀드의 A-X와 C-Ye 클래스가 동일 모펀드인지 비교해줘"
        intent, _ = evidence_contract.restore_class_comparison({"relations": [], "conditions": []}, question)
        self.assertEqual(intent["target_entities"][0]["surface_form"], "가상글로벌펀드")
        plan = self.planner.plan_query_node({"intent": intent, "question": question})["plan"]
        rdb = next(s for s in plan if s["engine"] == "rdb")
        self.assertEqual(rdb["class_suffixes"], ["A-X", "C-Ye"])
        self.assertFalse(any(s["engine"] == "graph" for s in plan))

    def test_same_parent_needs_manager_and_parent_keys_not_name(self):
        request = {"classes": ["A-X", "C-Ye"]}
        rows = [{"itm_nm": "가상펀드Class" + c, "itm_no": str(i), "or_co_xtn_itt_cd": "MGR",
                 "mtco_itm_no": "PARENT", "rptt_ksd_itm_no": "REP"} for i, c in enumerate(request["classes"])]
        state = {"intent": {"identity_comparison": request}, "step_results": {
            "r": {"engine": "rdb", "domain": "펀드", "rows": rows}}}
        self.assertIn("동일 모펀드의 클래스 그룹", evidence_contract.render_identity_comparison(state))
        rows[1]["or_co_xtn_itt_cd"] = "ANOTHER-MGR"
        self.assertNotIn("그룹으로 확인", evidence_contract.render_identity_comparison(state))
        rows[1]["or_co_xtn_itt_cd"] = None
        self.assertIn("미확보", evidence_contract.render_identity_comparison(state))

    def test_cross_market_identity_uses_ksd_code_not_name(self):
        state = {"intent": {"identity_comparison": {"mode": "cross_market"}}, "step_results": {
            "f": {"engine": "rdb", "domain": "펀드", "rows": [{"itm_no": "F1", "ksd_itm_no": "E1"}]},
            "e": {"engine": "rdb", "domain": "국내ETF", "rows": [{"pd_itm_no": "E1"}]}}}
        self.assertIn("F1 ↔ ETF E1", evidence_contract.render_identity_comparison(state))
        state["step_results"]["f"]["rows"][0]["ksd_itm_no"] = None
        self.assertIn("확정하지 않습니다", evidence_contract.render_identity_comparison(state))

    def test_independent_graph_conditions_are_intersection(self):
        results = {"g1": {"engine": "graph", "status": "ok", "entity_codes": ["A", "B"]},
                   "g2": {"engine": "graph", "status": "ok", "entity_codes": ["B", "C"]}}
        step = {"domain": "국내ETF", "depends_on": ["g1", "g2"]}
        changed = self.nodes._apply_graph_handoff(step, results)
        self.assertEqual(changed["conditions"][-1]["value"], "B")
        results["g2"]["entity_codes"] = ["C"]
        self.assertIn("교집합", self.nodes._apply_graph_handoff(step, results)["graph_handoff_blocked"])

    def test_unrelated_question_clause_cannot_change_graph_step_path(self):
        relation = {"id": "r", "subject_domain": "국내ETF", "relation": "holds", "object_entity": "가상회사", "entity_role": "company"}
        frame = self.nodes._build_graph_frame(relation, {"r": relation})
        plan, _ = self.graph._fast_plan("별도 질문에는 자회사라는 단어가 있다", frame)
        predicates = [e["predicate"] for e in plan["edges"]]
        self.assertIn("fp:hasHolding", predicates)
        self.assertNotIn("fp:hasSubsidiary", predicates)

    def test_security_seed_does_not_require_nonexistent_company(self):
        frame = {"relation_scope": True, "relations": [{"relation": "holds", "subject_domain": "국내ETF"}]}
        plan, _ = self.graph._fast_plan("", frame, "Security")
        self.assertEqual(next(n for n in plan["nodes"] if n["id"] == "seed")["class_uri"], "fp:Security")
        self.assertNotIn("fp:issuedByCompany", [e["predicate"] for e in plan["edges"]])

    def test_company_and_security_codes_do_not_leak_into_product_handoff(self):
        plan = {"outputs": [{"property": "fp:productCode", "alias": "product"},
                            {"property": "fp:corpCode", "alias": "company_code"},
                            {"property": "fp:securityCode", "alias": "security_code"}]}
        self.assertEqual(self.graph._extract_entity_codes(plan, [{"product": "P", "company_code": "C", "security_code": "S"}]), ["P"])

    def test_source_product_is_not_accepted_as_issuer(self):
        intent = {"product_domain": [{"domain": "채권"}], "target_entities": [{"entity_type": "company", "surface_form": "XYZ"}]}
        with patch.object(utils, "lookup_product_identities", return_value=[{"query_name": "XYZ", "domain": "해외ETF", "name": "가상 ETF", "code": "XYZ"}]), \
             patch.object(utils, "get_pg_connection", return_value=Mock()), patch.object(utils, "run_sql", return_value=[]):
            fixed, notes = utils.validate_issuer_subjects(intent, "XYZ가 발행한 채권")
        self.assertIn("발행사로는 확인되지", fixed["issuer_type_conflict"])
        self.assertTrue(notes)

    def test_named_product_does_not_add_inferred_class_filter(self):
        intent = {"target_entities": [{"entity_type": "product_name", "surface_form": "가상 ETF"}],
                  "product_domain": [{"domain": "국내ETF", "subtype": ["인덱스", "주식형"]}]}
        fixed, notes = utils.prune_inferred_named_subtypes(intent, "가상 ETF의 투자자산유형을 알려줘")
        self.assertEqual(fixed["product_domain"][0]["subtype"], [])


if __name__ == "__main__":
    unittest.main()
