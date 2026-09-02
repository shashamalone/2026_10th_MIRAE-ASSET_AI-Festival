# -*- coding: utf-8 -*-
"""측정 결과를 baseline_* 로 동결한다. 코드 개선은 하지 않는다.

    python3 eval130_freeze.py [name] [raw_filename] [table]
    python3 eval130_freeze.py [name] [raw_filename] [table] --verify

동결이 필요한 이유 두 가지:
  1. results/*_raw.json 은 eval130_run.py 를 다시 돌리면 덮어써진다.
  2. 질의셋이 완전히 정적이지 않다. partial 8건의 정답은 _family("등급") 처럼
     코퍼스에서 계산되므로, 코드리스트 91건을 인덱스에 넣으면 어군이 커져
     '정답 집합' 자체가 바뀐다(등급 14→28). 소스 파일만 얼리면 비교가 성립하지 않는다.
     → 전개가 끝난 결과(gold + lenient)를 값으로 고정한다.
     그래서 이 파일은 eval130_queries 를 import 하지 않는다. 언제나
     baseline_130.json 의 resolved_queryset 을 정본으로 재사용한다.
"""
import hashlib
import json
import sys
from pathlib import Path

import psycopg

# config.py 는 형제 폴더에 있다(폴더 재편). 저장소 루트보다 먼저 넣어야
# 루트 config.py 가 아니라 이 테스트용 config.py 가 잡힌다.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent
                       / "1_pgvector_test"))
from config import DSN, RESULTS, ROOT

HERE = Path(__file__).resolve().parent
TERMS = ROOT / "artifacts" / "bond_terms.json"
FROZEN = RESULTS / "2_baseline_130.json"             # resolved_queryset 정본

argv = [a for a in sys.argv[1:] if not a.startswith("--")]
NAME = argv[0] if len(argv) > 0 else "2_baseline_130"
RAWF = argv[1] if len(argv) > 1 else "2_eval130_raw.json"
TABLE = argv[2] if len(argv) > 2 else "terms130"
RAW = RESULTS / RAWF
OUT = RESULTS / f"{NAME}.json"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def canon(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


raw = json.loads(RAW.read_text(encoding="utf-8"))
resolved = json.loads(FROZEN.read_text(encoding="utf-8"))["resolved_queryset"]

# 코퍼스 사실은 하드코딩하지 않고 테이블에서 실측한다.
with psycopg.connect(DSN, autocommit=True) as conn:
    LABEL = dict(conn.execute(f"SELECT term_uri,label FROM {TABLE}").fetchall())
    n_terms = conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    dup_groups, dup_pairs = conn.execute(
        f"SELECT count(*), coalesce(sum(c),0) FROM (SELECT count(*)*(count(*)-1)/2 c"
        f" FROM {TABLE} GROUP BY label HAVING count(*)>1) s").fetchone()
    dup_pairs = int(dup_pairs)          # psycopg 는 sum() 을 Decimal 로 준다
    no_comment = conn.execute(
        f"SELECT count(*) FROM {TABLE} WHERE comment = ''").fetchone()[0]

A = raw["agg"]
ANS = ("exact", "natural", "synonym", "partial", "confuse")
CATS = ANS + ("noise", "absent")
gold_n = sum(1 for r in raw["rows"] if r["category"] in ANS and r["gold"])
n = sum(A[c]["n"] for c in ANS)
strict = sum(A[c].get("strict_top1", 0) for c in ANS)
lenient = sum(A[c]["lenient_top1"] for c in ANS)
r3 = sum(A[c]["lenient_r3"] for c in ANS)
hyb = sum(A[c]["hybrid_top1"] for c in ANS)
kw = sum(A[c]["kw_hit"] for c in ANS)
cov = {f"top{k}": {"hit": sum(A[c].get(f"cov{k}", 0) for c in CATS),
                   "of": sum(A[c].get(f"cov{k}_of", 0) for c in CATS)} for k in (3, 5)}
for v in cov.values():
    v["pct"] = round(v["hit"] / v["of"] * 100, 1) if v["of"] else None
# 동결본의 18 은 '답변 가능 60건' 기준이었다(전체 72 로 세면 28). 정의를 맞춘다.
gap = sum(1 for r in raw["rows"] if r["category"] in ANS and len(r["vector"]) > 1
          and r["vector"][0][1] - r["vector"][1][1] < 0.02)

baseline = {
    "name": NAME,
    "frozen_at": "2026-08-22",
    "note": "동결 질의셋(resolved_queryset, baseline_130 정본)으로 전후 비교한다.",

    "corpus": {
        "indexed_terms": n_terms,
        "table": TABLE,
        "source": "artifacts/bond_terms.json",
        "terms_without_comment": no_comment,
        "duplicate_label_groups": dup_groups,
        "duplicate_label_pairs": dup_pairs,
    },
    "queryset": {"n": len(resolved),
                 "by_category": {c: sum(1 for q in resolved if q["category"] == c)
                                 for c in CATS}},

    "metrics": {
        "indexed_terms": n_terms,
        "vector_k": raw.get("k"),
        "strict_top1": {"hit": strict, "of": gold_n, "pct": round(strict / gold_n * 100, 1)},
        "lenient_top1": {"hit": lenient, "of": n, "pct": round(lenient / n * 100, 1)},
        "recall_at_3": {"hit": r3, "of": n, "pct": round(r3 / n * 100, 1)},
        "noise_false_positive": {"hit": A["noise"]["over_floor"], "of": A["noise"]["n"],
                                 "pct": round(A["noise"]["over_floor"] / A["noise"]["n"] * 100, 1)},
        "noise_over_floor_terms": A["noise"]["over_cnt"],
        "absent_over_floor_terms": A["absent"]["over_cnt"],
        "vector_top1": {"hit": lenient, "of": n},
        "rrf_top1": {"hit": hyb, "of": n},
        # 사용자가 명시 요구: RRF 가 벡터 단독보다 나쁘다는 사실을 기준선에 박아 둔다
        "rrf_minus_vector": hyb - lenient,
        "fts_hit": {"hit": kw, "of": n},
        "fts_on_real_35_questions": {"and_mode": 0, "or_mode": 33, "of": 35},
        "score_floor": raw["floor"],
        "top1_top2_gap_under_0.02": gap,
        # 근거 커버리지 — 상위 n건 중 comment 를 가진 용어 수(질의 72건 합산)
        "comment_coverage": cov,
    },
    "per_category": {c: dict(A[c]) for c in A},
    "resolved_queryset": resolved,
    "per_query_results": raw["rows"],
    "labels": LABEL,
}

# 무결성 — 이후 비교 시 이 값이 다르면 '같은 질의셋'이 아니다
baseline["integrity"] = {
    "queryset_source_sha": sha((HERE / "eval130_queries.py").read_bytes()),
    "resolved_queryset_sha": sha(canon(resolved)),
    "corpus_sha": sha(TERMS.read_bytes()),
    "how_to_verify": f"python3 eval130_freeze.py {NAME} {RAWF} {TABLE} --verify",
}

if "--verify" in sys.argv:
    old = json.loads(OUT.read_text(encoding="utf-8"))
    cur, ref = baseline["integrity"], old["integrity"]
    bad = [k for k in ("queryset_source_sha", "resolved_queryset_sha", "corpus_sha")
           if cur[k] != ref[k]]
    for k in ("queryset_source_sha", "resolved_queryset_sha", "corpus_sha"):
        print(f"  {'FAIL' if k in bad else 'OK  '}  {k}: {ref[k]} → {cur[k]}")
    if bad:
        sys.exit(f"\nFAIL  질의셋/코퍼스가 변했다 — 전후 비교가 성립하지 않는다: {bad}")
    print(f"\n{NAME} 무결성 OK — 동일 질의셋으로 비교 가능")
    sys.exit(0)

OUT.write_text(json.dumps(baseline, ensure_ascii=False, indent=1), encoding="utf-8")
m = baseline["metrics"]
print(f"동결: {OUT.name}  ({OUT.stat().st_size:,} bytes)")
print(f"  indexed_terms        {m['indexed_terms']}  (comment 없음 {no_comment}건 / "
      f"레이블 중복 {dup_groups}그룹 {dup_pairs}쌍)")
print(f"  vector k             {m['vector_k']}")
print(f"  strict Top-1         {m['strict_top1']['pct']}%  ({m['strict_top1']['hit']}/{m['strict_top1']['of']})")
print(f"  lenient Top-1        {m['lenient_top1']['pct']}%  ({m['lenient_top1']['hit']}/{m['lenient_top1']['of']})")
print(f"  Recall@3             {m['recall_at_3']['pct']}%  ({m['recall_at_3']['hit']}/{m['recall_at_3']['of']})")
print(f"  noise false-positive {m['noise_false_positive']['pct']}%  ({m['noise_false_positive']['hit']}/{m['noise_false_positive']['of']})")
print(f"  vector Top-1         {m['vector_top1']['hit']}/{m['vector_top1']['of']}")
print(f"  RRF Top-1            {m['rrf_top1']['hit']}/{m['rrf_top1']['of']}   (벡터 대비 {m['rrf_minus_vector']:+d})")
print(f"  근거 커버리지        Top-3 {cov['top3']['hit']}/{cov['top3']['of']} ({cov['top3']['pct']}%)  "
      f"Top-5 {cov['top5']['hit']}/{cov['top5']['of']} ({cov['top5']['pct']}%)")
print(f"  질의 {baseline['queryset']['n']}건 / resolved_sha {baseline['integrity']['resolved_queryset_sha']}")
