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

SNAPSHOT_FORMAT_VERSION = 2

# [SCHEMA-003] 캐시 신선도. 스냅샷은 "그때의 DB"라서 재배포가 있으면 조용히
# 낡는다. 나이 제한과 release_id 결속을 둘 다 건다 - 나이만 보면 같은 시각에
# 배포가 바뀐 경우를 놓치고, release 만 보면 네트워크가 죽었을 때 무한히
# 낡은 캐시를 쓴다.
SNAPSHOT_MAX_AGE_SECONDS = float(os.environ.get("RDB_SCHEMA_SNAPSHOT_MAX_AGE", "3600"))

# [SCHEMA-005] 429 대기 상한. 서버 윈도우가 60초지만, 기동 경로에서 60초씩
# 무한정 멈춰 서면 운영상 장애와 구분되지 않는다. 총 대기 시간을 묶는다.
RATE_LIMIT_WAIT_SECONDS = float(os.environ.get("RDB_API_RATE_LIMIT_WAIT", "60"))
RATE_LIMIT_TOTAL_WAIT_BUDGET = float(os.environ.get("RDB_API_RATE_LIMIT_BUDGET", "120"))

# 운영 API는 같은 컨테이너의 loopback Data API를 사용하므로 기본 대기는 없다.
# 인증 없는 원격 공개 API에 직접 붙이는 별도 도구만 필요할 때 환경변수로
# 1.05초 등을 명시한다. 원격 429는 아래의 제한 응답 처리기가 담당한다.
DEFAULT_PACE_SECONDS = float(os.environ.get("RDB_SCHEMA_SNAPSHOT_PACE", "0"))


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
    wait_on_rate_limit: bool = False,
) -> dict:
    """introspection 엔드포인트 GET.

    429 처리는 호출 맥락에 따라 다르다.

    - `wait_on_rate_limit=False`(기본): Retry-After 가 없으면 **기다리지 않고
      즉시 실패**한다. 기동 경로에서 헤더 없는 429 에 60초씩 멈춰 서면
      장애와 구분되지 않고, 얼마나 기다려야 하는지는 순전히 추측이다.
    - `wait_on_rate_limit=True`: 스냅샷 수집처럼 원래 수십 번을 호출하는
      배치 작업용. 서버 윈도우가 60초로 알려져 있으므로 헤더가 없어도 그만큼
      기다린다. 총 대기는 RATE_LIMIT_TOTAL_WAIT_BUDGET 으로 묶는다.
    """
    url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}{path}"
    get = (session or requests).get
    last_error: Exception | None = None
    waited = 0.0

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
            if retry_after and retry_after.strip().isdigit():
                wait = float(retry_after)
            elif wait_on_rate_limit:
                # 배치 수집: 헤더가 없어도 알려진 윈도우 길이만큼 기다린다.
                wait = RATE_LIMIT_WAIT_SECONDS
            else:
                raise SnapshotUnavailableError(
                    f"{url} 분당 한도(429)이고 Retry-After 헤더가 없다. "
                    "얼마나 기다려야 할지 알 수 없어 즉시 중단한다"
                    "(서버가 Retry-After 를 주도록 보강 필요 - T-119)."
                )
            if attempt == max_retries or waited + wait > RATE_LIMIT_TOTAL_WAIT_BUDGET:
                raise SnapshotUnavailableError(
                    f"{url} 분당 한도(429). 총 대기 예산"
                    f"({RATE_LIMIT_TOTAL_WAIT_BUDGET:.0f}s) 안에서 통과하지 못했다."
                )
            waited += wait
            time.sleep(wait)
            continue

        if response.status_code != 200:
            raise SnapshotUnavailableError(
                f"{url} HTTP {response.status_code}: {response.text[:200]}"
            )

        payload = response.json()

        # [SCHEMA-002] fail-closed. "잘리지 않았다"는 명시적으로 False 여야
        # 인정한다. 필드가 없거나 None/0/"false" 같은 falsy 값이면 "잘렸는지
        # 알 수 없다"이고, 모르는 상태로 스키마 진실을 만들면 실제로는 있는
        # 컬럼을 없다고 단정하게 된다.
        if payload.get("truncated") is not False:
            raise SnapshotUnavailableError(
                f"{url} 응답의 truncated 가 False 가 아니다"
                f"(값: {payload.get('truncated')!r}). 잘렸거나, 잘림 여부를 "
                "확인할 수 없다. 기대 형식: "
                "{columns, rows, row_count, truncated, elapsed_ms}"
            )
        if not isinstance(payload.get("rows"), list):
            raise SnapshotUnavailableError(
                f"{url} 응답의 rows 가 리스트가 아니다"
                f"(타입: {type(payload.get('rows')).__name__}). 서버 계약 확인 필요."
            )
        return payload

    raise SnapshotUnavailableError(f"{url} 실패: {last_error}")


def _release_id_of(version_payload: Mapping[str, Any]) -> str | None:
    """/db/version 봉투에서 release_id 만 꺼낸다."""
    rows = version_payload.get("rows") or []
    return rows[0].get("release_id") if rows else None


def fetch_snapshot(
    base_url: str | None = None,
    timeout: float | None = None,
    pace_seconds: float | None = None,
) -> dict:
    """live information_schema 를 읽어 스냅샷 dict 를 만든다.

    호출 수는 (version 2회 + tables 1회 + 테이블당 columns 1회)다. 운영
    경로는 같은 컨테이너의 loopback API라 페이싱하지 않는다. 별도의 원격
    공개 API를 대상으로 수집할 때만 ``RDB_SCHEMA_SNAPSHOT_PACE``를 설정한다.
    """
    session = requests.Session()
    if pace_seconds is None:
        pace_seconds = DEFAULT_PACE_SECONDS

    # [race] 46회를 호출하는 동안 재배포가 일어나면 앞부분과 뒷부분이 서로
    # 다른 배포본에서 온 잡종 스냅샷이 된다. 시작과 끝의 release_id 가 같은지
    # 확인해 그 창을 닫는다.
    release_before = _release_id_of(
        _request(
            "/db/version", base_url=base_url, timeout=timeout, session=session,
            wait_on_rate_limit=True,
        )
    )
    if not release_before:
        raise SnapshotUnavailableError(
            "/db/version 이 release_id 를 주지 않았다. 스냅샷의 출처를 특정할 수 "
            "없으므로 스냅샷을 만들지 않는다."
        )

    tables_payload = _request(
        "/db/tables", base_url=base_url, timeout=timeout, session=session,
        wait_on_rate_limit=True,
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
            wait_on_rate_limit=True,
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

    # [SCHEMA-004] release 정보를 옵션으로 두지 않는다. 어떤 배포본을 보고
    # 만든 스냅샷인지 모르면 나중에 신선도를 판단할 근거가 없고, 결국 낡은
    # 스냅샷을 낡은 줄 모르고 쓰게 된다. 여기서 실패하면 스냅샷을 만들지
    # 않는다(실패를 삼키지 않는다).
    # /db/version 은 다른 조회와 같은 봉투({columns, rows, ...})로 온다.
    # 릴리스 매니페스트는 그 안의 단일 행이므로 행만 꺼내 둔다 - 봉투째
    # 넣으면 스냅샷 diff 를 볼 때 elapsed_ms 같은 잡음이 매번 바뀐다.
    version_payload = _request(
        "/db/version", base_url=base_url, timeout=timeout, session=session,
        wait_on_rate_limit=True,
    )
    release_after = _release_id_of(version_payload)
    if not release_after:
        raise SnapshotUnavailableError(
            "/db/version 이 release_id 를 주지 않았다. 스냅샷의 출처를 특정할 수 "
            "없으므로 스냅샷을 만들지 않는다."
        )
    if release_after != release_before:
        # 수집 도중 배포가 바뀌었다. 앞뒤가 다른 배포본에서 온 잡종이므로 버린다.
        raise SnapshotUnavailableError(
            "스냅샷 수집 중 배포본이 바뀌었다"
            f"(시작 {release_before} -> 종료 {release_after}). "
            "잡종 스냅샷을 만들지 않고 중단한다. 다시 수집할 것."
        )
    version_stamp: dict[str, Any] = version_payload["rows"][0]

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


def snapshot_release_id(snapshot: Mapping[str, Any]) -> str | None:
    return (snapshot.get("api_version") or {}).get("release_id")


def snapshot_age_seconds(snapshot: Mapping[str, Any]) -> float:
    fetched = snapshot.get("fetched_at")
    if not fetched:
        return float("inf")
    try:
        stamp = datetime.fromisoformat(fetched)
    except ValueError:
        return float("inf")
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def load_snapshot(
    path: Path | str | None = None,
    max_age_seconds: float | None = None,
) -> dict | None:
    """디스크 캐시를 읽는다. 포맷이 다르거나 너무 낡았으면 None."""
    target = Path(path or DEFAULT_SNAPSHOT_PATH)
    if not target.exists():
        return None
    snapshot = json.loads(target.read_text(encoding="utf-8"))
    if snapshot.get("snapshot_format_version") != SNAPSHOT_FORMAT_VERSION:
        # 포맷이 바뀌었으면 캐시를 신뢰하지 않는다.
        return None
    limit = SNAPSHOT_MAX_AGE_SECONDS if max_age_seconds is None else max_age_seconds
    if limit is not None and snapshot_age_seconds(snapshot) > limit:
        # [SCHEMA-003] 낡은 캐시는 없느니만 못하다 - 조용히 틀린 진실이 된다.
        return None
    return snapshot


def live_release_id(
    base_url: str | None = None, timeout: float | None = None
) -> str | None:
    """배포본의 현재 release_id 를 1회 조회한다(캐시 결속 확인용)."""
    payload = _request("/db/version", base_url=base_url, timeout=timeout)
    rows = payload.get("rows") or []
    return rows[0].get("release_id") if rows else None


_CACHED: dict | None = None
# 검증 사실은 "어느 캐시 경로 / 어느 서버에 대해" 확인했는지와 함께 기억한다.
# 전역 불리언 하나로 두면 base_url 이나 path 를 바꿔 호출했을 때 엉뚱한
# 검증 결과를 재사용하게 된다.
_RELEASE_VERIFIED_FOR: tuple[str, str] | None = None


def _cache_key(path: Path | str | None, base_url: str | None) -> tuple[str, str]:
    return (
        str(Path(path or DEFAULT_SNAPSHOT_PATH)),
        (base_url or DEFAULT_BASE_URL).rstrip("/"),
    )


def get_snapshot(
    refresh: bool = False,
    path: Path | str | None = None,
    base_url: str | None = None,
    verify_release: bool = True,
    max_age_seconds: float | None = None,
) -> dict:
    """스냅샷을 얻는다. 프로세스 캐시 -> 디스크 캐시 -> live fetch 순.

    [SCHEMA-003] 캐시를 쓸 때는 나이(TTL)와 release_id 를 둘 다 본다. 나이만
    보면 TTL 안에 일어난 재배포를 놓치고, release 만 보면 서버가 응답하지
    않을 때 낡은 캐시를 무한정 쓰게 된다.

    프로세스 캐시에도 TTL 을 적용한다 - 오래 사는 프로세스(노트북 커널,
    서버 워커)가 낡은 스냅샷을 영원히 붙잡는 것을 막는다.

    release 확인이 불가능하면(엔드포인트가 release_id 를 주지 않으면) 검증된
    것으로 취급하지 않고 실패시킨다. 출처를 모르는 스냅샷을 "확인됨"으로
    바꿔 놓으면 이 모듈이 하려던 일과 정반대가 된다.

    verify_release=False 는 오프라인 도구용 탈출구다. 런타임 경로에서는 쓰지
    말 것.
    """
    global _CACHED, _RELEASE_VERIFIED_FOR

    key = _cache_key(path, base_url)
    limit = SNAPSHOT_MAX_AGE_SECONDS if max_age_seconds is None else max_age_seconds

    if refresh:
        snapshot = fetch_snapshot(base_url=base_url)
        save_snapshot(snapshot, path)
        _CACHED, _RELEASE_VERIFIED_FOR = snapshot, key
        return snapshot

    candidate = _CACHED
    if candidate is not None and limit is not None:
        # 프로세스 캐시도 늙는다.
        if snapshot_age_seconds(candidate) > limit:
            candidate = None
    if candidate is None:
        candidate = load_snapshot(path, max_age_seconds)

    if candidate is not None and verify_release and _RELEASE_VERIFIED_FOR != key:
        current = live_release_id(base_url=base_url)
        if not current:
            raise SnapshotUnavailableError(
                "/db/version 이 release_id 를 주지 않아 캐시된 스냅샷이 현재 "
                "배포본과 같은지 확인할 수 없다. 확인되지 않은 스냅샷으로 "
                "스키마 계약을 판정하지 않는다."
            )
        if current != snapshot_release_id(candidate):
            # 배포본이 바뀌었다. 낡은 스냅샷으로 계약을 판정하면 "있는 컬럼을
            # 없다"고 하거나 그 반대가 된다 - 다시 받는다.
            candidate = None
        else:
            _RELEASE_VERIFIED_FOR = key

    if candidate is not None:
        _CACHED = candidate
        return candidate

    snapshot = fetch_snapshot(base_url=base_url)
    save_snapshot(snapshot, path)
    _CACHED, _RELEASE_VERIFIED_FOR = snapshot, key
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
