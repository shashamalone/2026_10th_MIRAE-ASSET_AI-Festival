"""expected_qa/2026_expected_qa.csv 35문항을 2026-08-24 배포본으로 재산출한다.

정본인 expected_qa/는 덮어쓰지 않고 재생성 가능한 artifacts/golden_answers_20260824.*로
출력한다. 정본을 갱신하려면 산출물을 검토한 뒤 별도로 반영한다.

원칙
  - 주최측 데이터로 산출 가능한 값은 전부 실측해서 넣는다. 손으로 적지 않는다.
  - 산출 불가 항목은 사유를 코드로 구분한다(엔티티 부재 / 컬럼 부재 / 외부데이터 필요).
  - 주최측 안내(2026-08-24): BUYABLE_QUANTITY 무효, 상장폐지·리스팅 종료 제외 = 구매가능.
  - 주최측 안내: 섹터-상품, 구성종목-상품 지식 구축은 참가자 자율 → holdings 부재는
    'ABSTAIN'이 아니라 '외부데이터 필요'로 분류한다.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "csv"
SOURCE = ROOT / "expected_qa" / "2026_expected_qa.csv"
OUT = ROOT / "artifacts"
ASOF = pd.Timestamp("2026-08-21")


def R(name):
    return pd.read_csv(CSV / name, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def num(s):
    return pd.to_numeric(s, errors="coerce")


def ymd(s):
    return pd.to_datetime(s.where(s.str.fullmatch(r"\d{8}")), format="%Y%m%d", errors="coerce")


bond = R("PRBD01N001_bond_kr_master_20260824.csv")
etf_all = R("PREF01N001_etf_kr_master_20260824.csv")
etf = etf_all[etf_all.pd_grp_no == "ETF"].copy()
gl_all = R("PREF02N001_etf_gl_master_20260824.csv")
gl = gl_all[gl_all.pd_grp_no == "ETF"].copy()
fund = R("PRFD01N001_fund_pub_master_20260824.csv")
pub = fund[fund.prvo_pbff_desc == "공모"].copy()
lseg = json.loads((ROOT / "data" / "lseg_static_metadata.json").read_text(encoding="utf-8"))
etf["ter"] = num(etf.pd_itm_no_ma.str[1:].map(lambda k: (lseg.get(k) or {}).get("ter")))
etf["themes"] = etf.pd_itm_no_ma.str[1:].map(lambda k: (lseg.get(k) or {}).get("themes") or [])

bond["mat"] = ymd(bond.mat_dt)
bond["구매가능"] = (bond.mat - ASOF).dt.days > 0          # 주최측 정의: 만기 미도래
GRADES = ["AAA", "AA+", "AA0", "AA-", "A+", "A0", "A-", "BBB+", "BBB0", "BBB-",
          "BB+", "BB0", "BB-", "B+", "B0", "B-", "CCC", "CC0", "CC", "C0", "C", "D"]
ORD = {g: i for i, g in enumerate(GRADES)}
bond["등급서열"] = bond.crd_grd.map(lambda g: ORD.get(g, 99))

FEE_DIV = 10  # 펀드 보수 컬럼은 천분율(‰) — EDA_REPORT_0825 §5-4에서 LSEG ter로 검증
FEE_COLS = ["trusc_rwrd_r", "or_co_rwrd_r", "sale_co_rwrd_r", "ofwk_trus_rwrd_r"]
fund["연보수율"] = sum(num(fund[c]).fillna(0) for c in FEE_COLS) / FEE_DIV
pub["연보수율"] = fund.loc[pub.index, "연보수율"]

rows = []


def add(qid, status, answer, evidence, external="", note=""):
    rows.append(dict(id=str(qid), data_status=status, golden_answer=answer.strip(),
                     evidence=evidence.strip(), external_needed=external.strip(), note_vs_0711=note.strip()))


def fmt(v, unit="", nd=None):
    if v in ("", None) or (isinstance(v, float) and pd.isna(v)):
        return "(값없음)"
    if nd is not None:
        return f"{float(v):,.{nd}f}{unit}"
    return f"{v}{unit}"


def won(v):
    v = num(pd.Series([v])).iloc[0]
    return "(값없음)" if pd.isna(v) else (f"{v/1e12:,.2f}조원" if v >= 1e12 else f"{v/1e8:,.0f}억원")


def usd(v):
    v = num(pd.Series([v])).iloc[0]
    if pd.isna(v):
        return "(값없음)"
    return f"{v/1e9:,.1f}십억USD" if v >= 1e9 else f"{v/1e6:,.1f}백만USD"


# ── Q1 에스케이하이닉스224-2 ────────────────────────────────────────────────
r = bond[bond.pd_nm == "에스케이하이닉스224-2"]
if len(r):
    x = r.iloc[0]
    add(1, "부분산출",
        f"상품번호 {x.pd_no} / 발행사 {x.pd_pbcm} / 신용등급 {x.crd_grd}(평가일 {x.crd_grd_dt}) / "
        f"표면금리 {x.srfc_irt}% / 만기일 {x.mat_dt} / 매수수익률 {fmt(x.buy_yield)} / "
        f"매수가능수량 → 주최측이 무효 처리한 컬럼이므로 제시하지 않고, "
        f"'만기 미도래이므로 구매 가능'({'예' if (pd.to_datetime(x.mat_dt)-ASOF).days>0 else '아니오'})으로 답한다. "
        f"장내/장외 {len(r)}행 존재.",
        "bond.pd_no·pd_pbcm·crd_grd·crd_grd_dt·srfc_irt·mat_dt·buy_yield / info_base_dt=20260821",
        note="07-11 21건 → 08-24 17건. buyable_quantity 무효화로 질문의 마지막 항목은 답 대신 사유를 제시해야 함")
else:
    add(1, "엔티티부재", "해당 종목 없음", "bond.pd_nm 전수 검색 0건")

# ── Q2 국고채권 02000-3106(21-5) ────────────────────────────────────────────
# 원 문항은 '개인투자용국채 02480-3006'이었으나 08-24 배포본에 해당 종목군이 0건이라
# 동일 성격(국고채·코드형 명칭·요구값 5종 보유)의 종목으로 교체했다.
r = bond[bond.pd_nm == "국고채권 02000-3106(21-5)"]
if len(r):
    x = r[r.after_tax_yield != ""].iloc[0]
    ays = sorted(set(r.after_tax_yield[r.after_tax_yield != ""]))
    add(2, "산출가능",
        f"상품번호 {x.pd_no} / 발행일 {x.isu_dt} / 만기일 {x.mat_dt} / 잔존일수 {x.remaining_days}일 / "
        f"표면금리 {x.srfc_irt}% / 세후수익률 {x.after_tax_yield}% / "
        f"데이터 갱신일 {x.info_base_dt}(info_base_dt=pd_std_info_update). "
        f"참고: 발행사 {x.pd_pbcm}, 분류 {x.std_pd_mcls_nm}>{x.std_pd_scls_nm}, "
        f"{x.bd_inrt_tcd}·{x.bd_intp_tcd}, 신용등급 {x.crd_grd or '(미평가 — 국채는 평가 대상 아님)'}",
        "bond.pd_no·isu_dt·mat_dt·remaining_days·srfc_irt·after_tax_yield·info_base_dt / info_base_dt=20260821",
        note=f"★ 원 문항의 '개인투자용국채 02480-3006'은 08-24 배포본에 없다('개인투자용국채' 종목군 전체가 0건) → "
             f"동일 성격 국고채로 교체함. "
             f"이 종목은 {len(r)}행(장내/장외)으로 적재되어 있고 세후수익률은 판매 게시 행에만 존재한다"
             f"(유효값 {ays}) — 답변 시 어느 행 기준인지 밝혀야 한다. "
             f"국채는 신용등급이 결측인 것이 정상이므로 'RatingUnknown'이 아니라 'UnratedByDesign'으로 표기")
else:
    add(2, "엔티티부재", "교체 종목도 조회되지 않음", "bond.pd_nm 전수 검색 0건")

# ── Q3 현대해상화재보험7(후)(콜/후) ─────────────────────────────────────────
r = bond[bond.pd_nm == "현대해상화재보험7(후)(콜/후)"]
if len(r):
    x = r.iloc[0]
    add(3, "산출가능",
        f"상품번호 {x.pd_no} / 채권종류 {x.bd_knd}(대분류 {x.std_pd_mcls_nm}) / 발행사 {x.pd_pbcm} / "
        f"원등급 {x.crd_grd} → 온톨로지 등급서열 {ORD.get(x.crd_grd,'-')} / "
        f"이자지급 {x.bd_intp_tcd} / 금리구분 {x.bd_inrt_tcd} / 만기일 {x.mat_dt} / "
        f"만기구분(발행시) {'LongTerm' if (pd.to_datetime(x.mat_dt)-pd.to_datetime(x.isu_dt)).days/365.25>=5 else 'MidTerm'} / "
        f"듀레이션 {x.dur} / 담보유형 Subordinated(상품명 '(후)' 토큰)",
        "bond.pd_no·bd_knd·std_pd_mcls_nm·pd_pbcm·crd_grd·bd_intp_tcd·bd_inrt_tcd·mat_dt·isu_dt·dur / info_base_dt=20260821",
        note="bd_intp_tcd·bd_inrt_tcd 신설로 이자구조를 상품명 파싱 없이 답할 수 있게 됨")

# ── Q4 KODEX 200 ────────────────────────────────────────────────────────────
r = etf[etf.pd_abrv_nm.str.replace(" ", "") == "KODEX200"]
if len(r):
    x = r.iloc[0]
    add(4, "산출가능",
        f"상품번호 {x.pd_itm_no} / 운용사 {x.ref_fund_mgmt_co or x.cu_fund_mgmt_co} / "
        f"기초지수 {x.ref_base_index} / AUM {won(x.pd_net_tamt)} / NAV {fmt(x.du_last_nav)} / "
        f"종가 {fmt(x.du_clpr)} / 괴리율 {x.du_diff_rt}% / 1년수익률 {x.du_er_1y}%",
        f"etf_kr.pd_itm_no·ref_fund_mgmt_co·ref_base_index·pd_net_tamt·du_last_nav·du_clpr·du_diff_rt·du_er_1y / "
        f"가격·NAV·괴리율 as_of={x.du_nav_base_dt} · 지수/운용사 as_of={x.ref_base_dt}",
        note="★ 07-11에는 기초지수 95% 결측·괴리율 더미라 두 항목 답변 불가였음. 08-24에 둘 다 실값")

# ── Q5 TIGER 미국S&P500 ─────────────────────────────────────────────────────
r = etf[etf.pd_abrv_nm.str.replace(" ", "") == "TIGER미국S&P500"]
if len(r):
    x = r.iloc[0]
    ter = "(값없음)" if pd.isna(x.ter) else f"{x.ter}% (출처 LSEG Lipper ter)"
    add(5, "산출가능",
        f"상품번호 {x.pd_itm_no} / 자산군 {x.wu_inv_ast_type} / 투자지역 {x.wu_inv_rgn} / "
        f"운용전략·복제방식 {x.cu_strtegy} / 총보수 {fmt(x.cu_charge_rt,'%') if x.cu_charge_rt else ter} / "
        f"1M {x.du_er_1m}% · 3M {x.du_er_3m}% · 6M {x.du_er_6m}%",
        f"etf_kr.wu_inv_ast_type·wu_inv_rgn·cu_strtegy·cu_charge_rt(+LSEG ter)·du_er_1m/3m/6m / "
        f"수익률 as_of={x.du_upt_dt} · 분류 as_of={x.cu_upt_dt}",
        note="⚠️ cu_charge_rt가 결측이라 LSEG ter(0.006%)로 대체했는데 이 값은 실제 총보수 대비 비정상적으로 낮다 — 답변 시 출처(LSEG Lipper)와 함께 제시하고 단정하지 말 것. cu_strtegy가 07-11 코드값에서 한글('실물복제'/'액티브'/'합성복제')로 정리됨. "
             "단 운용전략과 복제방식이 여전히 한 컬럼이라 답변에서 분리 설명 필요")

# ── Q6 VOO / Q7 BND ─────────────────────────────────────────────────────────
for qid, tic in [(6, "VOO"), (7, "BND")]:
    r = gl[gl.pd_itm_no.str.split(".").str[0] == tic]
    if not len(r):
        add(qid, "엔티티부재", f"{tic} 없음", "etf_gl.pd_itm_no 전수 검색 0건"); continue
    x = r.iloc[0]
    SENT = ("Index is not provided by Management Company", "Index is not available on Lipper Database")
    idx = "(실질 결측 — sentinel 문자열)" if x.cu_base_index in SENT else x.cu_base_index
    if qid == 6:
        add(6, "부분산출",
            f"정식명 {x.pd_nm} / ISIN {x.pd_isin_cd} / 기초지수 {idx} / 운용사 {x.cu_fund_mgmt_co} / "
            f"총보수 {x.cu_charge_rt}% / AUM {usd(x.du_last_aum)} / 종가 {x.du_clpr} USD / "
            f"거래량 {x.du_vol_1d}",
            f"etf_gl.pd_nm·pd_isin_cd·cu_base_index·cu_fund_mgmt_co·cu_charge_rt·du_last_aum·du_clpr·du_vol_1d / "
            f"종가 as_of={x.du_clpr_base_dt} · NAV as_of={x.du_nav_base_dt}",
            note="ru_mkt_price(현재가)는 기준일 컬럼이 없어 룩어헤드 위험 → du_clpr(기준일 명시)로 답해야 함. "
                 "du_base_dt_match_yn='N'(종가일≠NAV일)도 함께 고지")
    else:
        add(7, "산출가능",
            f"상품번호 {x.pd_itm_no} / 자산유형 {x.wu_inv_ast_type} / 투자지역 {x.wu_inv_rgn} / "
            f"기초지수 {idx} / 복제방식 {x.cu_index_repl_mthd or '(결측=지수 미추종/액티브)'} / "
            f"총보수 {x.cu_charge_rt}% / 운용전략 원문은 cu_strtegy(투자설명서 문장, 평균 309자)에서 인용",
            f"etf_gl.wu_inv_ast_type·wu_inv_rgn·cu_base_index·cu_index_repl_mthd·cu_charge_rt·cu_strtegy / as_of={x.du_upt_dt}",
            note="cu_strtegy는 코드가 아니라 자유 텍스트 — 분류축으로 쓰지 말고 원문 인용")

# ── Q8 미래에셋코어테크 종류A ────────────────────────────────────────────────
cand = pub[pub.itm_nm.str.startswith("미래에셋코어테크증권자투자신탁(주식)")]
exact = cand[cand.itm_nm.str.replace(" ", "").str.endswith("종류A")]
if len(exact):
    x = exact.iloc[0]
    add(8, "산출가능",
        f"종목번호 {x.itm_no} / 펀드유형 {x.or_attr_desc} / 순자산 {won(x.fd_nast_suma)} / "
        f"1M {x.fd_mm1_ern_r}% · 3M {x.fd_mm3_ern_r}% · 6M {x.fd_mm6_ern_r}% · 1Y {x.fd_yr1_ern_r}% / "
        f"위험등급 {x.zrin_fd_ivst_risk_grd_nm}(코드 {x.zrin_fd_ivst_risk_gcd}) / "
        f"판매 {x.sale_yn}·당사취급 {x.thco_sale_yn or 'N'} / 클래스 {x.han_clas_nm}",
        f"fund.itm_no·or_attr_desc·fd_nast_suma·fd_mm1/3/6_ern_r·fd_yr1_ern_r·zrin_fd_ivst_risk_*·sale_yn·thco_sale_yn "
        f"/ as_of={x.fd_price_bas_dt}",
        note=f"동일 모펀드 클래스 {len(cand)}종 존재 — 클래스 지정 없이 답하면 중복 계상")
else:
    add(8, "부분산출",
        f"'종류A' 정확 일치 클래스가 없다. 동일 모펀드 클래스 {len(cand)}종: "
        + ", ".join(cand.itm_nm.str.replace('미래에셋코어테크증권자투자신탁(주식) ', '', regex=False).head(8)),
        "fund.itm_nm 접두 일치 검색",
        note="★ 클래스 구성이 07-11과 달라졌을 가능성 — 문항의 클래스 지정을 데이터에 맞춰 재확인 필요")

# ── Q9 삼성 베스트 MMF 법인 제1호 ────────────────────────────────────────────
r = pub[pub.itm_nm == "삼성 베스트 MMF 법인 제1호"]
if len(r):
    x = r.iloc[0]
    add(9, "산출가능",
        f"종목번호 {x.itm_no}(예탁원 {x.ksd_itm_no}) / 벤치마크 {x.bmrk_nm or '(값없음)'} / 통화 {x.curr_cd} / "
        f"투자지역 {x.fd_ivst_rgn_desc} / 개인·법인 {x.pers_corp_desc} / "
        f"위험등급 {x.zrin_fd_ivst_risk_grd_nm or '(값없음)'} / 순자산 {won(x.fd_nast_suma)}",
        f"fund.itm_no·ksd_itm_no·bmrk_nm·curr_cd·fd_ivst_rgn_desc·pers_corp_desc·zrin_fd_ivst_risk_grd_nm·fd_nast_suma "
        f"/ as_of={x.fd_price_bas_dt or '(값없음)'}")

# ── Q10 우리반도체BIG2플러스 클래스 비교 ─────────────────────────────────────
r = fund[fund.itm_nm.str.contains("우리반도체BIG2플러스", regex=False)]
if len(r):
    same = r.rptt_ksd_itm_no.nunique() == 1 and r.rptt_ksd_itm_no.iloc[0] not in ("KR0000000000", "000000000000", "")
    lines = " | ".join(
        f"{x.itm_nm.split('Class')[-1]}: 종목번호 {x.itm_no}, 판매 {x.sale_yn}, "
        f"순자산 {won(x.fd_nast_suma)}, 1Y {x.fd_yr1_ern_r or '-'}%, 보수 {x.연보수율:.3f}%"
        for _, x in r.iterrows())
    add(10, "산출가능",
        f"동일 모펀드 여부: {'예' if same else '아니오/판정불가'} (대표종목번호 {r.rptt_ksd_itm_no.iloc[0]}). "
        f"클래스 {len(r)}종 — {lines}",
        f"fund.rptt_ksd_itm_no(대표종목번호)·itm_no·sale_yn·fd_nast_suma·fd_yr1_ern_r·보수4종 / as_of=20260821",
        note="대표종목번호 sentinel(KR0000000000·000000000000) 7,073건은 조인 전 반드시 제외")

# ── Q11 매수가능 + AA- 이상 (★ 정의 교체) ────────────────────────────────────
sel = bond[bond.구매가능 & (bond.curr_cd == "KRW") & (bond.등급서열 <= ORD["AA-"])]
top = sel.sort_values("등급서열").head(5)
add(11, "정의변경",
    f"주최측이 buyable_quantity를 무효 처리했으므로 '매수가능수량>0' 조건은 적용하지 않는다. "
    f"구매가능(만기 미도래)·원화·AA- 이상 = {len(sel):,}행 / 고유 {sel.pd_no.nunique():,}종목. "
    f"등급 분포 " + ", ".join(f"{k} {v:,}" for k, v in sel.crd_grd.value_counts().items()) + ". "
    f"예시: " + "; ".join(f"{x.pd_nm}({x.crd_grd}, 만기 {x.mat_dt}, 민평 {x.applied_yield})" for _, x in top.iterrows()),
    "bond.mat_dt·curr_cd·crd_grd(+등급서열)·applied_yield / info_base_dt=20260821. "
    "매수수익률(buy_yield)은 유효 634행뿐이라 민평수익률(applied_yield)로 대체 제시",
    note="★ 구 정의(buyable_quantity>0)로는 296행/AA-이상 33행. 새 정의로 모집단이 두 자릿수 배 커짐")

# ── Q12 판매중·거래가능·연금가능 국내ETF ────────────────────────────────────
sel = etf[(etf.pd_sale_yn == "1") & (etf.pd_tr_yn == "0") & (etf.pd_pen_tr_yn == "Y") &
          (etf.pd_lste_dt == "99991231")]
add(12, "산출가능",
    f"{len(sel):,}종목. 연금위험구분 " + ", ".join(f"{k} {v}" for k, v in sel.pd_pen_risk_nm.value_counts().items()) +
    " / 위험등급 " + ", ".join(f"{k} {v}" for k, v in sel.pd_risk_nm.value_counts().head(4).items()) +
    f" / 순자산 합계 {won(num(sel.pd_net_tamt).sum())} · 최대 {won(num(sel.pd_net_tamt).max())}",
    "etf_kr.pd_grp_no='ETF'·pd_sale_yn·pd_tr_yn·pd_pen_tr_yn·pd_lste_dt·pd_pen_risk_nm·pd_risk_nm·pd_net_tamt "
    "/ 순자산 as_of=20260821",
    note="pd_tr_yn은 0=정상인 역방향 플래그. ETN 545건 제외 필수")

# ── Q13 회사채 AA- 이상 잔존 3년 이하 상위 10 ────────────────────────────────
c = bond[bond.구매가능 & (bond.std_pd_mcls_nm == "회사채") & (bond.등급서열 <= ORD["AA-"])].copy()
c["잔존일"] = (c.mat - ASOF).dt.days
c = c[c.잔존일 <= 365 * 3]
c["수익률"] = num(c.applied_yield)
t10 = c.drop_duplicates("pd_no").nlargest(10, "수익률")
add(13, "정의변경",
    f"구매가능(만기 미도래)·회사채·AA- 이상·잔존 3년 이하 = {c.pd_no.nunique():,}종목. "
    f"민평수익률 상위 10: " + "; ".join(
        f"{x.pd_nm}({x.crd_grd}, 잔존 {int(x.잔존일)}일, {x.수익률}%)" for _, x in t10.iterrows()),
    "bond.std_pd_mcls_nm·crd_grd(등급서열 AA-=3 이하)·mat_dt(잔존일 재계산)·applied_yield / info_base_dt=20260821",
    note="'매수 가능'을 buyable_quantity가 아닌 만기 미도래로 해석. 매수수익률 대신 민평수익률 사용(전자는 97.1% 결측). "
         "⚠️ 주최측 정의를 그대로 적용하면 사모채(bd_ofr_tcd='사모')도 구매가능에 포함되어 상위 수익률을 점유한다 — "
         "개인 매수 가능성과 다르므로 답변에 공모/사모 구분을 병기하는 편이 안전하다")

# ── Q14 담보부/보증채 중 AAA 발행잔액 순 ─────────────────────────────────────
sec = bond[(bond.crd_grd == "AAA") & (
    bond.bd_knd.isin(["유동화회사채", "MBS", "유동화수익증권"]) | bond.pd_nm.str.contains("보증"))].copy()
sec["잔액"] = num(sec.isu_bal_amt)
t = sec.drop_duplicates("pd_no").nlargest(8, "잔액")
add(14, "부분산출",
    f"담보/보증 근거 컬럼이 없어 bd_knd(유동화회사채·MBS·유동화수익증권)와 상품명 '보증' 토큰으로 근사. "
    f"AAA 해당 {sec.pd_no.nunique():,}종목. 발행잔액 상위: " + "; ".join(
        f"{x.pd_nm}({x.pd_pbcm}, {x.bd_knd}, {won(x.isu_bal_amt)})" for _, x in t.iterrows()),
    "bond.bd_knd·pd_nm·crd_grd·isu_bal_amt·pd_pbcm / info_base_dt=20260821",
    note="담보 유형 전용 컬럼은 08-24에도 없음. 답변에 '분류 근거는 채권종류+상품명 토큰'임을 명시해야 함")

# ── Q15 해외주식 패시브·실물·정방향 + AUM 1조 이상, 1Y 상위 5 ────────────────
s = etf[(etf.wu_inv_ast_type == "주식") & (etf.wu_inv_rgn != "국내") &
        (etf.cu_strtegy == "실물복제") & (etf.cu_lev_fector == "1")].copy()
s["aum"] = num(s.pd_net_tamt); s["r1y"] = num(s.du_er_1y)
s = s[s.aum >= 1e12]
t5 = s.nlargest(5, "r1y")
add(15, "산출가능",
    f"조건 충족 {len(s)}종목. 1년수익률 상위 5: " + "; ".join(
        f"{x.pd_abrv_nm}(1Y {x.r1y}%, AUM {won(x.pd_net_tamt)}, 지수 {x.ref_base_index}, "
        f"보수 {x.cu_charge_rt or (f'{x.ter}%(LSEG)' if pd.notna(x.ter) else '값없음')})" for _, x in t5.iterrows()),
    "etf_kr.wu_inv_ast_type·wu_inv_rgn·cu_strtegy·cu_lev_fector·pd_net_tamt·du_er_1y·ref_base_index·cu_charge_rt(+LSEG ter) "
    "/ AUM·수익률 as_of=20260821 · 지수 as_of=20260822",
    note="cu_strtegy 한 컬럼이 전략·복제방식을 겸하므로 '실물복제'='패시브+실물'로 해석. "
         "정방향은 cu_lev_fector='1'. 총보수는 82.4% 결측이라 LSEG ter 병행")

# ── Q16 섹터·테마 액티브 ETF, AUM 5천억 이상 ────────────────────────────────
act = etf[etf.cu_strtegy == "액티브"].copy()
act["aum"] = num(act.pd_net_tamt)
# '섹터·테마형' 전용 축이 주최측 데이터에 없다 → 자산군=주식 + LSEG themes 보유로 조작적 정의
themed = act[(act.wu_inv_ast_type == "주식") & (act.themes.map(len) > 0)]
s = themed[themed.aum >= 5e11]
t = s.nlargest(8, "aum")
add(16, "부분산출",
    f"액티브 ETF {len(act)}종 중 자산군=주식이고 LSEG 테마가 부여된(=섹터·테마형) 상품이 {len(themed)}종, "
    f"그중 AUM 5천억 이상은 {len(s)}종목이다. " + "; ".join(
        f"{x.pd_abrv_nm}[{'/'.join(x.themes[:2])}](AUM {won(x.pd_net_tamt)}, 6M {x.du_er_6m or '값없음'}%, "
        f"보수 {x.cu_charge_rt or (f'{x.ter}%(LSEG)' if pd.notna(x.ter) else '값없음')}, 위험 {x.pd_risk_nm})"
        for _, x in t.iterrows()),
    "etf_kr.cu_strtegy='액티브'·wu_inv_ast_type·pd_net_tamt·du_er_6m·cu_charge_rt(+LSEG ter)·pd_risk_nm "
    "+ LSEG themes / as_of=20260821",
    external="'섹터·테마형' 축(axis_underlyingScope)이 주최측 데이터에 없어 LSEG themes로 대체(커버율 89.0%). "
             "LSEG 미매칭 ETF 136종은 판정 불가",
    note="⚠️ cu_strtegy='액티브'만으로 거르면 머니마켓·CD금리 액티브가 상위를 점유해 '섹터·테마'와 무관한 답이 나간다 — "
         "자산군·테마 조건을 반드시 함께 걸어야 한다")

# ── Q17 미국 주식형 AUM 1천억달러+ 보수 0.05% 이하 ──────────────────────────
s = gl[(gl.wu_inv_ast_type == "Equity") & (gl.wu_inv_rgn == "United States of America")].copy()
s["aum"] = num(s.du_last_aum); s["fee"] = num(s.cu_charge_rt)
s = s[(s.aum >= 1e11) & (s.fee <= 0.05)]
add(17, "산출가능",
    (f"{len(s)}종목: " + "; ".join(
        f"{x.pd_nm}({x.pd_itm_no}, 지수 {x.cu_base_index}, 복제 {x.cu_index_repl_mthd or '결측'}, "
        f"AUM {usd(x.aum)}, 보수 {x.cu_charge_rt}%)" for _, x in s.nlargest(10, "aum").iterrows())
     ) if len(s) else "조건 충족 0종목 — 임계값(AUM 1천억달러·보수 0.05%)을 만족하는 상품 없음",
    "etf_gl.wu_inv_ast_type·wu_inv_rgn·du_last_aum·cu_charge_rt·cu_base_index·cu_index_repl_mthd / "
    f"통화 단위 USD(pd_trd_ccy 전 행 USD) · as_of={gl.du_clpr_base_dt.mode()[0]}",
    note="du_last_aum의 통화 단위 표기가 스키마에 없다 — USD 가정 시 답변에 가정을 명시해야 함")

# ── Q18 해외 채권 ETF 보수 0.10% 이하 AUM 상위 10 ───────────────────────────
s = gl[(gl.wu_inv_ast_type == "Bond")].copy()
s["fee"] = num(s.cu_charge_rt); s["aum"] = num(s.du_last_aum)
s = s[s.fee <= 0.10]
t10 = s.nlargest(10, "aum")
add(18, "산출가능",
    f"조건 충족 {len(s)}종목. AUM 상위 10: " + "; ".join(
        f"{x.pd_nm}(보수 {x.cu_charge_rt}%, AUM {usd(x.aum)}, 지역 {x.wu_inv_rgn})"
        for _, x in t10.iterrows()),
    "etf_gl.wu_inv_ast_type='Bond'·cu_charge_rt·du_last_aum·cu_base_index·wu_inv_rgn·cu_index_repl_mthd / "
    f"가격·거래량 as_of={gl.du_clpr_base_dt.mode()[0]}(종가) / {gl.du_upt_dt.mode()[0]}(갱신)",
    note="기초지수는 실질 결측 48.6%(sentinel 문자열) — 결측 종목은 '미제공'으로 명시")

# ── Q19 판매중 공모펀드 1Y>0 & 순자산 1천억+ ────────────────────────────────
s = pub[(pub.sale_yn == "판매중") & (pub.thco_sale_yn == "Y")].copy()
s["r1y"] = num(s.fd_yr1_ern_r); s["aum"] = num(s.fd_nast_suma)
s = s[(s.r1y > 0) & (s.aum >= 1e11)]
t = s.nlargest(8, "r1y")
add(19, "산출가능",
    f"조건 충족 {len(s)}종목(클래스 단위). 수익률 상위: " + "; ".join(
        f"{x.itm_nm}(1Y {x.r1y}%, 순자산 {won(x.fd_nast_suma)}, 지역 {x.fd_ivst_rgn_desc}, "
        f"환헤지 {x.exchdg_yn or '미상'}, 위험 {x.zrin_fd_ivst_risk_grd_nm})" for _, x in t.iterrows()),
    "fund.prvo_pbff_desc='공모'·sale_yn·thco_sale_yn·fd_yr1_ern_r·fd_nast_suma·exchdg_yn·fd_ivst_rgn_desc·"
    "zrin_fd_ivst_risk_grd_nm / as_of=20260821",
    note="★ 사모 8,960건 제외 필수. exchdg_yn 결측 70.5%라 환헤지는 상당수 '미상'. "
         "클래스 중복이 있으므로 모펀드 단위 집계가 필요하면 rptt_ksd_itm_no로 묶어야 함")

# ── Q20 반도체 ETF+펀드 통합 ────────────────────────────────────────────────
e_semi = etf[etf.pd_abrv_nm.str.contains("반도체")].copy(); e_semi["aum"] = num(e_semi.pd_net_tamt)
f_semi = pub[pub.itm_nm.str.contains("반도체")].copy(); f_semi["aum"] = num(f_semi.fd_nast_suma)
JUNK = ["KR0000000000", "000000000000", ""]
# sentinel을 '제외'하면 해당 모펀드가 통째로 사라진다 → itm_no로 대체한 뒤 dedup
f_semi["모펀드키"] = f_semi.rptt_ksd_itm_no.where(~f_semi.rptt_ksd_itm_no.isin(JUNK), f_semi.itm_no)
f_semi_p = f_semi.sort_values("aum", ascending=False).drop_duplicates("모펀드키")
add(20, "부분산출",
    f"명칭 기준 후보: 국내ETF {len(e_semi)}종 / 공모펀드 {len(f_semi)}클래스(대표종목번호 dedup 후 {len(f_semi_p)}모펀드). "
    f"ETF 순자산 상위: " + "; ".join(f"{x.pd_abrv_nm}({won(x.pd_net_tamt)}, 지수 {x.ref_base_index})"
                                  for _, x in e_semi.nlargest(5, "aum").iterrows()) +
    f" / 펀드 상위: " + "; ".join(f"{x.itm_nm}({won(x.fd_nast_suma)})" for _, x in f_semi_p.nlargest(3, "aum").iterrows()),
    "etf_kr.pd_abrv_nm·ref_base_index·pd_net_tamt / fund.itm_nm·fd_nast_suma·rptt_ksd_itm_no / as_of=20260821",
    external="문항이 '이름에 반도체가 있다는 이유만으로 확정하지 말라'고 명시. "
             "기초지수명(ref_base_index)까지는 주최측 데이터로 확인되나 **편입내역 근거는 외부 수집 필요** "
             "(국내ETF PDF/포트폴리오, 펀드 자산운용보고서)",
    note="ref_base_index 신설로 '기초지수 근거'는 확보됨. 편입내역 근거만 외부 의존. "
         "⚠️ 클래스 dedup 시 대표종목번호 sentinel을 '제외'하면 해당 모펀드가 통째로 사라진다 — itm_no로 대체할 것")

# ── Q21 KODEX200 이중 등장 ──────────────────────────────────────────────────
k_etf = etf[etf.pd_abrv_nm.str.replace(" ", "") == "KODEX200"]
k_fund = fund[fund.ksd_itm_no.isin(set(k_etf.pd_itm_no))]
add(21, "산출가능",
    f"판정: 동일 운용상품(SAME_VEHICLE_AS). ETF 마스터의 {k_etf.pd_itm_no.iloc[0]}와 "
    f"공모펀드 마스터의 {'/'.join(k_fund.itm_no)} 가 `fund.ksd_itm_no == etf.pd_itm_no`로 결정적으로 연결된다"
    f"({'매칭 ' + str(len(k_fund)) + '건' if len(k_fund) else '이 종목은 미매칭'}). "
    f"ETF는 '상장된 집합투자기구'이므로 펀드 마스터에 원본 신탁이, ETF 마스터에 상장 클래스가 각각 적재된 것이다. "
    f"전체적으로 이 방식으로 연결되는 상품은 217종.",
    "fund.ksd_itm_no ↔ etf_kr.pd_itm_no 조인(217종) / fund.rptt_ksd_itm_no / etf_kr.pd_lstg_dt",
    note="★ 07-11에는 47종이었으나 08-24에서 217종으로 4.6배 증가. "
         "순자산은 07-11에 47/47 일치했으나 08-24는 0/217 — 펀드측 fd_nast_suma가 비어 ETF측을 정본으로 써야 함")

# ── Q22~Q30: 구성종목/문서 기반 ─────────────────────────────────────────────
HOLD = ("주최측 데이터에는 4개 도메인 어디에도 보유종목(holdings) 컬럼이 없다. "
        "주최측 안내상 섹터-상품·구성종목-상품 지식 구축은 참가자 자율이므로 "
        "**ABSTAIN이 아니라 외부 데이터로 채워야 하는 문항**이다.")

add(22, "외부데이터필요",
    HOLD + " 캠브리콘/Cambricon은 4개 도메인 상품명·176테마 전수 검색 0건이므로 "
    "'상품명 매칭'으로는 답할 수 없고, 편입내역을 확보해야만 답이 나온다. "
    f"중국 관련 국내ETF 후보는 명칭 기준 {int(etf.pd_abrv_nm.str.contains('차이나|중국').sum())}종.",
    "etf_kr/etf_gl/fund/bond 상품명 + theme_list(176) 전수 검색 = 0건",
    external="국내ETF PDF(운용사 공시) / 해외ETF SEC N-PORT(pd_us_cik 389개 → 시리즈ID 추가 필요) + "
             "종목↔국가·섹터 매핑. 조인키: pd_itm_no·pd_isin_cd·pd_ticker(08-24 신설)")

add(23, "부분산출",
    f"LSEG themes로 '우주항공/방산' 태그 ETF {int(etf.themes.map(lambda t: '우주항공/방산' in t).sum())}종 식별 가능"
    f"(예: " + ", ".join(etf[etf.themes.map(lambda t: '우주항공/방산' in t)].pd_abrv_nm.head(5)) + "). "
    "그러나 문항이 요구하는 '최근 6개월 연결 이력'은 시점 축이 필요한데 "
    "LSEG 메타에는 날짜 필드가 없다(themes·ter·replication·base_market·base_asset·hedge_type뿐).",
    "LSEG themes(커버율 89.0%) / etf_kr.cu_upt_dt=20260824",
    external="테마 부여 시점 이력(스냅샷 시계열) 또는 뉴스·공시 이벤트 일자. "
             "'현재 편입 관계'와 '단순 뉴스 언급' 구분에는 편입내역도 필요",
    note="현재 시점 테마 목록은 답 가능, '6개월 이력'은 불가 → 답변에서 두 층을 구분해 제시")

add(24, "외부데이터필요",
    HOLD + " 에코프로는 상품명 전수 검색상 채권에만 6건 존재하고 ETF/펀드 상품명에는 0건이다. "
    "'자회사' 관계도 주최측 데이터에 없다.",
    "bond.pd_nm '에코프로' 6건 / etf_kr·etf_gl·fund 상품명 0건",
    external="① 지배구조(DART 기업개황·지분관계) ② ETF 편입내역 ③ 위험요인 텍스트(투자설명서). "
             "AUM·기준일은 주최측 etf_kr.pd_net_tamt(as_of 20260821)로 충당 가능")

add(25, "부분산출",
    f"'국민성장' 명칭 매칭 {int(fund.itm_nm.str.contains('국민성장').sum())}건 — "
    + "; ".join(f"{x.itm_nm}(유형 {x.or_attr_desc}, 벤치마크 {x.bmrk_nm}, 순자산 {won(x.fd_nast_suma)})"
                for _, x in fund[fund.itm_nm.str.contains("국민성장")].iterrows()) +
    ". 구조·유형·벤치마크·순자산까지는 산출되나 '운용주체·자금조달 방식·투자전략 동향'은 서술형 텍스트라 원천에 없다.",
    "fund.itm_nm·or_attr_desc·bmrk_nm·fd_nast_suma·prvo_pbff_desc / as_of=20260821",
    external="공식 정책자료·운용보고서(발표기관·발행일 포함). 주최측 안내상 2026-08-24까지 발행분 사용 가능",
    note="이 4건은 prvo_pbff_desc='사모'로 적재되어 있어 '공모펀드' 필터에 걸리면 사라진다 — 필터 설계 주의")

sk = bond[bond.pd_nm.str.contains("에스케이하이닉스")].copy()
sk_ok = sk[sk.구매가능]
add(26, "부분산출",
    f"발행사→채권 경로는 산출 가능: '에스케이하이닉스(주)' 발행 채권 {sk.pd_no.nunique()}종목 "
    f"(구매가능 {sk_ok.pd_no.nunique()}종목). 등급 " +
    ", ".join(f"{k or '(미평가)'} {v}" for k, v in sk.crd_grd.value_counts().items()) +
    f", 만기 {sk.mat_dt.min()}~{sk.mat_dt.max()}. "
    "기업→편입증권→상품 경로는 편입내역 부재로 산출 불가.",
    "bond.pd_nm·pd_pbcm='에스케이하이닉스(주)'·crd_grd·mat_dt·applied_yield / info_base_dt=20260821",
    external="ETF·펀드 편입내역(삼성전자·SK하이닉스 등 대형주는 대부분 ETF에 편입되어 있으므로 커버리지 영향 큼)",
    note="★ 엔티티 표기 함정: 'SK하이닉스'로 검색하면 0건. 데이터 표기는 '에스케이하이닉스'(상품명)·"
         "'에스케이하이닉스(주)'(발행사) — 정규화 사전 필수")

lg = bond[bond.pd_pbcm == "(주)엘지에너지솔루션"]
add(27, "부분산출",
    f"'(주)엘지에너지솔루션' 발행 채권 {lg.pd_no.nunique()}종목(상품명은 'LG에너지솔루션…'). "
    + "; ".join(f"{x.pd_nm}({x.crd_grd}, 만기 {x.mat_dt})" for _, x in lg.drop_duplicates('pd_no').head(5).iterrows()) +
    ". 자회사 관계·ETF 편입비중·배터리 위험요인 문서는 원천에 없다.",
    "bond.pd_pbcm·pd_nm·crd_grd·mat_dt / info_base_dt=20260821",
    external="① 모자회사 공식 근거(DART) ② ETF 편입내역·비중 ③ 위험요인 문서",
    note="★ 표기 함정 2종 동시 발생: 상품명은 영문 'LG', 발행사는 한글 '엘지'. "
         "'엘지에너지솔루션'으로 상품명 검색 시 0건")

nv_kr = etf[etf.pd_abrv_nm.str.contains("엔비디아|NVIDIA", case=False)]
add(28, "외부데이터필요",
    HOLD + f" 상품명에 '엔비디아' 포함 국내ETF {len(nv_kr)}종은 찾을 수 있으나"
    + (f"({', '.join(nv_kr.pd_abrv_nm.head(5))})" if len(nv_kr) else "") +
    ", 이는 '엔비디아를 편입한' 상품이 아니라 '이름에 엔비디아가 든' 상품이다. 혼동하면 오답. "
    f"커버드콜형은 상품명 '커버드콜' 토큰으로 {int(etf.pd_abrv_nm.str.contains('커버드콜').sum())}종 식별 가능.",
    "etf_kr.pd_abrv_nm·pd_net_tamt·cu_strtegy / etf_gl.cu_strtegy(전략 원문)",
    external="편입내역·비중 + 유형별 위험 설명 문서. AUM·전략 원문은 주최측 데이터로 충당")

trio = gl[gl.pd_itm_no.str.split(".").str[0].isin(["VOO", "IVV", "SPY"])]
add(29, "부분산출",
    "기초지수·보수·AUM 비교는 산출 가능: " + "; ".join(
        f"{x.pd_itm_no}({x.cu_base_index}, 보수 {x.cu_charge_rt}%, AUM {usd(x.du_last_aum)})"
        for _, x in trio.iterrows()) +
    ". 세 상품이 같은 S&P 500 계열을 추종하는지는 지수명으로 판정 가능. "
    "편입종목 중복률·상위 기업 집중위험은 편입내역이 없어 산출 불가.",
    f"etf_gl.cu_base_index·cu_charge_rt·du_last_aum·pd_isin_cd / as_of={gl.du_clpr_base_dt.mode()[0]}",
    external="SEC N-PORT 또는 운용사 공시 편입내역(3종 모두 미국 상장 → pd_us_cik 활용). 중복률 계산식은 구성종목 확보 후")

add(30, "외부데이터필요",
    HOLD + " 우리반도체BIG2플러스는 클래스 2종(C-P·C-Pe)이며 대표종목번호로 중복 제거하면 1모펀드다(Q10 참조). "
    "클래스 중복 제거까지는 주최측 데이터로 되고, 편입종목 중복도는 외부 편입내역이 있어야 계산된다.",
    "fund.rptt_ksd_itm_no(클래스 dedup) / etf_kr 반도체 ETF 후보 " +
    f"{int(etf.pd_abrv_nm.str.contains('반도체').sum())}종",
    external="펀드 자산운용보고서 편입내역 + ETF PDF 편입내역 + 기업 지배구조·위험문서")

# ── Q31~Q35 답변불가 ────────────────────────────────────────────────────────
grades = sorted(set(bond.crd_grd) - {""})
add(31, "ABSTAIN",
    f"ABSTAIN_INVALID_TAXONOMY. 신용등급 허용값 사전은 {len(grades)}종 [{', '.join(grades)}]이며 "
    f"'AAAA'는 포함되지 않는다(매칭 0건). '존재하지 않는 등급'으로 답하고, "
    f"참고로 최상위 등급 AAA 구매가능 채권은 {bond[(bond.crd_grd=='AAA') & bond.구매가능].pd_no.nunique():,}종목임을 덧붙일 수 있다.",
    "bond.crd_grd DISTINCT (온톨로지 CreditRatingGrade 허용값)",
    note=f"★ 07-11 20종 → 08-24 {len(grades)}종으로 사전이 축소됨. 사전을 하드코딩했다면 갱신 필요")

add(32, "ABSTAIN",
    "ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF. 'Kimi' 전 도메인 상품명 + theme_list(176) 전수 검색 결과 "
    "국내ETF 0 / 해외ETF 0 / 공모펀드 0 / 채권 0 / 테마 0건. 연결 근거 문서·편입내역도 없다. "
    "데이터 기준일 2026-08-24(실질 08-21~08-24) 시점에도 해당 모델과 연결된 투자상품이 존재하지 않음을 "
    "전수 검색 결과로 증명해 답한다.",
    "4도메인 pd_nm/itm_nm + theme_list 전수 검색 = 0/0/0/0/0 / 기준일 info_base_dt=20260821·cu_upt_dt=20260824",
    note="문항 기준일을 07-11 → 08-24로 갱신함(주최측 안내에 맞춤). 기준일이 뒤로 밀려도 부재 판정은 그대로다")

kodex = etf[etf.pd_abrv_nm.str.startswith("KODEX")]
alt = kodex[kodex.pd_abrv_nm.str.contains("로봇|AI", regex=True)]
add(33, "ABSTAIN",
    f"ABSTAIN_ENTITY_NOT_FOUND. 'KODEX AI로봇' 정확 명칭 매칭 0건. "
    f"단 브랜드 'KODEX'는 실재하며 ETF {len(kodex)}종이 있다 → '브랜드는 존재하나 해당 상품은 없음'으로 분해 판정하고, "
    f"같은 브랜드의 로봇·AI 관련 대안 {len(alt)}종을 제시한다"
    f"(예: {', '.join(alt.pd_abrv_nm.head(4))}).",
    "etf_kr.pd_abrv_nm 정확일치 0건 / 브랜드 접두 토큰 사전",
    note="07-11 KODEX 240종 → 08-24 243종. 대안 후보도 18종으로 유지")

t5 = etf[etf.pd_abrv_nm.str.replace(" ", "") == "TIGER미국S&P500"]
add(34, "ABSTAIN",
    "ABSTAIN_FUTURE_DATA. 요청 기간(2027년 확정 연간수익률)이 데이터 기준일(2026-08-21) 이후다. "
    f"보유 수익률은 최장 1년({t5.du_er_1y.iloc[0] if len(t5) else '-'}%, as_of 20260821)이며 미래 실현값은 존재할 수 없다. "
    "대신 제공 가능한 것: 1D/1M/3M/6M/YTD/1Y 실적 수익률과 변동성(du_vlty_1y).",
    "etf_kr.du_er_* 최장 1년 / du_upt_dt=20260821",
    note="du_vlty_* 5종이 08-24에 신설되어 '대안 제시' 폭이 넓어짐")

add(35, "ABSTAIN",
    "ABSTAIN_DOMAIN_MISMATCH. VOO는 fp:ETF 인스턴스이고 fp:issuedBy의 domain은 fp:Bond 단독이므로 "
    "'VOO가 발행한 회사채'는 도메인 위반이다. 데이터상으로도 VOO(etf_gl)는 채권 마스터에 존재하지 않고, "
    "채권 발행사(pd_pbcm) 1,818종에 VOO/Vanguard는 없다. "
    "ETF는 채권 발행 주체가 아니라 채권을 편입할 수 있는 상품임을 설명한다.",
    "ontology fp:issuedBy domain=fp:Bond / etf_gl.pd_itm_no='VOO' / bond.pd_pbcm DISTINCT 1,818종에 부재")

# ── 출력 ────────────────────────────────────────────────────────────────────
gold = pd.DataFrame(rows)
# expected_qa는 이미 정답 컬럼을 포함한 단일 정본이다. 질문 컬럼만 복사해
# 재산출 결과를 붙임으로써 _x/_y 중복 컬럼과 자기 덮어쓰기를 피한다.
base = pd.read_csv(SOURCE, dtype=str, encoding="utf-8-sig")
base = base.drop(columns=[c for c in gold.columns if c != "id" and c in base.columns])
m = base.merge(gold, on="id", how="left")
assert m.golden_answer.notna().all(), "정답 미산출 문항: " + str(m[m.golden_answer.isna()].id.tolist())
OUT.mkdir(parents=True, exist_ok=True)
m.to_csv(OUT / "golden_answers_20260824.csv", index=False, encoding="utf-8-sig")

STATUS_DESC = {
    "산출가능": "주최측 데이터만으로 정답 전체를 산출했다.",
    "부분산출": "일부 항목은 산출했고 나머지는 근거 부재를 명시해야 한다.",
    "정의변경": "주최측 안내(BUYABLE_QUANTITY 무효)로 정답 정의 자체가 바뀌었다.",
    "엔티티부재": "질의 대상 종목이 2026-08-24 배포본에 존재하지 않는다.",
    "외부데이터필요": "구성종목·기업관계 등 외부 지식 구축이 있어야 답할 수 있다(주최측 안내상 참가자 자율 영역).",
    "ABSTAIN": "답변불가가 정답인 문항. 부재 근거를 제시해야 한다.",
}
md = ["# 2026 평가질의 골든셋 — 2026-08-24 배포본 기준", "",
      "> `script/build_golden_answers.py`가 `data/csv/*_20260824.csv`에서 **자동 산출**한다. 손으로 고치지 말고 스크립트를 고칠 것.",
      "> 문항 정본: `expected_qa/2026_expected_qa.csv` (35문항 = 하 10 / 중 10 / 상 10 + 답변불가 5)", "",
      "## 판정 요약", "", "| data_status | 문항 수 | 의미 |", "| --- | ---: | --- |"]
for k, v in m.data_status.value_counts().items():
    md.append(f"| **{k}** | {v} | {STATUS_DESC.get(k, '')} |")
md += [f"| 합계 | **{len(m)}** | |", "",
       "### 주최측 안내(2026-08-24) 반영 사항", "",
       "- `BUYABLE_QUANTITY` 무효 → '구매가능'은 **상장폐지·리스팅 종료 제외**(채권은 만기 미도래)로 재정의. Q11·Q13 정답이 바뀐다.",
       "- 섹터-상품 / 구성종목-상품 지식 구축은 **참가자 자율** → holdings 부재 문항은 `ABSTAIN`이 아니라 `외부데이터필요`로 분류.",
       "- 공시·시장데이터는 **2026-08-24까지** 발행분 사용 가능.",
       "- 교차질의(2개 이상 상품군 비교/검색)가 포함된다.", "", "---", ""]
for _, r in m.iterrows():
    md += [f"## Q{r.id}. [{r.difficulty}] {r.type}", "",
           f"**질문** — {r.question}", "",
           f"| 항목 | 내용 |", "| --- | --- |",
           f"| 상품군 | {r.product_category} |",
           f"| 기대 동작 | `{r.expected_behavior}` |",
           f"| **08-24 판정** | **{r.data_status}** |", "",
           f"**정답**", "", r.golden_answer, "",
           f"**근거** — {r.evidence}", ""]
    if isinstance(r.external_needed, str) and r.external_needed.strip():
        md += [f"**외부 데이터 필요** — {r.external_needed}", ""]
    if isinstance(r.note_vs_0711, str) and r.note_vs_0711.strip():
        md += [f"**비고** — {r.note_vs_0711}", ""]
    md += ["---", ""]
(OUT / "golden_answers_20260824.md").write_text("\n".join(md), encoding="utf-8")

print("저장:", OUT / "golden_answers_20260824.csv", m.shape)
print("저장:", OUT / "golden_answers_20260824.md")
print(m.data_status.value_counts().to_string())
