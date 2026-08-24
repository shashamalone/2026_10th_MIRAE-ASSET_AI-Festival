# -*- coding: utf-8 -*-
"""LangGraph State.

spec(agent-spec-0822.md §10)의 11필드를 다 넣지 않는다. 아직 아무도 쓰지 않는
필드를 미리 만들면 규격이 확정될 때 두 번 고친다. 값을 쓰는 노드가 생길 때 붙인다.
"""
from typing import TypedDict


class State(TypedDict):
    question_id: str
    question: str
    intent: dict          # 1단계 Query Frame (agent/query_frame.py, 14필드)
    schema_hits: list     # 2단계 bond_schema_search() 결과 Top-K
    trace: list           # 노드가 남기는 관측 기록. 주최측 규격의 think_trace 로 나간다
    answer: str
