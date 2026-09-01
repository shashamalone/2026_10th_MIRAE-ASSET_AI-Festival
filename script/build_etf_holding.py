# ETF↔편입종목 관계 테이블 생성 (data/external/etf_kr_holdings/ → data/relations/etf_holding.csv)
# 스키마: HOLDINGS_COLLECTION_DESIGN.md 3.2. 수량·평가금액·룩어헤드 컬럼은 싣지 않는다.
# 식별자는 원본 그대로 보존한다 — 티커↔ISIN 변환은 기업 마스터 확보 후 별도 작업(설계서 3.4).
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_etf_holdings as C  # noqa: E402
from collect_etf_holdings import BRANDS, OUTDIR, path_of, set_as_of, targets  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data/relations/etf_holding.csv"

# 디스크에 있는 스냅샷 날짜를 전부 싣는다 (파일명 {brand}_{ticker}_{YMD}.{ext})
DATES = sorted({f"{m[1][:4]}-{m[1][4:6]}-{m[1][6:]}"
                for p in OUTDIR.iterdir() if not p.name.endswith(".meta.json")
                if (m := re.fullmatch(r"[a-z]+_[0-9A-Z]+_(\d{8})\.\w+", p.name))})
assert DATES, f"스냅샷 없음: {OUTDIR}"


def code_type(c):
    c = str(c).strip()
    if re.fullmatch(r"\d{6}", c):
        return "ticker6"
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", c):
        return "isin"
    if " " in c and c.replace(" ", "").isalnum() and c.isascii():
        return "bloomberg"  # NVDA US EQUITY
    return "other"


assert code_type("005930") == "ticker6"
assert code_type("KR7005930003") == "isin"
assert code_type("NVDA US EQUITY") == "bloomberg"
assert code_type("03502G") == "other"

rows, missing = [], []
for as_of in DATES:
    set_as_of(as_of)  # KODEX·ACE·PLUS·SOL parse가 모듈 전역 날짜와 응답 기준일을 대조한다
    for brand, a in BRANDS.items():
        for r in targets(brand):
            p = path_of(brand, r.pd_itm_no_ma[1:])
            if not p.exists():
                missing.append((as_of, brand, r.pd_itm_no_ma[1:], r.pd_abrv_nm))
                continue
            for code, name, weight in a["parse"](p.read_bytes()):
                rows.append((r.pd_itm_no, code, code_type(code), name, weight, brand, as_of))

df = pd.DataFrame(rows, columns=["pd_itm_no", "holding_code_raw", "holding_code_type",
                                 "holding_name", "weight", "source", "as_of"])
df["weight"] = pd.to_numeric(df["weight"], errors="coerce")

assert len(df) and df["pd_itm_no"].str.startswith("KR").all()
assert df["as_of"].isin(DATES).all() and df["source"].isin(BRANDS).all()
assert set(df["as_of"]) == set(DATES), f"파싱 0행인 날짜: {set(DATES) - set(df['as_of'])}"

OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False, encoding="utf-8-sig", lineterminator="\n")

print(f"{OUT}: {len(df):,}행, 스냅샷 {DATES}, ETF {df['pd_itm_no'].nunique()}종")
print(df.groupby("as_of").agg(행수=("weight", "size"), ETF종수=("pd_itm_no", "nunique")).to_string())
print(df.pivot_table(index="source", columns="as_of", values="pd_itm_no", aggfunc="nunique").to_string())
print(df["holding_code_type"].value_counts().to_string())
w = df.groupby(["as_of", "source", "pd_itm_no"])["weight"].sum()
print(f"비중합계 95~105 밖: {((w < 95) | (w > 105)).sum()}종")

# 마스터(ETF 1,235종) 대비 신규 스냅샷 커버리지 — 종수와 순자산 비중
m = pd.read_csv(C.MASTER, dtype=str, keep_default_na=False)
m = m[m.pd_grp_no == "ETF"]
m["net"] = pd.to_numeric(m.pd_net_tamt, errors="coerce").fillna(0)
for d in DATES:
    got = set(df.loc[df.as_of == d, "pd_itm_no"])
    hit = m[m.pd_itm_no.isin(got)]
    print(f"커버리지 {d}: {len(hit)}/{len(m)}종 ({len(hit) / len(m):.1%}), "
          f"순자산 {hit.net.sum() / m.net.sum():.1%}")
print(f"미수집 {len(missing)}건 "
      + str(pd.Series([f"{d} {b}" for d, b, _, _ in missing]).value_counts().to_dict()))
