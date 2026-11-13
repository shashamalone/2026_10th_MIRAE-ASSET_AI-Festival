"""답변 생성 노드(generate_answer_node) 단위 테스트(LLM·DB 호출 없음).

python script/agent_test/test_answer_generation.py

행 예산(sort.limit·기본 10), 빈 answer·길이 초과 시 예산 절반 재시도와 결정론 폴백,
요청 항목별 산출 상태 조립(RDB 제외 메모·Vector 미확보·Graph abstain), 미산출 footer를 확인한다.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")  # nodes는 import 시점에 ChatClovaX를 만든다

from agent import nodes  # noqa: E402


class LengthFinishReasonError(Exception):
    """openai.LengthFinishReasonError와 같은 이름 - nodes는 클래스 이름으로만 판별한다."""


class FakeStructuredLLM:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)  # dict(응답) 또는 Exception
        self.calls: list[str] = []

    def with_structured_output(self, *a, **k):
        return self

    def invoke(self, messages):
        self.calls.append(messages[1][1])
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def _rows(n, domain="채권"):
    return [{"pd_nm": f"상품{i}", "crd_grd": "AA-", "_domain": domain, "_step_id": "rdb_채권"} for i in range(n)]


def _state(rows, intent=None, step_results=None, plan=None):
    return {
        "question_id": "T", "question": "q", "merged_rows": rows,
        "intent": intent or {"output_requirements": {"fields": ["신용등급"]}, "sort": {}},
        "step_results": step_results or {"rdb_채권": {"engine": "rdb", "domain": "채권", "rows": rows, "count": len(rows), "sql": "SELECT 1"}},
        "plan": plan or [], "route": {"blocking_reasons": []}, "trace": ["질문 수신"],
    }


def _answer(out):
    return json.loads(out["answer"])["answer"]


class RowBudgetTest(unittest.TestCase):
    def test_default_and_limit(self):
        self.assertEqual(nodes._answer_row_budget({"sort": {}}), 10)
        self.assertEqual(nodes._answer_row_budget({"sort": {"limit": "5"}}), 5)
        self.assertEqual(nodes._answer_row_budget({"sort": {"limit": "50"}}), 20)

    def test_preview_uses_budget(self):
        fake = FakeStructuredLLM([{"think_trace": "t", "answer": "전체 100건 중 10건: 상품0 AA- 외 9건입니다."}])
        nodes._llm_answer = fake
        nodes.generate_answer_node(_state(_rows(100)))
        self.assertIn("전체 100건 중 10건 표시", fake.calls[0])


class BlankAnswerTest(unittest.TestCase):
    def test_blank_detection(self):
        for blank in ("", "[]", "[", "{}", "요청하신 정보는 다음과 같습니다."):
            self.assertTrue(nodes._is_blank_answer(blank), blank)
        self.assertFalse(nodes._is_blank_answer("상품0의 신용등급은 AA-이며 기준일은 2026-08-21입니다."))

    def test_blank_then_retry_with_half_budget(self):
        good = "전체 100건 중 5건: 상품0의 신용등급은 AA-입니다. 상품1도 AA-입니다."
        fake = FakeStructuredLLM([{"think_trace": "t", "answer": "[]"}, {"think_trace": "t", "answer": good}])
        nodes._llm_answer = fake
        out = nodes.generate_answer_node(_state(_rows(100)))
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("전체 100건 중 5건 표시", fake.calls[1])
        self.assertIn("[재시도 안내]", fake.calls[1])
        self.assertTrue(_answer(out).startswith(good))
        self.assertIn("수치 기준일: 채권 2026-08-21", _answer(out))

    def test_length_error_twice_falls_back_to_rows(self):
        fake = FakeStructuredLLM([LengthFinishReasonError("len"), LengthFinishReasonError("len")])
        nodes._llm_answer = fake
        out = nodes.generate_answer_node(_state(_rows(12)))
        text = _answer(out)
        self.assertIn("전체 12건 중 5건", text)
        self.assertIn("상품0", text)
        self.assertIn("AA-", text)
        self.assertTrue(any("결정론 폴백" in m for m in out["trace"]))


class RateLimitError(Exception):
    """openai.RateLimitError와 같은 이름."""


class RateLimitTest(unittest.TestCase):
    def test_rate_limit_skips_retry_and_falls_back(self):
        fake = FakeStructuredLLM([RateLimitError("429")])
        nodes._llm_answer = fake
        out = nodes.generate_answer_node(_state(_rows(3)))
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("상품0", _answer(out))


class ItemStatusTest(unittest.TestCase):
    def test_rdb_excluded_fields_and_vector_uncovered(self):
        rows = [{"itm_nm": "미래에셋국민참여형국민성장혼합자산", "_domain": "펀드", "_step_id": "rdb_펀드"}]
        intent = {"output_requirements": {"fields": ["구조", "운용주체"], "narrative_topics": ["최근 투자전략 동향"]}, "sort": {}}
        step_results = {
            "rdb_펀드": {"engine": "rdb", "domain": "펀드", "rows": rows, "count": 1, "sql": "SELECT 1",
                        "assumptions": ["요청된 필드 '구조'는 대응하는 컬럼을 찾지 못해 결과에서 제외했습니다.",
                                        "요청된 필드 '운용주체'는 대응하는 컬럼을 찾지 못해 결과에서 제외했습니다."]},
            "vector_narrative": {"engine": "vector", "status": "no_document", "count": 0, "note": "문서 확보 0",
                                 "topic_coverage": {"uncovered": {"objective_strategy": ["최근 투자전략 동향"]}}},
        }
        status = nodes._build_item_status(_state(rows, intent, step_results))
        by = {x["item"]: x for x in status}
        self.assertEqual(by["구조"]["status"], "미산출")
        self.assertIn("대응 컬럼이 없음", by["구조"]["reason"])
        self.assertEqual(by["운용주체"]["status"], "미산출")
        self.assertIn("투자목적·운용전략 섹션", by["최근 투자전략 동향"]["reason"])

        fake = FakeStructuredLLM([{"think_trace": "t", "answer": "국민성장 명칭 상품 1건은 존재하나 요청 항목은 데이터에 없습니다."}])
        nodes._llm_answer = fake
        text = _answer(nodes.generate_answer_node(_state(rows, intent, step_results)))
        self.assertIn("제공된 데이터로 확인할 수 없는 항목: 구조, 운용주체 — 펀드 데이터에 대응 컬럼이 없음", text)
        self.assertIn("최근 투자전략 동향 — 문서에 투자목적·운용전략 섹션", text)
        self.assertTrue(text.startswith("검색된 상품 1건: 미래에셋국민참여형국민성장혼합자산"), text)
        self.assertIn("수치 기준일: 펀드 2026-08-21", text)
        self.assertIn("[요청 항목별 산출 상태]", fake.calls[0])

    def test_graph_holds_abstain_names_needed_data(self):
        rows = [{"pd_nm": "ETF A", "_domain": "해외ETF", "_step_id": "rdb_해외ETF"}]
        intent = {"output_requirements": {"fields": ["ETF명", "편입비중", "편입기준일"]}, "sort": {}}
        plan = [{"step_id": "graph_R1", "engine": "graph", "relation": {"id": "R1", "relation": "holds", "object_entity": "캠브리콘"}}]
        step_results = {
            "graph_R1": {"engine": "graph", "status": "abstain_entity_not_found", "rows": []},
            "rdb_해외ETF": {"engine": "rdb", "domain": "해외ETF", "rows": rows, "count": 1, "sql": "SELECT 1"},
        }
        by = {x["item"]: x for x in nodes._build_item_status(_state(rows, intent, step_results, plan))}
        self.assertEqual(by["ETF명"]["status"], "산출")
        self.assertEqual(by["편입비중"]["status"], "미산출")
        self.assertIn("편입내역", by["편입비중"]["reason"])
        self.assertIn("외부 데이터가 필요함", by["편입기준일"]["reason"])
        self.assertIn("캠브리콘 holds 관계", by)
        self.assertIn("그래프에서 해당 엔티티를 찾지 못함", by["캠브리콘 holds 관계"]["reason"])

    def test_issued_by_relation_is_not_a_gap(self):
        plan = [{"step_id": "graph_R1", "engine": "graph", "relation": {"id": "R1", "relation": "발행사", "object_entity": "SK하이닉스"}}]
        step_results = {"graph_R1": {"engine": "graph", "status": "abstain_evidence_missing", "rows": []}}
        status = nodes._build_item_status(_state([], {"output_requirements": {"fields": ["등급"]}}, step_results, plan))
        self.assertEqual([x["status"] for x in status], ["산출"])

    def test_no_rows_branch_includes_skipped_reason_and_footer(self):
        step_results = {"rdb_채권": {"engine": "rdb", "domain": "채권", "rows": [], "count": 0, "sql": None,
                                   "skipped_reason": "유효하지 않은 조건: 신용등급='AAAA'"}}
        text = _answer(nodes.generate_answer_node(_state([], {"output_requirements": {"fields": ["상품번호"]}}, step_results)))
        self.assertIn("답변할 수 없습니다", text)
        self.assertIn("AAAA", text)
        self.assertIn("채권 조회 — 유효하지 않은 조건", text)

    def test_deprecated_column_note_becomes_definition_change(self):
        rows = _rows(2)
        intent = {"output_requirements": {"fields": ["매수가능수량", "신용등급"]}, "sort": {}}
        step_results = {"rdb_채권": {"engine": "rdb", "domain": "채권", "rows": rows, "count": 2, "sql": "SELECT 1",
                                   "assumptions": ["buyable_quantity(매수가능수량)는 주최측이 무효로 공지한 컬럼이라 조건·정렬·출력에 쓰지 않는다"]}}
        by = {x["item"]: x for x in nodes._build_item_status(_state(rows, intent, step_results))}
        self.assertEqual(by["매수가능수량"]["status"], "미산출")
        self.assertIn("무효로 공지해 사용하지 않음", by["매수가능수량"]["reason"])
        self.assertEqual(by["신용등급"]["status"], "산출")

    def test_names_guard_skips_large_dumps(self):
        self.assertTrue(nodes._names_guard("확인 불가", _rows(3)).startswith("검색된 상품 3건: 상품0, 상품1, 상품2"))
        self.assertEqual(nodes._names_guard("상품1 포함", _rows(3)), "상품1 포함")
        self.assertEqual(nodes._names_guard("확인 불가", _rows(100)), "확인 불가")


if __name__ == "__main__":
    unittest.main()
