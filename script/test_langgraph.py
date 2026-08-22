# -*- coding: utf-8 -*-
"""LangGraph + CLOVA 최소 배선 확인.

증명하려는 것은 셋뿐이다.
  1. LangGraph 노드 안에서 CLOVA를 호출해 값을 받을 수 있다
  2. 노드 사이로 state가 넘어간다
  3. LLM에 맡기면 안 되는 판정을 코드 노드가 덮어쓴다

실행:  python3 script/test_langgraph.py
"""

import pathlib
import sys
import time
from typing import TypedDict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from langgraph.graph import END, START, StateGraph

from test_clova import (INTENT_SCHEMA, INTENT_SYSTEM, chat, load_key,
                        parse_json_loose)

MODEL = "HCX-DASH-002"   # structured outputs로 스키마를 강제한다. 속도 우선이면 HCX-DASH-002. 성능우선이면 HCX-007
RESPONSE_FORMAT = {"type": "json", "schema": INTENT_SCHEMA}

KEY = load_key()


class State(TypedDict):
    question: str
    intent: dict
    notes: list[str]


def node_intent(state: State) -> dict:
    """1단계 — CLOVA로 의도 분류. TBox도 데이터도 보지 않는다."""
    text = chat(KEY, MODEL, INTENT_SYSTEM, state["question"],
                max_tokens=1024, response_format=RESPONSE_FORMAT)
    return {"intent": parse_json_loose(text), "notes": ["intent: clova ok"]}


def node_guard(state: State) -> dict:
    """결정적 보정 — LLM 판단을 코드가 덮어쓴다.

    지목된 상품이 없으면 simple_lookup일 수 없다. 조회할 대상이 없기 때문이다.
    세 모델 모두 "안전한 ETF 추천해줘"를 simple_lookup으로 분류했다 — 프롬프트로
    고치려 하지 말고 여기서 잡는다.
    """
    intent = dict(state["intent"])
    notes = list(state["notes"])
    if intent.get("query_type") == "simple_lookup" and not intent.get("entities"):
        intent["query_type"] = "conditional_search"
        notes.append("guard: entities 없음 → simple_lookup 기각")
    return {"intent": intent, "notes": notes}


def build():
    g = StateGraph(State)
    g.add_node("intent", node_intent)
    g.add_node("guard", node_guard)
    g.add_edge(START, "intent")
    g.add_edge("intent", "guard")
    g.add_edge("guard", END)
    return g.compile()


if __name__ == "__main__":
    app = build()
    for q in ["안전한 ETF 추천해줘",
              "에스케이하이닉스224-2의 발행사와 신용등급 알려줘",
              "에코프로의 자회사를 편입한 ETF 알려줘"]:
        t0 = time.time()
        out = app.invoke({"question": q, "intent": {}, "notes": []})
        i = out["intent"]
        print(f"\n{q}   [{time.time()-t0:.2f}s]")
        print(f"  query_type : {i.get('query_type')}")
        print(f"  domain     : {i.get('domain')}")
        print(f"  entities   : {i.get('entities')}")
        print(f"  keywords   : {i.get('keywords')}")
        for n in out["notes"]:
            print(f"  · {n}")
    print()
