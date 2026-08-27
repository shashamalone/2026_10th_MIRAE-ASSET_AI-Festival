# 데이터 인벤토리

이 파일은 `script/build_data_inventory.py`가 생성한다. **직접 편집하지 말 것.**
데이터 구조 변경 시 재실행 후 커밋하면 `git diff`가 그대로 변경 이력이 된다.
(생성 시각을 넣지 않는 이유: 매번 바뀌면 diff가 노이즈로 덮여 변경 추적이 불가능해진다.)

## 계층별 요약

| 파일 | 계층 | 행수 | 컬럼수 | 생성 스크립트 |
|---|---|---|---|---|
| `data/csv/PRBD01N001_bond_kr_master_20260824.csv` | 원본 | 21,882 | 58 | — |
| `data/csv/PRBD01N001_bond_kr_schema_20260824.csv` | 원본 | 58 | 5 | — |
| `data/csv/PREF01N001_etf_kr_master_20260824.csv` | 원본 | 1,780 | 98 | — |
| `data/csv/PREF01N001_etf_kr_schema_20260824.csv` | 원본 | 98 | 5 | — |
| `data/csv/PREF02N001_etf_gl_master_20260824.csv` | 원본 | 6,037 | 49 | — |
| `data/csv/PREF02N001_etf_gl_schema_20260824.csv` | 원본 | 49 | 5 | — |
| `data/csv/PRFD01N001_fund_pub_master_20260824.csv` | 원본 | 23,676 | 75 | — |
| `data/csv/PRFD01N001_fund_pub_schema_20260824.csv` | 원본 | 75 | 5 | — |
| `data/enriched/bond_kr_enriched.csv` | 파생 | 21,882 | 12 | `script/build_bond_enrichment.py` |
| `data/enriched/company_master.csv` | 파생 | 118,709 | 5 | `script/build_company_relations.py` |
| `data/enriched/etf_kr_enriched.csv` | 파생 | 1,780 | 12 | `script/build_etf_enrichment.py` |
| `data/enriched/holding_code_map.csv` | 파생 | 1,393 | 8 | `script/build_holding_code_map.py` |
| `data/relations/company_subsidiary.csv` | 관계 | 30,097 | 10 | `script/build_company_relations.py` |
| `data/relations/etf_holding.csv` | 관계 | 47,016 | 7 | `script/build_etf_holding.py` |
| `data/relations/etf_theme.csv` | 관계 | 5,646 | 4 | `script/build_etf_enrichment.py` |

## 파일별 컬럼

결측률은 빈 문자열 기준. 값 예시는 문서 비대화를 막기 위해 싣지 않는다.

### `data/csv/PRBD01N001_bond_kr_master_20260824.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `after_tax_yield` | 97.1% | 475 |
| `applied_yield` | 0.0% | 3,162 |
| `avg_annual_tax_yield` | 97.1% | 2 |
| `bdbns_abl_chnl_nm` | 97.1% | 2 |
| `bdbns_abl_chnl_tcd` | 97.1% | 2 |
| `bd_inrt_tcd` | 0.0% | 3 |
| `bd_intp_tcd` | 0.0% | 4 |
| `bd_knd` | 0.7% | 33 |
| `bd_ofr_tcd` | 0.0% | 2 |
| `bd_tisu_a` | 0.0% | 2,790 |
| `buyable_quantity` | 97.1% | 298 |
| `buy_yield` | 97.1% | 349 |
| `corp_after_tax_yield` | 97.1% | 470 |
| `corp_pretax_yield` | 97.1% | 448 |
| `cov` | 0.1% | 15,802 |
| `crd_grd` | 18.4% | 16 |
| `crd_grd_dt` | 18.3% | 2,152 |
| `curr_cd` | 0.0% | 2 |
| `depo_equiv_yield_154` | 97.1% | 416 |
| `depo_equiv_yield_495` | 97.1% | 446 |
| `dirty` | 0.1% | 16,604 |
| `dur` | 0.1% | 14,588 |
| `eval_price` | 0.0% | 16,605 |
| `exg_close_price` | 18.9% | 284 |
| `exg_close_price_base_dt` | 94.2% | 100 |
| `exg_close_yield` | 18.9% | 300 |
| `exrt_grte_ern_r` | 0.0% | 19 |
| `exrt_grte_ern_r_tcd` | 0.0% | 6 |
| `exrt_rpy_r` | 0.0% | 101 |
| `info_base_dt` | 0.0% | 1 |
| `info_seq` | 0.0% | 3 |
| `isu_bal_amt` | 0.0% | 2,947 |
| `isu_dt` | 0.0% | 2,488 |
| `mat_dt` | 0.0% | 3,799 |
| `ndy_applied_yield` | 0.1% | 3,156 |
| `ndy_cov` | 0.1% | 15,727 |
| `ndy_dirty` | 0.1% | 16,509 |
| `ndy_dur` | 0.1% | 14,477 |
| `ndy_eval_price` | 0.1% | 16,504 |
| `pd_abrv_eng_nm` | 0.1% | 20,482 |
| `pd_abrv_nm` | 0.1% | 20,477 |
| `pd_ctry_cd` | 0.0% | 2 |
| `pd_eng_nm` | 0.0% | 20,492 |
| `pd_exg_mkt` | 0.0% | 2 |
| `pd_nm` | 0.0% | 20,499 |
| `pd_no` | 0.0% | 20,497 |
| `pd_pbcm` | 0.7% | 1,819 |
| `pd_pen_tr_yn` | 0.0% | 2 |
| `pd_risk_gcd` | 0.0% | 7 |
| `pd_risk_nm` | 0.0% | 7 |
| `pd_std_info_update` | 0.0% | 1 |
| `pref_tax_yield` | 97.1% | 470 |
| `remaining_days` | 0.0% | 3,796 |
| `sale_yield_base_dt` | 97.1% | 2 |
| `srfc_irt` | 0.0% | 3,700 |
| `std_pd_mcls_nm` | 0.0% | 3 |
| `std_pd_scls_nm` | 0.0% | 13 |
| `trade_price` | 97.1% | 392 |

### `data/csv/PRBD01N001_bond_kr_schema_20260824.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `seq` | 0.0% | 58 |
| `column` | 0.0% | 58 |
| `dtype` | 0.0% | 5 |
| `nullable` | 0.0% | 2 |
| `comment_ko` | 0.0% | 58 |

### `data/csv/PREF01N001_etf_kr_master_20260824.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `cu_base_index` | 96.9% | 20 |
| `cu_charge_etc_rt` | 87.8% | 2 |
| `cu_charge_rt` | 87.8% | 18 |
| `cu_fund_mgmt_co` | 0.0% | 100 |
| `cu_lev_fector` | 10.2% | 8 |
| `cu_strtegy` | 8.7% | 5 |
| `cu_upt_dt` | 10.2% | 23 |
| `du_bpr` | 0.2% | 1,428 |
| `du_chas_errt` | 10.2% | 498 |
| `du_chas_errt_base_dt` | 10.2% | 23 |
| `du_clpr` | 0.2% | 1,437 |
| `du_diff_rt` | 10.2% | 304 |
| `du_diff_rt_base_dt` | 10.2% | 23 |
| `du_er_1d` | 11.0% | 693 |
| `du_er_1m` | 11.0% | 1,094 |
| `du_er_1y` | 20.4% | 1,206 |
| `du_er_3m` | 12.8% | 1,182 |
| `du_er_6m` | 16.5% | 1,221 |
| `du_er_ytd` | 17.0% | 1,255 |
| `du_hpr` | 0.2% | 1,387 |
| `du_last_aum` | 10.2% | 1,172 |
| `du_last_nav` | 10.2% | 1,584 |
| `du_lpr` | 0.2% | 1,363 |
| `du_nav_base_dt` | 10.2% | 23 |
| `du_nav_rnf_amt` | 10.2% | 1,507 |
| `du_nav_yday` | 10.2% | 1,585 |
| `du_upt_dt` | 10.2% | 23 |
| `du_val_1d` | 0.2% | 1,465 |
| `du_val_1m` | 0.9% | 1,516 |
| `du_val_5d` | 0.3% | 1,507 |
| `du_vlty_1m` | 5.8% | 1,627 |
| `du_vlty_1y` | 26.5% | 1,291 |
| `du_vlty_3m` | 10.4% | 1,550 |
| `du_vlty_6m` | 16.5% | 1,449 |
| `du_vlty_base_dt` | 4.8% | 50 |
| `du_vol_1d` | 0.2% | 1,313 |
| `du_vol_avg_1m` | 0.8% | 1,506 |
| `du_vol_avg_5d` | 0.3% | 1,458 |
| `fn_average_coupon` | 88.8% | 197 |
| `fn_average_maturity` | 100.0% | 1 |
| `fn_average_quality` | 95.8% | 33 |
| `fn_base_dt` | 35.1% | 2 |
| `fn_effective_duration` | 100.0% | 1 |
| `fn_effective_maturity` | 87.9% | 213 |
| `fn_modified_duration` | 100.0% | 1 |
| `fn_nominal_maturity` | 87.9% | 213 |
| `fn_portfolio_dt` | 37.2% | 18 |
| `pd_abrv_nm` | 0.0% | 1,773 |
| `pd_circ_net_tamt` | 10.2% | 671 |
| `pd_circ_stk_cnt` | 10.2% | 630 |
| `pd_curr_cd` | 0.2% | 3 |
| `pd_curr_nm` | 0.2% | 3 |
| `pd_divd_amt_ann` | 53.4% | 590 |
| `pd_divd_amt_pshr` | 32.1% | 969 |
| `pd_dvid_base_dt` | 32.1% | 2 |
| `pd_dvid_cycl` | 32.1% | 5 |
| `pd_dvid_inc_dist` | 100.0% | 1 |
| `pd_dvid_nav` | 32.1% | 1,209 |
| `pd_dvid_pay_cnt` | 32.1% | 5 |
| `pd_dvid_pay_months` | 32.1% | 16 |
| `pd_dvid_prc_base_dt` | 32.1% | 32 |
| `pd_dvid_tax_basis` | 32.1% | 2 |
| `pd_dvid_yield` | 32.1% | 968 |
| `pd_exg_mkt_cd` | 0.2% | 2 |
| `pd_exg_mkt_nm` | 0.2% | 2 |
| `pd_grp_no` | 0.0% | 2 |
| `pd_isin_cd` | 32.1% | 1,209 |
| `pd_itm_no` | 0.0% | 1,780 |
| `pd_itm_no_ma` | 0.0% | 1,780 |
| `pd_lst_stk_cnt` | 0.0% | 688 |
| `pd_lste_dt` | 0.2% | 92 |
| `pd_lstg_dt` | 0.2% | 613 |
| `pd_mkt_id` | 0.2% | 2 |
| `pd_mkt_nm` | 0.2% | 2 |
| `pd_net_tamt` | 10.2% | 1,596 |
| `pd_nm` | 0.0% | 1,780 |
| `pd_pen_risk_nm` | 0.0% | 3 |
| `pd_pen_tr_yn` | 0.0% | 2 |
| `pd_ric` | 32.1% | 1,209 |
| `pd_risk_cd` | 0.0% | 6 |
| `pd_risk_nm` | 0.0% | 6 |
| `pd_sale_yn` | 0.0% | 2 |
| `pd_sect_cd` | 10.2% | 6 |
| `pd_spac_yn` | 10.2% | 2 |
| `pd_stk_cnt` | 10.2% | 662 |
| `pd_ticker` | 32.1% | 1,209 |
| `pd_tr_yn` | 0.2% | 3 |
| `ref_ast_type` | 32.1% | 8 |
| `ref_base_dt` | 32.1% | 2 |
| `ref_base_index` | 32.1% | 906 |
| `ref_fund_mgmt_co` | 32.1% | 30 |
| `ref_geo_focus` | 32.1% | 24 |
| `ru_mkt_price` | 0.2% | 1,439 |
| `ru_mkt_volume` | 0.2% | 1,313 |
| `wu_core_yn` | 0.0% | 2 |
| `wu_inv_ast_type` | 0.0% | 9 |
| `wu_inv_rgn` | 0.0% | 11 |
| `wu_upt_dt` | 0.2% | 2 |

### `data/csv/PREF01N001_etf_kr_schema_20260824.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `seq` | 0.0% | 98 |
| `column` | 0.0% | 98 |
| `dtype` | 0.0% | 4 |
| `nullable` | 0.0% | 2 |
| `comment_ko` | 0.0% | 98 |

### `data/csv/PREF02N001_etf_gl_master_20260824.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `cu_base_index` | 0.2% | 1,851 |
| `cu_charge_rt` | 0.0% | 130 |
| `cu_etn_yn` | 98.9% | 2 |
| `cu_fund_mgmt_co` | 0.2% | 383 |
| `cu_index_repl_mthd` | 60.1% | 5 |
| `cu_index_tracking_yn` | 60.1% | 2 |
| `cu_inverse_short_yn` | 97.0% | 2 |
| `cu_lev_fector` | 85.1% | 12 |
| `cu_strtegy` | 0.2% | 5,944 |
| `cu_upt_dt` | 0.0% | 1 |
| `du_base_dt_match_yn` | 0.2% | 2 |
| `du_bpr` | 0.2% | 5,437 |
| `du_clpr` | 0.2% | 5,400 |
| `du_clpr_base_dt` | 0.2% | 110 |
| `du_clpr_src` | 0.2% | 2 |
| `du_diff_rt` | 100.0% | 4 |
| `du_er_1d` | 0.2% | 960 |
| `du_hpr` | 0.2% | 5,031 |
| `du_last_aum` | 3.4% | 4,900 |
| `du_last_nav` | 87.4% | 530 |
| `du_lpr` | 0.2% | 5,035 |
| `du_nav_base_dt` | 0.0% | 1 |
| `du_opr` | 0.2% | 4,685 |
| `du_upt_dt` | 0.0% | 108 |
| `du_val_1d` | 0.2% | 5,753 |
| `du_vol_1d` | 0.2% | 4,950 |
| `pd_abrv_nm` | 0.0% | 6,031 |
| `pd_curr_cd` | 0.2% | 3 |
| `pd_exg_mkt_cd` | 0.0% | 5 |
| `pd_grp_no` | 0.0% | 2 |
| `pd_isin_cd` | 0.2% | 5,963 |
| `pd_itm_no` | 0.0% | 6,037 |
| `pd_itm_no_ma` | 0.0% | 6,037 |
| `pd_lipper_id` | 0.2% | 5,964 |
| `pd_lstg_dt` | 0.0% | 2,006 |
| `pd_lst_price` | 0.2% | 3 |
| `pd_lst_stk_cnt` | 0.0% | 3,213 |
| `pd_mkt_id` | 0.0% | 1 |
| `pd_nm` | 0.0% | 6,009 |
| `pd_sale_yn` | 0.2% | 2 |
| `pd_trd_ccy` | 0.0% | 1 |
| `pd_tr_yn` | 0.2% | 2 |
| `pd_us_cik` | 0.3% | 390 |
| `ru_mkt_price` | 0.2% | 5,400 |
| `ru_mkt_volume` | 0.2% | 4,950 |
| `wu_core_yn` | 98.2% | 2 |
| `wu_inv_ast_type` | 0.2% | 7 |
| `wu_inv_rgn` | 0.2% | 60 |
| `wu_upt_dt` | 0.0% | 1 |

### `data/csv/PREF02N001_etf_gl_schema_20260824.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `seq` | 0.0% | 49 |
| `column` | 0.0% | 49 |
| `dtype` | 0.0% | 5 |
| `nullable` | 0.0% | 2 |
| `comment_ko` | 0.0% | 49 |

### `data/csv/PRFD01N001_fund_pub_master_20260824.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `bmrk_eng_nm` | 52.4% | 387 |
| `bmrk_nm` | 52.4% | 390 |
| `bns_bpr` | 60.2% | 9,075 |
| `curr_cd` | 0.0% | 7 |
| `exchdg_yn` | 70.5% | 3 |
| `fd_daily_bas_dt` | 60.2% | 906 |
| `fd_estb_ctry_cd` | 0.0% | 7 |
| `fd_ivst_rgn_desc` | 0.0% | 9 |
| `fd_last_dstb_actg_bss_dt` | 54.1% | 2,020 |
| `fd_last_dstb_actg_eot_dt` | 54.1% | 1,786 |
| `fd_last_dstb_r` | 54.1% | 4,244 |
| `fd_mm18_ern_r` | 70.9% | 4,646 |
| `fd_mm1_ern_r` | 68.8% | 1,443 |
| `fd_mm3_ern_r` | 69.1% | 2,124 |
| `fd_mm6_ern_r` | 69.5% | 3,164 |
| `fd_nast_suma` | 60.2% | 9,410 |
| `fd_price_bas_dt` | 60.2% | 906 |
| `fd_prsv_r` | 0.0% | 790 |
| `fd_sbpr` | 0.0% | 1,978 |
| `fd_set_pcd` | 0.0% | 3 |
| `fd_wk1_ern_r` | 100.0% | 1 |
| `fd_yr1_ern_r` | 70.3% | 4,470 |
| `fd_yr2_ern_r` | 71.5% | 4,953 |
| `fd_yr3_ern_r` | 72.6% | 5,111 |
| `fd_yr5_ern_r` | 74.7% | 4,883 |
| `frc_bpr_itm_yn` | 0.0% | 2 |
| `fss_itm_no` | 0.2% | 11,971 |
| `han_clas_fee_type` | 59.3% | 4 |
| `han_clas_nm` | 59.3% | 196 |
| `han_clas_policies` | 73.5% | 34 |
| `han_clas_sales_channel` | 59.4% | 4 |
| `hdge_fd_yn` | 0.0% | 2 |
| `int_dvd_desc` | 0.0% | 3 |
| `itm_abrv_nm` | 0.0% | 23,588 |
| `itm_eabrv_nm` | 99.4% | 144 |
| `itm_eng_nm` | 0.0% | 23,403 |
| `itm_nm` | 0.0% | 23,624 |
| `itm_no` | 0.0% | 23,676 |
| `kofia_fd_ccd` | 0.2% | 6,766 |
| `ksd_itm_no` | 10.0% | 21,291 |
| `mtco_itm_no` | 0.5% | 14,059 |
| `ofsfd_yn` | 0.0% | 2 |
| `ofwk_trus_rwrd_r` | 0.0% | 70 |
| `or_attr_desc` | 0.0% | 14 |
| `or_co_rwrd_r` | 0.0% | 754 |
| `or_co_xtn_itt_cd` | 0.0% | 275 |
| `ovrs_fd_desc` | 0.0% | 4 |
| `pers_corp_desc` | 0.0% | 3 |
| `pfiv_sale_cntl_tcd` | 0.0% | 4 |
| `prfd_attr_cds` | 52.4% | 8,927 |
| `prfd_attr_cnt` | 0.0% | 14 |
| `prfd_attr_search_text` | 52.4% | 10,574 |
| `prvo_fd_desc` | 0.0% | 4 |
| `prvo_pbff_desc` | 0.0% | 2 |
| `rptt_ksd_itm_no` | 0.5% | 6,886 |
| `sale_co_rwrd_r` | 0.0% | 769 |
| `sale_yn` | 0.0% | 2 |
| `std_itm_no` | 18.4% | 18,948 |
| `thco_sale_yn` | 55.2% | 2 |
| `trusc_rwrd_r` | 0.0% | 96 |
| `trusc_xtn_itt_cd` | 0.2% | 51 |
| `zrin_attr_nms` | 52.4% | 10,578 |
| `zrin_btyp_cd` | 52.4% | 19 |
| `zrin_btyp_nm` | 52.4% | 19 |
| `zrin_dmst_bd_cmst_rt` | 60.2% | 284 |
| `zrin_dmst_stk_cmst_rt` | 60.2% | 337 |
| `zrin_etc_ast_cmst_rt` | 60.2% | 918 |
| `zrin_fd_cmst_rt` | 60.2% | 1,137 |
| `zrin_fd_ivst_risk_gcd` | 63.3% | 7 |
| `zrin_fd_ivst_risk_grd_nm` | 63.3% | 9 |
| `zrin_liqt_cmst_rt` | 60.2% | 974 |
| `zrin_ovrs_bd_cmst_rt` | 60.2% | 16 |
| `zrin_ovrs_stk_cmst_rt` | 60.2% | 107 |
| `zrin_pcd` | 52.4% | 105 |
| `zrin_ptn_nm` | 52.4% | 103 |

### `data/csv/PRFD01N001_fund_pub_schema_20260824.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `seq` | 0.0% | 75 |
| `column` | 0.0% | 75 |
| `dtype` | 0.0% | 7 |
| `nullable` | 0.0% | 2 |
| `comment_ko` | 0.0% | 75 |

### `data/enriched/bond_kr_enriched.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `pd_no` | 0.0% | 20,497 |
| `pd_exg_mkt` | 0.0% | 2 |
| `info_seq` | 0.0% | 3 |
| `crd_grd_norm` | 18.4% | 16 |
| `crd_grd_rank` | 18.4% | 16 |
| `crd_grd_source` | 18.4% | 2 |
| `remaining_days` | 0.0% | 3,798 |
| `maturity_bucket` | 0.0% | 7 |
| `is_krw` | 0.0% | 2 |
| `has_sale_info` | 0.0% | 2 |
| `is_sellable` | 0.0% | 3 |
| `source` | 0.0% | 1 |

### `data/enriched/company_master.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `corp_code` | 0.0% | 118,709 |
| `corp_name` | 0.0% | 110,838 |
| `corp_name_norm` | 0.0% | 110,822 |
| `stock_code` | 96.6% | 3,984 |
| `source` | 0.0% | 1 |

### `data/enriched/etf_kr_enriched.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `pd_itm_no` | 0.0% | 1,780 |
| `pd_itm_no_ma` | 0.0% | 1,780 |
| `pd_grp_no` | 0.0% | 2 |
| `pd_abrv_nm` | 0.0% | 1,773 |
| `lseg_key` | 0.0% | 1,780 |
| `ter` | 38.3% | 105 |
| `replication` | 38.3% | 5 |
| `base_market` | 38.3% | 4 |
| `base_asset` | 38.3% | 8 |
| `hedge_type` | 38.3% | 4 |
| `charge_rt_final` | 38.3% | 106 |
| `charge_rt_source` | 38.3% | 3 |

### `data/enriched/holding_code_map.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `holding_code_raw` | 0.0% | 1,393 |
| `holding_name` | 0.0% | 1,390 |
| `sec_type` | 6.5% | 4 |
| `corp_code` | 11.6% | 1,212 |
| `common_ticker` | 98.6% | 17 |
| `etf_isin` | 94.8% | 73 |
| `match_rule` | 6.5% | 4 |
| `source` | 0.0% | 1 |

### `data/relations/company_subsidiary.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `parent_corp_code` | 0.0% | 2,325 |
| `parent_name` | 0.0% | 2,325 |
| `child_name` | 0.0% | 27,406 |
| `child_name_norm` | 0.0% | 25,266 |
| `child_corp_code` | 69.7% | 6,289 |
| `child_match_rule` | 69.7% | 5 |
| `ownership_pct` | 8.1% | 4,235 |
| `invest_purpose` | 0.0% | 1,324 |
| `source` | 0.0% | 1 |
| `as_of` | 0.0% | 138 |

### `data/relations/etf_holding.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `pd_itm_no` | 0.0% | 711 |
| `holding_code_raw` | 0.0% | 12,880 |
| `holding_code_type` | 0.0% | 4 |
| `holding_name` | 0.1% | 10,681 |
| `weight` | 1.7% | 2,225 |
| `source` | 0.0% | 4 |
| `as_of` | 0.0% | 1 |

### `data/relations/etf_theme.csv`

| 컬럼 | 결측률 | 고유값수 |
|---|---|---|
| `pd_itm_no` | 0.0% | 1,099 |
| `theme` | 0.0% | 176 |
| `source` | 0.0% | 1 |
| `as_of` | 100.0% | 1 |
