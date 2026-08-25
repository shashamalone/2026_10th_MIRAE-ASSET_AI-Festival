# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # 05. 도메인 간 연결(Linkage) EDA — 2026-08-24 배포본
#
# 온톨로지(.ttl) 설계에 직결되는 **도메인 간 조인 키·엔티티 통합·평가질의 커버리지**를 검증한다.
# 대상: 국내채권 / 국내ETF(+ETN) / 해외ETF / 공모펀드 / LSEG 정적 메타데이터.
#
# 2026-07-11 배포본 대비 이 노트북에 영향을 주는 변경:
# - 공모펀드가 **1행 = 1펀드**가 되어 dedup이 불필요해졌다(무해한 no-op으로 유지).
# - 국내ETF에 `ref_base_index`(결측 2.2%)·`pd_isin_cd`·`pd_ric`·`ref_fund_mgmt_co`가 신설되어
#   **지수·운용사 엔티티 통합 난이도가 크게 낮아졌다.**
# - 국내채권 컬럼이 소문자로 바뀌고 `bd_inrt_tcd`·`bd_intp_tcd`가 신설되어 axis 재현 규칙이 달라진다.
# - `axis_sample`은 08-24 배포본에서 제공되지 않아 07-11 파일을 그대로 쓴다.
#   **채권 샘플 100행 중 69행만 새 마스터에 존재**하므로(만기 도래분 삭제) 재현율은 그 69행 기준이다.
#
# 주최측 추가 안내(2026-08-24) — 커버리지 판정에 직접 반영한다:
# - 평가는 **35문항**(상 10 / 중 10 / 하 10 + 답변불가 5).
# - **교차질의**가 포함된다. 예: "삼성전자를 보유한 국내/해외ETF와 공모펀드를 1년 수익률 기준 TOP10"
#   → ETF와 펀드를 **한 랭킹으로 합쳐야** 하므로 상품군 간 수익률 정의·기준일 정합이 필수다.
# - 공시·시장데이터는 **2026-08-24까지** 발행분 사용 가능(구 기준 07-11에서 이동).
# - `BUYABLE_QUANTITY`는 **무효**. 상장폐지·리스팅 종료 제외 종목은 모두 "구매 가능"으로 간주한다.
# - 응답시간 기준은 비공개, **300초 초과 시 미응답 처리**. 늦더라도 300초 내 응답과는 점수 차등.

# %%
import json
import re
from pathlib import Path

import pandas as pd

pd.set_option("display.max_columns", 60)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 60)

# 실행 위치(노트북 디렉터리 or 리포 루트)와 무관하게 data/csv를 찾는다
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "csv").is_dir())
CSV = ROOT / "data" / "csv"
print("ROOT:", ROOT)


def R(name):
    """모든 CSV는 문자열로 읽고 빈 문자열을 결측으로 취급한다."""
    return pd.read_csv(CSV / name, dtype=str, keep_default_na=False, encoding="utf-8-sig")


bond = R("PRBD01N001_bond_kr_master_20260824.csv")
etf_kr_all = R("PREF01N001_etf_kr_master_20260824.csv")
etf_gl = R("PREF02N001_etf_gl_master_20260824.csv")
fund_raw = R("PRFD01N001_fund_pub_master_20260824.csv")

# 08-24 배포본은 itm_no가 단독 유일키다. dedup은 무해한 no-op으로 남겨 방어한다.
fund = fund_raw.drop_duplicates("itm_no").reset_index(drop=True)

# 국내ETF 마스터에는 ETN이 섞여 있다
etf_kr = etf_kr_all[etf_kr_all.pd_grp_no == "ETF"].reset_index(drop=True)
etn_kr = etf_kr_all[etf_kr_all.pd_grp_no == "ETN"].reset_index(drop=True)

lseg = json.loads((ROOT / "data" / "lseg_static_metadata.json").read_text(encoding="utf-8"))
theme_list = json.loads((ROOT / "data" / "theme_list.json").read_text(encoding="utf-8"))

pd.DataFrame(
    [
        ("bond_kr", len(bond), bond.pd_no.nunique()),
        ("etf_kr(ETF)", len(etf_kr), etf_kr.pd_itm_no.nunique()),
        ("etf_kr(ETN)", len(etn_kr), etn_kr.pd_itm_no.nunique()),
        ("etf_gl", len(etf_gl), etf_gl.pd_itm_no.nunique()),
        ("fund_pub(raw)", len(fund_raw), fund_raw.itm_no.nunique()),
        ("fund_pub(dedup)", len(fund), fund.itm_no.nunique()),
        ("lseg_static", len(lseg), len(lseg)),
        ("theme_list", len(theme_list), len(theme_list)),
    ],
    columns=["dataset", "rows", "unique_key"],
)

# %% [markdown]
# 그레인 재검증: 08-24 배포본에서 `itm_no`가 단독 유일키인지, 채권 그레인이 무엇인지 확인한다.

# %%
print("fund itm_no 단독 유일키 :", fund_raw.itm_no.is_unique, "(07-11: False)")
print("fund dedup 손실 행       :", len(fund_raw) - len(fund))
print()
print("bond pd_no 단독 유일키   :", bond.pd_no.is_unique, "(07-11: True)")
print("bond (pd_no,pd_exg_mkt,info_seq) 중복:", int(bond.duplicated(["pd_no", "pd_exg_mkt", "info_seq"]).sum()))
print("bond 고유 종목(pd_no)    :", bond.pd_no.nunique(), "/", len(bond), "행")

# %% [markdown]
# > **시사점:** 두 도메인의 그레인이 **정반대로 바뀌었다.** 공모펀드는 롱포맷이 해소되어 1행=1펀드가 되었고, 국내채권은 반대로 `pd_no`가 유일키에서 내려와 **`(pd_no, pd_exg_mkt, info_seq)`** 가 유일키가 되었다(같은 채권이 장내/장외로 이중 게시). 교차 집계에서 "상품 개수"를 셀 때 **채권만 `DISTINCT pd_no`가 필요**하다.

# %% [markdown]
# ---
# ## 1. LSEG 정적 메타데이터 ↔ 국내ETF 매칭 (최우선)
#
# LSEG 키는 `'0028X0'` 같은 6자리, ETF 마스터는 `pd_itm_no_ma = 'A305080'` (7자리).
# 매칭 규칙 후보를 실험으로 비교한다.

# %%
K = set(lseg)
ma = etf_kr_all.pd_itm_no_ma

hypotheses = {
    "H1 pd_itm_no_ma 원본": set(ma),
    "H2 선두 1글자 제거 ma[1:]": set(ma.str[1:]),
    "H3 뒤 6자리 ma[-6:]": set(ma.str[-6:]),
    "H4 pd_itm_no 원본": set(etf_kr_all.pd_itm_no),
    "H5 pd_itm_no[3:9]": set(etf_kr_all.pd_itm_no.str[3:9]),
    "H6 'A'+lseg키 vs ma": set(ma),  # 역방향: 아래에서 별도 계산
}
rows = []
for name, s in hypotheses.items():
    hit = len({"A" + k for k in K} & s) if name.startswith("H6") else len(K & s)
    rows.append((name, hit, round(hit / len(K) * 100, 1)))
hyp_df = pd.DataFrame(rows, columns=["가설", "매칭된 lseg 키 수", "lseg 커버율(%)"])
hyp_df

# %% [markdown]
# > **시사점:** `pd_itm_no_ma`의 선두 1글자(시장구분 접두어 A=ETF, Q=ETN)를 떼면 LSEG 키와 정확히 일치한다. 확정 규칙: **`lseg_key == pd_itm_no_ma[1:]`** (= 표준 단축코드 6자리).

# %%
# 확정 규칙 적용
etf_kr = etf_kr.assign(lseg_key=etf_kr.pd_itm_no_ma.str[1:])
etn_kr = etn_kr.assign(lseg_key=etn_kr.pd_itm_no_ma.str[1:])
etf_kr["has_lseg"] = etf_kr.lseg_key.isin(K)

cov = pd.DataFrame(
    [
        ("lseg -> etf_kr(ETF)", len(K), int(etf_kr.has_lseg.sum()), len(K) - len(K & set(etf_kr.lseg_key))),
        ("etf_kr(ETF) -> lseg", len(etf_kr), int(etf_kr.has_lseg.sum()), int((~etf_kr.has_lseg).sum())),
        ("etf_kr(ETN) -> lseg", len(etn_kr), int(etn_kr.lseg_key.isin(K).sum()), int((~etn_kr.lseg_key.isin(K)).sum())),
    ],
    columns=["방향", "전체", "매칭", "미매칭"],
)
cov["매칭률(%)"] = (cov.매칭 / cov.전체 * 100).round(1)
cov

# %% [markdown]
# > **시사점:** LSEG 1,099건은 **100% 국내ETF에 붙는다**(고아 키 0). 역으로 ETF 1,202종 중 91.4%가 커버되고, ETN 532종은 0건 — LSEG는 ETF 전용 소스다. 온톨로지에서 ETN은 별도 클래스로 분리해야 메타데이터 결측이 설명된다.

# %% [markdown]
# ### 1-1. 결측 보완 효과 (cu_charge_rt / cu_base_index)

# %%
lseg_df = pd.DataFrame(
    [
        {"lseg_key": k, "ter": v.get("ter"), "replication": v.get("replication"),
         "base_market": v.get("base_market"), "base_asset": v.get("base_asset"),
         "hedge_type": v.get("hedge_type"), "themes": v.get("themes") or []}
        for k, v in lseg.items()
    ]
)
m = etf_kr.merge(lseg_df, on="lseg_key", how="left")
# 미매칭 행의 themes는 NaN -> 빈 리스트로 정규화
m["themes"] = m.themes.map(lambda t: t if isinstance(t, list) else [])

n = len(m)
fill = []
for col, src in [("cu_charge_rt", "ter"), ("cu_base_index", None)]:
    miss = m[col] == ""
    if src:
        recovered = int((miss & m[src].notna()).sum())
    else:
        recovered = 0  # lseg에는 지수명 필드가 없음
    fill.append((col, int(miss.sum()), round(miss.mean() * 100, 1), recovered,
                 round((miss.sum() - recovered) / n * 100, 1)))
fill_df = pd.DataFrame(fill, columns=["컬럼", "결측 건수", "결측률(%)", "lseg로 보완", "보완 후 결측률(%)"])

# lseg로 새로 부여 가능한 속성 커버리지
attr = pd.DataFrame(
    [(c, int(m[c].notna().sum() if c != "themes" else m.themes.map(len).gt(0).sum()),
      round((m[c].notna().sum() if c != "themes" else m.themes.map(len).gt(0).sum()) / n * 100, 1))
     for c in ["ter", "replication", "base_market", "base_asset", "hedge_type", "themes"]],
    columns=["lseg 속성", "부여 가능 ETF 수", "ETF 커버율(%)"],
)
display(fill_df)
display(attr)

# %% [markdown]
# ### 1-2. lseg `ter` vs 기존 `cu_charge_rt` 값 일치 검증 (둘 다 존재하는 건)

# %%
both = m[(m.cu_charge_rt != "") & m.ter.notna()].copy()
both["cu_charge_rt_num"] = pd.to_numeric(both.cu_charge_rt, errors="coerce")
both["diff"] = (both.cu_charge_rt_num - both.ter).abs()
agree = pd.DataFrame(
    [
        ("둘 다 존재", len(both)),
        ("완전 일치", int((both["diff"] < 1e-9).sum())),
        ("오차 <= 0.01%p", int((both["diff"] <= 0.01).sum())),
        ("불일치 > 0.01%p", int((both["diff"] > 0.01).sum())),
    ],
    columns=["구분", "건수"],
)
display(agree)
display(both.nlargest(5, "diff")[["pd_abrv_nm", "cu_charge_rt_num", "ter", "diff"]])

# %% [markdown]
# > **시사점:** `cu_charge_rt` 결측 81.9%(985건)를 LSEG `ter`로 대부분 메꿔 결측률을 한 자릿수로 낮춘다. 다만 두 값이 동시에 있는 구간에서 **불일치가 존재**하므로(기존 값 다수가 `0`인 더미), 온톨로지에서는 `ter`를 우선 소스로 삼고 `cu_charge_rt`는 출처 표기와 함께 보조로 둔다. `cu_base_index`(결측 95.2%)는 LSEG에 지수명 필드가 없어 **보완 불가** — 지수 엔티티는 별도 소스가 필요하다.

# %% [markdown]
# ---
# ## 2. 공모펀드 ↔ 국내ETF 중복 상품
#
# ETF는 법적으로 펀드라 공모펀드 마스터에도 등재된다. 조인 키 후보를 탐색한다.

# %%
etf_codes = set(etf_kr.pd_itm_no)
key_test = pd.DataFrame(
    [(c, int(fund[c].isin(etf_codes).sum())) for c in
     ["itm_no", "ksd_itm_no", "std_itm_no", "fss_itm_no", "rptt_ksd_itm_no"]],
    columns=["펀드 컬럼", "etf_kr.pd_itm_no와 일치"],
)
key_test

# %% [markdown]
# > **시사점:** 펀드의 `ksd_itm_no`(예탁원 종목코드)가 ETF의 `pd_itm_no`(KR7...)와 직접 일치한다. **명칭·순자산 휴리스틱이 아니라 결정적 조인 키가 존재**한다.

# %%
dup = fund.merge(etf_kr, left_on="ksd_itm_no", right_on="pd_itm_no", how="inner")
fa = pd.to_numeric(dup.fd_nast_suma, errors="coerce").round(0)
ea = pd.to_numeric(dup.pd_net_tamt, errors="coerce").round(0)

# 대조군: 명칭 정규화 / 순자산 일치 휴리스틱
norm = lambda s: re.sub(r"[^0-9A-Z가-힣]", "", str(s).upper())
name_hit = len(set(fund.itm_abrv_nm.map(norm)) & set(etf_kr.pd_abrv_nm.map(norm)))
nast_hit = len(set(pd.to_numeric(fund.fd_nast_suma, errors="coerce").round(0).dropna())
               & set(pd.to_numeric(etf_kr.pd_net_tamt, errors="coerce").round(0).dropna()))

pd.DataFrame(
    [
        ("ksd_itm_no 직접 조인 (확정)", len(dup)),
        ("  └ 순자산 완전 일치", int((fa == ea).sum())),
        ("정규화 약어명 일치 (휴리스틱)", name_hit),
        ("순자산 값 일치 (휴리스틱)", nast_hit),
        ("ksd_itm_no가 KR7...인 펀드 (ETF 마스터 미등재 포함)", int(fund.ksd_itm_no.str.startswith("KR7").sum())),
    ],
    columns=["매칭 방식", "건수"],
)

# %%
display(dup[["itm_no", "itm_abrv_nm", "ksd_itm_no", "pd_abrv_nm", "fd_nast_suma", "pd_net_tamt"]].head(8))

# %% [markdown]
# ### 2-1. 미처리 시 이중계상 — "국내 주식형 상품 순자산 합계"

# %%
eq_fund = fund[fund.or_attr_desc == "주식형"]
eq_fund_sum = pd.to_numeric(eq_fund.fd_nast_suma, errors="coerce").sum()
etf_sum = pd.to_numeric(etf_kr.pd_net_tamt, errors="coerce").sum()
dup_eq = dup[dup.or_attr_desc == "주식형"]
dbl = pd.to_numeric(dup_eq.fd_nast_suma, errors="coerce").sum()

pd.DataFrame(
    [
        ("공모펀드 주식형 순자산 합", eq_fund_sum),
        ("국내ETF 순자산 합", etf_sum),
        ("단순 합산 (중복 미처리)", eq_fund_sum + etf_sum),
        ("이중계상분 (중복 상품)", dbl),
        ("중복 제거 후 합계", eq_fund_sum + etf_sum - dbl),
    ],
    columns=["항목", "순자산(원)"],
).assign(순자산_조원=lambda d: (d["순자산(원)"] / 1e12).round(1))

# %% [markdown]
# > **시사점:** ETF 47종이 펀드로도 등재되어 있고 순자산이 **47/47 완전 일치**한다. 온톨로지에서는 `ksd_itm_no`를 `owl:sameAs`(또는 `:hasListedShareClass`) 링크로 명시해, 집계 질의 시 중복 제거가 추론으로 처리되게 해야 한다. 이 47종은 대형 ETF에 몰려 있어 금액 기준 이중계상 규모가 크다.

# %% [markdown]
# ---
# ## 3. 지수(Index) 엔티티 통합

# %%
SENTINEL = ["Index is not provided by Management Company", "Index is not available on Lipper Database"]


def norm_idx(s):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s.upper()


# ★ 08-24: etf_kr은 cu_base_index(95.5% 결측) 대신 신설 ref_base_index(2.2% 결측)를 쓴다.
src = {
    "fund.bmrk_nm": fund.bmrk_nm,
    "etf_kr.cu_base_index(구)": etf_kr.cu_base_index,
    "etf_kr.ref_base_index(신)": etf_kr.ref_base_index,
    "etf_gl.cu_base_index": etf_gl.cu_base_index,
}
sets, rows = {}, []
for name, s in src.items():
    raw = s[(s != "") & (~s.isin(SENTINEL))]
    n_set = set(raw.map(norm_idx))
    sets[name] = n_set
    rows.append((name, len(s), int((s == "").sum()), int(s.isin(SENTINEL).sum()), raw.nunique(), len(n_set)))
idx_df = pd.DataFrame(rows, columns=["소스", "행수", "결측", "sentinel", "정규화 전 고유", "정규화 후 고유"])
display(idx_df)

a, b_old, b, c = (sets["fund.bmrk_nm"], sets["etf_kr.cu_base_index(구)"],
                  sets["etf_kr.ref_base_index(신)"], sets["etf_gl.cu_base_index"])
overlap = pd.DataFrame(
    [
        ("fund ∩ etf_kr (구 cu_base_index)", len(a & b_old)),
        ("fund ∩ etf_kr (신 ref_base_index)", len(a & b)),
        ("fund ∩ etf_gl", len(a & c)),
        ("etf_kr(신) ∩ etf_gl", len(b & c)),
        ("3자 교집합(신 기준)", len(a & b & c)),
        ("합집합 (지수 노드 후보, 신 기준)", len(a | b | c)),
    ],
    columns=["관계", "고유 지수 수"],
)
display(overlap)
print("교집합 예시(fund ∩ etf_kr 신):", sorted(a & b)[:8])
print("교집합 예시(etf_kr 신 ∩ etf_gl):", sorted(b & c)[:8])

# %% [markdown]
# > **시사점(08-24):** 국내ETF 기초지수가 `cu_base_index`(유효 19종) → **`ref_base_index`(905종, 결측 2.2%)** 로 바뀌면서 지수 엔티티의 공급원이 하나 더 생겼다. 07-11 배포본에서 "국내ETF는 기초지수 95% 결측이라 지수 연결 사실상 불가"로 판정했던 부분이 **해소**된다. 도메인 간 교집합도 `etf_kr ∩ etf_gl`이 0종 → 실측치로 늘었다.
# >
# > 다만 **별칭 매핑 필요성 자체는 그대로다.** 국내(`KOSPI200`)와 해외(`S&P 500 TR`) 표기 체계가 다르고, `etf_gl.cu_base_index`는 여전히 **2,920행(48.4%)이 sentinel 문자열**이라 결측 처리해야 한다. 펀드 `bmrk_nm`은 합성 벤치마크(`A 50% + B 50%`) 문자열이라 분해가 선행되어야 한다. `.ttl`에서는 `:Index` 노드 + `skos:altLabel` + `:BenchmarkComposition` 중간 노드 설계를 유지한다.

# %% [markdown]
# ---
# ## 4. 운용사(AssetManager) 엔티티 통합

# %%
SUFFIX = r"(주식회사|\(주\)|㈜|증권|자산운용|투자신탁운용|운용|Inc\.?|Ltd\.?|LLC|L\.P\.?|Corp\.?|S\.A\.?|plc)"


def norm_co(s):
    s = str(s).strip()
    # 상품명이 운용사 컬럼에 잘못 들어간 경우(데이터 오염) 탐지용 길이 컷
    s = re.sub(r"\s+", " ", s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(SUFFIX + r"\s*$", "", s).strip()
    return s.upper()


# 운용사 컬럼에 상품명이 그대로 들어간 오염 행 (언어 무관 판정)
is_dirty = lambda s: s.str.contains("상장지수투자신탁|투자신탁|ETF Trust|Fund$", regex=True)
dirty = is_dirty(etf_kr_all.cu_fund_mgmt_co)
co_rows = []
for name, s in [("etf_kr.cu_fund_mgmt_co", etf_kr_all.cu_fund_mgmt_co),
                ("etf_gl.cu_fund_mgmt_co", etf_gl.cu_fund_mgmt_co)]:
    v = s[s != ""]
    co_rows.append((name, v.nunique(), v.map(norm_co).nunique(), int(is_dirty(v).sum())))
co_rows.append(("fund.or_co_xtn_itt_cd (코드)", fund.or_co_xtn_itt_cd.nunique(), fund.or_co_xtn_itt_cd.nunique(), 0))
co_rows.append(("fund.mtco_itm_no (코드)", fund.mtco_itm_no.nunique(), fund.mtco_itm_no.nunique(), 0))
co_df = pd.DataFrame(co_rows, columns=["소스", "정규화 전 고유", "정규화 후 고유", "오염 의심(상품명 혼입)"])
display(co_df)

print("오염 사례:", etf_kr_all.loc[dirty, "cu_fund_mgmt_co"].head(3).tolist())
print("\n정규화 전후 예시:")
ex = ["메리츠증권 주식회사", "KB증권(주)", "삼성", "미래에셋TIGER", "NH-Amundi", "iM에셋"]
display(pd.DataFrame({"원본": ex, "정규화": [norm_co(x) for x in ex]}))

# %% [markdown]
# > **시사점:** `cu_fund_mgmt_co`는 **일부 행에 상품명이 그대로 들어간 오염 컬럼**이라 고유값 97종이 실제 운용사 수가 아니다. 접미사 제거 정규화로 표기 변형(`메리츠증권 주식회사`→`메리츠`)은 접히지만, `미래에셋` vs `미래에셋TIGER`(브랜드)처럼 의미가 다른 값이 섞여 자동 통합만으로는 위험하다. 펀드 쪽은 **코드(`or_co_xtn_itt_cd`, 68종)** 라 이름-코드 매핑 테이블을 수작업으로 1회 구축하는 편이 확실하다.

# %% [markdown]
# ---
# ## 5. 기업(Company) 접점 — 채권 발행사 ↔ ETF/펀드/테마

# %%
def norm_corp(s):
    s = re.sub(r"\(주\)|주식회사|㈜|\s+", "", str(s))
    return s


issuers = bond.pd_pbcm[bond.pd_pbcm != ""].map(norm_corp)
iss_uniq = sorted(set(issuers) - {""})
print("채권 발행사 고유(정규화 후):", len(iss_uniq), "/ 원본:", bond.pd_pbcm.nunique())

name_blob = " ".join(etf_kr.pd_nm) + " " + " ".join(fund.itm_nm) + " " + " ".join(etf_gl.pd_nm)
theme_blob = " ".join(theme_list)

hits = [(c, name_blob.count(c)) for c in iss_uniq if len(c) >= 3 and c in name_blob]
hits_df = pd.DataFrame(sorted(hits, key=lambda x: -x[1]), columns=["발행사(정규화)", "상품명 내 등장 횟수"])
print("상품명에 등장하는 채권 발행사 수:", len(hits_df), f"({len(hits_df)/len(iss_uniq)*100:.2f}%)")
display(hits_df.head(15))
print("테마명에 등장하는 발행사:", [c for c in iss_uniq if len(c) >= 3 and c in theme_blob])

# %% [markdown]
# > **시사점:** 채권 발행사 7,994종 중 ETF/펀드 상품명에 등장하는 것은 **25종(0.31%)** 뿐이고, 그마저 `OCI`·`디에스`·`피닉스`처럼 **부분문자열 오탐**이 대부분이다(테마명 등장은 0종). ETF/펀드에 **구성종목(holdings) 데이터가 없어** 기업 노드로 채권-ETF-펀드를 잇는 것은 현재 데이터만으로 **실현 불가**다. `:Company` 노드는 채권 발행사(`pd_pbcm`)에 한정해 세우고, ETF/펀드와의 연결은 외부 구성종목 소스 확보를 전제로 별도 단계로 미룬다.

# %% [markdown]
# ---
# ## 6. axis_sample 라벨 재현율
#
# 주최측 분류 라벨 100행을 마스터 컬럼 기반 규칙으로 재현해 본다.

# %%
def recall_table(sample, master, left, right, rules, domain):
    # 샘플에서 axis_*와 조인키만 남겨 마스터 컬럼과의 이름 충돌(_x/_y)을 피한다
    s = sample[[left] + [c for c in sample.columns if c.startswith("axis_")]]
    mg = s.merge(master, left_on=left, right_on=right, how="inner").drop_duplicates(left)
    # axis_sample은 07-11 배포본 기준이라 08-24 마스터에 없는 종목이 있다(채권 만기 도래분 등).
    if len(mg) != len(s):
        print(f"[{domain}] axis 샘플 {len(s)}행 중 {len(mg)}행만 08-24 마스터에 존재 → 그 {len(mg)}행 기준 재현율")
    out = []
    for axis, (fn, need) in rules.items():
        if fn is None:
            out.append((domain, axis, None, "N/A", need))
            continue
        pred = mg.apply(fn, axis=1)
        acc = (pred == mg[axis]).mean() * 100
        wrong = mg.loc[pred != mg[axis], axis].value_counts().head(2).to_dict()
        out.append((domain, axis, round(acc, 1), str(wrong) if wrong else "-", need))
    return pd.DataFrame(out, columns=["도메인", "축", "재현율(%)", "주요 오분류", "부족한 정보"])


# --- bond ---
# axis_sample은 08-24 배포본에 없다. 07-11 파일을 그대로 쓴다.
b_s = R("PRBD01N001_bond_kr_axis_sample_20260711.csv")


def b_maturity(r):
    d = (pd.to_datetime(r.mat_dt, errors="coerce") - pd.to_datetime(r.isu_dt, errors="coerce"))
    y = d.days / 365.25 if pd.notna(d) else None
    if y is None:
        return ""
    return "ShortTerm" if y <= 1 else ("MidTerm" if y < 5 else "LongTerm")


def b_rating(r):
    g = r.crd_grd
    if g == "":
        return "NotRated"
    return {"AAA": "AAAGrade"}.get(g, ("AAGrade" if g.startswith("AA") else
                                       ("AGrade" if g.startswith("A") else "BelowAGrade")))


b_rules = {
    "axis_currency": (lambda r: r.curr_cd, "-"),
    "axis_issuanceMarket": (lambda r: "DomesticMarket" if r.pd_ctry_cd == "KR" else "ForeignMarket", "-"),
    "axis_creditRating": (b_rating, "-"),
    "axis_issuerType": (lambda r: {"회사채": "CorporateBond", "특수채": "SpecialBond",
                                   "국공채": "GovernmentBond"}.get(r.std_pd_mcls_nm, "CorporateBond"), "지방채/특수채 세분 기준"),
    "axis_maturityClass": (b_maturity, "-"),
    "axis_collateralType": (lambda r: ("Subordinated" if "후순위" in r.pd_nm else
                                       ("Secured" if r.bd_knd == "유동화회사채" else
                                        ("Guaranteed" if "보증" in r.pd_nm else "Unsecured"))), "담보/보증 구조 플래그"),
    # ★ 08-24 신설 bd_inrt_tcd(고정/변동) + bd_intp_tcd(이표/복리/할인)로 직접 판정
    "axis_couponType": (lambda r: ("FloatingCoupon" if r.bd_inrt_tcd == "변동금리" else
                                   ("ZeroCoupon" if r.bd_intp_tcd in ("할인채", "복리채") or r.srfc_irt == "0"
                                    else "FixedCoupon")),
                        "-"),
    "axis_issuerCategory": (None, "발행사 업종/섹터 분류 (금융 vs 비금융, 정부기관 여부)"),
}
bond_rec = recall_table(b_s, bond, "pd_no", "pd_no", b_rules, "bond_kr")

# --- etf_kr ---
e_s = R("PREF01N001_etf_kr_axis_sample_20260711.csv")
# axis 샘플 100행에는 ETN이 섞여 있으므로 ETF+ETN 전체 마스터에 붙인다
_sample_grp = etf_kr_all[etf_kr_all.pd_itm_no.isin(set(e_s.pd_itm_no))].pd_grp_no.value_counts().to_dict()
print("etf_kr axis 샘플 구성:", _sample_grp)
etf_lseg = (etf_kr_all.assign(lseg_key=etf_kr_all.pd_itm_no_ma.str[1:])
            .merge(lseg_df, on="lseg_key", how="left"))
etf_lseg["base_market"] = etf_lseg.base_market.fillna("")
etf_lseg["base_asset"] = etf_lseg.base_asset.fillna("")

LEV = {"2": "Leveraged2X", "1": "Standard", "-1": "Inverse1X", "-2": "Inverse2X"}
e_rules = {
    "axis_leverageType": (lambda r: LEV.get(r.cu_lev_fector, "Standard"), "-"),
    "axis_strategy": (lambda r: "Active" if r.cu_strtegy == "액티브" else "Passive", "-"),
    "axis_replicationMethod": (lambda r: "Synthetic" if r.cu_strtegy == "합성복제" else "Physical", "-"),
    # ★ LSEG 대신 마스터 자체 컬럼(wu_inv_rgn / wu_inv_ast_type)으로 판정 — 결측 0%
    "axis_region": (lambda r: "Domestic" if r.wu_inv_rgn == "국내" else "Overseas", "-"),
    "axis_assetType": (lambda r: {"주식": "Equity", "채권": "Bond", "원자재": "Commodity",
                                  "통화": "Currency", "혼합자산": "MixedAsset", "단기자금": "MoneyMarket",
                                  "부동산": "RealEstate", "대체투자": "Alternative"}.get(r.wu_inv_ast_type, "Equity"),
                       "대체투자/기타의 주최측 대응값 불명"),
    "axis_distributionType": (lambda r: "TotalReturn" if re.search(r"\bTR\b|Total ?Return", r.pd_nm, re.I) else "Distributing", "-"),
    # ★ 08-24 ref_base_index 신설 — 지수명으로 구성 범위를 근사
    "axis_underlyingScope": (None, "기초지수 구성종목 수 (ref_base_index로 지수명은 확보, 구성 범위는 여전히 없음)"),
}
etf_rec = recall_table(e_s, etf_lseg, "pd_itm_no", "pd_itm_no", e_rules, "etf_kr")

# --- fund_pub ---
f_s = R("PRFD01N001_fund_pub_axis_sample_20260711.csv")
FT = {"주식형": "SecuritiesFund", "채권형": "SecuritiesFund", "주식혼합": "MixedAssetsFund",
      "채권혼합": "MixedAssetsFund", "MMF": "MoneyMarketFund", "재간접": "SecuritiesFund",
      "혼합자산": "MixedAssetsFund", "부동산": "RealEstateFund", "특별자산": "SpecialAssetsFund"}
f_rules = {
    "axis_investorEligibility": (lambda r: "PublicOffering" if r.prvo_pbff_desc == "공모" else "PrivateOffering", "-"),
    "axis_listingType": (lambda r: "Listed" if str(r.ksd_itm_no).startswith("KR7") else "Unlisted", "-"),
    "axis_fundType": (lambda r: FT.get(r.or_attr_desc, "SecuritiesFund"), "-"),
    # ⚠️ 08-24 han_clas_nm·prfd_attr_cds(M111) 어느 쪽도 주최측 라벨을 못 맞힌다(둘 다 47%).
    # 항상 SingleClass로 찍는 다수결 베이스라인(64%)보다도 낮아, 신설 컬럼은 이 축의 신호가 아니다.
    # 07-11과 동일한 명칭 정규식(55%)을 유지하고 재현 불가로 표시한다.
    "axis_classDifferentiation": (lambda r: "MultiClass" if re.search(r"종류형|클래스|종류\s*[A-Za-z]", str(r.itm_nm))
                                  else "SingleClass",
                                  "★ han_clas_nm(47%)·M111(47%) 모두 다수결 베이스라인 64% 미달 — 신호 없음"),
    # ★ 08-24 prfd_attr_cds 라벨(C103=개방 / C102=단위 / C101=추가)로 판정
    "axis_redemptionType": (lambda r: "ClosedEnded" if "C104" in str(r.prfd_attr_cds) else "OpenEnded",
                            "속성코드 0개 펀드(52.4%)는 판정 불가 → 기본값 OpenEnded"),
    "axis_issuanceType": (lambda r: "UnitType" if "C102" in str(r.prfd_attr_cds) else "AdditionalType",
                          "속성코드 0개 펀드(52.4%)는 판정 불가 → 기본값 AdditionalType"),
}
fund_rec = recall_table(f_s, fund, "itm_no", "itm_no", f_rules, "fund_pub")

axis_all = pd.concat([bond_rec, etf_rec, fund_rec], ignore_index=True)
axis_all

# %% [markdown]
# > **시사점(08-24):** 재현 불가 축이 **4개 → 2개**로 줄었다. `axis_redemptionType`(80%)·`axis_issuanceType`(93%)은 신설 `prfd_attr_cds`의 코드 라벨(`C103 개방`·`C101 추가`·`C102 단위`)로 재현되고, `axis_couponType`은 채권 `bd_inrt_tcd`·`bd_intp_tcd`로 97.1%가 된다. 남은 재현 불가는 **`axis_issuerCategory`(발행사 업종)와 `axis_underlyingScope`(지수 구성 범위)** 둘뿐이다.
# >
# > ⚠️ 반대로 **`axis_classDifferentiation`은 신설 컬럼으로도 풀리지 않았다.** `han_clas_nm` 존재 여부(47%)와 `prfd_attr_cds`의 `M111`(종류형 클래스펀드, 47%) 모두 **"항상 SingleClass"로 찍는 다수결 베이스라인 64%보다 낮다** — 즉 주최측 라벨이 뜻하는 '클래스 구분'은 이 컬럼들이 가리키는 개념과 다르다. 이 축은 **컬럼이 없어서가 아니라 정의가 달라서 재현 불가**이며, 근거 없이 답하면 오답이 된다.
# >
# > 07-11 판정: 마스터 컬럼과 1:1 대응하는 축(레버리지·전략·복제·담보·신용등급·상장여부·공모여부)은 95~100% 재현된다. 반면 4개 축은 원천에 컬럼 자체가 없어 재현 불가다 — 온톨로지에서 외부 소스 보강 또는 LLM 텍스트 추출로 채워야 하는 **파생 속성**으로 분리해 표시해야 한다. 두 가지 함정도 확인했다: (1) `axis_maturityClass`는 잔존만기가 아니라 **발행 시 만기(mat_dt−isu_dt)** 기준이고, (2) `axis_assetType`은 LSEG `base_asset`만으로 70%에 그쳐 MMF·부동산 등 세분 자산군 규칙이 따로 필요하다. 또한 **etf_kr axis 샘플 100행 중 9행이 ETN**이라, ETF 전용 소스(LSEG)에 의존하는 축은 ETN에서 구조적으로 결측된다.

# %% [markdown]
# ---
# ## 7. 평가 질의 커버리지 매트릭스 (최종 산출물)
#
# 먼저 각 질의를 실제 데이터로 시연해 근거를 만든다.

# %% [markdown]
# ### 7-1. (하) "현재 판매 가능한 원화채권 중 AA- 이상"
#
# ⚠️ **주최측 안내에 따라 정의가 바뀌었다.** `BUYABLE_QUANTITY`는 무효이며
# 상장폐지·리스팅 종료 제외 종목은 모두 구매 가능으로 본다(채권에서는 = 만기 미도래).

# %%
ORDER = ["AAA", "AA+", "AA0", "AA", "AA-"]
_mat = pd.to_datetime(bond.mat_dt.where(bond.mat_dt.str.fullmatch(r"\d{8}")), format="%Y%m%d", errors="coerce")
ASOF = pd.Timestamp("2026-08-21")

old_def = bond[(pd.to_numeric(bond.buyable_quantity, errors="coerce").fillna(0) > 0) & (bond.curr_cd == "KRW")]
new_def = bond[((_mat - ASOF).dt.days > 0) & (bond.curr_cd == "KRW")]
print(f"[폐기] buyable_quantity>0 정의 : {len(old_def)}행 / AA-이상 {int(old_def.crd_grd.isin(ORDER).sum())}행")
print(f"[현행] 만기 미도래 정의        : {len(new_def)}행 / 고유 {new_def.pd_no.nunique()}종목")

q1 = new_def[new_def.crd_grd.isin(ORDER)]
print(f"→ 구매가능 원화채권 중 AA- 이상 : {len(q1)}행 / 고유 {q1.pd_no.nunique()}종목")
display(q1.crd_grd.value_counts().reindex(ORDER).fillna(0).astype(int).to_frame("건수"))
display(q1[["pd_no", "pd_nm", "crd_grd", "mat_dt", "applied_yield", "pd_exg_mkt"]].head(5))

# %% [markdown]
# ### 7-2. (중) "국민성장펀드의 구조와 투자전략 동향"

# %%
q2 = fund[fund.itm_nm.str.contains("국민성장")]
print("명칭 매칭:", len(q2), "건")
display(q2[["itm_no", "itm_nm", "or_attr_desc", "bmrk_nm", "fd_nast_suma", "fd_yr1_ern_r"]])

# %% [markdown]
# ### 7-3. (중) "캠브리콘이 편입된 중국 반도체 ETF" / (상) 에코프로 자회사 편입 ETF

# %%
def search_all(kw):
    return {
        "etf_kr.pd_nm": int(etf_kr.pd_nm.str.contains(kw, case=False, regex=False).sum()),
        "etf_gl.pd_nm": int(etf_gl.pd_nm.str.contains(kw, case=False, regex=False).sum()),
        "fund.itm_nm": int(fund.itm_nm.str.contains(kw, case=False, regex=False).sum()),
        "bond.pd_nm": int(bond.pd_nm.str.contains(kw, case=False, regex=False).sum()),
        "theme_list": int(sum(kw.lower() in t.lower() for t in theme_list)),
    }


kws = ["캠브리콘", "Cambricon", "에코프로", "우주항공", "반도체", "중국", "Kimi", "AI로봇", "KODEX"]
display(pd.DataFrame({k: search_all(k) for k in kws}).T)

# %% [markdown]
# ### 7-3b. (교차질의) "삼성전자를 보유한 국내/해외ETF와 공모펀드를 1년 수익률 기준 TOP10"
#
# 주최측이 예시로 든 교차질의 유형. **두 가지 서로 다른 능력**을 동시에 요구한다.
# (a) 구성종목(holdings)으로 상품을 걸러내기 → 원천에 없음
# (b) ETF와 펀드의 1년 수익률을 **하나의 랭킹으로 합치기** → (b)만 따로 실현 가능한지 실측한다.

# %%
# (a) 구성종목 보유 여부로 필터링할 수 있는가
print("보유종목(holdings) 컬럼 탐색:")
for name, dfx in [("etf_kr", etf_kr), ("etf_gl", etf_gl), ("fund", fund)]:
    hits = [c for c in dfx.columns if re.search(r"hold|stk_nm|const|comp|pdf", c, re.I)]
    print(f"  {name:8s} → {hits or '없음'}")
print("\n'삼성전자' 문자열 전 도메인 검색:", search_all("삼성전자") if "search_all" in dir() else "(아래 셀 참조)")

# %%
# (b) 수익률 랭킹 통합 가능성 — 컬럼·단위·기준일이 상품군마다 다른지 확인
ret = pd.DataFrame(
    [
        {"상품군": "국내ETF", "1년수익률 컬럼": "du_er_1y",
         "결측률": round((etf_kr.du_er_1y == "").mean(), 4),
         "기준일 컬럼": "du_upt_dt", "기준일 최빈": etf_kr.du_upt_dt.mode()[0]},
        {"상품군": "해외ETF", "1년수익률 컬럼": "(없음 — du_er_1d만 존재)",
         "결측률": 1.0, "기준일 컬럼": "du_upt_dt", "기준일 최빈": etf_gl.du_upt_dt.mode()[0]},
        {"상품군": "공모펀드", "1년수익률 컬럼": "fd_yr1_ern_r",
         "결측률": round((fund.fd_yr1_ern_r == "").mean(), 4),
         "기준일 컬럼": "fd_price_bas_dt", "기준일 최빈": fund.fd_price_bas_dt.mode()[0]},
    ]
)
display(ret)
print("해외ETF의 수익률 계열 컬럼:", [c for c in etf_gl.columns if "er_" in c])

# %%
# 실제로 합쳐본다: 국내ETF + 공모펀드 1년 수익률 통합 TOP10
_etf_r = etf_kr.loc[etf_kr.du_er_1y != "", ["pd_itm_no", "pd_abrv_nm", "du_er_1y"]].copy()
_etf_r.columns = ["id", "name", "ret1y"]; _etf_r["상품군"] = "국내ETF"
_fnd_r = fund.loc[(fund.fd_yr1_ern_r != "") & (fund.prvo_pbff_desc == "공모")
                  & (fund.sale_yn == "판매중"), ["itm_no", "itm_nm", "fd_yr1_ern_r"]].copy()
_fnd_r.columns = ["id", "name", "ret1y"]; _fnd_r["상품군"] = "공모펀드"
uni = pd.concat([_etf_r, _fnd_r], ignore_index=True)
uni["ret1y"] = pd.to_numeric(uni.ret1y, errors="coerce")
print("통합 모집단:", len(uni), "(국내ETF %d + 공모펀드 %d)" % (len(_etf_r), len(_fnd_r)))
display(uni.nlargest(10, "ret1y"))

# %% [markdown]
# > **시사점(교차질의):** 예시 질의를 두 층으로 쪼개면 **(b) 상품군 통합 랭킹은 지금 데이터로 된다.** 국내ETF `du_er_1y`와 공모펀드 `fd_yr1_ern_r`은 둘 다 % 단위 1년 수익률이고 기준일도 2026-08 로 근접해 하나의 랭킹으로 합칠 수 있다. **단 해외ETF에는 1년 수익률 컬럼이 아예 없다**(`du_er_1d` 일간뿐) — "국내/해외ETF와 펀드"를 한 랭킹에 올리려면 **해외ETF 1년 수익률을 외부에서 보강하거나, 답변에서 해외ETF 제외 사실을 명시**해야 한다.
# >
# > **(a) 구성종목 필터는 여전히 불가**다. 세 도메인 어디에도 보유종목 컬럼이 없다. 즉 교차질의의 병목은 "합치기"가 아니라 **holdings**이며, 이는 07-11 배포본의 결론과 동일하다.

# %% [markdown]
# ### 7-4. (상) "최근 6개월 우주항공 테마 연결 이력 ETF" — 테마 이력 존재 여부

# %%
theme_etf = m[m.themes.map(lambda t: "우주항공/방산" in t)]
print("우주항공/방산 테마 ETF:", len(theme_etf))
display(theme_etf[["pd_abrv_nm", "pd_net_tamt", "cu_upt_dt"]].head(5))
print("\nLSEG 메타에 시점 컬럼 존재 여부:", [k for k in next(iter(lseg.values()))])
print("ETF 마스터 날짜 컬럼:", [c for c in etf_kr.columns if "dt" in c.lower()])

# %% [markdown]
# ### 7-5. [답변불가] "신용등급 AAAA인 채권" — 존재하지 않는 등급 판정

# %%
grades = sorted(set(bond.crd_grd) - {""})
print("데이터상 실재 신용등급 사전 (%d종):" % len(grades))
print(grades)
print("\n'AAAA' 포함 여부:", "AAAA" in grades, "| 매칭 건수:", int((bond.crd_grd == "AAAA").sum()))

# %% [markdown]
# ### 7-6. [답변불가] "KODEX AI로봇 ETF" — 브랜드는 존재하나 상품명 없음

# %%
kodex = etf_kr[etf_kr.pd_abrv_nm.str.startswith("KODEX")]
print("KODEX 브랜드 ETF:", len(kodex), "| 'AI로봇' 정확 명칭:",
      int(etf_kr.pd_nm.str.contains("AI로봇", regex=False).sum()))
print("KODEX 중 로봇/AI 관련 상품:")
display(kodex[kodex.pd_abrv_nm.str.contains("로봇|AI", regex=True)][["pd_itm_no", "pd_abrv_nm"]])

# %% [markdown]
# ### 7-7. 커버리지 매트릭스

# %%
matrix = pd.DataFrame(
    [
        ("(하) 판매가능 원화채권 AA- 이상",
         "bond: mat_dt(만기미도래), curr_cd, crd_grd", "가능",
         "- (주최측 지침으로 buyable_quantity 대신 만기 기준. 모집단 296 → 15,992행)"),
        ("(중) 국민성장펀드 구조·투자전략 동향",
         "fund: itm_nm, or_attr_desc, bmrk_nm, fd_*_ern_r", "부분",
         "투자전략 서술 텍스트(운용보고서) 없음. 구조·수익률만 가능"),
        ("(중) 캠브리콘 편입 중국 반도체 ETF",
         "ETF 구성종목(holdings) + 종목-국가/섹터 매핑", "불가",
         "구성종목 데이터 전무. 명칭·테마 검색 0건"),
        ("(교차) 삼성전자 보유 국내/해외ETF+펀드 1년수익률 TOP10",
         "holdings + du_er_1y + fd_yr1_ern_r 통합 랭킹", "불가",
         "수익률 통합 랭킹은 가능하나 ① holdings 부재 ② 해외ETF에 1년수익률 컬럼 자체가 없음"),
        ("(상) 최근 6개월 우주항공 테마 연결 이력 ETF",
         "lseg.themes + 테마 부여 시점(스냅샷 이력)", "부분",
         "테마 부여는 가능하나 LSEG는 단일 시점 정적 스냅샷 — '연결 이력' 시계열 없음"),
        ("(상) 에코프로 자회사 편입 ETF 중 순자산 큰 상품의 위험요인",
         "구성종목 + 기업 지배구조(모-자회사) + 위험요인 텍스트", "불가",
         "구성종목·지배구조·위험서술 3종 모두 없음. pd_risk_cd는 등급 숫자뿐"),
        ("[불가] 신용등급 AAAA 채권",
         "bond: crd_grd 고유값 사전", "가능",
         "- (실재 등급 사전으로 '존재하지 않는 등급' 판정 가능)"),
        ("[불가] Kimi 관련 투자 상품",
         "전 도메인 pd_nm/itm_nm + theme_list 전수 검색", "가능",
         "- (4개 도메인·176테마 모두 0건 → 근거 있는 부재 증명)"),
        ("[불가] KODEX AI로봇 ETF",
         "etf_kr: pd_abrv_nm 브랜드 접두어 + 정확 명칭", "가능",
         "- (브랜드 존재/상품 부재를 구분해 답변 가능)"),
    ],
    columns=["평가 질의", "필요 데이터·컬럼", "현재 가능 여부", "부족한 것"],
)
matrix

# %%
matrix["현재 가능 여부"].value_counts().to_frame("질의 수")

# %% [markdown]
# > **시사점:** 9개 질의 중 **가능 4 / 부분 2 / 불가 3**. 08-24 배포본이 컬럼을 대폭 보강했는데도 **커버리지 매트릭스의 판정은 하나도 바뀌지 않았다** — 불가 판정의 원인이 전부 **구성종목(holdings)** 이고, 이번 배포본은 holdings를 주지 않았기 때문이다. 주최측이 예시로 든 교차질의도 같은 이유로 불가다.
# >
# > 즉 **P0 외부 데이터는 여전히 holdings 단 하나**이며, 35문항 중 상(上) 난도 10문항 상당수가 여기에 걸릴 가능성이 높다. 온톨로지 확장 우선순위도 그대로다: ① `:holds` 관계(상품→기업) ② 시점 축 ③ 텍스트 문서 노드. 반대로 [답변불가] 5문항 대응은 오히려 쉬워졌다 — 등급 사전(15종)·전수 명칭 검색·브랜드 계층으로 **근거 있는 부재 증명**이 가능하다.

# %% [markdown]
# ---
# ## 종합 요약

# %%
pd.DataFrame(
    [
        ("LSEG ↔ 국내ETF", "lseg_key == pd_itm_no_ma[1:]",
         f"lseg 1,099건 100% 매칭 / ETF {int(etf_kr.has_lseg.sum())}/{len(etf_kr)} ({etf_kr.has_lseg.mean()*100:.1f}%) / ETN 0%"),
        ("펀드 ↔ 국내ETF", "fund.ksd_itm_no == etf.pd_itm_no",
         f"중복 상품 {len(dup)}종, 순자산 {int((fa == ea).sum())}/{len(dup)} 완전 일치"),
        ("지수 통합", "대소문자·공백 정규화", f"노드 후보 {len(a | b | c)}종, 3자 교집합 {len(a & b & c)}종 (별칭 매핑 필요)"),
        ("운용사 통합", "법인 접미사 제거 + 코드 매핑",
         f"etf_kr {etf_kr_all.cu_fund_mgmt_co.nunique()}→{etf_kr_all.cu_fund_mgmt_co[etf_kr_all.cu_fund_mgmt_co!=''].map(norm_co).nunique()}종 (상품명 오염 {int(dirty.sum())}건)"),
        ("기업 접점", "pd_pbcm ↔ 상품명 문자열", f"발행사 {len(iss_uniq)}종 중 상품명 등장 {len(hits_df)}종 → 실현 불가"),
        ("axis 재현", "마스터 컬럼 규칙",
         f"재현 시도 {int(axis_all['재현율(%)'].notna().sum())}축 평균 {axis_all['재현율(%)'].mean():.1f}%, 재현 불가 {int(axis_all['재현율(%)'].isna().sum())}축"),
        ("질의 커버리지", f"{len(matrix)}개 평가 질의(주최측 예시 + 교차질의)",
         " / ".join(f"{k} {v}" for k, v in matrix["현재 가능 여부"].value_counts().items())),
    ],
    columns=["항목", "확정 규칙", "결과"],
)
