"""
세 엔진(Graph, RDB, Vector)의 HTTP 어댑터.

팀원 서버의 Swagger(http://40.82.145.44:8000/docs)에서 확인된 실제 사용법:
  POST /db      - 단일 창구. {"sql": ...}면 RDB(Postgres), {"sparql": ...}면
                  Graph(Oxigraph)로 처리된다. 팀원분이 "이 URL 하나만 상수로
                  두면 된다"고 안내한 방식이라 RDB, Graph 둘 다 이걸 쓴다.
  GET  /db/tables, GET /db/columns/{schema}/{table} - 스키마 조회용
  GET  /health, GET /db/stats - 확인됨
  POST /chat, GET /answer - 이 프로젝트의 다른 부분(전체 파이프라인용)으로 보임

RDB와 Graph가 완전히 같은 엔드포인트(/db)를 쓰기 때문에 base_url을 공유한다.
Vector 전용 경로는 Swagger 목록에서 안 보였다. pgvector가 RDB와 같은
Postgres(vec 스키마, 확인 시점 기준 아직 비어 있음) 안에 있으니, 별도 경로
없이 /db에 vec 스키마를 대상으로 한 SQL을 보내는 방식일 가능성이 있다.
"""
from __future__ import annotations

import os
from typing import Protocol

import httpx

from .state import PlanStep, StepResult


class GraphEngine(Protocol):
    async def query(self, sparql: str) -> list[dict]: ...


class RdbEngine(Protocol):
    async def query(self, sql: str) -> list[dict]: ...


class VectorEngine(Protocol):
    async def search(self, text: str, top_k: int = 5) -> list[dict]: ...


class RdbHttpEngine:
    """사내 FastAPI 서버를 통해 PostgreSQL(raw 스키마)에 접근하는 RDB 엔진.

    SSH 접속 정보는 이 어댑터에서 쓰지 않는다. 서버가 공개 IP로 열려 있어
    HTTP로 바로 질의한다.

    QUERY_PATH는 팀원분이 안내해주신 단일 창구 POST /db 다. Swagger 설명에
    "DB 하나로 취급하는 단일 창구, 팀원 코드에서는 이 URL 하나만 상수로 두면
    된다"고 되어 있고, {"sql": ...}를 보내면 RDB로, {"sparql": ...}를 보내면
    Graph(Oxigraph)로 처리된다. GraphDbHttpEngine도 같은 경로를 쓴다.

    요청 본문: {"sql": str, "params": dict, "limit": int}
    응답 본문: {"columns": [...], "rows": [...], "row_count": int,
              "truncated": bool, "elapsed_ms": float}
    둘 다 Swagger에서 실제로 확인했다.

    스키마는 raw(주최측 원본 데이터)와 vec(벡터, 확인 시점 기준 아직 비어 있음)
    두 개가 있다고 한다. Vector 검색도 결국 이 엔드포인트로, vec 스키마를
    대상으로 하는 SQL(pgvector의 <-> 연산자 등)을 보내는 방식일 가능성이 크다.

    TODO: params가 파라미터 바인딩(플레이스홀더 문법)을 지원하는 것 같은데
    정확한 문법(:이름 / %(이름)s / $1 등)은 아직 확인 전이라 지금은 빈 dict만
    보낸다. 확인되면 inject_results로 문자열에 직접 값을 끼워 넣는 대신
    params로 안전하게 바인딩하도록 바꾸는 게 SQL 인젝션 위험을 줄이는 데 낫다.
    """

    QUERY_PATH = "/db"
    HEALTH_PATH = "/health"
    STATS_PATH = "/db/stats"
    TABLES_PATH = "/db/tables"
    COLUMNS_PATH = "/db/columns/{schema}/{table}"
    DEFAULT_LIMIT = 200

    def __init__(self, base_url: str | None = None, timeout_s: float = 5.0):
        resolved = base_url or os.environ.get("RDB_API_BASE_URL", "http://40.82.145.44:8000")
        self.base_url = resolved.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s)

    # async def query(self, sql: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    #     response = await self._client.post(
    #         self.QUERY_PATH,
    #         json={"sql": sql, "params": {}, "limit": limit},
    #     )
    #     response.raise_for_status()
    #     return self._parse_rows(response.json())
    
    async def query(self, sql: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
        response = await self._client.post(
            self.QUERY_PATH,
            json={"sql": sql, "params": {}, "limit": limit},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text
            raise RuntimeError(f"RDB API 에러: {exc}\n서버 응답 상세: {error_body}") from exc
            
        return self._parse_rows(response.json())

    @staticmethod
    def _parse_rows(payload: object) -> list[dict]:
        if isinstance(payload, dict) and "rows" in payload:
            # payload에는 rows 외에 row_count, truncated, elapsed_ms도 들어있다.
            # truncated가 True면 limit에 걸려 결과가 잘렸다는 뜻이니, 필요하면
            # 여기서 로그를 남기거나 limit을 조정하는 로직을 추가할 수 있다.
            return payload["rows"]
        if isinstance(payload, list):
            return payload
        raise ValueError(f"예상치 못한 RDB 응답 형태: {type(payload)}")

    async def health_check(self) -> dict:
        response = await self._client.get(self.HEALTH_PATH)
        response.raise_for_status()
        return response.json()

    async def db_stats(self) -> dict:
        response = await self._client.get(self.STATS_PATH)
        response.raise_for_status()
        return response.json()

    async def list_tables(self) -> object:
        """GET /db/tables. plan_routing에 넘길 metadata_context를 만들 때
        실제 테이블 목록을 참고하고 싶으면 2단계 쪽에서 이 메서드를 쓸 수 있다."""
        response = await self._client.get(self.TABLES_PATH)
        response.raise_for_status()
        return response.json()

    async def list_columns(self, schema: str, table: str) -> object:
        """GET /db/columns/{schema}/{table}. 특정 테이블의 실제 컬럼 목록을 확인한다."""
        path = self.COLUMNS_PATH.format(schema=schema, table=table)
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()


class VectorHttpEngine:
    """pgvector 기반 벡터 검색 엔진. RDB와 물리적으로 같은 FastAPI 서버를 쓰므로
    base_url 기본값도 RdbHttpEngine과 동일하게 맞췄다.

    TODO: Swagger 목록에서 Vector 전용 경로가 안 보였다. 아래 두 가능성 중
    실제로 어느 쪽인지 팀원분께 확인이 필요하다.
      (1) 별도 경로가 있는데 이번에 캡처된 화면에 안 잡혔을 가능성
          (Swagger에서 위아래로 더 스크롤하면 나올 수 있음)
      (2) 별도 경로 없이 POST /db/sql로 pgvector의 <-> 연산자를 쓴 SQL을
          보내는 방식일 가능성 (이 경우 VectorHttpEngine이 따로 필요 없고
          RdbHttpEngine.query()로 통합될 수 있음)
    지금은 (1)이라고 가정하고 자리표시자 경로를 남겨뒀다.
    """

    SEARCH_PATH = "/vector/search"  # TODO: 확인 필요. 존재하지 않을 수도 있음

    def __init__(self, base_url: str | None = None, timeout_s: float = 5.0):
        resolved = (
            base_url
            or os.environ.get("VECTOR_API_BASE_URL")
            or os.environ.get("RDB_API_BASE_URL", "http://40.82.145.44:8000")
        )
        self.base_url = resolved.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s)

    # async def search(self, text: str, top_k: int = 5) -> list[dict]:
    #     response = await self._client.post(self.SEARCH_PATH, json={"text": text, "top_k": top_k})
    #     response.raise_for_status()
    #     return self._parse_results(response.json())
    
    async def search(self, text: str, top_k: int = 5) -> list[dict]:
        response = await self._client.post(self.SEARCH_PATH, json={"text": text, "top_k": top_k})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text
            raise RuntimeError(f"Vector API 에러: {exc}\n서버 응답 상세: {error_body}") from exc
            
        return self._parse_results(response.json())


    @staticmethod
    def _parse_results(payload: object) -> list[dict]:
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
        if isinstance(payload, list):
            return payload
        raise ValueError(f"예상치 못한 Vector 응답 형태: {type(payload)}")

    async def aclose(self) -> None:
        await self._client.aclose()


class GraphDbHttpEngine:
    """Graph(SPARQL) 엔진.

    RDB와 완전히 같은 단일 창구 POST /db를 쓴다. sql 대신 sparql 키를
    보내는 것만 다르다. 팀원분 설명에 따르면 SPARQL은 Oxigraph로 그대로
    전달된다(GraphDB Desktop이 아니었다).

    네임스페이스: fp: http://mafest.ai/product# (스키마),
                fpi: http://mafest.ai/instance/ (개체)
    이 네임스페이스는 prompts.py의 PLAN_SYSTEM_PROMPT에도 반영해서, LLM이
    SPARQL을 쓸 때 정확한 URI를 쓰도록 했다.

    성능 주의(팀원분이 직접 알려주신 내용): OPTIONAL 절은 반드시 필수 패턴
    뒤에 와야 한다. 중간에 두면 같은 결과를 내는 데 1000배까지 느려질 수
    있다고 한다. 이것도 프롬프트에 반영해뒀다.

    요청/응답 형식은 RdbHttpEngine과 동일하게 Swagger에서 확인했다.
    요청 본문: {"sparql": str, "params": dict, "limit": int}
    응답 본문: {"columns": [...], "rows": [...], "row_count": int,
              "truncated": bool, "elapsed_ms": float}
    """

    QUERY_PATH = "/db"
    DEFAULT_LIMIT = 200

    def __init__(self, base_url: str | None = None, timeout_s: float = 5.0):
        resolved = (
            base_url
            or os.environ.get("GRAPH_API_BASE_URL")
            or os.environ.get("RDB_API_BASE_URL", "http://40.82.145.44:8000")
        )
        self.base_url = resolved.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s)

    # async def query(self, sparql: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    #     response = await self._client.post(
    #         self.QUERY_PATH,
    #         json={"sparql": sparql, "params": {}, "limit": limit},
    #     )
    #     response.raise_for_status()
    #     return self._parse_rows(response.json())
    
    async def query(self, sparql: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
        response = await self._client.post(
            self.QUERY_PATH,
            json={"sparql": sparql, "params": {}, "limit": limit},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text
            raise RuntimeError(f"Graph API 에러: {exc}\n서버 응답 상세: {error_body}") from exc
            
        return self._parse_rows(response.json())


    @staticmethod
    def _parse_rows(payload: object) -> list[dict]:
        if isinstance(payload, dict) and "rows" in payload:
            return payload["rows"]
        if isinstance(payload, list):
            return payload
        raise ValueError(f"예상치 못한 Graph 응답 형태: {type(payload)}")

    async def aclose(self) -> None:
        await self._client.aclose()



class EngineRegistry:
    """세 엔진 클라이언트를 묶는 컨테이너. graph_flow.py에서 그래프 빌드 시
    각 DB 노드에 주입하는 용도로 쓴다."""

    def __init__(self, rdb: RdbEngine, graph: GraphEngine, vector: VectorEngine):
        self.rdb = rdb
        self.graph = graph
        self.vector = vector

    async def aclose(self) -> None:
        for engine in (self.rdb, self.graph, self.vector):
            aclose = getattr(engine, "aclose", None)
            if aclose is not None:
                await aclose()


def inject_results(query_template: str, upstream: dict[str, StepResult]) -> str:
    """선행 단계 결과를 쿼리 템플릿에 주입한다.

    예: RDB의 WHERE IN (...) 절에 Graph 단계에서 뽑은 후보 코드 목록을 채워 넣는다.
    쿼리 템플릿에는 {step_id} 형태의 자리표시자를 사용한다고 가정했다.
    """
    query = query_template
    for step_id, result in upstream.items():
        if not result["ok"]:
            continue
        candidates = extract_candidate_ids(result["data"])
        placeholder = f"{{{step_id}}}"
        if placeholder in query:
            in_clause = ", ".join(f"'{c}'" for c in candidates) or "NULL"
            query = query.replace(placeholder, in_clause)
    return query


def extract_candidate_ids(data: object) -> list[str]:
    """상위 단계 결과에서 다음 단계가 사용할 식별자 목록을 뽑는다.

    Graph 단계라면 SPARQL 결과 바인딩에서 ETF/채권 코드를, RDB 단계라면 select
    결과 row의 PK 컬럼을 추출하도록 실제 응답 구조에 맞춰 조정해야 한다.
    """
    if isinstance(data, list):
        return [str(row.get("id", row)) if isinstance(row, dict) else str(row) for row in data]
    return []


async def build_schema_hint(rdb: RdbEngine, schema: str = "raw") -> str:
    """실제 DB의 테이블/컬럼 목록을 조회해서 plan_routing 프롬프트에 넣을 수
    있는 텍스트로 만든다.

    RdbHttpEngine.list_tables(), list_columns()를 그대로 쓴다. 요청마다
    부르면 매 질의마다 DB 왕복이 여러 번 추가되니, 그래프를 실행하기 전에
    한 번만 호출해서 run_agent(..., schema_hint=...)로 넘기는 방식을 권장한다.
    예:
        schema_hint = await build_schema_hint(engines.rdb)
        await run_agent(..., engines=engines, schema_hint=schema_hint)

    응답 형태는 Swagger로 확인했다.
    GET /db/tables -> {"raw": ["etf_master", ...], "vec": [...]} 형태.
    스키마 이름을 키로 하는 dict라서, 그중 schema 인자로 받은 것만 쓴다.
    GET /db/columns/{schema}/{table} -> 컬럼 하나당 dict 하나로 된 리스트.
    정확한 키 이름(column_name 등)은 아직 확인 전이라 _extract_column_names가
    흔한 이름 몇 가지를 순서대로 시도한다.
    """
    tables_by_schema = await rdb.list_tables()
    table_names = tables_by_schema.get(schema, []) if isinstance(tables_by_schema, dict) else []

    lines: list[str] = []
    for table in table_names:
        try:
            raw_columns = await rdb.list_columns(schema, table)
            column_names = _extract_column_names(raw_columns)
            lines.append(f"- {schema}.{table}({', '.join(column_names)})")
        except Exception as exc:  # noqa: BLE001 - 컬럼 하나 조회 실패해도 나머지는 계속
            lines.append(f"- {schema}.{table} (컬럼 조회 실패: {exc})")

    return "\n".join(lines)


def _extract_column_names(payload: object) -> list[str]:
    """GET /db/columns/{schema}/{table} 응답에서 컬럼 이름만 뽑는다.

    각 원소가 {"column_name": ..., "data_type": ...} 같은 information_schema
    스타일 dict라고 가정하고 흔한 키 이름 몇 가지를 순서대로 시도한다.
    실제 키 이름이 다르면 이 함수만 고치면 된다.
    """
    if not isinstance(payload, list):
        return []
    names: list[str] = []
    for item in payload:
        if isinstance(item, str):
            names.append(item)
            continue
        if isinstance(item, dict):
            for key in ("column_name", "name", "column"):
                if key in item:
                    names.append(str(item[key]))
                    break
    return names