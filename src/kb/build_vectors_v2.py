# -*- coding: utf-8 -*-
"""pgvector 1024차원 계약을 검증하고 동일 해시 운영 벡터만 재사용한다.

이 릴리스에서는 신규 CLOVA 임베딩 호출을 절대 수행하지 않는다. 재사용 계약을
모두 만족하지 못하면 세 테이블을 비우고 ``vector_status=pending``을 기록한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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


def existing_embeddings(
    conn: psycopg.Connection, table_name: str, hashes: set[str]
) -> dict[str, list[float]]:
    """정식 ``vec``에서 모델·차원·content hash가 모두 맞는 벡터만 읽는다."""
    if not hashes:
        return {}
    result: dict[str, list[float]] = {}
    exists = conn.execute(
        "SELECT to_regclass(%s)", (f"vec.{table_name}",)
    ).fetchone()[0]
    if not exists:
        return result
    rows = conn.execute(
        f"SELECT content_hash, embedding::text FROM vec.{table_name} "
        "WHERE embedding_model=%s AND embedding_dim=%s "
        "AND vector_dims(embedding)=%s AND content_hash = ANY(%s)",
        (MODEL, DIMENSION, DIMENSION, list(hashes)),
    ).fetchall()
    for content_hash, vector_text in rows:
        vector = json.loads(vector_text)
        if len(vector) == DIMENSION:
            result[content_hash] = [float(value) for value in vector]
    return result


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


def validate_chunk_foreign_keys(
    conn: psycopg.Connection, chunks: list[dict[str, object]]
) -> None:
    document_ids = {str(chunk["document_id"]) for chunk in chunks}
    product_ids = {
        str(chunk["product_id"])
        for chunk in chunks
        if chunk.get("product_id") not in (None, "")
    }
    if document_ids:
        found = {
            row[0]
            for row in conn.execute(
                f"SELECT document_id FROM {SCHEMAS['RELATIONS']}.source_document "
                "WHERE document_id = ANY(%s)",
                (list(document_ids),),
            ).fetchall()
        }
        if found != document_ids:
            raise ValueError(f"document_chunk FK 미해결: {sorted(document_ids - found)[:10]}")
    if product_ids:
        found = {
            row[0]
            for row in conn.execute(
                f"SELECT product_id FROM {SCHEMAS['ENRICHED']}.product_master "
                "WHERE product_id = ANY(%s)",
                (list(product_ids),),
            ).fetchall()
        }
        if found != product_ids:
            raise ValueError(f"document_chunk product FK 미해결: {sorted(product_ids - found)[:10]}")


def latest_vector_status(conn: psycopg.Connection) -> str:
    row = conn.execute(
        f"SELECT validation_result->>'vector_status' "
        f"FROM {SCHEMAS['META']}.load_run ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return str(row[0] or "pending") if row else "pending"


def validate_vectors(
    conn: psycopg.Connection, document_count: int | None = None
) -> dict[str, object]:
    bond, all_terms = collect_schema_sets()
    if not conn.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')"
    ).fetchone()[0]:
        raise RuntimeError("pgvector extension이 없습니다")
    expected_document_count = len(read_document_chunks())
    if document_count is not None and document_count not in {0, expected_document_count}:
        raise RuntimeError(
            f"document_chunk 입력/DB 행 수 계약 불일치: {document_count}/{expected_document_count}"
        )
    expected = {
        "bond_schema_terms": len(bond),
        "schema_terms_all": len(all_terms),
        "document_chunk": expected_document_count,
    }
    result: dict[str, int] = {}
    column_types = dict(
        conn.execute(
            """
            SELECT c.relname, format_type(a.atttypid,a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relname = ANY(%s)
              AND a.attname='embedding' AND NOT a.attisdropped
            """,
            (SCHEMAS["VEC"], list(expected)),
        ).fetchall()
    )
    if column_types != {name: "vector(1024)" for name in expected}:
        raise RuntimeError(f"vector(1024) 컬럼 계약 불일치: {column_types}")

    status = latest_vector_status(conn)
    if status not in {"pending", "ready"}:
        raise RuntimeError(f"알 수 없는 vector_status={status}")
    for table_name, expected_count in expected.items():
        count, nulls, bad_dim, duplicate_hashes = conn.execute(
            f"""
            SELECT count(*), count(*) FILTER (WHERE embedding IS NULL),
                   count(*) FILTER (WHERE vector_dims(embedding) <> 1024),
                   count(*) - count(DISTINCT content_hash)
            FROM {SCHEMAS['VEC']}.{table_name}
            """
        ).fetchone()
        required_count = expected_count if status == "ready" else 0
        if (count, nulls, bad_dim, duplicate_hashes) != (required_count, 0, 0, 0):
            raise RuntimeError(
                f"{table_name}: rows={count}/{required_count}, null={nulls}, "
                f"dim={bad_dim}, dup={duplicate_hashes}, status={status}"
            )
        result[table_name] = count
    hnsw = conn.execute(
        "SELECT count(*) FROM pg_indexes WHERE schemaname=%s "
        "AND indexdef ILIKE '%%USING hnsw%%'",
        (SCHEMAS["VEC"],),
    ).fetchone()[0]
    expected_hnsw = (
        sum(1 for expected_count in expected.values() if expected_count > 0)
        if status == "ready"
        else 0
    )
    if hnsw != expected_hnsw:
        raise RuntimeError(f"HNSW index={hnsw} != {expected_hnsw} for vector_status={status}")
    reader_write_privileges = 0
    if conn.execute("SELECT to_regrole('agent_reader') IS NOT NULL").fetchone()[0]:
        reader_write_privileges = conn.execute(
            """
            SELECT count(*) FROM unnest(%s::text[]) AS t(table_name)
            WHERE has_table_privilege(
              'agent_reader', format('%I.%I', %s, table_name),
              'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
            )
            """,
            (list(expected), SCHEMAS["VEC"]),
        ).fetchone()[0]
        if reader_write_privileges:
            raise RuntimeError(
                f"agent_reader가 vec stage 쓰기 권한을 가짐: {reader_write_privileges}"
            )
    return {
        "status": status,
        "rows": result,
        "hnsw_indexes": hnsw,
        "agent_reader_write_privileges": reader_write_privileges,
    }


def build() -> dict[str, object]:
    if psycopg is None:
        raise RuntimeError("실제 적재에는 requirements.txt의 psycopg가 필요합니다")
    bond, all_terms = collect_schema_sets()
    chunks = read_document_chunks()
    with psycopg.connect(dsn()) as conn:
        if not conn.execute(
            "SELECT to_regclass(%s)", (f"{SCHEMAS['VEC']}.schema_terms_all",)
        ).fetchone()[0]:
            raise RuntimeError("vec_next가 없습니다. RDB stage 빌더를 먼저 실행하세요")
        validate_chunk_foreign_keys(conn, chunks)
        expected_sets = {
            "bond_schema_terms": bond,
            "schema_terms_all": all_terms,
            "document_chunk": chunks,
        }
        caches = {
            table_name: existing_embeddings(
                conn,
                table_name,
                {str(record["content_hash"]) for record in records},
            )
            for table_name, records in expected_sets.items()
        }
        reusable = all(
            len(caches[table_name]) == len(records)
            for table_name, records in expected_sets.items()
        )

        conn.execute(
            f"TRUNCATE {SCHEMAS['VEC']}.document_chunk, "
            f"{SCHEMAS['VEC']}.bond_schema_terms, {SCHEMAS['VEC']}.schema_terms_all"
        )
        for table_name in expected_sets:
            conn.execute(
                f"DROP INDEX IF EXISTS {SCHEMAS['VEC']}.{table_name}_embedding_hnsw_idx"
            )

        status = "pending"
        if reusable:
            insert_terms(
                conn,
                "bond_schema_terms",
                bond,
                [caches["bond_schema_terms"][str(term["content_hash"])] for term in bond],
            )
            insert_terms(
                conn,
                "schema_terms_all",
                all_terms,
                [caches["schema_terms_all"][str(term["content_hash"])] for term in all_terms],
            )
            insert_document_chunks(
                conn,
                chunks,
                [caches["document_chunk"][str(chunk["content_hash"])] for chunk in chunks],
            )
            for table_name, records in expected_sets.items():
                if not records:
                    continue
                conn.execute(
                    f"CREATE INDEX {table_name}_embedding_hnsw_idx "
                    f"ON {SCHEMAS['VEC']}.{table_name} USING hnsw "
                    "(embedding vector_cosine_ops)"
                )
            status = "ready"

        row_counts = {
            table_name: conn.execute(
                f"SELECT count(*) FROM {SCHEMAS['VEC']}.{table_name}"
            ).fetchone()[0]
            for table_name in expected_sets
        }
        conn.execute(
            f"UPDATE {SCHEMAS['META']}.load_run SET "
            "validation_result=validation_result || %s::jsonb "
            "WHERE run_id=(SELECT run_id FROM "
            f"{SCHEMAS['META']}.load_run ORDER BY started_at DESC LIMIT 1)",
            (
                json.dumps(
                    {
                        "vector_status": status,
                        "vector_rows": row_counts,
                        "embedding_calls": 0,
                    }
                ),
            ),
        )
        validation = validate_vectors(conn, len(chunks))
    return {
        "model": MODEL,
        "dimension": DIMENSION,
        "vector_status": status,
        "embedding_calls": 0,
        "validation": validation,
        "document_source": str(DOCUMENT_CHUNKS),
    }


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
        "embedding_calls": 0,
        "new_embedding_generation": "disabled_for_this_release",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 pgvector 빌더")
    parser.add_argument("--check", action="store_true", help="DB/API 호출 없이 입력만 검증")
    args = parser.parse_args()
    print(json.dumps(check() if args.check else build(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
