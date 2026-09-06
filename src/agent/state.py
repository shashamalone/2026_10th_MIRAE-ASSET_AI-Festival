"""
전체 파이프라인 상태 정의.

[병렬 실행과 리듀서]
LangGraph의 StateGraph는 노드가 반환한 dict를 상태에 병합한다. 리듀서가
없는 키는 기본적으로 "나중 값이 이전 값을 덮어쓰기"로 동작하는데, 여러
노드가 같은 슈퍼스텝에서(=병렬로) 같은 키에 값을 쓰면 충돌 에러가 난다.
RDB/GraphDB/VectorDB 검색 노드 세 개가 DB 검색 흐름 결정 노드 뒤에서
병렬로 실행되면서 step_results와 trace에 동시에 쓰기 때문에, 이 두 키는
리듀서를 반드시 지정해야 한다.

  - step_results: 세 검색 노드가 각자 자기 몫의 {step_id: 결과}만
    반환하고, merge_step_results 리듀서가 이를 얕게 합친다. 예를 들어
    RDB 노드가 {"rdb_채권": {...}}만 반환해도, GraphDB/VectorDB 노드가
    돌려준 다른 step_id들과 합쳐져서 최종 step_results에 전부 남는다.

  - trace: 각 노드가 "이번에 추가할 메시지 리스트"만 반환하고,
    operator.add(리스트 이어붙이기)가 누적한다. 그래서 이 상태를 쓰는
    모든 노드 함수는 지금까지의 trace 전체를 다시 반환하면 안 된다
    (리듀서가 있는데 누적된 전체를 또 반환하면 중복된다). plan_query_db.py
    의 _trace(msg)도 이 규칙에 맞춰 [msg] 하나만 돌려주도록 이미
    고쳐뒀다.

plan/route/intent/merged_rows/answer/question은 파이프라인 안에서 정확히
한 노드만 쓰기 때문에(동시에 쓰는 노드가 없기 때문에) 리듀서가 필요
없다. 기본 동작(마지막 쓴 값 유지)으로 충분하다.

[원본 초안과 달라진 점]
원본에 있던 `from langgraph.graph.message import add_messages`는 여기서
빼뒀다. add_messages는 대화형 챗봇처럼 여러 턴에 걸쳐 누적되는
messages: list 필드에 쓰는 리듀서인데, 이 파이프라인은 질문 하나를
받아 답변 하나를 내는 단발성 배치 작업이라 그런 필드가 필요 없다.
나중에 여러 턴을 기억해야 하는 대화형으로 확장하면 그때 다시 추가하면
된다.

query_intent/plan_query_db/db_routing 세 필드는 intent/plan/route로
정리했다. plan_query_db.py가 실제로 반환하는 키가 "plan"과 "route"
두 개라서, 필드 이름을 그 노드의 실제 반환 키와 맞췄다. db_routing은
route와 의미가 겹쳐서(둘 다 "이 질문을 어디로 보낼지") 뺐다.
"""
from __future__ import annotations

import operator
from typing import Any, TypedDict

from typing_extensions import Annotated


def merge_step_results(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    """RDB/GraphDB/VectorDB 검색 노드가 병렬로 각자 반환한 step_results
    조각을 얕게 합친다. 세 노드가 서로 다른 step_id만 다루므로(plan에서
    이미 엔진별로 나뉘어 있음) 키 충돌은 일어나지 않는다."""
    return {**(a or {}), **(b or {})}


def ready_step_ids(plan: list[dict], done: set[str]) -> set[str]:
    """plan 중 아직 결과가 없고(done에 없고) depends_on이 전부 done에
    있는 단계의 step_id 집합.

    graph.py의 웨이브 라우터(dispatch)가 "이번에 어느 엔진 노드를 스케줄할지"
    계산할 때와, nodes.py의 각 검색 노드가 "이번 웨이브에 내가 실행해야 할
    내 엔진의 단계는 어느 것인지" 걸러낼 때 똑같이 이 함수를 쓴다. "언제
    실행 가능한가"의 정의가 두 곳에 따로 있으면 미묘하게 어긋날 수 있어서
    (예: dispatch는 준비됐다고 판단해 그 엔진 노드를 불렀는데 노드 안의
    필터 기준이 달라 아무 단계도 못 찾는 경우) 하나로 통일했다."""
    return {
        s["step_id"] for s in plan
        if s["step_id"] not in done
        and all(d in done for d in (s.get("depends_on") or []))
    }


class ChatbotState(TypedDict, total=False):
    # --- 입력 ---
    question_id: str 
    question: str

    max_sql_retries: int

    # --- 노드 2: 질문 분석(analyze_intent_node) ---
    intent: dict

    # --- 노드 3: DB 검색 흐름 결정(plan_query_db.plan_query_node) ---
    plan: list[dict] | None
    route: dict | None

    # --- 노드 4: RDB / GraphDB / VectorDB 검색 (병렬) ---
    step_results: Annotated[dict[str, Any], merge_step_results]

    # --- 노드 5: 결과 합치기 ---
    merged_rows: list[dict]

    # --- 노드 6: 답변 생성 ---
    answer: str

    # --- 공통: 실행 로그(디버그/설명용) ---
    trace: Annotated[list[str], operator.add]