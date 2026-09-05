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
    def test_region_is_exposure_only_for_explicit_asset_phrase(self):
        intent = {"product_domain": [{"domain": "해외ETF", "subtype": ["주식형"]}], "conditions": []}
        fixed, notes = utils.preserve_explicit_investment_region(intent, "미국 주식형 ETF 중 보수 낮은 상품")
        self.assertEqual(fixed["conditions"][0]["value"], "미국")
        self.assertTrue(notes)
        unchanged, notes = utils.preserve_explicit_investment_region(intent, "미국 상장 ETF의 보수")
        self.assertEqual(unchanged["conditions"], [])
        self.assertFalse(notes)
        intent["target_entities"] = [{"entity_type": "product_name", "surface_form": "미국 주식 펀드"}]
        self.assertFalse(utils.preserve_explicit_investment_region(intent, "미국 주식 펀드의 보수")[1])

    def test_listing_never_uses_sale_status(self):
        view = rdb_schema.get_output_view("펀드", "상장 여부")
        row = utils.derive_output_views([{"sale_yn": "판매중"}], [{"attribute": "상장 여부", **view}])[0]
        field = row["_derived_fields"]["상장여부"]
        self.assertEqual(field["status"], "derivation_unavailable")
        self.assertIn("판매 상태", field["detail"])
        view = rdb_schema.get_output_view("국내ETF", "상장 여부")
        row = utils.derive_output_views([{"pd_lstg_dt": "20200101", "pd_lste_dt": "99991231", "cu_upt_dt": "20260824"}], [{"attribute": "상장 여부", **view}])[0]
        self.assertEqual(row["_derived_fields"]["상장여부"]["value"], "상장기간 내")

    def test_unqualified_return_has_periods_and_keeps_nulls(self):
        view = rdb_schema.get_output_view("펀드", "수익률")
        row = utils.derive_output_views([{"fd_mm1_ern_r": 2.3, "fd_yr1_ern_r": None}], [{"attribute": "수익률", **view}])[0]
        self.assertIn("1개월: 2.3%", row["_derived_fields"]["수익률"]["value"])
        self.assertIn("1년: NULL", row["_derived_fields"]["수익률"]["value"])
        self.assertIn("3개월: 미조회", row["_derived_fields"]["수익률"]["value"])

    def test_identity_computed_field_cannot_be_unmapped(self):
        state = {"intent": {"identity_comparison": {"classes": ["A", "B"]},
                            "output_requirements": {"fields": ["클래스 동일성 여부"]}},
                 "step_results": {"r": {"engine": "rdb", "domain": "펀드", "rows": [{"itm_nm": "가상ClassA"}]}}}
        contract = self.nodes._build_rdb_answer_contract(state)
        self.assertFalse(any(i["field"] == "클래스 동일성 여부" for r in contract for i in r["items"]))
        self.assertIn("판정할 수 없습니다", evidence_contract.render_identity_comparison(state))

    def test_identity_only_narrative_does_not_require_llm(self):
        intent = {"product_domain": [{"domain": "국내ETF"}, {"domain": "펀드"}],
                  "target_entities": [{"entity_type": "product_name", "surface_form": "가상200"}],
                  "output_requirements": {"narrative_topics": ["동일 운용상품 여부", "상장 클래스 여부", "운용 위험"]}}
        fixed, _ = evidence_contract.restore_cross_market_identity(intent, "동일 상품인지")
        self.assertEqual(fixed["output_requirements"]["narrative_topics"], ["운용 위험"])

    def test_won_currency_uses_source_code(self):
        self.assertEqual(utils.categorical_source_values("채권", "curr_cd", "원화"), ["KRW"])
        records, _ = utils.resolve_subtype_conditions("채권", ["원화채권"])
        self.assertEqual(records[0]["column"], "curr_cd")

    def test_money_unit_requires_a_number(self):
        with self.assertRaises(catalog_sql.CompileError):
            catalog_sql.numeric_value("원", "du_last_aum", "국내ETF")
        self.assertEqual(catalog_sql.numeric_value("천억원", "du_last_aum", "국내ETF"), "100000000000")

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

    def test_class_suffix_is_an_and_constraint_not_global_product_or(self):
        step = {"domain": "펀드", "fields": ["상품명"], "class_suffixes": ["A-X", "C-Ye"],
                "product_name_entities": [{"surface_form": "가상글로벌펀드"}]}
        schema = utils.build_resolved_schema(step, rdb_schema.get_attribute_catalog("펀드"), [])
        sql = catalog_sql.compile_select(schema, snapshot=snapshot(), metadata={})["sql"]
        self.assertIn("가상글로벌펀드", sql)
        self.assertIn("base.itm_nm ~*", sql)
        self.assertIn("C\\-Ye$", sql.replace("\\\\", "\\"))

    def test_union_top_rows_retain_requested_fields_without_reranking(self):
        steps = [{"step_id": "e", "domain": "국내ETF", "fields": ["1년수익률"], "conditions": [],
                  "sort": {"attribute": "순자산", "order": "desc", "limit": "2"}},
                 {"step_id": "f", "domain": "펀드", "fields": ["1년수익률"], "conditions": [],
                  "sort": {"attribute": "순자산", "order": "desc", "limit": "2"}}]
        etf_return = rdb_schema.get_attribute_catalog("국내ETF")["1년수익률"].column
        fund_return = rdb_schema.get_attribute_catalog("펀드")["1년수익률"].column
        source_rows = [[{"code": "E", "name": "ETF", "domain": "국내ETF", "sort_value": 200},
                        {"code": "F", "name": "펀드", "domain": "펀드", "sort_value": 100}],
                       [{"pd_itm_no": "E", "pd_nm": "ETF", etf_return: "12.5"}],
                       [{"itm_no": "F", "itm_nm": "펀드", fund_return: None}]]
        with patch.object(schema_snapshot, "get_snapshot", return_value=snapshot()), \
             patch.object(catalog_sql, "domain_metadata", return_value={}), \
             patch.object(utils, "run_sql", side_effect=source_rows) as run:
            results = self.nodes._execute_merged_target_group(steps, "상위 상품 수익률", Mock(), {"order": "desc"}, "2", 1)
        rows = results["e"]["rows"]
        self.assertEqual([r["code"] for r in rows], ["E", "F"])
        self.assertEqual([r["sort_value"] for r in rows], [200, 100])
        self.assertEqual(rows[0][etf_return], "12.5")
        self.assertIsNone(rows[1][fund_return])
        self.assertEqual(run.call_count, 3)
        self.assertEqual(len(results["e"]["hydration_queries"]), 2)


if __name__ == "__main__":
    unittest.main()
