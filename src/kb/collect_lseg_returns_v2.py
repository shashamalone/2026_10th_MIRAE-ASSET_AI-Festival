# -*- coding: utf-8 -*-
"""LSEG Platform OAuth + get_history로 해외ETF 1년 조정수익률을 수집한다.

권한상 조정가격을 받을 수 없으면 단순 종가로 대체하지 않고 미확보로 기록한다.
자격증명은 환경변수로만 받으며 출력 JSONL은 ``artifacts/`` 아래에 둔다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.build_data_platform_v2 import SCHEMAS, dsn  # noqa: E402
from kb.v2_manifest import EXTERNAL_CUTOFF, ROOT  # noqa: E402

START_DATE = date(2025, 8, 24)
END_DATE = EXTERNAL_CUTOFF
OUTPUT = ROOT / "artifacts" / "lseg_return_1y_20260824.jsonl"
ADJUSTMENTS = [
    "exchangeCorrection",
    "manualCorrection",
    "CCH",
    "CRE",
    "RPO",
    "RTS",
]


def credentials() -> dict[str, str]:
    names = ("LSEG_APP_KEY", "LSEG_CLIENT_ID", "LSEG_CLIENT_SECRET")
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError("LSEG Platform OAuth 환경변수 누락: " + ", ".join(missing))
    return values


def target_products(limit: int) -> list[tuple[str, str]]:
    explicit = [value.strip() for value in os.environ.get("LSEG_RICS", "").split(",") if value.strip()]
    with psycopg.connect(dsn()) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        if explicit:
            return list(
                conn.execute(
                    f"SELECT product_id,source_key FROM {SCHEMAS['ENRICHED']}.product_master "
                    "WHERE product_type='ETF_GL' AND source_key = ANY(%s) ORDER BY source_key",
                    (explicit,),
                ).fetchall()
            )
        return list(
            conn.execute(
                f"""
                SELECT product_id, source_key
                FROM {SCHEMAS['ENRICHED']}.product_master p
                LEFT JOIN {SCHEMAS['ENRICHED']}.product_search s USING (product_id)
                WHERE product_type='ETF_GL'
                ORDER BY s.aum DESC NULLS LAST, source_key
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        )


def open_platform_session():
    values = credentials()
    import lseg.data as ld
    from lseg.data import session

    definition = session.platform.Definition(
        app_key=values["LSEG_APP_KEY"],
        app_secret=values["LSEG_CLIENT_SECRET"],
        client_id=session.platform.ClientCredentials(
            client_id=values["LSEG_CLIENT_ID"],
            client_secret=values["LSEG_CLIENT_SECRET"],
        ),
        signon_control=True,
    )
    platform_session = definition.get_session()
    platform_session.open()
    try:
        session.set_default(platform_session)
    except AttributeError:
        # 라이브러리 버전에 따라 최상위 helper에 노출된다.
        ld.session.set_default(platform_session)
    return ld, platform_session


def adjusted_return(ld, ric: str) -> dict[str, object]:
    base = {
        "ric": ric,
        "metric_code": "RETURN_1Y",
        "unit": "percent",
        "as_of": END_DATE.isoformat(),
        "source": "LSEG",
        "source_column": "TRDPRC_1 adjusted",
        "method": "lseg_get_history_adjusted_price_return",
        "source_priority": 2,
    }
    try:
        frame = ld.get_history(
            universe=[ric],
            fields=["TRDPRC_1"],
            interval="1D",
            start=START_DATE.isoformat(),
            end=END_DATE.isoformat(),
            adjustments=ADJUSTMENTS,
        )
        if frame is None or frame.empty:
            return {**base, "value": None, "is_available": False, "unavailable_reason": "NO_ADJUSTED_HISTORY"}
        series = frame.iloc[:, 0].dropna()
        if len(series) < 2:
            return {**base, "value": None, "is_available": False, "unavailable_reason": "INSUFFICIENT_ADJUSTED_HISTORY"}
        first, last = float(series.iloc[0]), float(series.iloc[-1])
        if first == 0:
            return {**base, "value": None, "is_available": False, "unavailable_reason": "ZERO_START_VALUE"}
        return {
            **base,
            "value": (last / first - 1.0) * 100.0,
            "is_available": True,
            "unavailable_reason": None,
            "observation_start": str(series.index[0])[:10],
            "observation_end": str(series.index[-1])[:10],
        }
    except Exception as exc:
        # 오류 본문에 토큰은 포함하지 않지만 길이는 제한한다. 필드 권한/상품 미존재를
        # 미확보로 남기고 종가·현재가 등 다른 축으로 조용히 대체하지 않는다.
        return {
            **base,
            "value": None,
            "is_available": False,
            "unavailable_reason": f"ADJUSTED_FIELD_UNAVAILABLE:{type(exc).__name__}:{str(exc)[:160]}",
        }


def collect(limit: int, output: Path) -> dict[str, object]:
    targets = target_products(limit)
    ld, platform_session = open_platform_session()
    records: list[dict[str, object]] = []
    try:
        for product_id, ric in targets:
            records.append({"product_id": product_id, **adjusted_return(ld, ric)})
    finally:
        platform_session.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "targets": len(targets),
        "available": sum(bool(record["is_available"]) for record in records),
        "unavailable": sum(not bool(record["is_available"]) for record in records),
        "output": str(output),
        "start": START_DATE.isoformat(),
        "end": END_DATE.isoformat(),
        "plain_close_fallback": False,
    }


def check(limit: int) -> dict[str, object]:
    targets = target_products(limit)
    return {
        "mode": "check",
        "mutated_files": False,
        "mutated_database": False,
        "target_count": len(targets),
        "start": START_DATE.isoformat(),
        "end": END_DATE.isoformat(),
        "adjustments": ADJUSTMENTS,
        "plain_close_fallback": False,
        "credentials_configured": all(
            os.environ.get(name) for name in ("LSEG_APP_KEY", "LSEG_CLIENT_ID", "LSEG_CLIENT_SECRET")
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="LSEG 해외ETF 1년 조정수익률 수집")
    parser.add_argument("--limit", type=int, default=100, help="AUM 상위 대상 수")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true", help="API 호출/파일 쓰기 없이 대상·설정만 확인")
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("--limit은 1 이상이어야 합니다")
    result = check(args.limit) if args.check else collect(args.limit, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
