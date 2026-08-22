# -*- coding: utf-8 -*-
"""LangGraph State — 채권 MVP 최소 필드."""
from typing import TypedDict


class State(TypedDict):
    question: str
    intent: dict          # {"domain","intent","keywords"}
    schema_hits: list     # bond_schema_search() 결과 Top-K
    answer: str
