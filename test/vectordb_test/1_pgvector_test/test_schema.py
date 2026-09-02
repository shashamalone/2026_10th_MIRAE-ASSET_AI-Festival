# -*- coding: utf-8 -*-
"""테이블 구조 · 인덱스 · 적재량 확인."""
import psycopg

from checks import check, finish
from config import DSN, EMBED_DIM

print("test_schema")
conn = psycopg.connect(DSN, autocommit=True)

cols = dict(conn.execute("""
    SELECT column_name, data_type FROM information_schema.columns
     WHERE table_name = 'documents'
""").fetchall())
check("documents 테이블 존재", bool(cols), f"컬럼 {len(cols)}개")
for c in ("id", "doc_key", "lang", "content", "embedding"):
    check(f"컬럼 {c}", c in cols)

dim = conn.execute("""
    SELECT a.atttypmod FROM pg_attribute a
     WHERE a.attrelid = 'documents'::regclass AND a.attname = 'embedding'
""").fetchone()[0]
check(f"embedding 차원 == {EMBED_DIM}", dim == EMBED_DIM, f"실제 {dim}")

idx = {r[0]: r[1] for r in conn.execute("""
    SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'documents'
""").fetchall()}
check("FTS 인덱스 (simple)", "documents_fts_simple_idx" in idx)
check("FTS 인덱스 (english)", "documents_fts_english_idx" in idx)
check("트라이그램 인덱스", "documents_content_trgm_idx" in idx)
hnsw = idx.get("documents_embedding_hnsw_idx", "")
check("벡터 인덱스 (HNSW/cosine)", "hnsw" in hnsw and "vector_cosine_ops" in hnsw, hnsw[-40:])

n, ko, en = conn.execute("""
    SELECT count(*), count(*) FILTER (WHERE lang='ko'), count(*) FILTER (WHERE lang='en')
      FROM documents
""").fetchone()
check("문서 10건 적재", n == 10, f"총 {n}건 (ko {ko} / en {en})")
check("한국어 5건 포함", ko == 5)

lo, hi = conn.execute(
    "SELECT min(vector_norm(embedding)), max(vector_norm(embedding)) FROM documents").fetchone()
check("임베딩 NOT NULL·유효", lo > 0)
print(f"  참고: 저장 벡터 L2 norm {lo:.3f}~{hi:.3f} "
      f"→ 정규화되지 않은 원본. <=> 는 내부 정규화라 무관.")

finish("test_schema")
