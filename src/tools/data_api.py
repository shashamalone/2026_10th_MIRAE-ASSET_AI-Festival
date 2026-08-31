# -*- coding: utf-8 -*-
"""HTTP-only raw SQL/SPARQL client for local or same-VM Agent tools."""
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
    _raw_release_verified: bool = False

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
                headers={"User-Agent": "financial-agent-data-client/4.0"},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        self._raw_release_verified = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        verify_release: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
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
            detail = payload.get("detail")
            message = payload.get("message") or (detail if isinstance(detail, str) else None)
            raise DataApiClientError(
                response.status_code,
                str(payload.get("code") or "DATA_API_ERROR"),
                str(message or response.reason_phrase),
                payload.get("details") if isinstance(payload.get("details"), dict) else {},
            )
        release_id = payload.get("release_id")
        if verify_release and self.expected_release_id and release_id != self.expected_release_id:
            raise DataApiClientError(
                409,
                "RELEASE_MISMATCH",
                "Agent와 Data API의 release_id가 다릅니다",
                {"expected": self.expected_release_id, "actual": release_id},
            )
        return payload

    def _ensure_raw_release(self) -> None:
        if self.expected_release_id and not self._raw_release_verified:
            self.db_version()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def db_version(self) -> dict[str, Any]:
        payload = self._request("GET", "/db/version", verify_release=False)
        rows = payload.get("rows") or []
        actual = rows[0].get("release_id") if rows and isinstance(rows[0], dict) else None
        if self.expected_release_id and actual != self.expected_release_id:
            raise DataApiClientError(
                409,
                "RELEASE_MISMATCH",
                "Agent와 Data API의 release_id가 다릅니다",
                {"expected": self.expected_release_id, "actual": actual},
            )
        self._raw_release_verified = True
        return payload

    def stats(self) -> dict[str, Any]:
        self._ensure_raw_release()
        return self._request("GET", "/db/stats", verify_release=False)

    def tables(self) -> dict[str, Any]:
        self._ensure_raw_release()
        return self._request("GET", "/db/tables", verify_release=False)

    def columns(self, table_schema: str, table_name: str) -> dict[str, Any]:
        self._ensure_raw_release()
        return self._request(
            "GET",
            "/db/columns",
            verify_release=False,
            params={"table_schema": table_schema, "table_name": table_name},
        )

    def catalog(
        self,
        *,
        table_schema: str | None = None,
        table_name: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_raw_release()
        params = {
            key: value
            for key, value in {"table_schema": table_schema, "table_name": table_name}.items()
            if value is not None
        }
        return self._request("GET", "/db/catalog", verify_release=False, params=params)

    def sql(self, statement: str) -> dict[str, Any]:
        self._ensure_raw_release()
        return self._request(
            "POST",
            "/db/sql",
            verify_release=False,
            content=statement.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )

    def sparql(self, statement: str) -> dict[str, Any]:
        self._ensure_raw_release()
        return self._request(
            "POST",
            "/db/sparql",
            verify_release=False,
            content=statement.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
