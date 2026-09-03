"""Read-only Oxigraph client with ordered store and HTTP failover."""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from kb.config import ARTIFACTS

MAX_ROWS = 10_000
DEFAULT_TIMEOUT_SECONDS = 60.0
logger = logging.getLogger(__name__)
_FORBIDDEN = re.compile(
    r"\b(?:ADD|CLEAR|COPY|CREATE|DELETE|DROP|INSERT|LOAD|MOVE|SERVICE|WITH)\b",
    re.IGNORECASE,
)


class GraphStoreUnavailable(RuntimeError):
    """A configured Oxigraph store cannot be opened or read."""


class GraphDBUnavailable(RuntimeError):
    """No configured GraphDB transport is currently available."""


def _validate_query(query: str) -> str:
    text = query.lstrip()
    text = re.sub(r"(?is)^(?:PREFIX\s+\w*:\s*<[^>]+>\s*)+", "", text).lstrip()
    kind = text.split(None, 1)[0].upper() if text else ""
    if kind not in {"SELECT", "ASK"} or _FORBIDDEN.search(query):
        raise ValueError("Graph query는 SERVICE 없는 SELECT/ASK만 허용합니다")
    return kind


class OxigraphClient:
    """Query external snapshot, local snapshot, then the HTTP endpoint.

    The external path must be a filesystem path mounted on the Agent host. It
    is not an HTTP URL.  Only store availability failures trigger failover;
    invalid SPARQL and valid empty results do not.
    """

    def __init__(
        self,
        *,
        remote_store_path: str | Path | None = None,
        local_store_path: str | Path | None = None,
        endpoint: str | None = None,
        timeout: float | None = None,
        # Backward-compatible alias for the previous single local store.
        store_path: str | Path | None = None,
    ) -> None:
        remote_value = remote_store_path or os.getenv("OXIGRAPH_REMOTE_STORE_PATH")
        local_value = (
            local_store_path
            or store_path
            or os.getenv("OXIGRAPH_LOCAL_STORE_PATH")
            or os.getenv("OXIGRAPH_STORE_PATH")
            or str(ARTIFACTS / "oxigraph")
        )
        self.remote_store_path = Path(remote_value) if remote_value else None
        self.local_store_path = Path(local_value)
        self.endpoint = (
            endpoint
            or os.getenv("OXIGRAPH_FALLBACK_ENDPOINT")
            or os.getenv("OXIGRAPH_ENDPOINT", "")
        )
        self.timeout = float(
            timeout if timeout is not None else os.getenv("OXIGRAPH_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
        )

    def query(self, sparql: str) -> bool | list[dict[str, Any]]:
        kind = _validate_query(sparql)
        failures: list[str] = []
        attempted_paths: set[str] = set()

        for transport, path in (
            ("remote_store", self.remote_store_path),
            ("local_store", self.local_store_path),
        ):
            if path is None:
                continue
            # 경로 비교 때문에 원격 mount에 실제 접근하지 않도록 문자열만
            # 정규화한다. Path.resolve()는 UNC/NFS 장애 시 여기서 먼저
            # 지연되거나 실패할 수 있다.
            path_key = os.path.normcase(os.path.abspath(os.fspath(path)))
            if path_key in attempted_paths:
                continue
            attempted_paths.add(path_key)
            try:
                return self._query_store(path, sparql, kind)
            except GraphStoreUnavailable as exc:
                failures.append(f"{transport}: {exc}")
                logger.warning("Oxigraph %s unavailable; trying next transport: %s", transport, exc)

        if self.endpoint:
            try:
                return self._query_http(sparql, kind)
            except (OSError, RuntimeError) as exc:
                failures.append(f"endpoint: {type(exc).__name__}: {exc}")

        detail = "; ".join(failures) or "configured transport 없음"
        raise GraphDBUnavailable(f"GraphDB 연결 실패: {detail}")

    @lru_cache(maxsize=2)
    def _store(self, path_value: str):
        try:
            from pyoxigraph import Store
        except ImportError as exc:
            raise GraphStoreUnavailable("pyoxigraph가 설치되지 않았습니다") from exc

        path = Path(path_value)
        try:
            if not path.is_dir():
                raise GraphStoreUnavailable(f"Graph store 경로 없음: {path}")
            return Store.read_only(str(path))
        except GraphStoreUnavailable:
            raise
        except Exception as exc:
            raise GraphStoreUnavailable(f"Graph store open 실패({path}): {exc}") from exc

    def _query_store(self, path: Path, sparql: str, kind: str) -> bool | list[dict[str, Any]]:
        try:
            result = self._store(str(path)).query(sparql)
            if kind == "ASK":
                return bool(result)
            variables = [variable.value for variable in result.variables]
            rows = []
            for solution in result:
                if len(rows) >= MAX_ROWS:
                    raise ValueError(f"Graph 결과가 상한 {MAX_ROWS:,}행을 초과했습니다")
                rows.append(
                    {
                        name: (solution[name].value if solution[name] is not None else None)
                        for name in variables
                    }
                )
            return rows
        except GraphStoreUnavailable:
            raise
        except OSError as exc:
            raise GraphStoreUnavailable(f"Graph store query 실패({path}): {exc}") from exc

    def _query_http(self, sparql: str, kind: str) -> bool | list[dict[str, Any]]:
        import requests

        response = requests.post(
            self.endpoint,
            data=sparql.encode("utf-8"),
            headers={"Content-Type": "application/sparql-query", "Accept": "application/sparql-results+json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if kind == "ASK":
            return bool(payload.get("boolean"))
        rows = []
        for binding in payload.get("results", {}).get("bindings", []):
            rows.append({key: value.get("value") for key, value in binding.items()})
        return rows[:MAX_ROWS]

    def triple_count(self) -> int:
        result = self.query(
            """
            SELECT (COUNT(*) AS ?count)
            WHERE {
              { ?s ?p ?o }
              UNION
              { GRAPH ?g { ?s ?p ?o } }
            }
            """
        )
        if not isinstance(result, list) or not result or result[0].get("count") is None:
            raise RuntimeError("GraphDB triple count 응답 형식이 올바르지 않습니다")
        return int(result[0]["count"])
