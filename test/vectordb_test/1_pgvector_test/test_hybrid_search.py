# -*- coding: utf-8 -*-
"""하이브리드 = 벡터 랭킹 + FTS 랭킹의 RRF 결합. reranker 없음."""
import search
from checks import check, finish
from config import RRF_K
from samples import QUERIES, query_vectors

print(f"test_hybrid_search  (RRF, k={RRF_K})")
conn = search.connect()
qv = query_vectors()

for q, expected, note in QUERIES:
    hits = search.hybrid_search(conn, q, qv[q])
    top = hits[0]
    check(f"'{q}' 하이브리드 1위 == {expected}", top["doc_key"] == expected,
          "; ".join(f"{h['doc_key']}({h['score']},{h['ranks']})" for h in hits[:3]))

print("\n  [RRF 산식 검증]")
hits = search.hybrid_search(conn, "듀레이션", qv["듀레이션"])
top = hits[0]
check("양쪽 리스트 모두 1위인 문서의 점수 == 2/(k+1)",
      abs(top["score"] - round(2.0 / (RRF_K + 1), 6)) < 1e-6,
      f"{top['score']} vs {round(2.0/(RRF_K+1),6)} / ranks={top['ranks']}")
check("양쪽 기여 표시", top["ranks"] == {"vector": 1, "keyword": 1}, str(top["ranks"]))
check("점수 내림차순", all(a["score"] >= b["score"] for a, b in zip(hits, hits[1:])))

print("\n  [FTS 가 0건일 때 벡터가 살려내는지]")
q = "듀레이션이 뭐야?"
kw = search.keyword_search(conn, q, cfg="simple")
hits = search.hybrid_search(conn, q, qv[q])
check("해당 질의의 FTS 결과는 0건", kw == [], str(kw))
check("그래도 하이브리드 1위는 정답", hits[0]["doc_key"] == "fp:duration", hits[0]["doc_key"])
check("벡터 랭킹만 기여", hits[0]["ranks"] == {"vector": 1}, str(hits[0]["ranks"]))

print("\n  [합집합인지 — 한쪽에만 있는 문서도 포함]")
q = "위험등급"
v = {h["doc_key"] for h in search.vector_search(conn, qv[q], k=10)}
k = {h["doc_key"] for h in search.keyword_search(conn, q, k=10)}
h = {x["doc_key"] for x in search.hybrid_search(conn, q, qv[q])}
check("하이브리드 ⊆ (벡터 ∪ 키워드)", h <= (v | k), f"vec={len(v)} kw={len(k)} hyb={len(h)}")
check("키워드 적중 문서가 융합 결과에 남아 있음", k <= h, f"kw={k} hyb={h}")

finish("test_hybrid_search")
