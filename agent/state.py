"""
전체 파이프라인 상태 정의.

question, decomposed_conditions(1단계), metadata_context(2단계)는 다른 담당자가
채우는 입력이다. 이 모듈은 execution_plan부터 answer까지, 즉 3단계(Plan & Routing)
와 그 이후 실행/통합/답변 생성 노드를 담당한다.
"""
from __future__ import annotations

import operator
from typing import Literal, TypedDict
from typing_extensions import Annotated, NotRequired

EngineName = Literal["graph", "rdb", "vector"]


class PlanStep(TypedDict):
    """3단계에서 LLM이 생성하는 실행 계획의 개별 단계."""

    id: str
    engine: EngineName
    query: str  # SPARQL / SQL / 벡터 검색어. 상위 단계 결과 주입 전 원형.
    depends_on: list[str]


class StepResult(TypedDict):
    """DB 노드 실행 후 각 단계의 결과."""

    id: str
    engine: EngineName
    ok: bool
    data: NotRequired[object]
    error: NotRequired[str]
    elapsed_ms: NotRequired[float]


def merge_step_results(left: dict[str, StepResult], right: dict[str, StepResult]) -> dict[str, StepResult]:
    """graph_node, rdb_node, vector_node가 같은 슈퍼스텝에서 병렬로 실행되며
    각자 새로 계산한 항목만 반환하므로, step_results는 dict 병합 리듀서가 필요하다.
    (단순 TypedDict 필드였다면 병렬 노드가 동시에 같은 채널에 쓰려다 LangGraph가
    InvalidUpdateError를 던진다. 실제로 재현해서 확인한 문제다.)"""
    return {**left, **right}


class AgentState(TypedDict):
    # 공통 입력
    question_id: str
    question: str

    # 1단계 결과 (다른 담당자 노드가 채움, 이 모듈은 입력으로만 사용)
    decomposed_conditions: NotRequired[list[str]]

    # 2단계 결과 (다른 담당자 노드가 채움, 이 모듈은 입력으로만 사용)
    metadata_context: NotRequired[list[dict]]  # [{"name": "fp:riskGrade", "description": "..."}]

    # plan_routing 호출 전에 run_agent가 채워주는 선택 입력. 실제 DB에서 미리
    # 조회해둔 테이블/컬럼 목록 텍스트. engines.build_schema_hint()로 만든다.
    schema_hint: NotRequired[str]

    # 3단계: Plan & Routing (이 모듈 담당)
    execution_plan: NotRequired[list[PlanStep]]
    query_type: NotRequired[str]

    # plan_routing이 유형6(TBox 검증, 답변불가)로 판단했을 때만 채워진다.
    abstain_reason: NotRequired[str]

    # DB 노드(graph_node/rdb_node/vector_node) 실행 결과. 병렬 실행을 위한 병합 리듀서 적용.
    step_results: Annotated[dict[str, StepResult], merge_step_results]

    # combine_db_results 산출물
    combined_context: NotRequired[str]
    retrieved_context: NotRequired[list[dict]]

    # generate_answer 산출물
    answer: NotRequired[str]
    evidence: NotRequired[list[dict]]

    # 관측/디버깅. 여러 노드가 이어서 기록하므로 누산 리듀서 사용.
    think_trace: Annotated[list[str], operator.add]
    timing_ms: NotRequired[dict[str, float]]