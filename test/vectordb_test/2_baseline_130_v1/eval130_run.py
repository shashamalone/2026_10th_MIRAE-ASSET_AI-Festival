# -*- coding: utf-8 -*-
"""2차 테스트 — 실제 130개 용어 환경에서 검색 품질 측정.

재는 것:
  Top-1 정확도   엄격(gold 1개) / 관대(레이블 쌍둥이 허용)
  Recall@3       상위 3건 안에 정답이 있는가
  0.45 기준선    (a) 무관 질의에서 넘는 게 있는가 = 오탐
                 (b) 정답이 기준선에 걸려 잘리는가 = 누락  ← 이쪽이 더 위험하다
  하이브리드      벡터 단독 대비 RRF 결합이 실제로 이득인가
"""
import json
import sys
from collections import defaultdict

import psycopg

# 순서가 중요하다. config.py 는 형제 폴더(1_pgvector_test)에 있고, 저장소 루트에도
# 동명 파일이 있다. 테스트용 config 를 먼저 넣어야 clova 가 임베딩 캐시를
# vectordb_test/artifacts 로 쓴다(루트 config 면 저장소 캐시를 건드린다).
_VDB = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_VDB / "1_pgvector_test"))
sys.path.append(str(_VDB.parent / "src"))       # clova.py 는 src/ 아래로 옮겨졌다
import clova  # noqa: E402

from config import DSN, RESULTS, RRF_K  # noqa: E402

FLOOR = 0.45          # config.BOND_SCORE_FLOOR 와 같은 값
CATS = ("exact", "natural", "synonym", "partial", "confuse", "noise", "absent")
K = 30                # 벡터 k. 10이면 absent 3건이 이미 10/10 포화라 악화를 표현할 여지가 없다

# 인자: [table] [raw_out_filename]
# 질의셋은 반드시 동결본에서 '값으로' 읽는다. eval130_queries.queryset() 은 import 시점에
# artifacts/bond_terms.json 으로 _family("등급") 을 재계산하므로 코퍼스가 커지면
# 정답 집합 자체가 바뀐다(등급 14→28). 그러면 전/후 비교가 성립하지 않는다.
TABLE = sys.argv[1] if len(sys.argv) > 1 else "terms130"
RAW_OUT = RESULTS / (sys.argv[2] if len(sys.argv) > 2 else "2_eval130_raw.json")
FROZEN = RESULTS / "2_baseline_130.json"      # 동결 정본
LABEL, COMMENT = {}, {}      # 검색 대상 테이블에서 직접 읽는다 (main 에서 채움)


def frozen_queryset():
    qs = json.loads(FROZEN.read_text(encoding="utf-8"))["resolved_queryset"]
    return [{**q, "lenient": set(q["lenient"])} for q in qs]


def vsearch(conn, qvec, k=K):
    rows = conn.execute(
        f"SELECT term_uri, 1-(embedding <=> %(v)s::vector) FROM {TABLE}"
        " ORDER BY embedding <=> %(v)s::vector LIMIT %(k)s",
        {"v": str(list(map(float, qvec))), "k": k}).fetchall()
    return [(u, round(s, 4)) for u, s in rows]


def ksearch(conn, q, k=10):
    # ORDER BY 에 term_uri 를 붙여 동점을 결정적으로 만든다. 없으면 물리 행 순서가
    # 순위를 정해 테이블만 바꿔도 keyword 순위가 흔들리고 RRF 로 전파된다(96행 중 59행 동점).
    rows = conn.execute(
        f"SELECT term_uri, ts_rank(to_tsvector('simple',content),"
        f"       plainto_tsquery('simple',%(q)s)) r FROM {TABLE}"
        " WHERE to_tsvector('simple',content) @@ plainto_tsquery('simple',%(q)s)"
        " ORDER BY r DESC, term_uri LIMIT %(k)s", {"q": q, "k": k}).fetchall()
    return [(u, round(r, 6)) for u, r in rows]


def rrf(*lists):
    f = defaultdict(float)
    for lst in lists:
        for rank, (u, _) in enumerate(lst, 1):
            f[u] += 1.0 / (RRF_K + rank)
    return sorted(f.items(), key=lambda x: -x[1])


def main():
    qs = frozen_queryset()
    print(f"table={TABLE}  k={K}  질의 {len(qs)}건 (동결 질의셋, 임베딩은 캐시)")
    vecs = clova.embed_many([q["query"] for q in qs], pause=1.2, progress=True)

    conn = psycopg.connect(DSN, autocommit=True)
    for u, l, c in conn.execute(f"SELECT term_uri,label,comment FROM {TABLE}").fetchall():
        LABEL[u], COMMENT[u] = l, c
    rows = []
    for q, v in zip(qs, vecs):
        vres = vsearch(conn, v)
        kres = ksearch(conn, q["query"])
        hres = rrf(vres, kres)
        rows.append({**q, "vector": vres, "keyword": kres, "hybrid": hres})
    conn.close()

    # ── 집계 ──────────────────────────────────────────────────────────────
    agg = {c: defaultdict(int) for c in CATS}
    for r in rows:
        c, a = r["category"], agg[r["category"]]
        a["n"] += 1
        top = [u for u, _ in r["vector"]]
        top1s = r["vector"][0][1] if r["vector"] else 0.0

        # 근거 커버리지 — 상위 n건 중 comment 를 가진 용어 수.
        # agent/nodes.py 는 comment 문장만 근거로 삼는다. comment 없는 용어가 슬롯을
        # 차지하면 Top-1 이 맞아도 답변 근거가 사라진다.
        for n_ in (3, 5):
            r[f"cov{n_}"] = sum(1 for u, _ in r["vector"][:n_] if COMMENT.get(u))
            a[f"cov{n_}"] += r[f"cov{n_}"]
            a[f"cov{n_}_of"] += min(n_, len(r["vector"]))

        if c in ("noise", "absent"):
            # 정답 없음 → 0.45 를 넘긴 건수가 관심사
            over = [(u, s) for u, s in r["vector"] if s >= FLOOR]
            a["over_floor"] += bool(over)
            a["over_cnt"] += len(over)
            r["over"] = over
            continue

        if r["gold"]:
            a["strict_top1"] += top[0] == r["gold"]
            a["strict_r3"] += r["gold"] in top[:3]
        a["lenient_top1"] += top[0] in r["lenient"]
        a["lenient_r3"] += bool(r["lenient"] & set(top[:3]))
        # 하이브리드 비교
        ht = [u for u, _ in r["hybrid"]]
        a["hybrid_top1"] += bool(ht) and ht[0] in r["lenient"]
        a["kw_hit"] += bool(r["keyword"])
        # 기준선에 정답이 잘리는가
        gold_score = next((s for u, s in r["vector"] if u in r["lenient"]), 0.0)
        r["gold_score"] = gold_score
        a["gold_below_floor"] += 0 < gold_score < FLOOR
        a["gold_missing"] += gold_score == 0.0
        if top1s < FLOOR:
            a["top1_below_floor"] += 1

    out = {"table": TABLE, "k": K, "floor": FLOOR, "n": len(rows), "agg": {k: dict(v) for k, v in agg.items()},
           "rows": [{k: v for k, v in r.items() if k != "lenient"} |
                    {"lenient": sorted(r["lenient"])} for r in rows]}
    RAW_OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 출력 ──────────────────────────────────────────────────────────────
    hdr = ("분류", "n", "Top1엄격", "Top1관대", "R@3관대", "하이브리드", "FTS적중", "정답<0.45")
    print("\n" + "".join(h.ljust(11) for h in hdr))
    print("-" * 84)
    for c in ("exact", "natural", "synonym", "partial", "confuse"):
        a = agg[c]; n = a["n"]
        gn = sum(1 for r in rows if r["category"] == c and r["gold"])
        cells = [c, str(n),
                 f"{a['strict_top1']}/{gn}" if gn else "-",
                 f"{a['lenient_top1']}/{n}", f"{a['lenient_r3']}/{n}",
                 f"{a['hybrid_top1']}/{n}", f"{a['kw_hit']}/{n}",
                 str(a["gold_below_floor"])]
        print("".join(x.ljust(11) for x in cells))
    print("-" * 84)
    for c in ("noise", "absent"):
        a = agg[c]
        print(f"{c:<9}{a['n']:>3}  0.45 초과 질의 {a['over_floor']}/{a['n']}건 "
              f"(용어 {a['over_cnt']}개)")

    tot3 = sum(agg[c]["cov3"] for c in CATS); of3 = sum(agg[c]["cov3_of"] for c in CATS)
    tot5 = sum(agg[c]["cov5"] for c in CATS); of5 = sum(agg[c]["cov5_of"] for c in CATS)
    print(f"\n근거 커버리지(comment 보유)  Top-3 {tot3}/{of3} ({tot3/of3*100:.1f}%)  "
          f"Top-5 {tot5}/{of5} ({tot5/of5*100:.1f}%)")

    print(f"\n[0.45 기준선을 넘긴 무관/부재 질의]")
    for r in rows:
        if r["category"] in ("noise", "absent") and r.get("over"):
            print(f"  {r['category']:<7}{r['query'][:22]:<24}"
                  f"{', '.join(f'{LABEL.get(u, u)}({s})' for u, s in r['over'][:3])}")

    print(f"\n[정답이 0.45 미만이라 잘리는 질의 — 누락]")
    miss = [r for r in rows if r["category"] not in ("noise", "absent")
            and 0 < r.get("gold_score", 0) < FLOOR]
    for r in miss:
        print(f"  {r['category']:<9}{r['query'][:24]:<26}정답 {r['gold_score']:.3f}"
              f"  1위 {LABEL.get(r['vector'][0][0], r['vector'][0][0])}({r['vector'][0][1]})")
    print(f"  → {len(miss)}건")

    print(f"\n[Top-1 오답 — 혼동군]")
    for r in rows:
        if r["category"] == "confuse" and r["vector"][0][0] not in r["lenient"]:
            u0 = r["vector"][0][0]
            print(f"  {r['query'][:24]:<26}1위 {LABEL.get(u0, u0)}"
                  f"({r['vector'][0][1]})  기대 {LABEL.get(r['gold'], r['gold'])}"
                  f"({r['gold_score']:.3f})")


if __name__ == "__main__":
    main()
