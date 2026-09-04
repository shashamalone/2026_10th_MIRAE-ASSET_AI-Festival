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
    return VectorDBClient().search(
        query_vector,
        top_k=top_k,
        product_ids=product_ids or None,
        section_types=section_types or None,
    )


def resolve_product_ids(codes: list[str], names: list[str]) -> list[str]:
    return VectorDBClient().resolve_product_ids(codes, names)


def get_coverage(product_ids: list[str]) -> dict[str, dict[str, Any]]:
    return VectorDBClient().coverage(product_ids)


def search_schema_terms(query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    return VectorDBClient().search_schema_terms(query_vector, top_k=top_k)
