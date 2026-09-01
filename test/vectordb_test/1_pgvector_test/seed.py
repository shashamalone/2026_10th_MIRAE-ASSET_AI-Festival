# -*- coding: utf-8 -*-
"""샘플 10건을 임베딩해 documents 에 적재한다.

임베딩은 저장소의 검증된 clova.embed_many() 를 그대로 쓴다(bge-m3 / 1024차원).
분당 쿼터가 있어 embed_many 가 1.2초 간격 + 429 백오프 + 디스크 캐시를 건다.
문서 10건 + 질의 7건 = 17회로, 캐시가 비어 있어도 한 번에 통과하는 양이다.

  python3 seed.py
"""
import sys

import psycopg
from pgvector.psycopg import register_vector

import clovax
from config import DSN, EMBED_DIM, EMBEDDING_MODEL
from samples import DOCS, QUERIES


def main():
    texts = [c for _, _, c in DOCS] + [q for q, _, _ in QUERIES]
    print(f"임베딩 {len(texts)}건 — 모델 {EMBEDDING_MODEL} (원본: {clovax.ORIGIN})")
    vecs = clovax.embed_many(texts)

    dim = len(vecs[0])
    if dim != EMBED_DIM:
        sys.exit(f"FAIL  임베딩 차원 {dim} != {EMBED_DIM}")
    print(f"  차원 {dim} 확인")

    doc_vecs = vecs[: len(DOCS)]
    with psycopg.connect(DSN, autocommit=True) as conn:
        register_vector(conn)
        conn.execute("TRUNCATE documents RESTART IDENTITY")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO documents (doc_key, lang, content, embedding) "
                "VALUES (%s, %s, %s, %s)",
                [(k, lg, c, v) for (k, lg, c), v in zip(DOCS, doc_vecs)],
            )
        n = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    print(f"적재 완료 — {n}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
