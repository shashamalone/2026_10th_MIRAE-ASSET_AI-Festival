"""
graph.py

LangGraph StateGraph 조립. 목표로 준 다이어그램(사용자 질문 입력 ->
질문 분석 노드 -> DB 검색 흐름 결정 노드 -> {RDB, GraphDB, VectorDB}
검색 노드 -> 결과 합치기 노드 -> 답변 생성 노드 -> 최종 답변 출력)을
그대로 구현한다.

[의존관계 기반 웨이브 스케줄러 — 2026-09-02]
plan_query_db.py가 각 단계에 계산해 두는 depends_on(§4, relation.
subject_domain 기반 정밀 판정)을 실제 실행 순서에 반영해야 하므로, 예전의
"needs_rdb/needs_graph/needs_vector가 True면 전부 같은 슈퍼스텝에서 병렬"
방식(route_after_plan, 이제 삭제)을 dispatch() 기반 웨이브 구조로
바꿨다. dispatch는 plan_query 뒤와 세 검색 노드 각각의 뒤에서 반복
호출되는 라우터다 - 매번 state.py의 ready_step_ids(plan, done)로 "이번에
새로 실행 가능해진 단계"를 계산해서, 그 단계들의 엔진만큼만 검색 노드를
스케줄한다. 더 준비된 단계가 없으면 merge_results로 보낸다.

이 구조에서 각 케이스가 어떻게 도는지:
  - RDB만 필요 -> 웨이브 1에 rdb_search만 -> 다음 dispatch에서 merge_results
  - Graph만 필요 -> 웨이브 1에 graph_search만
  - 서로 무관한 Graph+RDB(§4에서 depends_on=[]로 판정된 경우) -> 웨이브
    1에 graph_search와 rdb_search가 동시에 선택됨(진짜 병렬)
  - Graph->RDB 의존(terminal relation의 subject_domain이 매칭되는 경우)
    -> 웨이브 1엔 graph_search만(RDB는 아직 depends_on 미충족), 웨이브
    2에 rdb_search
  - Graph(체인)->RDB->Vector -> 웨이브 1 Graph, 웨이브 2 RDB, 웨이브 3 Vector

각 검색 노드(nodes.py의 rdb_search_node/graph_search_node/
vector_search_node)도 이제 자기 엔진의 전체 단계가 아니라 "이번 웨이브에
준비되고 아직 안 한 단계"만 처리하도록 같은 ready_step_ids로 걸러낸다 -
그래야 같은 엔진이 서로 다른 웨이브에 걸쳐 다시 호출돼도(예: RDB 단계
하나는 의존관계가 없어 1웨이브에, 다른 RDB 단계는 Graph를 기다려야 해서
2웨이브에 실행되는 경우) 중복 실행이나 누락 없이 정확히 자기 몫만
처리한다.

[지금 이 상태에서 실제로 도는 경로]
RDB 검색 노드는 nodes.py에서 실제 원격 API 호출까지 전부 구현되어 있다.
GraphDB/VectorDB 검색 노드는 라우팅(이 자리로 오는 것과 웨이브 순서)까지만
맞고 내부 조회 로직은 스텁이다. 그래서 지금 이 그래프를 실행하면 RDB-only
질문은 끝까지 정상 동작하고, Graph/Vector가 필요한 질문은 해당 단계에서
빈 결과만 나오지만 "언제(몇 번째 웨이브에) 실행됐는지"는 이미 올바르다.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.nodes import *
from agent.plan_query_db import plan_query_node
from agent.state import ChatbotState, ready_step_ids

# dispatch가 고를 수 있는 다음 노드 전부. 각 소스 노드(plan_query, 세 검색
# 노드)가 전부 같은 목적지 목록을 쓴다 - 자기 자신으로도 다시 돌아갈 수
# 있어야 한다(같은 엔진이 여러 웨이브에 걸쳐 필요한 경우). LangGraph가
# 그래프 구조를 정적으로 검증하므로 이론상 가능한 다음 목적지를 전부
# 선언해 둬야 한다.
_WAVE_TARGETS = ["graph_search", "rdb_search", "vector_search", "merge_results"]


def dispatch(state: ChatbotState) -> list[str]:
    """매 웨이브 다시 계산하는 라우터. state.step_results에 이미 쌓인
    step_id 집합(done)을 기준으로 이번에 새로 준비된 단계들을 찾고, 그
    단계들의 엔진 집합만큼 검색 노드를 스케줄한다. 준비된 단계가 하나도
    없으면(모든 단계가 끝났거나, plan_query_db._topo_sort_relations가
    이미 막아주지만 혹시 모를 순환 등 이상 상황) merge_results로 바로
    보낸다 - 무한 루프 방지용 방어 장치다."""
    plan = state.get("plan") or []
    done = set((state.get("step_results") or {}).keys())
    ready_ids = ready_step_ids(plan, done)
    if not ready_ids:
        return ["merge_results"]

    ready_engines = {s["engine"] for s in plan if s["step_id"] in ready_ids}
    targets = []
    if "graph" in ready_engines:
        targets.append("graph_search")
    if "rdb" in ready_engines:
        targets.append("rdb_search")
    if "vector" in ready_engines:
        targets.append("vector_search")
    return targets


def build_graph():
    graph = StateGraph(ChatbotState)

    graph.add_node("receive_question", receive_question_node)
    graph.add_node("analyze_intent", analyze_intent_node)
    graph.add_node("verify_intent", verify_intent_node)
    graph.add_node("plan_query", plan_query_node)
    graph.add_node("rdb_search", rdb_search_node)
    graph.add_node("graph_search", graph_search_node)
    graph.add_node("vector_search", vector_search_node)
    graph.add_node("merge_results", merge_results_node)
    graph.add_node("generate_answer", generate_answer_node)

    graph.set_entry_point("receive_question")
    graph.add_edge("receive_question", "analyze_intent")
    graph.add_edge("analyze_intent", "verify_intent")
    graph.add_edge("verify_intent", "plan_query")

    # DB 검색 흐름 결정 노드 -> {RDB, GraphDB, VectorDB} 웨이브 기반 분기.
    # plan_query와 세 검색 노드 전부 dispatch로 돌아가는 루프 구조다: 한
    # 웨이브가 끝나면 dispatch가 다음으로 준비된 단계들을 다시 계산해서
    # 스케줄하고, 더 없으면 merge_results로 수렴한다.
    graph.add_conditional_edges("plan_query", dispatch, _WAVE_TARGETS)
    graph.add_conditional_edges("graph_search", dispatch, _WAVE_TARGETS)
    graph.add_conditional_edges("rdb_search", dispatch, _WAVE_TARGETS)
    graph.add_conditional_edges("vector_search", dispatch, _WAVE_TARGETS)

    graph.add_edge("merge_results", "generate_answer")
    graph.add_edge("generate_answer", END)

    return graph.compile()


app = build_graph()


if __name__ == "__main__":
    # 그래프 구조만 시각화하고 싶을 때: python graph.py
    print(app.get_graph().draw_mermaid())