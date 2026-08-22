"""
전체 그래프 조립.

plan_routing 다음이 이제 조건부다. 유형6(답변불가)로 판정되면 dispatch,
DB 노드, generate_answer를 전부 건너뛰고 format_abstain으로 바로 가서
답을 만든다. 그 외에는 기존과 동일하게 dispatch 루프를 돈다.
"""
from __future__ import annotations

import asyncio
from typing import Literal

from langgraph.graph import END, START, StateGraph

from .engines import EngineRegistry
from .node import (
    build_engine_nodes,
    combine_db_results,
    dispatch,
    format_abstain,
    generate_answer,
    plan_routing,
    route_by_readiness,
)
from .state import AgentState


def _route_after_plan(state: AgentState) -> Literal["dispatch", "format_abstain"]:
    """execution_plan이 비어 있으면(=plan_routing이 abstain 판정) format_abstain으로,
    아니면 평소대로 dispatch로 보낸다."""
    if not state.get("execution_plan"):
        return "format_abstain"
    return "dispatch"


def build_graph(engines: EngineRegistry):
    graph = StateGraph(AgentState)

    graph.add_node("plan_routing", plan_routing)
    graph.add_node("dispatch", dispatch)
    for name, node_fn in build_engine_nodes(engines).items():
        graph.add_node(name, node_fn)
    graph.add_node("combine_db_results", combine_db_results)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("format_abstain", format_abstain)

    graph.add_edge(START, "plan_routing")
    graph.add_conditional_edges(
        "plan_routing", _route_after_plan, ["dispatch", "format_abstain"]
    )
    graph.add_conditional_edges("dispatch", route_by_readiness, ["graph_node", "rdb_node", "vector_node", "combine_db_results"])
    graph.add_edge("graph_node", "dispatch")
    graph.add_edge("rdb_node", "dispatch")
    graph.add_edge("vector_node", "dispatch")
    graph.add_edge("combine_db_results", "generate_answer")
    graph.add_edge("generate_answer", END)
    graph.add_edge("format_abstain", END)

    return graph.compile()


async def run_agent(
    question_id: str,
    question: str,
    decomposed_conditions: list[str],
    metadata_context: list[dict],
    engines: EngineRegistry,
    schema_hint: str = "",
    timeout_s: float = 14.0,
) -> dict:
    """1, 2단계 결과물을 받아 3단계부터 답변 생성까지 실행하는 진입점.

    schema_hint는 선택 입력이다. engines.build_schema_hint(engines.rdb)로
    미리(그래프를 여러 번 실행하기 전에 한 번만) 만들어서 넘기면, plan_routing이
    실제 테이블/컬럼 이름을 참고해서 더 정확한 SQL을 짤 수 있다. 비워두면
    기존처럼 metadata_context만으로 계획을 만든다.
    """
    app = build_graph(engines)
    try:
        final_state = await asyncio.wait_for(
            app.ainvoke(
                {
                    "question_id": question_id,
                    "question": question,
                    "decomposed_conditions": decomposed_conditions,
                    "metadata_context": metadata_context,
                    "schema_hint": schema_hint,
                    "step_results": {},
                    "think_trace": [],
                },
                config={"recursion_limit": 30},
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        return {
            "question_id": question_id,
            "retrieved_context": [],
            "think_trace": [f"{timeout_s}초 내에 완료되지 않아 중단됨"],
            "answer": "제한 시간 내에 답변을 생성하지 못했습니다.",
            "evidence": [],
        }

    return {
        "question_id": question_id,
        "retrieved_context": final_state.get("retrieved_context", []),
        "think_trace": final_state.get("think_trace", []),
        "answer": final_state["answer"],
        "evidence": final_state.get("evidence", []),
    }