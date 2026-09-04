"""live DB 스키마 실측 스냅샷 (T-115).

이 모듈이 필요한 이유
---------------------
rdb_schema.py는 도메인 카탈로그를 파이썬 상수로 들고 있는데, 그 상수가
가리키는 테이블·컬럼이 실제 DB에 있는지는 아무도 검증하지 않았다. 그리고
2026-09-05 실측 기준으로 실제로 어긋나 있었다:

  카탈로그 주장                      live(information_schema)
  ---------------------------------  ------------------------------------
  enriched.etf_kr_enriched           없음 (enriched.etf_kr 은 있음)
  enriched.bond_kr_enriched          없음 (bond_kr_offer / bond_kr_product)
  charge_rt_final                    enriched.etf_kr 에 그런 컬럼 없음

이 어긋남이 조용히 넘어가면 SQL 생성 -> 실행 실패 -> nodes._fix_sql 재시도로
이어진다. 그런데 재시도에 넘기는 "실제 컬럼 목록"까지 같은 상수
(rdb_schema.get_full_column_list)에서 나오기 때문에, 수리 루프는 방금 실패한
것과 똑같은 오답을 근거로 다시 쓴다 - 구조적으로 수렴하지 않고 재시도 횟수만
소진한다. LLM 호출이 실패 1건당 재시도 횟수만큼 증폭되므로 서버의 분당
한도(기본 60)를 그대로 밀어 올린다.

그래서 역할을 나눈다.

  의미(설명·단위·주의사항·판매정책)  -> rdb_schema.py 의 상수가 정본
  물리적 존재(테이블·컬럼 목록)       -> 이 모듈의 live 스냅샷이 정본

둘이 어긋나면 쿼리 시점의 UndefinedTable 이 아니라 **기동 시점**에
SchemaContractError 로 죽인다. 조용한 실패보다 시끄러운 실패가 낫다.

수집 경로
---------
배포된 데이터 플랫폼 API(`RDB_API_BASE_URL`, 기본 http://40.82.145.44:8000)의
introspection 엔드포인트를 쓴다. 직접 psycopg 로 붙지 않는 이유는 두 가지다.

  1. `.env` 는 DB_HOST/DB_PORT/... 이름을 주는데 kb.build_data_platform.dsn()
     은 DATABASE_URL 또는 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE 를
     요구한다. 즉 현재 환경에서 DB 직결 경로는 RuntimeError 로 죽는다.
  2. 에이전트 런타임이 이미 같은 API 로 SQL 을 실행하고 있다. 스키마 진실을
     같은 출처에서 가져와야 "실행되는 곳"과 "검증하는 곳"이 갈라지지 않는다.

  GET /db/tables   -> information_schema.tables   (실측)
  GET /db/columns  -> information_schema.columns  (실측)
  GET /db/catalog  -> meta.column_catalog         (사람이 관리하는 의미 메타)

`/db/catalog` 는 적재된 테이블이라 물리 스키마와 어긋날 수 있다. 그래서
물리적 존재의 근거로 쓰지 않고, 의미 메타데이터로만 쓴다.

응답 상한
---------
서버는 모든 응답을 MAX_ROWS(기본 100)행에서 자르고 `truncated` 플래그를
같이 준다. `/db/columns` 를 필터 없이 부르면 100행에서 잘리므로(실측)
테이블별로 나눠 받는다. `truncated` 가 True 인 응답은 불완전한 진실이므로
스냅샷에 넣지 않고 예외를 던진다.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import requests

# rdb_schema 가 참조하는 스키마들. 서버의 introspection 엔드포인트도 같은
# 목록으로 필터링하므로 여기서 더 넓게 잡아도 의미가 없다.
KNOWN_SCHEMAS = ("meta", "raw", "enriched", "relations", "vec", "core")

DEFAULT_BASE_URL = os.environ.get("RDB_API_BASE_URL", "http://40.82.145.44:8000")
DEFAULT_TIMEOUT = float(os.environ.get("RDB_API_TIMEOUT", "30"))

# 스냅샷 캐시 위치. 공유 데이터 영역에 쓰지 않는다(AGENTS.md 규칙).
# 환경변수로 세션별 artifacts 경로를 주입할 수 있게 열어 둔다.
DEFAULT_SNAPSHOT_PATH = Path(
    os.environ.get("RDB_SCHEMA_SNAPSHOT_PATH", ".cache/schema_snapshot.json")
)

SNAPSHOT_FORMAT_VERSION = 1


class SchemaContractError(RuntimeError):
    """카탈로그 상수와 live 스키마가 어긋날 때 기동 시점에 던진다.

    이 예외가 났다는 건 "SQL 이 실패할 것"이 아니라 "이미 잘못된 전제로
    돌고 있었다"는 뜻이다. 삼키지 말 것.
    """


class SnapshotUnavailableError(RuntimeError):
    """live 스냅샷을 만들 수도, 캐시에서 읽을 수도 없을 때."""


def _request(
    path: str,
    params: Mapping[str, Any] | None = None,
    base_url: str | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    max_retries: int = 3,
) -> dict:
    """introspection 엔드포인트 GET.

    429 는 서버의 분당 한도(기본 60)에 걸린 것이다. 현재 서버는 Retry-After
    헤더를 주지 않으므로(T-119 에서 보강 예정), 헤더가 있으면 그 값을 쓰고
    없으면 슬라이딩 윈도우 길이인 60초를 보수적으로 기다린다.
    """
    url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}{path}"
    get = (session or requests).get
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = get(url, params=params, timeout=timeout or DEFAULT_TIMEOUT)
        except requests.RequestException as exc:  # 네트워크/타임아웃
            last_error = exc
            if attempt == max_retries:
                raise SnapshotUnavailableError(f"{url} 요청 실패: {exc}") from exc
            time.sleep(2**attempt)
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 60.0
            if attempt == max_retries:
                raise SnapshotUnavailableError(
                    f"{url} 분당 한도(429) 초과. {max_retries}회 대기 후에도 실패."
                )
            time.sleep(wait)
            continue

        if response.status_code != 200:
            raise SnapshotUnavailableError(
                f"{url} HTTP {response.status_code}: {response.text[:200]}"
            )

        payload = response.json()
        if payload.get("truncated"):
            # 잘린 응답은 "없는 컬럼"을 없다고 잘못 단정하게 만든다.
            raise SnapshotUnavailableError(
                f"{url} 응답이 서버 MAX_ROWS 에서 잘렸다(truncated=true). "
                "테이블 단위로 나눠 받아야 한다."
            )
        return payload

    raise SnapshotUnavailableError(f"{url} 실패: {last_error}")


def fetch_snapshot(
    base_url: str | None = None,
    timeout: float | None = None,
    pace_seconds: float = 0.2,
) -> dict:
    """live information_schema 를 읽어 스냅샷 dict 를 만든다.

    테이블 목록 1회 + 테이블당 컬럼 1회를 호출한다(2026-09-05 실측 45개
    테이블 기준 46회). 서버 한도가 분당 60이라 `pace_seconds` 로 간격을 둔다.
    """
    session = requests.Session()
    tables_payload = _request(
        "/db/tables", base_url=base_url, timeout=timeout, session=session
    )

    tables: dict[str, dict[str, Any]] = {}
    for row in tables_payload["rows"]:
        schema, name = row["table_schema"], row["table_name"]
        if schema not in KNOWN_SCHEMAS:
            continue
        tables[f"{schema}.{name}"] = {"table_type": row.get("table_type"), "columns": {}}

    for qualified in sorted(tables):
        schema, name = qualified.split(".", 1)
        payload = _request(
            "/db/columns",
            params={"table_schema": schema, "table_name": name},
            base_url=base_url,
            timeout=timeout,
            session=session,
        )
        tables[qualified]["columns"] = {
            row["column_name"]: {
                "data_type": row.get("data_type"),
                "is_nullable": row.get("is_nullable"),
                "ordinal_position": row.get("ordinal_position"),
            }
            for row in payload["rows"]
        }
        if pace_seconds:
            time.sleep(pace_seconds)

    try:
        version_payload = _request(
            "/db/version", base_url=base_url, timeout=timeout, session=session
        )
        # /db/version 은 다른 조회와 같은 봉투({columns, rows, ...})로 온다.
        # 릴리스 매니페스트는 그 안의 단일 행이므로 행만 꺼내 둔다 - 봉투째
        # 넣으면 스냅샷 diff 를 볼 때 elapsed_ms 같은 잡음이 매번 바뀐다.
        rows = version_payload.get("rows") or []
        version_stamp: dict[str, Any] = rows[0] if rows else {"unavailable": True}
    except SnapshotUnavailableError:
        # 버전 엔드포인트가 없어도 스냅샷 자체는 유효하다. 다만 어떤 배포본을
        # 봤는지 모른다는 사실은 스냅샷에 남긴다.
        version_stamp = {"unavailable": True}

    return {
        "snapshot_format_version": SNAPSHOT_FORMAT_VERSION,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_url": (base_url or DEFAULT_BASE_URL).rstrip("/"),
        "api_version": version_stamp,
        "table_count": len(tables),
        "tables": tables,
    }


def save_snapshot(snapshot: dict, path: Path | str | None = None) -> Path:
    target = Path(path or DEFAULT_SNAPSHOT_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


def load_snapshot(path: Path | str | None = None) -> dict | None:
    target = Path(path or DEFAULT_SNAPSHOT_PATH)
    if not target.exists():
        return None
    snapshot = json.loads(target.read_text(encoding="utf-8"))
    if snapshot.get("snapshot_format_version") != SNAPSHOT_FORMAT_VERSION:
        # 포맷이 바뀌었으면 캐시를 신뢰하지 않는다.
        return None
    return snapshot


_CACHED: dict | None = None


def get_snapshot(
    refresh: bool = False,
    path: Path | str | None = None,
    base_url: str | None = None,
) -> dict:
    """스냅샷을 얻는다. 프로세스 캐시 -> 디스크 캐시 -> live fetch 순."""
    global _CACHED
    if _CACHED is not None and not refresh:
        return _CACHED
    if not refresh:
        cached = load_snapshot(path)
        if cached is not None:
            _CACHED = cached
            return _CACHED
    snapshot = fetch_snapshot(base_url=base_url)
    save_snapshot(snapshot, path)
    _CACHED = snapshot
    return snapshot


def table_exists(qualified_name: str, snapshot: Mapping[str, Any]) -> bool:
    return qualified_name in snapshot["tables"]


def column_exists(
    qualified_name: str, column: str, snapshot: Mapping[str, Any]
) -> bool:
    table = snapshot["tables"].get(qualified_name)
    return bool(table) and column in table["columns"]


def get_columns(qualified_name: str, snapshot: Mapping[str, Any]) -> list[str]:
    table = snapshot["tables"].get(qualified_name)
    if table is None:
        raise SchemaContractError(f"{qualified_name} 이(가) live 스키마에 없다.")
    return sorted(
        table["columns"],
        key=lambda c: table["columns"][c].get("ordinal_position") or 0,
    )


def resolve_table(candidates: Iterable[str], snapshot: Mapping[str, Any]) -> str:
    """후보 중 실제로 존재하는 첫 테이블을 고른다.

    테이블이 개명됐을 때(etf_kr_enriched -> etf_kr) 카탈로그에 후보를
    나열해 두면 이 함수가 live 기준으로 하나를 고른다. 하나도 없으면
    조용히 넘어가지 않고 SchemaContractError 를 던진다.
    """
    candidates = list(candidates)
    for name in candidates:
        if table_exists(name, snapshot):
            return name
    raise SchemaContractError(
        f"후보 테이블이 전부 live 에 없다: {', '.join(candidates)}"
    )


def assert_contract(
    table_refs: Iterable[str] = (),
    column_refs: Iterable[tuple[str, str]] = (),
    snapshot: Mapping[str, Any] | None = None,
) -> None:
    """카탈로그가 참조하는 테이블·컬럼이 live 에 전부 있는지 확인한다.

    하나라도 없으면 전부 모아서 SchemaContractError 를 던진다. 첫 번째에서
    끊지 않는 이유는, 드리프트가 보통 한 건이 아니라 무더기로 나기 때문이다
    (2026-09-05 실측에서도 2개 테이블 + 1개 컬럼이 동시에 어긋나 있었다).
    """
    snap = snapshot if snapshot is not None else get_snapshot()
    problems: list[str] = []

    for ref in table_refs:
        if not table_exists(ref, snap):
            problems.append(f"테이블 없음: {ref}")

    for qualified, column in column_refs:
        if not table_exists(qualified, snap):
            problems.append(f"테이블 없음: {qualified} (컬럼 {column} 확인 불가)")
        elif not column_exists(qualified, column, snap):
            problems.append(f"컬럼 없음: {qualified}.{column}")

    if problems:
        raise SchemaContractError(
            "카탈로그와 live 스키마가 어긋난다(기동 중단):\n  - "
            + "\n  - ".join(problems)
            + f"\n스냅샷 기준시각: {snap.get('fetched_at')} / 출처: {snap.get('source_url')}"
        )
