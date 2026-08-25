# -*- coding: utf-8 -*-
"""RDB vertical slice 노드. LLM은 Query Frame 1회에만 사용한다."""
from __future__ import annotations

import datetime as dt
import decimal

from agent import query_frame
from agent.state import State
from tools import rdb, schema_context, validate


def extract_query_frame(state: State) -> dict:
    """1단계 — 자연어 의미 후보. 별도 audit LLM은 사용하지 않는다."""
    try:
        frame = query_frame.extract(state["question"], use_audit=False)
    except Exception as e:
        frame = query_frame.empty_frame()
        frame["_error"] = f"{type(e).__name__}: {e}"
    trace = [f"intent: task={frame['task']} domain={frame['domain_candidates']} "
             f"entities={len(frame['entities'])} constraints={len(frame['constraints'])}"]
    if frame.get("_error"):
        trace.append(f"intent 추출 실패 — 안전 중단: {frame['_error']}")
    return {"intent": frame, "trace": trace}


def ground_query(state: State) -> dict:
    grounded = schema_context.ground(state["question"], state["intent"])
    trace = list(state.get("trace") or [])
    trace.append(f"grounding: domain={grounded.get('domain')} concepts={grounded.get('concepts')} "
                 f"unresolved={len(grounded.get('unresolved') or [])}")
    return {"metadata_context": grounded, "plan": grounded, "trace": trace}


def validate_query(state: State) -> dict:
    abstain = validate.validate_query(state["question"], state["metadata_context"])
    trace = list(state.get("trace") or [])
    trace.append("validation: PASS" if not abstain else f"validation: {abstain['code']}")
    return {"abstain": abstain, "trace": trace}


def execute_rdb(state: State) -> dict:
    trace = list(state.get("trace") or [])
    try:
        result = rdb.execute(state["plan"])
    except Exception as e:
        result = {"rows": [], "columns": [], "evidence": [],
                  "abstain": {"code": "ABSTAIN_EXECUTION_FAILED",
                              "reason": f"RDB 실행 실패: {type(e).__name__}: {e}"}}
    trace.append(f"rdb: rows={len(result.get('rows') or [])} "
                 f"status={'ABSTAIN' if result.get('abstain') else 'PASS'}")
    return {"results": result, "evidence": result.get("evidence") or [],
            "abstain": result.get("abstain"), "trace": trace}


def verify_results(state: State) -> dict:
    if state.get("abstain"):
        return {}
    expected = [x["source_column"] for x in state.get("evidence") or []]
    got = state.get("results", {}).get("columns") or []
    abstain = None
    if expected != got:
        abstain = {"code": "ABSTAIN_EVIDENCE_MISMATCH",
                   "reason": f"결과 컬럼과 evidence 계약 불일치: expected={expected}, got={got}"}
    trace = list(state.get("trace") or [])
    trace.append("verify: PASS" if not abstain else "verify: ABSTAIN_EVIDENCE_MISMATCH")
    return {"abstain": abstain, "trace": trace}


def _scalar(value):
    if isinstance(value, decimal.Decimal):
        return str(value.normalize()) if value else "0"
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    return value


def render_answer(state: State) -> dict:
    abstain = state.get("abstain")
    if abstain:
        return {"answer": f"확인할 수 없음: {abstain['reason']}"}
    rows = state.get("results", {}).get("rows") or []
    if not rows:
        return {"answer": "주어진 조건과 완전일치하는 상품을 확인할 수 없습니다."}
    evidence = state.get("evidence") or []
    by_col = {e["source_column"]: e for e in evidence}
    sampled = len(rows) > 100
    lines = [f"총 {len(rows):,}건 중 정렬 기준 상위 5건입니다."] if sampled else []
    for row in rows[:5] if sampled else rows:
        values = []
        for column, raw in row.items():
            e = by_col[column]
            values.append(f"{e['label']}={_scalar(raw)} "
                          f"[{e['source_table']}.{column}, 기준일 {e['as_of']}]")
        lines.append("; ".join(values))
    return {"answer": "\n".join(lines)}
