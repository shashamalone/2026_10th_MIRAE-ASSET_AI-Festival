# -*- coding: utf-8 -*-
"""A/B/C metadata context로 NL2SQL Planner를 실행한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))           # 런타임 모듈은 src/ 아래에 있다
import clova  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULT = HERE / "results/nl2sql_raw.json"
MODEL = "HCX-007"
CONDITIONS = ("A", "B", "C")
CALL_PAUSE = float(os.environ.get("ACTION3_CALL_PAUSE", "12"))

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "execution_plan": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "engine": {"type": "string", "enum": ["rdb"]},
            "query": {"type": "string"},
            "depends_on": {"type": "array", "items": {"type": "string"}},
        }, "required": ["id", "engine", "query", "depends_on"]}},
        "query_type": {"type": "string"},
    }, "required": ["execution_plan", "query_type"],
}
RESPONSE_FORMAT = {"type": "json", "schema": PLAN_SCHEMA}
SYSTEM = """당신은 PostgreSQL 금융상품 NL2SQL Planner다.
주어진 질문과 metadata context만 사용한다. 존재하지 않는 table/column을 만들지 않는다.
반드시 단일 읽기 전용 SELECT 또는 WITH...SELECT SQL을 execution_plan의 rdb step 하나로 반환한다.
질문이 요구한 식별자·수치·근거 컬럼을 SELECT하고 완전일치 상품명을 우선한다.
PostgreSQL 문법만 사용한다. 설명이나 markdown 없이 지정된 JSON schema만 반환한다."""


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_dump(data, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def context_for(condition: str, qid: str, contexts: dict) -> dict:
    if condition == "A":
        return {"physical_schema": contexts["A"]["tables"]}
    if condition == "B":
        return {"physical_schema": contexts["B"]["physical_schema"],
                "grounded_concepts": contexts["B"]["question_contexts"].get(qid, [])}
    return {"physical_schema": contexts["C"]["physical_schema"],
            "metadata_context": contexts["C"]["question_contexts"].get(qid, []),
            "global_rules": contexts["C"]["global_rules"]}


def load_inputs(gold_name: str) -> tuple[dict, dict, dict]:
    gold_path = HERE / f"gold/{gold_name}"
    gold = load(gold_path)
    paths = {"A": HERE / "contexts/schema_only.json",
             "B": HERE / "contexts/schema_tbox.json",
             "C": HERE / "contexts/schema_tbox_business.json"}
    contexts = {k: load(v) for k, v in paths.items()}
    if contexts["A"]["catalog_sha256"] != gold["meta"]["catalog_sha256"]:
        raise RuntimeError("Gold와 Physical Catalog SHA 불일치")
    hashes = {"gold": sha(gold_path), **{f"context_{k}": sha(v) for k, v in paths.items()}}
    for rel, expected in gold["meta"]["snapshot"].items():
        if sha(ROOT / rel) != expected:
            raise RuntimeError(f"동결 snapshot 변경: {rel}")
    return gold, contexts, hashes


def new_raw(kind: str, hashes: dict) -> dict:
    return {"meta": {"kind": kind, "model": MODEL, "temperature": 0.1, "seed": 0,
                     "top_p": 0.8, "max_completion_tokens": 4096,
                     "api_timeout_seconds": 120, "data_cutoff": "2026-08-24",
                     "hashes": hashes,
                     "repeat_rule": "run1 전체; 오류 또는 A/B/C primary 결과 차이 문항만 run2-3"},
            "runs": []}


def open_raw(path: Path, kind: str, hashes: dict) -> dict:
    if not path.exists():
        return new_raw(kind, hashes)
    raw = load(path)
    if raw["meta"]["hashes"] != hashes:
        raise RuntimeError(f"기존 {path.name}의 Gold/context SHA가 다름 — 덮어쓰기 거부")
    return raw


def condition_order(qid: str, run: int) -> tuple[str, ...]:
    offset = (int(qid[1:]) + run - 2) % 3
    return CONDITIONS[offset:] + CONDITIONS[:offset]


def run_one(question: dict, condition: str, context: dict) -> dict:
    user = question["question"] + "\n\nmetadata_context:\n" + json.dumps(
        context, ensure_ascii=False, separators=(",", ":"))
    started = time.perf_counter()
    try:
        response = call_clova(SYSTEM, user, RESPONSE_FORMAT)
        plan = clova.parse_json_loose(response)
        error = None
    except Exception as e:
        response, plan, error = None, None, f"{type(e).__name__}: {str(e)[:500]}"
    return {"question_id": question["question_id"], "condition": condition,
            "response": response, "plan": plan, "error": error,
            "latency_seconds": round(time.perf_counter() - started, 3)}


def call_clova(system: str, user: str, response_format: dict) -> str:
    """429는 분 단위 quota이므로 기다린 뒤 같은 cell을 재시도한다."""
    for attempt in range(7):
        try:
            return clova.chat(MODEL, system, user, max_tokens=4096,
                              response_format=response_format, temperature=0.1)
        except Exception as e:
            if "429" not in str(e) or attempt == 6:
                raise
            wait = min(65, 10 * (2 ** attempt))
            print(f"  429 — {wait}s 대기 후 재시도 {attempt+1}/6", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def selected_ids(kind: str) -> set[str]:
    path = HERE / "results/error_cases.json"
    if not path.exists():
        raise RuntimeError("먼저 evaluator를 실행해 error_cases.json을 생성해야 함")
    return set(load(path).get(f"{kind}_repeat_ids", []))


def retryable_infrastructure_error(row: dict) -> bool:
    error = row.get("error") or ""
    return any(marker in error for marker in (
        "429", "NameResolutionError", "Temporary failure in name resolution",
        "ConnectTimeout", "ReadTimeout", "ConnectionError",
    ))


def execute(gold_name: str, result: Path, system_kind: str, make_user_context,
            question_id: str | None, repeat_selected: bool) -> None:
    gold, contexts, hashes = load_inputs(gold_name)
    raw = open_raw(result, system_kind, hashes)
    retryable = [r for r in raw["runs"] if retryable_infrastructure_error(r)]
    if retryable:
        raw["runs"] = [r for r in raw["runs"] if r not in retryable]
        raw["meta"]["infrastructure_cells_retried"] = raw["meta"].get(
            "infrastructure_cells_retried", 0) + len(retryable)
        atomic_dump(raw, result)
        print(f"인프라 실패 cell {len(retryable)}개를 resume 대상으로 복구", flush=True)
    done = {(r["question_id"], r["condition"], r["run"]) for r in raw["runs"]}
    questions = gold["questions"]
    if question_id:
        questions = [q for q in questions if q["question_id"] == question_id]
        if not questions:
            raise SystemExit(f"없는 question_id: {question_id}")
    target_runs = (2, 3) if repeat_selected else (1,)
    if repeat_selected:
        wanted = selected_ids(system_kind)
        questions = [q for q in questions if q["question_id"] in wanted]
    for run in target_runs:
        for q in questions:
            for condition in condition_order(q["question_id"], run):
                key = (q["question_id"], condition, run)
                if key in done:
                    continue
                print(f"{system_kind} {q['question_id']} {condition} run={run}", flush=True)
                row = run_one(q, condition, make_user_context(condition, q["question_id"], contexts))
                row["run"] = run
                raw["runs"].append(row)
                atomic_dump(raw, result)
                print(f"  {'PASS' if not row['error'] else 'FAIL'} {row['latency_seconds']:.1f}s", flush=True)
                if not row["error"] and CALL_PAUSE:
                    time.sleep(CALL_PAUSE)
    print(f"완료 {result.name}: {len(raw['runs'])} cells")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question")
    ap.add_argument("--repeat-selected", action="store_true")
    args = ap.parse_args()
    execute("gold_nl2sql.json", RESULT, "nl2sql", context_for,
            args.question, args.repeat_selected)


if __name__ == "__main__":
    main()
