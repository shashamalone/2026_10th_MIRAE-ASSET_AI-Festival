# -*- coding: utf-8 -*-
"""벡터 검색 — 영문·한국어 모두 기대 문서를 1위로 올리는지."""
import search
from checks import check, finish
from samples import QUERIES, query_vectors

print("test_vector_search  (cosine <=>, bge-m3 1024d)")
conn = search.connect()
qv = query_vectors()

for q, expected, note in QUERIES:
    hits = search.vector_search(conn, qv[q], k=3)
    top = hits[0]["doc_key"]
    check(f"'{q}' 1위 == {expected}", top == expected,
          f"{note} | " + ", ".join(f"{h['doc_key']}:{h['score']}" for h in hits))

# 랭킹이 실제로 거리순인지 (인덱스/연산자가 뒤집혀 있지 않은지)
hits = search.vector_search(conn, qv["듀레이션"], k=10)
check("점수 내림차순 정렬", all(a["score"] >= b["score"] for a, b in zip(hits, hits[1:])))
check("cosine 유사도 범위 [-1,1]", all(-1.0 <= h["score"] <= 1.0 for h in hits))
check("전체 10건 반환 가능", len(hits) == 10, f"{len(hits)}건")

# HNSW 인덱스가 계획에 잡히는지 — 10건이라 seq scan 이 정상이다. 사실만 기록한다.
plan = "\n".join(r[0] for r in conn.execute(
    "EXPLAIN SELECT doc_key FROM documents ORDER BY embedding <=> %s::vector LIMIT 5",
    (str(list(map(float, qv["듀레이션"]))),)).fetchall())
print(f"  참고: 10건 규모라 플래너 선택 = "
      f"{'HNSW 인덱스' if 'hnsw' in plan.lower() or 'Index Scan' in plan else 'Seq Scan (정상)'}")

# --- FAISS 동등성 --------------------------------------------------------
# 현행 kb/build_bond_index.py 는 faiss.normalize_L2 + IndexFlatIP 로 cosine 을 구한다.
# pgvector 의 1 - (a <=> b) 와 수치가 같아야 config.BOND_SCORE_FLOOR(0.45) 를
# 그대로 들고 갈 수 있다. 다르면 이전 시 임계값을 다시 잡아야 한다.
print("\n  [FAISS 동등성 — 이전 시 임계값을 그대로 쓸 수 있는가]")
import numpy as np

rows = conn.execute("SELECT doc_key, embedding FROM documents ORDER BY id").fetchall()
M = np.asarray([r[1].to_numpy() for r in rows], dtype=np.float32)  # register_vector -> Vector 객체
M /= np.linalg.norm(M, axis=1, keepdims=True)          # faiss.normalize_L2 와 동일
q = np.asarray(qv["듀레이션"], dtype=np.float32)
q /= np.linalg.norm(q)
faiss_style = {r[0]: float(v) for r, v in zip(rows, M @ q)}   # IndexFlatIP 내적 = cosine

pg = {h["doc_key"]: h["score"] for h in search.vector_search(conn, qv["듀레이션"], k=10)}
worst = max(abs(faiss_style[k] - pg[k]) for k in pg)
check("pgvector(1-거리) == FAISS(정규화+IP) cosine", worst < 1e-5, f"최대 오차 {worst:.2e}")
check("Top-5 순서 동일",
      [k for k, _ in sorted(faiss_style.items(), key=lambda x: -x[1])][:5]
      == list(pg.keys())[:5])

finish("test_vector_search")
