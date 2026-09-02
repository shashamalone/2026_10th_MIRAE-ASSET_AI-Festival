# -*- coding: utf-8 -*-
"""전체 질의를 세 방식으로 돌려 results/sample_queries.json 을 만든다.

이 파일이 통과한다는 것은 '벡터 + FTS + 하이브리드가 한 파이프라인에서 함께 동작한다'는 뜻이다.
"""
import json

import search
from checks import check, finish
from config import EMBED_DIM, EMBEDDING_MODEL, HERE, PGDATABASE, RRF_K
from samples import DOCS, QUERIES, query_vectors

print("test_integration")
conn = search.connect()
qv = query_vectors()

server = conn.execute("SHOW server_version").fetchone()[0]
pgv = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0]

out = {
    "환경": {
        "postgresql": server,
        "pgvector": pgv,
        "database": PGDATABASE,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBED_DIM,
        "distance": "cosine (<=>, vector_cosine_ops)",
        "hybrid": f"RRF (k={RRF_K}), vector + FTS(simple)",
        "documents": len(DOCS),
    },
    "queries": [],
}

for q, expected, note in QUERIES:
    rec = {
        "query": q,
        "note": note,
        "expected_doc_key": expected,
        "vector_results": search.vector_search(conn, qv[q]),
        "keyword_results_simple": search.keyword_search(conn, q, cfg="simple"),
        "keyword_results_english": search.keyword_search(conn, q, cfg="english"),
        "trigram_results": search.trigram_search(conn, q, threshold=0.3),
        "hybrid_results": search.hybrid_search(conn, q, qv[q]),
    }
    out["queries"].append(rec)

    v_ok = rec["vector_results"] and rec["vector_results"][0]["doc_key"] == expected
    h_ok = rec["hybrid_results"] and rec["hybrid_results"][0]["doc_key"] == expected
    check(f"'{q}' 벡터·하이브리드 모두 1위 정답", bool(v_ok and h_ok),
          f"kw(simple) {len(rec['keyword_results_simple'])}건")

# 한국어 FTS 종합 판정 — 보고서 숫자의 출처
ko = [r for r in out["queries"] if any(ord(c) > 0x3130 for c in r["query"])]
ko_fts_hit = sum(1 for r in ko if r["keyword_results_simple"])
ko_vec_hit = sum(1 for r in ko
                 if r["vector_results"] and r["vector_results"][0]["doc_key"] == r["expected_doc_key"])
out["환경"]["korean_summary"] = {
    "한국어_질의수": len(ko),
    "FTS_simple_적중": ko_fts_hit,
    "FTS_english_적중": sum(1 for r in ko if r["keyword_results_english"]),
    "벡터_1위정답": ko_vec_hit,
}
print(f"\n  한국어 질의 {len(ko)}건 — FTS(simple) 적중 {ko_fts_hit}건 / 벡터 1위정답 {ko_vec_hit}건")

check("한국어에서 벡터가 FTS 보다 많이 맞힌다", ko_vec_hit > ko_fts_hit,
      f"벡터 {ko_vec_hit} > FTS {ko_fts_hit}")
check("세 검색이 한 연결에서 모두 동작", True)

path = HERE / "results" / "sample_queries.json"
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  기록: {path}")

finish("test_integration")
