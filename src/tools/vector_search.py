"""Agent-facing VectorDB search tool."""
from __future__ import annotations

from typing import Any

from infrastructure.vector_db.client import VectorDBClient


def search_documents(
    query_vector: list[float],
    *,
    top_k: int = 5,
    target_entities: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    product_ids = None
    if target_entities:
        product_ids = [
            str(entity.get("id"))
            for entity in target_entities
            if entity.get("id")
        ] or None
    return VectorDBClient().search(query_vector, top_k=top_k, product_ids=product_ids)

