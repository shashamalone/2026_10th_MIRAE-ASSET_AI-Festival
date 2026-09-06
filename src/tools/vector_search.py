"""
Agent 노드용 VectorDB 검색 도구. VectorDBClient를 얇게 감싸기만 한다.
문서 청크 검색·상품 ID 해소·문서 확보 여부·온톨로지 용어 검색을 노출한다.
입력은 질의 벡터와 상품 코드/이름, 출력은 dict 목록 또는 product_id 매핑이다.
DB/SQL 실패는 예외로 그대로 전파해 호출 노드가 abstain 판정하게 한다.
[구현 상태] 네 함수 모두 동작한다. 상태를 갖지 않고 호출마다 클라이언트를 만든다.
"""
from __future__ import annotations

from typing import Any

from infrastructure.vector_db.client import VectorDBClient


def search_documents(
    query_vector: list[float],
    *,
    top_k: int = 5,
    target_entities: list[dict[str, Any]] | None = None,
    product_ids: list[str] | None = None,
    section_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    # product_ids는 노드가 product_master로 실제 해소한 결과라 항상 우선한다.
    # target_entities 경로는 intent가 이미 id를 들고 있던 예전 호출부 호환용이다.
    if not product_ids and target_entities:
        product_ids = [str(entity.get("id")) for entity in target_entities if entity.get("id")]
    chunks = VectorDBClient().search(
        query_vector,
        top_k=top_k,
        product_ids=product_ids or None,
        section_types=section_types or None,
    )
    ids = list(dict.fromkeys(c.get("document_id") for c in chunks if c.get("document_id")))
    if not ids:
        return chunks
    try:
        metadata = _read_document_metadata(ids)
    except Exception:
        # Valid retrieved chunks remain useful; absent metadata stays absent.
        return chunks
    return [{**c, **metadata.get(c.get("document_id"), {})} for c in chunks]


def _read_document_metadata(document_ids: list[str]) -> dict[str, dict]:
    from agent import utils
    from tools import catalog_sql, schema_snapshot
    table = "vec.source_document"
    columns = ("document_id", "title", "publisher", "source_type")
    schema_snapshot.assert_contract(column_refs=[(table, c) for c in columns])
    conn = utils.get_pg_connection()
    try:
        rows = utils.run_sql(conn, f"SELECT {','.join(columns)} FROM {table} WHERE document_id IN ("
                            + ",".join(catalog_sql.literal(v) for v in document_ids[:60]) + ")")
    finally:
        conn.close()
    return {r["document_id"]: {"document_title": r.get("title"), "publisher": r.get("publisher"),
                                "source_type": r.get("source_type")} for r in rows}


def search_policy_documents(terms: list[str], limit: int = 10) -> list[dict]:
    """Official-policy/manager source catalogue route; no product-master fiction.

    Exact subject phrase in title/body plus source type, not global similarity.
    Unchunked documents can be cited as metadata only, not as policy claims.
    """
    from agent import utils
    from tools import catalog_sql, schema_snapshot
    terms = list(dict.fromkeys(t.strip() for t in terms if t.strip()))[:5]
    if not terms:
        return []
    columns = {"vec.source_document": ("document_id", "title", "publisher", "published_at", "source_url", "source_type", "as_of"),
               "vec.document_chunk": ("chunk_id", "document_id", "section_type", "page_number", "heading_path", "chunk_text", "effective_as_of")}
    schema_snapshot.assert_contract(column_refs=[(t, c) for t, cs in columns.items() for c in cs])
    terms_sql = " OR ".join("POSITION(" + catalog_sql.literal(catalog_sql.normalize(t))
                            + " IN LOWER(REPLACE(COALESCE(d.title,'') || ' ' || COALESCE(c.chunk_text,''),' ',''))) > 0"
                            for t in terms)
    sql = ("SELECT c.chunk_id,d.document_id,c.section_type,c.page_number,c.heading_path,c.chunk_text,"
           "c.effective_as_of,d.title AS document_title,d.publisher,d.published_at,d.source_url,d.source_type "
           "FROM vec.source_document d LEFT JOIN vec.document_chunk c ON c.document_id=d.document_id "
           "WHERE LOWER(d.source_type) IN ('policy','manager') AND (" + terms_sql + ") "
           "ORDER BY d.published_at DESC NULLS LAST,d.document_id,c.chunk_id LIMIT " + str(max(1, min(int(limit), 20))))
    conn = utils.get_pg_connection()
    try:
        return utils.run_sql(conn, sql)
    finally:
        conn.close()


def resolve_product_ids(codes: list[str], names: list[str]) -> list[str]:
    return VectorDBClient().resolve_product_ids(codes, names)


def get_coverage(product_ids: list[str]) -> dict[str, dict[str, Any]]:
    return VectorDBClient().coverage(product_ids)


def search_schema_terms(query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    return VectorDBClient().search_schema_terms(query_vector, top_k=top_k)
