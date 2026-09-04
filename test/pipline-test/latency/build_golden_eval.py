"""
골든셋 35문항의 Claim 분해(루브릭 §3·§4·§5) 정본 생성기. 출력: latency/golden_eval.jsonl.
근거: goldset/golden_answers_20260824.md 의 정답·근거 컬럼·외부 데이터 필요 항목을 그대로 Claim으로 옮겼다.
Claim 필드: source(rdb|graph|vector|ontology, '|'로 복수 허용) / availability / required_fields(any-of)
 / answer_tokens(any-of, 답변 포함 검사) / gap_tokens(부재 고지 검사) / abstain_reason_tokens(ABSTAIN subtype 근거).
수치 토큰은 표기 차이(콤마·단위)를 흡수하도록 대안을 여러 개 둔다. 루브릭에 없는 기준은 추가하지 않는다.
"""
import json
from pathlib import Path

DATES = ["20260821", "2026-08-21", "20260822", "2026-08-22", "20260824", "2026-08-24", "2026.08.21", "2026.08.24"]
GAP_GENERIC = ["없", "부족", "외부", "필요", "미제공", "확인할 수 없", "확인되지", "제공되지", "불가"]
ABSTAIN_GENERIC = ["답변할 수 없", "확인할 수 없", "존재하지 않", "없습니다", "불가", "찾을 수 없", "해당하지 않", "0건", "없음"]


def C(cid, label, source, availability, **kw):
    d = {"claim_id": cid, "label": label, "source": source, "availability": availability}
    d.update(kw)
    return d


def avail(cid, label, source, fields, tokens=None):
    d = C(cid, label, source, "available", required_fields=fields)
    if tokens:
        d["answer_tokens"] = tokens
    return d


def ext(cid, label, source, gap, fields=None, relations=None):
    d = C(cid, label, source, "external_required", gap_tokens=gap + ["외부", "필요", "미제공", "부족", "미확보", "적재되지", "제공되지"],
          generic_tokens=GAP_GENERIC + ABSTAIN_GENERIC)
    if fields:
        d["required_fields"] = fields
    if relations:
        d["required_relations"] = relations
    return d


def part(cid, label, source, gap, fields=None):
    d = C(cid, label, source, "partial", gap_tokens=gap + GAP_GENERIC)
    if fields:
        d["required_fields"] = fields
    return d


HOLDING_REL = ["HOLDS_SECURITY", "hasHolding", "holding", "fp:Holding", "편입"]
HOLD_GAP = ["편입내역", "편입 내역", "편입 정보", "편입 관계", "보유종목", "구성종목", "holdings", "편입 여부"]

CASES = [
    {"question_id": "Q1", "golden_data_status": "부분산출", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "forbidden_fields": ["buyable_quantity"], "required_definition_tokens": ["만기", "무효", "미도래", "폐기", "사용하지"],
     "claims": [
         avail("C1", "상품번호", "rdb", ["pd_no"], ["KR6000662D25"]),
         avail("C2", "발행사", "rdb", ["pd_pbcm"], ["에스케이하이닉스"]),
         avail("C3", "신용등급", "rdb", ["crd_grd"], ["AA+"]),
         avail("C4", "표면금리", "rdb", ["srfc_irt"], ["4.266"]),
         avail("C5", "만기일", "rdb", ["mat_dt"], ["20280214", "2028-02-14", "2028.02.14", "2028년 2월 14일"]),
         part("C6", "매수수익률(값없음)", "rdb", ["값없음", "값이 없", "null", "None", "비어"], ["buy_yield"]),
         C("C7", "매수가능수량 재정의", "rdb", "deprecated_definition", required_fields=["mat_dt"]),
     ]},
    {"question_id": "Q2", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "상품번호", "rdb", ["pd_no"], ["KR103502GB66"]),
         avail("C2", "발행일", "rdb", ["isu_dt"], ["20210610", "2021-06-10", "2021.06.10"]),
         avail("C3", "만기일", "rdb", ["mat_dt"], ["20310610", "2031-06-10", "2031.06.10"]),
         avail("C4", "잔존일수", "rdb", ["remaining_days"], ["1754"]),
         avail("C5", "표면금리", "rdb", ["srfc_irt"], ["\"srfc_irt\":2", "2.0", "2%", "2 %", "2퍼", "금리 2", "금리는 2", "2.00"]),
         avail("C6", "세후수익률", "rdb", ["after_tax_yield"], ["3.9279", "3.93"]),
         avail("C7", "데이터 갱신일", "rdb", ["info_base_dt", "pd_std_info_update"], ["20260821", "2026-08-21", "2026.08.21"]),
     ]},
    {"question_id": "Q3", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "상품번호", "rdb", ["pd_no"], ["KR6001451F34"]),
         avail("C2", "채권종류", "rdb", ["bd_knd", "std_pd_mcls_nm"], ["보험회사채", "회사채"]),
         avail("C3", "발행사", "rdb", ["pd_pbcm"], ["현대해상화재보험"]),
         avail("C4", "원등급", "rdb", ["crd_grd"], ["AA0"]),
         avail("C5", "만기구분/만기일", "rdb", ["mat_dt"], ["20350327", "2035-03-27", "2035.03.27", "LongTerm", "장기"]),
         avail("C6", "듀레이션", "rdb", ["dur"], ["4.3459", "4.35", "4.34"]),
     ]},
    {"question_id": "Q4", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "상품번호", "rdb", ["pd_itm_no"], ["KR7069500007"]),
         avail("C2", "운용사", "rdb", ["ref_fund_mgmt_co"], ["Samsung Asset", "삼성자산운용", "삼성"]),
         avail("C3", "기초지수", "rdb", ["ref_base_index"], ["KOSPI 200", "코스피 200", "코스피200", "KOSPI200"]),
         avail("C4", "AUM", "rdb", ["pd_net_tamt"], ["25.47", "25,47", "2547", "25조", "25.5조"]),
         avail("C5", "NAV", "rdb", ["du_last_nav"], ["110190", "110,190"]),
         avail("C6", "종가", "rdb", ["du_clpr"], ["109980", "109,980"]),
         avail("C7", "괴리율", "rdb", ["du_diff_rt"], ["-0.19"]),
         avail("C8", "1년수익률", "rdb", ["du_er_1y"], ["158.14", "158.1"]),
     ]},
    {"question_id": "Q5", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "상품번호", "rdb", ["pd_itm_no"], ["KR7360750004"]),
         avail("C2", "투자자산군", "rdb", ["wu_inv_ast_type"], ["주식"]),
         avail("C3", "투자지역", "rdb", ["wu_inv_rgn"], ["미국", "북미"]),
         avail("C4", "운용전략/복제방식", "rdb", ["cu_strtegy"], ["실물복제", "실물", "패시브"]),
         avail("C5", "총보수", "rdb", ["cu_charge_rt", "ter", "charge_rt_final", "총보수"], ["0.006", "0.0060"]),
         avail("C6", "1개월 수익률", "rdb", ["du_er_1m"], ["-3.93"]),
         avail("C7", "3개월 수익률", "rdb", ["du_er_3m"], ["-5.23"]),
         avail("C8", "6개월 수익률", "rdb", ["du_er_6m"], ["6.46"]),
     ]},
    {"question_id": "Q6", "golden_data_status": "부분산출", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "정식 상품명", "rdb", ["pd_nm"], ["Vanguard 500", "Vanguard S&P 500"]),
         avail("C2", "ISIN", "rdb", ["pd_isin_cd"], ["US9229083632"]),
         avail("C3", "기초지수", "rdb", ["cu_base_index"], ["S&P 500", "S&P500"]),
         avail("C4", "운용사", "rdb", ["cu_fund_mgmt_co"], ["Vanguard"]),
         avail("C5", "총보수", "rdb", ["cu_charge_rt"], ["0.02", "0.03"]),
         avail("C6", "AUM", "rdb", ["du_last_aum"], ["997.4", "997,4", "997", "9974"]),
         avail("C7", "종가/현재가", "rdb", ["du_clpr", "ru_mkt_price"], ["703.71", "703.7"]),
         avail("C8", "거래량", "rdb", ["du_vol_1d"], ["10712821", "10,712,821"]),
         part("C9", "현재가 기준일 고지(ru_mkt_price 기준일 없음)", "rdb", ["기준일", "종가", "du_clpr", "기준 시점"]),
     ]},
    {"question_id": "Q7", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "상품번호", "rdb", ["pd_itm_no", "pd_ticker", "pd_isin_cd"], ["BND"]),
         avail("C2", "투자자산 유형", "rdb", ["wu_inv_ast_type"], ["Bond", "채권"]),
         avail("C3", "투자지역", "rdb", ["wu_inv_rgn"], ["United States", "미국"]),
         avail("C4", "기초지수", "rdb", ["cu_base_index"], ["Bloomberg", "Agg"]),
         avail("C5", "복제방식", "rdb", ["cu_index_repl_mthd"], ["Optimized", "최적화", "샘플링"]),
         avail("C6", "총보수", "rdb", ["cu_charge_rt"], ["0.02", "0.03"]),
         avail("C7", "운용전략 원문", "rdb", ["cu_strtegy"], ["cu_strtegy", "invest", "index", "전략", "strategy", "seeks", "track"]),
     ]},
    {"question_id": "Q8", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "종목번호", "rdb", ["itm_no"], ["KR5153450780"]),
         avail("C2", "펀드유형", "rdb", ["or_attr_desc"], ["주식형", "주식"]),
         avail("C3", "순자산", "rdb", ["fd_nast_suma"], ["7,348", "7348", "734,8", "7348억", "0.73조"]),
         avail("C4", "1개월 수익률", "rdb", ["fd_mm1_ern_r"], ["3.32"]),
         avail("C5", "3개월 수익률", "rdb", ["fd_mm3_ern_r"], ["-9.64"]),
         avail("C6", "6개월 수익률", "rdb", ["fd_mm6_ern_r"], ["30.39"]),
         avail("C7", "1년 수익률", "rdb", ["fd_yr1_ern_r"], ["187.94", "187.9"]),
         avail("C8", "위험등급", "rdb", ["zrin_fd_ivst_risk_grd_nm", "zrin_fd_ivst_risk_grd", "zrin_fd_ivst_risk"], ["매우 높은 위험", "매우높은위험", "1등급", "\"1\"", "위험등급\":1", "등급 1", "1 "]),
         avail("C9", "판매 여부", "rdb", ["sale_yn", "thco_sale_yn"], ["판매중", "판매 중", "판매 가능", "\"Y\"", "Y "]),
     ]},
    {"question_id": "Q9", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "종목번호", "rdb", ["itm_no", "ksd_itm_no"], ["KR5014410050", "KRZ500626190"]),
         avail("C2", "벤치마크", "rdb", ["bmrk_nm"], ["CALL", "콜"]),
         avail("C3", "통화", "rdb", ["curr_cd"], ["KRW", "원화", "원"]),
         avail("C4", "투자지역", "rdb", ["fd_ivst_rgn_desc"], ["국내"]),
         avail("C5", "개인·법인 구분", "rdb", ["pers_corp_desc"], ["법인"]),
         avail("C6", "위험등급", "rdb", ["zrin_fd_ivst_risk_grd_nm", "zrin_fd_ivst_risk"], ["매우 낮은 위험", "매우낮은위험", "6등급", "낮은"]),
         avail("C7", "순자산", "rdb", ["fd_nast_suma"], ["2.19조", "2,19", "219", "21,9", "2조"]),
     ]},
    {"question_id": "Q10", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "동일 모펀드 판정(대표종목번호)", "rdb", ["rptt_ksd_itm_no"], ["031010005F29", "동일", "같은 모펀드", "같은 펀드"]),
         avail("C2", "C-P 종목번호", "rdb", ["itm_no"], ["KR5118430058"]),
         avail("C3", "C-Pe 종목번호", "rdb", ["itm_no"], ["KR5118430059"]),
         avail("C4", "순자산", "rdb", ["fd_nast_suma"], ["2,079", "2079", "207,9", "20억", "2,0"]),
         avail("C5", "1년 수익률", "rdb", ["fd_yr1_ern_r"], ["57.61", "57.9", "57.6"]),
         avail("C6", "판매 여부", "rdb", ["sale_yn", "thco_sale_yn"], ["판매중", "판매 중", "판매 가능", "\"Y\"", "Y,", "Y "]),
     ]},
    {"question_id": "Q11", "golden_data_status": "정의변경", "expected_action": "ANSWER_WITH_REDEFINED_RULE", "expected_routes": ["rdb"],
     "forbidden_fields": ["buyable_quantity"], "required_definition_tokens": ["만기", "무효", "미도래", "폐기", "사용하지", "적용하지"],
     "claims": [
         C("C1", "구매가능 재정의(만기 미도래)", "rdb", "deprecated_definition", required_fields=["mat_dt", "remaining_days"]),
         avail("C2", "신용등급 AA- 이상 필터", "rdb", ["crd_grd"], ["AAA", "AA+", "AA0", "AA-", "AA"]),
         avail("C3", "원화 필터", "rdb", ["curr_cd"], None),
         avail("C4", "수익률(민평/매수)", "rdb", ["applied_yield", "buy_yield"], None),
         avail("C5", "상품명·발행사·만기일 출력", "rdb", ["pd_nm", "pd_pbcm", "mat_dt"], None),
     ]},
    {"question_id": "Q12", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "판매중·거래정지 아님·연금가능 필터", "rdb", ["pd_sale_yn", "pd_tr_yn", "pd_pen_tr_yn"], None),
         avail("C2", "ETN 제외(pd_grp_no='ETF')", "rdb", ["pd_grp_no"], None),
         avail("C3", "연금 위험구분", "rdb", ["pd_pen_risk_nm"], ["위험자산", "안전자산"]),
         avail("C4", "상품 위험등급", "rdb", ["pd_risk_nm"], ["위험"]),
         avail("C5", "순자산", "rdb", ["pd_net_tamt"], None),
         avail("C6", "기준일", "rdb", ["pd_net_tamt", "du_upt_dt", "cu_upt_dt"], DATES),
     ]},
    {"question_id": "Q13", "golden_data_status": "정의변경", "expected_action": "ANSWER_WITH_REDEFINED_RULE", "expected_routes": ["rdb"],
     "forbidden_fields": ["buyable_quantity"], "required_definition_tokens": ["만기", "무효", "미도래", "폐기", "사용하지", "적용하지"],
     "claims": [
         C("C1", "매수 가능 재정의(만기 미도래)", "rdb", "deprecated_definition", required_fields=["mat_dt", "remaining_days"]),
         avail("C2", "회사채 필터", "rdb", ["std_pd_mcls_nm", "bd_knd"], None),
         avail("C3", "등급 서열 AA- 이상", "rdb", ["crd_grd"], ["AA"]),
         avail("C4", "잔존기간 3년 이하", "rdb", ["mat_dt", "remaining_days"], None),
         avail("C5", "수익률 상위 10", "rdb", ["applied_yield", "buy_yield"], ["뉴젠에너지", "스마트케이", "블루스네이크", "엘씨글로리", "뉴에스에프", "플로우제일차", "뉴스텔라", "그린이노베이션", "레드홀스"]),
     ]},
    {"question_id": "Q14", "golden_data_status": "부분산출", "expected_action": "ANSWER_PARTIAL_WITH_GAP", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "AAA 등급 필터", "rdb", ["crd_grd"], ["AAA"]),
         avail("C2", "담보/보증 근사 필터(bd_knd·상품명 토큰)", "rdb", ["bd_knd"], ["유동화", "MBS", "보증", "담보"]),
         avail("C3", "발행잔액 정렬", "rdb", ["isu_bal_amt"], ["에이블이목", "한국주택금융공사", "MBS", "유동화"]),
         avail("C4", "발행사·상품번호", "rdb", ["pd_pbcm", "pd_no"], None),
     ]},
    {"question_id": "Q15", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "해외주식·패시브·실물복제·정방향·AUM 1조 필터", "rdb", ["wu_inv_ast_type", "wu_inv_rgn", "cu_strtegy", "cu_lev_fector", "pd_net_tamt"], None),
         avail("C2", "1년 수익률 상위 5", "rdb", ["du_er_1y"], ["PLUS 글로벌HBM", "ACE 글로벌반도체TOP4", "TIGER 미국필라델피아반도체나스닥", "KODEX 미국반도체", "TIGER 미국필라델피아AI반도체"]),
         avail("C3", "보수", "rdb", ["cu_charge_rt", "ter", "charge_rt_final", "총보수"], None),
         avail("C4", "기초지수", "rdb", ["ref_base_index"], None),
         avail("C5", "AUM", "rdb", ["pd_net_tamt"], None),
         avail("C6", "기준일", "rdb", ["pd_net_tamt"], DATES),
     ]},
    {"question_id": "Q16", "golden_data_status": "부분산출", "expected_action": "ANSWER_PARTIAL_WITH_GAP", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "액티브 필터", "rdb", ["cu_strtegy"], None),
         avail("C2", "섹터·테마형 축(LSEG themes, 로컬 Graph 적재)", "graph", ["themes", "theme", "relatedToTheme", "lseg"], ["테마", "섹터"]),
         avail("C3", "AUM 5천억 이상", "rdb", ["pd_net_tamt"], None),
         avail("C4", "6개월 수익률", "rdb", ["du_er_6m"], None),
         avail("C5", "총보수", "rdb", ["cu_charge_rt", "ter", "charge_rt_final", "총보수"], None),
         avail("C6", "위험등급", "rdb", ["pd_risk_nm"], None),
         avail("C7", "상위 상품(섹터·테마 조건 반영)", "rdb", ["pd_net_tamt"], ["TIME 미국나스닥100액티브", "TIGER 배당커버드콜액티브", "TIME 글로벌AI인공지능액티브", "KODEX 미국배당커버드콜액티브", "KODEX 로봇액티브", "KODEX 200액티브", "TIGER 반도체TOP10커버드콜", "TIME Korea플러스배당"]),
     ]},
    {"question_id": "Q17", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "미국 주식형·AUM 1천억달러·보수 0.05% 필터", "rdb", ["wu_inv_ast_type", "wu_inv_rgn", "du_last_aum", "cu_charge_rt"], None),
         avail("C2", "상품명", "rdb", ["pd_nm"], ["Vanguard 500", "iShares Core S&P 500", "SPDR S&P 500", "Vanguard"]),
         avail("C3", "티커", "rdb", ["pd_itm_no", "pd_ticker", "pd_abrv_nm"], ["VOO", "IVV", "SPY", "VTI"]),
         avail("C4", "기초지수", "rdb", ["cu_base_index"], ["S&P 500"]),
         avail("C5", "복제방식", "rdb", ["cu_index_repl_mthd"], ["Full", "Optimized", "완전", "최적화"]),
         avail("C6", "통화 단위", "rdb", ["pd_trd_ccy", "du_last_aum"], ["USD", "달러", "$"]),
     ]},
    {"question_id": "Q18", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "해외 채권 ETF·보수 0.10% 필터", "rdb", ["wu_inv_ast_type", "cu_charge_rt"], None),
         avail("C2", "AUM 상위 10", "rdb", ["du_last_aum"], ["Vanguard Total Bond", "iShares Core US Aggregate", "BND", "AGG", "iShares 0-3 Month", "Vanguard Total International Bond"]),
         avail("C3", "기초지수", "rdb", ["cu_base_index"], None),
         avail("C4", "투자지역", "rdb", ["wu_inv_rgn"], None),
         avail("C5", "복제방식", "rdb", ["cu_index_repl_mthd"], None),
         avail("C6", "현재가·거래량 기준일", "rdb", ["du_clpr", "du_vol_1d", "du_upt_dt", "cu_upt_dt"], DATES),
     ]},
    {"question_id": "Q19", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "공모·판매중·1년수익률 양수·순자산 1천억 필터", "rdb", ["prvo_pbff_desc", "sale_yn", "fd_yr1_ern_r", "fd_nast_suma"], None),
         avail("C2", "수익률 상위 상품", "rdb", ["fd_yr1_ern_r"], ["한화2.2배레버리지", "NH-Amundi코리아2배레버리지", "NH-Amundi", "하나IT코리아", "레버리지"]),
         avail("C3", "환헤지 여부", "rdb", ["exchdg_yn"], ["환헤지", "환 헤지", "미상", "헤지"]),
         avail("C4", "투자지역", "rdb", ["fd_ivst_rgn_desc"], ["국내", "해외"]),
         avail("C5", "위험등급", "rdb", ["zrin_fd_ivst_risk_grd_nm", "zrin_fd_ivst_risk"], ["위험"]),
         avail("C6", "기준일", "rdb", ["fd_nast_suma"], DATES),
     ]},
    {"question_id": "Q20", "golden_data_status": "부분산출", "expected_action": "ANSWER_PARTIAL_WITH_GAP", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "국내 반도체 ETF 순자산 상위", "rdb", ["pd_abrv_nm", "pd_nm", "pd_net_tamt"], ["TIGER 반도체TOP10", "SOL AI반도체TOP2", "KODEX 반도체", "TIGER 미국필라델피아반도체", "KODEX AI반도체TOP2"]),
         avail("C2", "반도체 공모펀드 순자산 상위", "rdb", ["itm_nm", "fd_nast_suma"], ["유리필라델피아반도체", "한국투자글로벌AI&반도체", "삼성글로벌반도체", "반도체"]),
         avail("C3", "기초지수 근거", "rdb", ["ref_base_index"], ["FnGuide", "KRX Semiconductor", "Philadelphia", "기초지수", "Semiconductor"]),
         ext("C4", "편입내역 근거", "graph|vector", HOLD_GAP, relations=HOLDING_REL),
         avail("C5", "AUM·수익률 기준일", "rdb", ["pd_net_tamt", "fd_nast_suma"], DATES),
     ]},
    {"question_id": "Q21", "golden_data_status": "산출가능", "expected_action": "ANSWER", "expected_routes": ["rdb"],
     "claims": [
         avail("C1", "동일 운용상품 판정(ksd_itm_no=pd_itm_no)", "rdb|graph", ["ksd_itm_no", "pd_itm_no", "SAME_VEHICLE", "sameVehicle"], ["동일 운용상품", "동일 운용", "동일운용", "같은 운용", "동일한 운용", "동일한 상품", "같은 상품", "동일 상품", "상장 클래스", "상장된 집합투자기구", "상장된 펀드", "SAME_VEHICLE", "동일"]),
         avail("C2", "ETF 상품번호", "rdb|graph", ["pd_itm_no"], ["KR7069500007"]),
         avail("C3", "펀드 종목번호/대표종목번호", "rdb|graph", ["itm_no", "ksd_itm_no", "rptt_ksd_itm_no"], ["KR5114601001", "KR7069500007"]),
         avail("C4", "상장 여부 관계", "rdb|graph", ["pd_lstg_dt", "pd_lste_dt", "상장"], ["상장"]),
     ]},
    {"question_id": "Q22", "golden_data_status": "외부데이터필요", "expected_action": "ANSWER_WITH_EXTERNAL_GAP", "expected_routes": ["graph"],
     "claims": [
         ext("C1", "캠브리콘 편입 관계(ETF→편입증권→기업)", "graph", HOLD_GAP + ["캠브리콘", "Cambricon"], relations=HOLDING_REL),
         ext("C2", "편입비중·편입기준일", "graph", HOLD_GAP + ["비중", "기준일"], fields=["holding_weight", "holding_as_of", "weight"]),
         ext("C3", "편입내역 문서명·근거 문장", "vector", ["문서", "근거 문장", "인용"], fields=["document_name", "citation_text", "evidence_text"]),
     ]},
    {"question_id": "Q23", "golden_data_status": "부분산출", "expected_action": "ANSWER_PARTIAL_WITH_GAP", "expected_routes": ["rdb", "graph", "vector"],
     "claims": [
         avail("C1", "현재 우주항공/방산 테마 ETF", "rdb|graph", ["themes", "theme", "relatedToTheme", "Theme", "테마"], ["방산", "우주", "K방산", "TIGER K방산", "SOL K방산", "KODEX 방산", "팔란티어", "TIME 글로벌우주"]),
         ext("C2", "최근 6개월 테마 연결 이력(시점 축)", "graph", ["6개월", "이력", "시점", "날짜", "사건일", "시계열", "기간"], relations=["THEME_HISTORY", "theme_history", "event_date"]),
         ext("C3", "현재 편입 관계와 뉴스 언급 구분", "vector", HOLD_GAP + ["뉴스", "언급", "문서", "근거문서"], fields=["holding_as_of", "event_date", "citation_text"]),
     ]},
    {"question_id": "Q24", "golden_data_status": "외부데이터필요", "expected_action": "ANSWER_WITH_EXTERNAL_GAP", "expected_routes": ["graph", "rdb", "vector"],
     "claims": [
         ext("C1", "에코프로 자회사 관계", "graph", ["자회사", "지배구조", "DART", "기업 관계"], relations=["SUBSIDIARY_OF", "SubsidiaryRelation", "subsidiary", "자회사"]),
         ext("C2", "자회사 ETF 편입 관계", "graph", HOLD_GAP, relations=HOLDING_REL),
         ext("C3", "편입비중·기준일", "graph", HOLD_GAP + ["비중", "기준일"], fields=["holding_weight", "holding_as_of", "weight"]),
         part("C4", "ETF AUM·기준일(대상 ETF 특정 시)", "rdb", ["AUM", "순자산", "pd_net_tamt", "기준일"], ["pd_net_tamt"]),
         ext("C5", "위험요인 문서 인용", "vector", ["위험", "투자설명서", "문서", "인용"], fields=["citation_text", "document_name", "evidence_text"]),
     ]},
    {"question_id": "Q25", "golden_data_status": "부분산출", "expected_action": "ANSWER_PARTIAL_WITH_GAP", "expected_routes": ["rdb", "vector"],
     "claims": [
         avail("C1", "국민성장 명칭 매칭 펀드", "rdb", ["itm_nm"], ["국민성장", "국민참여형"]),
         avail("C2", "구조/펀드유형", "rdb", ["or_attr_desc", "prvo_pbff_desc"], ["혼합자산", "혼합", "사모투자재간접", "재간접"]),
         avail("C3", "벤치마크", "rdb", ["bmrk_nm"], ["KOSPI200", "KOSPI 200", "종합채권"]),
         avail("C4", "순자산", "rdb", ["fd_nast_suma"], ["184", "618", "719", "471", "억"]),
         ext("C5", "운용주체·자금조달·투자전략 동향(공식 문서)", "vector", ["문서", "정책자료", "운용보고서", "운용자료", "발표기관", "발행일", "동향"], fields=["citation_text", "document_name", "published_at"]),
     ]},
    {"question_id": "Q26", "golden_data_status": "부분산출", "expected_action": "ANSWER_PARTIAL_WITH_GAP", "expected_routes": ["rdb", "graph"],
     "claims": [
         avail("C1", "에스케이하이닉스(주) 발행 채권 목록(발행사/상품명 필터)", "rdb", ["pd_pbcm", "에스케이하이닉스", "sk하이닉스"], ["에스케이하이닉스"]),
         avail("C2", "채권 신용등급", "rdb", ["crd_grd"], ["AA+"]),
         avail("C3", "채권 만기", "rdb", ["mat_dt"], ["2027", "2028", "2029", "2030", "2031", "2035"]),
         avail("C4", "채권 수익률", "rdb", ["applied_yield", "buy_yield"], None),
         ext("C5", "SK하이닉스 편입 ETF·공모펀드 경로", "graph", HOLD_GAP, relations=HOLDING_REL),
         ext("C6", "편입비중·AUM 기준일", "graph|rdb", HOLD_GAP + ["비중", "기준일"], fields=["holding_weight", "holding_as_of", "weight"]),
     ]},
    {"question_id": "Q27", "golden_data_status": "부분산출", "expected_action": "ANSWER_PARTIAL_WITH_GAP", "expected_routes": ["rdb", "graph", "vector"],
     "claims": [
         avail("C1", "(주)엘지에너지솔루션 발행 채권(발행사/상품명 필터)", "rdb", ["pd_pbcm", "lg에너지솔루션", "엘지에너지솔루션"], ["LG에너지솔루션", "엘지에너지솔루션"]),
         avail("C2", "채권 신용등급", "rdb", ["crd_grd"], ["AA0", "AA"]),
         avail("C3", "채권 만기", "rdb", ["mat_dt"], ["2028", "2029", "2031", "2030", "2027"]),
         ext("C4", "모자회사 관계 공식 근거", "graph", ["자회사", "모자회사", "지배구조", "DART", "기업 관계"], relations=["SUBSIDIARY_OF", "SubsidiaryRelation", "subsidiary", "자회사"]),
         ext("C5", "ETF 편입비중", "graph", HOLD_GAP + ["비중"], relations=HOLDING_REL),
         ext("C6", "배터리산업 위험요인 문서", "vector", ["위험", "문서", "투자설명서", "인용"], fields=["citation_text", "document_name", "evidence_text"]),
     ]},
    {"question_id": "Q28", "golden_data_status": "외부데이터필요", "expected_action": "ANSWER_WITH_EXTERNAL_GAP", "expected_routes": ["graph", "rdb", "vector"],
     "claims": [
         ext("C1", "엔비디아 편입 관계(이름 포함≠편입)", "graph", HOLD_GAP + ["엔비디아", "NVIDIA", "이름"], relations=HOLDING_REL),
         ext("C2", "편입비중·편입기준일", "graph", HOLD_GAP + ["비중", "기준일"], fields=["holding_weight", "holding_as_of", "weight"]),
         part("C3", "AUM(상품명 후보 기준)", "rdb", ["AUM", "순자산", "pd_net_tamt", "du_last_aum"], ["pd_net_tamt", "du_last_aum"]),
         part("C4", "전략 원문·커버드콜 식별", "rdb", ["커버드콜", "전략", "cu_strtegy", "지수형"], ["cu_strtegy", "pd_abrv_nm", "pd_nm"]),
         ext("C5", "위험 설명 문서 근거", "vector", ["위험", "문서", "투자설명서", "인용"], fields=["citation_text", "document_name", "evidence_text"]),
     ]},
    {"question_id": "Q29", "golden_data_status": "부분산출", "expected_action": "ANSWER_PARTIAL_WITH_GAP", "expected_routes": ["rdb", "graph"],
     "claims": [
         avail("C1", "기초지수 동일(S&P 500 TR)", "rdb", ["cu_base_index"], ["S&P 500", "S&P500"]),
         avail("C2", "보수", "rdb", ["cu_charge_rt"], ["0.02", "0.03", "0.0492", "0.05"]),
         avail("C3", "AUM", "rdb", ["du_last_aum"], ["997", "889", "820"]),
         ext("C4", "편입종목 중복률", "graph", HOLD_GAP + ["중복률", "중복"], relations=HOLDING_REL),
         ext("C5", "상위 기업 집중위험(종목별 비중)", "graph", HOLD_GAP + ["집중", "비중"], fields=["holding_weight", "weight"]),
         ext("C6", "운용문서 근거", "vector", ["문서", "운용문서", "인용", "투자설명서"], fields=["citation_text", "document_name"]),
     ]},
    {"question_id": "Q30", "golden_data_status": "외부데이터필요", "expected_action": "ANSWER_WITH_EXTERNAL_GAP", "expected_routes": ["rdb", "graph", "vector"],
     "claims": [
         avail("C1", "우리반도체BIG2플러스 클래스 중복 제거", "rdb", ["rptt_ksd_itm_no", "itm_no", "itm_nm"], ["C-P", "C-Pe", "클래스", "대표종목번호", "우리반도체BIG2"]),
         ext("C2", "편입종목 중복도(계산식)", "graph", HOLD_GAP + ["중복도", "중복", "계산식"], relations=HOLDING_REL),
         ext("C3", "중복 노출 기업의 자회사·산업 위험", "graph", ["자회사", "산업 위험", "기업관계", "지배구조"], relations=["SUBSIDIARY_OF", "SubsidiaryRelation", "subsidiary", "자회사"]),
         ext("C4", "위험문서 근거", "vector", ["위험", "문서", "인용", "투자설명서"], fields=["citation_text", "document_name"]),
     ]},
    {"question_id": "Q31", "golden_data_status": "ABSTAIN", "expected_action": "ABSTAIN_INVALID_TAXONOMY", "expected_routes": [],
     "claims": [C("C1", "신용등급 AAAA는 허용값 아님", "ontology", "invalid_taxonomy",
                  abstain_tokens=ABSTAIN_GENERIC,
                  abstain_reason_tokens=["허용", "유효한 등급", "유효하지", "유효 값", "존재하지 않는 등급", "등급이 아니", "등급 체계", "없는 등급", "등급 값", "AAAA", "AAA가 최상", "최상위 등급", "taxonomy", "분류값"])]},
    {"question_id": "Q32", "golden_data_status": "ABSTAIN", "expected_action": "ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF", "expected_routes": [],
     "claims": [C("C1", "Kimi 관련 상품이 기준일 시점에 없음", "ontology", "not_released_as_of_cutoff",
                  abstain_tokens=ABSTAIN_GENERIC,
                  abstain_reason_tokens=["기준일", "2026-08-24", "20260824", "2026.08.24", "시점", "출시", "Kimi", "키미", "존재하지 않", "확인되지", "검색 결과", "0건", "찾을 수 없", "관련 상품"])]},
    {"question_id": "Q33", "golden_data_status": "ABSTAIN", "expected_action": "ABSTAIN_ENTITY_NOT_FOUND", "expected_routes": [],
     "claims": [C("C1", "KODEX AI로봇 상품 부재", "ontology", "entity_not_found",
                  abstain_tokens=ABSTAIN_GENERIC,
                  abstain_reason_tokens=["존재하지 않", "일치하는 상품", "찾을 수 없", "해당 상품", "상품이 없", "KODEX AI로봇", "정확한 명칭", "확인되지"])]},
    {"question_id": "Q34", "golden_data_status": "ABSTAIN", "expected_action": "ABSTAIN_FUTURE_DATA", "expected_routes": [],
     "claims": [C("C1", "2027년 확정 수익률은 미래값", "ontology", "future_unavailable",
                  abstain_tokens=ABSTAIN_GENERIC,
                  abstain_reason_tokens=["2027", "미래", "기준일 이후", "아직", "확정되지", "실현되지", "존재하지 않", "제공되지"])]},
    {"question_id": "Q35", "golden_data_status": "ABSTAIN", "expected_action": "ABSTAIN_DOMAIN_MISMATCH", "expected_routes": [],
     "claims": [C("C1", "VOO는 ETF, issuedBy domain은 Bond", "ontology", "domain_mismatch",
                  abstain_tokens=ABSTAIN_GENERIC,
                  abstain_reason_tokens=["ETF", "발행 주체", "발행하지", "발행할 수 없", "발행사가 아니", "도메인", "채권을 발행", "회사채를 발행", "발행 기관", "상장지수"])]},
]

if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "golden_eval.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for case in CASES:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
    n_claims = sum(len(c["claims"]) for c in CASES)
    assert len(CASES) == 35, len(CASES)
    assert len({c["question_id"] for c in CASES}) == 35
    print(f"{out}: {len(CASES)} questions, {n_claims} claims")
