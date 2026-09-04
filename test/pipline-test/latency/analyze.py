"""
traces_*.jsonl + golden_eval.jsonl -> 루브릭 채점(Claim 단위) + 단계별 지연 통계 + 보고서용 표.
흐름: 루브릭 §9 규칙(ROUTING_MISS/RETRIEVAL_MISS/GENERATION_OMISSION/UNSUPPORTED_INFERENCE/ABSTAIN subtype)으로
 문항·회차별 판정 -> 오답 원인 A~F 라벨 -> warm(2회차 이후) p50/p95/max·단계 기여·계층 점수 계산.
입력: --traces, --golden. 출력: analysis_summary.json, analysis_tables.md(표1~3·막대), per_run_eval.jsonl.
제약: p95는 nearest-rank(n=3이면 최댓값과 같다). 429/예외/타임아웃 회차는 정답률 분모에서 뺀다.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE_NODES = {
    "query_frame": ["analyze_intent_node", "verify_intent_node"],
    "plan/route_guard": ["plan_query_node"],
    "graph_exec": ["graph_search_node"],
    "rdb_exec": ["rdb_search_node"],
    "vector_exec": ["vector_search_node"],
    "merge": ["merge_results_node"],
    "generate": ["generate_answer_node"],
}
POSITIVE = {"PASS", "EXPECTED_ABSTAIN", "EXTERNAL_DATA_REQUIRED", "PARTIAL_GAP_ACKNOWLEDGED",
            "EXTERNAL_EVIDENCE_PRESENT_OR_SCHEMA_CHECK_NEEDED"}
ABSTAIN_MAP = {
    "invalid_taxonomy": "ABSTAIN_INVALID_TAXONOMY", "domain_mismatch": "ABSTAIN_DOMAIN_MISMATCH",
    "future_unavailable": "ABSTAIN_FUTURE_DATA", "entity_not_found": "ABSTAIN_ENTITY_NOT_FOUND",
    "not_released_as_of_cutoff": "ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF",
}


# ---------------------------------------------------------------------------
# 통계 유틸
# ---------------------------------------------------------------------------
def pct(values, q):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = max(0, math.ceil(q * len(vals)) - 1)
    return vals[k]


def med(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def fmt(v, nd=0):
    if v is None:
        return "미측정"
    return f"{v:,.{nd}f}"


# ---------------------------------------------------------------------------
# trace 접근자
# ---------------------------------------------------------------------------
def answer_text(t):
    a = t.get("answer") or {}
    if isinstance(a, dict):
        # 채점은 사용자에게 보이는 answer 본문만 본다(think_trace의 "부족" 같은 표현을 부재 고지로 인정하지 않는다)
        return str(a.get("answer", "")).lower()
    return str(a).lower()


def exec_text(t):
    return "\n".join([
        json.dumps(t.get("plan") or [], ensure_ascii=False, default=str),
        json.dumps(t.get("step_results") or {}, ensure_ascii=False, default=str),
        json.dumps(t.get("merged_rows") or [], ensure_ascii=False, default=str),
        " ".join(t.get("trace_messages") or []),
    ]).lower()


def flatten_keys(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(str(k).lower())
            flatten_keys(v, acc)
    elif isinstance(obj, list):
        for x in obj:
            flatten_keys(x, acc)
    return acc


def steps_of(t, source):
    return [r for r in (t.get("step_results") or {}).values() if isinstance(r, dict) and r.get("engine") == source]


def step_rows(r):
    if r.get("engine") == "vector":
        return r.get("chunks_total") or r.get("count") or len(r.get("chunks") or [])
    return r.get("rows_total") or r.get("count") or len(r.get("rows") or [])


def executed_sources(t):
    s = {r.get("engine") for r in (t.get("step_results") or {}).values() if isinstance(r, dict)}
    s.discard(None)
    s.add("ontology")
    return s


def source_list(src):
    return [x for x in str(src).split("|") if x]


def has_rows(t, srcs):
    return any(step_rows(r) > 0 for s in srcs for r in steps_of(t, s))


def contains_any(text, tokens):
    return any(str(x).lower() in text for x in tokens or [])


# ---------------------------------------------------------------------------
# Claim 진단 (루브릭 §9)
# ---------------------------------------------------------------------------
def diagnose_claim(case, claim, t):
    availability = claim["availability"]
    srcs = source_list(claim.get("source", ""))
    db_srcs = [s for s in srcs if s in ("rdb", "graph", "vector")]
    executed = executed_sources(t)
    ans = answer_text(t)
    text = exec_text(t)
    keys = flatten_keys({"s": t.get("step_results"), "m": t.get("merged_rows")}, set())

    fields = [f.lower() for f in claim.get("required_fields", [])]
    relations = [r.lower() for r in claim.get("required_relations", [])]
    if db_srcs == ["rdb"]:
        # RDB 근거는 실행된 SQL과 반환 행 키에서만 찾는다(plan/intent 문구의 우연 일치 배제)
        sql_text = " ".join(str(r.get("sql") or "") for r in steps_of(t, "rdb")).lower()
        row_keys = flatten_keys({"s": [r.get("rows") for r in steps_of(t, "rdb")], "m": t.get("merged_rows")}, set())
        fields_ok = (not fields) or any(f in row_keys or f in sql_text for f in fields)
    else:
        fields_ok = (not fields) or any(f in keys or f in text for f in fields)
    relations_ok = (not relations) or any(r in text for r in relations)
    src_executed = (not db_srcs) or any(s in executed for s in db_srcs)
    rows_ok = (not db_srcs) or has_rows(t, db_srcs)
    found = fields_ok and relations_ok and rows_ok

    res = {"question_id": case["question_id"], "claim_id": claim["claim_id"], "claim": claim["label"],
           "availability": availability, "source": claim.get("source"), "source_executed": src_executed,
           "evidence_found": found, "diagnosis": None, "severity": "INFO", "note": ""}

    if availability in ABSTAIN_MAP:
        abstained = contains_any(ans, claim.get("abstain_tokens") or [])
        reason_ok = contains_any(ans, claim.get("abstain_reason_tokens") or [])
        if not abstained:
            res.update(diagnosis="MISSED_ABSTAIN", severity="CRITICAL", note="abstain 없이 답변 생성")
        elif reason_ok:
            res.update(diagnosis="EXPECTED_ABSTAIN")
        else:
            res.update(diagnosis="MISSING_EVIDENCE", severity="ERROR",
                       note=f"abstain은 했으나 subtype 근거 없음(기대 {ABSTAIN_MAP[availability]})")
        return res

    if availability == "deprecated_definition":
        forbidden = [x.lower() for x in case.get("forbidden_fields", [])]
        req = case.get("required_definition_tokens", [])
        if forbidden and contains_any(text, forbidden):
            res.update(diagnosis="STALE_DEFINITION", severity="CRITICAL", note="폐기 컬럼을 plan/SQL에서 사용")
        elif req and not contains_any(ans, req):
            res.update(diagnosis="MISSING_DEFINITION_EXPLANATION", severity="ERROR", note="재정의 사실을 답변에 미명시(§11.5)")
        else:
            res.update(diagnosis="PASS")
        return res

    if availability == "available":
        if not src_executed:
            res.update(diagnosis="ROUTING_MISS", severity="ERROR")
            return res
        if not found:
            errs = [r for s in db_srcs for r in steps_of(t, s) if r.get("error")]
            skips = [r for s in db_srcs for r in steps_of(t, s) if r.get("skipped_reason")]
            if errs:
                res.update(diagnosis="QUERY_EXECUTION_ERROR", severity="ERROR", note=str(errs[0].get("error"))[:160])
            elif skips:
                res.update(diagnosis="QUERY_GENERATION_ERROR", severity="ERROR", note=str(skips[0].get("skipped_reason"))[:160])
            else:
                res.update(diagnosis="RETRIEVAL_MISS", severity="ERROR",
                           note="0행/필드 미검색" if not rows_ok else "필요 컬럼/관계 미검색")
            return res
        tokens = claim.get("answer_tokens") or []
        if tokens and not contains_any(ans, tokens):
            res.update(diagnosis="GENERATION_OMISSION", severity="ERROR")
            return res
        res.update(diagnosis="PASS")
        return res

    if availability in ("external_required", "partial", "not_available_by_design"):
        gap = claim.get("gap_tokens") or ["없", "부족", "외부", "필요", "미제공"]
        acknowledged = contains_any(ans, gap)
        generic = contains_any(ans, claim.get("generic_tokens") or [])
        if found and availability == "external_required":
            res.update(diagnosis="EXTERNAL_EVIDENCE_PRESENT_OR_SCHEMA_CHECK_NEEDED", note="외부 관계/문서가 실제 적재됨 - 수동 확인")
        elif found and availability == "partial":
            res.update(diagnosis="PASS")
        elif acknowledged:
            res.update(diagnosis="EXTERNAL_DATA_REQUIRED" if availability == "external_required" else "PARTIAL_GAP_ACKNOWLEDGED")
        elif availability == "external_required" and generic:
            res.update(diagnosis="GENERATION_OMISSION", severity="ERROR", note="답변불가만 말하고 필요한 외부 데이터 종류를 명시하지 않음(§11.3)")
        elif availability == "external_required":
            res.update(diagnosis="UNSUPPORTED_INFERENCE", severity="CRITICAL", note="외부 필요 항목의 부재를 고지하지 않음")
        else:
            res.update(diagnosis="GENERATION_OMISSION", severity="ERROR", note="부분산출 항목의 부족 사유 미명시(§11.2)")
        return res

    res.update(diagnosis="UNCLASSIFIED", severity="WARN")
    return res


DOMAIN_MAP = {"채권": {"채권"}, "국내ETF": {"국내ETF"}, "해외ETF": {"해외ETF"}, "공모펀드": {"펀드"}, "ETF": {"국내ETF", "해외ETF"}}


def expected_domains(category: str) -> set:
    out = set()
    for part in str(category).replace(",", "·").split("·"):
        part = part.strip()
        if part == "전체":
            return set()
        out |= DOMAIN_MAP.get(part, set())
    return out


def domain_routing_miss(case, t):
    """골든 상품군의 테이블이 하나도 계획되지 않았으면 ROUTING_MISS(필요한 DB 단계 미실행)."""
    exp = set(case.get("expected_domains") or [])
    if not exp or case["golden_data_status"] == "ABSTAIN":
        return None
    planned = {s.get("domain") for s in (t.get("plan") or []) if s.get("engine") == "rdb"}
    if planned and not (planned & exp):
        return {"question_id": case["question_id"], "claim_id": "R0", "claim": f"상품군 라우팅(기대 {sorted(exp)}, 계획 {sorted(planned)})",
                "availability": "available", "source": "rdb", "source_executed": True, "evidence_found": False,
                "diagnosis": "ROUTING_MISS", "severity": "ERROR", "note": "intent product_domain이 골든 상품군과 불일치"}
    return None


def cause_label(case, t, claim_results):
    """오답 원인 A~F 중 하나. 가장 앞 단계에서 실패한 원인을 고른다."""
    if t.get("status") in ("exception", "timeout", "rate_limited"):
        return "F"
    fails = [c for c in claim_results if c["severity"] in ("ERROR", "CRITICAL")]
    if not fails:
        return ""
    route = t.get("route") or {}
    if route.get("blocking_reasons") and not route.get("needs_rdb") and not route.get("needs_graph"):
        return "D"
    stage_rank = {"D": 0, "C": 1, "A": 1, "B": 1, "E": 2}
    labels = []
    for c in fails:
        d = c["diagnosis"]
        srcs = source_list(c.get("source") or "")
        if d in ("ROUTING_MISS", "PLAN_MISS"):
            labels.append("D")
        elif d in ("QUERY_EXECUTION_ERROR", "QUERY_GENERATION_ERROR", "RETRIEVAL_MISS", "STALE_DEFINITION"):
            labels.append({"graph": "A", "vector": "B"}.get(srcs[0] if srcs else "rdb", "C"))
        elif d == "MISSING_EVIDENCE":
            had_reason = any(r.get("skipped_reason") for r in (t.get("step_results") or {}).values() if isinstance(r, dict)) \
                or bool(route.get("blocking_reasons"))
            labels.append("E" if had_reason else "D")
        else:
            labels.append("E")
    return sorted(labels, key=lambda x: stage_rank[x])[0]


OVERRIDES_PATH = HERE / "manual_overrides.json"
OVERRIDES = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")) if OVERRIDES_PATH.exists() else {}


def apply_overrides(case, t, crs):
    """manual_overrides.json: {qid: {"when_sql_contains"|"when_answer_contains": str, "add_codes": [...], "cause": "C", "note": ...}}.
    조건(when_*)이 있으면 그 trace에서 성립할 때만 적용한다. 회차마다 답변이 달라질 수 있어서다."""
    ovs = OVERRIDES.get(case["question_id"])
    if not ovs:
        return crs, None
    if isinstance(ovs, dict):
        ovs = [ovs]
    forced = None
    for ov in ovs:
        crs, c = _apply_one(case, t, crs, ov)
        forced = forced or c
    return crs, forced


def _apply_one(case, t, crs, ov):
    sql_text = " ".join(str(r.get("sql") or "") for r in steps_of(t, "rdb")).lower()
    ans = answer_text(t)
    cond_sql = ov.get("when_sql_contains")
    cond_ans = ov.get("when_answer_contains")
    cond_sql_absent = ov.get("when_sql_lacks")
    if cond_sql and cond_sql.lower() not in sql_text:
        return crs, None
    if cond_ans and cond_ans.lower() not in ans:
        return crs, None
    if cond_sql_absent and cond_sql_absent.lower() in sql_text:
        return crs, None
    for code in ov.get("add_codes", []):
        sev = "CRITICAL" if code in ("UNSUPPORTED_INFERENCE", "UNGROUNDED_CLAIM", "MISSED_ABSTAIN", "STALE_DEFINITION") else "ERROR"
        crs.append({"question_id": case["question_id"], "claim_id": "M", "claim": f"수동 검토: {ov.get('note', '')}",
                    "availability": "-", "source": ov.get("source", "rdb"), "source_executed": True, "evidence_found": False,
                    "diagnosis": code, "severity": sev, "note": ov.get("note", "")})
    return crs, ov.get("cause")


def evaluate(case, t):
    if t.get("status") == "rate_limited":
        return {"question_id": case["question_id"], "round": t["round"], "status": "rate_limited",
                "overall_pass": None, "failure_codes": ["RATE_LIMITED"], "claim_results": [], "cause": "F"}
    crs = [diagnose_claim(case, c, t) for c in case["claims"]]
    rm = domain_routing_miss(case, t)
    if rm:
        crs.insert(0, rm)
    crs, forced_cause = apply_overrides(case, t, crs)
    # 답변 본문이 비었거나 30자 미만이면(예: "[" / 빈 JSON 골격) ANSWER형 문항은 생성 누락으로 본다.
    body = str((t.get("answer") or {}).get("answer") or "").strip() if isinstance(t.get("answer"), dict) else ""
    if case["golden_data_status"] != "ABSTAIN" and t.get("status") == "ok" and len(body) < 30:
        crs.append({"question_id": case["question_id"], "claim_id": "M0", "claim": "답변 본문 비어 있음/무의미",
                    "availability": "-", "source": "generate", "source_executed": True, "evidence_found": False,
                    "diagnosis": "GENERATION_OMISSION", "severity": "ERROR", "note": f"answer 길이 {len(body)}자"})
    codes = sorted({c["diagnosis"] for c in crs if c["diagnosis"] not in POSITIVE})
    critical = any(c["severity"] == "CRITICAL" for c in crs)
    errors = any(c["severity"] == "ERROR" for c in crs)
    infra = t.get("status") in ("exception", "timeout")
    overall = (not critical) and (not errors) and (not infra)
    if infra:
        codes.append(f"INFRA_{t['status'].upper()}")
    return {"question_id": case["question_id"], "round": t["round"], "status": t.get("status"),
            "overall_pass": overall, "policy_pass": not critical, "failure_codes": codes,
            "claim_results": crs, "cause": "" if overall else (forced_cause or cause_label(case, t, crs))}


# ---------------------------------------------------------------------------
# 지연 분해
# ---------------------------------------------------------------------------
def node_ms(t, node):
    return sum(x["ms"] for x in (t.get("timing") or {}).get("nodes", []) if x["name"] == node)


def stage_ms(t):
    out = {}
    for stage, nodes in STAGE_NODES.items():
        out[stage] = sum(node_ms(t, n) for n in nodes)
    gs = (t.get("timing") or {}).get("graph_sub", [])
    out["tbox_grounding"] = sum(x["ms"] for x in gs if x["name"] in ("resolve_frame_seed", "select_fragment"))
    out["graph_sparql"] = sum(x["ms"] for x in gs if x["name"] == "sparql")
    out["rdb_sql_api"] = sum(x["ms"] for x in (t.get("timing") or {}).get("rdb_sql", []))
    out["embed"] = sum(x["ms"] for x in (t.get("timing") or {}).get("embed", []))
    out["vector_db"] = sum(x["ms"] for x in (t.get("timing") or {}).get("vector_db", []))
    return out


def critical_path_ms(t):
    """노드 구간의 합집합 길이(병렬 웨이브는 겹치는 만큼 한 번만 센다)."""
    iv = sorted((x["start_s"] * 1000, x["start_s"] * 1000 + x["ms"]) for x in (t.get("timing") or {}).get("nodes", []))
    total, cur = 0.0, None
    for s, e in iv:
        if cur is None or s > cur[1]:
            if cur:
                total += cur[1] - cur[0]
            cur = [s, e]
        else:
            cur[1] = max(cur[1], e)
    if cur:
        total += cur[1] - cur[0]
    return total


def llm_by_node(t):
    nodes = (t.get("timing") or {}).get("nodes", [])
    out = defaultdict(lambda: {"n": 0, "ms": 0.0})
    for call in (t.get("timing") or {}).get("llm", []):
        owner = "other"
        cands = [n for n in nodes if n["ms"] >= 1 and n["start_s"] - 0.002 <= call["start_s"] <= n["start_s"] + n["ms"] / 1000 + 0.002]
        if cands:
            owner = max(cands, key=lambda n: n["start_s"])["name"]
        out[owner]["n"] += 1
        out[owner]["ms"] += call["ms"]
    return dict(out)


def fallback_ms(t):
    """재시도·폴백 루프에 쓰인 시간: SQL 수정 LLM, Graph plan 교정(2회차 이후 시도), 개념 LLM 폴백, transport 폴백, 429."""
    tm = t.get("timing") or {}
    fix = sum(x["ms"] for x in tm.get("rdb_llm", []) if x["name"] == "fix_sql")
    concept = sum(x["ms"] for x in tm.get("rdb_llm", []) if x["name"] == "concept_fallback")
    # graph 교정: attempts>1 이면 (attempts-1)/attempts 만큼의 orchestrator LLM 시간을 재시도로 본다(근사)
    graph_retry = 0.0
    plans = tm.get("graph_plan", [])
    llm_in_graph = llm_by_node(t).get("graph_search_node", {}).get("ms", 0.0)
    for p in plans:
        n = p.get("attempts") or 0
        if n > 1 and "hcx_graph_plan" in (p.get("modes") or []):
            graph_retry += llm_in_graph * (n - 1) / n
    sql_retries = sum(max(0, (r.get("sql_attempts") or 1) - 1) for r in (t.get("step_results") or {}).values() if isinstance(r, dict))
    return {"fix_sql_ms": fix, "concept_fallback_ms": concept, "graph_plan_retry_ms": graph_retry,
            "graph_transport_fallback": len(tm.get("graph_fallback", [])), "sql_retries": sql_retries,
            "llm_429": t.get("rate_limit", {}).get("status_429_count", 0),
            "total_ms": fix + concept + graph_retry}


def parallelizable_ms(t):
    """서로 의존하지 않는데 순차 실행된 구간: 같은 rdb_search 호출 안의 target/entity_lookup 단계가 2개 이상이면
    (합 - 최댓값), vector 단계의 topic별 임베딩이 2회 이상이면 (합 - 최댓값)."""
    tm = t.get("timing") or {}
    subs = [x for x in tm.get("rdb_sub", []) if x["name"] in ("_execute_target_step", "_execute_entity_lookup_step")]
    # rdb_search_node 호출 창별로 묶는다
    windows = [(n["start_s"], n["start_s"] + n["ms"] / 1000) for n in tm.get("nodes", []) if n["name"] == "rdb_search_node"]
    total = 0.0
    for ws, we in windows:
        inside = [x["ms"] for x in subs if ws <= x["start_s"] <= we]
        if len(inside) >= 2:
            total += sum(inside) - max(inside)
    emb = [x["ms"] for x in tm.get("embed", [])]
    if len(emb) >= 2:
        total += sum(emb) - max(emb)
    return total


def failure_signals(t):
    sig = []
    if t.get("status") != "ok":
        sig.append(t["status"])
    if t.get("rate_limit", {}).get("status_429_count"):
        sig.append("429")
    for sid, r in (t.get("step_results") or {}).items():
        if not isinstance(r, dict):
            continue
        if r.get("error"):
            sig.append(f"{sid}:error")
        elif r.get("skipped_reason"):
            sig.append(f"{sid}:skipped")
        elif str(r.get("status") or "").startswith("abstain"):
            sig.append(f"{sid}:{r['status']}")
        elif step_rows(r) == 0 and r.get("status") not in ("chained",):
            sig.append(f"{sid}:0행")
    if (t.get("route") or {}).get("blocking_reasons"):
        sig.append("plan_block")
    return sig


def route_label(t):
    engines = [s.get("engine") for s in (t.get("plan") or [])]
    g, r, v = "graph" in engines, "rdb" in engines, "vector" in engines
    if not engines:
        return "none"
    deps_graph_to_rdb = any(s.get("engine") == "rdb" and any(str(d).startswith("graph") for d in (s.get("depends_on") or [])) for s in t.get("plan") or [])
    if g and r:
        base = "graph_then_rdb" if deps_graph_to_rdb else "graph+rdb(parallel)"
    elif g:
        base = "graph_only"
    elif r:
        base = "rdb_only"
    else:
        base = "vector_only"
    return base + ("+vector" if v and base != "vector_only" else "")


# ---------------------------------------------------------------------------
# 집계
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", default=str(HERE / "traces_full.jsonl"))
    ap.add_argument("--golden", default=str(HERE / "golden_eval.jsonl"))
    ap.add_argument("--warm-from", type=int, default=2)
    args = ap.parse_args()

    golden = {}
    for line in open(args.golden, encoding="utf-8"):
        c = json.loads(line)
        golden[c["question_id"]] = c
    import csv
    for r in csv.DictReader(open(HERE.parents[2] / "goldset" / "golden_answers_20260824.csv", encoding="utf-8-sig")):
        q = f"Q{int(r['id'])}"
        if q in golden:
            golden[q]["question"] = r["question"]
            golden[q]["expected_domains"] = expected_domains(r["product_category"])
    traces = [json.loads(l) for l in open(args.traces, encoding="utf-8") if l.strip()]
    # 429로 대체 실행된 회차는 superseded=True. 통계에서는 재실행분을 쓰고 429 건수는 따로 센다.
    n_429_runs = sum(1 for t in traces if t.get("superseded"))
    traces = [t for t in traces if not t.get("superseded")]
    by_q = defaultdict(list)
    for t in traces:
        by_q[t["question_id"]].append(t)
    qids = [f"Q{i}" for i in range(1, 36) if f"Q{i}" in by_q]

    evals = []
    for t in traces:
        evals.append(evaluate(golden[t["question_id"]], t))
    with open(HERE / "per_run_eval.jsonl", "w", encoding="utf-8") as f:
        for e in evals:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    ev_by = {(e["question_id"], e["round"]): e for e in evals}

    warm = [t for t in traces if t["round"] >= args.warm_from]
    cold = [t for t in traces if t["round"] < args.warm_from]
    warm_ok = [t for t in warm if t["status"] == "ok"]

    # ----- 표 1 -----
    rows1 = []
    for q in qids:
        ts = [t for t in by_q[q] if t["round"] >= args.warm_from]
        ts_ok = [t for t in ts if t["status"] == "ok"]
        e2e = [t["e2e_ms"] for t in ts_ok]
        st = [stage_ms(t) for t in ts_ok]
        evs = [ev_by[(q, t["round"])] for t in ts]
        scored = [e for e in evs if e["overall_pass"] is not None]
        passes = sum(1 for e in scored if e["overall_pass"])
        causes = Counter(e["cause"] for e in scored if not e["overall_pass"] and e["cause"])
        codes = Counter(c for e in scored for c in e["failure_codes"])
        sig = Counter(s for t in ts for s in failure_signals(t))
        rows1.append({
            "id": q, "question": golden[q]["question"][:38] if "question" in golden[q] else "",
            "type": golden[q]["golden_data_status"], "route": Counter(route_label(t) for t in ts).most_common(1)[0][0] if ts else "미측정",
            "n_warm": len(ts), "n_scored": len(scored), "pass": passes,
            "correct": "O" if scored and passes == len(scored) else ("△" if passes else "X"),
            "e2e_p50": med(e2e), "e2e_p95": pct(e2e, 0.95), "e2e_max": max(e2e) if e2e else None,
            "frame": med([s["query_frame"] for s in st]), "plan": med([s["plan/route_guard"] for s in st]),
            "graph": med([s["graph_exec"] for s in st]), "tbox": med([s["tbox_grounding"] for s in st]),
            "rdb": med([s["rdb_exec"] for s in st]), "vector": med([s["vector_exec"] for s in st]),
            "merge": med([s["merge"] for s in st]), "generate": med([s["generate"] for s in st]),
            "llm_calls": med([t["rate_limit"]["llm_calls"] for t in ts_ok]),
            "signals": ", ".join(f"{k}×{v}" for k, v in sig.most_common(4)) or "-",
            "codes": ", ".join(f"{k}×{v}" for k, v in codes.most_common(3)) or "-",
            "cause": "/".join(f"{k}×{v}" for k, v in causes.most_common()) or "-",
            "cold_e2e": med([t["e2e_ms"] for t in by_q[q] if t["round"] < args.warm_from and t["status"] == "ok"]),
        })

    # ----- 표 2 유형별 -----
    rows2 = []
    for typ in ["산출가능", "부분산출", "외부데이터필요", "정의변경", "ABSTAIN"]:
        qs = [q for q in qids if golden[q]["golden_data_status"] == typ]
        scored = [ev_by[(q, t["round"])] for q in qs for t in by_q[q] if t["round"] >= args.warm_from and ev_by[(q, t["round"])]["overall_pass"] is not None]
        wrong = [e for e in scored if not e["overall_pass"]]
        e2e = [t["e2e_ms"] for q in qs for t in by_q[q] if t["round"] >= args.warm_from and t["status"] == "ok"]
        rows2.append({"type": typ, "n_q": len(qs), "n_runs": len(scored), "pass_runs": len(scored) - len(wrong),
                      "wrong_rate": (len(wrong) / len(scored)) if scored else None, "mean_e2e": statistics.mean(e2e) if e2e else None,
                      "top_cause": Counter(e["cause"] for e in wrong).most_common(1)[0][0] if wrong else "-",
                      "top_code": Counter(c for e in wrong for c in e["failure_codes"]).most_common(1)[0][0] if wrong else "-"})

    # ----- 표 3 계층별 -----
    wrong_warm = [ev_by[(t["question_id"], t["round"])] for t in warm if ev_by[(t["question_id"], t["round"])]["overall_pass"] is False]
    cause_counts = Counter(e["cause"] for e in wrong_warm)
    n_wrong = len(wrong_warm)
    layer_defs = {
        "GraphDB": ("graph_exec", "A"), "RDB": ("rdb_exec", "C"), "VectorDB": ("vector_exec", "B"),
        "query_frame(LLM)": ("query_frame", None), "generate(LLM)": ("generate", "E"), "plan/route_guard": ("plan/route_guard", "D"),
    }
    e2e_p95_warm = pct([t["e2e_ms"] for t in warm_ok], 0.95)
    rows3 = []
    for layer, (stage, cause) in layer_defs.items():
        vals = [stage_ms(t)[stage] for t in warm_ok]
        used = [v for v in vals if v > 0.5]
        share_q = len({t["question_id"] for t in warm_ok if stage_ms(t)[stage] > 0.5}) / max(1, len(qids))
        p95 = pct(used, 0.95)
        rows3.append({"layer": layer, "mean": statistics.mean(used) if used else 0.0, "p95": p95 or 0.0,
                      "share_pct": 100 * (statistics.mean(vals) / statistics.mean([t["e2e_ms"] for t in warm_ok])) if warm_ok else 0.0,
                      "share_q": share_q, "wrong": cause_counts.get(cause, 0) if cause else 0,
                      "time_score": (p95 or 0.0) * share_q, "quality_score": (cause_counts.get(cause, 0) / n_wrong) if (cause and n_wrong) else 0.0})
    db_layers = [r for r in rows3 if r["layer"] in ("GraphDB", "RDB", "VectorDB")]
    for rank, r in enumerate(sorted(db_layers, key=lambda x: -x["time_score"]), 1):
        r["time_rank"] = rank
    for rank, r in enumerate(sorted(db_layers, key=lambda x: -x["quality_score"]), 1):
        r["quality_rank"] = rank

    # ----- 결정 규칙 수치 -----
    par = [parallelizable_ms(t) for t in warm_ok]
    par_ratio = [parallelizable_ms(t) / t["e2e_ms"] for t in warm_ok]
    fb = [fallback_ms(t) for t in warm_ok]
    fb_total = sum(x["total_ms"] for x in fb)
    e2e_total = sum(t["e2e_ms"] for t in warm_ok)
    frame_vals = [stage_ms(t)["query_frame"] for t in warm_ok]
    llm_calls = [t["rate_limit"]["llm_calls"] for t in warm_ok]
    llm_ms = [sum(c["ms"] for c in t["timing"].get("llm", [])) for t in warm_ok]
    llm_node_agg = defaultdict(lambda: {"n": 0, "ms": 0.0})
    for t in warm_ok:
        for k, v in llm_by_node(t).items():
            llm_node_agg[k]["n"] += v["n"]
            llm_node_agg[k]["ms"] += v["ms"]

    sum_check = [(critical_path_ms(t), sum(stage_ms(t)[s] for s in STAGE_NODES), t["e2e_ms"]) for t in warm_ok]
    within10 = sum(1 for cp, _, e in sum_check if abs(cp - e) / e <= 0.10)

    summary = {
        "n_traces": len(traces), "n_429_runs_superseded": n_429_runs,
        "warm": {"runs": len(warm), "ok": len(warm_ok), "e2e_p50": med([t["e2e_ms"] for t in warm_ok]), "e2e_p95": e2e_p95_warm,
                 "e2e_max": max((t["e2e_ms"] for t in warm_ok), default=None),
                 "over_15s_runs": sum(1 for t in warm_ok if t["e2e_ms"] > 15000),
                 "over_15s_questions": len({t["question_id"] for t in warm_ok if t["e2e_ms"] > 15000}),
                 "frame_p50": med(frame_vals), "frame_p95": pct(frame_vals, 0.95), "frame_over_5s_runs": sum(1 for v in frame_vals if v > 5000),
                 "llm_calls_p50": med(llm_calls), "llm_calls_max": max(llm_calls, default=None),
                 "llm_ms_p50": med(llm_ms), "llm_share_of_e2e": (sum(llm_ms) / e2e_total) if e2e_total else None,
                 "status_counts": dict(Counter(t["status"] for t in warm))},
        "cold": {"runs": len(cold), "e2e_p50": med([t["e2e_ms"] for t in cold if t["status"] == "ok"]),
                 "e2e_p95": pct([t["e2e_ms"] for t in cold if t["status"] == "ok"], 0.95),
                 "status_counts": dict(Counter(t["status"] for t in cold))},
        "accuracy": {
            "scored_runs": sum(1 for e in evals if e["round"] >= args.warm_from and e["overall_pass"] is not None),
            "pass_runs": sum(1 for e in evals if e["round"] >= args.warm_from and e["overall_pass"]),
            "questions_all_pass": sum(1 for r in rows1 if r["correct"] == "O"),
            "questions_any_pass": sum(1 for r in rows1 if r["correct"] in ("O", "△")),
            "cause_counts": dict(cause_counts), "n_wrong_runs": n_wrong,
            "code_counts": dict(Counter(c for e in wrong_warm for c in e["failure_codes"])),
        },
        "rules": {
            "a_parallelizable_p95_ms": pct(par, 0.95), "a_parallelizable_ratio_p95": pct(par_ratio, 0.95),
            "a_runs_over_20pct": sum(1 for r in par_ratio if r >= 0.20),
            "b_fallback_total_ms": fb_total, "b_fallback_ratio": (fb_total / e2e_total) if e2e_total else None,
            "b_detail": {"fix_sql_ms": sum(x["fix_sql_ms"] for x in fb), "concept_fallback_ms": sum(x["concept_fallback_ms"] for x in fb),
                         "graph_plan_retry_ms": sum(x["graph_plan_retry_ms"] for x in fb), "sql_retries": sum(x["sql_retries"] for x in fb),
                         "graph_transport_fallback": sum(x["graph_transport_fallback"] for x in fb)},
            "c_cause_D_ratio": (cause_counts.get("D", 0) / n_wrong) if n_wrong else 0.0,
            "onto_cause_A_ratio": (cause_counts.get("A", 0) / n_wrong) if n_wrong else 0.0,
            "vec_cause_B_ratio": (cause_counts.get("B", 0) / n_wrong) if n_wrong else 0.0,
        },
        "llm_by_node": {k: {"n": v["n"], "ms": v["ms"], "ms_per_call": v["ms"] / v["n"] if v["n"] else 0} for k, v in llm_node_agg.items()},
        "sum_check_within10pct": f"{within10}/{len(sum_check)}",
        "layers": rows3, "types": rows2, "questions": rows1,
    }
    (HERE / "analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # ----- markdown -----
    md = []
    md.append("### 표 1. 질의별 결과 (warm 2~4회차, ms는 중앙값)\n")
    md.append("| ID | 질문 | 루브릭 유형 | 라우트 | 정답 | E2E p50 | E2E p95 | frame ms | plan ms | graph ms | rdb ms | vector ms | generate ms | LLM 호출 | 실패신호 | 오답 원인코드 |")
    md.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
    for r in rows1:
        md.append(f"| {r['id']} | {r['question']} | {r['type']} | {r['route']} | {r['correct']}({r['pass']}/{r['n_scored']}) | {fmt(r['e2e_p50'])} | {fmt(r['e2e_p95'])} | "
                  f"{fmt(r['frame'])} | {fmt(r['plan'])} | {fmt(r['graph'])} | {fmt(r['rdb'])} | {fmt(r['vector'])} | {fmt(r['generate'])} | {fmt(r['llm_calls'])} | {r['signals']} | {r['cause']} {r['codes']} |")
    md.append("\n### 표 2. 루브릭 유형별\n")
    md.append("| 유형 | 문항수 | 채점 회차 | 정답 회차 | 오답률 % | 평균 E2E ms | 최다 오답 원인 | 최다 실패코드 |")
    md.append("|---|---:|---:|---:|---:|---:|---|---|")
    for r in rows2:
        md.append(f"| {r['type']} | {r['n_q']} | {r['n_runs']} | {r['pass_runs']} | {fmt(100 * r['wrong_rate'], 1) if r['wrong_rate'] is not None else '미측정'} | {fmt(r['mean_e2e'])} | {r['top_cause']} | {r['top_code']} |")
    md.append("\n### 표 3. 계층별 병목 (warm ok 회차)\n")
    md.append("| 계층 | 평균 기여 ms | p95 기여 ms | E2E 기여율 % | 타는 질의 비율 | 원인 오답 수 | 시간축 점수 | 품질축 점수 | 시간 순위 | 품질 순위 |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows3:
        md.append(f"| {r['layer']} | {fmt(r['mean'])} | {fmt(r['p95'])} | {fmt(r['share_pct'], 1)} | {r['share_q']:.2f} | {r['wrong']} | {fmt(r['time_score'])} | {r['quality_score']:.2f} | {r.get('time_rank', '-')} | {r.get('quality_rank', '-')} |")
    md.append("\n### 질의별 단계 누적 시간 (warm 중앙값, 1칸=1초)\n")
    md.append("| ID | frame | rdb | graph | vector | generate | E2E p50 s | 막대 (F=frame R=rdb G=graph V=vector A=generate) |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for r in rows1:
        bar = "".join(ch * int(round((r[k] or 0) / 1000)) for k, ch in (("frame", "F"), ("rdb", "R"), ("graph", "G"), ("vector", "V"), ("generate", "A")))
        md.append(f"| {r['id']} | {fmt(r['frame'])} | {fmt(r['rdb'])} | {fmt(r['graph'])} | {fmt(r['vector'])} | {fmt(r['generate'])} | {fmt((r['e2e_p50'] or 0) / 1000, 1)} | `{bar}` |")
    md.append("\n### 루브릭 유형별 오답률 (1칸=5%)\n")
    md.append("| 유형 | 오답률 % | 막대 |")
    md.append("|---|---:|---|")
    for r in rows2:
        wr = r['wrong_rate'] or 0
        md.append(f"| {r['type']} | {fmt(100 * wr, 1)} | `{'█' * int(round(100 * wr / 5))}` |")
    (HERE / "analysis_tables.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("layers", "types", "questions")}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
