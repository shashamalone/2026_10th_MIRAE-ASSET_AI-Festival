"""Notebook-only observation of the real app.stream path; no production edits.

Importing this module does not import the agent, open a DB, or call a model.
Run guards are process-local. All temporary instrumentation is restored, even
after errors/interrupts. Viewer functions only read saved in-memory data.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from functools import wraps
import hashlib
from html import escape
import importlib.util
import inspect
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "artifacts/runs"
AGENT_ID = "codex-t139-sql-0905"
NODE_NAMES = {"receive_question", "analyze_intent", "verify_intent", "plan_query",
              "rdb_search", "graph_search", "vector_search", "merge_results", "generate_answer"}
_RUN_LOCK = threading.Lock()
_ATTEMPTED: set[str] = set()
_LOADED_SOURCE_HASH: str | None = None


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _source_manifest():
    hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
              for folder in ("src", "ontology") for p in sorted((ROOT / folder).rglob("*"))
              if p.suffix in {".py", ".ttl"}}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unavailable", None
    return {"commit": commit, "dirty": dirty, "source_sha256": hashes,
            "source_fingerprint": digest, "python": sys.version, "python_executable": sys.executable,
            "repo": str(ROOT)}


def dependency_status():
    """Availability, not a live connection/credential test."""
    return {name: importlib.util.find_spec(name) is not None
            for name in ("IPython", "ipykernel", "dotenv", "langgraph", "langchain_naver", "psycopg2")}


class Redactor:
    KEYS = {"api_key", "authorization", "password", "secret", "access_token", "refresh_token", "database_url", "dsn"}

    def __init__(self):
        self.secrets = sorted({v for k, v in os.environ.items() if v and len(v) >= 8
                               and (re.search(r"(?:API_KEY|PASSWORD|SECRET|ACCESS_TOKEN|DATABASE_URL)$", k)
                                    or k.lower() == "clova")}, key=len, reverse=True)

    def text(self, value):
        text = str(value)
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)(Bearer\s+)[^\s\"'<>]+", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)((?:password|api_key|access_token)=)[^\s&]+", r"\1[REDACTED]", text)
        return text

    def clean(self, value):
        if isinstance(value, dict):
            return {str(k): "[REDACTED]" if str(k).lower() in self.KEYS else self.clean(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self.text(value)


class _LogWriter(io.TextIOBase):
    def __init__(self, file, redactor):
        self.file, self.redactor, self.buffer = file, redactor, ""
        self.lock = threading.RLock()

    def write(self, text):
        with self.lock:
            self.buffer += text
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                self.file.write(self.redactor.text(line) + "\n")
            self.file.flush()
        return len(text)

    def flush(self):
        with self.lock:
            if self.file.closed:
                return
            if self.buffer:
                self.file.write(self.redactor.text(self.buffer))
                self.buffer = ""
            self.file.flush()


def _node_context():
    try:
        from langgraph.config import get_config
        return get_config().get("metadata", {}).get("langgraph_node", "setup")
    except (ImportError, RuntimeError):
        return "setup"


class Recorder:
    def __init__(self, redactor):
        self.redactor, self.start = redactor, time.perf_counter()
        self.calls, self.nodes, self.llm = [], [], []
        self.lock = threading.RLock()

    def elapsed(self):
        return round(time.perf_counter() - self.start, 4)

    def wrapper(self, fn, kind, describe):
        signature = inspect.signature(fn)

        @wraps(fn)
        def observed(*args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            item = {"kind": kind, "node": _node_context(), "start_s": self.elapsed(),
                    **self.redactor.clean(describe(bound.arguments))}
            with self.lock:
                item["call_id"] = len(self.calls) + 1
                self.calls.append(item)
            try:
                result = fn(*args, **kwargs)
                item["result"] = self.redactor.clean(result)
                item["returned_rows"] = len(result) if isinstance(result, list) else None
                item["status"] = "ok"
                return result
            except BaseException as exc:
                item.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "error",
                            error=self.redactor.text(f"{type(exc).__name__}: {exc}"))
                raise
            finally:
                item["end_s"] = self.elapsed()
                item["duration_s"] = round(item["end_s"] - item["start_s"], 4)
        return observed


def _callback(recorder):
    from langchain_core.callbacks import BaseCallbackHandler

    class TraceCallback(BaseCallbackHandler):
        def __init__(self):
            self.running_nodes, self.running_llm = {}, {}

        def on_chain_start(self, serialized, inputs, *, run_id, **kwargs):
            name = kwargs.get("name") or (serialized or {}).get("name")
            if name not in NODE_NAMES:
                return
            item = {"run_id": str(run_id), "node": name, "start_s": recorder.elapsed(),
                    "input": recorder.redactor.clean(inputs), "status": "running"}
            with recorder.lock:
                recorder.nodes.append(item)
                self.running_nodes[str(run_id)] = item

        def _end_node(self, run_id, output=None, error=None):
            with recorder.lock:
                item = self.running_nodes.pop(str(run_id), None)
                if item is not None:
                    item.update(end_s=recorder.elapsed(), status="error" if error else "ok")
                    item["duration_s"] = round(item["end_s"] - item["start_s"], 4)
                    if error:
                        item["error"] = recorder.redactor.text(error)
                    else:
                        item["output"] = recorder.redactor.clean(output)

        def on_chain_end(self, outputs, *, run_id, **kwargs):
            self._end_node(run_id, outputs)

        def on_chain_error(self, error, *, run_id, **kwargs):
            self._end_node(run_id, error=f"{type(error).__name__}: {error}")

        def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
            # Do not collect API headers, messages/prompts, or hidden reasoning.
            details = (serialized or {}).get("kwargs") or {}
            item = {"run_id": str(run_id), "node": (kwargs.get("metadata") or {}).get("langgraph_node", _node_context()),
                    "model": details.get("model_name") or details.get("model") or (serialized or {}).get("name"),
                    "start_s": recorder.elapsed(), "status": "running"}
            with recorder.lock:
                recorder.llm.append(item)
                self.running_llm[str(run_id)] = item

        def on_llm_end(self, response, *, run_id, **kwargs):
            with recorder.lock:
                item = self.running_llm.pop(str(run_id), None)
                if item is None:
                    return
                usage = (response.llm_output or {}).get("token_usage") or {}
                if not usage:
                    for generation in response.generations or []:
                        for result in generation:
                            usage = getattr(getattr(result, "message", None), "usage_metadata", None) or usage
                item.update(status="ok", end_s=recorder.elapsed(), usage=recorder.redactor.clean(usage))
                item["duration_s"] = round(item["end_s"] - item["start_s"], 4)

        def on_llm_error(self, error, *, run_id, **kwargs):
            with recorder.lock:
                item = self.running_llm.pop(str(run_id), None)
                if item is not None:
                    item.update(status="error", end_s=recorder.elapsed(), error=recorder.redactor.text(f"{type(error).__name__}: {error}"))
                    item["duration_s"] = round(item["end_s"] - item["start_s"], 4)
    return TraceCallback()


@contextmanager
def instrument(recorder, snapshot_path):
    """Scoped, nonpersisting wrappers around actual query entry points."""
    from agent import utils, nodes, get_clova
    from agent.graph_logic import graph_engine
    from infrastructure.vector_db.client import VectorDBClient
    from tools import schema_snapshot

    def direct_search(a):
        sql, params = a["self"]._direct_sql(a.get("product_ids"), a.get("section_types"))
        return {"sql": sql, "params": [a["vector"], *params, a["vector"], a["top_k"]], "transport": "direct"}

    with ExitStack() as stack:
        stack.enter_context(patch.object(schema_snapshot, "DEFAULT_SNAPSHOT_PATH", snapshot_path))
        stack.enter_context(patch.dict(os.environ, {"RDB_SCHEMA_SNAPSHOT_PATH": str(snapshot_path)}))
        for target, name, kind, describe in [
            (utils, "run_sql", "sql", lambda a: {"sql": a["sql"], "transport": "sql_api"}),
            (graph_engine, "sparql", "sparql", lambda a: {"sparql": a["query"]}),
            (nodes, "embed", "embedding", lambda a: {"text": a["text"]}),
            (VectorDBClient, "_search_direct", "sql", direct_search),
            (VectorDBClient, "_run_read_sql", "vector_read", lambda a: {"sql": a["sql"], "params": a.get("params"),
                "transport": "direct" if a["self"]._has_direct_dsn else "sql_api (nested run_sql captured)"}),
        ]:
            original = getattr(target, name)
            stack.enter_context(patch.object(target, name, recorder.wrapper(original, kind, describe)))
        # A manual execution should not secretly repeat failed model requests.
        # Restore each SDK object when this run leaves the context.
        for name in ("_llm_plan", "_llm_answer"):
            llm = getattr(get_clova, name)
            root = getattr(llm, "root_client", None)
            if root is not None and hasattr(root, "with_options"):
                client = root.with_options(max_retries=0)
                stack.enter_context(patch.object(llm, "root_client", client))
                stack.enter_context(patch.object(llm, "client", client.chat.completions))
        # Also disable the node's separate SQL-429 waiting/retry loop locally.
        stack.enter_context(patch.object(nodes, "_MAX_RATE_LIMIT_WAITS", 0))
        yield


def _merge_update(state, update):
    for key, value in update.items():
        if key == "step_results":
            state[key] = {**state.get(key, {}), **(value or {})}
        elif key == "trace":
            state[key] = state.get(key, []) + (value or [])
        else:
            state[key] = value


def collect_stream(app, inputs, recorder, *, on_event=None, events_file=None):
    """Execute app.stream exactly once, retaining partial state on failure."""
    report = {"question": inputs["question"], "question_id": inputs["question_id"], "status": "running",
              "events": [], "final_state": dict(inputs), "initial_intent": None, "verified_intent": None}
    try:
        for chunk in app.stream(inputs, config={"callbacks": [_callback(recorder)]}, stream_mode="updates"):
            for node, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                clean = recorder.redactor.clean(update)
                event = {"index": len(report["events"]), "node": node, "received_s": recorder.elapsed(), "update": clean}
                report["events"].append(event)
                _merge_update(report["final_state"], clean)
                if node == "analyze_intent":
                    report["initial_intent"] = clean.get("intent")
                if node == "verify_intent":
                    report["verified_intent"] = clean.get("intent")
                if events_file is not None:
                    events_file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
                    events_file.flush()
                if on_event is not None:
                    try:
                        on_event(event)
                    except Exception as exc:
                        report.setdefault("viewer_warnings", []).append(recorder.redactor.text(str(exc)))
        report["status"] = "completed" if report["final_state"].get("answer") else "no_final_answer"
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "error",
                      exception=recorder.redactor.text(f"{type(exc).__name__}: {exc}"))
    report["elapsed_s"] = recorder.elapsed()
    state = report["final_state"]
    report.update(step_results=state.get("step_results", {}), plan=state.get("plan"), route=state.get("route"),
                  calls=recorder.calls, node_runs=recorder.nodes, llm_calls=recorder.llm)
    raw = state.get("answer")
    try:
        report["answer"] = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        report["answer"] = {"answer": str(raw), "parse_error": True}
    if report["answer"] is not None and not isinstance(report["answer"], dict):
        report["answer"] = {"answer": str(report["answer"]), "parse_error": True}
    return report


def _save_report(report, run_dir):
    """Only called for a newly created, owned run directory."""
    (run_dir / "trace.json").write_text(json_text(report), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json_text(report["manifest"]), encoding="utf-8")
    (run_dir / "calls.json").write_text(json_text(report.get("calls", [])), encoding="utf-8")
    (run_dir / "answer.md").write_text((report.get("answer") or {}).get("answer") or "최종 답변 미생성 — trace.json의 exception 확인", encoding="utf-8")
    queries_dir = run_dir / "queries"
    queries_dir.mkdir()
    for call in report.get("calls", []):
        for field in ("sql", "sparql"):
            if call.get(field):
                (queries_dir / f"{call['call_id']:03d}.{field}").write_text(call[field], encoding="utf-8")


def run_question(question, *, env_file, question_id="manual", allow_repeat=False, on_event=None):
    global _LOADED_SOURCE_HASH
    question = str(question).strip()
    if not question:
        raise ValueError("질문을 입력하세요.")
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("이미 질문을 실행 중입니다. 같은 커널에서 동시에 실행하지 마세요.")
    try:
        manifest = _source_manifest()
        fingerprint = manifest["source_fingerprint"]
        if _LOADED_SOURCE_HASH is not None and fingerprint != _LOADED_SOURCE_HASH:
            raise RuntimeError("소스가 실행 중 변경됐습니다. 최신 코드를 쓰려면 커널을 재시작하세요.")
        signature = hashlib.sha256((fingerprint + "\n" + question).encode()).hexdigest()
        if signature in _ATTEMPTED and not allow_repeat:
            raise RuntimeError("이 커널에서 이미 시도한 질문입니다. 결과 확인 셀을 사용하세요. 의도적인 재실행만 ALLOW_REPEAT=True로 허용하세요.")
        env_file = Path(env_file).resolve()
        if not env_file.is_file():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {env_file}")
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
        if not any(os.getenv(k) for k in ("CLOVA_API_KEY", "CLOVASTUDIO_API_KEY", "clova")):
            raise RuntimeError("Clova 키가 없습니다. ENV_FILE을 확인하세요. 노트북에 키를 직접 붙여넣지 마세요.")
        if str(ROOT / "src") not in sys.path:
            sys.path.insert(0, str(ROOT / "src"))
        loaded = sys.modules.get("agent.nodes")
        if loaded is not None and ROOT not in Path(loaded.__file__).resolve().parents:
            raise RuntimeError("다른 저장소의 agent가 이미 로드됐습니다. 커널을 재시작하세요.")
        from agent.graph import app
        _LOADED_SOURCE_HASH = fingerprint
        run_id = "manual-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        run_dir = OUTPUT_ROOT / run_id / AGENT_ID
        run_dir.mkdir(parents=True, exist_ok=False)
        _ATTEMPTED.add(signature)
        redactor = Redactor()
        recorder = Recorder(redactor)
        manifest.update(run_id=run_id, started_at=datetime.now(timezone.utc).isoformat(), env_file=str(env_file),
                        whole_question_attempts=1, sdk_chat_retries=0, sql_retry_budget=1, output_dir=str(run_dir))
        with (run_dir / "run.log").open("x", encoding="utf-8") as log, \
             (run_dir / "events.jsonl").open("x", encoding="utf-8") as events:
            writer = _LogWriter(log, redactor)
            handler = logging.StreamHandler(writer)
            logging.getLogger().addHandler(handler)
            try:
                with instrument(recorder, run_dir / "schema_snapshot.json"), redirect_stdout(writer), redirect_stderr(writer):
                    report = collect_stream(app, {"question": question, "question_id": question_id, "max_sql_retries": 1},
                                            recorder, on_event=on_event, events_file=events)
            except (Exception, KeyboardInterrupt) as exc:
                report = {"question": question, "question_id": question_id, "status": "setup_error",
                          "exception": redactor.text(f"{type(exc).__name__}: {exc}"), "elapsed_s": recorder.elapsed(),
                          "events": [], "step_results": {}, "calls": recorder.calls, "node_runs": recorder.nodes,
                          "llm_calls": recorder.llm, "answer": None, "final_state": {}}
            finally:
                logging.getLogger().removeHandler(handler)
                writer.close()
        snapshot = run_dir / "schema_snapshot.json"
        if snapshot.is_file():
            try:
                from tools.schema_snapshot import snapshot_release_id
                manifest["release_id"] = snapshot_release_id(json.loads(snapshot.read_text(encoding="utf-8")))
            except (ValueError, OSError) as exc:
                manifest["snapshot_warning"] = redactor.text(f"{type(exc).__name__}: {exc}")
        manifest["ended_at"] = datetime.now(timezone.utc).isoformat()
        report.update(manifest=manifest, run_dir=str(run_dir))
        report = redactor.clean(report)
        _save_report(report, run_dir)
        return report
    finally:
        _RUN_LOCK.release()


def load_report(path, *, index=0):
    """Read manual trace.json or a prior team's traces.jsonl; never rerun it."""
    path = Path(path).expanduser()
    path = path if path.is_absolute() else ROOT / path
    if path.is_dir():
        path = path / ("trace.json" if (path / "trace.json").exists() else "traces.jsonl")
    text = path.read_text(encoding="utf-8")
    raw = json.loads(text.splitlines()[index]) if path.suffix == ".jsonl" else json.loads(text)
    if "final_state" not in raw:
        raw = {**raw, "initial_intent": raw.get("intent"), "final_state": {"trace": raw.get("trace_messages", []),
            "step_results": raw.get("step_results", {})}, "elapsed_s": (raw.get("e2e_ms") or 0) / 1000,
            "node_runs": (raw.get("timing") or {}).get("nodes", []),
            "llm_calls": (raw.get("timing") or {}).get("llm", []),
            "viewer_note": "과거 형식: 전체 node 입력·하위 호출이 저장되지 않은 항목은 복구할 수 없습니다."}
    raw["loaded_from"] = str(path)
    return Redactor().clean(raw)


def show_json(value, title="JSON", *, collapsed=False):
    from IPython.display import HTML, display
    body = f"<pre style='white-space:pre-wrap;overflow-wrap:anywhere'>{escape(json_text(value))}</pre>"
    if collapsed:
        display(HTML(f"<details><summary>{escape(title)}</summary>{body}</details>"))
    else:
        display(HTML(f"<h4>{escape(title)}</h4>{body}"))


def show_table(rows, *, limit=25):
    from IPython.display import HTML, display
    rows = list(rows or [])
    selected = rows if limit is None else rows[:limit]
    if not selected:
        print("반환 행 없음 — 미실행/차단/0건 여부는 단계 상태를 확인하세요.")
        return
    keys = list(dict.fromkeys(k for row in selected if isinstance(row, dict) for k in row))
    if not keys:
        show_json(selected)
        return
    heads = "".join(f"<th>{escape(str(k))}</th>" for k in keys)
    body = "".join("<tr>" + "".join(f"<td style='max-width:440px;white-space:pre-wrap;overflow-wrap:anywhere'>{escape(json_text(row.get(k)))}</td>" for k in keys) + "</tr>" for row in selected)
    display(HTML(f"<p>반환 {len(rows)}행 중 {len(selected)}행 표시 (원본 DB 전체 건수 아님)</p><div style='overflow:auto'><table border='1'><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table></div>"))


def show_summary(report):
    if not report:
        print("실행하거나 저장 기록을 불러오면 결과가 표시됩니다.")
        return
    show_json({k: report.get(k) for k in ("question_id", "question", "status", "elapsed_s", "exception", "run_dir", "loaded_from", "viewer_note")}, "실행 요약 — 정상 종료와 정답 여부는 별개")
    manifest = report.get("manifest") or {}
    show_json({k: manifest.get(k) for k in ("commit", "dirty", "python_executable", "source_fingerprint", "release_id", "started_at", "ended_at")}, "코드·데이터 버전")
    show_table([{k: r.get(k) for k in ("node", "name", "start_s", "end_s", "duration_s", "ms", "status", "error")} for r in report.get("node_runs", [])], limit=None)
    show_table([{"step_id": sid, "engine": r.get("engine"), "status": r.get("status") or ("error" if r.get("error") else "blocked" if r.get("skipped_reason") else "returned"),
                 "rows": r.get("rows_total", len(r.get("rows") or r.get("chunks") or [])),
                 "reason": r.get("error") or r.get("skipped_reason") or r.get("note")}
                for sid, r in (report.get("step_results") or {}).items()], limit=None)


def show_steps(report, engine, *, row_limit=25):
    from IPython.display import Code, display
    found = False
    for sid, result in ((report or {}).get("step_results") or {}).items():
        if result.get("engine") != engine:
            continue
        found = True
        print(f"\n[{sid}] {engine}")
        show_json({k: v for k, v in result.items() if k not in {"sql", "sparql", "rows", "chunks", "evidence"}}, "상태·조건·출력 컬럼·가정·범위", collapsed=True)
        for kind in ("sql", "sparql"):
            if result.get(kind):
                print(f"[{kind}] 결과에 기록된 쿼리 — 실제 호출 여부/오류는 전체 호출 기록 참고")
                display(Code(result[kind], language=kind))
        for query in result.get("hydration_queries") or []:
            print("[통합 순위 후 상세 조회]", query.get("domain"))
            display(Code(query.get("sql") or "", language="sql"))
        show_table(result.get("rows") or [], limit=row_limit) if engine != "vector" else None
        if result.get("evidence"):
            show_json(result["evidence"], "전체 관계 근거", collapsed=True)
        for chunk in result.get("chunks") or []:
            show_json({k: v for k, v in chunk.items() if k != "chunk_text"}, "문서 출처·유사도·페이지·날짜")
            show_json(chunk.get("chunk_text"), "검색된 청크 본문 (문서 전체가 아님)", collapsed=True)
    if not found:
        print(f"{engine} 결과 없음 — 해당 엔진을 쓰지 않았거나 그 전에 중단됐습니다.")


def show_calls(report, *, include_metadata=True):
    from IPython.display import Code, display
    calls = (report or {}).get("calls") or []
    if not calls:
        print("하위 호출 기록 없음. 과거 trace라면 단계별 SQL/SPARQL 셀을 확인하세요.")
    for call in calls:
        if not include_metadata and call.get("node") in {"analyze_intent", "verify_intent", "setup"}:
            continue
        show_json({k: v for k, v in call.items() if k not in {"sql", "sparql", "params", "result"}}, "실제 함수 호출")
        for kind in ("sql", "sparql"):
            if call.get(kind):
                display(Code(call[kind], language=kind))
        if call.get("params") is not None:
            show_json(call["params"], "바인딩 파라미터 (임베딩 포함 가능)", collapsed=True)
        show_json(call.get("result"), "호출이 반환한 전체 결과", collapsed=True)


def show_event(report, index=-1):
    nodes = (report or {}).get("node_runs") or []
    if nodes and "input" in nodes[0]:
        show_json(nodes[index], f"노드 호출 {index}: 실제 입력·출력 전체", collapsed=True)
    else:
        events = (report or {}).get("events") or []
        show_json(events[index] if events else None, "저장된 상태 업데이트 (콜백 입력 기록이 없으면 입력 복구 불가)", collapsed=True)
