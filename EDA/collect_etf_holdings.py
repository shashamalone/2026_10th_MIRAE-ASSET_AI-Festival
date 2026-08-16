"""국내 ETF 편입종목 스냅샷 수집 (KODEX/TIGER/RISE/ACE, as_of=2026-07-10).

설계: docs_data_collection/HOLDINGS_COLLECTION_DESIGN.md
원본을 data/external/etf_kr_holdings/{brand}_{ticker}_{as_of}.{ext} + 사이드카로 저장한다.
브랜드별 어댑터는 list_products / url / parse 3함수뿐이고 나머지 파이프라인은 공유한다.

    python3 EDA/collect_etf_holdings.py        # 전량
    python3 EDA/collect_etf_holdings.py 3      # 브랜드당 3종 시범
    COLLECT_SLEEP=2 python3 EDA/collect_etf_holdings.py KODEX   # 한 브랜드만 천천히 재시도

parse()는 build_etf_holding.py가 재사용한다(원본 → 행 변환 로직 중복 방지).
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data/csv/PREF01N001_etf_kr_master_20260711.csv"
OUTDIR = ROOT / "data/external/etf_kr_holdings"
AS_OF = "2026-07-10"
YMD = AS_OF.replace("-", "")
DOT = AS_OF.replace("-", ".")
SLEEP = float(os.environ.get("COLLECT_SLEEP", 0.3))  # 429를 맞으면 늘려서 재실행(받은 파일은 건너뛴다)
# 429는 레이트리밋이라 기다리면 풀린다. COLLECT_BACKOFF>0이면 중단 대신 그만큼 쉬었다 같은 종목을 재시도한다.
BACKOFF = float(os.environ.get("COLLECT_BACKOFF", 0))
MAX_RETRY = int(os.environ.get("COLLECT_MAX_RETRY", 5))
UA = {"User-Agent": "Mozilla/5.0 (research; one-off snapshot)",
      "Accept": "*/*", "Accept-Language": "ko-KR,ko;q=0.9"}


def get(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r


def cells(tr):
    """<tr> 조각 → 셀 텍스트 리스트"""
    return [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]


# ── KODEX (삼성) : 내부 fId 매핑 필요, JSON ───────────────────────────────
def kodex_list():
    m = {}
    for p in range(1, 13):
        url = ("https://www.samsungfund.com/api/v1/kodex/product.do"
               f"?ordrColm=LIST_D&ordrSort=DESC&pageNo={p}&srchTerm=w&pageRows=20")
        for it in get(url).json():
            m[it["stkTicker"]] = it["fId"]
        time.sleep(SLEEP)
    return m


def kodex_parse(b):
    pdf = json.loads(b)["pdf"]
    if pdf.get("gijunYMD") not in (YMD, None):  # 요청 일자와 응답 기준일 대조
        raise ValueError(f"기준일 불일치 {pdf.get('gijunYMD')}")
    # 드롭: curp(현재가)·risep(등락) = 룩어헤드, applyQ·evalA = 스키마 제외
    return [(x["itmNo"], x["secNm"], x["ratio"]) for x in (pdf.get("list") or [])]


# ── TIGER (미래에셋) : ISIN 직결, HTML <tr> 조각 ──────────────────────────
def tiger_parse(b):
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", b.decode("utf-8", "replace"), re.S):
        c = cells(tr)
        if len(c) >= 5 and c[0]:
            out.append((c[0], c[1], c[4]))  # 드롭: c[2]수량 c[3]평가금액 c[5]등락률(룩어헤드)
    return out


# ── RISE (KB) : 내부 4자리 ID 매핑 필요, HTML table(.xls 위장) ────────────
def rise_list():
    m, page = {}, 1
    while page <= 40:
        h = get(f"https://www.riseetf.co.kr/prod/document/pdf?searchDate={AS_OF}&page={page}").text
        cards = h.split('class="card_type07"')[1:]
        if not cards:
            break
        for card in cards:
            t = re.search(r'<p class="title">(.*?)</p>', card, re.S)
            i = re.search(r"searchTargetId=([0-9A-Za-z]+)", card)
            code = re.findall(r"\(([0-9A-Z]{6})\)", re.sub(r"<[^>]+>", "", t.group(1))) if t else []
            if code and i:
                m[code[-1]] = i.group(1)
        page += 1
        time.sleep(SLEEP)
    return m


def rise_parse(b):
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", b.decode("utf-8", "replace"), re.S):
        c = cells(tr)
        # 레이아웃: 여백 | No | 종목코드(12자리) | 종목명 | 수량 | 보유비중 | 평가금액(항상 -)
        # 채권 ETF는 종목명이 빈 셀이라 빈 셀을 걸러내면 컬럼이 밀린다 → 종목코드 위치를 앵커로 잡는다
        i = next((k for k, x in enumerate(c) if re.fullmatch(r"[A-Z0-9]{12}", x)), None)
        if i is None or i + 3 >= len(c) or c[i].startswith("CASH"):
            continue  # CASH… = 설정현금액(CU 설정 단위). 편입종목이 아니고 비중 100을 중복 계상한다(142종 중 84종)
        out.append((c[i], c[i + 1], c[i + 3]))
    return out


# ── ACE (한국투자) : 내부 fundCd 매핑 필요, JSON ──────────────────────────
def ace_list():
    data = get("https://papi.aceetf.co.kr/api/funds?page=1&size=500").json()["data"]
    return {d["stockCd"]: d["fundCd"] for d in data}


def ace_parse(b):
    j = json.loads(b)
    lst = j.get("pdfList") or []
    bad = {x.get("std_DT") for x in lst} - {AS_OF}
    if bad:  # 없는 날짜는 보통 빈 리스트지만 방어적으로 대조
        raise ValueError(f"기준일 불일치 {sorted(bad)}")
    return [(x["jm_KSC_CD"], x["sec_NM"], x["wg"]) for x in lst]  # 드롭: cu_ITEM_CNT·val_AM


BRANDS = {
    "KODEX": dict(
        key="ticker", ext="json", list=kodex_list, parse=kodex_parse,
        url=lambda i: f"https://www.samsungfund.com/api/v1/kodex/product-pdf/{i}.do?gijunYMD={DOT}",
        source="삼성자산운용 KODEX (samsungfund.com)"),
    "TIGER": dict(
        key="isin", ext="html", list=None, parse=tiger_parse,
        url=lambda i: ("https://investments.miraeasset.com/tigeretf/ko/product/search/detail/pdfListAjax.ajax"
                       f"?ksdFund={i}&fixDate={DOT}&pageIndex=1&firstIndex=0&listCnt=1000"),
        source="Mirae Asset TIGER ETF (investments.miraeasset.com/tigeretf)"),
    "RISE": dict(
        key="ticker", ext="xls", list=rise_list, parse=rise_parse,
        url=lambda i: f"https://www.riseetf.co.kr/prod/document/pdf/listExcel?searchTargetId={i}&searchDate={AS_OF}",
        source="KB Asset Management RISE ETF (riseetf.co.kr)"),
    "ACE": dict(
        key="isin", ext="json", list=ace_list, parse=ace_parse,
        url=lambda i: f"https://papi.aceetf.co.kr/api/funds/{i}/pdf?page=1&size=1000&std_dt={YMD}",
        source="한국투자신탁운용 ACE ETF (papi.aceetf.co.kr)"),
}


def targets(brand):
    """마스터에서 해당 브랜드 ETF 행 (pd_itm_no=ISIN, pd_itm_no_ma[1:]=티커)"""
    m = pd.read_csv(MASTER, dtype=str, keep_default_na=False)
    m = m[(m.pd_grp_no == "ETF") & (m.pd_abrv_nm.str.split().str[0] == brand)]
    return list(m[["pd_itm_no", "pd_itm_no_ma", "pd_abrv_nm"]].itertuples(index=False))


def path_of(brand, ticker):
    return OUTDIR / f"{brand.lower()}_{ticker}_{YMD}.{BRANDS[brand]['ext']}"


def main(limit=None, only=None):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    fails, anomalies = [], []
    for brand, a in BRANDS.items():
        if only and brand != only:
            continue
        rows = targets(brand)[:limit]
        try:
            idmap = a["list"]() if a["list"] else None
        except Exception as e:  # 한 브랜드의 차단이 나머지를 죽이지 않게
            print(f"[{brand}] 목록 매핑 실패 — 브랜드 건너뜀: {e}")
            fails.append((brand, "-", "-", f"목록 매핑 실패: {type(e).__name__}"))
            continue
        print(f"[{brand}] 대상 {len(rows)}종" + (f", 매핑 {len(idmap)}건" if idmap is not None else ", ISIN 직결"))
        ok = skip = 0
        for n, r in enumerate(rows, 1):
            ticker = r.pd_itm_no_ma[1:]
            path = path_of(brand, ticker)
            if path.exists():
                skip += 1
                continue
            key = r.pd_itm_no if a["key"] == "isin" else ticker
            internal = key if idmap is None else idmap.get(key)
            if internal is None:
                fails.append((brand, ticker, r.pd_abrv_nm, "매핑 없음(상폐/미노출)"))
                continue
            url = a["url"](internal)
            try:
                for attempt in range(MAX_RETRY + 1):
                    try:
                        body = get(url).content
                        break
                    except requests.HTTPError as e:
                        blocked = e.response.status_code in (403, 429)
                        if not (blocked and BACKOFF and attempt < MAX_RETRY):
                            raise
                        print(f"  .. {brand} {e.response.status_code} — {BACKOFF:.0f}초 대기 후 재시도"
                              f" ({attempt + 1}/{MAX_RETRY}) [{ticker}]", flush=True)
                        time.sleep(BACKOFF)
                parsed = a["parse"](body)
                if not parsed:
                    raise ValueError("0행")
                path.write_bytes(body)
                meta = {"source": a["source"], "as_of": AS_OF,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "url": url, "isin": r.pd_itm_no, "ticker": ticker, "name": r.pd_abrv_nm,
                        "internal_id": internal, "holdings_count": len(parsed)}
                path.with_name(path.name + ".meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                ok += 1
                s = sum(float(w) for _, _, w in parsed if str(w).strip() not in ("", "None", "-"))
                if not 95 <= s <= 105:
                    anomalies.append((brand, ticker, r.pd_abrv_nm, round(s, 2)))
            except requests.HTTPError as e:
                fails.append((brand, ticker, r.pd_abrv_nm, f"HTTP {e.response.status_code}"))
                if e.response.status_code in (403, 429):
                    print(f"  !! {brand} {e.response.status_code} — 브랜드 중단")
                    break
            except Exception as e:
                fails.append((brand, ticker, r.pd_abrv_nm, f"{type(e).__name__}: {e}"))
            time.sleep(SLEEP)
            if n % 25 == 0:
                print(f"  {n}/{len(rows)} (성공 {ok}, 스킵 {skip}, 실패 {len(fails)})")
        print(f"[{brand}] 완료: 성공 {ok}, 스킵 {skip}, 누적 실패 {len(fails)}")

    print(f"\n실패 {len(fails)}건")
    for f in fails:
        print("  FAIL", *f, sep="\t")
    print(f"\n비중합계 이상 {len(anomalies)}건 (원본은 보존, 관계 테이블에는 포함)")
    for x in anomalies:
        print("  WARN", *x, sep="\t")


if __name__ == "__main__":
    args = sys.argv[1:]  # [건수제한] [브랜드]
    main(int(args[0]) if args and args[0].isdigit() else None,
         next((x.upper() for x in args if not x.isdigit()), None))
