# -*- coding: utf-8 -*-
"""Query Frame과 verified plan을 실행 가능한 현재 capability로 제한한다."""
from __future__ import annotations

RDB_TASKS = {"lookup", "filter_rank", "comparison"}
RDB_COMPUTATIONS = {"compare"}
QUERY_TYPES = ("rdb_only", "tbox_validate_only", "graph_only", "graph_then_rdb",
               "graph_then_rdb_vector", "unsupported")
MAX_PLAN_STEPS = 3
ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "query_type": {"type": "string", "enum": list(QUERY_TYPES)},
        "execution_plan": {"type": "array", "maxItems": MAX_PLAN_STEPS},
        "reason": {"type": "string"},
    },
    "required": ["query_type", "execution_plan", "reason"],
}


def select_route(frame: dict, plan: dict) -> dict:
    """고정 enum/step 상한을 지키는 실행 계약을 반환한다.

    Graph/Vector route는 실제 vertical slice가 통과하기 전까지 활성화하지 않는다.
    """
    def unsupported(reason: str) -> dict:
        return {"query_type": "unsupported", "execution_plan": [], "reason": reason}

    if not plan.get("domain") or plan.get("unresolved"):
        return unsupported("도메인 또는 binding이 완전히 해소되지 않았습니다.")
    if len(frame.get("domain_candidates") or []) != 1:
        return unsupported("여러 상품 도메인을 함께 실행하는 경로는 아직 지원하지 않습니다.")
    if frame.get("task") not in RDB_TASKS:
        return unsupported(f"현재 RDB가 지원하지 않는 task입니다: {frame.get('task')}")
    kinds = {x.get("kind") for x in frame.get("computation") or []}
    if not kinds <= RDB_COMPUTATIONS:
        return unsupported(f"현재 지원하지 않는 계산입니다: {sorted(kinds - RDB_COMPUTATIONS)}")
    result = {"query_type": "rdb_only",
              "execution_plan": [{"id": "A", "engine": "rdb", "depends_on": []}],
              "reason": "verified single-domain RDB capability"}
    assert len(result["execution_plan"]) <= MAX_PLAN_STEPS
    return result
