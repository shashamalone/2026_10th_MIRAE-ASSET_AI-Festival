"""Offline field-completeness regressions. No live DB or paid LLM calls."""
import copy
import json
import os
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from agent import utils
from tools import catalog_sql, rdb_schema, schema_snapshot
from test_catalog_sql import snapshot, resolved


class AnswerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "offline-test-key"}):
            from agent import nodes
        cls.nodes = nodes

    def setUp(self):
        self.llm_patch = patch.object(self.nodes, "_llm_answer")
        self.llm = self.llm_patch.start()
        self.llm.with_structured_output.return_value.invoke.side_effect = AssertionError("unexpected LLM call")
        self.addCleanup(self.llm_patch.stop)
        for target, name, value in [(schema_snapshot, "get_snapshot", snapshot()),
                                    (catalog_sql, "domain_metadata", {"buyable_quantity": {"description": "매수가능수량"}})]:
            p = patch.object(target, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def state(self, rows=None, fields=None, domain="채권", metadata=None):
        fields = fields or ["발행사", "신용등급", "표면금리", "만기일", "매수수익률", "매수가능수량", "상품번호"]
        if rows is None:
            rows = [{"pd_nm": "가상회사채 1-2", "pd_pbcm": "가상발행사(주)", "crd_grd": "AA+",
                     "srfc_irt": 4.266, "mat_dt": "20280214", "buy_yield": None,
                     "buyable_quantity": None, "pd_no": "TEST-BOND", "info_base_dt": "20260821"}]
        metadata = {"buyable_quantity": {"description": "매수가능수량"}, **(metadata or {})}
        mapping = dict(rdb_schema.get_attribute_catalog(domain))
        aliases = catalog_sql.description_aliases(domain, metadata)
        mapping.update({f: aliases[catalog_sql.normalize(f)] for f in fields
                        if catalog_sql.normalize(f) in aliases})
        spec = utils.build_resolved_schema({"domain": domain, "fields": fields}, mapping, [])
        compiled = catalog_sql.compile_select(spec, snapshot=snapshot(), metadata=metadata)
        step = {"engine": "rdb", "role": "target", "domain": domain, "rows": rows,
                "count": len(rows), "sql": compiled["sql"], "output_fields": compiled["output_fields"],
                "requested_fields": list(fields)}
        state = {"question_id": "unseen-case", "question": "항목별 값을 알려줘",
                 "intent": {"task": "lookup", "output_requirements": {"fields": list(fields)}},
                 "route": {}, "step_results": {"r1": step}, "plan": []}
        state.update(self.nodes.merge_results_node(state))
        return state

    def response(self, state):
        response = json.loads(self.nodes.generate_answer_node(state)["answer"])
        self.assertEqual(set(response), {"question_id", "question", "retrieved_context", "think_trace", "answer"})
        return response

    def answer(self, state):
        return self.response(state)["answer"]

    def items(self, state):
        return {i["field"]: i for i in self.nodes._build_rdb_answer_contract(state)[0]["items"]}

    def test_null_fields_are_never_omitted(self):
        state = self.state()
        answer = self.answer(state)
        for label in state["intent"]["output_requirements"]["fields"]:
            self.assertIn(label, answer)
        self.assertIn("매수수익률, 매수가능수량: 제공된 조회 결과의 값이 NULL", answer)
        self.assertNotIn("raw.prbd01n001.buyable_quantity", answer)
        context = self.response(state)["retrieved_context"]
        self.assertIn("국내채권마스터 · 2026-08-24 · 1건", context)
        self.assertIn("raw.prbd01n001.buyable_quantity", context)
        self.assertNotIn("SQL:", context)
        self.assertIn("4.266", answer)
        self.llm.with_structured_output.assert_not_called()

    def test_condition_code_binding_can_attach_graph_weight(self):
        state = self.state(rows=[{"pd_itm_no": "TEST-ETF", "pd_nm": "예시 ETF"}], fields=["상품코드", "편입비중"], domain="국내ETF")
        for binding in state["step_results"]["r1"]["output_fields"]:
            if binding["attribute"] == "상품코드":
                binding["attribute"] = "조건근거(상품코드)"
        state["step_results"]["g"] = {"engine": "graph", "status": "ok", "rows": [{"code": "TEST-ETF", "weight": 3.5, "h_as_of": "2026-07-10", "h_source": "source"}],
            "graph_plan": {"nodes": [{"id": "h", "class_uri": "fp:Holding"}], "outputs": [{"alias": "code", "property": "fp:productCode"}, {"alias": "weight", "property": "fp:weight"}]}}
        self.assertEqual(self.items(state)["편입비중"]["value"][0]["weight"], 3.5)
        answer = self.answer(state)
        self.assertIn("편입비중: 3.5%", answer)
        self.assertNotIn('{"weight"', answer)

    def test_general_fund_grade_cannot_be_industry_risk_evidence(self):
        state = self.state()
        state["question"] = "로봇산업 위험요인을 설명해줘"
        state["intent"]["output_requirements"]["narrative_topics"] = ["로봇산업 위험요인"]
        state["step_results"]["v"] = {"engine": "vector", "status": "ok", "chunks": [{"chunk_id": "x", "chunk_text": "이 상품은 위험등급 2등급입니다."}]}
        answer = self.answer(state)
        self.assertIn("산업별 위험 근거 미확보", answer)
        self.llm.with_structured_output.assert_not_called()

    def test_zero_and_false_are_values_without_missing_policy(self):
        for value in [0, 0.0, "0", "0.00", False, Decimal("0.00")]:
            with self.subTest(value=value):
                item = self.nodes._field_evidence("필드", {"key": "x", "column": "raw.t.x"}, {"x": value})
                self.assertEqual(item["status"], "available")
                self.assertEqual(item["value"], value)

    def test_null_fee_is_a_valid_explicit_unavailable_answer(self):
        state = self.state(domain="국내ETF", fields=["총보수", "투자지역"], rows=[{
            "pd_nm": "가상 ETF", "pd_itm_no": "TEST-ETF", "expense_ratio": None,
            "wu_inv_rgn": "미국"}])
        answer = self.answer(state)
        self.assertEqual(self.items(state)["총보수"]["status"], "null")
        self.assertIn("총보수: 제공된 조회 결과의 값이 NULL", answer)
        self.assertIn("투자지역: 미국", answer)
        self.assertNotIn("총보수: 0", answer)
        self.assertNotIn("상품이 없습니다", answer)
        self.llm.with_structured_output.assert_not_called()

    def test_missing_column_is_not_sql_null(self):
        state = self.state()
        del state["step_results"]["r1"]["rows"][0]["buyable_quantity"]
        self.assertEqual(self.items(state)["매수가능수량"]["status"], "not_selected")
        self.assertIn("NULL 여부도 확인되지 않았습니다", self.answer(state))

    def test_blank_is_not_zero_or_null(self):
        for value in ["", "  "]:
            state = self.state()
            state["step_results"]["r1"]["rows"][0]["buy_yield"] = value
            self.assertEqual(self.items(state)["매수수익률"]["status"], "empty")
            self.assertIn("매수수익률: 제공된 조회 결과가 빈 값", self.answer(state))

    def test_unknown_request_and_planner_omission_are_visible(self):
        state = self.state()
        state["intent"]["output_requirements"]["fields"].append("미지원 항목")
        self.assertEqual(self.items(state)["미지원 항목"]["status"], "unmapped")
        self.assertIn("미지원 항목: 요청 항목과 조회 컬럼의 대응", self.answer(state))

    def test_failure_and_blocked_do_not_claim_null_or_product_absence(self):
        for key, status in [("error", "query_failed"), ("skipped_reason", "blocked")]:
            state = self.state()
            state["step_results"]["r1"][key] = "simulated failure"
            self.assertTrue(all(i["status"] == status for i in self.items(state).values()))
            answer = self.answer(state)
            self.assertNotIn("4.266", answer)  # no stale rows after failure
            self.assertNotIn("상품이 없습니다", answer)
            self.assertNotIn("값이 NULL", answer)
            self.assertEqual(answer.count("제공 데이터로 확인할 수 없습니다."), 1)
            self.assertNotIn("r1", answer)

    def test_zero_rows_have_a_distinct_reason(self):
        state = self.state(rows=[])
        self.assertTrue(all(i["status"] == "no_rows" for i in self.items(state).values()))
        answer = self.answer(state)
        self.assertIn("조회 결과가 없어 확인할 수 없습니다.", answer)
        self.assertEqual(answer.count("조회 결과가 없어 확인할 수 없습니다."), 1)

    def test_all_null_rows_still_produce_an_answer(self):
        state = self.state()
        row = state["step_results"]["r1"]["rows"][0]
        for key in row:
            row[key] = None
        answer = self.answer(state)
        self.assertIn("확인 불가 항목", answer)
        self.assertNotIn("확인된 값", answer)

    def test_exact_name_large_number_decimal_and_date_are_preserved(self):
        name = "가상 KODEX200 증권상장지수투자신탁[주식]"
        state = self.state(domain="국내ETF", fields=["상품명", "AUM", "NAV"], rows=[{
            "pd_nm": name, "du_last_aum": 25474813891225, "du_last_nav": Decimal("110190.8100"),
            "pd_itm_no": "TEST-ETF"}])
        answer = self.answer(state)
        for value in [name, "25474813891225", "110190.8100"]:
            self.assertIn(value, answer)
        self.assertNotIn("KODEX 200", answer)

    def test_metadata_zero_unavailability_preserves_raw_without_claiming_free(self):
        for value in [0, "0.0", Decimal("0.00")]:
            binding = {"key": "fee", "column": "raw.t.fee", "zero_null_rule":
                       "빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음"}
            item = self.nodes._field_evidence("보수", binding, {"fee": value})
            self.assertEqual(item["status"], "zero_unavailable")
            self.assertEqual(item["value"], value)
        flag = {"key": "x", "column": "raw.t.x", "zero_null_rule":
                "빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지"}
        self.assertEqual(self.nodes._field_evidence("플래그", flag, {"x": 0})["status"], "available")

    def test_nan_and_infinity_are_not_valid_measurements(self):
        for value in [float("nan"), float("inf"), Decimal("NaN")]:
            item = self.nodes._field_evidence("수치", {"key": "x", "column": "raw.t.x"}, {"x": value})
            self.assertEqual(item["status"], "invalid")

    def test_source_dates_use_metadata_not_dataset_date(self):
        state = self.state(fields=["발행사", "매수수익률", "기준일"], metadata={
            "pd_pbcm": {"as_of_column": "info_base_dt"},
            "buy_yield": {"as_of_column": "sale_yield_base_dt"}})
        state["step_results"]["r1"]["rows"][0]["sale_yield_base_dt"] = None
        answer = self.answer(state)
        self.assertIn("기준일 (발행사 관련): 20260821", answer)
        self.assertIn("기준일 (매수수익률 관련): 제공된 조회 결과의 값이 NULL", answer)
        self.assertNotIn("info_base_dt", answer)
        self.assertNotIn("sale_yield_base_dt", answer)
        self.assertNotIn("2026-08-24", answer)

    def test_answer_surface_hides_internal_execution_identifiers(self):
        state = self.state(fields=["상품명", "상품번호"])
        state["step_results"]["graph_R1"] = {
            "engine": "graph", "status": "ok",
            "rows": [{"etf_code": "TEST-ETF", "etf_name": "예시 ETF", "weight": 3.5,
                      "holding_as_of": "2026-07-10", "holding_source": "TEST"}],
            "graph_plan": {"edges": [{"subject": "etf", "predicate": "fp:hasHolding", "object": "holding"}]},
        }
        response = self.response(state)
        answer = response["answer"]
        self.assertNotIn("r1", answer)
        self.assertNotIn("graph_R1", answer)
        self.assertNotIn("raw.", answer)
        self.assertNotIn("실행 경로", answer)
        self.assertNotIn("etf_code", answer)
        self.assertIn("상품코드: TEST-ETF", answer)
        self.assertIn("편입비중: 3.5", answer)
        self.assertIn("r1", response["think_trace"])

    def test_graph_candidates_consumed_by_rdb_are_not_rendered_as_final_rows(self):
        state = self.state(fields=["상품명", "상품번호"])
        state["step_results"]["graph_R1"] = {
            "engine": "graph", "status": "ok",
            "rows": [{"etf_code": f"CANDIDATE-{index}", "etf_name": f"후보 {index}"}
                     for index in range(14)],
        }
        state["plan"] = [
            {"step_id": "graph_R1", "engine": "graph", "depends_on": []},
            {"step_id": "r1", "engine": "rdb", "depends_on": ["graph_R1"]},
        ]
        answer = self.answer(state)
        self.assertNotIn("CANDIDATE-", answer)
        self.assertNotIn("Graph 관계 조회 결과", answer)

    def test_zero_row_labels_strip_physical_date_columns(self):
        contract = [{
            "step_id": "rdb_국내ETF", "domain": "국내ETF", "row_number": None,
            "retrieved_rows": 0, "displayed_rows": 0, "notes": [],
            "items": [
                {"field": "상품명", "status": "no_rows", "value": None, "column": None},
                {"field": "출처기준일(cu_upt_dt)", "status": "no_rows", "value": None, "column": None},
                {"field": "출처기준일(du_upt_dt)", "status": "no_rows", "value": None, "column": None},
            ],
        }]
        answer = self.nodes._render_rdb_answer_contract(contract)
        self.assertIn("상품명, 출처기준일: 조회 결과가 없어", answer)
        self.assertNotIn("cu_upt_dt", answer)
        self.assertNotIn("du_upt_dt", answer)
        self.assertEqual(answer.count("출처기준일"), 1)

    def test_repeated_available_dates_and_notices_are_collapsed(self):
        base_item = {"field": "기준일", "answer_field": "기준일 (상품명 관련)",
                     "status": "available", "value": "20260821", "column": "raw.t.info_base_dt"}
        contract = [
            {"step_id": "r1", "domain": "채권", "row_number": index,
             "retrieved_rows": 2, "displayed_rows": 2, "notes": ["같은 유의사항"],
             "items": [dict(base_item), dict(base_item)]}
            for index in (1, 2)
        ]
        answer = self.nodes._render_rdb_answer_contract(contract)
        self.assertEqual(answer.count("기준일 (상품명 관련): 20260821"), 2)
        self.assertEqual(answer.count("같은 유의사항"), 1)
        self.assertEqual(answer.count("반환 2건 중 2건 표시"), 1)

    def test_graph_exception_details_do_not_leak_into_answer(self):
        state = self.state()
        secret_path = r"C:\\private\\artifacts\\oxigraph"
        state["step_results"]["graph_R1"] = {
            "engine": "graph", "status": "abstain_exception", "rows": [],
            "note": f"GraphDBUnavailable: store path missing: {secret_path}",
        }
        answer = self.answer(state)
        self.assertIn("관계 근거 미확보", answer)
        self.assertNotIn("GraphDBUnavailable", answer)
        self.assertNotIn(secret_path, answer)

    def test_blocking_reason_is_not_repeated_in_empty_answer(self):
        reason = "Kimi와 상품을 연결하는 관계를 확정하지 못했습니다. 정확한 상품 식별자를 알려주세요."
        state = {"question_id": "Q32", "question": "Kimi 관련 상품", "intent": {},
                 "route": {"blocking_reasons": [reason]}, "step_results": {},
                 "merged_rows": [], "plan": []}
        answer = self.answer(state)
        self.assertEqual(answer.count(reason), 1)

    def test_rows_remain_separate_not_cross_filled(self):
        state = self.state()
        second = copy.deepcopy(state["step_results"]["r1"]["rows"][0])
        second["buy_yield"] = 3.9279
        state["step_results"]["r1"]["rows"].append(second)
        contract = self.nodes._build_rdb_answer_contract(state)
        values = [next(i for i in r["items"] if i["field"] == "매수수익률") for r in contract]
        self.assertEqual([v["status"] for v in values], ["null", "available"])

    def test_display_cap_is_explicit(self):
        state = self.state()
        row = state["step_results"]["r1"]["rows"][0]
        state["step_results"]["r1"]["rows"] = [dict(row) for _ in range(25)]
        self.assertEqual(len(self.nodes._build_rdb_answer_contract(state)), 20)
        self.assertIn("반환 25건 중 20건 표시", self.answer(state))

    def test_narrative_output_cannot_erase_structured_fields(self):
        state = self.state()
        state["intent"]["output_requirements"]["narrative_topics"] = ["위험"]
        state["step_results"]["v"] = {"engine": "vector", "status": "ok", "chunks": [{"document_id": "D", "chunk_id": "C", "chunk_text": "가상 문서의 위험 근거", "document_title": "가상 위험자료"}]}
        invocation = self.llm.with_structured_output.return_value.invoke
        invocation.side_effect = None
        for reply in ["", "  ", "확보된 문서의 위험 요약"]:
            invocation.return_value = {"answer": reply, "think_trace": "실행 요약"}
            answer = self.answer(state)
            self.assertIn("매수가능수량: 제공된 조회 결과의 값이 NULL", answer)
            self.assertIn("4.266", answer)
            if reply.strip():
                self.assertIn(reply, answer)
        self.assertIn("요청 항목별 RDB 상태", invocation.call_args.args[0][1][1])

    def test_narrative_outage_keeps_retrieved_values(self):
        state = self.state()
        state["intent"]["output_requirements"]["narrative_topics"] = ["위험"]
        state["step_results"]["v"] = {"engine": "vector", "status": "ok", "chunks": [{"document_id": "D", "chunk_id": "C", "chunk_text": "가상 문서의 위험 근거", "document_title": "가상 위험자료"}]}
        self.llm.with_structured_output.return_value.invoke.side_effect = RuntimeError("mock outage")
        response = self.response(state)
        answer = response["answer"]
        self.assertIn("추가 설명 생성에 실패", answer)
        self.assertIn("4.266", answer)
        self.assertNotIn("buyable_quantity", answer)
        self.assertIn("buyable_quantity", response["retrieved_context"])

    def test_no_document_body_cannot_generate_a_risk_claim(self):
        state = self.state()
        state["intent"]["output_requirements"]["narrative_topics"] = ["위험"]
        answer = self.answer(state)
        self.assertIn("문서 기반 설명 확인 불가", answer)
        self.llm.with_structured_output.assert_not_called()

    def test_node_transmits_execution_bindings_and_original_requests(self):
        step = {"domain": "채권", "fields": ["매수수익률", "매수가능수량"]}
        with patch.object(utils, "run_sql", return_value=[{"buy_yield": None, "buyable_quantity": None}]):
            result = self.nodes._execute_target_step(step, "", Mock(), True, 1)
        self.assertEqual(result["requested_fields"], step["fields"])
        bindings = {b["attribute"]: b for b in result["output_fields"]}
        self.assertEqual(bindings["매수가능수량"]["key"], "buyable_quantity")

    def test_join_null_is_query_null_not_claim_about_underlying_table(self):
        compiled = catalog_sql.compile_select(resolved(fields=["총보수율"]), snapshot=snapshot(), metadata={})
        binding = next(b for b in compiled["output_fields"] if b["attribute"] == "총보수율")
        item = self.nodes._field_evidence("총보수율", binding, {binding["key"]: None})
        self.assertEqual(item["status"], "null")
        self.assertIn("조회 결과", self.nodes._FIELD_UNAVAILABLE_TEXT["null"])

    def test_union_ordinal_rank_is_not_reported_as_rating(self):
        spec = resolved(domain="채권", fields=["상품코드"], sort={"attribute": "신용등급", "order": "desc"})
        compiled = catalog_sql.compile_select(spec, snapshot=snapshot(), metadata={}, union_mode=True)
        binding = next(b for b in compiled["output_fields"] if b["key"] == "sort_value")
        self.assertEqual(binding["attribute"], "정렬순위(신용등급)")

    def test_contract_does_not_mutate_state(self):
        state = self.state()
        before = copy.deepcopy(state)
        self.answer(state)
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
