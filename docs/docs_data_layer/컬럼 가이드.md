# 컬럼 설명서 (COLUMN_GUIDE)

> 현행 기준: 주최측 2026-08-24 배포본. 원천 스키마 280컬럼을 실제 CSV로 재계산했다.

이 문서는 컬럼의 물리 정의와 질의 안전 규칙을 함께 제공한다. 상세 RDB 타입·PK·FK·출처는 `table_definition_v1_0.csv`, 파일별 전체 결측률은 자동 생성물 `DATA_INVENTORY.md`, 분석 근거는 `EDA/EDA_REPORT_0824.md`를 정본으로 삼는다. 결측률은 빈 문자열 기준이며 스키마 설명은 주최측 `*_schema_20260824.csv`에서 가져왔다.

## 1. 원천 규모와 그레인

| 도메인 | master | 행×열 | 엔티티/모집단 | 그레인·PK | 실질 기준일 |
|---|---|---:|---|---|---|
| 국내채권 `bond_kr` | `PRBD01N001_bond_kr_master_20260824.csv` | 21,882 × 58 | 20,497종목 | 채권 거래·정보차수 1건; `(pd_no, pd_exg_mkt, info_seq)` | 2026-08-21 (`info_base_dt`) |
| 국내 ETF/ETN `etf_kr` | `PREF01N001_etf_kr_master_20260824.csv` | 1,780 × 98 | ETF 1,235 / ETN 545 | 상품 1건; `pd_itm_no` | 가격 2026-08-21 / 상품속성 08-24 / Refinitiv 08-22 |
| 해외 ETF/ETN `etf_gl` | `PREF02N001_etf_gl_master_20260824.csv` | 6,037 × 49 | ETF 5,972 / ETN 65 | 상품 1건; `pd_itm_no` | 종가 2026-08-21 / 갱신 08-22 |
| 국내 펀드 `fund_pub` | `PRFD01N001_fund_pub_master_20260824.csv` | 23,676 × 75 | 23,676펀드(공모 14,716 / 사모 8,960) | 펀드 1건; `itm_no` | 2026-08-21 (`fd_price_bas_dt` 최빈값) |

합계는 **280컬럼(58 + 98 + 49 + 75)**이다. 파일명의 2026-08-24는 배포 스냅샷이고, 답변 evidence에는 표의 실질 기준일 컬럼을 사용한다.

## 2. 판정 규칙

- **식별**: PK, 상품코드, 상품명. 완전일치 우선이며 유사명으로 대체하지 않는다.
- **조건**: 필터·정렬·비교에 쓰는 값. 단위·허용값·기준일을 함께 검증한다.
- **관계**: 외부 조인키나 도메인 연결축. 중복·sentinel을 제거한 뒤 연결한다.
- **보조/제외**: 전량 결측, 상수, 무효 지정, 시점 불명 값은 답변 근거나 필터로 쓰지 않는다.

### 반드시 지킬 모집단 규칙

1. 채권 수는 `COUNT(DISTINCT pd_no)`이며 물리 PK는 `(pd_no, pd_exg_mkt, info_seq)`다. 구매가능은 원화·만기 미도래로 정의하고 `buyable_quantity`는 쓰지 않는다.
2. 국내 ETF 질의는 `pd_grp_no='ETF'`로 ETN 545건을 제외한다.
3. 공모펀드 질의는 `prvo_pbff_desc='공모'`로 사모 8,960건을 제외한다. 원천이 이미 `itm_no` 단독 유일키이므로 dedup 파생물을 만들지 않는다.
4. 펀드 보수 4종은 천분율(‰)이므로 합계 후 10으로 나눠 %로 표시한다. `fd_prsv_r`은 판매보수와 중복이라 합산하지 않는다.
5. 외부 관계의 실제 `as_of`(ETF 편입 2026-07-10, DART/KIND 2026-07-11 등)는 정책 상한 2026-08-24와 구분해 그대로 표시한다.

## 3. 전체 원천 컬럼


### 3.1 국내채권 `bond_kr` (21,882행 × 58컬럼)

| 컬럼 | 설명 | 타입 | 결측률 | 고유값수 | 사용 주의 |
|---|---|---|---:|---:|---|
| `after_tax_yield` | 개인 세후 운용수익률 | `double precision` | 97.1% | 475 |  |
| `applied_yield` | 민평수익률/민평금리 | `double precision` | 0.0% | 3,162 |  |
| `avg_annual_tax_yield` | 세후 연평균수익률 | `double precision` | 97.1% | 2 |  |
| `bdbns_abl_chnl_nm` | 채권매매가능채널구분명 | `text` | 97.1% | 2 |  |
| `bdbns_abl_chnl_tcd` | 채권매매가능채널구분코드 | `text` | 97.1% | 2 |  |
| `bd_inrt_tcd` | 금리구분 | `text` | 0.0% | 3 |  |
| `bd_intp_tcd` | 이자지급구분 | `text` | 0.0% | 4 |  |
| `bd_knd` | 예탁원 기준 채권종류명 | `text` | 0.7% | 33 |  |
| `bd_ofr_tcd` | 모집구분 | `text` | 0.0% | 2 |  |
| `bd_tisu_a` | 총발행금액 | `numeric(26,8)` | 0.0% | 2,790 |  |
| `buyable_quantity` | 매수가능수량 | `double precision` | 97.1% | 298 | 주최측 무효 지정. 조회·필터·근거 사용 금지 |
| `buy_yield` | 매수수익률/매수금리 | `double precision` | 97.1% | 349 | 구매가능 판정에 사용 금지. 구매가능 목록 정렬은 `applied_yield` 사용 |
| `corp_after_tax_yield` | 법인 세후 투자수익률 | `double precision` | 97.1% | 470 |  |
| `corp_pretax_yield` | 법인 세전 투자수익률 | `double precision` | 97.1% | 448 |  |
| `cov` | 컨벡시티 | `double precision` | 0.1% | 15,802 |  |
| `crd_grd` | 적용신용등급 | `text` | 18.4% | 16 |  |
| `crd_grd_dt` | 신용등급 적용일자(등급 미변경 시 과거 일자로 유지될 수 있음) | `text` | 18.3% | 2,152 |  |
| `curr_cd` | 통화코드 | `text` | 0.0% | 2 |  |
| `depo_equiv_yield_154` | 예금환산수익률(세율 15.4 기준) | `double precision` | 97.1% | 416 |  |
| `depo_equiv_yield_495` | 은행환산수익률(세율 49.5 기준) | `double precision` | 97.1% | 446 |  |
| `dirty` | 이자부단가/Dirty Price | `double precision` | 0.1% | 16,604 |  |
| `dur` | 듀레이션 | `double precision` | 0.1% | 14,588 |  |
| `eval_price` | 평가일단가/Clean Price 성격 | `double precision` | 0.0% | 16,605 |  |
| `exg_close_price` | 장내 채권종가 | `double precision` | 18.9% | 284 |  |
| `exg_close_price_base_dt` | 장내 채권종가/종가수익률 기준일 | `text` | 94.2% | 100 |  |
| `exg_close_yield` | 장내 종가수익률 | `double precision` | 18.9% | 300 |  |
| `exrt_grte_ern_r` | 만기보장수익률 | `numeric(20,12)` | 0.0% | 19 |  |
| `exrt_grte_ern_r_tcd` | 만기보장수익률구분코드 | `text` | 0.0% | 6 |  |
| `exrt_rpy_r` | 만기상환율 | `numeric(20,12)` | 0.0% | 101 |  |
| `info_base_dt` | 판매/민평 공통 기준일 | `text` | 0.0% | 1 |  |
| `info_seq` | 동일 종목/시장/기준일 내 판매 LOT 구분 순번 | `bigint` | 0.0% | 3 | 복합 PK 구성 |
| `isu_bal_amt` | 발행잔액/발행금액잔액 | `double precision` | 0.0% | 2,947 |  |
| `isu_dt` | 발행일자 | `text` | 0.0% | 2,488 |  |
| `mat_dt` | 상환일자(영구채는 1차 콜행사개시일) | `text` | 0.0% | 3,799 | 구매가능 판정 축: 원화이면서 만기 미도래 |
| `ndy_applied_yield` | 익일 민평수익률/민평금리 | `double precision` | 0.1% | 3,156 |  |
| `ndy_cov` | 익일 컨벡시티 | `double precision` | 0.1% | 15,727 |  |
| `ndy_dirty` | 익일 이자부단가 | `double precision` | 0.1% | 16,509 |  |
| `ndy_dur` | 익일 듀레이션 | `double precision` | 0.1% | 14,477 |  |
| `ndy_eval_price` | 익일 평가일단가 | `double precision` | 0.1% | 16,504 |  |
| `pd_abrv_eng_nm` | 상품영문약어명 | `text` | 0.1% | 20,482 |  |
| `pd_abrv_nm` | 상품약어명 | `text` | 0.1% | 20,477 |  |
| `pd_ctry_cd` | 국가코드: 종목번호 앞 2자리(KR 등) | `text` | 0.0% | 2 |  |
| `pd_eng_nm` | 상품영문명 | `text` | 0.0% | 20,492 |  |
| `pd_exg_mkt` | 거래구분 | `text` | 0.0% | 2 | 복합 PK 구성 |
| `pd_nm` | 상품명/채권명 | `text` | 0.0% | 20,499 |  |
| `pd_no` | 상품번호/채권종목번호 | `text` | 0.0% | 20,497 | 단독 비유일(20,497종). 종목 수는 `DISTINCT pd_no` |
| `pd_pbcm` | 발행기관/발행자명 | `text` | 0.7% | 1,819 |  |
| `pd_pen_tr_yn` | 퇴직연금 편입 가능 여부 | `text` | 0.0% | 2 |  |
| `pd_risk_gcd` | 상품위험등급 원문 코드 | `text` | 0.0% | 7 |  |
| `pd_risk_nm` | 상품위험등급명 | `text` | 0.0% | 7 |  |
| `pd_std_info_update` | 민평정보 기준일/최근 업데이트 일자 | `text` | 0.0% | 1 |  |
| `pref_tax_yield` | 세금우대 세후 운용수익률 | `double precision` | 97.1% | 470 |  |
| `remaining_days` | 잔존일수 | `double precision` | 0.0% | 3,796 |  |
| `sale_yield_base_dt` | 판매수익률 기준일 | `text` | 97.1% | 2 |  |
| `srfc_irt` | 표면이자율/쿠폰금리 | `double precision` | 0.0% | 3,700 |  |
| `std_pd_mcls_nm` | 상품중분류명 | `text` | 0.0% | 3 |  |
| `std_pd_scls_nm` | 상품소분류명 | `text` | 0.0% | 13 |  |
| `trade_price` | 매매단가(표준투입단가) | `double precision` | 97.1% | 392 |  |

### 3.2 국내 ETF/ETN `etf_kr` (1,780행 × 98컬럼)

| 컬럼 | 설명 | 타입 | 결측률 | 고유값수 | 사용 주의 |
|---|---|---|---:|---:|---|
| `cu_base_index` | 기초지수 | `text` | 96.9% | 20 |  |
| `cu_charge_etc_rt` | 기타비용요율 | `text` | 87.8% | 2 |  |
| `cu_charge_rt` | 총보수요율 | `text` | 87.8% | 18 |  |
| `cu_fund_mgmt_co` | 운용사 | `text` | 0.0% | 100 |  |
| `cu_lev_fector` | 배수 | `text` | 10.2% | 8 |  |
| `cu_strtegy` | 운용전략 | `text` | 8.7% | 5 |  |
| `cu_upt_dt` | 변동갱신일자 | `text` | 10.2% | 23 |  |
| `du_bpr` | 기준가 | `numeric(28,2)` | 0.2% | 1,428 |  |
| `du_chas_errt` | 추적오차율 | `numeric(28,2)` | 10.2% | 498 | 08-24 실측값 사용 가능. 기준일 함께 표기 |
| `du_chas_errt_base_dt` | 추적오차율 기준일 | `text` | 10.2% | 23 |  |
| `du_clpr` | 종가 | `numeric(28,2)` | 0.2% | 1,437 |  |
| `du_diff_rt` | 괴리율 | `numeric(28,2)` | 10.2% | 304 | 08-24 실측값 사용 가능. 극단값 범위 검증 필요 |
| `du_diff_rt_base_dt` | 괴리율 기준일 | `text` | 10.2% | 23 |  |
| `du_er_1d` | 수익률_1D | `numeric(28,2)` | 11.0% | 693 |  |
| `du_er_1m` | 수익률_1M | `numeric(28,2)` | 11.0% | 1,094 |  |
| `du_er_1y` | 수익률_1Y | `numeric(28,2)` | 20.4% | 1,206 |  |
| `du_er_3m` | 수익률_3M | `numeric(28,2)` | 12.8% | 1,182 |  |
| `du_er_6m` | 수익률_6M | `numeric(28,2)` | 16.5% | 1,221 |  |
| `du_er_ytd` | 수익률_YTD | `numeric(28,2)` | 17.0% | 1,255 |  |
| `du_hpr` | 고가 | `numeric(28,2)` | 0.2% | 1,387 |  |
| `du_last_aum` | 최종AUM | `numeric(28,2)` | 10.2% | 1,172 |  |
| `du_last_nav` | 최종NAV | `numeric(28,2)` | 10.2% | 1,584 |  |
| `du_lpr` | 시가 | `numeric(28,2)` | 0.2% | 1,363 |  |
| `du_nav_base_dt` | NAV 기준일 | `text` | 10.2% | 23 |  |
| `du_nav_rnf_amt` | 전일NAV등락금액 | `numeric(28,2)` | 10.2% | 1,507 |  |
| `du_nav_yday` | 전일NAV | `numeric(28,2)` | 10.2% | 1,585 |  |
| `du_upt_dt` | 일간갱신일자 | `text` | 10.2% | 23 |  |
| `du_val_1d` | 일거래대금 | `numeric(28,2)` | 0.2% | 1,465 |  |
| `du_val_1m` | 일거래대금평균_1M | `numeric(28,2)` | 0.9% | 1,516 |  |
| `du_val_5d` | 일거래대금평균_5D | `numeric(28,2)` | 0.3% | 1,507 |  |
| `du_vlty_1m` | 최근 20거래일 연환산 변동성(%) | `numeric(28,8)` | 5.8% | 1,627 |  |
| `du_vlty_1y` | 최근 252거래일 연환산 변동성(%) | `numeric(28,8)` | 26.5% | 1,291 |  |
| `du_vlty_3m` | 최근 60거래일 연환산 변동성(%) | `numeric(28,8)` | 10.4% | 1,550 |  |
| `du_vlty_6m` | 최근 120거래일 연환산 변동성(%) | `numeric(28,8)` | 16.5% | 1,449 |  |
| `du_vlty_base_dt` | 변동성 산출 기준일 | `text` | 4.8% | 50 |  |
| `du_vol_1d` | 일거래량 | `numeric(28,2)` | 0.2% | 1,313 |  |
| `du_vol_avg_1m` | 거래량평균_1M | `numeric(28,2)` | 0.8% | 1,506 |  |
| `du_vol_avg_5d` | 거래량평균_5D | `numeric(28,2)` | 0.3% | 1,458 |  |
| `fn_average_coupon` | 평균쿠폰이자율 | `numeric(28,8)` | 88.8% | 197 |  |
| `fn_average_maturity` | 평균잔존만기 | `numeric(28,8)` | 100.0% | 1 |  |
| `fn_average_quality` | 평균신용품질 | `text` | 95.8% | 33 |  |
| `fn_base_dt` | 펀더멘털 기준일 | `text` | 35.1% | 2 |  |
| `fn_effective_duration` | 듀레이션 | `numeric(28,8)` | 100.0% | 1 |  |
| `fn_effective_maturity` | 실질만기 | `numeric(28,8)` | 87.9% | 213 |  |
| `fn_modified_duration` | 수정듀레이션 | `numeric(28,8)` | 100.0% | 1 |  |
| `fn_nominal_maturity` | 명목만기 | `numeric(28,8)` | 87.9% | 213 |  |
| `fn_portfolio_dt` | 포트폴리오 기준일 | `text` | 37.2% | 18 |  |
| `pd_abrv_nm` | 상품약어명 | `text` | 0.0% | 1,773 |  |
| `pd_circ_net_tamt` | 유통순자산총액 | `numeric(28,2)` | 10.2% | 671 |  |
| `pd_circ_stk_cnt` | 유통주식수 | `numeric(28,2)` | 10.2% | 630 |  |
| `pd_curr_cd` | 상품통화코드 | `text` | 0.2% | 3 |  |
| `pd_curr_nm` | 상품통화명 | `text` | 0.2% | 3 |  |
| `pd_divd_amt_ann` | 연간 추정 분배금 | `numeric(28,8)` | 53.4% | 590 |  |
| `pd_divd_amt_pshr` | 주당 분배금(원천 우선, 없으면 회당 추정) | `numeric(28,8)` | 32.1% | 969 |  |
| `pd_dvid_base_dt` | 분배정보 기준일 | `text` | 32.1% | 2 |  |
| `pd_dvid_cycl` | 분배주기(A/Q/M/S) | `text` | 32.1% | 5 |  |
| `pd_dvid_inc_dist` | 원천 성과배분/분배금 | `numeric(28,8)` | 100.0% | 1 |  |
| `pd_dvid_nav` | 분배금 계산 기준 NAV | `numeric(28,8)` | 32.1% | 1,209 |  |
| `pd_dvid_pay_cnt` | 연간 지급횟수 | `numeric(28,0)` | 32.1% | 5 |  |
| `pd_dvid_pay_months` | 분배 지급월 | `text` | 32.1% | 16 |  |
| `pd_dvid_prc_base_dt` | 분배금 계산 NAV 기준일 | `text` | 32.1% | 32 |  |
| `pd_dvid_tax_basis` | 분배 과세기준 | `text` | 32.1% | 2 |  |
| `pd_dvid_yield` | 연환산 분배수익률 | `numeric(28,8)` | 32.1% | 968 |  |
| `pd_exg_mkt_cd` | 거래소코드 | `text` | 0.2% | 2 |  |
| `pd_exg_mkt_nm` | 거래소명 | `text` | 0.2% | 2 |  |
| `pd_grp_no` | 상품군종류 | `text` | 0.0% | 2 | ETF 질의는 `ETF` 필터 필수(ETF 1,235 / ETN 545) |
| `pd_isin_cd` | Refinitiv ISIN | `text` | 32.1% | 1,209 |  |
| `pd_itm_no` | 상품번호 | `text` | 0.0% | 1,780 |  |
| `pd_itm_no_ma` | 상품번호_미래에셋 | `text` | 0.0% | 1,780 |  |
| `pd_lst_stk_cnt` | 상품상장주식수 | `numeric(28,2)` | 0.0% | 688 |  |
| `pd_lste_dt` | 상품거래종료일자 | `text` | 0.2% | 92 |  |
| `pd_lstg_dt` | 상품거래가능일자 | `text` | 0.2% | 613 |  |
| `pd_mkt_id` | 상품거래시장코드 | `text` | 0.2% | 2 |  |
| `pd_mkt_nm` | 상품거래시장 | `text` | 0.2% | 2 |  |
| `pd_net_tamt` | 순자산총액 | `numeric(28,2)` | 10.2% | 1,596 |  |
| `pd_nm` | 상품명 | `text` | 0.0% | 1,780 |  |
| `pd_pen_risk_nm` | 연금거래위험구분 | `text` | 0.0% | 3 |  |
| `pd_pen_tr_yn` | 연금거래가능여부 | `text` | 0.0% | 2 |  |
| `pd_ric` | Refinitiv RIC | `text` | 32.1% | 1,209 |  |
| `pd_risk_cd` | 상품등급코드 | `text` | 0.0% | 6 |  |
| `pd_risk_nm` | 상품등급명 | `text` | 0.0% | 6 |  |
| `pd_sale_yn` | 상품판매여부 | `text` | 0.0% | 2 |  |
| `pd_sect_cd` | ETF 섹터코드 | `text` | 10.2% | 6 |  |
| `pd_spac_yn` | SPAC 여부 | `text` | 10.2% | 2 |  |
| `pd_stk_cnt` | 상장주식수 | `numeric(28,2)` | 10.2% | 662 |  |
| `pd_ticker` | Refinitiv 티커 | `text` | 32.1% | 1,209 |  |
| `pd_tr_yn` | 상품거래정지혀부 | `text` | 0.2% | 3 |  |
| `ref_ast_type` | refinitiv 자산유형 | `text` | 32.1% | 8 |  |
| `ref_base_dt` | refinitiv 기준일 | `text` | 32.1% | 2 |  |
| `ref_base_index` | refinitiv 벤치마크 | `text` | 32.1% | 906 |  |
| `ref_fund_mgmt_co` | refinitiv 운용사 | `text` | 32.1% | 30 |  |
| `ref_geo_focus` | refinitiv 투자지역 | `text` | 32.1% | 24 |  |
| `ru_mkt_price` | 현재가 | `numeric(28,2)` | 0.2% | 1,439 |  |
| `ru_mkt_volume` | 거래량 | `numeric(28,2)` | 0.2% | 1,313 |  |
| `wu_core_yn` | 핵심ETF여부 | `text` | 0.0% | 2 |  |
| `wu_inv_ast_type` | 투자자산군 | `text` | 0.0% | 9 |  |
| `wu_inv_rgn` | 투자지역 | `text` | 0.0% | 11 |  |
| `wu_upt_dt` | 주간갱신일자 | `text` | 0.2% | 2 |  |

### 3.3 해외 ETF/ETN `etf_gl` (6,037행 × 49컬럼)

| 컬럼 | 설명 | 타입 | 결측률 | 고유값수 | 사용 주의 |
|---|---|---|---:|---:|---|
| `cu_base_index` | 기초지수 | `text` | 0.2% | 1,851 |  |
| `cu_charge_rt` | 연간보수율 | `numeric(18,6)` | 0.0% | 130 |  |
| `cu_etn_yn` | ETN 여부 | `text` | 98.9% | 2 |  |
| `cu_fund_mgmt_co` | 운용사 | `text` | 0.2% | 383 |  |
| `cu_index_repl_mthd` | 인덱스 복제방법 | `text` | 60.1% | 5 |  |
| `cu_index_tracking_yn` | 인덱스 추적 여부 | `text` | 60.1% | 2 |  |
| `cu_inverse_short_yn` | 인버스 또는 숏 여부 | `text` | 97.0% | 2 |  |
| `cu_lev_fector` | 배수 | `numeric(18,6)` | 85.1% | 12 |  |
| `cu_strtegy` | 운용전략 | `text` | 0.2% | 5,944 |  |
| `cu_upt_dt` | 변동갱신일자 | `text` | 0.0% | 1 |  |
| `du_base_dt_match_yn` | NAV/종가 기준일 일치 여부 | `text` | 0.2% | 2 |  |
| `du_bpr` | 기준가 | `numeric(28,8)` | 0.2% | 5,437 |  |
| `du_clpr` | 종가 | `numeric(28,8)` | 0.2% | 5,400 |  |
| `du_clpr_base_dt` | 선택된 종가의 원천 기준일 | `text` | 0.2% | 110 |  |
| `du_clpr_src` | 선택된 종가 원천 컬럼 | `text` | 0.2% | 2 |  |
| `du_diff_rt` | 종가 대비 추정 NAV 괴리율 | `numeric(28,6)` | 100.0% | 4 | 전량 결측으로 사용 금지 |
| `du_er_1d` | 수익률_1D | `numeric(28,6)` | 0.2% | 960 |  |
| `du_hpr` | 고가 | `numeric(28,8)` | 0.2% | 5,031 |  |
| `du_last_aum` | 일간 순자산총액 | `numeric(28,2)` | 3.4% | 4,900 |  |
| `du_last_nav` | 추정 주당 NAV | `numeric(28,6)` | 87.4% | 530 |  |
| `du_lpr` | 저가 | `numeric(28,8)` | 0.2% | 5,035 |  |
| `du_nav_base_dt` | NAV 원천 etf_reference 기준일 | `text` | 0.0% | 1 |  |
| `du_opr` | 시가 | `numeric(28,8)` | 0.2% | 4,685 |  |
| `du_upt_dt` | 일간갱신일자 | `text` | 0.0% | 108 |  |
| `du_val_1d` | 외화거래대금 | `numeric(28,8)` | 0.2% | 5,753 |  |
| `du_vol_1d` | 거래량 | `numeric(28,8)` | 0.2% | 4,950 |  |
| `pd_abrv_nm` | 상품약어명_티커 | `text` | 0.0% | 6,031 |  |
| `pd_curr_cd` | 펀드통화코드 | `text` | 0.2% | 3 |  |
| `pd_exg_mkt_cd` | 거래소코드 | `text` | 0.0% | 5 |  |
| `pd_grp_no` | 상품군종류 | `text` | 0.0% | 2 | ETF 5,972 / ETN 65 구분 |
| `pd_isin_cd` | ISIN 코드 | `text` | 0.2% | 5,963 |  |
| `pd_itm_no` | 해외 ETF RIC | `text` | 0.0% | 6,037 |  |
| `pd_itm_no_ma` | 해외 ETF RIC_PDF 조인키 | `text` | 0.0% | 6,037 |  |
| `pd_lipper_id` | Lipper 펀드코드 | `text` | 0.2% | 5,964 |  |
| `pd_lstg_dt` | 설정일 | `text` | 0.0% | 2,006 |  |
| `pd_lst_price` | 액면가 | `numeric(28,8)` | 0.2% | 3 |  |
| `pd_lst_stk_cnt` | 상장주식수 | `numeric(28,2)` | 0.0% | 3,213 |  |
| `pd_mkt_id` | 거래소국가코드 | `text` | 0.0% | 1 |  |
| `pd_nm` | 상품명 | `text` | 0.0% | 6,009 |  |
| `pd_sale_yn` | 판매여부 | `text` | 0.2% | 2 |  |
| `pd_trd_ccy` | 거래통화코드 | `text` | 0.0% | 1 | 거래통화 정본. 전 행 USD |
| `pd_tr_yn` | 거래정지여부 | `text` | 0.2% | 2 |  |
| `pd_us_cik` | 미국 CIK | `text` | 0.3% | 390 |  |
| `ru_mkt_price` | 실시간 현재가 | `numeric(28,8)` | 0.2% | 5,400 |  |
| `ru_mkt_volume` | 실시간 거래량 | `numeric(28,8)` | 0.2% | 4,950 |  |
| `wu_core_yn` | 핵심 ETF 여부 | `text` | 98.2% | 2 |  |
| `wu_inv_ast_type` | 투자자산군 | `text` | 0.2% | 7 |  |
| `wu_inv_rgn` | 투자지역 | `text` | 0.2% | 60 |  |
| `wu_upt_dt` | 주간갱신일자 | `text` | 0.0% | 1 |  |

### 3.4 국내 펀드 `fund_pub` (23,676행 × 75컬럼)

| 컬럼 | 설명 | 타입 | 결측률 | 고유값수 | 사용 주의 |
|---|---|---|---:|---:|---|
| `bmrk_eng_nm` | 벤치마크영문명 | `text` | 52.4% | 387 |  |
| `bmrk_nm` | 벤치마크명 | `text` | 52.4% | 390 |  |
| `bns_bpr` | 매매기준가 | `numeric(38,15)` | 60.2% | 9,075 |  |
| `curr_cd` | 통화코드 | `text` | 0.0% | 7 |  |
| `exchdg_yn` | 환헤지여부 | `text` | 70.5% | 3 |  |
| `fd_daily_bas_dt` | 펀드데일리정보 기준일자 | `text` | 60.2% | 906 |  |
| `fd_estb_ctry_cd` | 펀드설립국가코드 | `text` | 0.0% | 7 |  |
| `fd_ivst_rgn_desc` | 펀드투자지역구분코드 설명 | `text` | 0.0% | 9 |  |
| `fd_last_dstb_actg_bss_dt` | 최근 분배 회계기초일자 | `text` | 54.1% | 2,020 |  |
| `fd_last_dstb_actg_eot_dt` | 최근 분배 회계기말일자 | `text` | 54.1% | 1,786 |  |
| `fd_last_dstb_r` | 최근 분배율 | `numeric(20,12)` | 54.1% | 4,244 |  |
| `fd_mm18_ern_r` | 펀드 18개월수익률 | `numeric(30,2)` | 70.9% | 4,646 |  |
| `fd_mm1_ern_r` | 펀드 1개월수익률 | `numeric(30,2)` | 68.8% | 1,443 |  |
| `fd_mm3_ern_r` | 펀드 3개월수익률 | `numeric(30,2)` | 69.1% | 2,124 |  |
| `fd_mm6_ern_r` | 펀드 6개월수익률 | `numeric(30,2)` | 69.5% | 3,164 |  |
| `fd_nast_suma` | 펀드 순자산 | `numeric(22,4)` | 60.2% | 9,410 |  |
| `fd_price_bas_dt` | 펀드 기준가/수익률 기준일자 | `text` | 60.2% | 906 |  |
| `fd_prsv_r` | 보전율 | `numeric(20,12)` | 0.0% | 790 | `sale_co_rwrd_r`와 동일해 총보수 합산에서 제외 |
| `fd_sbpr` | 시가평가금액 | `numeric(30,12)` | 0.0% | 1,978 |  |
| `fd_set_pcd` | 펀드설정유형코드 | `text` | 0.0% | 3 |  |
| `fd_wk1_ern_r` | 펀드 1주일수익률 | `numeric(30,2)` | 100.0% | 1 | 전량 결측으로 사용 금지 |
| `fd_yr1_ern_r` | 펀드 1년수익률 | `numeric(30,2)` | 70.3% | 4,470 |  |
| `fd_yr2_ern_r` | 펀드 2년수익률 | `numeric(30,2)` | 71.5% | 4,953 |  |
| `fd_yr3_ern_r` | 펀드 3년수익률 | `numeric(30,2)` | 72.6% | 5,111 |  |
| `fd_yr5_ern_r` | 펀드 5년수익률 | `numeric(30,2)` | 74.7% | 4,883 |  |
| `frc_bpr_itm_yn` | 외화기준가종목여부 | `text` | 0.0% | 2 |  |
| `fss_itm_no` | 금융감독원종목번호 | `text` | 0.2% | 11,971 |  |
| `han_clas_fee_type` | 클래스 수수료 부과 유형 | `text` | 59.3% | 4 |  |
| `han_clas_nm` | 클래스 한글 표기 | `text` | 59.3% | 196 |  |
| `han_clas_policies` | 클래스 부가 정책 | `text` | 73.5% | 34 |  |
| `han_clas_sales_channel` | 클래스 판매채널 | `text` | 59.4% | 4 |  |
| `hdge_fd_yn` | 헤지펀드여부 | `text` | 0.0% | 2 |  |
| `int_dvd_desc` | 이자배당구분코드 설명 | `text` | 0.0% | 3 |  |
| `itm_abrv_nm` | 종목약어명 | `text` | 0.0% | 23,588 |  |
| `itm_eabrv_nm` | 종목영문약어명 | `text` | 99.4% | 144 |  |
| `itm_eng_nm` | 종목영문명 | `text` | 0.0% | 23,403 |  |
| `itm_nm` | 종목명 | `text` | 0.0% | 23,624 |  |
| `itm_no` | 종목번호 | `text` | 0.0% | 23,676 | 단독 PK. 원천이 이미 1행=1펀드 |
| `kofia_fd_ccd` | 금융투자협회펀드분류코드 | `text` | 0.2% | 6,766 |  |
| `ksd_itm_no` | 예탁원종목번호 | `text` | 10.0% | 21,291 |  |
| `mtco_itm_no` | 운용사종목번호 | `text` | 0.5% | 14,059 |  |
| `ofsfd_yn` | 역외펀드여부 | `text` | 0.0% | 2 |  |
| `ofwk_trus_rwrd_r` | 일반사무관리보수 | `numeric(20,12)` | 0.0% | 70 | 보수 천분율(‰). 4종 합계 후 ÷10하여 % 변환 |
| `or_attr_desc` | 운용속성구분코드 설명 | `text` | 0.0% | 14 |  |
| `or_co_rwrd_r` | 집합투자업자보수 | `numeric(20,12)` | 0.0% | 754 | 보수 천분율(‰). 4종 합계 후 ÷10하여 % 변환 |
| `or_co_xtn_itt_cd` | 운용회사대외기관코드 | `text` | 0.0% | 275 |  |
| `ovrs_fd_desc` | 해외펀드구분코드 설명 | `text` | 0.0% | 4 |  |
| `pers_corp_desc` | 개인법인구분코드 설명 | `text` | 0.0% | 3 |  |
| `pfiv_sale_cntl_tcd` | 전문투자자판매제어구분코드 | `text` | 0.0% | 4 |  |
| `prfd_attr_cds` | 펀드별속성코드 목록(쉼표 구분) | `text` | 52.4% | 8,927 | 원천에서 집약된 속성코드 목록. 별도 dedup 불필요 |
| `prfd_attr_cnt` | 펀드별속성 개수 | `text` | 0.0% | 14 |  |
| `prfd_attr_search_text` | 상품검색용 속성 코드/명칭 | `text` | 52.4% | 10,574 |  |
| `prvo_fd_desc` | 사모펀드구분코드 설명 | `text` | 0.0% | 4 |  |
| `prvo_pbff_desc` | 사모/공모구분코드 설명 | `text` | 0.0% | 2 | 공모 질의는 `공모` 필터 필수(14,716 / 사모 8,960) |
| `rptt_ksd_itm_no` | 대표예탁원종목번호 | `text` | 0.5% | 6,886 | `KR0000000000`, `000000000000`, 결측 sentinel 제외 |
| `sale_co_rwrd_r` | 판매회사보수 | `numeric(20,12)` | 0.0% | 769 | 보수 천분율(‰). 4종 합계 후 ÷10하여 % 변환 |
| `sale_yn` | 판매여부 | `text` | 0.0% | 2 |  |
| `std_itm_no` | 표준종목번호 | `text` | 18.4% | 18,948 |  |
| `thco_sale_yn` | 당사판매여부 | `text` | 55.2% | 2 |  |
| `trusc_rwrd_r` | 신탁업자보수 | `numeric(20,12)` | 0.0% | 96 | 보수 천분율(‰). 4종 합계 후 ÷10하여 % 변환 |
| `trusc_xtn_itt_cd` | 수탁회사대외기관코드 | `text` | 0.2% | 51 |  |
| `zrin_attr_nms` | 제로인속성명 목록(쉼표 구분) | `text` | 52.4% | 10,578 |  |
| `zrin_btyp_cd` | 제로인대유형코드 | `text` | 52.4% | 19 |  |
| `zrin_btyp_nm` | 제로인대유형명 | `text` | 52.4% | 19 |  |
| `zrin_dmst_bd_cmst_rt` | 제로인국내채권구성비율 | `numeric(26,12)` | 60.2% | 284 |  |
| `zrin_dmst_stk_cmst_rt` | 제로인국내주식구성비율 | `numeric(26,12)` | 60.2% | 337 |  |
| `zrin_etc_ast_cmst_rt` | 제로인기타자산구성비율 | `numeric(26,12)` | 60.2% | 918 |  |
| `zrin_fd_cmst_rt` | 제로인펀드구성비율 | `numeric(26,12)` | 60.2% | 1,137 |  |
| `zrin_fd_ivst_risk_gcd` | 제로인펀드투자위험등급코드 | `text` | 63.3% | 7 |  |
| `zrin_fd_ivst_risk_grd_nm` | 제로인펀드투자위험등급명 | `text` | 63.3% | 9 |  |
| `zrin_liqt_cmst_rt` | 제로인유동성구성비율 | `numeric(26,12)` | 60.2% | 974 |  |
| `zrin_ovrs_bd_cmst_rt` | 제로인해외채권구성비율 | `numeric(26,12)` | 60.2% | 16 |  |
| `zrin_ovrs_stk_cmst_rt` | 제로인해외주식구성비율 | `numeric(26,12)` | 60.2% | 107 |  |
| `zrin_pcd` | 제로인유형코드 | `text` | 52.4% | 105 |  |
| `zrin_ptn_nm` | 제로인유형명 | `text` | 52.4% | 103 |  |

## 4. 답변 근거와 변경 관리

- 모든 수치에는 실제 기준일과 `sourceTable.sourceColumn`을 붙인다.
- 컬럼이 없거나 전량 결측·무효이면 추측하지 않고 “확인할 수 없음”으로 답한다.
- 스키마 변경 시 `script/build_data_inventory.py`와 `src/kb/build_schema_catalog.py`를 먼저 실행한 뒤 이 문서를 다시 대조한다.
- 과거 배포본 상세 분석은 현재 계약이 아니며 Git 이력에서만 조회한다.
