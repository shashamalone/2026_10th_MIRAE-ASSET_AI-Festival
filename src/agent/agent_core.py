# -*- coding: utf-8 -*-
"""RDB 14문항 vertical slice LangGraph."""
from langgraph.graph import END, START, StateGraph

from agent.nodes import (execute_rdb, extract_query_frame, ground_query,
                         render_answer, select_route, validate_query,
                         verify_results)
from agent.state import State


def _after_validation(state: State) -> str:
    return "render_answer" if state.get("abstain") else "select_route"


def _after_routing(state: State) -> str:
    return "execute_rdb" if state.get("route", {}).get("query_type") == "rdb_only" else "render_answer"


def build():
    graph = StateGraph(State)
    graph.add_node("extract_query_frame", extract_query_frame)
    graph.add_node("ground_query", ground_query)
    graph.add_node("validate_query", validate_query)
    graph.add_node("select_route", select_route)
    graph.add_node("execute_rdb", execute_rdb)
    graph.add_node("verify_results", verify_results)
    graph.add_node("render_answer", render_answer)
    graph.add_edge(START, "extract_query_frame")
    graph.add_edge("extract_query_frame", "ground_query")
    graph.add_edge("ground_query", "validate_query")
    graph.add_conditional_edges("validate_query", _after_validation,
                                {"select_route": "select_route", "render_answer": "render_answer"})
    graph.add_conditional_edges("select_route", _after_routing,
                                {"execute_rdb": "execute_rdb", "render_answer": "render_answer"})
    graph.add_edge("execute_rdb", "verify_results")
    graph.add_edge("verify_results", "render_answer")
    graph.add_edge("render_answer", END)
    return graph.compile()


APP = build()


def to_response(state: State) -> dict:
    return {"question_id": state.get("question_id", ""),
            "question": state["question"],
            "retrieved_context": state.get("evidence") or [],
            "think_trace": state.get("trace") or [],
            "answer": state.get("answer", "")}


def ask(question: str, question_id: str = "") -> dict:
    initial = {"question_id": question_id, "question": question, "intent": {},
               "metadata_context": {}, "plan": {}, "route": {}, "results": {}, "evidence": [],
               "abstain": None, "trace": [], "answer": ""}
    return to_response(APP.invoke(initial))
