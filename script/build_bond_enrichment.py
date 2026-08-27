# 국내채권 보강 테이블(enriched) 생성 — 등급 ordinal, 잔존만기 버킷, 판매가능 플래그
# 기준일: 08-24 배포본 채권 마스터의 실질 기준일은 info_base_dt = 2026-08-21(전 행 동일)이다.
#         잔존만기는 이 날짜로 재계산한다. 원본 remaining_days는 쓰지 않는다.
# 그레인: 08-24 배포본부터 pd_no가 단독 유일키가 아니다.
#         (pd_no, pd_exg_mkt, info_seq) 복합키로 원천 21,882행을 보존한다.
# 출처: 모든 컬럼이 원본 컬럼에서 계산한 파생값이라 컬럼별 *_source 대신 테이블 전체에 source 한 컬럼을 둔다.
import os
from datetime import date

import pandas as pd

SRC = "data/csv/PRBD01N001_bond_kr_master_20260824.csv"
OUT = "data/enriched/bond_kr_enriched.csv"
BASE_DATE = date(2026, 8, 21)  # info_base_dt 실측값

# 신용등급 서열: 1 = AAA(최상), 커질수록 낮은 등급 → "AA- 이상" = crd_grd_rank <= rank('AA-')
# 사내 표기의 `0` 접미는 등급 내 중위(flat)라 접미를 떼어 정규화한다 (AA0→AA, C0→C).
GRADES = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
          "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "CC", "C"]
RANK = {g: i + 1 for i, g in enumerate(GRADES)}
SALE_COLS = ["buy_yield", "corp_pretax_yield", "corp_after_tax_yield", "after_tax_yield",
             "pref_tax_yield", "avg_annual_tax_yield", "depo_equiv_yield_154", "buyable_quantity"]


def norm_grade(g):
    g = g.strip()
    return g[:-1] if g.endswith("0") and len(g) > 1 else g


def to_days(s):
    """YYYYMMDD → 기준일 대비 잔존일수. 빈 값·'00000000' sentinel은 None."""
    if len(s) != 8:
        return None
    try:
        return (date(int(s[:4]), int(s[4:6]), int(s[6:])) - BASE_DATE).days
    except ValueError:  # '00000000' 결측 sentinel 4건
        return None


# 08-24 배포본 CSV는 UTF-8 BOM으로 시작한다. 미지정 시 첫 컬럼명이 '﻿after_tax_yield'가 된다.
raw = pd.read_csv(SRC, dtype=str, keep_default_na=False, encoding="utf-8-sig")

has_sale_raw = raw[SALE_COLS].ne("").all(axis=1)
assert (has_sale_raw == raw[SALE_COLS].ne("").any(axis=1)).all(), "판매 8컬럼 결측 패턴이 이분법이 아님"
assert has_sale_raw.sum() == 634, has_sale_raw.sum()
df = raw
has_sale = has_sale_raw

KEY = ["pd_no", "pd_exg_mkt", "info_seq"]
enr = df[KEY].copy()

crd = df["crd_grd"].map(norm_grade)
assert set(crd) <= set(GRADES) | {""}, set(crd) - set(GRADES)

# 08-24 배포본에서 pd_evco_crd_grd(평가사별 등급) 컬럼이 삭제됐다.
# 폴백 소스가 없으므로 crd_grd 단독으로 산출한다.
enr["crd_grd_norm"] = crd
enr["crd_grd_rank"] = crd.map(RANK).astype("Int64")
enr["crd_grd_source"] = crd.mask(crd.ne(""), "crd_grd")

# mat_dt 결측 sentinel은 '00000000'(07-11의 '0'에서 변경). 음수(만기경과) 허용.
# 영구채는 mat_dt=99991231(pandas datetime 범위 밖)이라 stdlib date로 파싱한다.
days = df["mat_dt"].map(to_days).astype("Int64")
enr["remaining_days"] = days
enr["maturity_bucket"] = pd.cut(
    days, [-float("inf"), 0, 365, 365 * 3, 365 * 5, 365 * 10, float("inf")],
    labels=["만기경과", "1년미만", "1-3년", "3-5년", "5-10년", "10년이상"],
).cat.add_categories("미상").fillna("미상")

enr["is_krw"] = (df["curr_cd"] == "KRW").map({True: "Y", False: "N"})
enr["has_sale_info"] = has_sale.map({True: "Y", False: "N"})  # 판매 화면 게시 여부(참고용)

# is_sellable = 만기 미도래. 주최측이 buyable_quantity를 무효 처리해 재고 기반 판정이 불가하고,
# has_sale_info는 게시 여부일 뿐 판매 가능성이 아니므로 둘 다 조건에서 뺐다.
enr["is_sellable"] = (days > 0).map({True: "Y", False: "N"})
enr["source"] = "derived:PRBD01N001"

assert len(enr) == 21882, len(enr)
assert not enr.duplicated(KEY).any()
assert enr["crd_grd_rank"].notna().sum() == enr["crd_grd_norm"].ne("").sum()
assert (enr["crd_grd_source"].eq("") == enr["crd_grd_norm"].eq("")).all()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
enr.to_csv(OUT, index=False, encoding="utf-8-sig", lineterminator="\n")

print(f"enriched {len(enr)}행 → {OUT} (복합키 {KEY})")
print(f"AA- 이상(rank<={RANK['AA-']}): {(enr['crd_grd_rank'] <= RANK['AA-']).sum()}건")
print(f"is_sellable=Y(만기 미도래): {(enr['is_sellable'] == 'Y').sum()}건 / "
      f"has_sale_info=Y {(enr['has_sale_info'] == 'Y').sum()}건 (원본 {has_sale_raw.sum()}행)")
print("maturity_bucket:", enr["maturity_bucket"].value_counts().reindex(
    ["만기경과", "1년미만", "1-3년", "3-5년", "5-10년", "10년이상", "미상"]).to_dict())
print("등급 출처:", enr["crd_grd_source"].replace("", "(무등급)").value_counts().to_dict())
