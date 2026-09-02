#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data/pdf_demo PDF → 로컬 pgvector vec.document_chunk 적재.

검증: EXP-20260828-vector-01. DDL은 Azure vec.document_chunk 12컬럼을 미러링하고
published_at <= 2026-08-24 CHECK로 룩어헤드를 DB 제약으로 차단한다.
manifest({파일명: {product_id, domain, published_at}})의 product_id는 적재 전에
로컬 RDB 실재를 검증한다 — 조용한 오매핑 방지 게이트.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import clova  # noqa: E402
from config import BOND_DSN, PDF_DEMO_DIR  # noqa: E402

EMBED_DIM = 1024
DATA_CUTOFF = "2026-08-24"

DDL = """
CREATE SCHEMA IF NOT EXISTS vec;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS vec.document_chunk (
  chunk_id        text PRIMARY KEY,
  document_id     text NOT NULL,
  product_id      text,
  page_number     integer,
  citation_text   text NOT NULL,
  chunk_text      text NOT NULL,
  published_at    date NOT NULL CHECK (published_at <= DATE '2026-08-24'),
  source_url      text NOT NULL,
  content_hash    text NOT NULL,
  embedding_model text NOT NULL,
  embedding_dim   smallint NOT NULL,
  embedding       vector(1024) NOT NULL
);
CREATE INDEX IF NOT EXISTS document_chunk_embedding_hnsw
  ON vec.document_chunk USING hnsw (embedding vector_cosine_ops);
"""

PRODUCT_TABLES = {"fund_pub": ("raw.fund_pub_master", "itm_no"),
                  "etf_kr": ("raw.etf_kr_master", "pd_itm_no")}


def _pages(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def _chunks(text: str, limit: int = 2000, piece: int = 1200) -> list[str]:
    # ponytail: 1페이지=1청크, 2000자 초과만 문단 경계 분할. 검색 품질 부족이 실측되면 슬라이딩 윈도우.
    if len(text) <= limit:
        return [text] if text else []
    out, buf = [], ""
    for para in text.split("\n"):
        if len(buf) + len(para) + 1 > piece and buf:
            out.append(buf.strip())
            buf = ""
        buf += para + "\n"
    if buf.strip():
        out.append(buf.strip())
    return out


def _assert_product(cur, meta: dict) -> None:
    """상품코드가 로컬 RDB에 실재하는지 검증 — 조용한 오매핑 방지 (빌드 게이트)."""
    table, col = PRODUCT_TABLES[meta["domain"]]
    cur.execute(f"SELECT count(*) FROM {table} WHERE {col} = %s", (meta["product_id"],))
    if cur.fetchone()[0] == 0:
        raise ValueError(f"RDB에 없는 상품코드: {meta['product_id']} ({table}.{col})")


def ingest(pdf_dir: Path, manifest: dict) -> dict:
    """TRUNCATE 후 재적재(멱등). 임베딩은 artifacts/embed_cache.json 캐시로 재실행이 저렴하다."""
    rows = []
    with psycopg.connect(BOND_DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        for fname, meta in manifest.items():
            path = Path(pdf_dir) / fname
            if not path.is_file():
                raise ValueError(f"PDF 없음: {path}")
            if str(meta["published_at"]) > DATA_CUTOFF:
                raise ValueError(f"look-ahead: {fname} published_at={meta['published_at']}")
            _assert_product(cur, meta)
            doc_id = path.stem
            for pno, page_text in enumerate(_pages(path), start=1):
                for i, chunk in enumerate(_chunks(page_text)):
                    rows.append({
                        "chunk_id": f"{doc_id}:p{pno}:{i}",
                        "document_id": doc_id,
                        "product_id": meta["product_id"],
                        "page_number": pno,
                        "citation_text": f"{doc_id} p.{pno}",
                        "chunk_text": chunk,
                        "published_at": meta["published_at"],
                        "source_url": path.resolve().as_uri(),
                        "content_hash": hashlib.sha256(chunk.encode()).hexdigest(),
                    })
        if not rows:
            raise ValueError("추출된 텍스트 청크가 없다 — PDF 텍스트 추출 실패 여부를 확인할 것")
        vectors = clova.embed_many([r["chunk_text"] for r in rows])
        cur.execute("TRUNCATE vec.document_chunk")
        cur.executemany(
            "INSERT INTO vec.document_chunk (chunk_id, document_id, product_id, page_number,"
            " citation_text, chunk_text, published_at, source_url, content_hash,"
            " embedding_model, embedding_dim, embedding)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'bge-m3',1024,%s::vector)",
            [(r["chunk_id"], r["document_id"], r["product_id"], r["page_number"],
              r["citation_text"], r["chunk_text"], r["published_at"], r["source_url"],
              r["content_hash"], str([float(x) for x in v]))
             for r, v in zip(rows, vectors)])
        cur.execute("SELECT count(*), count(DISTINCT document_id),"
                    " max(vector_dims(embedding)) FROM vec.document_chunk")
        n, docs, dim = cur.fetchone()
    if n != len(rows) or dim != EMBED_DIM:
        raise ValueError(f"적재 검증 실패: count={n}/{len(rows)} dim={dim}")
    return {"chunks": n, "documents": docs, "dim": dim}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", default=str(PDF_DEMO_DIR))
    parser.add_argument("--manifest", default=None, help="기본: <pdf-dir>/manifest.json")
    args = parser.parse_args()
    pdf_dir = Path(args.pdf_dir)
    manifest_path = Path(args.manifest) if args.manifest else pdf_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print("PASS " + json.dumps(ingest(pdf_dir, manifest), ensure_ascii=False))


if __name__ == "__main__":
    main()
