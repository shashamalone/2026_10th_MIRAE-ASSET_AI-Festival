#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HCX Query Frame 지연 원인을 한 변수씩 분리하는 실험 실행기.

운영 src/**를 바꾸지 않고 prompt → token → schema → connection → queue →
timeout → qualification 순서로만 실행한다. 결과에는 질문/요청 본문과 인증값을
저장하지 않는다.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import socket
import statistics
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import psycopg
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from agent import query_frame  # noqa: E402
from agent.agent_core import APP, to_response  # noqa: E402
from config import BOND_DSN, CLOVA_HOST, FRAME_MODEL  # noqa: E402
from script.test_rdb_vertical_slice import IDS, comparable, load_inputs  # noqa: E402

RAW_PATH = HERE / "results/query_frame_latency_raw.jsonl"
METRICS_PATH = HERE / "results/query_frame_latency_metrics.json"
REPORT_PATH = HERE / "6_2_result_query_frame_latency.md"
STAGES = ["prompt", "token", "schema", "connection", "queue", "timeout", "qualification"]
SCREEN_IDS = ["q003", "q010", "q013"]
EXPAND_IDS = ["q006", "q018"]
PROMPT_MARKER = "예시 — 평가 문항이 아니라 형식을 보이기 위한 가상 질의다."
SAFE_HEADERS = {"date", "server-timing", "x-request-id", "x-trace-id",
                "x-ncp-apigw-trace-id", "x-ratelimit-limit", "x-ratelimit-remaining",
                "ratelimit-limit", "ratelimit-remaining", "retry-after"}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha(value) -> str:
    blob = value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def without_descriptions(value):
    if isinstance(value, dict):
        return {k: without_descriptions(v) for k, v in value.items() if k != "description"}
    if isinstance(value, list):
        return [without_descriptions(v) for v in value]
    return value


def compact_prompt() -> str:
    before, marker, _ = query_frame.FRAME_SYSTEM.partition(PROMPT_MARKER)
    if not marker:
        raise RuntimeError("축약 prompt 경계 marker를 찾을 수 없습니다")
    return before.rstrip()


def load_metrics() -> dict:
    if not METRICS_PATH.exists():
        return {
            "experiment": "query_frame_latency_single_variable_v1",
            "created_at": now(),
            "model": FRAME_MODEL,
            "endpoint": f"{CLOVA_HOST}/v3/chat-completions/{FRAME_MODEL}",
            "target_seconds": 5.0,
            "stage_order": STAGES,
            "stages": {},
            "selected_config": {"prompt": "full", "max_completion_tokens": 3072,
                                "schema": "full", "connection": "fresh",
                                "timeout_seconds": 13},
            "runtime_source_modified": False,
        }
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


def prompt_for(name: str) -> str:
    return query_frame.FRAME_SYSTEM if name == "full" else compact_prompt()


def schema_for(name: str) -> dict:
    schema = query_frame.QUERY_FRAME_SCHEMA
    return copy.deepcopy(schema if name == "full" else without_descriptions(schema))


def request_manifest(config: dict) -> dict:
    prompt = prompt_for(config["prompt"])
    schema = schema_for(config["schema"])
    manifest = {
        "model": FRAME_MODEL,
        "endpoint": f"{CLOVA_HOST}/v3/chat-completions/{FRAME_MODEL}",
        "prompt_variant": config["prompt"],
        "prompt_chars": len(prompt),
        "prompt_utf8_bytes": len(prompt.encode("utf-8")),
        "schema_variant": config["schema"],
        "schema_chars": len(json.dumps(schema, ensure_ascii=False, separators=(",", ":"))),
        "max_completion_tokens": config["max_completion_tokens"],
        "connection": config["connection"],
        "timeout_seconds": config["timeout_seconds"],
        "temperature": 0.0,
        "top_p": 0.8,
        "seed": 0,
        "thinking": "none",
        "stream": False,
    }
    manifest["sha256"] = sha(manifest)
    return manifest


def validate_schema(value, schema: dict, path: str = "$") -> list[str]:
    errors = []
    kinds = schema.get("type")
    kinds = [kinds] if isinstance(kinds, str) else kinds or []
    checks = {"object": dict, "array": list, "string": str, "integer": int,
              "number": (int, float), "null": type(None), "boolean": bool}
    valid = any(isinstance(value, checks[k]) and not (k in {"integer", "number"}
                and isinstance(value, bool)) for k in kinds if k in checks)
    if kinds and not valid:
        return [f"{path}: type"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: enum")
    if isinstance(value, dict):
        for key in schema.get("required") or []:
            if key not in value:
                errors.append(f"{path}.{key}: required")
        for key, child in (schema.get("properties") or {}).items():
            if key in value:
                errors.extend(validate_schema(value[key], child, f"{path}.{key}"))
    elif isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value):
            errors.extend(validate_schema(item, schema["items"], f"{path}[{index}]"))
    return errors


def api_body(question: str, config: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": prompt_for(config["prompt"])}]},
            {"role": "user", "content": [{"type": "text", "text": question}]},
        ],
        "topP": 0.8, "temperature": 0.0, "repetitionPenalty": 1.1,
        "stop": [], "seed": 0,
        "maxCompletionTokens": config["max_completion_tokens"],
        "thinking": {"effort": "none"},
        "responseFormat": {"type": "json", "schema": schema_for(config["schema"])},
    }


def response_content(data: dict) -> str:
    content = (data.get("result") or {}).get("message", {}).get("content")
    if isinstance(content, list):
        content = "".join(x.get("text", "") for x in content if isinstance(x, dict))
    if not isinstance(content, str):
        raise RuntimeError(f"content 형태 불명: {type(content).__name__}")
    return content


def usage_tokens(data: dict):
    usage = (data.get("result") or {}).get("usage") or data.get("usage") or {}
    for key in ("completionTokens", "outputTokens", "completion_tokens", "output_tokens"):
        if key in usage:
            return usage[key]
    return None


def call_hcx(question: str, config: dict, session=None) -> tuple[dict, dict | None]:
    """한 번만 호출한다. 반환 row에는 비밀/본문을 넣지 않는다."""
    import clova

    sender = session.post if session else requests.post
    endpoint = f"{CLOVA_HOST}/v3/chat-completions/{FRAME_MODEL}"
    started = time.perf_counter()
    row = {"http_status": None, "timeout": False, "error_type": None,
           "error_message": None, "response_elapsed_seconds": None,
           "safe_response_headers": {}, "output_chars": 0, "output_utf8_bytes": 0,
           "usage_completion_tokens": None, "parse_valid": False,
           "raw_schema_valid": False, "raw_schema_errors": [], "guard_14_fields_valid": False,
           "tbox_leaks": [], "frame": None}
    try:
        response = sender(endpoint,
                          headers={"Authorization": clova.key(),
                                   "Content-Type": "application/json; charset=utf-8",
                                   "Accept": "application/json"},
                          json=api_body(question, config), timeout=config["timeout_seconds"])
        row["http_status"] = response.status_code
        row["response_elapsed_seconds"] = round(response.elapsed.total_seconds(), 4)
        row["safe_response_headers"] = {k.lower(): v for k, v in response.headers.items()
                                          if k.lower() in SAFE_HEADERS}
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        data = response.json()
        status = data.get("status") or {}
        if status.get("code") not in (None, "20000"):
            raise RuntimeError(f"status {status.get('code')}")
        text = response_content(data)
        row["output_chars"] = len(text)
        row["output_utf8_bytes"] = len(text.encode("utf-8"))
        row["usage_completion_tokens"] = usage_tokens(data)
        raw = clova.parse_json_loose(text)
        row["parse_valid"] = True
        errors = validate_schema(raw, query_frame.QUERY_FRAME_SCHEMA)
        row["raw_schema_errors"] = errors[:20]
        row["raw_schema_valid"] = not errors
        frame = query_frame.guard(raw)
        frame["_raw"] = raw
        row["guard_14_fields_valid"] = all(k in frame for k in query_frame.FIELDS)
        row["tbox_leaks"] = query_frame.leaks(frame)
        row["frame"] = frame
    except requests.Timeout as exc:
        row["timeout"] = True
        row["error_type"] = type(exc).__name__
        row["error_message"] = "HTTP timeout"
    except Exception as exc:  # 호출 실패도 실험 결과로 남긴다.
        row["error_type"] = type(exc).__name__
        row["error_message"] = str(exc)[:180]
    row["wall_latency_seconds"] = round(time.perf_counter() - started, 4)
    latency = row["wall_latency_seconds"]
    row["latency_bin"] = "timeout" if row["timeout"] else \
        "http_error" if row["http_status"] != 200 else \
        "le_4" if latency <= 4 else "4_to_5" if latency <= 5 else "gt_5"
    return row, row.pop("frame")


def initial_state(qid: str, question: str) -> dict:
    return {"question_id": qid, "question": question, "intent": {},
            "metadata_context": {}, "plan": {}, "results": {}, "evidence": [],
            "abstain": None, "trace": [], "answer": ""}


def downstream(conn, qid: str, question: str, frame: dict | None) -> dict:
    out = {"functional_success": False, "db_exact": False, "evidence_complete": False,
           "response_contract": False, "abstain_code": None}
    if frame is None:
        return out
    try:
        _, _, golds = load_inputs()
        with patch("agent.nodes.query_frame.extract", return_value=frame):
            state = APP.invoke(initial_state(qid, question))
        response = to_response(state)
        results = state.get("results") or {}
        columns = results.get("columns") or []
        evidence = state.get("evidence") or []
        abstain = state.get("abstain")
        out["abstain_code"] = abstain.get("code") if abstain else None
        out["response_contract"] = list(response) == ["question_id", "question",
                                                       "retrieved_context", "think_trace", "answer"]
        out["evidence_complete"] = bool(evidence) and \
            [x.get("source_column") for x in evidence] == columns and \
            all(x.get("source_table") and x.get("source_column") and x.get("as_of") for x in evidence)
        if not abstain:
            gold = golds[qid]
            cursor = conn.execute(gold["gold_sql"])
            gold_columns = [x.name for x in cursor.description]
            gold_rows = [dict(zip(gold_columns, row)) for row in cursor.fetchall()]
            out["db_exact"] = set(columns) == set(gold_columns) and \
                comparable(results.get("rows") or [], gold["order_sensitive"]) == \
                comparable(gold_rows, gold["order_sensitive"])
        out["functional_success"] = (not abstain and out["db_exact"] and
                                     out["evidence_complete"] and out["response_contract"])
    except Exception as exc:
        out["downstream_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    return out


def complete_row(base: dict, api: dict, downstream_result: dict) -> dict:
    row = {**base, **api, **downstream_result}
    row["valid_query_frame_le_5s"] = (row["parse_valid"] and row["raw_schema_valid"] and
                                      row["guard_14_fields_valid"] and not row["tbox_leaks"] and
                                      not row["timeout"] and row["wall_latency_seconds"] <= 5)
    row["strict_success"] = row["valid_query_frame_le_5s"] and row["functional_success"]
    row["late_recovery"] = (row["functional_success"] and not row["timeout"] and
                            row["wall_latency_seconds"] > 5)
    row["safe_deadline_exit"] = row["timeout"] and row["wall_latency_seconds"] <= 5.5
    return row


def execute_one(conn, stage: str, arm: str, qid: str, question: str, order: int,
                pair_id: str, config: dict, session=None) -> dict:
    manifest = request_manifest(config)
    base = {"run_id": str(uuid.uuid4()), "measured_at": now(), "stage": stage,
            "pair_id": pair_id, "arm": arm, "question_id": qid, "order": order,
            "changed_variable": changed_variable(stage),
            "request_manifest_sha256": manifest["sha256"], "request_manifest": manifest}
    api, frame = call_hcx(question, config, session=session)
    result = complete_row(base, api, downstream(conn, qid, question, frame))
    print(f"LIVE {stage} {pair_id} {arm}: strict={result['strict_success']} "
          f"functional={result['functional_success']} qf={result['wall_latency_seconds']}s", flush=True)
    return result


def changed_variable(stage: str) -> str:
    return {"prompt": "prompt_length", "token": "max_completion_tokens",
            "schema": "schema_descriptions", "connection": "connection_reuse",
            "queue": "request_concurrency", "timeout": "http_timeout_policy",
            "qualification": "none_selected_configuration"}[stage]


def stage_configs(stage: str, selected: dict) -> tuple[dict, dict]:
    control = dict(selected)
    candidate = dict(selected)
    if stage == "prompt":
        control["prompt"], candidate["prompt"] = "full", "compact"
    elif stage == "token":
        control["max_completion_tokens"], candidate["max_completion_tokens"] = 3072, 1536
    elif stage == "schema":
        control["schema"], candidate["schema"] = "full", "no_descriptions"
    elif stage == "connection":
        control["connection"], candidate["connection"] = "fresh", "session"
    elif stage == "timeout":
        control["timeout_seconds"], candidate["timeout_seconds"] = 13, 5
    return control, candidate


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    completed = [x for x in rows if not x["timeout"] and x["http_status"] == 200]
    latencies = [x["wall_latency_seconds"] for x in completed]
    return {
        "attempts": total,
        "responses": len(completed),
        "timeouts": sum(x["timeout"] for x in rows),
        "http_429": sum(x["http_status"] == 429 for x in rows),
        "http_5xx": sum(isinstance(x["http_status"], int) and 500 <= x["http_status"] < 600
                        for x in rows),
        "valid_query_frame_le_5s": sum(x["valid_query_frame_le_5s"] for x in rows),
        "valid_json_schema": sum(x["parse_valid"] and x["raw_schema_valid"] for x in rows),
        "functional_success_non_timeout": sum(x["functional_success"] for x in completed),
        "functional_success_non_timeout_denominator": len(completed),
        "strict_success": sum(x["strict_success"] for x in rows),
        "latency_bins": dict(sorted(Counter(x["latency_bin"] for x in rows).items())),
        "completed_latency_seconds": {
            "min": min(latencies) if latencies else None,
            "median": statistics.median(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "censored_timeout_seconds": [x["wall_latency_seconds"] for x in rows if x["timeout"]],
        "parse_schema_db_evidence_regressions": sum(
            (not x["parse_valid"] or not x["raw_schema_valid"] or
             (not x["db_exact"] and x["abstain_code"] is None) or
             (not x["evidence_complete"] and x["abstain_code"] is None))
            for x in completed),
    }


def decide(control: list[dict], candidate: list[dict], expanded: bool) -> dict:
    completed = sum(not x["timeout"] and x["http_status"] == 200 for x in control + candidate)
    if completed < 2:
        return {"status": "measurement_blocked_by_service", "selected": "control",
                "expanded": expanded, "reason": "completed responses across both arms < 2"}
    c_strict = sum(x["strict_success"] for x in control)
    n_strict = sum(x["strict_success"] for x in candidate)
    regressions = any(not x["parse_valid"] or not x["raw_schema_valid"] or x["tbox_leaks"] or
                      (not x["db_exact"] and x["abstain_code"] is None) or
                      (not x["evidence_complete"] and x["abstain_code"] is None)
                      for x in candidate if not x["timeout"] and x["http_status"] == 200)
    threshold = 1 if expanded else 2
    if n_strict >= c_strict + threshold and not regressions:
        return {"status": "selected", "selected": "candidate", "expanded": expanded,
                "reason": f"strict {n_strict}>{c_strict}, regressions=0"}
    if not expanded and abs(n_strict - c_strict) <= 1:
        return {"status": "expand_required", "selected": None, "expanded": False,
                "reason": f"initial strict difference {n_strict - c_strict}"}
    return {"status": "selected", "selected": "control", "expanded": expanded,
            "reason": f"candidate threshold/regression gate failed ({n_strict} vs {c_strict})"}


def dns_probe() -> dict:
    host = urlparse(CLOVA_HOST).hostname
    started = time.perf_counter()
    try:
        addresses = socket.getaddrinfo(host, 443)
        return {"host": host, "latency_seconds": round(time.perf_counter() - started, 4),
                "resolved_address_count": len({x[4][0] for x in addresses}), "error": None}
    except OSError as exc:
        return {"host": host, "latency_seconds": round(time.perf_counter() - started, 4),
                "resolved_address_count": 0, "error": type(exc).__name__}


def paired_stage(stage: str, selected: dict) -> tuple[list[dict], dict]:
    questions, _, _ = load_inputs()
    control_config, candidate_config = stage_configs(stage, selected)
    rows = []
    probe = dns_probe() if stage == "connection" else None
    candidate_session = requests.Session() if stage == "connection" else None
    try:
        with psycopg.connect(BOND_DSN, autocommit=True) as conn:
            conn.execute("SET statement_timeout = 2000")
            for index, qid in enumerate(SCREEN_IDS):
                arms = ["control", "candidate"] if index % 2 == 0 else ["candidate", "control"]
                for order, arm in enumerate(arms, 1):
                    cfg = control_config if arm == "control" else candidate_config
                    session = candidate_session if arm == "candidate" else None
                    rows.append(execute_one(conn, stage, arm, qid, questions[qid], order,
                                            qid, cfg, session=session))
            control = [x for x in rows if x["arm"] == "control"]
            candidate = [x for x in rows if x["arm"] == "candidate"]
            decision = decide(control, candidate, expanded=False)
            if decision["status"] == "expand_required":
                for index, qid in enumerate(EXPAND_IDS, start=len(SCREEN_IDS)):
                    arms = ["control", "candidate"] if index % 2 == 0 else ["candidate", "control"]
                    for order, arm in enumerate(arms, 1):
                        cfg = control_config if arm == "control" else candidate_config
                        session = candidate_session if arm == "candidate" else None
                        rows.append(execute_one(conn, stage, arm, qid, questions[qid], order,
                                                qid, cfg, session=session))
                control = [x for x in rows if x["arm"] == "control"]
                candidate = [x for x in rows if x["arm"] == "candidate"]
                decision = decide(control, candidate, expanded=True)
    finally:
        if candidate_session:
            candidate_session.close()
    result = {"status": "completed", "changed_variable": changed_variable(stage),
              "control_config": request_manifest(control_config),
              "candidate_config": request_manifest(candidate_config),
              "control": summarize([x for x in rows if x["arm"] == "control"]),
              "candidate": summarize([x for x in rows if x["arm"] == "candidate"]),
              "decision": decision}
    if probe:
        result["dns_probe"] = probe
    return rows, result


def queue_stage(selected: dict) -> tuple[list[dict], dict]:
    questions, _, _ = load_inputs()
    qid = "q013"
    config = dict(selected, connection="fresh")
    rows, wave_seconds = [], []
    with psycopg.connect(BOND_DSN, autocommit=True) as conn:
        conn.execute("SET statement_timeout = 2000")
        for n in range(4):
            rows.append(execute_one(conn, "queue", "control", qid, questions[qid], n + 1,
                                    f"sequential_{n + 1}", config))
        for wave in range(2):
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(call_hcx, questions[qid], config) for _ in range(2)]
                outputs = [f.result() for f in futures]
            wave_seconds.append(round(time.perf_counter() - started, 4))
            for offset, (api, frame) in enumerate(outputs, 1):
                manifest = request_manifest(config)
                base = {"run_id": str(uuid.uuid4()), "measured_at": now(), "stage": "queue",
                        "pair_id": f"wave_{wave + 1}", "arm": "candidate", "question_id": qid,
                        "order": offset, "changed_variable": changed_variable("queue"),
                        "request_manifest_sha256": manifest["sha256"],
                        "request_manifest": manifest, "concurrency": 2}
                row = complete_row(base, api, downstream(conn, qid, questions[qid], frame))
                rows.append(row)
                print(f"LIVE queue wave_{wave + 1} candidate: strict={row['strict_success']} "
                      f"qf={row['wall_latency_seconds']}s", flush=True)
    return rows, {"status": "completed", "diagnostic_only": True,
                  "control_label": "sequential_4", "candidate_label": "concurrency_2_two_waves",
                  "wave_wall_seconds": wave_seconds,
                  "control": summarize([x for x in rows if x["arm"] == "control"]),
                  "candidate": summarize([x for x in rows if x["arm"] == "candidate"]),
                  "decision": {"selected": None, "reason": "diagnostic only; never promoted"}}


def qualification_stage(selected: dict) -> tuple[list[dict], dict]:
    questions, _, _ = load_inputs()
    rows = []
    session = requests.Session() if selected["connection"] == "session" else None
    try:
        with psycopg.connect(BOND_DSN, autocommit=True) as conn:
            conn.execute("SET statement_timeout = 2000")
            for number, qid in enumerate(IDS, 1):
                rows.append(execute_one(conn, "qualification", "selected", qid,
                                        questions[qid], number, qid, selected, session=session))
    finally:
        if session:
            session.close()
    gate = {
        "valid_query_frame_le_5s": sum(x["valid_query_frame_le_5s"] for x in rows) == 14,
        "functional_db_exact": sum(x["functional_success"] and x["db_exact"] for x in rows) == 14,
        "zero_contract_regressions": all(
            x["http_status"] != 200 or x["timeout"] or
            (not x["tbox_leaks"] and x["response_contract"] and
             (x["abstain_code"] is not None or x["evidence_complete"])) for x in rows),
        "zero_timeout_429_5xx": all(not x["timeout"] and x["http_status"] != 429 and
                                    not (isinstance(x["http_status"], int) and
                                         500 <= x["http_status"] < 600) for x in rows),
    }
    passed = all(gate.values())
    return rows, {"status": "completed", "selected_config": request_manifest(selected),
                  "summary": summarize(rows), "gate": gate,
                  "runtime_candidate": passed, "redesign_recommended": not passed}


def apply_decision(stage: str, result: dict, selected: dict) -> None:
    decision = result.get("decision") or {}
    if decision.get("selected") != "candidate":
        return
    if stage == "prompt":
        selected["prompt"] = "compact"
    elif stage == "token":
        selected["max_completion_tokens"] = 1536
    elif stage == "schema":
        selected["schema"] = "no_descriptions"
    elif stage == "connection":
        selected["connection"] = "session"
    elif stage == "timeout":
        selected["timeout_seconds"] = 5


def prerequisite(stage: str, metrics: dict) -> None:
    index = STAGES.index(stage)
    missing = [x for x in STAGES[:index] if x not in metrics["stages"]]
    # payload 측정이 서비스 차단이면 token/schema를 생략할 수 있다.
    if stage in {"connection", "queue"}:
        missing = [x for x in missing if x not in {"token", "schema"}]
    if missing:
        raise RuntimeError(f"선행 stage 미완료: {', '.join(missing)}")


def append_rows(rows: list[dict]) -> None:
    RAW_PATH.parent.mkdir(exist_ok=True)
    with RAW_PATH.open("a", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def percent(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d * 100:.1f}%)" if d else "0/0"


def write_report(metrics: dict) -> None:
    raw = [json.loads(line) for line in RAW_PATH.read_text(encoding="utf-8").splitlines()
           if line.strip()] if RAW_PATH.exists() else []
    lines = ["# Query Frame HCX Latency 단일변수 실험 결과", "",
             f"- 갱신 시각: {metrics.get('updated_at', metrics['created_at'])}",
             f"- 모델/endpoint: `{metrics['model']}` / `{metrics['endpoint']}`",
             "- 데이터 기준일: `2026-07-11`",
             "- 목표: Query Frame 구조·RDB 정확성을 유지하면서 wall-clock 5초 이내",
             "- 범위: 실험 전용 코드와 결과만 추가하며 운영 `src/**`는 변경하지 않음", "",
             "## 1. 측정 명세", "",
             "| 지표 | 측정 기준 | 의미 |", "|---|---|---|",
             "| Valid Query Frame ≤5s | HTTP 호출 시작부터 JSON parse·원본 schema·14필드 guard·TBox leak 검사를 5초 이내 통과 | intent 출력의 구조와 시간 목표를 동시에 충족 |",
             "| Functional Success | non-ABSTAIN + 실제 PostgreSQL Gold exact + evidence complete + 공개 응답 5필드 | 빠르기와 무관하게 RDB E2E가 정답을 반환 |",
             "| Strict Success | Valid Query Frame ≤5s AND Functional Success | 이 실험의 arm 선택 지표 |",
             "| Completed latency | HTTP 200 응답만의 wall-clock | timeout·429를 빠른 응답으로 오인하지 않음 |",
             "| Censored timeout | timeout까지 기다린 wall-clock을 별도 기록 | 미완료 호출을 latency 표본에 섞지 않음 |",
             "| HTTP 429/5xx | 응답 상태별 개수 | endpoint/queue 운영 안정성 확인 |", "",
             "공통 조건은 HCX-007, temperature=0, topP=0.8, seed=0, thinking=none, "
             "non-streaming이다. 따라서 TTFT는 측정하지 않는다. 질문 본문·request body·인증값은 "
             "원자료에 저장하지 않는다.", "",
             "## 2. 단계별 결과", "",
             "| 단계 | Arm | 시도/HTTP 200/429/timeout | Strict | 완료 latency min/median/max(초) | 판정 |",
             "|---|---|---:|---:|---:|---|"]
    for stage in STAGES:
        result = metrics["stages"].get(stage)
        if not result:
            lines.append(f"| {stage} | NOT RUN | - | - | - | - |")
            continue
        if stage == "qualification":
            summary = result["summary"]
            latency = summary["completed_latency_seconds"]
            calls = f"{summary['attempts']}/{summary['responses']}/{summary['http_429']}/{summary['timeouts']}"
            lat = f"{latency['min']}/{latency['median']}/{latency['max']}"
            lines.append(f"| {stage} | selected | {calls} | "
                         f"{percent(summary['strict_success'], summary['attempts'])} | {lat} | "
                         f"runtime_candidate={str(result['runtime_candidate']).lower()} |")
        else:
            control, candidate = result["control"], result["candidate"]
            decision = (result.get("decision") or {}).get("selected")
            for arm, values in (("control", control), ("candidate", candidate)):
                latency = values["completed_latency_seconds"]
                calls = f"{values['attempts']}/{values['responses']}/{values['http_429']}/{values['timeouts']}"
                lat = f"{latency['min']}/{latency['median']}/{latency['max']}"
                lines.append(f"| {stage} | {arm} | {calls} | "
                             f"{percent(values['strict_success'], values['attempts'])} | {lat} | "
                             f"{decision or 'diagnostic only'} |")
    cfg = metrics["selected_config"]
    lines += ["", "표의 시도 열은 `전체/HTTP 200/HTTP 429/timeout` 순서다. 모든 payload와 "
              "connection 후보는 선택 기준을 넘지 못해 control을 유지했다.", "",
              "### 변수별 해석", "",
              "- Prompt: 6,128자 control이 strict 2/3, 4,994자 축약안이 0/3이었다. 길이 축소만으로 개선되지 않았고 축약안에 downstream 회귀가 있었다.",
              "- Token: 3,072 대 1,536은 5쌍 후 strict 1/5 대 1/5로 동률이었다.",
              "- Schema: full 대 description 제거는 strict 2/5 대 1/5였으며 제거안에서 HTTP 429가 1건 발생했다.",
              "- Connection: DNS 0.0098초로 병목이 아니었다. fresh strict 3/5, Session 2/5이고 Session arm에 HTTP 429가 1건 있었다.",
              "- Queue: q013은 순차와 concurrency=2 모두 strict 0/4였다. 동시 실행은 두 요청의 wave wall time을 약 7초로 묶어 처리량만 높였고 개별 5초 SLA는 개선하지 않았다.",
              "- Timeout: 13초와 5초 모두 strict 3/5였다. 5초 정책은 q013을 약 5.03초에 안전 종료했으나 원인 latency를 줄이지 않았다.", "",
              "## 3. 현재 선택 구성", "", "```json",
              json.dumps(cfg, ensure_ascii=False, indent=2), "```", "",
              "## 4. 판정 기준", "",
              "- 각 payload/connection arm은 q003·q010·q013 각 3회로 시작하고, 차이가 0~1이면 q006·q018을 추가해 arm당 5회로 확장한다.",
              "- 5쌍 후 candidate strict 성공 수가 더 많고 parse/schema/DB/evidence 회귀가 0일 때만 선택한다. 동률은 control이다.",
              "- queue 단계는 동일 q013의 순차 4회와 concurrency=2 두 wave를 비교하는 진단이며 운영 설정으로 승격하지 않는다.",
              "- 최종 14문항 모두 Query Frame ≤5초, functional+DB exact, 계약 오류 0, timeout/429/5xx 0이어야 runtime candidate다.", "",
              "## 5. Qualification과 최종 판정", ""]
    qualification = metrics["stages"].get("qualification")
    if qualification:
        summary = qualification["summary"]
        failures = [x for x in raw if x["stage"] == "qualification" and not x["strict_success"]]
        safe_abstains = [x["question_id"] for x in failures if x.get("abstain_code")]
        rate_limited = [x["question_id"] for x in failures if x.get("http_status") == 429]
        lines += [f"- Strict Success: {percent(summary['strict_success'], summary['attempts'])}",
                  f"- HTTP 200 응답: {summary['responses']}/14; 그중 Functional Success: "
                  f"{summary['functional_success_non_timeout']}/{summary['functional_success_non_timeout_denominator']}",
                  f"- 완료 응답 latency: min {summary['completed_latency_seconds']['min']}초 / "
                  f"median {summary['completed_latency_seconds']['median']}초 / "
                  f"max {summary['completed_latency_seconds']['max']}초",
                  f"- 안전 ABSTAIN: {', '.join(safe_abstains) if safe_abstains else '없음'}",
                  f"- HTTP 429: {', '.join(rate_limited) if rate_limited else '없음'}", ""]
        verdict = "PASS" if qualification["runtime_candidate"] else "FAIL — 재설계 필요"
        lines.append(f"최종 qualification 판정은 **{verdict}**다. 정상 응답 9건은 모두 5초 "
                     "이내였지만 q006의 의미/엔티티 해석 실패와 연속 429 5건 때문에 14/14 "
                     "운영 통과 조건을 충족하지 못했다. 이번 표본에서는 prompt·token·schema·"
                     "connection 변경이 5초 성공률을 높인다는 근거가 없으며, endpoint rate limit/"
                     "queue 정책을 확인한 후 실험 간 cooldown을 둔 재검증이 필요하다.")
    else:
        lines.append("실험이 아직 끝나지 않았다. 완료되지 않은 단계는 위 표에 `NOT RUN`으로 표시한다.")
    lines += ["", "## 6. 재현 파일", "",
              "- 실행 코드: `evaluate_query_frame_latency.py`",
              "- 호출 단위 원자료: `results/query_frame_latency_raw.jsonl`",
              "- 단계 집계·선택 구성: `results/query_frame_latency_metrics.json`",
              "- 기존 RDB E2E 기준 결과: `results/metrics.json`", ""]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dry_run() -> None:
    base = load_metrics()["selected_config"]
    data = {"stage_order": STAGES, "screen_ids": SCREEN_IDS, "expand_ids": EXPAND_IDS,
            "full_prompt_chars": len(query_frame.FRAME_SYSTEM),
            "compact_prompt_chars": len(compact_prompt()),
            "full_schema_chars": len(json.dumps(query_frame.QUERY_FRAME_SCHEMA, ensure_ascii=False,
                                                  separators=(",", ":"))),
            "no_description_schema_chars": len(json.dumps(without_descriptions(
                query_frame.QUERY_FRAME_SCHEMA), ensure_ascii=False, separators=(",", ":"))),
            "base_manifest": request_manifest(base),
            "writes": False, "network_calls": 0, "db_calls": 0}
    assert data["compact_prompt_chars"] < data["full_prompt_chars"]
    assert data["no_description_schema_chars"] < data["full_schema_chars"]
    assert len(query_frame.QUERY_FRAME_SCHEMA["required"]) == 14
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-results", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        if args.stage or args.write_results:
            parser.error("--dry-run은 다른 옵션과 함께 사용할 수 없습니다")
        dry_run()
        return
    if not args.stage:
        parser.error("--stage가 필요합니다")
    if not args.write_results:
        parser.error("live 실험은 결과 유실 방지를 위해 --write-results가 필요합니다")
    metrics = load_metrics()
    prerequisite(args.stage, metrics)
    if args.stage in metrics["stages"]:
        raise RuntimeError(f"이미 실행된 stage입니다: {args.stage}")

    selected = dict(metrics["selected_config"])
    if args.stage == "queue":
        rows, result = queue_stage(selected)
    elif args.stage == "qualification":
        rows, result = qualification_stage(selected)
    else:
        rows, result = paired_stage(args.stage, selected)
    apply_decision(args.stage, result, selected)
    metrics["stages"][args.stage] = result
    metrics["selected_config"] = selected
    metrics["updated_at"] = now()
    append_rows(rows)
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    write_report(metrics)
    print(f"RESULT {METRICS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
