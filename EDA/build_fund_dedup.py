# 공모펀드마스터 롱포맷(속성코드별 행 복제) → 펀드 1개당 1행 dedup 테이블 생성
import pandas as pd

SRC = "data/csv/PRFD01N001_fund_pub_master_20260711.csv"
OUT = "data/csv/PRFD01N001_fund_pub_dedup_20260711.csv"

df = pd.read_csv(SRC, dtype=str, keep_default_na=False)

# 깨진 단일 행(itm_no='"', 값이 좌우로 밀린 행) 배제 — EDA_REPORT §7 참조
broken = df["itm_no"] == '"'
df = df[~broken]

# 유일키 (itm_no, prfd_attr_cd) 검증 후 속성코드만 집약, 나머지 컬럼은 첫 행 값
assert not df.duplicated(["itm_no", "prfd_attr_cd"]).any()
attrs = df.groupby("itm_no", sort=False)["prfd_attr_cd"].agg(";".join).rename("prfd_attr_cds")
dedup = df.drop_duplicates("itm_no").drop(columns=["prfd_attr_cd"]).merge(attrs, on="itm_no")

assert len(dedup) == df["itm_no"].nunique()
dedup.to_csv(OUT, index=False, encoding="utf-8-sig", lineterminator="\n")
print(f"원본 {len(df)+broken.sum()}행 → dedup {len(dedup)}행 (깨진 행 {broken.sum()}건 배제)")
print("순자산 합계(dedup, 조원):", round(pd.to_numeric(dedup["fd_nast_suma"], errors="coerce").sum() / 1e12, 1))
