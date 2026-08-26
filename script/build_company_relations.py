"""DART 원천 → 기업 마스터/자회사 관계 테이블 (data/external/company_* → data/enriched·relations).

    python3 EDA/build_company_relations.py

- data/enriched/company_master.csv     : corpCode.xml 전체(비상장 포함) + 정규화명
- data/relations/company_subsidiary.csv: 타법인 출자현황 롱포맷. as_of는 rcept_no 접수일, 컷오프 초과 행은 제외
조인률 개선(채권 발행사·편입종목)과 목표 기업 자회사 실증을 함께 출력한다.
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CORPCODE = ROOT / "data/external/company_master/dart_corpcode_20260711.xml"
KIND = ROOT / "data/external/company_master/kind_listed_corp_20260711.csv"
GOV = ROOT / "data/external/company_governance"
BOND = ROOT / "data/csv/PRBD01N001_bond_kr_master_20260711.csv"
HOLDING = ROOT / "data/relations/etf_holding.csv"
OUT_MASTER = ROOT / "data/enriched/company_master.csv"
OUT_SUB = ROOT / "data/relations/company_subsidiary.csv"
CUTOFF = "2026-08-24"

# 한글 음차 → 영문 약칭. 실제 조인에서 확인된 것만 둔다(오탐 방지). 긴 것부터 치환한다.
ALIAS = {"에스케이": "SK", "엘지": "LG", "케이티": "KT", "지에스": "GS", "씨제이": "CJ",
         "에이치디": "HD", "에스디": "SD", "디비": "DB", "케이비": "KB", "엔에이치": "NH"}
DROP = re.compile(r"\(주\)|㈜|\(유\)|주식회사|[\s·,]")


def norm(name):
    """(a) 법인격 표기·구분자 제거 (b) 한글 음차 → 영문 약칭"""
    s = DROP.sub("", str(name))
    for k in sorted(ALIAS, key=len, reverse=True):
        s = s.replace(k, ALIAS[k])
    return s.upper()


assert norm("에스케이하이닉스(주)") == "SK하이닉스"
assert norm("(주)엘지에너지솔루션") == "LG에너지솔루션"
assert norm("주식회사 에코프로 비엠") == "에코프로비엠"

# ── 1. 기업 마스터 ────────────────────────────────────────────────────────
m = pd.read_xml(CORPCODE, dtype=str, encoding="utf-8")
m["corp_code"] = m["corp_code"].str.zfill(8)
m["stock_code"] = m["stock_code"].fillna("").str.strip()
m["corp_name_norm"] = m["corp_name"].map(norm)
m["source"] = "DART:corpCode"
m = m[["corp_code", "corp_name", "corp_name_norm", "stock_code", "source"]]
assert m.corp_code.is_unique and m.corp_code.str.len().eq(8).all()
OUT_MASTER.parent.mkdir(parents=True, exist_ok=True)
m.to_csv(OUT_MASTER, index=False, encoding="utf-8-sig", lineterminator="\n")
listed = m.stock_code.str.len().eq(6)
print(f"{OUT_MASTER}: {len(m):,}행 (상장 {listed.sum():,} / 비상장 {(~listed).sum():,})")

# ── 2. 자회사 관계 ────────────────────────────────────────────────────────
rows, files, empty = [], 0, 0
for p in sorted(GOV.glob("dart_invst_*.json")):
    if p.name.endswith(".meta.json"):  # 사이드카는 원본이 아니다
        continue
    files += 1
    lst = json.loads(p.read_text(encoding="utf-8")).get("list") or []
    empty += not lst
    for x in lst:  # 법인명·출자목적에 줄바꿈이 섞여 온다 → 공백 정규화
        rows.append((x["corp_code"].zfill(8), " ".join(str(x["corp_name"]).split()),
                     " ".join(str(x.get("inv_prm", "")).split()),
                     x.get("trmend_blce_qota_rt", ""), " ".join(str(x.get("invstmnt_purps", "")).split()),
                     x.get("rcept_no", "")))

s = pd.DataFrame(rows, columns=["parent_corp_code", "parent_name", "child_name",
                                "ownership_pct", "invest_purpose", "rcept_no"])
s["child_name_norm"] = s["child_name"].map(norm)
s["ownership_pct"] = pd.to_numeric(s["ownership_pct"].str.replace(",", ""), errors="coerce")
r = s["rcept_no"].str[:8]
s["as_of"] = r.str[:4] + "-" + r.str[4:6] + "-" + r.str[6:8]
s["source"] = "DART:otrCprInvstmntSttus"

ahead = s["as_of"] > CUTOFF  # 룩어헤드 가드: 컷오프 이후 접수분 제외
print(f"as_of > {CUTOFF} 제외: {ahead.sum()}행" + (f" {sorted(s.loc[ahead, 'as_of'].unique())}" if ahead.any() else ""))
junk = s.child_name_norm.isin(["합계", "소계", "계", "-", ""])  # DART 표의 소계 행. 자회사가 아니다
print(f"요약행 제외: {junk.sum()}행 {s.loc[junk, 'child_name'].value_counts().head(3).to_dict()}")
s = s[~ahead & ~junk]

# 자회사는 법인명 문자열로만 오므로 정규화명으로 마스터에 되붙인다.
# 1순위: 정규화명이 마스터에서 유일 → 그 법인. 2순위: 동명이인이지만 상장사가 정확히 1개 →
# 그 상장사(타법인출자에 등장하는 KT·삼성물산류 대형명은 상장사가 맞다). 비상장 동명이인은 특정 불가라 공란.
uniq = m.groupby("corp_name_norm").corp_code.nunique()
by_unique = m[m.corp_name_norm.isin(uniq[uniq == 1].index)].set_index("corp_name_norm").corp_code
lst = m[listed]
lst_uniq = lst.groupby("corp_name_norm").corp_code.nunique()
by_listed = lst[lst.corp_name_norm.isin(lst_uniq[lst_uniq == 1].index)].set_index("corp_name_norm").corp_code
s["child_corp_code"] = s.child_name_norm.map(by_unique).fillna("")
s["child_match_rule"] = ""
s.loc[s.child_corp_code.ne(""), "child_match_rule"] = "unique_name"
amb = s.child_corp_code.eq("") & s.child_name_norm.isin(by_listed.index)
s.loc[amb, "child_corp_code"] = s.loc[amb, "child_name_norm"].map(by_listed)
s.loc[amb, "child_match_rule"] = "unique_listed"
print(f"동명이인 중 유일 상장사 매칭(unique_listed): {amb.sum()}행")

# 3순위: 공시 표기 노이즈 제거 후 재매칭 — 각주((주1)·(*2)), 개명 주석((구XX)), 증권종류 접미(보통주·RCPS 등).
# 지역명 괄호((곤산)·(베트남) = 별도 현지법인)는 제거하지 않는다. 사명 변경(에코프로머티리얼즈→에코프로머티)은
# 오프라인 근거가 없어 규칙으로 풀지 않고 미매칭으로 남긴다.
NOISE_PAREN = re.compile(r"\((?:주\s?\d*|\*+\d*|구[.,]?\s?[^)]*|사명변경전[^)]*|유상증자|KOSDAQ|주\d+참조)\)")
SEC_SUFFIX = re.compile(r"(_?(투자분|의무인수분|환매청구권)|보통주식?|전환?우선주(식)?|전환사채\(?\d*CB\)?|\d+C[BP]S?|RCPS|CPS|CB)+$")
cl = s.child_name_norm.map(lambda n: SEC_SUFFIX.sub("", NOISE_PAREN.sub("", n)).strip())
for rule, table in [("clean_unique_name", by_unique), ("clean_unique_listed", by_listed)]:
    todo = s.child_corp_code.eq("") & cl.ne(s.child_name_norm) & cl.isin(table.index)
    s.loc[todo, "child_corp_code"] = cl[todo].map(table)
    s.loc[todo, "child_match_rule"] = rule
    print(f"표기 정제 재매칭({rule}): {todo.sum()}행")
s = s[["parent_corp_code", "parent_name", "child_name", "child_name_norm", "child_corp_code",
       "child_match_rule", "ownership_pct", "invest_purpose", "source", "as_of"]]
hit = s.child_corp_code.ne("")
print(f"child_corp_code 매칭: {hit.sum():,} / {len(s):,} = {hit.mean():.1%} "
      f"(그중 상장 {s.child_corp_code.isin(set(m.loc[listed, 'corp_code'])).sum():,}행)")
assert len(s) and s.as_of.le(CUTOFF).all() and s.parent_corp_code.str.len().eq(8).all()
OUT_SUB.parent.mkdir(parents=True, exist_ok=True)
s.to_csv(OUT_SUB, index=False, encoding="utf-8-sig", lineterminator="\n")
print(f"{OUT_SUB}: {len(s):,}행, 모회사 {s.parent_corp_code.nunique():,}종 "
      f"(원천 {files:,}건 중 빈결과 {empty:,})")
print("출자목적 상위:", s.invest_purpose.value_counts().head(5).to_dict())

# ── 3. 조인 효과 측정 (KIND 상장사 마스터 대비) ────────────────────────────
kind = pd.read_csv(KIND, dtype=str, keep_default_na=False)
kind_norm, kind_stock = set(kind["회사명"].map(norm)), set(kind["종목코드"])
dart_norm, dart_stock = set(m.corp_name_norm), set(m.loc[listed, "stock_code"])


def rate(keys, pool):
    return f"{sum(k in pool for k in keys):,} / {len(keys):,} = {sum(k in pool for k in keys) / len(keys):.1%}"


pbcm = {norm(x) for x in pd.read_csv(BOND, dtype=str, keep_default_na=False).PD_PBCM.unique() if x.strip()}
h = pd.read_csv(HOLDING, dtype=str, keep_default_na=False)
t6 = set(h.loc[h.holding_code_type == "ticker6", "holding_code_raw"])
isin = {x[3:9] for x in h.loc[h.holding_code_type == "isin", "holding_code_raw"].unique() if x.startswith("KR7")}

print("\n조인률 (KIND 상장사 → DART 마스터)")
for label, keys, a, b in [("채권 발행사 PD_PBCM(명칭)", pbcm, kind_norm, dart_norm),
                          ("편입종목 ticker6", t6, kind_stock, dart_stock),
                          ("편입종목 ISIN→ticker6", isin, kind_stock, dart_stock)]:
    print(f"  {label:24s} {rate(keys, a):>22s}  →  {rate(keys, b):>22s}")

# ── 4. 목표 기업 자회사 실증 ──────────────────────────────────────────────
print("\n목표 기업 자회사 (상위 5건, 지분율순)")
for name in ["에코프로", "LG에너지솔루션", "SK하이닉스"]:
    hit = m[(m.corp_name_norm == norm(name)) & listed]
    if hit.empty:
        print(f"  [{name}] 마스터 미발견")
        continue
    code = hit.iloc[0].corp_code
    sub = s[s.parent_corp_code == code].sort_values("ownership_pct", ascending=False)
    print(f"  [{name}] corp_code={code} stock={hit.iloc[0].stock_code} 자회사 {len(sub)}건 as_of={sub.as_of.iloc[0] if len(sub) else '-'}")
    for x in sub.head(5).itertuples(index=False):
        print(f"      {x.child_name:30s} {x.ownership_pct:>7}%  {x.invest_purpose}")
