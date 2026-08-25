# TABLE DEFINITION V2.0

자동 생성 파일입니다. 모든 물리 컬럼은 공식 XLSX 또는 `src/kb/catalog_v2.py`의 단일 카탈로그에서 생성됩니다.

## `raw.bond_kr_master`

- 종류: table
- 설명: PRBD01N001 공식 원천 42,394행
- grain: 국내 채권 상품
- PK: `pd_no`
- 인덱스: pd_no
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `pd_no` | `text` | N | 1 |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 2 | `pd_exg_mkt` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 3 | `pd_nm` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 4 | `pd_abrv_nm` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 5 | `pd_eng_nm` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 6 | `pd_abrv_eng_nm` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 7 | `pd_ctry_cd` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 8 | `pd_pbcm` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 9 | `std_pd_mcls_nm` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 10 | `std_pd_scls_nm` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 11 | `bd_knd` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 12 | `curr_cd` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 13 | `isu_bal_amt` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 14 | `isu_dt` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 15 | `mat_dt` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 16 | `srfc_irt` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 17 | `pd_evco_crd_grd` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 18 | `pd_risk_gcd` | `bigint` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 19 | `pd_std_info_update` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 20 | `buy_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 21 | `corp_pretax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 22 | `corp_after_tax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 23 | `after_tax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 24 | `pref_tax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 25 | `avg_annual_tax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 26 | `depo_equiv_yield_154` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 27 | `buyable_quantity` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 28 | `remaining_days` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 29 | `dur` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 30 | `cov` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 31 | `ndy_dur` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 32 | `ndy_cov` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 33 | `eval_price` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 34 | `applied_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 35 | `dirty` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 36 | `ndy_eval_price` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 37 | `ndy_applied_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 38 | `ndy_dirty` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 39 | `crd_grd` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 40 | `crd_grd_dt` | `double precision` | Y |  |  | 공식 문서 미표기 | pd_std_info_update |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |

## `raw.etf_kr_master`

- 종류: table
- 설명: PREF01N001 공식 원천 1,734행
- grain: 국내 ETF/ETN 상품
- PK: `pd_itm_no`
- 인덱스: pd_itm_no
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `cu_base_index` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 기초지수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 2 | `cu_charge_etc_rt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 기타비용요율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 3 | `cu_charge_rt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 총보수요율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 4 | `cu_fund_mgmt_co` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 운용사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 5 | `cu_lev_fector` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 배수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 6 | `cu_strtegy` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 운용전략 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 7 | `cu_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt | 변동갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 8 | `du_bpr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 기준가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 9 | `du_chas_errt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 추적오차율 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 10 | `du_clpr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 종가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 11 | `du_diff_rt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 괴리율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 12 | `du_er_1d` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 수익률_1D | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 13 | `du_er_1m` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 수익률_1M | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 14 | `du_er_1y` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 수익률_1Y | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 15 | `du_er_3m` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 수익률_3M | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 16 | `du_er_6m` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 수익률_6M | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 17 | `du_er_ytd` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 수익률_YTD | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 18 | `du_hpr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 고가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 19 | `du_last_aum` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 최종AUM | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 20 | `du_last_nav` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 최종NAV | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 21 | `du_lpr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 시가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 22 | `du_nav_rnf_amt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 전일NAV등락금액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 23 | `du_nav_yday` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 전일NAV | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 24 | `du_upt_dt` | `timestamp without time zone` | Y |  |  | 공식 문서 미표기 | du_upt_dt | 일간갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 25 | `du_val_1d` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 일거래대금 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 26 | `du_val_1m` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 일거래대금평균_1M | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 27 | `du_val_5d` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 일거래대금평균_5D | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 28 | `du_vol_1d` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 일거래량 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 29 | `du_vol_avg_1m` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 거래량평균_1M | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 30 | `du_vol_avg_5d` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 거래량평균_5D | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 31 | `nru_mkt_diff_rt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 괴리율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 32 | `nru_mkt_inav` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 장중 iNAV | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 33 | `pd_abrv_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품약어명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 34 | `pd_circ_net_tamt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 유통순자산총액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 35 | `pd_circ_stk_cnt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 유통주식수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 36 | `pd_curr_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품통화코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 37 | `pd_curr_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품통화명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 38 | `pd_divd_amt_pshr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 주당 배당금 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 39 | `pd_dvid_cycl` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 당주기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 40 | `pd_dvid_yield` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 배당수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 41 | `pd_exg_mkt_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 거래소코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 42 | `pd_exg_mkt_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 거래소명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 43 | `pd_grp_no` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품군종류 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 44 | `pd_itm_no` | `text` | N | 1 |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 45 | `pd_itm_no_ma` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품번호_미래에셋 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 46 | `pd_lst_price` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품액면가 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 47 | `pd_lst_stk_cnt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품상장주식수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 48 | `pd_lste_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품거래종료일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 49 | `pd_lstg_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품거래가능일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 50 | `pd_mkt_id` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품거래시장코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 51 | `pd_mkt_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품거래시장 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 52 | `pd_nav_pshr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 주당 순자산가치 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 53 | `pd_net_ast_pshr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 주당 순자산 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 54 | `pd_net_prft_pshr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 주당 순이익 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 55 | `pd_net_rt_ast_pshr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 주당 순자산비율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 56 | `pd_net_tamt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 순자산총액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 57 | `pd_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 58 | `pd_pen_risk_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 연금거래위험구분 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 59 | `pd_pen_tr_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 연금거래가능여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 60 | `pd_risk_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품등급코드 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 61 | `pd_risk_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품등급명 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 62 | `pd_sale_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품판매여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 63 | `pd_sect_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | ETF 섹터코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 64 | `pd_sect_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | ETF 섹터명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 65 | `pd_spac_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | SPAC 여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 66 | `pd_stk_cnt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상장주식수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 67 | `pd_tr_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 상품거래정지혀부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 68 | `ru_mkt_price` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 현재가 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 69 | `ru_mkt_volume` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 거래량 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 70 | `wu_core_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 핵심ETF여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 71 | `wu_inv_ast_type` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 투자자산군 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 72 | `wu_inv_rgn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt | 투자지역 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 73 | `wu_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | wu_upt_dt | 주간갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |

## `raw.etf_gl_master`

- 종류: table
- 설명: PREF02N001 공식 원천 5,646행
- grain: 해외 ETF/ETN 상품
- PK: `pd_itm_no`
- 인덱스: pd_itm_no
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `cu_base_index` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 2 | `cu_charge_rt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 3 | `cu_etn_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 4 | `cu_fund_mgmt_co` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 5 | `cu_index_repl_mthd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 6 | `cu_index_tracking_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 7 | `cu_inverse_short_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 8 | `cu_lev_fector` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 9 | `cu_strtegy` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 10 | `cu_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 11 | `du_base_dt_match_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 12 | `du_bpr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 13 | `du_clpr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 14 | `du_clpr_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | du_clpr_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 15 | `du_clpr_src` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 16 | `du_diff_rt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 17 | `du_er_1d` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 18 | `du_hpr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 19 | `du_last_aum` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 20 | `du_last_nav` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 21 | `du_lpr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 22 | `du_nav_base_dt` | `timestamp without time zone` | Y |  |  | 공식 문서 미표기 | du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 23 | `du_opr` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 24 | `du_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | du_upt_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 25 | `du_val_1d` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 26 | `du_vol_1d` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 27 | `pd_abrv_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 28 | `pd_curr_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 29 | `pd_exg_mkt_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 30 | `pd_grp_no` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 31 | `pd_isin_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 32 | `pd_itm_no` | `text` | N | 1 |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 33 | `pd_itm_no_ma` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 34 | `pd_lipper_id` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 35 | `pd_lstg_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 36 | `pd_lst_price` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 37 | `pd_lst_stk_cnt` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 38 | `pd_mkt_id` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 39 | `pd_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 40 | `pd_sale_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 41 | `pd_trd_ccy` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 42 | `pd_tr_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 43 | `pd_us_cik` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 44 | `ru_mkt_price` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 45 | `ru_mkt_volume` | `numeric` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 46 | `wu_core_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 47 | `wu_inv_ast_type` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 48 | `wu_inv_rgn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt |  | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 49 | `wu_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | wu_upt_dt |  | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |

## `raw.fund_pub_master`

- 종류: table
- 설명: PRFD01N001 공식 원천 95,619행
- grain: 공모펀드 클래스 속성
- PK: `itm_no, prfd_attr_cd`
- 인덱스: itm_no,prfd_attr_cd
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `bmrk_eng_nm` | `text` | Y |  |  | 공식 문서 미표기 |  | 벤치마크영문명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 2 | `bmrk_nm` | `text` | Y |  |  | 공식 문서 미표기 |  | 벤치마크명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 3 | `curr_cd` | `text` | Y |  |  | 공식 문서 미표기 |  | 통화코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 4 | `exchdg_yn` | `text` | Y |  |  | 공식 문서 미표기 |  | 환헤지여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 5 | `fd_estb_ctry_cd` | `text` | Y |  |  | 공식 문서 미표기 |  | 펀드설립국가코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 6 | `fd_ivst_rgn_desc` | `text` | Y |  |  | 공식 문서 미표기 |  | 펀드투자지역구분코드 설명 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 7 | `fd_mm18_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 18개월수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 8 | `fd_mm1_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 1개월수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 9 | `fd_mm3_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 3개월수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 10 | `fd_mm6_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 6개월수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 11 | `fd_nast_suma` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 순자산 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 12 | `fd_set_pcd` | `text` | Y |  |  | 공식 문서 미표기 |  | 펀드설정유형코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 13 | `fd_wk1_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 1주일수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 14 | `fd_yr1_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 1년수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 15 | `fd_yr2_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 2년수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 16 | `fd_yr3_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 3년수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 17 | `fd_yr5_ern_r` | `numeric` | Y |  |  | 공식 문서 미표기 |  | 펀드 5년수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 18 | `frc_bpr_itm_yn` | `text` | Y |  |  | 공식 문서 미표기 |  | 외화기준가종목여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 19 | `fss_itm_no` | `text` | Y |  |  | 공식 문서 미표기 |  | 금융감독원종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 20 | `hdge_fd_yn` | `text` | Y |  |  | 공식 문서 미표기 |  | 헤지펀드여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 21 | `int_dvd_desc` | `text` | Y |  |  | 공식 문서 미표기 |  | 이자배당구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 22 | `itm_abrv_nm` | `text` | Y |  |  | 공식 문서 미표기 |  | 종목약어명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 23 | `itm_eabrv_nm` | `text` | Y |  |  | 공식 문서 미표기 |  | 종목영문약어명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 24 | `itm_eng_nm` | `text` | Y |  |  | 공식 문서 미표기 |  | 종목영문명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 25 | `itm_nm` | `text` | Y |  |  | 공식 문서 미표기 |  | 종목명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 26 | `itm_no` | `text` | N | 1 |  | 공식 문서 미표기 |  | 종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 27 | `kofia_fd_ccd` | `text` | Y |  |  | 공식 문서 미표기 |  | 금융투자협회펀드분류코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 28 | `ksd_itm_no` | `text` | Y |  |  | 공식 문서 미표기 |  | 예탁원종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 29 | `mtco_itm_no` | `text` | Y |  |  | 공식 문서 미표기 |  | 운용사종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 30 | `ofsfd_yn` | `text` | Y |  |  | 공식 문서 미표기 |  | 역외펀드여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 31 | `or_attr_desc` | `text` | Y |  |  | 공식 문서 미표기 |  | 운용속성구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 32 | `or_co_xtn_itt_cd` | `text` | Y |  |  | 공식 문서 미표기 |  | 운용회사대외기관코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 33 | `ovrs_fd_desc` | `text` | Y |  |  | 공식 문서 미표기 |  | 해외펀드구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 34 | `pers_corp_desc` | `text` | Y |  |  | 공식 문서 미표기 |  | 개인법인구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 35 | `pfiv_sale_cntl_tcd` | `text` | Y |  |  | 공식 문서 미표기 |  | 전문투자자판매제어구분코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 36 | `prfd_attr_cd` | `text` | N | 2 |  | 공식 문서 미표기 |  | 펀드별속성코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 37 | `prvo_fd_desc` | `text` | Y |  |  | 공식 문서 미표기 |  | 사모펀드구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 38 | `prvo_pbff_desc` | `text` | Y |  |  | 공식 문서 미표기 |  | 사모/공모구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 39 | `rptt_ksd_itm_no` | `text` | Y |  |  | 공식 문서 미표기 |  | 대표예탁원종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 40 | `sale_yn` | `text` | Y |  |  | 공식 문서 미표기 |  | 판매여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 41 | `std_itm_no` | `text` | Y |  |  | 공식 문서 미표기 |  | 표준종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 42 | `thco_sale_yn` | `text` | Y |  |  | 공식 문서 미표기 |  | 당사판매여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 43 | `trusc_xtn_itt_cd` | `text` | Y |  |  | 공식 문서 미표기 |  | 수탁회사대외기관코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 44 | `zrin_fd_ivst_risk_gcd` | `text` | Y |  |  | 공식 문서 미표기 |  | 제로인펀드투자위험등급코드 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 45 | `zrin_fd_ivst_risk_grd_nm` | `text` | Y |  |  | 공식 문서 미표기 |  | 제로인펀드투자위험등급명 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL |

## `meta.dataset_snapshot`

- 종류: table
- 설명: 버전·배포일·도메인별 실질 기준일·8개 원천 해시
- grain: 데이터셋 빌드 스냅샷
- PK: `snapshot_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `snapshot_id` | `uuid` | N | 1 |  |  |  | 스냅샷 식별자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `dataset_version` | `text` | N |  |  |  |  | 데이터 버전 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `release_date` | `date` | N |  |  |  |  | 주최측 배포일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `cutoff_date` | `date` | N |  |  |  |  | 외부 근거 허용 상한 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `domain_as_of` | `jsonb` | N |  |  |  |  | 도메인별 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `source_files` | `jsonb` | N |  |  |  |  | 원천 파일명·행/열·SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `source_hash` | `text` | N |  |  |  |  | 전체 원천 manifest SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `built_at` | `timestamptz` | N |  |  |  |  | 빌드 완료 시각 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `meta.load_run`

- 종류: table
- 설명: 단계·시작/종료·행 수·검증 결과와 실패 사유
- grain: 1회 적재 실행
- PK: `run_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `run_id` | `uuid` | N | 1 |  |  |  | 적재 실행 식별자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `snapshot_id` | `uuid` | N |  | meta.dataset_snapshot.snapshot_id |  |  | 대상 스냅샷 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `started_at` | `timestamptz` | N |  |  |  |  | 적재 시작 시각 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `finished_at` | `timestamptz` | Y |  |  |  |  | 적재 종료 시각 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `status` | `text` | N |  |  |  |  | running/passed/failed | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `phase` | `text` | N |  |  |  |  | 마지막 빌드 단계 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `source_rows` | `jsonb` | N |  |  |  |  | 원천 행 수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `loaded_rows` | `jsonb` | N |  |  |  |  | 적재 행 수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `validation_result` | `jsonb` | N |  |  |  |  | 검증 결과 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `error_message` | `text` | Y |  |  |  |  | 실패 사유 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `meta.column_catalog`

- 종류: table
- 설명: 공식 설명·타입·단위·기준일·처리 규칙·출처 우선순위
- grain: 물리 컬럼 1개
- PK: `table_schema, table_name, ordinal_position`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `table_schema` | `text` | N | 1 |  |  |  | 물리 스키마 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `table_name` | `text` | N | 2 |  |  |  | 물리 테이블 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `ordinal_position` | `integer` | N | 3 |  |  |  | 컬럼 순번 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `column_name` | `text` | N |  |  |  |  | 물리 컬럼 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `data_type` | `text` | N |  |  |  |  | PostgreSQL 타입 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `is_nullable` | `boolean` | N |  |  |  |  | NULL 허용 여부 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `description` | `text` | N |  |  |  |  | 공식 또는 파생 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `unit` | `text` | N |  |  |  |  | 단위; 미표기는 '공식 문서 미표기' | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `as_of_column` | `text` | N |  |  |  |  | 실질 기준일 컬럼 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `zero_null_rule` | `text` | N |  |  |  |  | 0/결측 처리 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `source_priority` | `text` | N |  |  |  |  | 출처 우선순위 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 12 | `transform_expression` | `text` | N |  |  |  |  | 변환식 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 13 | `implementation_status` | `text` | N |  |  |  |  | 구현 상태 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 14 | `deployment_status` | `text` | N |  |  |  |  | 배포 상태 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 15 | `pk_ordinal` | `integer` | Y |  |  |  |  | PK 내 순번 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 16 | `fk_target` | `text` | N |  |  |  |  | 참조 대상 schema.table.column | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 17 | `grain` | `text` | N |  |  |  |  | 테이블 그레인 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `meta.product_coverage`

- 종류: table
- 설명: 관계·문서·성과 확보/미확보 상태와 사유
- grain: 상품×스냅샷
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `holdings_status` | `text` | N |  |  |  |  | available/unavailable/not_applicable | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `holdings_reason` | `text` | N |  |  |  |  | 편입내역 상태 사유 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `document_status` | `text` | N |  |  |  |  | available/unavailable | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `document_reason` | `text` | N |  |  |  |  | 문서 상태 사유 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `performance_status` | `text` | N |  |  |  |  | available/unavailable | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `performance_reason` | `text` | N |  |  |  |  | 성과 상태 사유 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `as_of` | `date` | N |  |  |  | as_of | 커버리지 판정 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `source_document_id` | `text` | Y |  | relations.source_document.document_id |  |  | 상태 근거 문서 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.product_master`

- 종류: table
- 설명: 전 상품 공통 식별자와 유형·국내/해외·통화·활성 상태
- grain: 공통 상품 1개
- PK: `product_id`
- 인덱스: product_type, name, source_table,source_key
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 |  |  |  | 도메인 접두 공통 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `source_table` | `text` | N |  |  |  |  | 주최측 코드 테이블 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `source_key` | `text` | N |  |  |  |  | 원천 상품키 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `product_type` | `text` | N |  |  |  |  | BOND/ETF/ETN/FUND_PUB/FUND_PRIVATE | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `market_scope` | `text` | N |  |  |  |  | KR/GL | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `name` | `text` | N |  |  |  |  | 정식 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `short_name` | `text` | Y |  |  |  |  | 상품 약칭 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `currency` | `text` | Y |  |  |  |  | 원천 통화 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `is_active` | `boolean` | N |  |  |  |  | 명시 만기·상장종료 여부 기반 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `active_rule` | `text` | N |  |  |  |  | 활성 판정 근거 규칙 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `snapshot_date` | `date` | N |  |  |  | effective_as_of | 주최측 배포일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 12 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 도메인 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.bond_kr_product`

- 종류: table
- 설명: 최신 offer에서 접은 상품 속성과 보수적 구매가능 가정
- grain: 국내채권 pd_no 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `pd_no` | `text` | N |  |  |  |  | 채권 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `name` | `text` | N |  |  |  |  | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `issuer` | `text` | Y |  |  |  |  | 발행사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `credit_rating` | `text` | Y |  |  |  |  | 신용등급 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `currency` | `text` | Y |  |  |  |  | 통화 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `issue_date` | `date` | Y |  |  |  |  | 발행일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `maturity_date` | `date` | Y |  |  |  |  | 만기일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `risk_code` | `text` | Y |  |  |  |  | 위험등급 코드 원문 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 파생 |
| 10 | `risk_name` | `text` | Y |  |  |  |  | 위험등급명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `is_assumed_purchasable` | `boolean` | N |  |  |  |  | 최신 존재·명시 만기/종료만 제외 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 12 | `purchasable_rule` | `text` | N |  |  |  |  | BUYABLE_QUANTITY 미사용 판정 규칙 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 13 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 채권 정보 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.bond_kr_offer`

- 종류: table
- 설명: 채권 수익률·가격·판매 LOT; BUYABLE_QUANTITY는 저장 전용
- grain: 채권×시장×기준일×판매 LOT
- PK: `pd_no, exchange_market, info_base_dt, info_seq`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `pd_no` | `text` | N | 1 |  |  |  | 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `exchange_market` | `text` | N | 2 |  |  |  | 시장 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `info_base_dt` | `date` | N | 3 |  |  | info_base_dt | 정보 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `info_seq` | `integer` | N | 4 |  |  |  | 정보 순번 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `product_id` | `text` | N |  | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `applied_yield` | `double precision` | Y |  |  | percent |  | 민평수익률 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 7 | `after_tax_yield` | `double precision` | Y |  |  | percent |  | 개인 세후 운용수익률 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 8 | `buy_yield` | `double precision` | Y |  |  | percent |  | 매수수익률 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 9 | `sale_yield_base_dt` | `date` | Y |  |  |  | sale_yield_base_dt | 수익률 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `eval_price` | `double precision` | Y |  |  |  |  | 평가가격 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 11 | `trade_price` | `double precision` | Y |  |  |  |  | 거래가격 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 12 | `buyable_quantity` | `numeric(26,8)` | Y |  |  |  |  | 저장 전용 매수가능수량; 판매 판정 사용 금지 | 원본 0/NULL 보존; 판정·필터·정렬 사용 금지 | 주최측(1순위) | 파생 |

## `enriched.etf_kr`

- 종류: table
- 설명: pd_grp_no='ETF'만 명시 분리
- grain: 국내 ETF 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `pd_itm_no` | `text` | N |  |  |  |  | 원천 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `name` | `text` | N |  |  |  |  | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `ticker` | `text` | Y |  |  |  |  | 국내 티커 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `isin` | `text` | Y |  |  |  |  | ISIN | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `manager` | `text` | Y |  |  |  |  | 운용사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `base_index` | `text` | Y |  |  |  |  | 기초지수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `currency` | `text` | Y |  |  |  |  | 통화 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `listing_date` | `date` | Y |  |  |  |  | 상장일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `delisting_date` | `date` | Y |  |  |  |  | 상장종료일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.etf_gl`

- 종류: table
- 설명: pd_grp_no='ETF'만 명시 분리
- grain: 해외 ETF 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `pd_itm_no` | `text` | N |  |  |  |  | 원천 RIC 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `name` | `text` | N |  |  |  |  | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `ticker` | `text` | Y |  |  |  |  | 티커 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `isin` | `text` | Y |  |  |  |  | ISIN(비유일 보조 식별자) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `manager` | `text` | Y |  |  |  |  | 운용사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `base_index` | `text` | Y |  |  |  |  | 기초지수; sentinel은 NULL | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `currency` | `text` | Y |  |  |  |  | 거래 통화 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `inception_date` | `date` | Y |  |  |  | pd_lstg_dt | 설정일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | yyyymmdd(pd_lstg_dt); 상장일로 해석 금지 |
| 10 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.etn_kr`

- 종류: table
- 설명: 국내 ETF 원천의 pd_grp_no='ETN' 분리
- grain: 국내 ETN 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `pd_itm_no` | `text` | N |  |  |  |  | 원천 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `name` | `text` | N |  |  |  |  | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `ticker` | `text` | Y |  |  |  |  | 국내 티커 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `isin` | `text` | Y |  |  |  |  | ISIN | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `issuer` | `text` | Y |  |  |  |  | 발행사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `currency` | `text` | Y |  |  |  |  | 통화 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `listing_date` | `date` | Y |  |  |  |  | 상장일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `delisting_date` | `date` | Y |  |  |  |  | 상장종료일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.etn_gl`

- 종류: table
- 설명: 해외 ETF 원천의 pd_grp_no='ETN' 분리
- grain: 해외 ETN 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `pd_itm_no` | `text` | N |  |  |  |  | 원천 RIC 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `name` | `text` | N |  |  |  |  | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `ticker` | `text` | Y |  |  |  |  | 티커 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `isin` | `text` | Y |  |  |  |  | ISIN | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `issuer` | `text` | Y |  |  |  |  | 발행사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `currency` | `text` | Y |  |  |  |  | 거래 통화 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `inception_date` | `date` | Y |  |  |  | pd_lstg_dt | 설정일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | yyyymmdd(pd_lstg_dt); 상장일로 해석 금지 |
| 9 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.fund`

- 종류: table
- 설명: 공모·사모 전체 보존; fund_pub 뷰에서 공모만 노출
- grain: 펀드 itm_no 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `itm_no` | `text` | N |  |  |  |  | 펀드 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `name` | `text` | N |  |  |  |  | 펀드명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `short_name` | `text` | Y |  |  |  |  | 펀드 약칭 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `offering_type` | `text` | N |  |  |  |  | 공모/사모 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `manager_org_code` | `text` | Y |  |  |  |  | 운용사 기관코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `benchmark` | `text` | Y |  |  |  |  | 벤치마크 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `currency` | `text` | Y |  |  |  |  | 통화 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 성과 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.product_metric`

- 종류: table
- 설명: AUM·수익률·보수 등 공통 지표와 값 미확보 상태
- grain: 상품×지표×기준일×출처×방법
- PK: `metric_id`
- 인덱스: product_id,metric_code, metric_code,value DESC WHERE is_available
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `metric_id` | `text` | N | 1 |  |  |  | 결정적 지표 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `product_id` | `text` | N |  | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `metric_code` | `text` | N |  |  |  |  | AUM/RETURN_1Y/EXPENSE_RATIO 등 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `value` | `numeric` | Y |  |  |  |  | 측정값; 0도 보존 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 5 | `unit` | `text` | N |  |  |  |  | KRW/USD/percent 등 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `as_of` | `date` | Y |  |  |  | as_of | 측정 기준일; 없으면 지표 미확보 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `source` | `text` | N |  |  |  |  | 주최측 코드 또는 검증된 외부 원천 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `source_column` | `text` | N |  |  |  |  | 직접 출처 컬럼/필드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `method` | `text` | N |  |  |  |  | raw/calculated_total_return 등 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `is_available` | `boolean` | N |  |  |  |  | 랭킹·비교 사용 가능 여부 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `unavailable_reason` | `text` | Y |  |  |  |  | NULL/0/권한 미확보 등 사유 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 12 | `source_priority` | `smallint` | N |  |  |  |  | 1=주최측, 2=외부 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.security_master`

- 종류: table
- 설명: 편입증권·기업의 통합 식별자
- grain: 증권 1개
- PK: `security_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `security_id` | `text` | N | 1 |  |  |  | 결정적 증권 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `display_name` | `text` | N |  |  |  |  | 표시명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `security_type` | `text` | N |  |  |  |  | equity/bond/company/unknown | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `issuer_name` | `text` | Y |  |  |  |  | 발행사명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `country_code` | `text` | Y |  |  |  |  | 국가 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `enriched.security_identifier`

- 종류: table
- 설명: ISIN·국내 티커·RIC·Bloomberg 표기 통합
- grain: 증권×식별자 유형×값
- PK: `security_id, id_type, id_value`
- 인덱스: id_type,id_value
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `security_id` | `text` | N | 1 | enriched.security_master.security_id |  |  | 증권 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `id_type` | `text` | N | 2 |  |  |  | ISIN/KR_TICKER/RIC/BLOOMBERG | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `id_value` | `text` | N | 3 |  |  |  | 식별자 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `is_primary` | `boolean` | N |  |  |  |  | 해당 유형의 대표 식별자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `relations.source_document`

- 종류: table
- 설명: 문서명·발행기관·발행일·URL·원천 해시
- grain: 외부 근거 문서 1개
- PK: `document_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `document_id` | `text` | N | 1 |  |  |  | 결정적 문서 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `title` | `text` | N |  |  |  |  | 문서명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 3 | `publisher` | `text` | N |  |  |  |  | 발행기관 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 4 | `published_at` | `date` | N |  |  |  | published_at | 발행일(상한 검증) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 5 | `url` | `text` | N |  |  |  |  | 공식 원문 URL | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 6 | `source_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 7 | `source_type` | `text` | N |  |  |  |  | DART/manager/policy/LSEG | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 8 | `as_of` | `date` | Y |  |  |  | as_of | 문서가 증명하는 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 9 | `ingested_at` | `timestamptz` | N |  |  |  |  | 수집 시각 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |

## `relations.product_holding`

- 종류: table
- 설명: ETF·펀드 공통 편입관계; 미확보는 coverage로 분리
- grain: 상품×편입증권×기준일×문서
- PK: `holding_id`
- 인덱스: product_id,as_of, security_id,as_of
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `holding_id` | `text` | N | 1 |  |  |  | 결정적 관계 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `product_id` | `text` | N |  | enriched.product_master.product_id |  |  | 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `security_id` | `text` | N |  | enriched.security_master.security_id |  |  | 편입증권 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `weight` | `numeric` | Y |  |  | percent |  | 편입비중 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 5 | `unit` | `text` | N |  |  |  |  | 비중 단위 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `as_of` | `date` | N |  |  |  | as_of | 편입 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 7 | `source_document_id` | `text` | N |  | relations.source_document.document_id |  |  | 직접 근거 문서 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 8 | `source` | `text` | N |  |  |  |  | 운용사/DART 원천 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |

## `relations.product_classification`

- 종류: table
- 설명: 상품↔테마·섹터·지역 관계
- grain: 상품×분류 유형×값×기준일
- PK: `classification_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `classification_id` | `text` | N | 1 |  |  |  | 결정적 관계 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `product_id` | `text` | N |  | enriched.product_master.product_id |  |  | 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `classification_type` | `text` | N |  |  |  |  | theme/sector/region | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `classification_value` | `text` | N |  |  |  |  | 원천 분류값 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `as_of` | `date` | N |  |  |  | as_of | 분류 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `source_document_id` | `text` | Y |  | relations.source_document.document_id |  |  | 직접 근거 문서 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `source` | `text` | N |  |  |  |  | 원천 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `relations.company_subsidiary`

- 종류: table
- 설명: 기업↔자회사 n-ary 관계와 지분율
- grain: 기업×자회사×기준일×문서
- PK: `relation_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `relation_id` | `text` | N | 1 |  |  |  | 결정적 관계 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `parent_security_id` | `text` | N |  | enriched.security_master.security_id |  |  | 모회사 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `child_security_id` | `text` | N |  | enriched.security_master.security_id |  |  | 자회사 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `ownership_pct` | `numeric` | Y |  |  | percent |  | 지분율 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 5 | `as_of` | `date` | N |  |  |  | as_of | 공시 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 6 | `source_document_id` | `text` | N |  | relations.source_document.document_id |  |  | DART 근거 문서 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 7 | `source` | `text` | N |  |  |  |  | 원천 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |

## `relations.product_document`

- 종류: table
- 설명: 상품과 투자설명서·보고서·구성내역 연결
- grain: 상품×문서×관계유형
- PK: `product_id, document_id, relation_type`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `document_id` | `text` | N | 2 | relations.source_document.document_id |  |  | 문서 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `relation_type` | `text` | N | 3 |  |  |  | prospectus/report/holdings | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `vec.bond_schema_terms`

- 종류: table
- 설명: common+bond TBox 주석 130행 CLOVA bge-m3 임베딩
- grain: 채권 TBox grounding term 1개
- PK: `term_uri`
- 인덱스: embedding vector_cosine_ops (HNSW), content_hash,embedding_model
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `term_uri` | `text` | N | 1 |  |  |  | TBox URI | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `label` | `text` | N |  |  |  |  | 라벨 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `comment` | `text` | N |  |  |  |  | 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `alt_labels` | `text[]` | N |  |  |  |  | 대체 표기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `content` | `text` | N |  |  |  |  | 임베딩 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `content_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `embedding_model` | `text` | N |  |  |  |  | bge-m3 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `embedding_dim` | `smallint` | N |  |  |  |  | 1024 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `embedding` | `vector(1024)` | N |  |  |  |  | CLOVA 임베딩 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `vec.schema_terms_all`

- 종류: table
- 설명: 5개 TBox 주석 189행 CLOVA bge-m3 임베딩
- grain: 전체 TBox grounding term 1개
- PK: `term_uri`
- 인덱스: embedding vector_cosine_ops (HNSW), content_hash,embedding_model
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `term_uri` | `text` | N | 1 |  |  |  | TBox URI | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `label` | `text` | N |  |  |  |  | 라벨 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `comment` | `text` | N |  |  |  |  | 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `alt_labels` | `text[]` | N |  |  |  |  | 대체 표기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `content` | `text` | N |  |  |  |  | 임베딩 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `content_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `embedding_model` | `text` | N |  |  |  |  | bge-m3 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `embedding_dim` | `smallint` | N |  |  |  |  | 1024 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `embedding` | `vector(1024)` | N |  |  |  |  | CLOVA 임베딩 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## `vec.document_chunk`

- 종류: table
- 설명: 문서·상품·페이지·발행일·인용 위치가 있는 콘텐츠 임베딩
- grain: 문서 청크 1개
- PK: `chunk_id`
- 인덱스: embedding vector_cosine_ops (HNSW), document_id, product_id
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `chunk_id` | `text` | N | 1 |  |  |  | 결정적 청크 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `document_id` | `text` | N |  | relations.source_document.document_id |  |  | 근거 문서 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `product_id` | `text` | Y |  | enriched.product_master.product_id |  |  | 연결 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `page_number` | `integer` | Y |  |  |  |  | 원문 페이지 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `citation_text` | `text` | N |  |  |  |  | 인용 위치/문장 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `chunk_text` | `text` | N |  |  |  |  | 임베딩 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `published_at` | `date` | N |  |  |  | published_at | 문서 발행일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 8 | `source_url` | `text` | N |  |  |  |  | 원문 URL | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 9 | `content_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `embedding_model` | `text` | N |  |  |  |  | bge-m3 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `embedding_dim` | `smallint` | N |  |  |  |  | 1024 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 12 | `embedding` | `vector(1024)` | N |  |  |  |  | CLOVA 임베딩 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## 호환 뷰와 검색 뷰

| 이름 | 종류 | 원천/정의 | 목적/필터 |
|---|---|---|---|
| `raw.prbd01n001` | view | `raw.bond_kr_master` | 코드명 호환 |
| `raw.pref01n001` | view | `raw.etf_kr_master` | 코드명 호환 |
| `raw.pref02n001` | view | `raw.etf_gl_master` | 코드명 호환 |
| `raw.prfd01n001` | view | `raw.fund_pub_master` | 코드명 호환 |
| `enriched.fund_pub` | view | `enriched.fund` | offering_type='공모' |
| `core.bond_kr` | view | `enriched.bond_kr_product` | Agent 호환 |
| `core.etf_kr` | view | `enriched.etf_kr` | Agent 호환 |
| `core.etf_gl` | view | `enriched.etf_gl` | Agent 호환 |
| `core.fund_pub` | view | `enriched.fund_pub` | Agent 호환 |
| `core.etn` | view | `enriched.etn_kr UNION ALL enriched.etn_gl` | Agent 호환 |
| `enriched.product_search` | materialized view | `product_master+product_metric+product_coverage` |  |
