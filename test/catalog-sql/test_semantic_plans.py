"""Scope, relation and identity regressions using unseen names and mocked I/O."""
from datetime import date
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_catalog_sql import snapshot, resolved
from agent import evidence_contract, utils
from tools import catalog_sql, rdb_schema, schema_snapshot


class SemanticPlanTests(unittest.TestCase):
    def test_relative_event_dates_use_execution_date_not_invented_year(self):
        intent = {"conditions": [{"attribute": "사건일", "operator": "gte", "value": "2023-01-01"}]}
        fixed, _ = evidence_contract.restore_relative_event_window(intent, "최근 6개월 연결 이력", today=date(2026, 9, 5))
        self.assertEqual((fixed["conditions"][0]["value"], fixed["conditions"][0]["value_2"]), ("2026-03-05", "2026-09-05"))
        fixed, _ = evidence_contract.restore_relative_event_window(intent, "최근 1개월 사건", today=date(2024, 3, 31))
        self.assertEqual(fixed["conditions"][0]["value"], "2024-02-29")
        self.assertFalse(evidence_contract.restore_relative_event_window(intent, "2025-01-01 기준 최근 6개월 사건")[1])
        self.assertFalse(evidence_contract.restore_relative_event_window(intent, "최근 6개월 수익률")[1])

    def test_explicit_parent_children_union_keeps_other_constraints(self):
        intent = {"product_domain": [{"domain": "국내ETF"}], "output_requirements": {"fields": ["상품명", "편입비중"]}, "relations": [
            {"id": "P", "subject_domain": "Company", "relation": "subsidiary_of", "object_entity": "예시전자"},
            {"id": "A", "subject_domain": "ETF", "relation": "holds", "object_entity": "예시전자"},
            {"id": "B", "subject_domain": "ETF", "relation": "holds", "object_ref": "P"}]}
        planned = self.planner.plan_query_node({"intent": intent, "question": "예시전자 및 확인된 자회사를 편입한 ETF"})
        step = next(p for p in planned["plan"] if p["engine"] == "rdb")
        self.assertEqual(step["graph_any_groups"], [["graph_A", "graph_B"]])
        results = {"graph_A": {"engine": "graph", "status": "ok", "entity_codes": ["A"]},
                   "graph_B": {"engine": "graph", "status": "ok", "entity_codes": ["B"]}}
        changed = self.nodes._apply_graph_handoff(step, results)
        self.assertEqual(changed["conditions"][-1]["value"], "A, B")
        step["depends_on"].append("other")
        results["other"] = {"engine": "graph", "status": "ok", "entity_codes": ["B"]}
        self.assertEqual(self.nodes._apply_graph_handoff(step, results)["conditions"][-1]["value"], "B")

    def test_issuer_handoff_uses_names_not_company_codes_as_isins(self):
        step = self.nodes._apply_graph_handoff({"domain": "채권", "depends_on": ["g"]}, {
            "g": {"engine": "graph", "status": "ok", "handoff_kind": "issuer_names", "issuer_names": ["예시전자", "예시소재"]}})
        conditions = utils.build_condition_list(step)
        self.assertEqual({c["attribute"] for c in conditions}, {"발행사"})
        self.assertEqual({c["any_group"] for c in conditions}, {"graph_issuer_names"})

    def test_organization_equality_normalizes_legal_designator_only(self):
        schema = resolved("채권", conditions=[{"attribute": "발행사", "operator": "eq", "value": "예시회사", "value_2": ""}])
        sql = catalog_sql.compile_select(schema, snapshot=snapshot(), metadata={})["sql"]
        self.assertIn("(주)", sql)
        self.assertIn("주식회사", sql)
        self.assertNotIn("POSITION", sql)

    def test_compound_output_fields_are_split_only_if_catalogued(self):
        fixed, _ = utils.preserve_explicit_output_requests({"product_domain": [{"domain": "채권"}, {"domain": "국내ETF"}],
            "output_requirements": {"fields": ["채권 신용등급·만기", "ETF 편입비중", "위험 문서 근거"]}}, "신용등급·만기와 ETF 편입비중을 제시")
        self.assertTrue({"신용등급", "만기", "편입비중", "위험 문서 근거"} <= set(fixed["output_requirements"]["fields"]))

    def test_blank_subtype_is_not_a_filter(self):
        from agent.intent_guard import guard_intent
        fixed, _ = guard_intent({"product_domain": [{"domain": "국내ETF", "subtype": ["", " "]}]})
        self.assertEqual(fixed["product_domain"][0]["subtype"], [])
        self.assertEqual(utils.resolve_subtype_conditions("국내ETF", [""])[0], [])

    def test_company_issuer_and_holding_paths_keep_separate_scopes(self):
        from agent.intent_guard import guard_intent
        intent = {"product_domain": [{"domain": d} for d in ("채권", "국내ETF", "펀드")],
                  "target_entities": [{"entity_type": "company", "surface_form": "예시전자"}],
                  "conditions": [{"domain": "국내ETF", "attribute": "편입 여부", "operator": "eq", "value": "true"},
                                 {"domain": "채권", "attribute": "매수 가능 여부", "operator": "eq", "value": "true"}],
                  "relations": [{"id": "R1", "relation": "발행", "subject_domain": "Company", "object_entity": "예시전자", "path": ["발행사", "채권"]},
                                {"id": "R2", "relation": "편입", "subject_domain": "Company", "object_entity": "예시전자", "path": ["기업", "편입증권", "상품"], "entity_role": "product"}]}
        fixed, _ = guard_intent(intent)
        self.assertEqual({r["subject_domain"] for r in fixed["relations"]}, {"국내ETF", "펀드"})
        self.assertTrue(all(r["relation"] == "holds" and r["entity_role"] == "company" for r in fixed["relations"]))
        self.assertEqual({c["attribute"] for c in fixed["conditions"]}, {"발행사", "판매가능여부"})
        plan = self.planner.plan_query_node({"intent": fixed, "question": "회사 발행 채권과 편입 상품"})
        for step in plan["plan"]:
            if step["engine"] == "rdb":
                self.assertEqual(bool(step["depends_on"]), step["domain"] != "채권")
        self.assertEqual(guard_intent(fixed)[0], fixed)

    def test_unbound_or_negative_holding_flag_is_not_dropped(self):
        from agent.intent_guard import guard_intent
        for value in ("true", "false"):
            condition = {"domain": "펀드", "attribute": "편입여부", "value": value, "operator": "eq"}
            self.assertEqual(guard_intent({"conditions": [condition]})[0]["conditions"], [condition])

    def test_fund_holdings_use_publicfund_not_etf(self):
        plan, _ = self.graph._fast_plan("회사 편입 펀드", {"relation_scope": True, "relations": [{"relation": "holds", "subject_domain": "펀드"}]})
        self.assertTrue(any(n["class_uri"] == "fp:PublicFund" for n in plan["nodes"]))
        self.assertFalse(any(n["class_uri"] == "fp:ETF" for n in plan["nodes"]))

    def test_shared_topic_cannot_leave_fund_branch_unfiltered(self):
        intent = {"product_domain": [{"domain": "국내ETF", "subtype": ["바이오"]}, {"domain": "펀드", "subtype": ["공모펀드"]}]}
        with patch.object(utils, "_ontology_labels", side_effect=lambda axis: [{"label": "국내", "aliases": {"국내"}}] if axis == "InvestmentRegion" else [{"label": "글로벌바이오", "aliases": {"글로벌바이오"}}]):
            fixed, _ = utils.restore_shared_theme_scope(intent, "국내 바이오에 투자하는 ETF와 공모펀드를 통합 검색")
        self.assertEqual({r["subject_domain"] for r in fixed["relations"]}, {"국내ETF", "펀드"})
        planned = self.planner.plan_query_node({"intent": fixed, "question": "통합 검색"})
        self.assertTrue(all(p["depends_on"] for p in planned["plan"] if p["engine"] == "rdb"))

    def test_graph_weight_is_matched_by_product_code_not_row_order(self):
        plan = {"nodes": [{"id": "h", "class_uri": "fp:Holding"}], "outputs": [
            {"alias": "code", "property": "fp:productCode"}, {"alias": "weight", "property": "fp:weight"}]}
        results = {"g": {"engine": "graph", "status": "ok", "graph_plan": plan,
                         "rows": [{"code": "A", "weight": 3.2, "h_as_of": "2026-07-10", "h_source": "SRC"},
                                  {"code": "B", "weight": 8.1, "h_as_of": "2026-07-10", "h_source": "SRC"}]}}
        item = evidence_contract.graph_field_evidence("편입비중", "B", results)
        self.assertEqual(item["value"][0]["weight"], 8.1)
        self.assertIsNone(evidence_contract.graph_field_evidence("편입비중", "C", results))

    def test_graph_source_records_do_not_require_nonexistent_documents(self):
        from types import SimpleNamespace
        compiled = SimpleNamespace(evidence_columns=("h_as_of", "h_source", "h_document", "h_document_title"), tbox_provenance=())
        evidence, reason = self.graph.resolve_evidence([{"h_as_of": "2026-07-10", "h_source": "SourceFile"}], compiled)
        self.assertFalse(reason)
        self.assertEqual(evidence[0]["document_status"], "metadata_missing")
        self.assertEqual(evidence[0]["kind"], "source_record")
        self.assertTrue(self.graph.resolve_evidence([{"h_as_of": "2026-07-10"}], compiled)[1])
        self.assertTrue(self.graph.resolve_evidence([{"h_as_of": "2026-07-10", "h_source": ""}], compiled)[1])

    def test_capped_graph_candidates_cannot_be_global_top_rank(self):
        step = {"depends_on": ["g"], "sort": {"attribute": "AUM"}}
        results = {"g": {"engine": "graph", "status": "ok", "entity_codes": ["X"], "coverage_truncated": True}}
        self.assertIn("전체 후보", self.nodes._apply_graph_handoff(step, results)["graph_handoff_blocked"])

    def test_overseas_exposure_does_not_exclude_domestic_listing(self):
        intent = {"product_domain": [{"domain": "해외ETF", "subtype": ["패시브"]}], "conditions": [], "sort": {"domains": ["해외ETF"]}}
        fixed, _ = utils.preserve_overseas_exposure_scope(intent, "해외주식에 투자하는 ETF 중 순자산 2조원")
        self.assertEqual({d["domain"] for d in fixed["product_domain"]}, {"국내ETF", "해외ETF"})
        self.assertTrue(any(c["attribute"] == "투자자산유형" and c["value"] == "주식" for c in fixed["conditions"]))
        self.assertFalse(utils.preserve_overseas_exposure_scope(intent, "해외주식에 투자하는 해외 상장 ETF")[1])

    def test_broad_overseas_is_not_a_literal_country(self):
        intent = {"product_domain": [{"domain": "해외ETF"}], "conditions": []}
        fixed, notes = utils.preserve_explicit_investment_region(intent, "해외 채권 ETF")
        self.assertFalse(notes)
        records, _ = utils.resolve_subtype_conditions("해외ETF", ["채권 ETF"])
        self.assertTrue(all(r["valid"] for r in records))
        self.assertEqual(records[0]["column"], "wu_inv_ast_type")

    def test_unrequested_top_one_is_removed_not_confused_with_months(self):
        intent = {"sort": {"attribute": "순자산", "limit": "1"}}
        fixed, _ = evidence_contract.restore_explicit_comparators(intent, "6개월 수익률을 비교해줘")
        self.assertEqual(fixed["sort"]["limit"], "")
        fixed, _ = evidence_contract.restore_explicit_comparators(intent, "상위 1개를 비교해줘")
        self.assertEqual(fixed["sort"]["limit"], "1")

    def test_strict_comparators_are_preserved_from_user_words(self):
        intent = {"conditions": [{"attribute": "수량", "value": "0", "operator": "gte"}]}
        fixed, _ = evidence_contract.restore_explicit_comparators(intent, "수량이 0보다 큰 상품")
        self.assertEqual(fixed["conditions"][0]["operator"], "gt")
        fixed, _ = evidence_contract.restore_explicit_comparators(intent, "수량이 0 이상인 상품")
        self.assertEqual(fixed["conditions"][0]["operator"], "gte")
        from agent.intent_guard import _fix_condition
        self.assertEqual(_fix_condition({"operator": ">"})[0]["operator"], "gt")

    def test_return_display_matches_explicit_ranking_measure(self):
        intent = {"sort": {"attribute": "매수수익률"}, "output_requirements": {"fields": ["수익률"]}}
        fixed, _ = evidence_contract.restore_explicit_comparators(intent, "매수수익률 순으로 수익률 보여줘")
        self.assertEqual(fixed["output_requirements"]["fields"], ["매수수익률"])

    def test_boolean_aliases_do_not_require_llm_resolution(self):
        forbidden = Mock()
        forbidden.with_structured_output.side_effect = AssertionError("LLM forbidden")
        mapping, missing = utils.resolve_concepts_for_domain("국내ETF", ["판매 여부", "거래 정지 여부"], "", forbidden)
        self.assertEqual(missing, [])
        self.assertEqual(mapping["거래 정지 여부"].column, "pd_tr_yn")

    def test_identity_plan_has_no_document_search_without_document_topics(self):
        intent = {"identity_comparison": {"classes": ["A", "C"]}, "product_domain": [{"domain": "펀드", "subtype": []}],
                  "output_requirements": {"fields": ["대표종목번호"], "narrative_topics": []}, "answer_format": "list_with_narrative"}
        plan = self.planner.plan_query_node({"intent": intent, "question": "클래스 비교"})
        self.assertFalse(plan["route"]["needs_vector"])

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

    def test_replication_axis_uses_same_raw_strategy_without_guessing(self):
        view = rdb_schema.get_output_view("국내ETF", "복제방식")
        row = utils.derive_output_views([{"cu_strtegy": "실물복제"}], [{"attribute": "복제방식", **view}])[0]
        self.assertIn("Replication_Physical", row["_derived_fields"]["복제방식"]["value"])

    def test_cross_currency_aum_cannot_have_global_rank(self):
        state = {"question": "국내 해외 ETF AUM 비교", "intent": {
            "task": "comparison", "product_domain": [{"domain": d, "subtype": []} for d in ("국내ETF", "해외ETF")],
            "sort": {"attribute": "AUM", "order": "desc", "limit": "5"},
            "output_requirements": {"fields": ["AUM"]}}}
        result = self.planner.plan_query_node(state)
        self.assertFalse(result["route"]["needs_merge_rank"])
        self.assertIn("환율", " ".join(result["route"]["blocking_reasons"]))

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

    def test_reviewed_foreign_security_alias_returns_all_source_identifiers(self):
        from agent.graph_logic.graph_ids import reviewed_holding_security_alias

        aliases = reviewed_holding_security_alias("캠브리콘")
        self.assertEqual(aliases["label_contains"], ("cambricon",))
        self.assertIn("CNE1000041R8", aliases["codes"])
        rows = [
            {"etf_code": "KR1", "etf_name": "첫 ETF", "security_code": "688256 C1 Equity",
             "security_name": "Cambricon Technologies Corp Ltd", "weight": "10.0",
             "holding_as_of": "2026-07-10", "holding_source": "TEST"},
            {"etf_code": "KR2", "etf_name": "둘 ETF", "security_code": "CNE1000041R8",
             "security_name": "CAMBRICON TECHNOLOGIES CORP", "weight": "9.0",
             "holding_as_of": "2026-07-10", "holding_source": "TEST"},
        ]
        with patch.object(self.graph.graph_engine, "sparql", return_value=rows) as query:
            result = self.graph._run_reviewed_holding_alias("캠브리콘")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["entity_codes"], ["KR1", "KR2"])
        self.assertEqual(len(result["evidence"]), 2)
        executed = "\n".join(call.args[0] for call in query.call_args_list)
        self.assertIn("688256", executed)
        self.assertIn("CNE1000041R8", executed)
        self.assertIsNone(self.graph._run_reviewed_holding_alias("등록되지 않은 통칭"))

    def test_compound_theme_is_intersection_of_verified_facets(self):
        def candidates(text, *, partial):
            if text == "중국 반도체":
                return []
            return [{"uri": f"urn:theme:{text}",
                     "class_uri": "http://mafest.ai/product#Theme", "canonical_name": text,
                     "names": (text,), "codes": ()}]

        fragment = Mock()
        fragment.selection_mode = "fixture"
        fragment.classes = ["fp:Theme", "fp:ETF"]
        fragment.properties = ["fp:relatedToTheme"]
        fragment.as_dict.return_value = {"classes": ["fp:Theme", "fp:ETF"]}
        graph_catalog = Mock()
        graph_catalog.select_fragment.return_value = fragment
        compiled = lambda candidate: SimpleNamespace(
            sparql=candidate["canonical_name"], evidence_columns=(),
            tbox_provenance=(("fp:relatedToTheme", "relations.etf_theme", "theme"),),
        )
        rows = {
            "중국": [{"etf_code": code, "etf_name": code} for code in ("A", "B", "C")],
            "반도체": [{"etf_code": code, "etf_name": code} for code in ("B", "C", "D")],
        }
        with patch.object(self.graph, "_theme_candidates", side_effect=candidates), \
             patch.object(self.graph, "catalog", return_value=graph_catalog), \
             patch.object(self.graph, "validate_graph_plan", return_value=Mock(ok=True)), \
             patch.object(self.graph, "compile_graph_plan",
                          side_effect=lambda _p, candidate, _f, _c: compiled(candidate)), \
             patch.object(self.graph.graph_engine, "sparql",
                          side_effect=lambda query: rows[query]):
            result = self.graph.run_theme_membership("중국 반도체 ETF", "중국 반도체")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["entity_codes"], ["B", "C"])
        self.assertTrue(all(row["_matched_theme_facets"] == ["중국", "반도체"]
                            for row in result["rows"]))

    def test_unqualified_foreign_theme_etf_is_domestic_but_explicit_listing_is_not(self):
        from agent.intent_guard import guard_intent

        base = {
            "product_domain": [{"domain": "해외ETF", "subtype": ["반도체"]}],
            "target_entities": [], "conditions": [],
            "relations": [
                {"id": "R1", "subject_domain": "ETF", "relation": "holds",
                 "object_entity": "캠브리콘", "entity_role": "product"},
                {"id": "R2", "subject_domain": "ETF", "relation": "tagged_with",
                 "object_entity": "중국 반도체", "entity_role": "theme"},
            ],
        }
        fixed, notes = guard_intent({**base, "raw_question": "캠브리콘이 편입된 중국 반도체 ETF"})
        self.assertEqual(fixed["product_domain"][0]["domain"], "국내ETF")
        self.assertEqual(fixed["product_domain"][0]["subtype"], [])
        self.assertEqual({r["subject_domain"] for r in fixed["relations"]}, {"국내ETF"})
        self.assertTrue(any("해외ETF 오분류" in note for note in notes))

        explicit, _ = guard_intent({**base, "raw_question": "중국 거래소에 상장된 ETF 중 캠브리콘 편입 상품"})
        self.assertEqual(explicit["product_domain"][0]["domain"], "해외ETF")

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
