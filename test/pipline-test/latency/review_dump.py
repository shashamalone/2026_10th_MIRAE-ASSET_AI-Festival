"""
수동 검토용 덤프: 문항별(기본 2회차) 최종 answer·think_trace·plan·단계 상태·Claim 진단을 한 화면에 펼친다.
입력: traces_full.jsonl, per_run_eval.jsonl. 출력: stdout (review_round{N}.md로 리다이렉트해 읽는다).
결정론 채점이 놓친 판정(수치 표기 차이, 과잉 추론)을 사람이 대조하는 용도이며 채점 규칙은 바꾸지 않는다.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--round", type=int, default=2)
ap.add_argument("--ids", default="")
args = ap.parse_args()
ids = {x for x in args.ids.split(",") if x}

evals = {}
for line in open(HERE / "per_run_eval.jsonl", encoding="utf-8"):
    e = json.loads(line)
    evals[(e["question_id"], e["round"])] = e

for line in open(HERE / "traces_full.jsonl", encoding="utf-8"):
    t = json.loads(line)
    if t.get("superseded") or t["round"] != args.round or (ids and t["question_id"] not in ids):
        continue
    e = evals.get((t["question_id"], t["round"]), {})
    print(f"\n## {t['question_id']} r{t['round']} status={t['status']} e2e={t['e2e_ms']/1000:.1f}s pass={e.get('overall_pass')} cause={e.get('cause')} codes={e.get('failure_codes')}")
    print(f"Q: {t['question']}")
    print(f"plan: {[ (s['step_id'], s.get('domain')) for s in t.get('plan') or []]} block={t.get('route',{}).get('blocking_reasons')}")
    for sid, r in (t.get("step_results") or {}).items():
        if not isinstance(r, dict):
            continue
        n = r.get("rows_total") or r.get("count") or r.get("chunks_total") or 0
        print(f"  step {sid}: engine={r.get('engine')} status={r.get('status')} rows={n} err={str(r.get('error') or '')[:100]} skip={str(r.get('skipped_reason') or '')[:120]} note={str(r.get('note') or '')[:100]}")
        if r.get("sql"):
            print(f"    SQL: {r['sql'][:300]}")
    a = t.get("answer") or {}
    print(f"think_trace: {str(a.get('think_trace',''))[:300]}")
    print(f"ANSWER: {str(a.get('answer',''))[:1200]}")
    for c in e.get("claim_results", []):
        flag = "" if c["severity"] == "INFO" else f" <-- {c['severity']}"
        print(f"  [{c['claim_id']}] {c['claim']} ({c['availability']}/{c['source']}) -> {c['diagnosis']}{flag} {c.get('note','')}")
