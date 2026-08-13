# 국내채권 보강 테이블(enriched) 생성 — 등급 ordinal, 잔존만기 버킷, 판매가능 플래그
# 기준일: 채권 마스터의 실질 기준일은 2026-02-24(잔존일수·듀레이션·평가가격류가 그 시점 값)이나,
#         평가 기준일이 2026-07-11이므로 잔존만기는 후자로 재계산한다. 원본 REMAINING_DAYS는 쓰지 않는다.
# 출처: 모든 컬럼이 원본 컬럼에서 계산한 파생값이라 컬럼별 *_source 대신 테이블 전체에 source 한 컬럼을 둔다.
import os
from datetime import date

import pandas as pd

SRC = "data/csv/PRBD01N001_bond_kr_master_20260711.csv"
OUT = "data/enriched/bond_kr_enriched.csv"
BASE_DATE = date(2026, 7, 11)

# 신용등급 서열: 1 = AAA(최상), 커질수록 낮은 등급 → "AA- 이상" = crd_grd_rank <= rank('AA-')
# 사내 표기의 `0` 접미는 등급 내 중위(flat)라 접미를 떼어 정규화한다 (AA0→AA, C0→C).
GRADES = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
          "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "CC", "C"]
RANK = {g: i + 1 for i, g in enumerate(GRADES)}
SALE_COLS = ["BUY_YIELD", "CORP_PRETAX_YIELD", "CORP_AFTER_TAX_YIELD", "AFTER_TAX_YIELD",
             "PREF_TAX_YIELD", "AVG_ANNUAL_TAX_YIELD", "DEPO_EQUIV_YIELD_154", "BUYABLE_QUANTITY"]


def norm_grade(g):
    g = g.strip()
    return g[:-1] if g.endswith("0") and len(g) > 1 else g


def to_days(s):
    """YYYYMMDD → 기준일 대비 잔존일수. 결측 sentinel('0')·빈 값은 None."""
    if len(s) != 8:
        return None
    return (date(int(s[:4]), int(s[4:6]), int(s[6:])) - BASE_DATE).days


df = pd.read_csv(SRC, dtype=str, keep_default_na=False)
enr = pd.DataFrame({"PD_NO": df["PD_NO"]})

enr["crd_grd_norm"] = df["CRD_GRD"].map(norm_grade)
assert set(enr["crd_grd_norm"]) <= set(GRADES) | {""}, set(enr["crd_grd_norm"]) - set(GRADES)
enr["crd_grd_rank"] = enr["crd_grd_norm"].map(RANK).astype("Int64")

# 다중 평가사 등급 문자열(콤마 구분) — 평가사 수와 등급 일치 여부. 1개 이하면 판정불가(빈 값).
evco = df["PD_EVCO_CRD_GRD"].map(lambda s: [norm_grade(t) for t in s.split(",") if t.strip()])
enr["evco_grd_count"] = evco.map(len)
enr["evco_grd_agree"] = evco.map(lambda v: "" if len(v) < 2 else ("Y" if len(set(v)) == 1 else "N"))

# MAT_DT 결측 sentinel은 '0'. 음수(만기경과) 허용.
# 영구채 4건은 MAT_DT=99991231(pandas datetime 범위 밖)이라 stdlib date로 파싱한다.
days = df["MAT_DT"].map(to_days).astype("Int64")
enr["remaining_days"] = days
enr["maturity_bucket"] = pd.cut(
    days, [-float("inf"), 0, 365, 365 * 3, 365 * 5, 365 * 10, float("inf")],
    labels=["만기경과", "1년미만", "1-3년", "3-5년", "5-10년", "10년이상"],
).cat.add_categories("미상").fillna("미상")

enr["is_krw"] = (df["CURR_CD"] == "KRW").map({True: "Y", False: "N"})
# 판매 8컬럼은 전부 있거나 전부 없는 완전 이분법(881 / 41,513) → 단일 플래그로 축약
has_sale = df[SALE_COLS].ne("").all(axis=1)
assert (has_sale == df[SALE_COLS].ne("").any(axis=1)).all(), "판매 8컬럼 결측 패턴이 이분법이 아님"
enr["has_sale_info"] = has_sale.map({True: "Y", False: "N"})

qty = pd.to_numeric(df["BUYABLE_QUANTITY"], errors="coerce")
enr["is_sellable"] = (has_sale & (qty > 0) & (df["CURR_CD"] == "KRW") & (days > 0)).map({True: "Y", False: "N"})
enr["source"] = "derived:PRBD01N001"

assert len(enr) == 42394, len(enr)
assert enr["PD_NO"].is_unique
assert (enr["has_sale_info"] == "Y").sum() == 881
assert enr["crd_grd_rank"].notna().sum() == df["CRD_GRD"].ne("").sum()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
enr.to_csv(OUT, index=False, encoding="utf-8-sig", lineterminator="\n")

aa_minus = (enr["crd_grd_rank"] <= RANK["AA-"]).sum()
print(f"enriched {len(enr)}행 → {OUT}")
print(f"AA- 이상(rank<={RANK['AA-']}): {aa_minus}건 (EDA 보고서 22,083)")
print(f"is_sellable=Y: {(enr['is_sellable'] == 'Y').sum()}건 (EDA 보고서 254) / has_sale_info=Y {(enr['has_sale_info'] == 'Y').sum()}건")
print("maturity_bucket:", enr["maturity_bucket"].value_counts().reindex(
    ["만기경과", "1년미만", "1-3년", "3-5년", "5-10년", "10년이상", "미상"]).to_dict())
print("evco_grd_agree:", enr["evco_grd_agree"].value_counts(dropna=False).to_dict())
