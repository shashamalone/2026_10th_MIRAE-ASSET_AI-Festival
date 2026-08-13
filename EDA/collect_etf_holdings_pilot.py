"""ETF PDF(구성종목) 시범 수집 — 순자산 상위 N종.

전제: KRX 정보데이터시스템이 2026년부터 로그인을 요구한다.
    export KRX_ID=... KRX_PW=...   (KRX 회원 계정)
없으면 pykrx가 "KRX 로그인 실패"를 출력하고 모든 요청이 JSONDecodeError로 실패한다.

ISIN은 마스터 CSV의 pd_itm_no를 그대로 쓴다(pykrx의 티커→ISIN 조회도 로그인 필요라 우회).
"""

import sys
import time
from pathlib import Path

import pandas as pd
from pykrx.website.krx.etx.core import PDF

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data/csv/PREF01N001_etf_kr_master_20260711.csv"
OUT = ROOT / "data/relations/etf_holding_pilot.csv"

TOP_N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
# 대회 규칙: 2026-07-11 이전 데이터만. 첫 종목으로 조회 가능한 최신 일자를 탐색한다.
DATES = ["20260710", "20260709", "20260708", "20260707", "20260703", "20260630", "20260529"]


def top_etfs(n):
    df = pd.read_csv(MASTER, dtype=str, keep_default_na=False)
    df = df[df.pd_grp_no == "ETF"].copy()
    df["_nav"] = pd.to_numeric(df.pd_net_tamt, errors="coerce")
    return df.sort_values("_nav", ascending=False).head(n)


def fetch(isin, date):
    """비었거나 예외면 빈 DataFrame."""
    try:
        return PDF().fetch(date, isin)
    except Exception as e:  # noqa: BLE001 - 종목 하나 실패로 전체가 죽으면 안 됨
        print(f"    ERR {type(e).__name__}: {str(e)[:120]}")
        return pd.DataFrame()


def main():
    etfs = top_etfs(TOP_N)
    print(f"대상 {len(etfs)}종")

    # 1) 조회 가능한 최신 일자 탐색 (첫 종목 기준)
    probe = etfs.iloc[0]
    as_of = None
    for d in DATES:
        print(f"  일자 탐색 {d} ...")
        if len(fetch(probe.pd_itm_no, d)):
            as_of = d
            break
        time.sleep(1)
    if as_of is None:
        print(f"조회 가능한 일자를 찾지 못함 (시도: {DATES}). KRX_ID/KRX_PW 확인 필요.")
        return 1
    print(f"기준일자 = {as_of}")

    # 2) 수집
    rows, failed = [], []
    t0 = time.time()
    for _, e in etfs.iterrows():
        ticker = e.pd_itm_no_ma[1:]  # A069500 -> 069500
        t = time.time()
        df = fetch(e.pd_itm_no, as_of)
        if not len(df):
            failed.append((ticker, e.pd_nm))
            continue
        df = df.assign(
            pd_itm_no=e.pd_itm_no, ticker=ticker, etf_name=e.pd_nm, as_of=as_of, source="KRX/pykrx"
        ).rename(
            columns={
                "COMPST_ISU_CD": "holding_code",
                "COMPST_ISU_NM": "holding_name",
                "COMPST_RTO": "weight",
            }
        )
        rows.append(df)
        print(f"  {ticker} {e.pd_nm[:30]}: {len(df)}행 ({time.time() - t:.1f}s)")
        time.sleep(1)

    elapsed = time.time() - t0
    print(f"\n성공 {len(rows)} / 실패 {len(failed)} / {elapsed:.1f}s "
          f"(종목당 {elapsed / max(len(etfs), 1):.1f}s)")
    for tk, nm in failed:
        print(f"  실패: {tk} {nm}")
    if not rows:
        return 1

    cols = ["pd_itm_no", "ticker", "etf_name", "holding_code", "holding_name", "weight",
            "as_of", "source"]
    out = pd.concat(rows, ignore_index=True)
    out = out[[c for c in cols if c in out.columns]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"저장: {OUT} ({len(out)}행)")
    print(out.head(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
