"""
ETF 편입내역의 출처 문서를 답변 조립 시점에 붙여 주는 조회 모듈.

[왜 필요한가]
골드셋 22번은 "ETF명·티커·편입비중·편입기준일·**편입내역 문서명과 근거 문장**"을
요구한다. 앞의 넷은 그래프에 있다(`fp:weight`, `fp:asOf`, 47,016 Holding).
없는 것은 **문서명과 URL** 뿐인데, 그래프의 `fp:sourceId` 에는 운용사 브랜드명
("KODEX", "TIGER", "RISE", "ACE")만 들어 있다.

문서명·URL 은 수집 당시 사이드카에 기록돼 있고, 그것을
`metadata/etf_holdings_provenance.json`(711건)으로 뽑아 뒀다. 배포된 Oxigraph 가
읽기 전용(`/update` 403)이라 트리플을 새로 넣을 수 없으므로, 그래프를 다시 쌓는
대신 답변 조립 시점에 조인한다.

[매칭 방식]
그래프 행에 어떤 컬럼명으로 ETF 가 실려 오는지는 질의마다 다르다. 그래서 컬럼명을
가정하지 않고 행의 모든 문자열 값을 인덱스와 대조한다. 우선순위는
티커(정확) > ISIN(정확) > 상품명(정규화 후 포함) 이다.

상품명 매칭에 포함 관계를 쓰는 이유: 그래프의 `fp:productName` 은 정식 명칭
("미래에셋 TIGER 차이나반도체FACTSET증권상장지수투자신탁(주식-파생형)")이고 사이드카
`name` 은 통칭("TIGER 차이나반도체FACTSET")이라 정확 일치가 성립하지 않는다.
실측으로 캠브리콘 편입 14건 중 13건이 이 방식으로 붙었다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_INDEX_PATH = Path(__file__).resolve().parents[2] / "metadata" / "etf_holdings_provenance.json"

# 상품명 비교 전에 지우는 문자: 공백과 괄호류. 운용사마다 띄어쓰기와 괄호
# 표기가 달라서 이걸 남겨 두면 같은 상품이 안 붙는다.
_NOISE = re.compile(r"[\s\[\]()·\-]")

# 티커로 오해하기 쉬운 짧은 문자열을 걸러내기 위한 최소 길이. 국내 ETF 티커는
# 6자리다(예: 396520, 0164G0).
_MIN_TICKER_LEN = 6


def _norm(text: object) -> str:
    return _NOISE.sub("", str(text or "")).upper()


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, dict], dict[str, dict], tuple[tuple[str, dict], ...]]:
    """(티커 인덱스, ISIN 인덱스, 정규화 상품명 목록)을 돌려준다.

    인덱스 파일이 없으면 빈 인덱스를 돌려준다 - 출처를 못 붙이는 것은
    답변을 막을 사유가 아니다. 근거가 없으면 그 사실만 조용히 빠진다.
    """
    if not _INDEX_PATH.exists():
        return {}, {}, ()

    try:
        payload = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, {}, ()

    entries = payload.get("entries") or {}
    by_ticker: dict[str, dict] = {}
    by_isin: dict[str, dict] = {}
    by_name: list[tuple[str, dict]] = []

    for entry in entries.values():
        ticker = str(entry.get("ticker") or "").strip().upper()
        if ticker:
            by_ticker[ticker] = entry
        isin = str(entry.get("isin") or "").strip().upper()
        if isin:
            by_isin[isin] = entry
        name_key = _norm(entry.get("name"))
        if name_key:
            by_name.append((name_key, entry))

    # 긴 이름부터 대조해야 "ACE 200" 이 "ACE 200TR" 을 가로채지 않는다.
    by_name.sort(key=lambda pair: len(pair[0]), reverse=True)
    return by_ticker, by_isin, tuple(by_name)


def clear_cache() -> None:
    """인덱스를 다시 읽게 한다(테스트용)."""
    _load.cache_clear()


def lookup(*, ticker: str | None = None, isin: str | None = None, name: str | None = None) -> dict | None:
    """티커 > ISIN > 상품명 순으로 출처를 찾는다."""
    by_ticker, by_isin, by_name = _load()

    if ticker:
        hit = by_ticker.get(str(ticker).strip().upper())
        if hit:
            return hit
    if isin:
        hit = by_isin.get(str(isin).strip().upper())
        if hit:
            return hit
    if name:
        target = _norm(name)
        if target:
            for name_key, entry in by_name:
                if name_key in target or target in name_key:
                    return entry
    return None


def find_for_row(row: dict[str, Any]) -> dict | None:
    """그래프 결과 행 하나에서 출처를 찾는다. 컬럼명을 가정하지 않는다."""
    by_ticker, by_isin, _ = _load()
    if not by_ticker and not by_isin:
        return None

    values = [str(v).strip() for v in row.values() if isinstance(v, (str, int)) and str(v).strip()]

    # 1순위: 티커 정확 일치
    for value in values:
        if len(value) >= _MIN_TICKER_LEN:
            hit = by_ticker.get(value.upper())
            if hit:
                return hit
    # 2순위: ISIN 정확 일치
    for value in values:
        hit = by_isin.get(value.upper())
        if hit:
            return hit
    # 3순위: 상품명 포함
    for value in values:
        if len(value) < 4:
            continue
        hit = lookup(name=value)
        if hit:
            return hit
    return None


def find_for_rows(rows: list[dict[str, Any]], *, limit: int = 5) -> list[dict]:
    """행 목록에서 출처를 모은다. 같은 문서는 한 번만 담고 순서를 지킨다."""
    found: list[dict] = []
    seen: set[str] = set()
    for row in rows or []:
        if len(found) >= limit:
            break
        entry = find_for_row(row) if isinstance(row, dict) else None
        if not entry:
            continue
        key = entry.get("url") or entry.get("ticker") or ""
        if key in seen:
            continue
        seen.add(key)
        found.append(entry)
    return found


def citation(entry: dict) -> str:
    """답변 근거로 인용할 한 줄. 문서명과 기준일이 핵심이고 URL 이 검증 경로다."""
    name = entry.get("name") or entry.get("ticker") or "ETF"
    document = entry.get("document") or "편입내역"
    as_of = entry.get("as_of") or "기준일 미상"
    url = entry.get("url") or ""
    line = f"{name} 편입내역 - {document}, 기준일 {as_of}"
    if entry.get("holdings_count"):
        line += f", {entry['holdings_count']}종목"
    if url:
        line += f" ({url})"
    return line


def describe_rows(rows: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    """`_build_retrieved_context` 가 그대로 붙일 수 있는 인용 문자열 목록."""
    return [citation(entry) for entry in find_for_rows(rows, limit=limit)]
