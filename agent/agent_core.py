# -*- coding: utf-8 -*-
"""LangGraph 조립. 이번 MVP는 분기 없이 직선이다."""
from langgraph.graph import END, START, StateGraph

from agent.nodes import answer, classify_intent, search_bond_schema
from agent.state import State


def build():
    g = StateGraph(State)
    g.add_node("classify_intent", classify_intent)
    g.add_node("search_bond_schema", search_bond_schema)
    g.add_node("answer", answer)
    g.add_edge(START, "classify_intent")
    g.add_edge("classify_intent", "search_bond_schema")
    g.add_edge("search_bond_schema", "answer")
    g.add_edge("answer", END)
    return g.compile()


APP = build()


def ask(question: str) -> dict:
    return APP.invoke({"question": question, "intent": {}, "schema_hits": [], "answer": ""})
