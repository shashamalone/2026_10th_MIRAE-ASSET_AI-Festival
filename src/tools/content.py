# -*- coding: utf-8 -*-
"""로컬 pgvector 콘텐츠 인덱스(vec.document_chunk) 검색.

검증: EXP-20260828-vector-01 (V01~V08 PASS) — 적재는 src/kb/build_content_index.py.
반환은 검색 노드 공통 계약을 따르고 예외를 위로 던지지 않는다:
  {"evidence": [...], "retrieval_status": "ok|empty|pending|error", "trace": [...]}
  evidence item: {"source": "vector", "text", "score", "document_id", "as_of", ...}
- pending = 인덱스 미구축(테이블 없음/0행) — 답변 근거로 쓰지 않는다
- empty   = 인덱스 정상, score floor 이상 결과 0건 — "확인할 수 없음"이 정답
"""
from __future__ import annotations

import psycopg

import clova
from config import BOND_DSN, CONTENT_SCORE_FLOOR, CONTENT_TOP_K

_SQL = (
    "SELECT document_id, product_id, page_number, citation_text, chunk_text,"
    " published_at, 1 - (embedding <=> %(v)s::vector) AS score"
    " FROM vec.document_chunk"
    " ORDER BY embedding <=> %(v)s::vector LIMIT %(k)s")


def search(text: str, k: int = CONTENT_TOP_K, floor: float = CONTENT_SCORE_FLOOR) -> dict:
    try:
        vector = str([float(x) for x in clova.embed(text)])
        with psycopg.connect(BOND_DSN, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM vec.document_chunk")
            if cur.fetchone()[0] == 0:
                return {"evidence": [], "retrieval_status": "pending",
                        "trace": ["content: 인덱스 0행 — python3 src/kb/build_content_index.py"]}
            cur.execute(_SQL, {"v": vector, "k": k})
            raw = cur.fetchall()
    except psycopg.errors.UndefinedTable:
        return {"evidence": [], "retrieval_status": "pending",
                "trace": ["content: vec.document_chunk 없음 — python3 src/kb/build_content_index.py"]}
    except Exception as exc:  # DB·임베딩 API 실패 — 근거 없이 조용히 진행하지 않도록 사유를 남긴다
        return {"evidence": [], "retrieval_status": "error",
                "trace": [f"content: {type(exc).__name__}: {exc}"[:200]]}
    evidence = [
        {"source": "vector", "text": r[4], "score": round(float(r[6]), 4),
         "document_id": r[0], "as_of": str(r[5]),
         "product_id": r[1], "page": r[2], "citation": r[3]}
        for r in raw if float(r[6]) >= floor]
    status = "ok" if evidence else "empty"
    top = f"top={raw[0][0]}:{round(float(raw[0][6]), 4)}" if raw else "top=none"
    return {"evidence": evidence, "retrieval_status": status,
            "trace": [f"content: {status} k={k} floor={floor} {top}"]}
