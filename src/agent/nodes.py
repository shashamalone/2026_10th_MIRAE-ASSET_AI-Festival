# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime as dt
import decimal

from agent import query_frame
from agent import text2sparql
from agent.state import State
from tools import rdb, route, schema_context, validate


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
    if state["intent"].get("task") == "relation":
        grounded = {"engine": "graph", "domain": None, "unresolved": [],
                    "concepts": [], "entities": state["intent"].get("entities") or []}
    else:
        grounded = schema_context.ground(state["question"], state["intent"])
    trace = list(state.get("trace") or [])
    trace.append(f"grounding: domain={grounded.get('domain')} concepts={grounded.get('concepts')} "
                 f"unresolved={len(grounded.get('unresolved') or [])}")
    return {"metadata_context": grounded, "plan": grounded, "trace": trace}


def validate_query(state: State) -> dict:
    intent, grounded = state["intent"], state["metadata_context"]
    # RDB로 완결되지 않은 lookup은 route가 Graph로 폴백하므로 RDB용 ABSTAIN으로 끊지 않는다.
    graph_fallback = (intent.get("task") == "lookup"
                      and (not grounded.get("domain") or grounded.get("unresolved"))
                      and any(x.get("text") for x in intent.get("entities") or []))
    if intent.get("task") == "relation" or graph_fallback:
        abstain = validate.validate_graph_request(state["question"], intent)
    else:
        abstain = validate.validate_query(state["question"], grounded)
    trace = list(state.get("trace") or [])
    trace.append("validation: PASS" if not abstain else f"validation: {abstain['code']}")
    return {"abstain": abstain, "trace": trace}


def select_route(state: State) -> dict:
    selected = route.select_route(state["intent"], state["plan"])
    query_type, reason = selected["query_type"], selected["reason"]
    abstain = None
    if query_type == "unsupported":
        abstain = {"code": "ABSTAIN_UNSUPPORTED_ROUTE", "reason": reason}
    trace = list(state.get("trace") or [])
    trace.append(f"route: {query_type} steps={len(selected['execution_plan'])} — {reason}")
    return {"route": selected, "abstain": abstain, "trace": trace}


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


def execute_graph(state: State) -> dict:
    trace = list(state.get("trace") or [])
    route_type = state.get("route", {}).get("query_type")
    result = text2sparql.run(
        state["question"], frame=state["intent"],
        execute_rdb=route_type == "graph_then_rdb",
    )
    trace.extend(result.get("trace") or [])
    abstain = None
    if result.get("status", "").startswith("abstain"):
        abstain = {"code": result["status"].upper(),
                   "reason": (result.get("trace") or [result["status"]])[-1]}
    return {"results": result, "evidence": result.get("evidence") or [],
            "abstain": abstain, "trace": trace}


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
    if state.get("route", {}).get("query_type") in {"graph_only", "graph_then_rdb"}:
        return _render_graph_answer(state)
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


def _render_graph_answer(state: State) -> dict:
    result = state.get("results") or {}
    if state.get("route", {}).get("query_type") == "graph_then_rdb" and result.get("rdb_result"):
        ranked = result["rdb_result"]
        if ranked.get("abstain"):
            return {"answer": f"확인할 수 없음: {ranked['abstain']['reason']}"}
        rows = ranked.get("rows") or []
        evidence = ranked.get("evidence") or []
        by_col = {e["source_column"]: e for e in evidence}
        lines = []
        for row in rows:
            values = []
            for column, raw in row.items():
                item = by_col[column]
                values.append(f"{item['label']}={_scalar(raw)} "
                              f"[{item['source_table']}.{column}, 기준일 {item['as_of']}]")
            lines.append("; ".join(values))
        return {"answer": "\n".join(lines) if lines else "조건에 맞는 ETF를 확인할 수 없습니다."}

    rows = result.get("rows") or []
    if not rows:
        return {"answer": "근거가 완비된 관계를 확인할 수 없습니다."}
    lines = [f"근거가 확인된 관계는 총 {len(rows):,}건입니다."]
    row_evidence = False
    for row in rows[:20]:
        values, evidence = _split_row_evidence(row)
        evidence["_document_title"] = (evidence.get("_document_title")
                                       or evidence.get("_document"))
        tags = [f"{label} {evidence[suffix]}"
                for suffix, label in (("_as_of", "관계 기준일"), ("_source", "출처"),
                                      ("_document_title", "근거"))
                if evidence.get(suffix)]
        line = "- " + ", ".join(f"{k}={_scalar(v)}" for k, v in values.items() if v is not None)
        if tags:
            row_evidence = True
            line += f" [{', '.join(tags)}]"
        lines.append(line)
    if len(rows) > 20:
        lines.append(f"- 나머지 {len(rows) - 20:,}건은 응답 길이상 생략했습니다.")
    if not row_evidence:
        lines.extend(_tbox_source_lines(result.get("evidence") or []))
    return {"answer": "\n".join(lines)}


# 노드 id prefix(relation_/holding_/...)에 의존하지 않도록 suffix로 evidence 컬럼을 가른다.
_EVIDENCE_SUFFIXES = ("_as_of", "_source", "_document_title", "_document_publisher",
                      "_document_date", "_document_quote", "_document")


def _split_row_evidence(row: dict) -> tuple[dict, dict]:
    values, evidence = {}, {}
    for key, raw in row.items():
        suffix = next((s for s in _EVIDENCE_SUFFIXES if key.endswith(s)), None)
        if suffix:
            evidence.setdefault(suffix, raw)
        else:
            values[key] = raw
    return values, evidence


def _tbox_source_lines(evidence: list[dict]) -> list[str]:
    """행별 근거가 없을 때 TBox 출처 애노테이션을 답변 말미에 붙인다(없으면 무시)."""
    seen = []
    for item in evidence:
        if item.get("kind") != "tbox_source":
            continue
        as_of = (item.get("as_of_rule") or "@2026-08-24").split("@")[-1]
        text = (f"[출처 {item.get('source_table')}.{item.get('source_column')}, "
                f"적재 기준일 {as_of} 스냅샷]")
        if text not in seen:
            seen.append(text)
    return seen
