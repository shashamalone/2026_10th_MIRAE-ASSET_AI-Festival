# -*- coding: utf-8 -*-
"""TBox grounding과 근거 문서 청크를 pgvector 1024차원으로 적재한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Namespace, URIRef
from rdflib.namespace import OWL

try:
    import psycopg
except ImportError:  # --check는 DB 드라이버 없이도 순수 검증으로 동작한다.
    psycopg = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import clova  # noqa: E402
from kb.build_data_platform_v2 import SCHEMAS, dsn  # noqa: E402
from kb.v2_manifest import EXTERNAL_CUTOFF, ROOT  # noqa: E402

FP = Namespace("http://mafest.ai/product#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
MODEL = "bge-m3"
DIMENSION = 1024
TBOX_FILES = (
    "common.ttl",
    "bond_kr.ttl",
    "etf_kr.ttl",
    "etf_gl.ttl",
    "fund_pub.ttl",
)
DOCUMENT_CHUNKS = ROOT / "artifacts" / "document_chunks.jsonl"


def execute_many(conn: psycopg.Connection, statement: str, rows) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(statement, rows)


def pick(graph: Graph, subject, prop, language: str = "ko") -> str:
    values = list(graph.objects(subject, prop))
    preferred = [str(value) for value in values if getattr(value, "language", None) == language]
    return (preferred or [str(value) for value in values] or [""])[0]


def collect_terms(file_names: tuple[str, ...]) -> list[dict[str, object]]:
    graph = Graph()
    origins: dict[URIRef, set[str]] = {}
    for name in file_names:
        one = Graph()
        one.parse(ROOT / "ontology" / name, format="turtle")
        graph += one
        for subject in one.subjects(RDFS.comment, None):
            if isinstance(subject, URIRef) and str(subject).startswith(str(FP)):
                origins.setdefault(subject, set()).add(name)
    subjects = {
        subject
        for subject in graph.subjects(RDFS.comment, None)
        if isinstance(subject, URIRef) and str(subject).startswith(str(FP))
    }
    terms: list[dict[str, object]] = []
    for subject in sorted(subjects, key=str):
        term_uri = f"fp:{str(subject).split('#')[-1]}"
        label = pick(graph, subject, RDFS.label)
        comment = pick(graph, subject, RDFS.comment)
        alt_labels = sorted(str(value) for value in graph.objects(subject, SKOS.altLabel))
        if (subject, RDF.type, OWL.Class) in graph:
            property_type = "class"
        elif (subject, RDF.type, OWL.ObjectProperty) in graph:
            property_type = "object_property"
        elif (subject, RDF.type, OWL.DatatypeProperty) in graph:
            property_type = "datatype_property"
        elif any(graph.objects(subject, RDF.type)):
            property_type = "individual"
        else:
            property_type = "other"
        content = " | ".join(
            value for value in (term_uri, label, " / ".join(alt_labels), comment) if value
        )
        terms.append(
            {
                "term_uri": term_uri,
                "label": label,
                "comment": comment,
                "alt_labels": alt_labels,
                "domain_file": ",".join(sorted(origins[subject])),
                "property_type": property_type,
                "content": content,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        )
    return terms


def collect_schema_sets() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    bond = collect_terms(("common.ttl", "bond_kr.ttl"))
    all_terms = collect_terms(TBOX_FILES)
    if len(bond) != 130:
        raise ValueError(f"채권 TBox grounding 행 수 불일치: bond={len(bond)}")
    for name, terms in (("bond", bond), ("all", all_terms)):
        hashes = [str(term["content_hash"]) for term in terms]
        if len(hashes) != len(set(hashes)):
            raise ValueError(f"{name}: 중복 원문 해시")
    return bond, all_terms


def read_document_chunks(path: Path = DOCUMENT_CHUNKS) -> list[dict[str, object]]:
    if not path.exists():
        return []
    required = {
        "chunk_id",
        "document_id",
        "citation_text",
        "chunk_text",
        "published_at",
        "source_url",
    }
    chunks: list[dict[str, object]] = []
    seen_hashes: set[str] = set()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            missing = required - set(row)
            if missing:
                raise ValueError(f"{path.name}:{line_number}: 필수 필드 누락 {sorted(missing)}")
            published_at = date.fromisoformat(row["published_at"])
            if published_at > EXTERNAL_CUTOFF:
                raise ValueError(
                    f"{path.name}:{line_number}: published_at {published_at} > {EXTERNAL_CUTOFF}"
                )
            text = str(row["chunk_text"]).strip()
            if not text:
                raise ValueError(f"{path.name}:{line_number}: 빈 chunk_text")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in seen_hashes:
                raise ValueError(f"{path.name}:{line_number}: 중복 원문 해시 {digest}")
            seen_hashes.add(digest)
            chunks.append({**row, "published_at": published_at, "content_hash": digest})
    return chunks


def existing_embeddings(conn: psycopg.Connection, hashes: set[str]) -> dict[str, list[float]]:
    if not hashes:
        return {}
    result: dict[str, list[float]] = {}
    for schema_name in (SCHEMAS["VEC"], "vec"):
        for table_name in ("bond_schema_terms", "schema_terms_all", "document_chunk"):
            exists = conn.execute(
                "SELECT to_regclass(%s)", (f"{schema_name}.{table_name}",)
            ).fetchone()[0]
            if not exists:
                continue
            rows = conn.execute(
                f"SELECT content_hash, embedding::text FROM {schema_name}.{table_name} "
                "WHERE embedding_model=%s AND content_hash = ANY(%s)",
                (MODEL, list(hashes)),
            ).fetchall()
            for content_hash, vector_text in rows:
                result[content_hash] = json.loads(vector_text)
    return result


def embeddings_for(
    conn: psycopg.Connection, records: list[dict[str, object]], cache: dict[str, list[float]]
) -> list[list[float]]:
    missing_records = [record for record in records if record["content_hash"] not in cache]
    if missing_records:
        vectors = clova.embed_many([str(record.get("content") or record["chunk_text"]) for record in missing_records])
        for record, vector in zip(missing_records, vectors):
            if len(vector) != DIMENSION:
                raise ValueError(f"CLOVA 임베딩 차원 {len(vector)} != {DIMENSION}")
            cache[str(record["content_hash"])] = [float(value) for value in vector]
    return [cache[str(record["content_hash"])] for record in records]


def insert_terms(
    conn: psycopg.Connection,
    table_name: str,
    terms: list[dict[str, object]],
    vectors: list[list[float]],
) -> None:
    execute_many(
        conn,
        f"""
        INSERT INTO {SCHEMAS['VEC']}.{table_name}
          (term_uri,label,comment,alt_labels,domain_file,property_type,content,content_hash,
           embedding_model,embedding_dim,embedding)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
        ON CONFLICT (term_uri) DO UPDATE SET
          label=EXCLUDED.label, comment=EXCLUDED.comment, alt_labels=EXCLUDED.alt_labels,
          domain_file=EXCLUDED.domain_file, property_type=EXCLUDED.property_type,
          content=EXCLUDED.content, content_hash=EXCLUDED.content_hash,
          embedding_model=EXCLUDED.embedding_model, embedding_dim=EXCLUDED.embedding_dim,
          embedding=EXCLUDED.embedding
        """,
        [
            (
                term["term_uri"],
                term["label"],
                term["comment"],
                term["alt_labels"],
                term["domain_file"],
                term["property_type"],
                term["content"],
                term["content_hash"],
                MODEL,
                DIMENSION,
                json.dumps(vector),
            )
            for term, vector in zip(terms, vectors)
        ],
    )


def insert_document_chunks(
    conn: psycopg.Connection,
    chunks: list[dict[str, object]],
    vectors: list[list[float]],
) -> None:
    execute_many(
        conn,
        f"""
        INSERT INTO {SCHEMAS['VEC']}.document_chunk
          (chunk_id,document_id,product_id,page_number,citation_text,chunk_text,published_at,
           source_url,content_hash,embedding_model,embedding_dim,embedding)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
        ON CONFLICT (chunk_id) DO UPDATE SET
          document_id=EXCLUDED.document_id, product_id=EXCLUDED.product_id,
          page_number=EXCLUDED.page_number, citation_text=EXCLUDED.citation_text,
          chunk_text=EXCLUDED.chunk_text, published_at=EXCLUDED.published_at,
          source_url=EXCLUDED.source_url, content_hash=EXCLUDED.content_hash,
          embedding_model=EXCLUDED.embedding_model, embedding_dim=EXCLUDED.embedding_dim,
          embedding=EXCLUDED.embedding
        """,
        [
            (
                chunk["chunk_id"],
                chunk["document_id"],
                chunk.get("product_id"),
                chunk.get("page_number"),
                chunk["citation_text"],
                chunk["chunk_text"],
                chunk["published_at"],
                chunk["source_url"],
                chunk["content_hash"],
                MODEL,
                DIMENSION,
                json.dumps(vector),
            )
            for chunk, vector in zip(chunks, vectors)
        ],
    )


def validate_vectors(conn: psycopg.Connection, document_count: int) -> dict[str, int]:
    bond, all_terms = collect_schema_sets()
    expected = {
        "bond_schema_terms": len(bond),
        "schema_terms_all": len(all_terms),
        "document_chunk": document_count,
    }
    result: dict[str, int] = {}
    for table_name, expected_count in expected.items():
        count, nulls, bad_dim, duplicate_hashes = conn.execute(
            f"""
            SELECT count(*), count(*) FILTER (WHERE embedding IS NULL),
                   count(*) FILTER (WHERE vector_dims(embedding) <> 1024),
                   count(*) - count(DISTINCT content_hash)
            FROM {SCHEMAS['VEC']}.{table_name}
            """
        ).fetchone()
        if (count, nulls, bad_dim, duplicate_hashes) != (expected_count, 0, 0, 0):
            raise RuntimeError(
                f"{table_name}: rows={count}/{expected_count}, null={nulls}, dim={bad_dim}, dup={duplicate_hashes}"
            )
        result[table_name] = count
    return result


def build() -> dict[str, object]:
    if psycopg is None:
        raise RuntimeError("실제 적재에는 requirements.txt의 psycopg가 필요합니다")
    bond, all_terms = collect_schema_sets()
    chunks = read_document_chunks()
    all_records = all_terms + chunks
    hashes = {str(record["content_hash"]) for record in all_records}
    with psycopg.connect(dsn()) as conn:
        if not conn.execute(
            "SELECT to_regclass(%s)", (f"{SCHEMAS['VEC']}.schema_terms_all",)
        ).fetchone()[0]:
            raise RuntimeError("vec_next가 없습니다. RDB stage 빌더를 먼저 실행하세요")
        cache = existing_embeddings(conn, hashes)
        all_vectors = embeddings_for(conn, all_terms, cache)
        vector_by_hash = {
            str(term["content_hash"]): vector for term, vector in zip(all_terms, all_vectors)
        }
        bond_vectors = [vector_by_hash[str(term["content_hash"])] for term in bond]
        chunk_vectors = embeddings_for(conn, chunks, cache)
        insert_terms(conn, "bond_schema_terms", bond, bond_vectors)
        insert_terms(conn, "schema_terms_all", all_terms, all_vectors)
        insert_document_chunks(conn, chunks, chunk_vectors)
        for table_name in ("bond_schema_terms", "schema_terms_all", "document_chunk"):
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {table_name}_embedding_hnsw_idx "
                f"ON {SCHEMAS['VEC']}.{table_name} USING hnsw (embedding vector_cosine_ops)"
            )
        counts = validate_vectors(conn, len(chunks))
        conn.execute(
            f"UPDATE {SCHEMAS['META']}.load_run SET phase='vectors_validated', "
            "validation_result=validation_result || %s::jsonb WHERE status='passed'",
            (json.dumps({"vector_rows": counts}),),
        )
    return {"model": MODEL, "dimension": DIMENSION, "rows": counts, "document_source": str(DOCUMENT_CHUNKS)}


def check() -> dict[str, object]:
    bond, all_terms = collect_schema_sets()
    chunks = read_document_chunks()
    return {
        "mode": "check",
        "mutated_files": False,
        "mutated_database": False,
        "bond_schema_terms": len(bond),
        "schema_terms_all": len(all_terms),
        "document_chunks": len(chunks),
        "model": MODEL,
        "dimension": DIMENSION,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 pgvector 빌더")
    parser.add_argument("--check", action="store_true", help="DB/API 호출 없이 입력만 검증")
    args = parser.parse_args()
    print(json.dumps(check() if args.check else build(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
