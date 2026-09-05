"""
Oxigraph GraphDB 읽기 전용 클라이언트.

원격 VM의 Oxigraph 저장소를 Agent 호스트에 마운트한 경로로 직접 읽고,
해당 저장소를 사용할 수 없을 때 로컬 저장소, HTTP endpoint 순서로
조회 대상을 전환한다. GraphDB 연결과 SPARQL 실행을 Agent 노드에서
분리하기 위한 infrastructure adapter다.

[구현 상태]

- Oxigraph 직접 조회: pyoxigraph의 ``Store.read_only``로 파일 기반 저장소를
  열어 SELECT/ASK 쿼리를 실행한다.
- 연결 순서: ``OXIGRAPH_REMOTE_STORE_PATH``(원격 VM 마운트 경로) ->
  ``OXIGRAPH_LOCAL_STORE_PATH`` 또는 기본 artifacts 경로 ->
  ``OXIGRAPH_FALLBACK_ENDPOINT``/``OXIGRAPH_ENDPOINT``.
- 장애 처리: 저장소를 열거나 읽을 수 없는 경우에만 다음 transport로
  failover한다. 잘못된 SPARQL과 정상적인 빈 결과는 장애로 간주하지 않는다.
- SPARQL 안전성: SERVICE가 없는 SELECT/ASK만 허용하고, INSERT·DELETE·
  UPDATE 계열 키워드는 차단한다. 결과는 기본 최대 10,000행으로 제한하며,
  ``max_rows=None``은 엔티티 인덱스 구축처럼 전체를 읽어야 하는 내부 호출 전용이다.
- HTTP timeout: ``OXIGRAPH_TIMEOUT``으로 조정할 수 있으며 기본값은 60초다.
- ``triple_count``: 선택된 GraphDB transport에서 전체 triple 수를 확인한다.

원격 저장소는 HTTP URL을 파일 경로로 직접 전달하는 방식이 아니라,
SSHFS/NFS 등으로 Agent 실행 환경에 마운트된 실제 filesystem 경로를
``OXIGRAPH_REMOTE_STORE_PATH``에 설정해야 한다. 직접 저장소를 사용할 수
없을 때에만 endpoint 조회를 시도한다.
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# 저장소 루트: src/infrastructure/graph_db/client.py 기준 3단계 위.
# kb.config와 같은 기준을 독립적으로 계산해 infrastructure adapter가 kb
# 패키지에 결합되지 않게 한다.
REPO_ROOT = Path(__file__).resolve().parents[3]

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



def _anchor(path_value: str | Path) -> Path:
    """상대 store 경로를 저장소 루트 기준으로 고정한다.

    .env의 ``OXIGRAPH_LOCAL_STORE_PATH``가 상대경로("artifacts/oxigraph")면
    노트북이 ``os.chdir("src")``를 한 뒤에는 cwd 기준으로 풀려
    ``src/artifacts/oxigraph``를 찾다가 로컬 스토어를 통째로 건너뛰고
    원격 endpoint로만 붙었다(2026-09-03 실측). 실행 위치와 무관하게 같은
    스토어를 보도록 저장소 루트에 붙인다."""
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path

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
            or str(REPO_ROOT / "artifacts" / "oxigraph")
        )
        self.remote_store_path = _anchor(remote_value) if remote_value else None
        self.local_store_path = _anchor(local_value)
        self.endpoint = (
            endpoint
            or os.getenv("OXIGRAPH_FALLBACK_ENDPOINT")
            or os.getenv("OXIGRAPH_ENDPOINT", "")
        )
        self.timeout = float(
            timeout if timeout is not None else os.getenv("OXIGRAPH_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
        )

    def query(self, sparql: str, *, max_rows: int | None = MAX_ROWS) -> bool | list[dict[str, Any]]:
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
                return self._query_store(path, sparql, kind, max_rows=max_rows)
            except GraphStoreUnavailable as exc:
                failures.append(f"{transport}: {exc}")
                logger.warning("Oxigraph %s unavailable; trying next transport: %s", transport, exc)

        if self.endpoint:
            try:
                return self._query_http(sparql, kind, max_rows=max_rows)
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

    def _query_store(
        self, path: Path, sparql: str, kind: str, max_rows: int | None = MAX_ROWS
    ) -> bool | list[dict[str, Any]]:
        try:
            result = self._store(str(path)).query(sparql)
            if kind == "ASK":
                return bool(result)
            variables = [variable.value for variable in result.variables]
            rows = []
            for solution in result:
                if max_rows is not None and len(rows) >= max_rows:
                    raise ValueError(f"Graph 결과가 상한 {max_rows:,}행을 초과했습니다")
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

    def _query_http(
        self, sparql: str, kind: str, max_rows: int | None = MAX_ROWS
    ) -> bool | list[dict[str, Any]]:
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
        return rows if max_rows is None else rows[:max_rows]

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
