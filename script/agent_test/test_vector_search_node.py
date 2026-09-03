"""vector_search_node 단위 테스트(DB·LLM 호출 없음).

python script\agent_test\test_vector_search_node.py

임베딩·검색·상품해소·커버리지 네 함수를 nodes 모듈 수준에서 가로채고,
스코프 수집 / 주제→section_type 힌트 / 상태 판정(ok·low_confidence·
no_document·topic_not_covered·no_hit) /
예외 abstain / merge_results_node의 vector 행을 확인한다.
"""
from __future__ import annotations

import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

# nodes는 import 시점에 ChatClovaX를 만들기 때문에 API 키가 필요하다.
load_dotenv(REPO_ROOT / ".env")

from agent import nodes  # noqa: E402


def make_chunk(chunk_id: str, score: float, **over) -> dict:
    chunk = {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "section_type": "risk",
        "citation_text": f"투자설명서 {chunk_id}",
        "chunk_text": "본문 " * 300,
        "score": score,
        "effective_as_of": "2026-08-21",
        "published_at": "2026-08-01",
        "source_url": "https://example.com/doc-1.pdf",
        "product_ids": ["etf_kr:KR7449690007"],
    }
    chunk.update(over)
    return chunk


def make_state(**over) -> dict:
    state = {
        "question": "이 상품의 투자 위험은?",
        "intent": {},
        "plan": [{"step_id": "vector_narrative", "engine": "vector", "depends_on": [], "topics": []}],
        "step_results": {},
    }
    state.update(over)
    return state


@contextmanager
def patch_vector(search, *, product_ids=None, coverage=None):
    """nodes 모듈에 붙어 있는 네 외부 의존성을 한 번에 가로채고 그 mock을 넘긴다."""
    mocks = {
        "embed": mock.Mock(return_value=[0.1] * 1024),
        "search_documents": search,
        "resolve_product_ids": mock.Mock(return_value=list(product_ids or [])),
        "get_coverage": mock.Mock(return_value=dict(coverage or {})),
    }
    with mock.patch.multiple(nodes, **mocks):
        yield mocks


class VectorScopeTest(unittest.TestCase):
    def test_collects_names_and_codes_from_intent_and_dependencies(self):
        state = make_state(
            intent={"target_entities": [
                {"surface_form": "TIGER 반도체", "entity_type": "product_name"},
                {"surface_form": "삼성전자", "entity_type": "company"},
            ]},
            step_results={
                # RDB 행은 LLM이 고른 컬럼만 담는다 - 여기선 이름 컬럼만 있다.
                "rdb_etf": {"engine": "rdb", "rows": [{"pd_nm": "KODEX 200", "pd_net_tamt": 1}]},
                "graph_r1": {"engine": "graph", "entity_codes": ["KR7069500007"]},
            },
        )
        step = {"step_id": "v", "depends_on": ["rdb_etf", "graph_r1"],
                "target_entities": [{"surface_form": "TIGER 반도체", "entity_type": "product_name"}]}

        codes, names = nodes._vector_scope(state, step)

        self.assertEqual(codes, ["KR7069500007"])
        self.assertEqual(names, ["TIGER 반도체", "KODEX 200"])  # 중복 제거 + 순서 유지


class SectionHintTest(unittest.TestCase):
    def test_maps_only_matching_labels_to_sections(self):
        self.assertEqual(
            nodes._section_hints(["운용 전략", "순자산", "투자 위험"]),
            {"objective_strategy": ["운용 전략"], "risk": ["투자 위험"]},
        )

    def test_returns_empty_when_nothing_matches(self):
        self.assertEqual(nodes._section_hints(["순자산", "총보수"]), {})


class VectorSectionScopeTest(unittest.TestCase):
    """요청 주제(topics/fields)가 section_type 필터로 넘어가는지."""

    def run_step(self, search, *, topics, fields, **kwargs):
        plan = [{"step_id": "vector_narrative", "engine": "vector",
                 "depends_on": [], "topics": topics, "fields": fields}]
        with patch_vector(search, **kwargs):
            out = nodes.vector_search_node(make_state(plan=plan))
        return out["step_results"]["vector_narrative"]

    def test_topics_scope_search_to_strategy_section(self):
        search = mock.Mock(return_value=[])
        self.run_step(search, topics=["운용 전략"], fields=[])
        self.assertEqual(search.call_args.kwargs["section_types"], ["objective_strategy"])

    def test_fields_alone_supply_hint_without_changing_queries(self):
        search = mock.Mock(return_value=[])
        result = self.run_step(search, topics=[], fields=["투자 위험", "순자산"])
        self.assertEqual(search.call_args.kwargs["section_types"], ["risk"])
        self.assertEqual(result["queries"], ["이 상품의 투자 위험은?"])

    def test_topic_not_covered_when_requested_section_has_no_chunk(self):
        search = mock.Mock(return_value=[])
        state = make_state(intent={"target_entities": [
            {"surface_form": "미래에셋 인컴", "entity_type": "product_name"}]})
        plan = [{"step_id": "vector_narrative", "engine": "vector",
                 "depends_on": [], "topics": ["운용 전략"], "fields": []}]
        state["plan"] = plan
        with patch_vector(search, product_ids=["fund:A"],
                          coverage={"fund:A": {"status": "matched_dart"}}):
            result = nodes.vector_search_node(state)["step_results"]["vector_narrative"]

        self.assertEqual(result["status"], "topic_not_covered")
        self.assertEqual(result["topic_coverage"]["uncovered"], {"objective_strategy": ["운용 전략"]})
        self.assertIn("요청 주제 미확보", result["note"])
        self.assertIn("투자목적·운용전략 섹션 없음", result["note"])

    def test_ok_still_reports_uncovered_topic(self):
        # risk 청크만 걸린 상태에서 전략을 물은 경우 - 인용은 하되 미확보를 남긴다.
        search = mock.Mock(return_value=[make_chunk("c1", 0.62, section_type="risk")])
        result = self.run_step(search, topics=["투자 위험", "운용 전략"], fields=[])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["topic_coverage"]["uncovered"], {"objective_strategy": ["운용 전략"]})
        self.assertEqual(result["topic_coverage"]["requested"],
                         {"risk": ["투자 위험"], "objective_strategy": ["운용 전략"]})

    def test_no_hint_leaves_search_unscoped_by_section(self):
        search = mock.Mock(return_value=[])
        result = self.run_step(search, topics=[], fields=["순자산"])
        self.assertIsNone(search.call_args.kwargs["section_types"])
        self.assertEqual(result["topic_coverage"], {"requested": {}, "uncovered": {}})


class VectorStatusTest(unittest.TestCase):
    def run_node(self, search, **kwargs):
        state = kwargs.pop("state", None) or make_state()
        with patch_vector(search, **kwargs):
            return nodes.vector_search_node(state)

    def test_ok_filters_chunks_below_score_floor(self):
        search = mock.Mock(return_value=[make_chunk("c1", 0.62), make_chunk("c2", 0.31)])
        out = self.run_node(search, product_ids=["etf_kr:A"],
                            coverage={"etf_kr:A": {"status": "matched_dart"}},
                            state=make_state(intent={"target_entities": [
                                {"surface_form": "TIGER 반도체", "entity_type": "product_name"}]}))

        result = out["step_results"]["vector_narrative"]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["count"], 1)
        self.assertEqual([c["chunk_id"] for c in result["chunks"]], ["c1"])
        self.assertEqual(result["raw_top"], [("c1", 0.62), ("c2", 0.31)])
        self.assertEqual(result["product_scope"]["coverage"]["matched"], 1)
        self.assertEqual(len(result["chunks"][0]["chunk_text"]), 900)

    def test_dedupes_by_chunk_id_keeping_max_score_across_topics(self):
        search = mock.Mock(side_effect=[
            [make_chunk("c1", 0.50)],
            [make_chunk("c1", 0.66), make_chunk("c2", 0.55)],
            [],
        ])
        state = make_state(plan=[{"step_id": "vector_narrative", "engine": "vector",
                                 "depends_on": [], "topics": ["투자 위험", "기초지수", "보수", "여분"]}])
        out = self.run_node(search, state=state)

        result = out["step_results"]["vector_narrative"]
        self.assertEqual(len(result["queries"]), 3)  # VECTOR_MAX_TOPICS로 잘림
        self.assertEqual(result["queries"][0], "이 상품의 투자 위험은? 투자 위험")
        self.assertEqual([(c["chunk_id"], c["score"]) for c in result["chunks"]],
                         [("c1", 0.66), ("c2", 0.55)])

    def test_low_confidence_when_every_hit_is_below_floor(self):
        search = mock.Mock(return_value=[make_chunk("c1", 0.30)])
        result = self.run_node(search)["step_results"]["vector_narrative"]
        self.assertEqual(result["status"], "low_confidence")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["raw_top"], [("c1", 0.3)])

    def test_no_document_when_scoped_products_have_no_coverage(self):
        search = mock.Mock(return_value=[])
        state = make_state(intent={"target_entities": [
            {"surface_form": "TIGER 반도체", "entity_type": "product_name"}]})
        result = self.run_node(
            search, state=state, product_ids=["etf_kr:A", "etf_kr:B"],
            coverage={"etf_kr:A": {"status": "unavailable"},
                      "etf_kr:B": {"status": "download_failed"}},
        )["step_results"]["vector_narrative"]

        self.assertEqual(result["status"], "no_document")
        self.assertEqual(result["product_scope"]["coverage"],
                         {"matched": 0, "unavailable": 1, "download_failed": 1, "unknown": 0})
        self.assertIn("미확보 2", result["note"])

    def test_no_product_match_skips_search_when_scope_unresolved(self):
        # 상품명을 지목했지만 product_master 완전일치에 실패하면 전체 문서로
        # 넓히지 않는다 - 다른 상품의 투자설명서를 인용하는 오답을 막는다.
        search = mock.Mock(return_value=[make_chunk("c1", 0.7)])
        state = make_state(intent={"target_entities": [{"surface_form": "TIGER 한중반도체 ETF", "entity_type": "product_name"}]})
        with patch_vector(search, product_ids=[]) as patched:
            result = nodes.vector_search_node(state)["step_results"]["vector_narrative"]
        self.assertEqual(result["status"], "no_product_match")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["product_scope"]["names"], ["TIGER 한중반도체 ETF"])
        patched["embed"].assert_not_called()
        search.assert_not_called()

    def test_no_hit_when_unscoped_search_returns_nothing(self):
        search = mock.Mock(return_value=[])
        with patch_vector(search) as patched:
            result = nodes.vector_search_node(make_state())["step_results"]["vector_narrative"]
        self.assertEqual(result["status"], "no_hit")
        self.assertEqual(result["product_scope"]["product_ids"], [])
        patched["resolve_product_ids"].assert_not_called()  # 스코프가 비면 질의하지 않는다
        self.assertIsNone(search.call_args.kwargs["product_ids"])

    def test_exception_abstains_only_that_step(self):
        search = mock.Mock(side_effect=RuntimeError("pgvector down"))
        out = self.run_node(search)
        result = out["step_results"]["vector_narrative"]
        self.assertEqual(result["status"], "abstain_vector_unavailable")
        self.assertEqual(result["chunks"], [])
        self.assertIn("pgvector down", result["error"])
        self.assertIn("검색 불가", out["trace"][0])

    def test_skips_when_no_ready_vector_step(self):
        state = make_state(plan=[{"step_id": "rdb_1", "engine": "rdb", "depends_on": []}])
        with patch_vector(mock.Mock()) as patched:
            out = nodes.vector_search_node(state)
        self.assertNotIn("step_results", out)
        self.assertIn("건너뜀", out["trace"][0])
        patched["embed"].assert_not_called()


class VectorMergeTest(unittest.TestCase):
    def test_merge_results_node_emits_one_row_per_chunk(self):
        state = {"step_results": {"vector_narrative": {
            "engine": "vector", "status": "ok",
            "chunks": [nodes._normalize_chunk(make_chunk("c1", 0.6234))],
        }}}
        rows = nodes.merge_results_node(state)["merged_rows"]

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["_domain"], "vector")
        self.assertEqual(row["_step_id"], "vector_narrative")
        self.assertEqual(row["유사도"], 0.623)
        self.assertEqual(row["기준일"], "2026-08-21")
        self.assertEqual(row["상품ID"], "etf_kr:KR7449690007")
        self.assertEqual(len(row["인용"]), 400)

    def test_retrieved_context_reports_status_and_citations(self):
        state = {"step_results": {"vector_narrative": {
            "engine": "vector", "status": "no_document", "count": 0,
            "chunks": [], "note": "스코프 2상품(문서 확보 0, 미확보 2), 청크 0건(≥0.45)",
        }}, "plan": []}
        context = nodes._build_retrieved_context(state)
        self.assertIn("[Vector] status=no_document", context)
        self.assertIn("미확보 2", context)

    def test_merge_results_node_tags_row_with_section_label(self):
        state = {"step_results": {"vector_narrative": {
            "engine": "vector", "status": "ok",
            "chunks": [nodes._normalize_chunk(make_chunk("c1", 0.6, section_type="risk"))],
        }}}
        row = nodes.merge_results_node(state)["merged_rows"][0]
        self.assertEqual(row["섹션"], "투자위험")


class AnswerContextTest(unittest.TestCase):
    """generate_answer_node가 요청 항목·문서 근거 상태를 답변 LLM에 넘기는지
    (DB·실제 LLM 호출 없이 _llm_answer만 mock)."""

    def test_describe_requested_items_joins_fields_and_topics(self):
        self.assertEqual(
            nodes._describe_requested_items(
                {"output_requirements": {"fields": ["순자산"], "narrative_topics": ["운용 전략"]}}
            ),
            "구조화 값: 순자산; 서술 주제: 운용 전략",
        )

    def test_describe_requested_items_empty_falls_back(self):
        self.assertEqual(
            nodes._describe_requested_items({}),
            "(명시된 항목 없음 - 질문 원문을 따른다)",
        )

    def test_describe_vector_status_reports_uncovered_topic(self):
        step_results = {"vector_narrative": {
            "engine": "vector", "status": "topic_not_covered",
            "note": "스코프 1상품(문서 확보 1, 미확보 0), 청크 0건(≥0.45), 요청 주제 미확보: 운용 전략(투자목적·운용전략 섹션 없음)",
            "topic_coverage": {"requested": {"objective_strategy": ["운용 전략"]},
                                "uncovered": {"objective_strategy": ["운용 전략"]}},
        }}
        out = nodes._describe_vector_status(step_results)
        self.assertIn("status=topic_not_covered", out)
        self.assertIn("운용 전략(투자목적·운용전략 섹션 없음)", out)

    def test_describe_vector_status_handles_missing_topic_coverage(self):
        step_results = {"vector_narrative": {
            "engine": "vector", "status": "abstain_vector_unavailable",
            "error": "RuntimeError: pgvector down",
        }}
        out = nodes._describe_vector_status(step_results)
        self.assertIn("pgvector down", out)

    def test_describe_vector_status_no_vector_results(self):
        self.assertEqual(nodes._describe_vector_status({}), "(문서 검색 단계 없음)")

    def test_generate_answer_node_passes_requested_items_and_vector_status(self):
        mock_llm = mock.Mock()
        mock_llm.with_structured_output.return_value.invoke.return_value = {
            "think_trace": "t", "answer": "a",
        }
        state = {
            "question_id": "Q1",
            "question": "이 펀드의 운용 전략을 설명해줘",
            "intent": {"output_requirements": {"fields": [], "narrative_topics": ["운용 전략"]}},
            "merged_rows": [{"itm_nm": "X", "_domain": "펀드", "_step_id": "rdb_펀드"}],
            "step_results": {
                "vector_narrative": {
                    "engine": "vector", "status": "topic_not_covered",
                    "note": "요청 주제 미확보: 운용 전략(투자목적·운용전략 섹션 없음)",
                    "topic_coverage": {"requested": {"objective_strategy": ["운용 전략"]},
                                        "uncovered": {"objective_strategy": ["운용 전략"]}},
                },
                "rdb_펀드": {"engine": "rdb", "role": "target", "domain": "펀드",
                            "rows": [{"itm_nm": "X"}], "count": 1, "sql": "SELECT 1"},
            },
            "plan": [],
            "trace": [],
        }
        with mock.patch.object(nodes, "_llm_answer", mock_llm):
            result = nodes.generate_answer_node(state)

        human_message = mock_llm.with_structured_output.return_value.invoke.call_args.args[0][1][1]
        self.assertIn("[질문이 요구한 항목]", human_message)
        self.assertIn("운용 전략", human_message)
        self.assertIn("[문서 근거 상태]", human_message)
        self.assertIn("topic_not_covered", human_message)

        final = json.loads(result["answer"])
        self.assertEqual(final["answer"], "a")


if __name__ == "__main__":
    unittest.main()
