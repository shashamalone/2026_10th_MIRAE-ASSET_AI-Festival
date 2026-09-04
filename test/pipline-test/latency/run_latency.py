"""
골든셋 35문항 E2E 지연·품질 계측 하네스 (2026-09-03).
흐름: 소스 무수정 - 노드 함수·LLM 콜백·SQL/SPARQL/임베딩 호출을 이 파일에서 감싸 시간을 기록하고 app.stream()을 순차 실행한다.
입력: goldset/golden_answers_20260824.csv, 출력: latency/traces_*.jsonl(문항·회차별 trace 1행).
제약: CLOVA 60 req/min·60k tok/min 고정창 - 문항 간 7초, 토큰 잔량<30k 또는 요청 잔량<=3이면 reset 대기, SDK 재시도 0, 429는 새 창에서 1회만 재실행(§13.2).
실행: repo 루트에서 mirea python으로 `python test/pipline-test/latency/run_latency.py --rounds 4`.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "src").exists():
    raise SystemExit("repo 루트에서 실행하라 (src/ 가 보여야 한다)")
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import requests  # noqa: E402

# ---------------------------------------------------------------------------
# 0) LLM 객체: 루브릭 §13.2-4 SDK 내부 재시도 끄기. 모델·온도·timeout·max_tokens는 그대로.
#    nodes/plan_query_db/graph_orchestrator가 import하기 전에 바꿔야 한다.
# ---------------------------------------------------------------------------
import agent.get_clova as clova  # noqa: E402


def _disable_sdk_retries(llm):
    root = getattr(llm, "root_client", None)
    if root is not None and hasattr(root, "with_options"):
        llm.root_client = root.with_options(max_retries=0)
        llm.client = llm.root_client.chat.completions
        return "with_options"
    try:
        llm.max_retries = 0
        return "attr"
    except Exception:
        return "unchanged"


RETRY_MODE = {name: _disable_sdk_retries(getattr(clova, name)) for name in ("_llm_plan", "_llm_answer")}

# ---------------------------------------------------------------------------
# 1) 계측 레코드. 문항은 순차 실행이므로 전역 CUR 하나로 충분하다.
#    (웨이브 병렬 노드는 스레드지만 같은 문항 안이라 락만 잡으면 된다)
# ---------------------------------------------------------------------------
_LOCK = threading.Lock()
CUR: dict = {}
T0 = 0.0


def _rec(kind: str, **kw):
    with _LOCK:
        CUR.setdefault(kind, []).append(kw)


def _timed(kind: str, name: str, fn, extra=None):
    def wrapper(*a, **k):
        t0 = time.perf_counter()
        err = None
        try:
            return fn(*a, **k)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            raise
        finally:
            item = {"name": name, "start_s": round(t0 - T0, 3), "ms": round((time.perf_counter() - t0) * 1000, 1)}
            if err:
                item["error"] = err[:300]
            if extra:
                try:
                    item.update(extra(a, k))
                except Exception:  # noqa: BLE001
                    pass
            _rec(kind, **item)

    wrapper.__name__ = getattr(fn, "__name__", name)
    wrapper.__doc__ = getattr(fn, "__doc__", None)
    return wrapper


import agent.nodes as nodes  # noqa: E402
import agent.plan_query_db as pq  # noqa: E402
import agent.utils as utils  # noqa: E402
from agent.graph_logic import graph_orchestrator as go  # noqa: E402
from tools import graph_schema  # noqa: E402

NODE_NAMES = [
    "receive_question_node", "analyze_intent_node", "verify_intent_node",
    "rdb_search_node", "graph_search_node", "vector_search_node",
    "merge_results_node", "generate_answer_node",
]
for _n in NODE_NAMES:
    setattr(nodes, _n, _timed("nodes", _n, getattr(nodes, _n)))
pq.plan_query_node = _timed("nodes", "plan_query_node", pq.plan_query_node)

# 하위 호출: RDB SQL API / 임베딩 / pgvector / Graph seed·fragment·SPARQL
utils.run_sql = _timed("rdb_sql", "run_sql", utils.run_sql)
nodes.embed = _timed("embed", "embed", nodes.embed)
nodes.search_documents = _timed("vector_db", "search_documents", nodes.search_documents)
nodes.resolve_product_ids = _timed("vector_db", "resolve_product_ids", nodes.resolve_product_ids)
nodes.get_coverage = _timed("vector_db", "get_coverage", nodes.get_coverage)
# RDB 내부 단계: 도메인별 target/entity_lookup/UNION 그룹 실행과 SQL 생성·수정 LLM
nodes._execute_target_step = _timed("rdb_sub", "_execute_target_step", nodes._execute_target_step,
                                    extra=lambda a, k: {"domain": (a[0] or {}).get("domain"), "step_id": (a[0] or {}).get("step_id")})
nodes._execute_entity_lookup_step = _timed("rdb_sub", "_execute_entity_lookup_step", nodes._execute_entity_lookup_step,
                                           extra=lambda a, k: {"domain": (a[0] or {}).get("domain"), "step_id": (a[0] or {}).get("step_id")})
nodes._execute_merged_target_group = _timed("rdb_sub", "_execute_merged_target_group", nodes._execute_merged_target_group,
                                            extra=lambda a, k: {"domains": [s.get("domain") for s in (a[0] or [])]})
nodes._draft_query_description = _timed("rdb_llm", "draft", nodes._draft_query_description)
nodes._write_sql = _timed("rdb_llm", "write_sql", nodes._write_sql)
nodes._fix_sql = _timed("rdb_llm", "fix_sql", nodes._fix_sql)
utils._resolve_unknown_concepts_via_llm = _timed("rdb_llm", "concept_fallback", utils._resolve_unknown_concepts_via_llm,
                                                 extra=lambda a, k: {"concepts": list(a[1]) if len(a) > 1 else None})
nodes._run_vector_step = _timed("vector_sub", "_run_vector_step", nodes._run_vector_step,
                                extra=lambda a, k: {"step_id": (a[1] or {}).get("step_id"), "topics": (a[1] or {}).get("topics")})
go.resolve_frame_seed = _timed("graph_sub", "resolve_frame_seed", go.resolve_frame_seed)
go.graph_engine.sparql = _timed("graph_sub", "sparql", go.graph_engine.sparql)
_CatalogCls = type(graph_schema.catalog())
_CatalogCls.select_fragment = _timed("graph_sub", "select_fragment", _CatalogCls.select_fragment)

_orig_run = go.run


def _run_wrapped(*a, **k):
    out = _orig_run(*a, **k)
    _rec("graph_plan", status=out.get("status"), attempts=len(out.get("attempts") or []),
         modes=[x.get("mode") for x in (out.get("attempts") or [])], trace=out.get("trace"))
    return out


go.run = _timed("graph_sub", "orchestrator.run", _run_wrapped)
go.run_theme_membership = _timed("graph_sub", "orchestrator.run_theme_membership", go.run_theme_membership)


class _FallbackHandler(logging.Handler):
    """Oxigraph transport 폴백 경고(로컬 스토어 실패 -> HTTP endpoint)를 trace에 남긴다."""

    def emit(self, record):
        _rec("graph_fallback", msg=record.getMessage()[:300], t_s=round(time.perf_counter() - T0, 3))


logging.getLogger("infrastructure.graph_db.client").addHandler(_FallbackHandler())
logging.getLogger("infrastructure.graph_db.client").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# 2) LLM 콜백: 호출별 시간·모델·토큰·에러(429 포함)
# ---------------------------------------------------------------------------
from langchain_core.callbacks import BaseCallbackHandler  # noqa: E402


class LLMTimer(BaseCallbackHandler):
    def __init__(self):
        self._start: dict = {}

    def _begin(self, serialized, run_id):
        model = ""
        try:
            model = (serialized or {}).get("kwargs", {}).get("model_name") or (serialized or {}).get("name", "")
        except Exception:  # noqa: BLE001
            pass
        self._start[str(run_id)] = (time.perf_counter(), model)

    def on_chat_model_start(self, serialized, messages, *, run_id, **kw):
        self._begin(serialized, run_id)

    def on_llm_start(self, serialized, prompts, *, run_id, **kw):
        self._begin(serialized, run_id)

    def on_llm_end(self, response, *, run_id, **kw):
        t0, model = self._start.pop(str(run_id), (time.perf_counter(), ""))
        usage = None
        try:
            usage = response.llm_output.get("token_usage") if response.llm_output else None
            if usage:
                usage = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        except Exception:  # noqa: BLE001
            pass
        _rec("llm", model=model, start_s=round(t0 - T0, 3), ms=round((time.perf_counter() - t0) * 1000, 1), usage=usage)

    def on_llm_error(self, error, *, run_id, **kw):
        t0, model = self._start.pop(str(run_id), (time.perf_counter(), ""))
        text = f"{type(error).__name__}: {error}"
        _rec("llm", model=model, start_s=round(t0 - T0, 3), ms=round((time.perf_counter() - t0) * 1000, 1),
             error=text[:300], is_429=("429" in text or "42901" in text))


# ---------------------------------------------------------------------------
# 3) CLOVA 한도 프로브 + 페이싱 가드
#    실측(2026-09-03): 429는 요청 60/min이 아니라 토큰 60k/min에서 먼저 난다.
#    호출당 prompt(~4k)+max_tokens(2048)가 예약되어 문항당 ~27k가 잡히므로
#    토큰 잔량을 기준으로 창을 관리한다(ratelimit 노트북 6단계 가드의 토큰 확장).
# ---------------------------------------------------------------------------
CLOVA_BASE = "https://clovastudio.stream.ntruss.com/v1/openai"
CLOVA_KEY = os.getenv("CLOVASTUDIO_API_KEY") or os.getenv("CLOVA_API_KEY")
MIN_TOKENS_TO_START = 30_000
MIN_TOKENS_TO_RETRY = 45_000


def probe_remaining(model="HCX-007") -> dict:
    """가장 싼 호출 1회로 x-ratelimit 헤더를 읽는다(요청 1건·토큰 2건 소비)."""
    try:
        r = requests.post(
            f"{CLOVA_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {CLOVA_KEY}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "1"}],
                  "max_completion_tokens": 1, "temperature": 0},
            timeout=30,
        )
        h = r.headers

        def _sec(v):
            return float(str(v or "0s").rstrip("s"))

        return {
            "status": r.status_code,
            "remaining": int(h.get("x-ratelimit-remaining-requests") or -1),
            "reset_s": _sec(h.get("x-ratelimit-reset-requests")),
            "remaining_tokens": int(h.get("x-ratelimit-remaining-tokens") or -1),
            "reset_tokens_s": _sec(h.get("x-ratelimit-reset-tokens")),
        }
    except Exception as e:  # noqa: BLE001
        return {"status": -1, "remaining": -1, "reset_s": 0.0, "remaining_tokens": -1, "reset_tokens_s": 0.0,
                "error": str(e)[:200]}


def wait_for_budget(min_tokens: int, floor_requests: int = 3) -> dict:
    """요청 잔량<=floor 또는 토큰 잔량<min_tokens이면 창 리셋까지 잔다. 대기 초를 함께 돌려준다."""
    waited = 0.0
    for _ in range(4):
        p = probe_remaining()
        if p["status"] == 429 or (0 <= p["remaining"] <= floor_requests) or (0 <= p["remaining_tokens"] < min_tokens):
            w = max(p["reset_s"], p["reset_tokens_s"], 1.0) + 0.5
            print(f"[guard] remaining={p['remaining']} tokens={p['remaining_tokens']} -> {w:.1f}s 대기", flush=True)
            time.sleep(w)
            waited += w
            continue
        p["waited_s"] = round(waited, 1)
        return p
    p["waited_s"] = round(waited, 1)
    return p


# ---------------------------------------------------------------------------
# 4) 파이프라인 1회 실행 -> trace dict
# ---------------------------------------------------------------------------
from agent.graph import app  # noqa: E402  (위 패치 이후에 import해야 래퍼가 그래프에 들어간다)


def _cap_rows(obj, n=30):
    """step_results/merged_rows의 행 목록을 n건으로 자른다(키·건수는 보존)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("rows", "chunks") and isinstance(v, list):
                out[k] = v[:n]
                out[f"{k}_total"] = len(v)
            else:
                out[k] = _cap_rows(v, n)
        return out
    if isinstance(obj, list):
        return [_cap_rows(x, n) for x in obj]
    return obj


def run_once(qid: str, question: str, round_no: int) -> dict:
    global CUR, T0
    CUR = {}
    T0 = time.perf_counter()
    inputs = {"question_id": f"{qid}-r{round_no}-{uuid.uuid4().hex[:4]}", "question": question}
    trace = {
        "question_id": qid, "round": round_no, "question": question,
        "nodes_executed": [], "intent": None, "verified_intent": None, "plan": [], "route": {},
        "step_results": {}, "merged_rows": [], "answer": {}, "trace_messages": [], "errors": [],
        "status": "ok", "exception": None,
    }
    t_start = time.perf_counter()
    try:
        for output in app.stream(inputs, config={"callbacks": [LLMTimer()]}):
            for node_name, update in output.items():
                trace["nodes_executed"].append(node_name)
                update = update or {}
                for msg in update.get("trace", []) or []:
                    trace["trace_messages"].append(str(msg))
                if node_name == "analyze_intent":
                    trace["intent"] = update.get("intent")
                elif node_name == "verify_intent":
                    trace["verified_intent"] = update.get("intent")
                elif node_name == "plan_query":
                    trace["plan"] = update.get("plan") or []
                    trace["route"] = update.get("route") or {}
                elif node_name in {"rdb_search", "graph_search", "vector_search"}:
                    for sid, res in (update.get("step_results") or {}).items():
                        trace["step_results"][sid] = _cap_rows(res)
                        if isinstance(res, dict) and res.get("error"):
                            trace["errors"].append({"node": node_name, "step_id": sid, "error": str(res["error"])[:500]})
                elif node_name == "merge_results":
                    trace["merged_rows"] = (update.get("merged_rows") or [])[:30]
                    trace["merged_rows_total"] = len(update.get("merged_rows") or [])
                elif node_name == "generate_answer":
                    raw = update.get("answer", {})
                    try:
                        trace["answer"] = json.loads(raw) if isinstance(raw, str) else raw
                    except Exception:  # noqa: BLE001
                        trace["answer"] = {"raw": raw}
    except Exception as e:  # noqa: BLE001
        trace["status"] = "exception"
        trace["exception"] = f"{type(e).__name__}: {e}"[:800]
    trace["e2e_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
    trace["timing"] = dict(CUR)
    llm = CUR.get("llm", [])
    trace["rate_limit"] = {
        "llm_calls": len(llm),
        "llm_errors": sum(1 for x in llm if x.get("error")),
        "status_429_count": sum(1 for x in llm if x.get("is_429")),
        "embed_calls": len(CUR.get("embed", [])),
        "prompt_tokens": sum((x.get("usage") or {}).get("prompt_tokens") or 0 for x in llm),
        "total_tokens": sum((x.get("usage") or {}).get("total_tokens") or 0 for x in llm),
    }
    if trace["rate_limit"]["status_429_count"] or "429" in (trace["exception"] or ""):
        trace["status"] = "rate_limited"
    elif any("timeout" in (x.get("error") or "").lower() or "timed out" in (x.get("error") or "").lower() for x in llm) \
            or "timeout" in (trace["exception"] or "").lower():
        trace["status"] = "timeout"
    return trace


def load_golden(ids: set[str] | None) -> list[tuple[str, str]]:
    rows = list(csv.DictReader(open(ROOT / "goldset" / "golden_answers_20260824.csv", encoding="utf-8-sig")))
    out = []
    for r in rows:
        qid = f"Q{int(r['id'])}"
        if ids and qid not in ids:
            continue
        out.append((qid, r["question"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--min-gap", type=float, default=7.0)
    args = ap.parse_args()

    ids = {x.strip() for x in args.ids.split(",") if x.strip()} or None
    cases = load_golden(ids)
    out_path = Path(args.out) if args.out else ROOT / "test" / "pipline-test" / "latency" / f"traces_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[run] {len(cases)}문항 x {args.rounds}회차 -> {out_path}", flush=True)
    print(f"[run] sdk retry mode: {RETRY_MODE}", flush=True)

    with open(out_path, "a", encoding="utf-8") as f:
        for round_no in range(1, args.rounds + 1):
            for qid, question in cases:
                for attempt in (1, 2):
                    # §13.2-3/6: 시작 전 잔량 확인. 재실행은 더 큰 여유(새 창)를 요구한다.
                    before = wait_for_budget(MIN_TOKENS_TO_START if attempt == 1 else MIN_TOKENS_TO_RETRY)
                    t0 = time.time()
                    print(f"\n===== [{qid} r{round_no}{' retry' if attempt == 2 else ''}] tokens={before.get('remaining_tokens')} | {question[:60]}", flush=True)
                    trace = run_once(qid, question, round_no)
                    after = probe_remaining()
                    trace["rate_limit"].update({
                        "remaining_before": before.get("remaining"),
                        "remaining_tokens_before": before.get("remaining_tokens"),
                        "guard_wait_s": before.get("waited_s"),
                        "remaining_after": after.get("remaining"),
                        "remaining_tokens_after": after.get("remaining_tokens"),
                        "reset_after": f"{after.get('reset_s')}s",
                    })
                    trace["attempt"] = attempt
                    trace["superseded"] = (trace["status"] == "rate_limited" and attempt == 1)
                    f.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
                    f.flush()
                    ans = (trace.get("answer") or {}).get("answer", "")
                    print(f"[done] {qid} r{round_no} a{attempt} status={trace['status']} e2e={trace['e2e_ms']/1000:.1f}s "
                          f"llm={trace['rate_limit']['llm_calls']} tok={trace['rate_limit']['total_tokens']} "
                          f"rem={after.get('remaining')}/{after.get('remaining_tokens')} | {str(ans)[:100]}", flush=True)
                    if trace["status"] == "rate_limited" and attempt == 1:
                        print("[guard] 429 -> 새 창에서 1회 재실행", flush=True)
                        continue
                    break
                elapsed = time.time() - t0
                time.sleep(max(0.0, args.min_gap - elapsed))  # §13.2-2 문항 간 최소 7초
    print(f"[run] 완료 -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
