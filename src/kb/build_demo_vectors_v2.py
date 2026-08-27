# -*- coding: utf-8 -*-
"""Build an isolated two-document bge-m3 demo index.

The canonical ``vec`` schema has an all-or-none release contract.  This builder
therefore owns only ``vec_demo`` and never changes ``meta.load_run`` or any
canonical vector table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg import sql

from kb.v2_manifest import EXTERNAL_CUTOFF, RELEASE_ID

MODEL = "bge-m3"
DIMENSION = 1024
SCHEMA = "vec_demo"
SOURCE_TYPES = {"official_policy", "official_risk"}
DEFAULT_TRUSTED_HOST_SUFFIXES = (
    ".go.kr",
    "fsc.go.kr",
    "dart.fss.or.kr",
    "dis.kofia.or.kr",
    "kofia.or.kr",
    "tigeretf.com",
    "miraeasset.com",
    "investments.miraeasset.com",
    "samsungfund.com",
    "kodex.com",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def trusted_hosts() -> tuple[str, ...]:
    extra = tuple(
        host.strip().lower()
        for host in os.environ.get("DEMO_TRUSTED_SOURCE_HOSTS", "").split(",")
        if host.strip()
    )
    return DEFAULT_TRUSTED_HOST_SUFFIXES + extra


def _trusted_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(
        host == suffix.lstrip(".") or host.endswith("." + suffix.lstrip("."))
        for suffix in trusted_hosts()
    )


def _source_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()


def validate_manifest(path: Path) -> list[dict[str, Any]]:
    manifest_path = path.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("demo manifest schema_version은 1이어야 합니다")
    if payload.get("release_id") != RELEASE_ID:
        raise ValueError("demo manifest release_id가 canonical release와 다릅니다")
    documents = payload.get("documents")
    if not isinstance(documents, list) or len(documents) != 2:
        raise ValueError("demo manifest는 정확히 외부문서 2건이어야 합니다")
    if {item.get("source_type") for item in documents if isinstance(item, dict)} != SOURCE_TYPES:
        raise ValueError("source_type은 official_policy와 official_risk 각 1건이어야 합니다")

    validated: list[dict[str, Any]] = []
    source_hashes: set[str] = set()
    content_hashes: set[str] = set()
    for index, item in enumerate(documents, 1):
        if not isinstance(item, dict):
            raise TypeError(f"documents[{index}]는 객체여야 합니다")
        required = {
            "source_type",
            "title",
            "publisher",
            "published_at",
            "source_url",
            "source_file",
            "source_sha256",
            "extracted_text_file",
            "extracted_text_sha256",
            "locator",
            "citation_text",
            "chunk_text",
            "chunk_sha256",
        }
        missing = sorted(name for name in required if item.get(name) in {None, ""})
        if missing:
            raise ValueError(f"documents[{index}] 필수 필드 누락: {missing}")
        try:
            published_at = date.fromisoformat(str(item["published_at"]))
        except ValueError as exc:
            raise ValueError(f"documents[{index}].published_at 형식 오류") from exc
        if published_at > EXTERNAL_CUTOFF:
            raise ValueError(f"documents[{index}] cutoff 초과: {published_at}")
        if not _trusted_url(str(item["source_url"])):
            raise ValueError(f"documents[{index}] 공식 HTTPS source host를 허용하지 않습니다")
        source_path = _source_path(manifest_path, str(item["source_file"]))
        if not source_path.is_file():
            raise FileNotFoundError(f"documents[{index}] 원문 파일 없음: {source_path}")
        source_hash = sha256_bytes(source_path.read_bytes())
        if source_hash != str(item["source_sha256"]).lower():
            raise ValueError(f"documents[{index}] source SHA-256 불일치")
        extracted_text_path = _source_path(manifest_path, str(item["extracted_text_file"]))
        if not extracted_text_path.is_file():
            raise FileNotFoundError(f"documents[{index}] 추출 텍스트 파일 없음: {extracted_text_path}")
        extracted_payload = extracted_text_path.read_bytes()
        extracted_hash = sha256_bytes(extracted_payload)
        if extracted_hash != str(item["extracted_text_sha256"]).lower():
            raise ValueError(f"documents[{index}] extracted text SHA-256 불일치")
        try:
            extracted_text = extracted_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"documents[{index}] 추출 텍스트는 UTF-8이어야 합니다") from exc
        chunk_text = str(item["chunk_text"]).strip()
        citation_text = str(item["citation_text"]).strip()
        locator = str(item["locator"]).strip()
        if not chunk_text or not citation_text or not locator:
            raise ValueError(f"documents[{index}] 빈 chunk/citation/locator")
        if citation_text not in chunk_text:
            raise ValueError(f"documents[{index}] citation_text가 chunk_text 원문에 없습니다")
        normalize = lambda text: " ".join(text.split())
        if normalize(citation_text) not in normalize(extracted_text):
            raise ValueError(f"documents[{index}] citation_text가 추출된 원문에 없습니다")
        content_hash = sha256_bytes(chunk_text.encode("utf-8"))
        if content_hash != str(item["chunk_sha256"]).lower():
            raise ValueError(f"documents[{index}] chunk SHA-256 불일치")
        if source_hash in source_hashes or content_hash in content_hashes:
            raise ValueError("두 demo 문서의 source/chunk hash는 서로 달라야 합니다")
        source_hashes.add(source_hash)
        content_hashes.add(content_hash)
        product_id = item.get("product_id")
        if item["source_type"] == "official_policy" and product_id:
            raise ValueError("official_policy demo 문서는 product_id를 갖지 않습니다")
        if item["source_type"] == "official_risk" and not product_id:
            raise ValueError("official_risk demo 문서는 canonical product_id가 필요합니다")
        if product_id is not None and not re.fullmatch(r"[A-Za-z0-9:_\-.]{1,300}", str(product_id)):
            raise ValueError(f"documents[{index}].product_id 형식 오류")
        page_number = item.get("page_number")
        if page_number is not None and (not isinstance(page_number, int) or page_number < 1):
            raise ValueError(f"documents[{index}].page_number는 양의 정수여야 합니다")
        validated.append(
            {
                "document_id": f"doc:demo:{source_hash[:24]}",
                "chunk_id": f"chunk:demo:{content_hash[:24]}",
                "source_type": str(item["source_type"]),
                "title": str(item["title"]).strip(),
                "publisher": str(item["publisher"]).strip(),
                "published_at": published_at,
                "source_url": str(item["source_url"]),
                "source_file": str(source_path),
                "source_hash": source_hash,
                "extracted_text_file": str(extracted_text_path),
                "extracted_text_hash": extracted_hash,
                "product_id": str(product_id) if product_id else None,
                "page_number": page_number,
                "locator": locator,
                "citation_text": citation_text,
                "chunk_text": chunk_text,
                "content_hash": content_hash,
            }
        )
    return validated


DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE TABLE IF NOT EXISTS {SCHEMA}.source_document (
  document_id text PRIMARY KEY,
  title text NOT NULL,
  publisher text NOT NULL,
  published_at date NOT NULL CHECK (published_at <= DATE '{EXTERNAL_CUTOFF.isoformat()}'),
  source_url text NOT NULL,
  source_hash text NOT NULL UNIQUE,
  extracted_text_hash text NOT NULL,
  source_type text NOT NULL CHECK (source_type IN ('official_policy','official_risk')),
  ingested_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.document_chunk (
  chunk_id text PRIMARY KEY,
  document_id text NOT NULL REFERENCES {SCHEMA}.source_document(document_id),
  product_id text REFERENCES enriched.product_master(product_id),
  page_number integer,
  locator text NOT NULL,
  citation_text text NOT NULL,
  chunk_text text NOT NULL,
  published_at date NOT NULL CHECK (published_at <= DATE '{EXTERNAL_CUTOFF.isoformat()}'),
  source_url text NOT NULL,
  content_hash text NOT NULL UNIQUE,
  embedding_model text NOT NULL CHECK (embedding_model='bge-m3'),
  embedding_dim smallint NOT NULL CHECK (embedding_dim=1024),
  embedding vector(1024) NOT NULL
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.index_metadata (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  release_id text NOT NULL,
  index_status text NOT NULL CHECK (index_status='demo'),
  production_ready boolean NOT NULL CHECK (NOT production_ready),
  seed_count smallint NOT NULL CHECK (seed_count=2),
  embedding_model text NOT NULL CHECK (embedding_model='bge-m3'),
  embedding_dim smallint NOT NULL CHECK (embedding_dim=1024),
  built_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
"""


def admin_dsn() -> str:
    # compose의 builder 서비스는 host ADMIN_DATABASE_URL을 container DATABASE_URL로 전달한다.
    value = (os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not value:
        raise RuntimeError("ADMIN_DATABASE_URL(또는 builder container의 DATABASE_URL)이 필요합니다")
    return value


def vector_literal(vector: list[float]) -> str:
    converted = [float(value) for value in vector]
    if len(converted) != DIMENSION:
        raise ValueError(f"bge-m3 embedding 차원 {len(converted)} != {DIMENSION}")
    if not all(math.isfinite(value) for value in converted):
        raise ValueError("embedding에는 유한한 숫자만 허용합니다")
    if not any(value != 0.0 for value in converted):
        raise ValueError("embedding은 영벡터일 수 없습니다")
    return "[" + ",".join(format(value, ".10g") for value in converted) + "]"


def apply(manifest_path: Path, reader_role: str = "agent_reader") -> dict[str, Any]:
    import clova

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", reader_role):
        raise ValueError("reader role identifier 형식 오류")
    documents = validate_manifest(manifest_path)
    vectors = clova.embed_many([item["chunk_text"] for item in documents], pause=1.2, progress=True)
    literals = [vector_literal(vector) for vector in vectors]
    with psycopg.connect(admin_dsn()) as conn:
        if not conn.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')").fetchone()[0]:
            raise RuntimeError("pgvector extension이 없습니다")
        conn.execute(DDL)
        product_ids = [item["product_id"] for item in documents if item["product_id"]]
        if product_ids:
            found = {
                row[0]
                for row in conn.execute(
                    "SELECT product_id FROM enriched.product_master WHERE product_id=ANY(%s)",
                    (product_ids,),
                ).fetchall()
            }
            if found != set(product_ids):
                raise ValueError(f"demo product FK 미해결: {sorted(set(product_ids)-found)}")
        conn.execute(f"TRUNCATE {SCHEMA}.document_chunk,{SCHEMA}.source_document,{SCHEMA}.index_metadata")
        for item, embedding in zip(documents, literals):
            conn.execute(
                f"""
                INSERT INTO {SCHEMA}.source_document
                  (document_id,title,publisher,published_at,source_url,source_hash,extracted_text_hash,source_type)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    item["document_id"],item["title"],item["publisher"],item["published_at"],
                    item["source_url"],item["source_hash"],item["extracted_text_hash"],item["source_type"],
                ),
            )
            conn.execute(
                f"""
                INSERT INTO {SCHEMA}.document_chunk
                  (chunk_id,document_id,product_id,page_number,locator,citation_text,chunk_text,
                   published_at,source_url,content_hash,embedding_model,embedding_dim,embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                """,
                (
                    item["chunk_id"],item["document_id"],item["product_id"],item["page_number"],
                    item["locator"],item["citation_text"],item["chunk_text"],item["published_at"],
                    item["source_url"],item["content_hash"],MODEL,DIMENSION,embedding,
                ),
            )
        conn.execute(
            f"""
            INSERT INTO {SCHEMA}.index_metadata
              (release_id,index_status,production_ready,seed_count,embedding_model,embedding_dim)
            VALUES (%s,'demo',false,2,%s,%s)
            """,
            (RELEASE_ID, MODEL, DIMENSION),
        )
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(SCHEMA), sql.Identifier(reader_role)))
        conn.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                sql.Identifier(SCHEMA), sql.Identifier(reader_role)
            )
        )
        result = verify_connection(conn)
        conn.commit()
    return {"mode": "apply", "embedding_calls_max": 2, **result}


def verify_connection(conn: psycopg.Connection) -> dict[str, Any]:
    rows = conn.execute(
        f"""
        SELECT count(*) AS seed_count,count(DISTINCT document_id) AS document_count,
               count(*) FILTER (WHERE embedding_dim=1024 AND embedding_model='bge-m3') AS valid_vectors,
               count(*) FILTER (WHERE published_at>%s) AS cutoff_violations
        FROM {SCHEMA}.document_chunk
        """,
        (EXTERNAL_CUTOFF,),
    ).fetchone()
    metadata = conn.execute(
        f"SELECT release_id,index_status,production_ready,seed_count FROM {SCHEMA}.index_metadata"
    ).fetchone()
    if tuple(rows) != (2, 2, 2, 0):
        raise RuntimeError(f"demo vector row contract 실패: {tuple(rows)}")
    if metadata is None or tuple(metadata) != (RELEASE_ID, "demo", False, 2):
        raise RuntimeError(f"demo metadata contract 실패: {metadata}")
    return {
        "release_id": RELEASE_ID,
        "index_status": "demo",
        "production_ready": False,
        "seed_count": 2,
        "document_count": 2,
        "embedding_model": MODEL,
        "embedding_dim": DIMENSION,
        "cutoff_violations": 0,
    }


def verify() -> dict[str, Any]:
    with psycopg.connect(admin_dsn()) as conn:
        return {"mode": "verify", **verify_connection(conn)}


def check(manifest_path: Path) -> dict[str, Any]:
    documents = validate_manifest(manifest_path)
    return {
        "mode": "check",
        "release_id": RELEASE_ID,
        "index_status": "demo",
        "production_ready": False,
        "documents": len(documents),
        "chunks": len(documents),
        "embedding_model": MODEL,
        "embedding_dim": DIMENSION,
        "embedding_calls": 0,
        "source_types": sorted(item["source_type"] for item in documents),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="공식 외부문서 2건 demo vector 적재")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--reader-role", default="agent_reader")
    args = parser.parse_args()
    if args.verify:
        result = verify()
    else:
        if args.manifest is None:
            parser.error("--manifest가 필요합니다")
        result = check(args.manifest) if args.check else apply(args.manifest, args.reader_role)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
