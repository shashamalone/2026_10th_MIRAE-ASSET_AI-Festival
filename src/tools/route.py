# -*- coding: utf-8 -*-
"""Query Frame과 verified plan을 실행 가능한 현재 capability로 제한한다."""
from __future__ import annotations

RDB_TASKS = {"lookup", "filter_rank", "comparison"}
RDB_COMPUTATIONS = {"compare"}
GRAPH_TASKS = {"relation", "lookup"}
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
    has_seed = any(x.get("text") for x in frame.get("entities") or [])

    def graph_only(reason: str) -> dict:
        return {"query_type": "graph_only",
                "execution_plan": [{"id": "G1", "engine": "graph",
                                    "operation": "graph_traverse", "depends_on": []}],
                "reason": reason}

    def unsupported(reason: str) -> dict:
        # lookup은 RDB 우선이며, binding이 해소되지 않았을 때만 Graph로 폴백한다.
        # 정렬·계산이 붙은 lookup은 Graph가 처리할 수 없으므로 그대로 unsupported다.
        if frame.get("task") == "lookup" and has_seed and not frame.get("computation"):
            return graph_only("RDB binding 미해소 lookup — Graph 탐색으로 폴백")
        return {"query_type": "unsupported", "execution_plan": [], "reason": reason}

    if frame.get("task") == "relation":
        entities = frame.get("entities") or []
        company = next((x for x in entities if x.get("role") == "company"
                        and x.get("text") not in {"자회사", "회사", "기업"}), None)
        relation_text = " ".join(
            x.get("raw", "") + " " + " ".join(x.get("path") or [])
            for x in frame.get("relations") or []
        ).casefold()
        if company and ("자회사" in relation_text or "출자" in relation_text):
            reaches_etf = any(x in relation_text for x in ("etf", "편입", "상장지수"))
            operation = "subsidiary_holding_etfs" if reaches_etf else "subsidiaries"
            if frame.get("ordering") and not reaches_etf:
                return unsupported("기업 자회사 자체의 수익률은 현재 상품 RDB 후처리 대상이 아닙니다.")
            query_type = "graph_then_rdb" if reaches_etf and frame.get("ordering") else "graph_only"
            steps = [{"id": "G1", "engine": "graph", "operation": operation,
                      "depends_on": []}]
            if query_type == "graph_then_rdb":
                steps.append({"id": "R1", "engine": "rdb",
                              "operation": "rank_graph_etf_candidates",
                              "depends_on": ["G1"]})
            result = {"query_type": query_type, "execution_plan": steps,
                      "reason": "verified company subsidiary Graph capability"}
            assert len(steps) <= MAX_PLAN_STEPS
            return result
        if has_seed:
            return graph_only("seed entity가 있는 관계 질의 — Graph 탐색")
        return unsupported("검증된 Graph capability와 seed company를 확정하지 못했습니다.")

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
