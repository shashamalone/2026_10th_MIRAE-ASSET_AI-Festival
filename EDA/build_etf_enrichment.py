# 국내ETF 보강 테이블(enriched) + ETF↔테마 관계 테이블 생성
# 매칭 규칙(05_linkage 검증): lseg 키 == pd_itm_no_ma[1:] (선두 A=ETF/Q=ETN 제거)
import json
import pandas as pd

master = pd.read_csv("data/csv/PREF01N001_etf_kr_master_20260711.csv", dtype=str, keep_default_na=False)
lseg = json.load(open("lseg_static_metadata.json", encoding="utf-8"))

enr = master[["pd_itm_no", "pd_itm_no_ma", "pd_grp_no", "pd_abrv_nm", "cu_charge_rt"]].copy()
enr["lseg_key"] = enr["pd_itm_no_ma"].str[1:]

SCALARS = ["ter", "replication", "base_market", "base_asset", "hedge_type"]
for c in SCALARS:
    enr[c] = enr["lseg_key"].map(lambda k: lseg.get(k, {}).get(c, ""))

# 총보수 확정값: 주최측 실값(>0) 우선, 아니면 LSEG ter
rdb = pd.to_numeric(enr["cu_charge_rt"], errors="coerce")
ter = pd.to_numeric(enr["ter"], errors="coerce")
enr["charge_rt_final"] = rdb.where(rdb > 0, ter)
enr["charge_rt_source"] = ""
enr.loc[enr["charge_rt_final"].notna(), "charge_rt_source"] = "LSEG"
enr.loc[rdb > 0, "charge_rt_source"] = "RDB"

# as_of는 LSEG 파일의 수집 시점이 미확인이라 공란. 추정 날짜를 채우면 근거 표시에서 거짓 기준일이 된다.
theme_rows = [
    {"pd_itm_no": r.pd_itm_no, "theme": t, "source": "LSEG", "as_of": ""}
    for r in enr.itertuples()
    for t in lseg.get(r.lseg_key, {}).get("themes", [])
]
themes = pd.DataFrame(theme_rows)

matched = enr["ter"].ne("").sum()
assert matched == 1099, matched  # linkage 검증값과 일치해야 함
assert themes["pd_itm_no"].nunique() <= matched

import os
os.makedirs("data/enriched", exist_ok=True)
os.makedirs("data/relations", exist_ok=True)
enr.drop(columns=["cu_charge_rt"]).to_csv("data/enriched/etf_kr_enriched.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
themes.to_csv("data/relations/etf_theme.csv", index=False, encoding="utf-8-sig", lineterminator="\n")

etf = enr[enr["pd_grp_no"] == "ETF"]
print(f"enriched {len(enr)}행 (LSEG 매칭 {matched}건, ETF 기준 {etf['ter'].ne('').mean()*100:.1f}%)")
print(f"charge_rt_final 보유: {enr['charge_rt_final'].notna().sum()}건 (RDB {(enr['charge_rt_source']=='RDB').sum()} / LSEG {(enr['charge_rt_source']=='LSEG').sum()})")
print(f"etf_theme {len(themes)}행, 테마 {themes['theme'].nunique()}종, ETF {themes['pd_itm_no'].nunique()}종")
