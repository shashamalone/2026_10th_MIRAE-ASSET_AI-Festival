# 편입종목 ticker6 식별자 해소 테이블 — etf_holding의 미매칭 182종을 우선주/모ETF/미해소로 분류
# 원칙: 규칙으로 확정 가능한 것만 매핑하고 match_rule을 남긴다. 애매하면 비워둔다(오매칭 > 미매칭).
import pandas as pd

OUT = "data/enriched/holding_code_map.csv"

h = pd.read_csv("data/relations/etf_holding.csv", dtype=str, keep_default_na=False)
cm = pd.read_csv("data/enriched/company_master.csv", dtype=str, keep_default_na=False)
etf = pd.read_csv("data/csv/PREF01N001_etf_kr_master_20260711.csv", dtype=str, keep_default_na=False)

listed = cm[cm.stock_code != ""].set_index("stock_code")
etf_by_ticker = etf[etf.pd_grp_no == "ETF"].assign(ticker=etf.pd_itm_no_ma.str[1:]).set_index("ticker")

t6 = (h[h.holding_code_type == "ticker6"]
      .drop_duplicates("holding_code_raw")[["holding_code_raw", "holding_name"]]
      .sort_values("holding_code_raw"))

rows = []
for code, name in t6.itertuples(index=False):
    r = {"holding_code_raw": code, "holding_name": name, "sec_type": "", "corp_code": "",
         "common_ticker": "", "etf_isin": "", "match_rule": ""}
    common = code[:5] + "0"
    if code in listed.index:
        r.update(sec_type="stock", corp_code=listed.loc[code, "corp_code"], match_rule="stock_code_exact")
    elif code in etf_by_ticker.index:
        r.update(sec_type="etf", etf_isin=etf_by_ticker.loc[code, "pd_itm_no"], match_rule="etf_ticker_exact")
    # 우선주: KRX 관행상 보통주 끝자리 0, 우선주는 5/7/9 등. 이름 접미(우/우B)와 보통주 실존을 함께 요구한다.
    elif code[-1] != "0" and common in listed.index and name.rstrip("B").endswith("우"):
        r.update(sec_type="stock_pref", common_ticker=common,
                 corp_code=listed.loc[common, "corp_code"], match_rule="pref_suffix_to_common")
    rows.append(r)

out = pd.DataFrame(rows)
out["source"] = "derived:etf_holding+company_master+PREF01N001"
out.to_csv(OUT, index=False, encoding="utf-8-sig", lineterminator="\n")

c = out.match_rule.replace("", "(미해소)").value_counts().to_dict()
print(f"{len(out)}종 → {OUT}")
print("분류:", c)
unres = out[out.match_rule == ""]
print("미해소 샘플:", unres.holding_name.head(8).tolist())
assert out.holding_code_raw.is_unique
assert (out[out.sec_type == "stock_pref"].common_ticker != "").all()
