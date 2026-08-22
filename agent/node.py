"""
LangGraph 노드 모음.

이 파일에는 그래프 노드 함수와, 그 노드들이 쓰는 작은 도우미 함수만 둔다.
프롬프트 문구는 prompts.py, LLM 출력 스키마는 schema.py에 따로 있다.

plan_routing: 1, 2단계 결과물을 받아 LLM 1회 호출로 실행 계획을 생성한다.
dispatch + route_by_readiness: 실행 계획의 의존관계를 보고 다음에 실행 가능한
    엔진 노드(들)로 분기한다. 독립적인 단계는 같은 슈퍼스텝에서 병렬로,
    의존관계가 있는 단계는 선행 단계가 끝난 뒤 실행된다.
graph_node / rdb_node / vector_node: 각각 GraphDB, RDB API, Vector API와 통신한다.
combine_db_results: 세 노드의 결과를 하나의 고정된 형식으로 합친다.
generate_answer: 합쳐진 컨텍스트를 LLM에 넣어 최종 답변을 만든다.

dispatch를 별도 노드로 둔 이유
--------------------------------
처음에는 plan_routing과 graph_node/rdb_node/vector_node 각각에 동일한 라우팅
함수를 직접 붙이는 방식을 시도했다. 이 경우 독립 단계 두 개가 같은 슈퍼스텝에서
병렬로 끝나면, 두 노드가 각자 독립적으로 "다음에 뭘 할지"를 재평가하면서
같은 다음 노드를 중복 실행하거나 combine이 여러 번 실행되는 문제가 실제로
재현됐다(langgraph 1.2 기준). 세 엔진 노드가 전부 dispatch라는 노드 하나로
되돌아오게 하고, 라우팅 판단을 dispatch에서만 하도록 바꾸니 병렬로 끝난
두 결과가 먼저 하나의 상태로 합쳐진 뒤 라우팅이 정확히 한 번만 평가되어
문제가 사라졌다.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from langchain_naver import ChatClovaX
from langgraph.types import Send

from .engines import EngineRegistry, inject_results
from .prompt import ANSWER_SYSTEM_PROMPT, PLAN_SYSTEM_PROMPT
from .schema import ANSWER_JSON_SCHEMA, PLAN_JSON_SCHEMA
from .state import AgentState, PlanStep, StepResult

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# _llm_plan = ChatClovaX(model="HCX-005", temperature=0, timeout=8)
# _llm_answer = ChatClovaX(model="HCX-005", temperature=0, timeout=8)

_llm_plan = ChatClovaX(model="HCX-007", temperature=0, timeout=8, thinking={"effort": "none"})
_llm_answer = ChatClovaX(model="HCX-007", temperature=0, timeout=8, thinking={"effort": "none"})



def _trace(msg: str) -> dict:
    return {"think_trace": [msg]}


def plan_routing(state: AgentState) -> dict:
    """
    3단계 노드. 1, 2단계 결과(와 있으면 schema_hint)를 LLM에 보내서 실행
    계획을 만든다. 질의가 답할 수 없는 개념을 묻고 있으면(유형6) steps 없이
    abstain만 표시하고 끝낸다.
    """
    conditions_block = "\n".join(f"- {c}" for c in state["decomposed_conditions"])
    metadata_block = "\n".join(
        f"- {m['name']}: {m['description']}" for m in state["metadata_context"]
    )
    # schema_hint는 run_agent가 미리 채워주는 선택 입력이다 (engines.build_schema_hint).
    # 없으면(2단계 metadata_context만으로 진행하던 이전 방식) 이 구간은 그냥 빠진다.
    schema_hint = state.get("schema_hint", "")
    schema_block = (
        f"\n\n[실제 DB 테이블/컬럼 목록 (raw 스키마)]\n{schema_hint}" if schema_hint else ""
    )

    structured_llm = _llm_plan.with_structured_output(PLAN_JSON_SCHEMA, method="json_schema")
    result = structured_llm.invoke(
        [
            ("system", PLAN_SYSTEM_PROMPT),
            (
                "human",
                f"[분해된 조건]\n{conditions_block}\n\n"
                f"[검색된 속성 메타데이터]\n{metadata_block}"
                f"{schema_block}\n\n"
                f"[사용자 질의]\n{state['question']}",
            ),
        ]
    )

    if result["abstain"]:
        return {
            "execution_plan": [],
            "query_type": "유형6_TBox검증단독",
            "abstain_reason": result["abstain_reason"],
            **_trace(f"답변 불가 판정: {result['abstain_reason']}"),
        }

    plan = result["steps"]
    return {
        "execution_plan": plan,
        "query_type": _classify_type(plan),
        **_trace(f"실행 계획 {len(plan)}단계 생성: {[s['id'] for s in plan]}"),
    }


def _compute_waves(plan: list[dict]) -> list[list[dict]]:
    """
    실행 계획을 dispatch가 실제로 처리할 순서대로 wave 단위로 나눈다.

    입력
        plan: list[dict]
            execution_plan.

    출력
        list[list[dict]]
            wave 순서대로 묶은 리스트. 순환 의존이 있으면 그 지점에서 멈춘다.
    """
    remaining = {s["id"]: s for s in plan}
    done: set[str] = set()
    waves: list[list[dict]] = []
    while remaining:
        wave = [s for s in remaining.values() if all(d in done for d in s["depends_on"])]
        if not wave:
            break
        for s in wave:
            del remaining[s["id"]]
            done.add(s["id"])
        waves.append(wave)
    return waves


def _classify_type(plan: list[dict]) -> str:
    """
    실행 계획을 문서의 유형 이름 중 하나로 분류한다. 유형6(TBox 검증, 답변불가)은
    plan_routing이 abstain을 판정한 시점에 별도로 처리되므로 여기서는 다루지
    않는다. 즉 이 함수가 받는 plan은 항상 유형1~5 중 하나에 해당하려는 시도다.

    입력
        plan: list[dict]
            plan_routing이 만든 실행 계획 (execution_plan과 같은 값).

    출력
        str
            유형 이름. 예: "유형1_RDB단독". 다섯 유형 중 어디에도 구조가
            정확히 맞지 않으면 억지로 끼워 맞추지 않고 "유형_기타"를 돌려준다.
            통계와 로그 표시용일 뿐이고 실제 실행 경로에는 영향을 주지 않는다.
    """
    engines = {s["engine"] for s in plan}
    waves = _compute_waves(plan)

    # 유형1: RDB만 쓰고, 의존관계 없이 한 번에 다 끝남 (wave 1개)
    if engines == {"rdb"} and len(waves) == 1:
        return "유형1_RDB단독"

    # 유형5: Graph만 쓰고, 의존관계 없이 한 번에 끝남 (관계 존재 확인 정도)
    if engines == {"graph"} and len(waves) == 1:
        return "유형5_Graph단독"

    # 유형2: Graph -> RDB 순서로 정확히 2 wave. 방향까지 확인한다
    # (RDB가 먼저 끝나고 Graph가 그 결과를 기다리는 반대 방향은 유형2가 아니다).
    if engines == {"graph", "rdb"} and len(waves) == 2:
        first_engines = {s["engine"] for s in waves[0]}
        second_engines = {s["engine"] for s in waves[1]}
        if first_engines == {"graph"} and second_engines == {"rdb"}:
            return "유형2_Graph순차RDB"

    # 유형3: 세 엔진 다 쓰고, Graph가 끝난 뒤 RDB와 Vector가 같은 wave에서 병렬
    if engines == {"graph", "rdb", "vector"} and len(waves) == 2:
        if {s["engine"] for s in waves[1]} == {"rdb", "vector"}:
            return "유형3_Graph_RDB_Vector병렬"

    # 유형4: wave가 3개 이상 이어지는 다단계 순차 (Graph 재방문이 있는 경우가 많음)
    if len(waves) >= 3:
        return "유형4_Graph다단계순차"

    # 위 다섯 가지 어디에도 깔끔하게 안 맞는 조합
    return "유형_기타"


async def dispatch(state: AgentState) -> dict:
    return {}


def route_by_readiness(state: AgentState) -> Send | list[Send]:
    plan = state["execution_plan"]
    results = state.get("step_results", {})

    if all(s["id"] in results for s in plan):
        return Send("combine_db_results", state)

    ready_engines = {
        s["engine"]
        for s in plan
        if s["id"] not in results and all(dep in results for dep in s["depends_on"])
    }
    if not ready_engines:
        return Send("combine_db_results", state)

    return [Send(f"{engine}_node", state) for engine in ready_engines]


def make_engine_node(engine_name: str, run_query: Callable[[str], Awaitable[object]]):
    async def node(state: AgentState) -> dict:
        plan = state["execution_plan"]
        results = state.get("step_results", {})
        ready = [
            s
            for s in plan
            if s["engine"] == engine_name
            and s["id"] not in results
            and all(dep in results for dep in s["depends_on"])
        ]
        if not ready:
            return {}

        upstream = {k: v for k, v in results.items()}
        outcomes = await asyncio.gather(*(_run_step(s, upstream, run_query) for s in ready))
        new_results = {r["id"]: r for r in outcomes}
        return {
            "step_results": new_results,
            **_trace(f"{engine_name}_node 실행: {[s['id'] for s in ready]}"),
        }

    return node


async def _run_step(
    step: PlanStep,
    upstream: dict[str, StepResult],
    run_query: Callable[[str], Awaitable[object]],
) -> StepResult:
    started = time.monotonic()
    query = inject_results(step["query"], {k: upstream[k] for k in step["depends_on"]})
    try:
        data = await run_query(query)
        return StepResult(
            id=step["id"],
            engine=step["engine"],
            ok=True,
            data=data,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
    except Exception as exc:
        return StepResult(
            id=step["id"],
            engine=step["engine"],
            ok=False,
            error=str(exc),
            elapsed_ms=(time.monotonic() - started) * 1000,
        )


def build_engine_nodes(engines: EngineRegistry) -> dict[str, Callable]:
    return {
        "graph_node": make_engine_node("graph", engines.graph.query),
        "rdb_node": make_engine_node("rdb", engines.rdb.query),
        "vector_node": make_engine_node("vector", engines.vector.search),
    }


def combine_db_results(state: AgentState) -> dict:
    plan = state["execution_plan"]
    results = dict(state.get("step_results", {}))

    for step in plan:
        if step["id"] not in results:
            results[step["id"]] = StepResult(
                id=step["id"],
                engine=step["engine"],
                ok=False,
                error="실행되지 않음 (의존 단계 미해결)",
            )

    successful = [r for r in results.values() if r["ok"]]
    retrieved_context = [
        {"step_id": r["id"], "engine": r["engine"], "data": r["data"]} for r in successful
    ]
    combined = "\n\n".join(f"[{r['id']}/{r['engine']}] {r['data']}" for r in successful)

    return {
        "step_results": results,
        "combined_context": combined,
        "retrieved_context": retrieved_context,
        **_trace(f"결과 통합 완료. 성공 {len(successful)}건, 실패 {len(results) - len(successful)}건"),
    }


def generate_answer(state: AgentState) -> dict:
    structured_llm = _llm_answer.with_structured_output(ANSWER_JSON_SCHEMA, method="json_schema")
    result = structured_llm.invoke(
        [
            ("system", ANSWER_SYSTEM_PROMPT),
            (
                "human",
                f"[근거 데이터]\n{state['combined_context']}\n\n[질문]\n{state['question']}",
            ),
        ]
    )
    evidence = [{"summary": e} for e in result["evidence"]]
    return {"answer": result["answer"], "evidence": evidence, **_trace("답변 생성 완료")}


def format_abstain(state: AgentState) -> dict:
    """
    유형6(TBox 검증, 답변불가) 전용 노드. plan_routing이 이미 답할 수 없다고
    판단한 뒤라서, LLM을 다시 부르지 않고 abstain_reason으로 바로 답을 만든다.
    dispatch, DB 노드, generate_answer를 전부 건너뛰므로 이 유형이 가장 빠르게
    끝난다.
    """
    reason = state.get("abstain_reason", "확인할 수 없는 질의입니다.")
    return {
        "answer": f"답변할 수 없습니다: {reason}",
        "evidence": [],
        "retrieved_context": [],
        **_trace(f"유형6 답변불가 처리: {reason}"),
    }