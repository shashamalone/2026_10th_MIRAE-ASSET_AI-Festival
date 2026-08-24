# -*- coding: utf-8 -*-
"""동결된 baseline 두 개를 같은 질의셋 기준으로 비교한다.

    python3 eval_compare.py results/A.json results/B.json

전제: 두 파일의 resolved_queryset_sha 가 같아야 한다. 다르면 비교가 성립하지 않는다.
Top-1 변화는 3분류로 나눈다 — ① 기존→기존  ② 기존→신규(B 에만 있는 용어)  ③ 근거 손실.
②를 '측정 아티팩트'라고 자동 판정하지 않는다. 목록을 그대로 찍어 사람이 나눈다.
"""
import json
import sys
from pathlib import Path

A = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
B = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert A["integrity"]["resolved_queryset_sha"] == B["integrity"]["resolved_queryset_sha"], \
    "질의셋이 다르다 — 비교 불가"

NEW = set(B["labels"]) - set(A["labels"])
LA, LB = A["labels"], B["labels"]
la = lambda u: LA.get(u, LB.get(u, u))
lb = lambda u: LB.get(u, u)
ra = {r["query"]: r for r in A["per_query_results"]}
rb = {r["query"]: r for r in B["per_query_results"]}

print(f"{A['name']} → {B['name']}   용어 {A['metrics']['indexed_terms']} → "
      f"{B['metrics']['indexed_terms']}  (신규 {len(NEW)}건)")
print(f"resolved_queryset_sha {A['integrity']['resolved_queryset_sha']} (동일)")
print(f"corpus_sha {A['integrity']['corpus_sha']} → {B['integrity']['corpus_sha']}\n")

# ── 지표 ─────────────────────────────────────────────────────────────────
def cell(m, k):
    v = m[k]
    return (f"{v['hit']}/{v['of']}" if isinstance(v, dict) and "hit" in v else str(v))

KEYS = ["strict_top1", "lenient_top1", "recall_at_3", "noise_false_positive",
        "noise_over_floor_terms", "absent_over_floor_terms", "rrf_top1", "fts_hit",
        "top1_top2_gap_under_0.02"]
print(f"{'지표':<26}{'전':<14}{'후':<14}델타")
print("-" * 62)
for k in KEYS:
    a, b = A["metrics"].get(k), B["metrics"].get(k)
    if a is None or b is None:
        continue
    d = (b["hit"] - a["hit"]) if isinstance(a, dict) else (b - a)
    print(f"{k:<26}{cell(A['metrics'],k):<14}{cell(B['metrics'],k):<14}{d:+d}")
for k in ("top3", "top5"):
    if "comment_coverage" not in A["metrics"] or "comment_coverage" not in B["metrics"]:
        break                       # 옛 baseline 에는 이 지표가 없다
    a, b = A["metrics"]["comment_coverage"][k], B["metrics"]["comment_coverage"][k]
    print(f"{'comment_coverage_'+k:<26}{a['hit']}/{a['of']} ({a['pct']}%)".ljust(54)[:40]
          + f"{b['hit']}/{b['of']} ({b['pct']}%)".ljust(16) + f"{b['hit']-a['hit']:+d}")

# ── Top-1 변화 ────────────────────────────────────────────────────────────
sub, reg = [], []
for q, r in rb.items():
    ua, sa = ra[q]["vector"][0]
    ub, sb = r["vector"][0]
    if ua == ub:
        continue
    ok_a, ok_b = ua in ra[q]["lenient"], ub in r["lenient"]
    rec = (r["category"], q, la(ua), sa, ok_a, lb(ub), sb, ok_b, ub)
    (sub if ub in NEW else reg).append(rec)

def dump(title, recs):
    print(f"\n{title}  {len(recs)}건")
    for c, q, a_, sa, oka, b_, sb, okb, ub in recs:
        print(f"  [{c}] {q}\n      {a_}({sa}) {'정답' if oka else '오답'}"
              f"  →  {b_}({sb}) {'정답' if okb else '오답'}   {ub}")

dump("① 기존 → 기존 (진짜 회귀/개선)", reg)
dump("② 기존 → 신규 (사람이 valid/invalid 를 판정할 것)", sub)

# ── ③ 근거 손실 ──────────────────────────────────────────────────────────
loss = [(r["category"], q, ra[q].get("cov3"), r.get("cov3"), ra[q].get("cov5"), r.get("cov5"))
        for q, r in rb.items()
        if None not in (r.get("cov5"), ra[q].get("cov5")) and r["cov5"] != ra[q]["cov5"]]
print(f"\n③ 근거 손실 — Top-5 comment 보유수가 변한 질의  {len(loss)}건")
for c, q, a3, b3, a5, b5 in sorted(loss, key=lambda x: x[5] - x[4]):
    print(f"  [{c}] {q:<28} Top-3 {a3}→{b3}   Top-5 {a5}→{b5}")

# ── Recall@3 손실 ────────────────────────────────────────────────────────
lost = [q for q, r in rb.items() if r["category"] not in ("noise", "absent")
        and bool(set(r["lenient"]) & {u for u, _ in ra[q]["vector"][:3]})
        and not bool(set(r["lenient"]) & {u for u, _ in r["vector"][:3]})]
print(f"\nRecall@3 에서 빠진 질의 {len(lost)}건: {lost}")
