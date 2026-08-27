# -*- coding: utf-8 -*-
"""HTTP-only client used by local or same-VM LangGraph tools.

This module intentionally has no PostgreSQL, Oxigraph, or CLOVA dependency.  The
Agent owns question embeddings and sends the resulting 1024-dimensional vector
to ``semantic_search``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Self

import httpx


class DataApiClientError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class FinancialDataClient:
    base_url: str
    timeout_seconds: float = 3.0
    expected_release_id: str | None = None
    _client: httpx.Client | None = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("FINANCIAL_DATA_API_URL은 http:// 또는 https:// URL이어야 합니다")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 10:
            raise ValueError("Data API timeout은 0초 초과 10초 이하여야 합니다")

    @classmethod
    def from_env(cls) -> FinancialDataClient:
        base_url = os.environ.get("FINANCIAL_DATA_API_URL", "").strip()
        if not base_url:
            raise RuntimeError("FINANCIAL_DATA_API_URL 환경변수가 필요합니다")
        timeout = float(os.environ.get("FINANCIAL_DATA_API_TIMEOUT_SECONDS", "3"))
        expected = os.environ.get("FINANCIAL_DATA_RELEASE_ID") or None
        return cls(base_url=base_url, timeout_seconds=timeout, expected_release_id=expected)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_seconds),
                headers={"User-Agent": "financial-agent-data-client/1.0"},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise DataApiClientError(504, "DATA_API_TIMEOUT", "Data API 응답 시간이 초과되었습니다") from exc
        except httpx.HTTPError as exc:
            raise DataApiClientError(502, "DATA_API_UNREACHABLE", str(exc)) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise DataApiClientError(
                502,
                "DATA_API_INVALID_RESPONSE",
                f"JSON이 아닌 응답입니다: HTTP {response.status_code}",
            ) from exc
        if response.is_error:
            raise DataApiClientError(
                response.status_code,
                str(payload.get("code") or "DATA_API_ERROR"),
                str(payload.get("message") or response.reason_phrase),
                payload.get("details") if isinstance(payload.get("details"), dict) else {},
            )
        release_id = payload.get("release_id")
        if self.expected_release_id and release_id != self.expected_release_id:
            raise DataApiClientError(
                409,
                "RELEASE_MISMATCH",
                "Agent와 Data API의 release_id가 다릅니다",
                {"expected": self.expected_release_id, "actual": release_id},
            )
        return payload

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def release(self) -> dict[str, Any]:
        return self._request("GET", "/v1/release")

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/v1/capabilities")

    def search_products(
        self,
        name: str,
        *,
        match: str = "exact",
        product_types: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/products/search",
            json={"name": name, "match": match, "product_types": product_types or [], "limit": limit},
        )

    def query_products(self, **query: Any) -> dict[str, Any]:
        return self._request("POST", "/v1/products/query", json=query)

    def product(self, product_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/products/{product_id}")

    def compare_products(self, product_ids: list[str], metric_codes: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/products/compare",
            json={"product_ids": product_ids, "metric_codes": metric_codes},
        )

    def holdings(self, product_id: str, *, as_of: str = "latest", limit: int = 20) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/products/{product_id}/holdings",
            params={"as_of": as_of, "limit": limit},
        )

    def traverse(
        self,
        start_entity_id: str,
        path: list[str],
        *,
        as_of: str = "latest",
        limit: int = 20,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/relations/traverse",
            json={"start_entity_id": start_entity_id, "path": path, "as_of": as_of, "limit": limit},
        )

    def validate_ontology(self, **request: Any) -> dict[str, Any]:
        return self._request("POST", "/v1/ontology/validate", json=request)

    def semantic_search(
        self,
        query_embedding: list[float],
        *,
        candidate_product_ids: list[str] | None = None,
        top_k: int = 2,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/evidence/semantic-search",
            json={
                "query_embedding": query_embedding,
                "candidate_product_ids": candidate_product_ids,
                "top_k": top_k,
            },
        )
