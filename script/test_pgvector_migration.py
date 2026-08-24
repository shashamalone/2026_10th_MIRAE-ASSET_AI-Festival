# -*- coding: utf-8 -*-
"""FAISS ↔ pgvector 런타임 이전 회귀 테스트.

    python3 script/test_pgvector_migration.py faiss      # 이전 전에 실행
    python3 script/test_pgvector_migration.py pgvector   # 이전 후에 실행
    python3 script/test_pgvector_migration.py compare    # 둘을 비교

엔진 이름은 인자로 받는다. 스크립트는 tools.bond_schema.bond_schema_search 만 부르므로,
같은 코드가 그 시점의 엔진을 그대로 잰다 — 시그니처가 유지됐는지도 함께 검증하는 셈이다.

질의는 동결된 72건을 값으로 읽는다(baseline 계열과 같은 정본). 새로 만들지 않는다.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent  # 저장소 루트 — FROZEN 경로가 쓴다
# 런타임 모듈(config/tools)은 루트가 아니라 src/ 아래에 있다.
sys.path.insert(0, str(ROOT / "src"))

from config import ARTIFACTS, BOND_TOP_K  # noqa: E402

FROZEN = ROOT / "vectordb_test" / "results" / "2_baseline_130.json"


def queries():
    d = json.loads(FROZEN.read_text(encoding="utf-8"))
    qs = d["resolved_queryset"]
    assert len(qs) == 72, f"동결 질의셋이 72건이 아니다: {len(qs)}"
    return qs, d["integrity"]["resolved_queryset_sha"]


def capture(engine: str):
    from tools.bond_schema import bond_schema_search

    qs, sha = queries()
    out = []
    for i, q in enumerate(qs, 1):
        hits = bond_schema_search(q["query"], k=BOND_TOP_K)
        out.append({"query": q["query"], "category": q["category"], "gold": q["gold"],
                    "lenient": q["lenient"],
                    "hits": [{"term_uri": h["term_uri"], "score": h["score"]} for h in hits]})
        if i % 20 == 0:
            print(f"  {i}/{len(qs)}", flush=True)
    p = ARTIFACTS / f"regression_{engine}.json"
    p.write_text(json.dumps({"engine": engine, "k": BOND_TOP_K, "queryset_sha": sha,
                             "rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    empty = sum(1 for r in out if not r["hits"])
    print(f"{engine}: 질의 {len(out)}건 / 결과 0건인 질의 {empty}건 → {p.name}")
    return out


def metrics(rows):
    """동결 정답으로 Top-1·Recall@3 을 센다. 답변 가능 5분류만 대상."""
    ANS = ("exact", "natural", "synonym", "partial", "confuse")
    t1 = r3 = n = strict = gold_n = 0
    for r in rows:
        if r["category"] not in ANS:
            continue
        n += 1
        uris = [h["term_uri"] for h in r["hits"]]
        len_set = set(r["lenient"])
        t1 += bool(uris) and uris[0] in len_set
        r3 += bool(len_set & set(uris[:3]))
        if r["gold"]:
            gold_n += 1
            strict += bool(uris) and uris[0] == r["gold"]
    return {"strict_top1": f"{strict}/{gold_n}", "lenient_top1": f"{t1}/{n}",
            "recall_at_3": f"{r3}/{n}"}


def compare():
    a = json.loads((ARTIFACTS / "regression_faiss.json").read_text(encoding="utf-8"))
    b = json.loads((ARTIFACTS / "regression_pgvector.json").read_text(encoding="utf-8"))
    assert a["queryset_sha"] == b["queryset_sha"], "질의셋이 다르다 — 비교 무효"
    assert a["k"] == b["k"], f"k 가 다르다: {a['k']} vs {b['k']}"

    ma, mb = metrics(a["rows"]), metrics(b["rows"])
    print(f"질의셋 sha {a['queryset_sha']} (동일) · k={a['k']}\n")
    print(f"  {'지표':<16}{'faiss':>12}{'pgvector':>12}")
    for key in ("strict_top1", "lenient_top1", "recall_at_3"):
        print(f"  {key:<16}{ma[key]:>12}{mb[key]:>12}")

    same_order = diff_order = 0
    worst = 0.0
    score_rows = []
    for ra, rb in zip(a["rows"], b["rows"]):
        ua = [h["term_uri"] for h in ra["hits"]]
        ub = [h["term_uri"] for h in rb["hits"]]
        if ua == ub:
            same_order += 1
        else:
            diff_order += 1
            print(f"\n  순서 불일치 [{ra['category']}] {ra['query'][:24]}")
            print(f"    faiss   : {ua}")
            print(f"    pgvector: {ub}")
        for ha, hb in zip(ra["hits"], rb["hits"]):
            if ha["term_uri"] == hb["term_uri"]:
                d = abs(ha["score"] - hb["score"])
                worst = max(worst, d)
                score_rows.append(d)

    print(f"\n  Top-{a['k']} 순서 동일: {same_order}/{len(a['rows'])}  불일치 {diff_order}")
    print(f"  같은 용어의 score 최대 오차: {worst:.2e}  (비교 {len(score_rows)}쌍)")
    ok = diff_order == 0 and worst < 1e-4 and ma == mb
    print(f"\n{'PASS — FAISS 와 pgvector 결과 동등' if ok else 'FAIL — 차이 있음'}")
    return 0 if ok else 1


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if mode == "compare":
        sys.exit(compare())
    if mode not in ("faiss", "pgvector"):
        sys.exit(f"엔진 이름은 faiss / pgvector / compare 중 하나: {mode}")
    rows = capture(mode)
    print("  " + json.dumps(metrics(rows), ensure_ascii=False))
