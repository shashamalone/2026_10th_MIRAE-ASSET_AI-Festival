"""
15초 로드맵 모델: warm ok 회차마다 조치별 예상 단축(ms)을 계측값에서 빼고 p50/p95를 다시 계산한다(추정치, 근거는 각 조치의 실측 구간).
A1 Graph 엔티티 해소 인덱스화(resolve_frame_seed -> 500ms) / A2 verify_intent 제거 / A3 SQL draft·concept_fallback LLM 제거
A4 SQL fix 재시도 제거 / A5 RDB 도메인 단계 병렬 / A6 generate 4초 상한. 출력: roadmap.json + stdout 표.
"""
import json, math, statistics
from pathlib import Path
HERE = Path(__file__).resolve().parent
def pct(v, q):
    v = sorted(v); return v[max(0, math.ceil(q * len(v)) - 1)] if v else None
tr = [json.loads(l) for l in open(HERE / "traces_full.jsonl", encoding="utf-8")]
ok = [t for t in tr if not t.get("superseded") and t["round"] >= 2 and t["status"] == "ok"]
def node_ms(t, n): return sum(x["ms"] for x in t["timing"]["nodes"] if x["name"] == n)
def rdb_par(t):
    subs = [x for x in t["timing"].get("rdb_sub", []) if x["name"] in ("_execute_target_step", "_execute_entity_lookup_step")]
    tot = 0
    for n in [x for x in t["timing"]["nodes"] if x["name"] == "rdb_search_node"]:
        inside = [x["ms"] for x in subs if n["start_s"] <= x["start_s"] <= n["start_s"] + n["ms"] / 1000]
        if len(inside) >= 2: tot += sum(inside) - max(inside)
    return tot
ACTIONS = ["A1 Graph seed 인덱스", "A2 verify_intent 제거", "A3 draft+concept LLM 제거", "A4 SQL fix 재시도 제거", "A5 RDB 도메인 병렬", "A6 generate 4s 상한"]
rows = []
for t in ok:
    tm = t["timing"]
    seeds = [x["ms"] for x in tm.get("graph_sub", []) if x["name"] == "resolve_frame_seed"]
    a1 = sum(max(0, s - 500) for s in seeds)
    a2 = node_ms(t, "verify_intent_node")
    a3 = sum(x["ms"] for x in tm.get("rdb_llm", []) if x["name"] in ("draft", "concept_fallback"))
    a4 = sum(x["ms"] for x in tm.get("rdb_llm", []) if x["name"] == "fix_sql")
    a5 = rdb_par(t)
    a6 = max(0, node_ms(t, "generate_answer_node") - 4000)
    rows.append({"q": t["question_id"], "r": t["round"], "e2e": t["e2e_ms"], "sav": [a1, a2, a3, a4, a5, a6]})
out = {"current": {"p50": pct([r["e2e"] for r in rows], .5), "p95": pct([r["e2e"] for r in rows], .95)}, "steps": []}
cur = [r["e2e"] for r in rows]
for i, name in enumerate(ACTIONS):
    sav = [r["sav"][i] for r in rows]
    cur = [c - s for c, s in zip(cur, sav)]
    out["steps"].append({"action": name, "saving_p50": pct(sav, .5), "saving_mean": statistics.mean(sav), "saving_p95_run": pct(sav, .95),
                         "p50_after": pct(cur, .5), "p95_after": pct(cur, .95), "max_after": max(cur), "over15": sum(1 for c in cur if c > 15000)})
out["remaining_over15"] = sorted({r["q"] for r, c in zip(rows, cur) if c > 15000})
json.dump(out, open(HERE / "roadmap.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"현재 p50={out['current']['p50']:.0f} p95={out['current']['p95']:.0f}")
for s in out["steps"]:
    print(f"{s['action']}: 단축 p50={s['saving_p50']:.0f} 평균={s['saving_mean']:.0f} p95회차={s['saving_p95_run']:.0f} -> p50 {s['p50_after']:.0f} / p95 {s['p95_after']:.0f} / max {s['max_after']:.0f} / >15s {s['over15']}")
print("잔여 15s 초과 문항:", out["remaining_over15"])
