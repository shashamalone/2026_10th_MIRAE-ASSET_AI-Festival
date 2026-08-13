# 데이터 인벤토리

이 파일은 `EDA/build_data_inventory.py`가 생성한다. **직접 편집하지 말 것.**
데이터 구조 변경 시 재실행 후 커밋하면 `git diff`가 그대로 변경 이력이 된다.
(생성 시각을 넣지 않는 이유: 매번 바뀌면 diff가 노이즈로 덮여 변경 추적이 불가능해진다.)

## 계층별 요약

| 파일 | 계층 | 행수 | 컬럼수 | 생성 스크립트 |
|---|---|---|---|---|
| `data/csv/PRBD01N001_bond_kr_axis_sample_20260711.csv` | 원본 | 100 | 20 | — |
| `data/csv/PRBD01N001_bond_kr_master_20260711.csv` | 원본 | 42,394 | 40 | — |
| `data/csv/PRBD01N001_bond_kr_schema_20260711.csv` | 원본 | 40 | 5 | — |
| `data/csv/PREF01N001_etf_kr_axis_sample_20260711.csv` | 원본 | 100 | 13 | — |
| `data/csv/PREF01N001_etf_kr_master_20260711.csv` | 원본 | 1,734 | 73 | — |
| `data/csv/PREF01N001_etf_kr_schema_20260711.csv` | 원본 | 73 | 5 | — |
| `data/csv/PREF02N001_etf_gl_axis_sample_20260711.csv` | 원본 | 100 | 49 | — |
| `data/csv/PREF02N001_etf_gl_master_20260711.csv` | 원본 | 5,646 | 49 | — |
| `data/csv/PREF02N001_etf_gl_schema_20260711.csv` | 원본 | 49 | 5 | — |
| `data/csv/PRFD01N001_fund_pub_axis_sample_20260711.csv` | 원본 | 100 | 11 | — |
| `data/csv/PRFD01N001_fund_pub_master_20260711.csv` | 원본 | 95,619 | 45 | — |
| `data/csv/PRFD01N001_fund_pub_schema_20260711.csv` | 원본 | 45 | 5 | — |
| `data/enriched/bond_kr_enriched.csv` | 파생 | 42,394 | 12 | `EDA/build_bond_enrichment.py` |
| `data/enriched/etf_kr_enriched.csv` | 파생 | 1,734 | 12 | `EDA/build_etf_enrichment.py` |
| `data/enriched/fund_pub_dedup.csv` | 파생 | 11,138 | 45 | `EDA/build_fund_dedup.py` |
| `data/relations/etf_holding.csv` | 관계 | 30,737 | 7 | `EDA/build_etf_holding.py` |
| `data/relations/etf_theme.csv` | 관계 | 5,646 | 4 | `EDA/build_etf_enrichment.py` |

## 파일별 컬럼

결측률은 빈 문자열 기준. 값 예시는 문서 비대화를 막기 위해 싣지 않는다.

### `data/csv/PRBD01N001_bond_kr_axis_sample_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `source_table` | 0.0% | 1 |
| `pd_no` | 0.0% | 100 |
| `pd_nm` | 0.0% | 100 |
| `pd_abrv_nm` | 1.0% | 100 |
| `isu_bal_amt` | 0.0% | 71 |
| `std_pd_mcls_nm` | 0.0% | 6 |
| `std_pd_scls_nm` | 4.0% | 12 |
| `bd_knd` | 2.0% | 16 |
| `pd_ctry_cd` | 0.0% | 2 |
| `pd_pbcm` | 1.0% | 40 |
| `axis_issuerType` | 0.0% | 4 |
| `axis_maturityClass` | 0.0% | 3 |
| `axis_couponType` | 0.0% | 4 |
| `axis_creditRating` | 0.0% | 4 |
| `axis_collateralType` | 0.0% | 4 |
| `axis_currency` | 0.0% | 1 |
| `axis_issuanceMarket` | 0.0% | 1 |
| `axis_issuerCategory` | 0.0% | 6 |
| `listingCountry` | 0.0% | 1 |
| `issuerCountry` | 0.0% | 1 |

### `data/csv/PRBD01N001_bond_kr_master_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `PD_NO` | 0.0% | 42,394 |
| `PD_EXG_MKT` | 0.0% | 2 |
| `PD_NM` | 0.0% | 42,284 |
| `PD_ABRV_NM` | 0.9% | 42,011 |
| `PD_ENG_NM` | 0.8% | 42,046 |
| `PD_ABRV_ENG_NM` | 0.9% | 41,996 |
| `PD_CTRY_CD` | 0.0% | 2 |
| `PD_PBCM` | 2.2% | 8,019 |
| `STD_PD_MCLS_NM` | 0.0% | 6 |
| `STD_PD_SCLS_NM` | 0.0% | 17 |
| `BD_KND` | 2.2% | 40 |
| `CURR_CD` | 0.0% | 5 |
| `ISU_BAL_AMT` | 0.0% | 4,452 |
| `ISU_DT` | 0.0% | 3,147 |
| `MAT_DT` | 0.0% | 5,352 |
| `SRFC_IRT` | 0.0% | 5,677 |
| `PD_EVCO_CRD_GRD` | 41.1% | 101 |
| `PD_RISK_GCD` | 0.0% | 7 |
| `PD_STD_INFO_UPDATE` | 24.9% | 911 |
| `BUY_YIELD` | 97.9% | 540 |
| `CORP_PRETAX_YIELD` | 97.9% | 830 |
| `CORP_AFTER_TAX_YIELD` | 97.9% | 830 |
| `AFTER_TAX_YIELD` | 97.9% | 829 |
| `PREF_TAX_YIELD` | 97.9% | 837 |
| `AVG_ANNUAL_TAX_YIELD` | 97.9% | 2 |
| `DEPO_EQUIV_YIELD_154` | 97.9% | 829 |
| `BUYABLE_QUANTITY` | 97.9% | 296 |
| `REMAINING_DAYS` | 25.1% | 3,943 |
| `DUR` | 31.6% | 14,851 |
| `COV` | 31.6% | 16,188 |
| `NDY_DUR` | 31.6% | 14,607 |
| `NDY_COV` | 31.6% | 15,941 |
| `EVAL_PRICE` | 24.9% | 20,313 |
| `APPLIED_YIELD` | 24.9% | 3,852 |
| `DIRTY` | 31.6% | 19,665 |
| `NDY_EVAL_PRICE` | 31.6% | 16,427 |
| `NDY_APPLIED_YIELD` | 31.6% | 2,945 |
| `NDY_DIRTY` | 31.6% | 16,381 |
| `CRD_GRD` | 41.6% | 21 |
| `CRD_GRD_DT` | 35.0% | 2,319 |

### `data/csv/PRBD01N001_bond_kr_schema_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `column` | 0.0% | 40 |
| `pk_fk` | 100.0% | 1 |
| `dtype` | 0.0% | 3 |
| `name_ko` | 100.0% | 1 |
| `example` | 100.0% | 1 |

### `data/csv/PREF01N001_etf_kr_axis_sample_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `pd_itm_no` | 0.0% | 100 |
| `pd_itm_no_ma` | 0.0% | 100 |
| `pd_nm` | 0.0% | 100 |
| `pd_abrv_nm` | 0.0% | 100 |
| `pd_net_tamt` | 3.0% | 98 |
| `legacy_leaf` | 0.0% | 23 |
| `axis_assetType` | 0.0% | 7 |
| `axis_region` | 0.0% | 2 |
| `axis_strategy` | 0.0% | 2 |
| `axis_replicationMethod` | 0.0% | 2 |
| `axis_leverageType` | 0.0% | 4 |
| `axis_underlyingScope` | 0.0% | 3 |
| `axis_distributionType` | 0.0% | 2 |

### `data/csv/PREF01N001_etf_kr_master_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `cu_base_index` | 96.7% | 20 |
| `cu_charge_etc_rt` | 10.4% | 2 |
| `cu_charge_rt` | 87.5% | 18 |
| `cu_fund_mgmt_co` | 0.0% | 97 |
| `cu_lev_fector` | 10.6% | 10 |
| `cu_strtegy` | 8.9% | 5 |
| `cu_upt_dt` | 10.6% | 12 |
| `du_bpr` | 0.3% | 1,404 |
| `du_chas_errt` | 10.6% | 2 |
| `du_clpr` | 0.3% | 1,416 |
| `du_diff_rt` | 12.5% | 2 |
| `du_er_1d` | 9.9% | 818 |
| `du_er_1m` | 11.2% | 1,154 |
| `du_er_1y` | 20.6% | 1,220 |
| `du_er_3m` | 13.2% | 1,251 |
| `du_er_6m` | 14.9% | 1,276 |
| `du_er_ytd` | 14.8% | 1,282 |
| `du_hpr` | 0.3% | 1,388 |
| `du_last_aum` | 16.2% | 1,044 |
| `du_last_nav` | 10.6% | 1,538 |
| `du_lpr` | 0.3% | 1,389 |
| `du_nav_rnf_amt` | 12.5% | 1,503 |
| `du_nav_yday` | 12.5% | 1,505 |
| `du_upt_dt` | 12.5% | 2 |
| `du_val_1d` | 0.3% | 1,476 |
| `du_val_1m` | 2.3% | 1,492 |
| `du_val_5d` | 0.3% | 1,498 |
| `du_vol_1d` | 0.3% | 1,366 |
| `du_vol_avg_1m` | 2.2% | 1,490 |
| `du_vol_avg_5d` | 0.3% | 1,470 |
| `nru_mkt_diff_rt` | 100.0% | 1 |
| `nru_mkt_inav` | 100.0% | 1 |
| `pd_abrv_nm` | 0.0% | 1,727 |
| `pd_circ_net_tamt` | 10.6% | 659 |
| `pd_circ_stk_cnt` | 10.6% | 623 |
| `pd_curr_cd` | 0.1% | 3 |
| `pd_curr_nm` | 0.1% | 3 |
| `pd_divd_amt_pshr` | 10.6% | 2 |
| `pd_dvid_cycl` | 100.0% | 1 |
| `pd_dvid_yield` | 10.6% | 2 |
| `pd_exg_mkt_cd` | 0.1% | 2 |
| `pd_exg_mkt_nm` | 0.1% | 2 |
| `pd_grp_no` | 0.0% | 2 |
| `pd_itm_no` | 0.0% | 1,734 |
| `pd_itm_no_ma` | 0.0% | 1,734 |
| `pd_lst_price` | 0.0% | 1 |
| `pd_lst_stk_cnt` | 0.0% | 678 |
| `pd_lste_dt` | 0.1% | 81 |
| `pd_lstg_dt` | 0.1% | 602 |
| `pd_mkt_id` | 0.1% | 2 |
| `pd_mkt_nm` | 0.1% | 2 |
| `pd_nav_pshr` | 10.6% | 1,538 |
| `pd_net_ast_pshr` | 10.6% | 2 |
| `pd_net_prft_pshr` | 10.6% | 2 |
| `pd_net_rt_ast_pshr` | 10.6% | 2 |
| `pd_net_tamt` | 10.6% | 1,549 |
| `pd_nm` | 0.0% | 1,734 |
| `pd_pen_risk_nm` | 0.0% | 3 |
| `pd_pen_tr_yn` | 0.0% | 2 |
| `pd_risk_cd` | 0.0% | 6 |
| `pd_risk_nm` | 0.0% | 6 |
| `pd_sale_yn` | 0.0% | 2 |
| `pd_sect_cd` | 10.6% | 6 |
| `pd_sect_nm` | 100.0% | 1 |
| `pd_spac_yn` | 10.6% | 2 |
| `pd_stk_cnt` | 10.6% | 647 |
| `pd_tr_yn` | 0.1% | 3 |
| `ru_mkt_price` | 100.0% | 1 |
| `ru_mkt_volume` | 100.0% | 1 |
| `wu_core_yn` | 0.0% | 2 |
| `wu_inv_ast_type` | 0.0% | 8 |
| `wu_inv_rgn` | 0.0% | 11 |
| `wu_upt_dt` | 0.3% | 2 |

### `data/csv/PREF01N001_etf_kr_schema_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `column` | 0.0% | 73 |
| `pk_fk` | 95.9% | 2 |
| `dtype` | 0.0% | 3 |
| `name_ko` | 0.0% | 72 |
| `example` | 17.8% | 48 |

### `data/csv/PREF02N001_etf_gl_axis_sample_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `cu_base_index` | 3.0% | 84 |
| `cu_charge_rt` | 0.0% | 26 |
| `cu_etn_yn` | 100.0% | 1 |
| `cu_fund_mgmt_co` | 3.0% | 18 |
| `cu_index_repl_mthd` | 14.0% | 4 |
| `cu_index_tracking_yn` | 14.0% | 2 |
| `cu_inverse_short_yn` | 100.0% | 1 |
| `cu_lev_fector` | 100.0% | 1 |
| `cu_strtegy` | 3.0% | 97 |
| `cu_upt_dt` | 0.0% | 1 |
| `du_base_dt_match_yn` | 4.0% | 2 |
| `du_bpr` | 4.0% | 96 |
| `du_clpr` | 4.0% | 96 |
| `du_clpr_base_dt` | 4.0% | 2 |
| `du_clpr_src` | 4.0% | 2 |
| `du_diff_rt` | 100.0% | 1 |
| `du_er_1d` | 5.0% | 2 |
| `du_hpr` | 4.0% | 96 |
| `du_last_aum` | 0.0% | 98 |
| `du_last_nav` | 100.0% | 1 |
| `du_lpr` | 4.0% | 96 |
| `du_nav_base_dt` | 0.0% | 1 |
| `du_opr` | 4.0% | 96 |
| `du_upt_dt` | 0.0% | 3 |
| `du_val_1d` | 4.0% | 96 |
| `du_vol_1d` | 4.0% | 96 |
| `pd_abrv_nm` | 0.0% | 100 |
| `pd_curr_cd` | 3.0% | 3 |
| `pd_exg_mkt_cd` | 0.0% | 3 |
| `pd_grp_no` | 0.0% | 1 |
| `pd_isin_cd` | 3.0% | 97 |
| `pd_itm_no` | 0.0% | 100 |
| `pd_itm_no_ma` | 0.0% | 100 |
| `pd_lipper_id` | 3.0% | 97 |
| `pd_lstg_dt` | 0.0% | 69 |
| `pd_lst_price` | 4.0% | 2 |
| `pd_lst_stk_cnt` | 0.0% | 97 |
| `pd_mkt_id` | 0.0% | 1 |
| `pd_nm` | 0.0% | 100 |
| `pd_sale_yn` | 4.0% | 2 |
| `pd_trd_ccy` | 0.0% | 1 |
| `pd_tr_yn` | 4.0% | 2 |
| `pd_us_cik` | 4.0% | 35 |
| `ru_mkt_price` | 4.0% | 96 |
| `ru_mkt_volume` | 4.0% | 96 |
| `wu_core_yn` | 100.0% | 1 |
| `wu_inv_ast_type` | 3.0% | 7 |
| `wu_inv_rgn` | 3.0% | 7 |
| `wu_upt_dt` | 0.0% | 1 |

### `data/csv/PREF02N001_etf_gl_master_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `cu_base_index` | 0.1% | 1,734 |
| `cu_charge_rt` | 0.0% | 127 |
| `cu_etn_yn` | 99.0% | 2 |
| `cu_fund_mgmt_co` | 0.1% | 373 |
| `cu_index_repl_mthd` | 58.2% | 5 |
| `cu_index_tracking_yn` | 58.2% | 2 |
| `cu_inverse_short_yn` | 97.0% | 2 |
| `cu_lev_fector` | 100.0% | 1 |
| `cu_strtegy` | 0.1% | 5,567 |
| `cu_upt_dt` | 0.0% | 1 |
| `du_base_dt_match_yn` | 0.2% | 2 |
| `du_bpr` | 0.2% | 5,182 |
| `du_clpr` | 0.2% | 5,106 |
| `du_clpr_base_dt` | 0.2% | 87 |
| `du_clpr_src` | 0.2% | 2 |
| `du_diff_rt` | 99.9% | 4 |
| `du_er_1d` | 4.6% | 2 |
| `du_hpr` | 0.2% | 4,622 |
| `du_last_aum` | 3.3% | 4,744 |
| `du_last_nav` | 87.9% | 528 |
| `du_lpr` | 0.2% | 4,736 |
| `du_nav_base_dt` | 0.0% | 1 |
| `du_opr` | 0.2% | 4,232 |
| `du_upt_dt` | 0.0% | 88 |
| `du_val_1d` | 0.2% | 5,353 |
| `du_vol_1d` | 0.2% | 4,853 |
| `pd_abrv_nm` | 0.0% | 5,641 |
| `pd_curr_cd` | 0.1% | 3 |
| `pd_exg_mkt_cd` | 0.0% | 5 |
| `pd_grp_no` | 0.0% | 2 |
| `pd_isin_cd` | 0.2% | 5,588 |
| `pd_itm_no` | 0.0% | 5,646 |
| `pd_itm_no_ma` | 0.0% | 5,646 |
| `pd_lipper_id` | 0.1% | 5,589 |
| `pd_lstg_dt` | 0.0% | 1,956 |
| `pd_lst_price` | 0.2% | 3 |
| `pd_lst_stk_cnt` | 0.0% | 3,105 |
| `pd_mkt_id` | 0.0% | 1 |
| `pd_nm` | 0.0% | 5,630 |
| `pd_sale_yn` | 0.2% | 2 |
| `pd_trd_ccy` | 0.0% | 1 |
| `pd_tr_yn` | 0.2% | 2 |
| `pd_us_cik` | 0.2% | 375 |
| `ru_mkt_price` | 0.2% | 5,102 |
| `ru_mkt_volume` | 0.2% | 4,853 |
| `wu_core_yn` | 98.2% | 2 |
| `wu_inv_ast_type` | 0.1% | 7 |
| `wu_inv_rgn` | 0.1% | 60 |
| `wu_upt_dt` | 0.0% | 1 |

### `data/csv/PREF02N001_etf_gl_schema_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `column` | 0.0% | 49 |
| `pk_fk` | 98.0% | 2 |
| `dtype` | 0.0% | 3 |
| `name_ko` | 100.0% | 1 |
| `example` | 100.0% | 1 |

### `data/csv/PRFD01N001_fund_pub_axis_sample_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `itm_no` | 0.0% | 100 |
| `itm_nm` | 0.0% | 100 |
| `itm_abrv_nm` | 0.0% | 100 |
| `fd_nast_suma` | 2.0% | 36 |
| `or_attr_desc` | 4.0% | 12 |
| `axis_fundType` | 0.0% | 5 |
| `axis_redemptionType` | 0.0% | 2 |
| `axis_issuanceType` | 0.0% | 2 |
| `axis_listingType` | 0.0% | 2 |
| `axis_classDifferentiation` | 0.0% | 2 |
| `axis_investorEligibility` | 0.0% | 2 |

### `data/csv/PRFD01N001_fund_pub_master_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `bmrk_eng_nm` | 0.0% | 388 |
| `bmrk_nm` | 0.0% | 391 |
| `curr_cd` | 0.0% | 3 |
| `exchdg_yn` | 31.1% | 4 |
| `fd_estb_ctry_cd` | 0.1% | 3 |
| `fd_ivst_rgn_desc` | 0.1% | 8 |
| `fd_mm18_ern_r` | 33.9% | 4,910 |
| `fd_mm1_ern_r` | 27.6% | 1,551 |
| `fd_mm3_ern_r` | 28.3% | 3,506 |
| `fd_mm6_ern_r` | 29.8% | 4,178 |
| `fd_nast_suma` | 13.1% | 2,683 |
| `fd_set_pcd` | 0.0% | 4 |
| `fd_wk1_ern_r` | 27.4% | 1,208 |
| `fd_yr1_ern_r` | 32.6% | 4,827 |
| `fd_yr2_ern_r` | 39.2% | 4,778 |
| `fd_yr3_ern_r` | 41.6% | 4,926 |
| `fd_yr5_ern_r` | 46.8% | 4,700 |
| `frc_bpr_itm_yn` | 0.0% | 3 |
| `fss_itm_no` | 0.0% | 8,087 |
| `hdge_fd_yn` | 0.1% | 2 |
| `int_dvd_desc` | 0.1% | 3 |
| `itm_abrv_nm` | 0.0% | 11,119 |
| `itm_eabrv_nm` | 99.8% | 15 |
| `itm_eng_nm` | 0.0% | 10,971 |
| `itm_nm` | 0.0% | 11,139 |
| `itm_no` | 0.0% | 11,139 |
| `kofia_fd_ccd` | 0.1% | 4,783 |
| `ksd_itm_no` | 0.3% | 11,093 |
| `mtco_itm_no` | 0.0% | 4,661 |
| `ofsfd_yn` | 0.0% | 2 |
| `or_attr_desc` | 0.1% | 12 |
| `or_co_xtn_itt_cd` | 0.1% | 68 |
| `ovrs_fd_desc` | 0.1% | 4 |
| `pers_corp_desc` | 0.1% | 4 |
| `pfiv_sale_cntl_tcd` | 0.1% | 4 |
| `prfd_attr_cd` | 0.0% | 228 |
| `prvo_fd_desc` | 0.1% | 3 |
| `prvo_pbff_desc` | 0.1% | 3 |
| `rptt_ksd_itm_no` | 0.1% | 2,629 |
| `sale_yn` | 0.0% | 3 |
| `std_itm_no` | 0.1% | 11,128 |
| `thco_sale_yn` | 4.2% | 3 |
| `trusc_xtn_itt_cd` | 0.1% | 19 |
| `zrin_fd_ivst_risk_gcd` | 19.3% | 8 |
| `zrin_fd_ivst_risk_grd_nm` | 19.3% | 10 |

### `data/csv/PRFD01N001_fund_pub_schema_20260711.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `column` | 0.0% | 45 |
| `pk_fk` | 93.3% | 2 |
| `dtype` | 0.0% | 2 |
| `name_ko` | 0.0% | 45 |
| `example` | 0.0% | 39 |

### `data/enriched/bond_kr_enriched.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `PD_NO` | 0.0% | 42,394 |
| `evco_grd_count` | 0.0% | 4 |
| `evco_grd_agree` | 46.7% | 3 |
| `crd_grd_norm` | 37.8% | 20 |
| `crd_grd_rank` | 37.8% | 20 |
| `crd_grd_source` | 37.8% | 3 |
| `remaining_days` | 0.8% | 5,351 |
| `maturity_bucket` | 0.0% | 7 |
| `is_krw` | 0.0% | 2 |
| `has_sale_info` | 0.0% | 2 |
| `is_sellable` | 0.0% | 2 |
| `source` | 0.0% | 1 |

### `data/enriched/etf_kr_enriched.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `pd_itm_no` | 0.0% | 1,734 |
| `pd_itm_no_ma` | 0.0% | 1,734 |
| `pd_grp_no` | 0.0% | 2 |
| `pd_abrv_nm` | 0.0% | 1,727 |
| `lseg_key` | 0.0% | 1,734 |
| `ter` | 36.6% | 105 |
| `replication` | 36.6% | 5 |
| `base_market` | 36.6% | 4 |
| `base_asset` | 36.6% | 8 |
| `hedge_type` | 36.6% | 4 |
| `charge_rt_final` | 36.6% | 106 |
| `charge_rt_source` | 36.6% | 3 |

### `data/enriched/fund_pub_dedup.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `bmrk_eng_nm` | 0.0% | 387 |
| `bmrk_nm` | 0.0% | 390 |
| `curr_cd` | 0.0% | 2 |
| `exchdg_yn` | 37.9% | 3 |
| `fd_estb_ctry_cd` | 0.1% | 3 |
| `fd_ivst_rgn_desc` | 0.1% | 8 |
| `fd_mm18_ern_r` | 38.2% | 4,910 |
| `fd_mm1_ern_r` | 32.0% | 1,551 |
| `fd_mm3_ern_r` | 32.7% | 3,506 |
| `fd_mm6_ern_r` | 34.1% | 4,178 |
| `fd_nast_suma` | 16.6% | 2,683 |
| `fd_set_pcd` | 0.0% | 3 |
| `fd_wk1_ern_r` | 31.8% | 1,208 |
| `fd_yr1_ern_r` | 37.0% | 4,827 |
| `fd_yr2_ern_r` | 42.9% | 4,778 |
| `fd_yr3_ern_r` | 45.2% | 4,926 |
| `fd_yr5_ern_r` | 49.9% | 4,700 |
| `frc_bpr_itm_yn` | 0.0% | 2 |
| `fss_itm_no` | 0.0% | 8,086 |
| `hdge_fd_yn` | 0.1% | 2 |
| `int_dvd_desc` | 0.1% | 3 |
| `itm_abrv_nm` | 0.0% | 11,118 |
| `itm_eabrv_nm` | 99.8% | 14 |
| `itm_eng_nm` | 0.0% | 10,970 |
| `itm_nm` | 0.0% | 11,138 |
| `itm_no` | 0.0% | 11,138 |
| `kofia_fd_ccd` | 0.1% | 4,783 |
| `ksd_itm_no` | 0.4% | 11,093 |
| `mtco_itm_no` | 0.0% | 4,660 |
| `ofsfd_yn` | 0.0% | 1 |
| `or_attr_desc` | 0.1% | 12 |
| `or_co_xtn_itt_cd` | 0.1% | 68 |
| `ovrs_fd_desc` | 0.1% | 4 |
| `pers_corp_desc` | 0.1% | 4 |
| `pfiv_sale_cntl_tcd` | 0.1% | 4 |
| `prvo_fd_desc` | 0.1% | 3 |
| `prvo_pbff_desc` | 0.1% | 3 |
| `rptt_ksd_itm_no` | 0.1% | 2,629 |
| `sale_yn` | 0.0% | 2 |
| `std_itm_no` | 0.1% | 11,128 |
| `thco_sale_yn` | 6.2% | 2 |
| `trusc_xtn_itt_cd` | 0.1% | 19 |
| `zrin_fd_ivst_risk_gcd` | 23.1% | 7 |
| `zrin_fd_ivst_risk_grd_nm` | 23.1% | 9 |
| `prfd_attr_cds` | 0.0% | 10,621 |

### `data/relations/etf_holding.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `pd_itm_no` | 0.0% | 487 |
| `holding_code_raw` | 0.0% | 9,265 |
| `holding_code_type` | 0.0% | 4 |
| `holding_name` | 0.1% | 8,349 |
| `weight` | 1.4% | 1,897 |
| `source` | 0.0% | 4 |
| `as_of` | 0.0% | 1 |

### `data/relations/etf_theme.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `pd_itm_no` | 0.0% | 1,099 |
| `theme` | 0.0% | 176 |
| `source` | 0.0% | 1 |
| `as_of` | 100.0% | 1 |
