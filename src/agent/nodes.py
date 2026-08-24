# -*- coding: utf-8 -*-
"""LangGraph 노드 3종. 검색 로직은 tools/ 에 두고 노드는 배선만 한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import clova  # noqa: E402
from agent import query_frame  # noqa: E402
from agent.state import State  # noqa: E402
from config import ANSWER_MODEL, BOND_TOP_K  # noqa: E402
from tools.bond_schema import bond_schema_search  # noqa: E402

ANSWER_SYSTEM = """너는 금융상품 온톨로지를 근거로 답하는 애널리스트다.

규칙:
- **아래 RETRIEVED SCHEMA의 comment 안에 적힌 문장만** 근거로 삼는다.
- 네가 알고 있는 금융 일반 지식은 쓰지 마라. comment에 없으면 없는 것이다.
  예: comment에 "금리 민감도"만 있으면 "금리가 오르면 가격이 내린다"까지 말하지 마라.
- 근거가 부족하면 부족하다고 말한다: "제공된 스키마에는 …까지만 정의돼 있습니다."
- 수익률 전망이나 투자 추천을 하지 않는다.
- 답변 끝에 근거로 쓴 term_uri를 나열한다.
- 한국어로 3~5문장 이내."""


def extract_query_frame(state: State) -> dict:
    """1단계 — TBox도 물리 스키마도 보지 않고 질의를 의미 요소로 쪼갠다.

    LLM 2회를 쓴다. 분해와 '검증이 필요한 지점' 감사를 한 프롬프트에 같이 시키면
    서로 밀어내는 것이 실측으로 확인됐다 — 감사 트리거를 늘릴수록 다른 슬롯이
    퇴행했고, 떼어내자 Validation Recall 이 1/5 → 5/5 로 올랐다.
    감사 호출은 프롬프트가 짧아 p50 0.76s 로 싸다.
    """
    try:
        frame = query_frame.extract(state["question"], use_audit=True)
    except Exception as e:
        # 추출이 실패해도 파이프라인은 계속 간다. 검색은 질문 원문으로도 된다.
        frame = query_frame.empty_frame()
        frame["_error"] = f"{type(e).__name__}: {e}"
    trace = [f"query_frame: task={frame['task']} domain={frame['domain_candidates']} "
             f"constraints={len(frame['constraints'])} relations={len(frame['relations'])} "
             f"validation={[v['type'] for v in frame['validation_targets']]}"]
    if frame.get("_error"):
        trace.append(f"query_frame 실패 — 질문 원문으로 진행: {frame['_error']}")
    return {"intent": frame, "trace": trace}


def search_bond_schema(state: State) -> dict:
    """2단계 — 벡터 검색. LLM 호출 없음."""
    return {"schema_hits": bond_schema_search(state["question"], k=BOND_TOP_K)}


def _context(hits):
    return "\n\n".join(
        f"[{i}] term_uri: {h['term_uri']}\nlabel: {h['label']}\ncomment: {h['comment']}"
        for i, h in enumerate(hits, 1))


def answer(state: State) -> dict:
    """3단계 — 검색된 주석만 근거로 자연어 답변."""
    hits = state.get("schema_hits") or []
    if not hits:
        return {"answer": "제공된 채권 스키마에서 관련 항목을 찾지 못했습니다."}
    user = f"QUESTION\n{state['question']}\n\nRETRIEVED SCHEMA\n{_context(hits)}"
    try:
        return {"answer": clova.chat(ANSWER_MODEL, ANSWER_SYSTEM, user, max_tokens=700, temperature=0.2)}
    except Exception as e:
        return {"answer": f"[답변 생성 실패] {type(e).__name__}: {e}"}
