# -*- coding: utf-8 -*-
"""LangGraph 조립. 이번 MVP는 분기 없이 직선이다."""
from langgraph.graph import END, START, StateGraph

from agent.nodes import answer, extract_query_frame, search_bond_schema
from agent.state import State


def build():
    g = StateGraph(State)
    g.add_node("extract_query_frame", extract_query_frame)
    g.add_node("search_bond_schema", search_bond_schema)
    g.add_node("answer", answer)
    g.add_edge(START, "extract_query_frame")
    g.add_edge("extract_query_frame", "search_bond_schema")
    g.add_edge("search_bond_schema", "answer")
    g.add_edge("answer", END)
    return g.compile()


APP = build()


def ask(question: str, question_id: str = "") -> dict:
    return APP.invoke({"question_id": question_id, "question": question,
                       "intent": {}, "schema_hits": [], "trace": [], "answer": ""})
