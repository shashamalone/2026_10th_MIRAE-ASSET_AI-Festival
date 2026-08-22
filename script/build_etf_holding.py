# ETF↔편입종목 관계 테이블 생성 (data/external/etf_kr_holdings/ → data/relations/etf_holding.csv)
# 스키마: HOLDINGS_COLLECTION_DESIGN.md 3.2. 수량·평가금액·룩어헤드 컬럼은 싣지 않는다.
# 식별자는 원본 그대로 보존한다 — 티커↔ISIN 변환은 기업 마스터 확보 후 별도 작업(설계서 3.4).
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_etf_holdings import AS_OF, BRANDS, path_of, targets  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data/relations/etf_holding.csv"


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
for brand, a in BRANDS.items():
    for r in targets(brand):
        p = path_of(brand, r.pd_itm_no_ma[1:])
        if not p.exists():
            missing.append((brand, r.pd_itm_no_ma[1:], r.pd_abrv_nm))
            continue
        for code, name, weight in a["parse"](p.read_bytes()):
            rows.append((r.pd_itm_no, code, code_type(code), name, weight, brand, AS_OF))

df = pd.DataFrame(rows, columns=["pd_itm_no", "holding_code_raw", "holding_code_type",
                                 "holding_name", "weight", "source", "as_of"])
df["weight"] = pd.to_numeric(df["weight"], errors="coerce")

assert len(df) and df["pd_itm_no"].str.startswith("KR").all()
assert df["as_of"].eq(AS_OF).all() and df["source"].isin(BRANDS).all()

OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False, encoding="utf-8-sig", lineterminator="\n")

print(f"{OUT}: {len(df):,}행, ETF {df['pd_itm_no'].nunique()}종")
print(df.groupby("source")["pd_itm_no"].nunique().to_string())
print(df["holding_code_type"].value_counts().to_string())
w = df.groupby(["source", "pd_itm_no"])["weight"].sum()
print(f"비중합계 95~105 밖: {((w < 95) | (w > 105)).sum()}종")
print(f"미수집 {len(missing)}종 " + str(pd.Series([b for b, _, _ in missing]).value_counts().to_dict()))
