# 원격 DB vs 로컬 RDB 로직 스키마 대조

작성일 2026-09-05 · 원격: `http://40.82.145.44:8000` (information_schema 실측) · 로컬: `src/tools/rdb_schema.py` 정의 · 데이터 기준일 2026-08-24

이 문서는 스크립트 `script/db_schema/dump_remote_vs_local_schema.py`가 생성한다. 값(데이터)은 담지 않고 구조만 담는다.

## 1. 요약

| 구분 | 내용 |
|---|---|
| 원격 테이블 수 | 50개 (스키마 7종: core, enriched, meta, raw, relations, vec, vec_prev_t108) |
| 로컬 로직이 조회하는 원본 테이블 | 4개: `raw.prbd01n001`(채권), `raw.pref01n001`(국내ETF), `raw.pref02n001`(해외ETF), `raw.prfd01n001`(펀드) |
| 로컬 로직이 JOIN하는 보강 테이블 | `enriched.etf_kr_enriched` |
| 원본 테이블 컬럼 불일치 | 없음 (4개 테이블 전부 컬럼 집합 동일) |
| 보강 테이블 불일치 | `enriched.etf_kr_enriched` 원격 부재 |

## 2. 원격 DB (실측)

### 2.1 테이블 목록과 행수

| 스키마.테이블 | 종류 | 행수 | 컬럼 수 | 로컬 로직 사용 |
|---|---|---:|---:|---|
| `core.bond_kr` | 뷰 | 20,497 | 13 | - |
| `core.etf_gl` | 뷰 | 5,972 | 10 | - |
| `core.etf_kr` | 뷰 | 1,235 | 11 | - |
| `core.etn` | 뷰 | 610 | 12 | - |
| `core.fund_pub` | 뷰 | 14,716 | 9 | - |
| `enriched.bond_kr_offer` | 테이블 | 21,882 | 12 | - |
| `enriched.bond_kr_product` | 테이블 | 20,497 | 13 | - |
| `enriched.etf_gl` | 테이블 | 5,972 | 10 | - |
| `enriched.etf_kr` | 테이블 | 1,235 | 11 | - |
| `enriched.etn_gl` | 테이블 | 65 | 9 | - |
| `enriched.etn_kr` | 테이블 | 545 | 10 | - |
| `enriched.fund` | 테이블 | 23,676 | 9 | - |
| `enriched.fund_pub` | 뷰 | 14,716 | 9 | - |
| `enriched.product_master` | 테이블 | 51,990 | 12 | - |
| `enriched.product_metric` | 테이블 | 113,146 | 12 | - |
| `enriched.security_identifier` | 테이블 | 87,558 | 4 | - |
| `enriched.security_master` | 테이블 | 71,953 | 5 | - |
| `meta.column_catalog` | 테이블 | 499 | 17 | - |
| `meta.dataset_snapshot` | 테이블 | 1 | 8 | - |
| `meta.load_run` | 테이블 | 1 | 10 | - |
| `meta.product_coverage` | 테이블 | 51,990 | 9 | - |
| `raw.bond_kr_master` | 테이블 | 21,882 | 58 | - |
| `raw.etf_gl_master` | 테이블 | 6,037 | 49 | - |
| `raw.etf_kr_master` | 테이블 | 1,780 | 98 | - |
| `raw.fund_pub_master` | 테이블 | 23,676 | 75 | - |
| `raw.prbd01n001` | 뷰 | 21,882 | 58 | 원본 조회 |
| `raw.pref01n001` | 뷰 | 1,780 | 98 | 원본 조회 |
| `raw.pref02n001` | 뷰 | 6,037 | 49 | 원본 조회 |
| `raw.prfd01n001` | 뷰 | 23,676 | 75 | 원본 조회 |
| `relations.company_subsidiary` | 테이블 | 8,866 | 7 | - |
| `relations.etf_holding` | 뷰 | 46,951 | 8 | - |
| `relations.etf_theme` | 뷰 | 0 | 7 | - |
| `relations.product_classification` | 테이블 | 61,744 | 7 | - |
| `relations.product_document` | 테이블 | 711 | 3 | - |
| `relations.product_holding` | 테이블 | 46,951 | 8 | - |
| `relations.source_document` | 테이블 | 2,345 | 9 | - |
| `vec.bond_schema_terms` | 테이블 | 130 | 12 | - |
| `vec.chunk_embedding` | 테이블 | 5,664 | 6 | - |
| `vec.document_chunk` | 테이블 | 9,055 | 14 | - |
| `vec.document_product` | 테이블 | 1,019 | 3 | - |
| `vec.product_coverage` | 테이블 | 15,951 | 7 | - |
| `vec.schema_terms_all` | 테이블 | 189 | 12 | - |
| `vec.source_document` | 테이블 | 974 | 8 | - |
| `vec.vector_deploy_event` | 테이블 | 7 | 5 | - |
| `vec.vector_deploy_run` | 테이블 | 1 | 15 | - |
| `vec_prev_t108.bond_schema_terms` | 테이블 | 0 | 11 | - |
| `vec_prev_t108.doc_chunk` | 뷰 | 0 | 12 | - |
| `vec_prev_t108.document_chunk` | 테이블 | 0 | 12 | - |
| `vec_prev_t108.schema_index` | 뷰 | 0 | 11 | - |
| `vec_prev_t108.schema_terms_all` | 테이블 | 0 | 11 | - |

### 2.2 테이블별 컬럼 구성

#### `core.bond_kr` (20,497행, 13열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_no` | text |
| `name` | text |
| `issuer` | text |
| `credit_rating` | text |
| `currency` | text |
| `issue_date` | date |
| `maturity_date` | date |
| `risk_code` | text |
| `risk_name` | text |
| `is_assumed_purchasable` | boolean |
| `purchasable_rule` | text |
| `effective_as_of` | date |

#### `core.etf_gl` (5,972행, 10열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_itm_no` | text |
| `name` | text |
| `ticker` | text |
| `isin` | text |
| `manager` | text |
| `base_index` | text |
| `currency` | text |
| `inception_date` | date |
| `effective_as_of` | date |

#### `core.etf_kr` (1,235행, 11열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_itm_no` | text |
| `name` | text |
| `ticker` | text |
| `isin` | text |
| `manager` | text |
| `base_index` | text |
| `currency` | text |
| `listing_date` | date |
| `delisting_date` | date |
| `effective_as_of` | date |

#### `core.etn` (610행, 12열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_itm_no` | text |
| `name` | text |
| `ticker` | text |
| `isin` | text |
| `issuer` | text |
| `currency` | text |
| `listing_date` | date |
| `inception_date` | date |
| `delisting_date` | date |
| `effective_as_of` | date |
| `market_scope` | text |

#### `core.fund_pub` (14,716행, 9열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `itm_no` | text |
| `name` | text |
| `short_name` | text |
| `offering_type` | text |
| `manager_org_code` | text |
| `benchmark` | text |
| `currency` | text |
| `effective_as_of` | date |

#### `enriched.bond_kr_offer` (21,882행, 12열)

| 컬럼 | 타입 |
|---|---|
| `pd_no` | text |
| `exchange_market` | text |
| `info_base_dt` | date |
| `info_seq` | integer |
| `product_id` | text |
| `applied_yield` | double precision |
| `after_tax_yield` | double precision |
| `buy_yield` | double precision |
| `sale_yield_base_dt` | date |
| `eval_price` | double precision |
| `trade_price` | double precision |
| `buyable_quantity` | numeric |

#### `enriched.bond_kr_product` (20,497행, 13열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_no` | text |
| `name` | text |
| `issuer` | text |
| `credit_rating` | text |
| `currency` | text |
| `issue_date` | date |
| `maturity_date` | date |
| `risk_code` | text |
| `risk_name` | text |
| `is_assumed_purchasable` | boolean |
| `purchasable_rule` | text |
| `effective_as_of` | date |

#### `enriched.etf_gl` (5,972행, 10열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_itm_no` | text |
| `name` | text |
| `ticker` | text |
| `isin` | text |
| `manager` | text |
| `base_index` | text |
| `currency` | text |
| `inception_date` | date |
| `effective_as_of` | date |

#### `enriched.etf_kr` (1,235행, 11열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_itm_no` | text |
| `name` | text |
| `ticker` | text |
| `isin` | text |
| `manager` | text |
| `base_index` | text |
| `currency` | text |
| `listing_date` | date |
| `delisting_date` | date |
| `effective_as_of` | date |

#### `enriched.etn_gl` (65행, 9열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_itm_no` | text |
| `name` | text |
| `ticker` | text |
| `isin` | text |
| `issuer` | text |
| `currency` | text |
| `inception_date` | date |
| `effective_as_of` | date |

#### `enriched.etn_kr` (545행, 10열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `pd_itm_no` | text |
| `name` | text |
| `ticker` | text |
| `isin` | text |
| `issuer` | text |
| `currency` | text |
| `listing_date` | date |
| `delisting_date` | date |
| `effective_as_of` | date |

#### `enriched.fund` (23,676행, 9열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `itm_no` | text |
| `name` | text |
| `short_name` | text |
| `offering_type` | text |
| `manager_org_code` | text |
| `benchmark` | text |
| `currency` | text |
| `effective_as_of` | date |

#### `enriched.fund_pub` (14,716행, 9열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `itm_no` | text |
| `name` | text |
| `short_name` | text |
| `offering_type` | text |
| `manager_org_code` | text |
| `benchmark` | text |
| `currency` | text |
| `effective_as_of` | date |

#### `enriched.product_master` (51,990행, 12열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `source_table` | text |
| `source_key` | text |
| `product_type` | text |
| `market_scope` | text |
| `name` | text |
| `short_name` | text |
| `currency` | text |
| `is_active` | boolean |
| `active_rule` | text |
| `snapshot_date` | date |
| `effective_as_of` | date |

#### `enriched.product_metric` (113,146행, 12열)

| 컬럼 | 타입 |
|---|---|
| `metric_id` | text |
| `product_id` | text |
| `metric_code` | text |
| `value` | numeric |
| `unit` | text |
| `as_of` | date |
| `source` | text |
| `source_column` | text |
| `method` | text |
| `is_available` | boolean |
| `unavailable_reason` | text |
| `source_priority` | smallint |

#### `enriched.security_identifier` (87,558행, 4열)

| 컬럼 | 타입 |
|---|---|
| `security_id` | text |
| `id_type` | text |
| `id_value` | text |
| `is_primary` | boolean |

#### `enriched.security_master` (71,953행, 5열)

| 컬럼 | 타입 |
|---|---|
| `security_id` | text |
| `display_name` | text |
| `security_type` | text |
| `issuer_name` | text |
| `country_code` | text |

#### `meta.column_catalog` (499행, 17열)

| 컬럼 | 타입 |
|---|---|
| `table_schema` | text |
| `table_name` | text |
| `ordinal_position` | integer |
| `column_name` | text |
| `data_type` | text |
| `is_nullable` | boolean |
| `description` | text |
| `unit` | text |
| `as_of_column` | text |
| `zero_null_rule` | text |
| `source_priority` | text |
| `transform_expression` | text |
| `implementation_status` | text |
| `deployment_status` | text |
| `pk_ordinal` | integer |
| `fk_target` | text |
| `grain` | text |

#### `meta.dataset_snapshot` (1행, 8열)

| 컬럼 | 타입 |
|---|---|
| `snapshot_id` | uuid |
| `dataset_version` | text |
| `release_date` | date |
| `cutoff_date` | date |
| `domain_as_of` | jsonb |
| `source_files` | jsonb |
| `source_hash` | text |
| `built_at` | timestamp with time zone |

#### `meta.load_run` (1행, 10열)

| 컬럼 | 타입 |
|---|---|
| `run_id` | uuid |
| `snapshot_id` | uuid |
| `started_at` | timestamp with time zone |
| `finished_at` | timestamp with time zone |
| `status` | text |
| `phase` | text |
| `source_rows` | jsonb |
| `loaded_rows` | jsonb |
| `validation_result` | jsonb |
| `error_message` | text |

#### `meta.product_coverage` (51,990행, 9열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `holdings_status` | text |
| `holdings_reason` | text |
| `document_status` | text |
| `document_reason` | text |
| `performance_status` | text |
| `performance_reason` | text |
| `as_of` | date |
| `source_document_id` | text |

#### `raw.bond_kr_master` (21,882행, 58열)

| 컬럼 | 타입 |
|---|---|
| `after_tax_yield` | double precision |
| `applied_yield` | double precision |
| `avg_annual_tax_yield` | double precision |
| `bdbns_abl_chnl_nm` | text |
| `bdbns_abl_chnl_tcd` | text |
| `bd_inrt_tcd` | text |
| `bd_intp_tcd` | text |
| `bd_knd` | text |
| `bd_ofr_tcd` | text |
| `bd_tisu_a` | numeric |
| `buyable_quantity` | double precision |
| `buy_yield` | double precision |
| `corp_after_tax_yield` | double precision |
| `corp_pretax_yield` | double precision |
| `cov` | double precision |
| `crd_grd` | text |
| `crd_grd_dt` | text |
| `curr_cd` | text |
| `depo_equiv_yield_154` | double precision |
| `depo_equiv_yield_495` | double precision |
| `dirty` | double precision |
| `dur` | double precision |
| `eval_price` | double precision |
| `exg_close_price` | double precision |
| `exg_close_price_base_dt` | text |
| `exg_close_yield` | double precision |
| `exrt_grte_ern_r` | numeric |
| `exrt_grte_ern_r_tcd` | text |
| `exrt_rpy_r` | numeric |
| `info_base_dt` | text |
| `info_seq` | bigint |
| `isu_bal_amt` | double precision |
| `isu_dt` | text |
| `mat_dt` | text |
| `ndy_applied_yield` | double precision |
| `ndy_cov` | double precision |
| `ndy_dirty` | double precision |
| `ndy_dur` | double precision |
| `ndy_eval_price` | double precision |
| `pd_abrv_eng_nm` | text |
| `pd_abrv_nm` | text |
| `pd_ctry_cd` | text |
| `pd_eng_nm` | text |
| `pd_exg_mkt` | text |
| `pd_nm` | text |
| `pd_no` | text |
| `pd_pbcm` | text |
| `pd_pen_tr_yn` | text |
| `pd_risk_gcd` | text |
| `pd_risk_nm` | text |
| `pd_std_info_update` | text |
| `pref_tax_yield` | double precision |
| `remaining_days` | double precision |
| `sale_yield_base_dt` | text |
| `srfc_irt` | double precision |
| `std_pd_mcls_nm` | text |
| `std_pd_scls_nm` | text |
| `trade_price` | double precision |

#### `raw.etf_gl_master` (6,037행, 49열)

| 컬럼 | 타입 |
|---|---|
| `cu_base_index` | text |
| `cu_charge_rt` | numeric |
| `cu_etn_yn` | text |
| `cu_fund_mgmt_co` | text |
| `cu_index_repl_mthd` | text |
| `cu_index_tracking_yn` | text |
| `cu_inverse_short_yn` | text |
| `cu_lev_fector` | numeric |
| `cu_strtegy` | text |
| `cu_upt_dt` | text |
| `du_base_dt_match_yn` | text |
| `du_bpr` | numeric |
| `du_clpr` | numeric |
| `du_clpr_base_dt` | text |
| `du_clpr_src` | text |
| `du_diff_rt` | numeric |
| `du_er_1d` | numeric |
| `du_hpr` | numeric |
| `du_last_aum` | numeric |
| `du_last_nav` | numeric |
| `du_lpr` | numeric |
| `du_nav_base_dt` | text |
| `du_opr` | numeric |
| `du_upt_dt` | text |
| `du_val_1d` | numeric |
| `du_vol_1d` | numeric |
| `pd_abrv_nm` | text |
| `pd_curr_cd` | text |
| `pd_exg_mkt_cd` | text |
| `pd_grp_no` | text |
| `pd_isin_cd` | text |
| `pd_itm_no` | text |
| `pd_itm_no_ma` | text |
| `pd_lipper_id` | text |
| `pd_lstg_dt` | text |
| `pd_lst_price` | numeric |
| `pd_lst_stk_cnt` | numeric |
| `pd_mkt_id` | text |
| `pd_nm` | text |
| `pd_sale_yn` | text |
| `pd_trd_ccy` | text |
| `pd_tr_yn` | text |
| `pd_us_cik` | text |
| `ru_mkt_price` | numeric |
| `ru_mkt_volume` | numeric |
| `wu_core_yn` | text |
| `wu_inv_ast_type` | text |
| `wu_inv_rgn` | text |
| `wu_upt_dt` | text |

#### `raw.etf_kr_master` (1,780행, 98열)

| 컬럼 | 타입 |
|---|---|
| `cu_base_index` | text |
| `cu_charge_etc_rt` | text |
| `cu_charge_rt` | text |
| `cu_fund_mgmt_co` | text |
| `cu_lev_fector` | text |
| `cu_strtegy` | text |
| `cu_upt_dt` | text |
| `du_bpr` | numeric |
| `du_chas_errt` | numeric |
| `du_chas_errt_base_dt` | text |
| `du_clpr` | numeric |
| `du_diff_rt` | numeric |
| `du_diff_rt_base_dt` | text |
| `du_er_1d` | numeric |
| `du_er_1m` | numeric |
| `du_er_1y` | numeric |
| `du_er_3m` | numeric |
| `du_er_6m` | numeric |
| `du_er_ytd` | numeric |
| `du_hpr` | numeric |
| `du_last_aum` | numeric |
| `du_last_nav` | numeric |
| `du_lpr` | numeric |
| `du_nav_base_dt` | text |
| `du_nav_rnf_amt` | numeric |
| `du_nav_yday` | numeric |
| `du_upt_dt` | text |
| `du_val_1d` | numeric |
| `du_val_1m` | numeric |
| `du_val_5d` | numeric |
| `du_vlty_1m` | numeric |
| `du_vlty_1y` | numeric |
| `du_vlty_3m` | numeric |
| `du_vlty_6m` | numeric |
| `du_vlty_base_dt` | text |
| `du_vol_1d` | numeric |
| `du_vol_avg_1m` | numeric |
| `du_vol_avg_5d` | numeric |
| `fn_average_coupon` | numeric |
| `fn_average_maturity` | numeric |
| `fn_average_quality` | text |
| `fn_base_dt` | text |
| `fn_effective_duration` | numeric |
| `fn_effective_maturity` | numeric |
| `fn_modified_duration` | numeric |
| `fn_nominal_maturity` | numeric |
| `fn_portfolio_dt` | text |
| `pd_abrv_nm` | text |
| `pd_circ_net_tamt` | numeric |
| `pd_circ_stk_cnt` | numeric |
| `pd_curr_cd` | text |
| `pd_curr_nm` | text |
| `pd_divd_amt_ann` | numeric |
| `pd_divd_amt_pshr` | numeric |
| `pd_dvid_base_dt` | text |
| `pd_dvid_cycl` | text |
| `pd_dvid_inc_dist` | numeric |
| `pd_dvid_nav` | numeric |
| `pd_dvid_pay_cnt` | numeric |
| `pd_dvid_pay_months` | text |
| `pd_dvid_prc_base_dt` | text |
| `pd_dvid_tax_basis` | text |
| `pd_dvid_yield` | numeric |
| `pd_exg_mkt_cd` | text |
| `pd_exg_mkt_nm` | text |
| `pd_grp_no` | text |
| `pd_isin_cd` | text |
| `pd_itm_no` | text |
| `pd_itm_no_ma` | text |
| `pd_lst_stk_cnt` | numeric |
| `pd_lste_dt` | text |
| `pd_lstg_dt` | text |
| `pd_mkt_id` | text |
| `pd_mkt_nm` | text |
| `pd_net_tamt` | numeric |
| `pd_nm` | text |
| `pd_pen_risk_nm` | text |
| `pd_pen_tr_yn` | text |
| `pd_ric` | text |
| `pd_risk_cd` | text |
| `pd_risk_nm` | text |
| `pd_sale_yn` | text |
| `pd_sect_cd` | text |
| `pd_spac_yn` | text |
| `pd_stk_cnt` | numeric |
| `pd_ticker` | text |
| `pd_tr_yn` | text |
| `ref_ast_type` | text |
| `ref_base_dt` | text |
| `ref_base_index` | text |
| `ref_fund_mgmt_co` | text |
| `ref_geo_focus` | text |
| `ru_mkt_price` | numeric |
| `ru_mkt_volume` | numeric |
| `wu_core_yn` | text |
| `wu_inv_ast_type` | text |
| `wu_inv_rgn` | text |
| `wu_upt_dt` | text |

#### `raw.fund_pub_master` (23,676행, 75열)

| 컬럼 | 타입 |
|---|---|
| `bmrk_eng_nm` | text |
| `bmrk_nm` | text |
| `bns_bpr` | numeric |
| `curr_cd` | text |
| `exchdg_yn` | text |
| `fd_daily_bas_dt` | text |
| `fd_estb_ctry_cd` | text |
| `fd_ivst_rgn_desc` | text |
| `fd_last_dstb_actg_bss_dt` | text |
| `fd_last_dstb_actg_eot_dt` | text |
| `fd_last_dstb_r` | numeric |
| `fd_mm18_ern_r` | numeric |
| `fd_mm1_ern_r` | numeric |
| `fd_mm3_ern_r` | numeric |
| `fd_mm6_ern_r` | numeric |
| `fd_nast_suma` | numeric |
| `fd_price_bas_dt` | text |
| `fd_prsv_r` | numeric |
| `fd_sbpr` | numeric |
| `fd_set_pcd` | text |
| `fd_wk1_ern_r` | numeric |
| `fd_yr1_ern_r` | numeric |
| `fd_yr2_ern_r` | numeric |
| `fd_yr3_ern_r` | numeric |
| `fd_yr5_ern_r` | numeric |
| `frc_bpr_itm_yn` | text |
| `fss_itm_no` | text |
| `han_clas_fee_type` | text |
| `han_clas_nm` | text |
| `han_clas_policies` | text |
| `han_clas_sales_channel` | text |
| `hdge_fd_yn` | text |
| `int_dvd_desc` | text |
| `itm_abrv_nm` | text |
| `itm_eabrv_nm` | text |
| `itm_eng_nm` | text |
| `itm_nm` | text |
| `itm_no` | text |
| `kofia_fd_ccd` | text |
| `ksd_itm_no` | text |
| `mtco_itm_no` | text |
| `ofsfd_yn` | text |
| `ofwk_trus_rwrd_r` | numeric |
| `or_attr_desc` | text |
| `or_co_rwrd_r` | numeric |
| `or_co_xtn_itt_cd` | text |
| `ovrs_fd_desc` | text |
| `pers_corp_desc` | text |
| `pfiv_sale_cntl_tcd` | text |
| `prfd_attr_cds` | text |
| `prfd_attr_cnt` | text |
| `prfd_attr_search_text` | text |
| `prvo_fd_desc` | text |
| `prvo_pbff_desc` | text |
| `rptt_ksd_itm_no` | text |
| `sale_co_rwrd_r` | numeric |
| `sale_yn` | text |
| `std_itm_no` | text |
| `thco_sale_yn` | text |
| `trusc_rwrd_r` | numeric |
| `trusc_xtn_itt_cd` | text |
| `zrin_attr_nms` | text |
| `zrin_btyp_cd` | text |
| `zrin_btyp_nm` | text |
| `zrin_dmst_bd_cmst_rt` | numeric |
| `zrin_dmst_stk_cmst_rt` | numeric |
| `zrin_etc_ast_cmst_rt` | numeric |
| `zrin_fd_cmst_rt` | numeric |
| `zrin_fd_ivst_risk_gcd` | text |
| `zrin_fd_ivst_risk_grd_nm` | text |
| `zrin_liqt_cmst_rt` | numeric |
| `zrin_ovrs_bd_cmst_rt` | numeric |
| `zrin_ovrs_stk_cmst_rt` | numeric |
| `zrin_pcd` | text |
| `zrin_ptn_nm` | text |

#### `raw.prbd01n001` (21,882행, 58열)

| 컬럼 | 타입 |
|---|---|
| `after_tax_yield` | double precision |
| `applied_yield` | double precision |
| `avg_annual_tax_yield` | double precision |
| `bdbns_abl_chnl_nm` | text |
| `bdbns_abl_chnl_tcd` | text |
| `bd_inrt_tcd` | text |
| `bd_intp_tcd` | text |
| `bd_knd` | text |
| `bd_ofr_tcd` | text |
| `bd_tisu_a` | numeric |
| `buyable_quantity` | double precision |
| `buy_yield` | double precision |
| `corp_after_tax_yield` | double precision |
| `corp_pretax_yield` | double precision |
| `cov` | double precision |
| `crd_grd` | text |
| `crd_grd_dt` | text |
| `curr_cd` | text |
| `depo_equiv_yield_154` | double precision |
| `depo_equiv_yield_495` | double precision |
| `dirty` | double precision |
| `dur` | double precision |
| `eval_price` | double precision |
| `exg_close_price` | double precision |
| `exg_close_price_base_dt` | text |
| `exg_close_yield` | double precision |
| `exrt_grte_ern_r` | numeric |
| `exrt_grte_ern_r_tcd` | text |
| `exrt_rpy_r` | numeric |
| `info_base_dt` | text |
| `info_seq` | bigint |
| `isu_bal_amt` | double precision |
| `isu_dt` | text |
| `mat_dt` | text |
| `ndy_applied_yield` | double precision |
| `ndy_cov` | double precision |
| `ndy_dirty` | double precision |
| `ndy_dur` | double precision |
| `ndy_eval_price` | double precision |
| `pd_abrv_eng_nm` | text |
| `pd_abrv_nm` | text |
| `pd_ctry_cd` | text |
| `pd_eng_nm` | text |
| `pd_exg_mkt` | text |
| `pd_nm` | text |
| `pd_no` | text |
| `pd_pbcm` | text |
| `pd_pen_tr_yn` | text |
| `pd_risk_gcd` | text |
| `pd_risk_nm` | text |
| `pd_std_info_update` | text |
| `pref_tax_yield` | double precision |
| `remaining_days` | double precision |
| `sale_yield_base_dt` | text |
| `srfc_irt` | double precision |
| `std_pd_mcls_nm` | text |
| `std_pd_scls_nm` | text |
| `trade_price` | double precision |

#### `raw.pref01n001` (1,780행, 98열)

| 컬럼 | 타입 |
|---|---|
| `cu_base_index` | text |
| `cu_charge_etc_rt` | text |
| `cu_charge_rt` | text |
| `cu_fund_mgmt_co` | text |
| `cu_lev_fector` | text |
| `cu_strtegy` | text |
| `cu_upt_dt` | text |
| `du_bpr` | numeric |
| `du_chas_errt` | numeric |
| `du_chas_errt_base_dt` | text |
| `du_clpr` | numeric |
| `du_diff_rt` | numeric |
| `du_diff_rt_base_dt` | text |
| `du_er_1d` | numeric |
| `du_er_1m` | numeric |
| `du_er_1y` | numeric |
| `du_er_3m` | numeric |
| `du_er_6m` | numeric |
| `du_er_ytd` | numeric |
| `du_hpr` | numeric |
| `du_last_aum` | numeric |
| `du_last_nav` | numeric |
| `du_lpr` | numeric |
| `du_nav_base_dt` | text |
| `du_nav_rnf_amt` | numeric |
| `du_nav_yday` | numeric |
| `du_upt_dt` | text |
| `du_val_1d` | numeric |
| `du_val_1m` | numeric |
| `du_val_5d` | numeric |
| `du_vlty_1m` | numeric |
| `du_vlty_1y` | numeric |
| `du_vlty_3m` | numeric |
| `du_vlty_6m` | numeric |
| `du_vlty_base_dt` | text |
| `du_vol_1d` | numeric |
| `du_vol_avg_1m` | numeric |
| `du_vol_avg_5d` | numeric |
| `fn_average_coupon` | numeric |
| `fn_average_maturity` | numeric |
| `fn_average_quality` | text |
| `fn_base_dt` | text |
| `fn_effective_duration` | numeric |
| `fn_effective_maturity` | numeric |
| `fn_modified_duration` | numeric |
| `fn_nominal_maturity` | numeric |
| `fn_portfolio_dt` | text |
| `pd_abrv_nm` | text |
| `pd_circ_net_tamt` | numeric |
| `pd_circ_stk_cnt` | numeric |
| `pd_curr_cd` | text |
| `pd_curr_nm` | text |
| `pd_divd_amt_ann` | numeric |
| `pd_divd_amt_pshr` | numeric |
| `pd_dvid_base_dt` | text |
| `pd_dvid_cycl` | text |
| `pd_dvid_inc_dist` | numeric |
| `pd_dvid_nav` | numeric |
| `pd_dvid_pay_cnt` | numeric |
| `pd_dvid_pay_months` | text |
| `pd_dvid_prc_base_dt` | text |
| `pd_dvid_tax_basis` | text |
| `pd_dvid_yield` | numeric |
| `pd_exg_mkt_cd` | text |
| `pd_exg_mkt_nm` | text |
| `pd_grp_no` | text |
| `pd_isin_cd` | text |
| `pd_itm_no` | text |
| `pd_itm_no_ma` | text |
| `pd_lst_stk_cnt` | numeric |
| `pd_lste_dt` | text |
| `pd_lstg_dt` | text |
| `pd_mkt_id` | text |
| `pd_mkt_nm` | text |
| `pd_net_tamt` | numeric |
| `pd_nm` | text |
| `pd_pen_risk_nm` | text |
| `pd_pen_tr_yn` | text |
| `pd_ric` | text |
| `pd_risk_cd` | text |
| `pd_risk_nm` | text |
| `pd_sale_yn` | text |
| `pd_sect_cd` | text |
| `pd_spac_yn` | text |
| `pd_stk_cnt` | numeric |
| `pd_ticker` | text |
| `pd_tr_yn` | text |
| `ref_ast_type` | text |
| `ref_base_dt` | text |
| `ref_base_index` | text |
| `ref_fund_mgmt_co` | text |
| `ref_geo_focus` | text |
| `ru_mkt_price` | numeric |
| `ru_mkt_volume` | numeric |
| `wu_core_yn` | text |
| `wu_inv_ast_type` | text |
| `wu_inv_rgn` | text |
| `wu_upt_dt` | text |

#### `raw.pref02n001` (6,037행, 49열)

| 컬럼 | 타입 |
|---|---|
| `cu_base_index` | text |
| `cu_charge_rt` | numeric |
| `cu_etn_yn` | text |
| `cu_fund_mgmt_co` | text |
| `cu_index_repl_mthd` | text |
| `cu_index_tracking_yn` | text |
| `cu_inverse_short_yn` | text |
| `cu_lev_fector` | numeric |
| `cu_strtegy` | text |
| `cu_upt_dt` | text |
| `du_base_dt_match_yn` | text |
| `du_bpr` | numeric |
| `du_clpr` | numeric |
| `du_clpr_base_dt` | text |
| `du_clpr_src` | text |
| `du_diff_rt` | numeric |
| `du_er_1d` | numeric |
| `du_hpr` | numeric |
| `du_last_aum` | numeric |
| `du_last_nav` | numeric |
| `du_lpr` | numeric |
| `du_nav_base_dt` | text |
| `du_opr` | numeric |
| `du_upt_dt` | text |
| `du_val_1d` | numeric |
| `du_vol_1d` | numeric |
| `pd_abrv_nm` | text |
| `pd_curr_cd` | text |
| `pd_exg_mkt_cd` | text |
| `pd_grp_no` | text |
| `pd_isin_cd` | text |
| `pd_itm_no` | text |
| `pd_itm_no_ma` | text |
| `pd_lipper_id` | text |
| `pd_lstg_dt` | text |
| `pd_lst_price` | numeric |
| `pd_lst_stk_cnt` | numeric |
| `pd_mkt_id` | text |
| `pd_nm` | text |
| `pd_sale_yn` | text |
| `pd_trd_ccy` | text |
| `pd_tr_yn` | text |
| `pd_us_cik` | text |
| `ru_mkt_price` | numeric |
| `ru_mkt_volume` | numeric |
| `wu_core_yn` | text |
| `wu_inv_ast_type` | text |
| `wu_inv_rgn` | text |
| `wu_upt_dt` | text |

#### `raw.prfd01n001` (23,676행, 75열)

| 컬럼 | 타입 |
|---|---|
| `bmrk_eng_nm` | text |
| `bmrk_nm` | text |
| `bns_bpr` | numeric |
| `curr_cd` | text |
| `exchdg_yn` | text |
| `fd_daily_bas_dt` | text |
| `fd_estb_ctry_cd` | text |
| `fd_ivst_rgn_desc` | text |
| `fd_last_dstb_actg_bss_dt` | text |
| `fd_last_dstb_actg_eot_dt` | text |
| `fd_last_dstb_r` | numeric |
| `fd_mm18_ern_r` | numeric |
| `fd_mm1_ern_r` | numeric |
| `fd_mm3_ern_r` | numeric |
| `fd_mm6_ern_r` | numeric |
| `fd_nast_suma` | numeric |
| `fd_price_bas_dt` | text |
| `fd_prsv_r` | numeric |
| `fd_sbpr` | numeric |
| `fd_set_pcd` | text |
| `fd_wk1_ern_r` | numeric |
| `fd_yr1_ern_r` | numeric |
| `fd_yr2_ern_r` | numeric |
| `fd_yr3_ern_r` | numeric |
| `fd_yr5_ern_r` | numeric |
| `frc_bpr_itm_yn` | text |
| `fss_itm_no` | text |
| `han_clas_fee_type` | text |
| `han_clas_nm` | text |
| `han_clas_policies` | text |
| `han_clas_sales_channel` | text |
| `hdge_fd_yn` | text |
| `int_dvd_desc` | text |
| `itm_abrv_nm` | text |
| `itm_eabrv_nm` | text |
| `itm_eng_nm` | text |
| `itm_nm` | text |
| `itm_no` | text |
| `kofia_fd_ccd` | text |
| `ksd_itm_no` | text |
| `mtco_itm_no` | text |
| `ofsfd_yn` | text |
| `ofwk_trus_rwrd_r` | numeric |
| `or_attr_desc` | text |
| `or_co_rwrd_r` | numeric |
| `or_co_xtn_itt_cd` | text |
| `ovrs_fd_desc` | text |
| `pers_corp_desc` | text |
| `pfiv_sale_cntl_tcd` | text |
| `prfd_attr_cds` | text |
| `prfd_attr_cnt` | text |
| `prfd_attr_search_text` | text |
| `prvo_fd_desc` | text |
| `prvo_pbff_desc` | text |
| `rptt_ksd_itm_no` | text |
| `sale_co_rwrd_r` | numeric |
| `sale_yn` | text |
| `std_itm_no` | text |
| `thco_sale_yn` | text |
| `trusc_rwrd_r` | numeric |
| `trusc_xtn_itt_cd` | text |
| `zrin_attr_nms` | text |
| `zrin_btyp_cd` | text |
| `zrin_btyp_nm` | text |
| `zrin_dmst_bd_cmst_rt` | numeric |
| `zrin_dmst_stk_cmst_rt` | numeric |
| `zrin_etc_ast_cmst_rt` | numeric |
| `zrin_fd_cmst_rt` | numeric |
| `zrin_fd_ivst_risk_gcd` | text |
| `zrin_fd_ivst_risk_grd_nm` | text |
| `zrin_liqt_cmst_rt` | numeric |
| `zrin_ovrs_bd_cmst_rt` | numeric |
| `zrin_ovrs_stk_cmst_rt` | numeric |
| `zrin_pcd` | text |
| `zrin_ptn_nm` | text |

#### `relations.company_subsidiary` (8,866행, 7열)

| 컬럼 | 타입 |
|---|---|
| `relation_id` | text |
| `parent_security_id` | text |
| `child_security_id` | text |
| `ownership_pct` | numeric |
| `as_of` | date |
| `source_document_id` | text |
| `source` | text |

#### `relations.etf_holding` (46,951행, 8열)

| 컬럼 | 타입 |
|---|---|
| `holding_id` | text |
| `product_id` | text |
| `security_id` | text |
| `weight` | numeric |
| `unit` | text |
| `as_of` | date |
| `source_document_id` | text |
| `source` | text |

#### `relations.etf_theme` (0행, 7열)

| 컬럼 | 타입 |
|---|---|
| `classification_id` | text |
| `product_id` | text |
| `classification_type` | text |
| `classification_value` | text |
| `as_of` | date |
| `source_document_id` | text |
| `source` | text |

#### `relations.product_classification` (61,744행, 7열)

| 컬럼 | 타입 |
|---|---|
| `classification_id` | text |
| `product_id` | text |
| `classification_type` | text |
| `classification_value` | text |
| `as_of` | date |
| `source_document_id` | text |
| `source` | text |

#### `relations.product_document` (711행, 3열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `document_id` | text |
| `relation_type` | text |

#### `relations.product_holding` (46,951행, 8열)

| 컬럼 | 타입 |
|---|---|
| `holding_id` | text |
| `product_id` | text |
| `security_id` | text |
| `weight` | numeric |
| `unit` | text |
| `as_of` | date |
| `source_document_id` | text |
| `source` | text |

#### `relations.source_document` (2,345행, 9열)

| 컬럼 | 타입 |
|---|---|
| `document_id` | text |
| `title` | text |
| `publisher` | text |
| `published_at` | date |
| `url` | text |
| `source_hash` | text |
| `source_type` | text |
| `as_of` | date |
| `ingested_at` | timestamp with time zone |

#### `vec.bond_schema_terms` (130행, 12열)

| 컬럼 | 타입 |
|---|---|
| `term_uri` | text |
| `label` | text |
| `comment` | text |
| `alt_labels` | ARRAY |
| `domain_file` | text |
| `property_type` | text |
| `content` | text |
| `content_hash` | text |
| `embedding_model` | text |
| `model_revision` | text |
| `embedding_dim` | smallint |
| `embedding` | USER-DEFINED |

#### `vec.chunk_embedding` (5,664행, 6열)

| 컬럼 | 타입 |
|---|---|
| `content_hash` | text |
| `embedding_text` | text |
| `embedding_model` | text |
| `model_revision` | text |
| `embedding_dim` | smallint |
| `embedding` | USER-DEFINED |

#### `vec.document_chunk` (9,055행, 14열)

| 컬럼 | 타입 |
|---|---|
| `chunk_id` | text |
| `document_id` | text |
| `section_type` | text |
| `chunk_ordinal` | integer |
| `heading_path` | text |
| `page_number` | integer |
| `citation_text` | text |
| `chunk_text` | text |
| `published_at` | date |
| `effective_as_of` | date |
| `source_url` | text |
| `content_hash` | text |
| `embedding_model` | text |
| `model_revision` | text |

#### `vec.document_product` (1,019행, 3열)

| 컬럼 | 타입 |
|---|---|
| `document_id` | text |
| `product_id` | text |
| `relation_type` | text |

#### `vec.product_coverage` (15,951행, 7열)

| 컬럼 | 타입 |
|---|---|
| `product_id` | text |
| `status` | text |
| `reason` | text |
| `as_of` | date |
| `source_run_id` | text |
| `document_id` | text |
| `source_route` | text |

#### `vec.schema_terms_all` (189행, 12열)

| 컬럼 | 타입 |
|---|---|
| `term_uri` | text |
| `label` | text |
| `comment` | text |
| `alt_labels` | ARRAY |
| `domain_file` | text |
| `property_type` | text |
| `content` | text |
| `content_hash` | text |
| `embedding_model` | text |
| `model_revision` | text |
| `embedding_dim` | smallint |
| `embedding` | USER-DEFINED |

#### `vec.source_document` (974행, 8열)

| 컬럼 | 타입 |
|---|---|
| `document_id` | text |
| `title` | text |
| `publisher` | text |
| `published_at` | date |
| `source_url` | text |
| `source_hash` | text |
| `source_type` | text |
| `as_of` | date |

#### `vec.vector_deploy_event` (7행, 5열)

| 컬럼 | 타입 |
|---|---|
| `event_id` | bigint |
| `run_id` | text |
| `event_type` | text |
| `details` | jsonb |
| `occurred_at` | timestamp with time zone |

#### `vec.vector_deploy_run` (1행, 15열)

| 컬럼 | 타입 |
|---|---|
| `run_id` | text |
| `manifest_sha256` | text |
| `release_id` | text |
| `model_id` | text |
| `model_revision` | text |
| `embedding_dim` | integer |
| `status` | text |
| `expected_counts` | jsonb |
| `observed_counts` | jsonb |
| `bundle_bytes` | bigint |
| `estimated_required_bytes` | bigint |
| `created_at` | timestamp with time zone |
| `updated_at` | timestamp with time zone |
| `cutover_at` | timestamp with time zone |
| `rollback_at` | timestamp with time zone |

#### `vec_prev_t108.bond_schema_terms` (0행, 11열)

| 컬럼 | 타입 |
|---|---|
| `term_uri` | text |
| `label` | text |
| `comment` | text |
| `alt_labels` | ARRAY |
| `domain_file` | text |
| `property_type` | text |
| `content` | text |
| `content_hash` | text |
| `embedding_model` | text |
| `embedding_dim` | smallint |
| `embedding` | USER-DEFINED |

#### `vec_prev_t108.doc_chunk` (0행, 12열)

| 컬럼 | 타입 |
|---|---|
| `chunk_id` | text |
| `document_id` | text |
| `product_id` | text |
| `page_number` | integer |
| `citation_text` | text |
| `chunk_text` | text |
| `published_at` | date |
| `source_url` | text |
| `content_hash` | text |
| `embedding_model` | text |
| `embedding_dim` | smallint |
| `embedding` | USER-DEFINED |

#### `vec_prev_t108.document_chunk` (0행, 12열)

| 컬럼 | 타입 |
|---|---|
| `chunk_id` | text |
| `document_id` | text |
| `product_id` | text |
| `page_number` | integer |
| `citation_text` | text |
| `chunk_text` | text |
| `published_at` | date |
| `source_url` | text |
| `content_hash` | text |
| `embedding_model` | text |
| `embedding_dim` | smallint |
| `embedding` | USER-DEFINED |

#### `vec_prev_t108.schema_index` (0행, 11열)

| 컬럼 | 타입 |
|---|---|
| `term_uri` | text |
| `label` | text |
| `comment` | text |
| `alt_labels` | ARRAY |
| `domain_file` | text |
| `property_type` | text |
| `content` | text |
| `content_hash` | text |
| `embedding_model` | text |
| `embedding_dim` | smallint |
| `embedding` | USER-DEFINED |

#### `vec_prev_t108.schema_terms_all` (0행, 11열)

| 컬럼 | 타입 |
|---|---|
| `term_uri` | text |
| `label` | text |
| `comment` | text |
| `alt_labels` | ARRAY |
| `domain_file` | text |
| `property_type` | text |
| `content` | text |
| `content_hash` | text |
| `embedding_model` | text |
| `embedding_dim` | smallint |
| `embedding` | USER-DEFINED |

## 3. 로컬 RDB 로직 스키마 (`src/tools/rdb_schema.py`)

RDB 검색 노드는 이 정의를 유일한 스키마 진실로 쓴다. 개념(한국어) → 컬럼 매핑은 ATTRIBUTE_CATALOG, 컬럼 설명은 RDB_SCHEMA, 하위유형 조건은 SUBTYPE_CONDITION_MAP, 실질 기준일은 DOMAIN_AS_OF다.

### 3.1 도메인 → 테이블 · 실질 기준일

| 도메인 | 테이블 | 실질 기준일 | 판매가능 정책 | 원격 행수 |
|---|---|---|---|---:|
| 채권 | `raw.prbd01n001` | 2026-08-21 | no_filter | 21,882 |
| 국내ETF | `raw.pref01n001` | 2026-08-22 | column_filter (pd_sale_yn = '1') | 1,780 |
| 해외ETF | `raw.pref02n001` | 2026-08-22 | no_filter | 6,037 |
| 펀드 | `raw.prfd01n001` | 2026-08-21 | column_filter (sale_yn = '판매중') | 23,676 |

### 3.2 도메인별 컬럼 정의 (RDB_SCHEMA) 와 카탈로그 개념 매핑

#### 채권 · `raw.prbd01n001` (58열 정의, 카탈로그 개념 31개)

| 컬럼 | 원격 타입 | 로컬 타입 | 카탈로그 개념(별칭 포함) | 설명(로컬) |
|---|---|---|---|---|
| `pd_no` | text | text | 상품코드 | 상품번호(채권 종목번호, 예: KR60143NEFC6). 결측 없음. 단 info_seq 때문에 한 종목이 여러 행일 수 있어 유일값이 아니다(21,882행 중  |
| `info_seq` | bigint | bigint | - | 동일 종목/시장/기준일 내 판매 LOT 구분 순번(1/2/3). 1이 21,574행, 2가 307행, 3이 1행. 종목 단위로 세려면 DISTINCT pd_no  |
| `info_base_dt` | text | text | - | 판매/민평 공통 기준일. 전 행이 20260821 단일값. |
| `pd_nm` | text | text | 상품명, ESG채권구분, 채권특수조건 | 상품명(채권명). 결측 없음. 발행사명과 회차가 붙은 형태(예: 경기주택도시공사24-10-83(지)). |
| `pd_abrv_nm` | text | text | - | 상품약어명. 뒤쪽에 공백 패딩이 붙어 있어 TRIM 비교를 권장. |
| `pd_eng_nm` | text | text | - | 상품영문명. |
| `pd_abrv_eng_nm` | text | text | - | 상품영문약어명. 공백 패딩 있음. |
| `pd_pbcm` | text | text | 발행기관, 발행사, 발행기관명, 발행사명, 발행회사 | 발행기관/발행자명(1,837종). 공백 패딩이 붙어 있어 TRIM 비교를 권장. 0.7% 결측. |
| `pd_ctry_cd` | text | text | - | 국가코드(종목번호 앞 2자리). 값은 KR/XS 두 가지. |
| `std_pd_mcls_nm` | text | text | 상품유형 | 상품중분류명. 값은 회사채(12,865)/특수채(6,177)/국공채(2,840) 세 가지뿐이다. 이전 배포본에 있던 개인투자용국채와 외화채권 분류는 이번 데이터에 |
| `std_pd_scls_nm` | text | text | 상품소분류 | 상품소분류명(13종: 일반사채 12,747, 공사채 4,208, 지역개발 1,679, 특수은행채 1,324, 은행채 703, 도시철도 452, 국고채 371, 국 |
| `bd_knd` | text | text | 채권종류 | 예탁원 기준 채권종류명(41종). 뒤쪽 공백 패딩이 있어 TRIM 비교를 권장. 0.7% 결측. |
| `bd_ofr_tcd` | text | text | 모집구분 | 모집구분. 값은 공모(19,875)/사모(2,007) 두 가지. 결측 없음. |
| `bd_inrt_tcd` | text | text | 금리구분 | 금리구분. 값은 고정금리(20,904)/변동금리(830)/고정+변동금리(148). 결측 없음. |
| `bd_intp_tcd` | text | text | 이자지급구분 | 이자지급구분. 값은 이표채(18,059)/복리채(2,867)/할인채(689)/단리채(267). 결측 없음. |
| `pd_exg_mkt` | text | text | 거래시장 | 거래구분. 값은 장내/장외 두 가지. 결측 없음. |
| `curr_cd` | text | text | 통화 | 통화코드. 21,881행이 KRW이고 '000'이라는 오류값이 1건 있다. 이번 배포본에는 USD/EUR/JPY 채권이 없다. |
| `crd_grd` | text | text | 신용등급 | 적용신용등급(15종: AAA 8,722 / AA- 3,530 / AA+ 2,543 / AA0 1,241 / A0 737 / A+ 678 / A- 124 / BBB |
| `crd_grd_dt` | text | text | - | 신용등급 적용일자(YYYYMMDD 숫자). 등급이 바뀌지 않으면 과거 일자로 유지될 수 있다. 18.3% 결측. |
| `pd_risk_gcd` | text | text | - | 상품위험등급 원문 코드(11~16 및 0). 11이 1등급, 16이 6등급이고 0은 '해당없음'(19건). 결측 없음. |
| `pd_risk_nm` | text | text | 위험등급 | 상품위험등급명(7종: 낮은위험(5등급) 9,849 / 매우낮은위험(6등급) 8,929 / 매우높은위험(1등급) 1,441 / 보통위험(4등급) 1,424 / 다소 |
| `isu_bal_amt` | double precision | double precision | 발행잔액 | 발행잔액(원). 결측 없음. |
| `bd_tisu_a` | numeric | numeric(26,8) | 총발행금액 | 총발행금액(원). 결측 없음. isu_bal_amt(잔액)와 다른 개념이다. |
| `isu_dt` | text | text | 발행일 | 발행일자. 문서 타입은 text지만 실제 값은 YYYYMMDD 숫자(예: 20251223.0). 결측 없음. |
| `mat_dt` | text | text | 만기일 | 상환일자(영구채는 1차 콜행사개시일). 문서 타입은 text지만 실제 값은 YYYYMMDD 숫자. 결측 없음. |
| `remaining_days` | double precision | double precision | 잔존기간 | 잔존일수(일 단위, 이미 계산되어 있음). 결측 없음(이전 배포본은 25.1% 결측이었다). mat_dt로 다시 계산할 필요 없다. |
| `pd_std_info_update` | text | text | - | 민평정보 기준일/최근 업데이트 일자. 전 행이 20260821 단일값. |
| `srfc_irt` | double precision | double precision | 표면금리 | 표면이자율/쿠폰금리(%). 결측 없음. |
| `applied_yield` | double precision | double precision | 민평수익률 | 민평수익률/민평금리(%). 결측 없음. 이 도메인에서 가장 신뢰할 만한 수익률 컬럼이다. |
| `ndy_applied_yield` | double precision | double precision | - | 익일 민평수익률/민평금리(%). 0.1% 결측. |
| `exg_close_yield` | double precision | double precision | - | 장내 종가수익률(%). 18.9% 결측이고 값이 있는 행 중에도 0.0이 다수다. |
| `exrt_grte_ern_r` | numeric | numeric(20,12) | - | 만기보장수익률. 19종뿐이고 대부분 0.0이라 사실상 특수 목적 컬럼이다. |
| `exrt_grte_ern_r_tcd` | text | text | - | 만기보장수익률구분코드(99가 21,338건으로 대부분, 나머지 1~5가 소수). |
| `exrt_rpy_r` | numeric | numeric(20,12) | - | 만기상환율(%). 대부분 100.0. |
| `buy_yield` | double precision | double precision | 매수수익률 | 매수수익률/매수금리(%). 97.1% 결측(634행에만 값 존재). 정렬/필터에 쓰면 대부분의 종목이 탈락한다. |
| `buyable_quantity` | double precision | double precision | - | 매수가능수량. 97.1% 결측. 주최측이 이 컬럼 값은 무효라고 공지했으므로 '판매 가능' 판단에 절대 쓰지 않는다(DOMAIN_SALE_POLICY 참고). |
| `trade_price` | double precision | double precision | - | 매매단가(표준투입단가). 97.1% 결측. |
| `sale_yield_base_dt` | text | text | - | 판매수익률 기준일. 97.1% 결측이고 값이 있는 행은 전부 20260821. |
| `bdbns_abl_chnl_nm` | text | text | - | 채권매매가능채널구분명. 97.1% 결측이고 값이 있는 행은 전부 '온오프 겸용' 단일값이라 변별력이 없다. |
| `bdbns_abl_chnl_tcd` | text | text | - | 채권매매가능채널구분코드. 97.1% 결측, 값은 0.0 단일값. |
| `after_tax_yield` | double precision | double precision | - | 개인 세후 운용수익률(%). 97.1% 결측. |
| `corp_pretax_yield` | double precision | double precision | - | 법인 세전 투자수익률(%). 97.1% 결측. |
| `corp_after_tax_yield` | double precision | double precision | - | 법인 세후 투자수익률(%). 97.1% 결측. |
| `pref_tax_yield` | double precision | double precision | - | 세금우대 세후 운용수익률(%). 97.1% 결측. |
| `avg_annual_tax_yield` | double precision | double precision | - | 세후 연평균수익률(%). 97.1% 결측이고 값이 있는 행 전부 0.0이라 사실상 미사용. |
| `depo_equiv_yield_154` | double precision | double precision | - | 예금환산수익률(세율 15.4% 기준). 97.1% 결측. |
| `depo_equiv_yield_495` | double precision | double precision | - | 은행환산수익률(세율 49.5% 기준). 97.1% 결측. |
| `eval_price` | double precision | double precision | 평가가격 | 평가일단가(Clean Price 성격). 결측 없음. |
| `dirty` | double precision | double precision | - | 이자부단가(Dirty Price). 0.1% 결측. |
| `dur` | double precision | double precision | 듀레이션 | 듀레이션(년). 0.1% 결측(이전 배포본은 31.6% 결측이었다). |
| `cov` | double precision | double precision | 컨벡시티 | 컨벡시티. 0.1% 결측. |
| `ndy_eval_price` | double precision | double precision | - | 익일 평가일단가. 0.1% 결측. |
| `ndy_dirty` | double precision | double precision | - | 익일 이자부단가. 0.1% 결측. |
| `ndy_dur` | double precision | double precision | - | 익일 듀레이션. 0.1% 결측. |
| `ndy_cov` | double precision | double precision | - | 익일 컨벡시티. 0.1% 결측. |
| `exg_close_price` | double precision | double precision | - | 장내 채권종가. 18.9% 결측이고 값이 있는 행에도 0.0이 다수 섞여 있다. |
| `exg_close_price_base_dt` | text | text | - | 장내 채권종가/종가수익률 기준일(YYYYMMDD 문자열). 19.0% 결측이고 공백 문자열이 섞여 있다. |
| `pd_pen_tr_yn` | text | text | 퇴직연금편입가능여부 | 퇴직연금 편입 가능 여부. 값은 N(19,951)/Y(1,931). 결측 없음. |

하위유형(subtype) 조건 90개가 쓰는 컬럼: `std_pd_mcls_nm`(3개: 국공채→eq 국공채, 특수채→eq 특수채, 회사채→eq 회사채); `std_pd_scls_nm`(12개: 공모지방채→eq 공모지방채, 공사채→eq 공사채, 국고채→eq 국고채, 국민주택→eq 국민주택…); `bd_knd`(33개: 특수은행채→eq 특수은행채, Conduit회사채→eq Conduit회사채, MBS→eq MBS, 국고채권→eq 국고채권…); `bd_inrt_tcd`(4개: 고정금리→eq 고정금리, 변동금리→eq 변동금리, 고정변동금리→eq 고정+변동금리, 혼합형금리→eq 고정+변동금리); `bd_intp_tcd`(4개: 단리채→eq 단리채, 복리채→eq 복리채, 이표채→eq 이표채, 할인채→eq 할인채); `pd_exg_mkt`(6개: 장내→eq 장내, 장내거래→eq 장내, 장내채권→eq 장내, 장외→eq 장외…); `curr_cd`(3개: 원화채권→eq KRW, 원화→eq KRW, KRW채권→eq KRW); `bd_ofr_tcd`(6개: 공모→eq 공모, 공모발행→eq 공모, 공모채권→eq 공모, 사모→eq 사모…); `pd_nm`(19개: 녹색채권→contains (녹), 사회적채권→contains (사), 지속가능채권→contains (지), ESG채권→contains (녹)…)

#### 국내ETF · `raw.pref01n001` (98열 정의, 카탈로그 개념 43개)

| 컬럼 | 원격 타입 | 로컬 타입 | 카탈로그 개념(별칭 포함) | 설명(로컬) |
|---|---|---|---|---|
| `pd_itm_no` | text | text | 상품코드 | 상품번호(ISIN, 예: KR70000Z0003). 1,780건 전부 유일값. 결측 없음. |
| `pd_itm_no_ma` | text | text | - | 상품번호(미래에셋 단축코드, 예: A0000Z0). 전부 유일값. |
| `pd_isin_cd` | text | text | - | Refinitiv ISIN. 32.1% 결측(ref_ 계열과 같은 결측 패턴). |
| `pd_ric` | text | text | - | Refinitiv RIC(예: 0000Z0.KS). 32.1% 결측. |
| `pd_ticker` | text | text | - | Refinitiv 티커. 32.1% 결측. |
| `pd_nm` | text | text | 상품명 | 상품명(정식). 결측 없음. 반도체/2차전지 같은 테마 키워드는 별도 섹터 컬럼이 아니라 이 텍스트 안에만 들어 있다. |
| `pd_abrv_nm` | text | text | - | 상품약어명(예: RISE 바이오TOP10액티브). |
| `pd_grp_no` | text | text | 상품군 | 상품군종류. 값은 ETF(1,235)/ETN(545) 두 가지. 이 테이블은 ETF만 있는 게 아니다. |
| `cu_fund_mgmt_co` | text | text | 운용사 | 운용사(100종, 예: KB/삼성/iM에셋). 결측 없음. |
| `cu_base_index` | text | text | - | 기초지수. 7.1% 결측이고 값이 있는 행에도 공백 문자열이 섞여 있다. nunique가 20뿐이라 대부분 공백 계열로 보인다. |
| `cu_strtegy` | text | text | 운용전략 | 운용전략. 실물복제(763)/액티브(358)/합성복제(82)가 정상 값이고, 'C'라는 코드성 오류값이 422건 섞여 있다. 8.7% 결측. |
| `cu_lev_fector` | text | text | 레버리지배수 | 레버리지 배수(1.0/1.5/2.0/-1.0/-2.0 등 7종). 음수가 인버스 상품이다. 10.2% 결측. |
| `cu_charge_rt` | text | double precision | - | 총보수요율(%). 87.8% 결측이라 실사용률이 매우 낮다. |
| `cu_charge_etc_rt` | text | double precision | - | 기타비용요율(%). 87.8% 결측이고 값이 있는 행 전부 0.0. |
| `wu_inv_ast_type` | text | text | 투자자산유형 | 투자자산군(9종: 주식 1,015 / 채권 221 / 원자재 211 / 대체투자 132 / 혼합자산 86 / 단기자금 45 / 기타 37 / 통화 29 / 부동산 |
| `wu_inv_rgn` | text | text | 투자지역 | 투자지역(11종: 국내 1,069 / 미국 466 / 글로벌 76 / 중국 63 / 아시아 33 / 일본 25 / 인도 19 / 남미북미 12 / 유럽 7 / 이 |
| `pd_sect_cd` | text | text | - | ETF 섹터코드. 값이 2.0/3.0/4.0/8.0/9.0 숫자뿐이고 이름으로 매핑해 줄 컬럼이 이 테이블에 없다. 이전 배포본에 있던 pd_sect_nm(섹터명 |
| `ref_ast_type` | text | text | - | Refinitiv 자산유형(영문 7종: Equity/Bond/Alternatives/Mixed Assets/Money Market/Commodity/Other). |
| `ref_geo_focus` | text | text | - | Refinitiv 투자지역(영문 23종, 예: Korea/United States of America/Global). 32.1% 결측. wu_inv_rgn의 영문 |
| `ref_base_index` | text | text | 기초지수 | Refinitiv 벤치마크명(905종). 32.1% 결측. cu_base_index보다 채움률과 다양성이 훨씬 낫다. |
| `ref_fund_mgmt_co` | text | text | - | Refinitiv 운용사(영문 29종). 32.1% 결측. |
| `ref_base_dt` | text | double precision | - | Refinitiv 기준일. 값이 있는 행 전부 20260822. |
| `pd_risk_cd` | text | text | - | 상품등급코드(PD_RISK_GCD_11~PD_RISK_GCD_16, 마지막 두 자리가 1~6등급). 결측 없음. |
| `pd_risk_nm` | text | text | 위험등급 | 상품등급명(6종: 매우높은위험(1등급) 775 / 높은위험(2등급) 691 / 낮은위험(5등급) 117 / 보통위험(4등급) 91 / 다소높은위험(3등급) 85  |
| `pd_sale_yn` | text | text | 판매가능여부, 판매상태, 판매여부, 판매중, 판매가능 | 상품판매여부. 문서 타입은 text지만 실제 값은 정수 1(1,534건)/0(246건)이고 Y/N 문자열이 아니다. 0인 246건 중 245건이 pd_lste_d |
| `pd_lste_dt` | text | text | 거래종료일 | 상품거래종료일자(YYYYMMDD 숫자). 1,535건이 99991231(종료 예정 없음)이고 242건만 실제 종료일이 잡혀 있다. |
| `pd_lstg_dt` | text | text | 상장일 | 상품거래가능일자(상장일, YYYYMMDD 숫자). 0.2% 결측. |
| `pd_tr_yn` | text | double precision | 거래정지여부, 거래정지, 거래정지상태 | 상품거래정지여부. 0.0(정상 1,695건)/1.0(정지 82건). |
| `pd_pen_tr_yn` | text | text | 연금거래가능여부, 연금거래가능, 연금거래여부, 연금거래 | 연금거래가능여부(Y/N). 결측 없음. |
| `pd_pen_risk_nm` | text | text | - | 연금거래위험구분. 값은 위험자산/안전자산/N 세 가지. 결측 없음. |
| `wu_core_yn` | text | text | - | 핵심ETF여부(Y/N). 결측 없음. |
| `pd_spac_yn` | text | text | - | SPAC 여부. 값이 있는 행 전부 'N'이라 변별력 없음. 10.2% 결측. |
| `pd_net_tamt` | numeric | double precision | 순자산, AUM, 순자산총액 | 순자산총액(원). 10.2% 결측. 이 도메인의 '순자산' 기본 컬럼이다. |
| `du_last_aum` | numeric | double precision | - | 최종 AUM(원). 10.2% 결측. pd_net_tamt와 유사 계열이나 값이 미세하게 다르다. |
| `pd_circ_net_tamt` | numeric | double precision | - | 유통순자산총액(원). 10.2% 결측. |
| `pd_lst_stk_cnt` | numeric | bigint | - | 상품상장주식수. 결측 없음. |
| `pd_stk_cnt` | numeric | double precision | - | 상장주식수. 10.2% 결측. |
| `pd_circ_stk_cnt` | numeric | double precision | - | 유통주식수. 10.2% 결측. |
| `du_last_nav` | numeric | double precision | - | 최종 NAV(주당 순자산가치). 10.2% 결측. |
| `du_nav_yday` | numeric | double precision | - | 전일 NAV. 10.2% 결측. |
| `du_nav_rnf_amt` | numeric | double precision | - | 전일 대비 NAV 등락금액. 10.2% 결측. |
| `du_nav_base_dt` | text | double precision | - | NAV 기준일(YYYYMMDD). 10.2% 결측. |
| `du_bpr` | numeric | double precision | - | 기준가. 0.2% 결측. |
| `du_clpr` | numeric | double precision | 종가 | 종가. 0.2% 결측. |
| `du_hpr` | numeric | double precision | - | 고가. 0.2% 결측. |
| `du_lpr` | numeric | double precision | - | 시가(스키마 코멘트는 '시가'지만 컬럼명은 low price 계열이라 저가일 가능성이 있다). 0.2% 결측. |
| `ru_mkt_price` | numeric | double precision | - | 현재가. du_clpr와 값이 같다. 0.2% 결측. |
| `ru_mkt_volume` | numeric | double precision | - | 거래량. du_vol_1d와 값이 같다. 0.2% 결측. |
| `du_er_1d` | numeric | double precision | - | 1일 수익률(%). 11.0% 결측. |
| `du_er_1m` | numeric | double precision | 1개월수익률 | 1개월 수익률(%). 11.0% 결측. |
| `du_er_3m` | numeric | double precision | 3개월수익률 | 3개월 수익률(%). 12.8% 결측. |
| `du_er_6m` | numeric | double precision | 6개월수익률 | 6개월 수익률(%). 16.5% 결측. |
| `du_er_1y` | numeric | double precision | 1년수익률 | 1년 수익률(%). 20.4% 결측. |
| `du_er_ytd` | numeric | double precision | 연초대비수익률 | 연초 대비 수익률(%). 17.0% 결측. |
| `du_vlty_1m` | numeric | double precision | - | 최근 20거래일 연환산 변동성(%). 5.8% 결측. 이전 배포본에 없던 컬럼이다. |
| `du_vlty_3m` | numeric | double precision | - | 최근 60거래일 연환산 변동성(%). 10.4% 결측. |
| `du_vlty_6m` | numeric | double precision | - | 최근 120거래일 연환산 변동성(%). 16.5% 결측. |
| `du_vlty_1y` | numeric | double precision | 변동성 | 최근 252거래일 연환산 변동성(%). 26.5% 결측. |
| `du_vlty_base_dt` | text | double precision | - | 변동성 산출 기준일(YYYYMMDD). 4.8% 결측. |
| `du_chas_errt` | numeric | double precision | 추적오차율 | 추적오차율(%). 10.2% 결측. 이전 배포본은 전부 0.0이었으나 이번에는 497종의 실제 값이 들어 있다. |
| `du_chas_errt_base_dt` | text | double precision | - | 추적오차율 기준일. 10.2% 결측. |
| `du_diff_rt` | numeric | double precision | 괴리율 | 괴리율(%). 10.2% 결측. 이전 배포본은 전부 0.0이었으나 이번에는 303종의 실제 값이 들어 있다. |
| `du_diff_rt_base_dt` | text | double precision | - | 괴리율 기준일. 10.2% 결측. |
| `du_val_1d` | numeric | double precision | 거래대금 | 일거래대금(원). 0.2% 결측. |
| `du_val_5d` | numeric | double precision | - | 5일 평균 일거래대금(원). 0.3% 결측. |
| `du_val_1m` | numeric | double precision | - | 1개월 평균 일거래대금(원). 0.9% 결측. |
| `du_vol_1d` | numeric | double precision | 거래량 | 일거래량(주). 0.2% 결측. |
| `du_vol_avg_5d` | numeric | double precision | - | 5일 평균 거래량(주). 0.3% 결측. |
| `du_vol_avg_1m` | numeric | double precision | - | 1개월 평균 거래량(주). 0.8% 결측. |
| `pd_dvid_cycl` | text | text | 분배주기 | 분배주기(Q 698 / A 306 / M 196 / S 8, 공백 422). 8.4% 결측. |
| `pd_dvid_yield` | numeric | double precision | 분배수익률 | 연환산 분배수익률(%). 32.1% 결측. 이전 배포본은 전부 0.0이었으나 이번에는 실제 값이 들어 있다. |
| `pd_divd_amt_pshr` | numeric | double precision | - | 주당 분배금(원천 우선, 없으면 회당 추정). 32.1% 결측. |
| `pd_divd_amt_ann` | numeric | double precision | - | 연간 추정 분배금. 53.4% 결측. |
| `pd_dvid_pay_cnt` | numeric | double precision | - | 연간 지급횟수(1/2/4/12). 32.1% 결측. |
| `pd_dvid_pay_months` | text | text | - | 분배 지급월(영문 월 이름을 쉼표로 나열, 예: January,April,July,October). 32.1% 결측. |
| `pd_dvid_nav` | numeric | double precision | - | 분배금 계산 기준 NAV. 32.1% 결측. |
| `pd_dvid_prc_base_dt` | text | double precision | - | 분배금 계산 NAV 기준일. 32.1% 결측. |
| `pd_dvid_base_dt` | text | double precision | - | 분배정보 기준일. 값이 있는 행 전부 20260822. |
| `pd_dvid_tax_basis` | text | text | - | 분배 과세기준. 값이 있는 행 전부 'Gross' 단일값. |
| `pd_dvid_inc_dist` | numeric | text | - | 원천 성과배분/분배금. 1,780건 전부 NULL이라 사실상 미사용 컬럼. |
| `fn_average_coupon` | numeric | double precision | - | 평균쿠폰이자율(%). 88.8% 결측(채권형 ETF에만 값이 있음). |
| `fn_average_quality` | text | double precision | - | 평균신용품질(숫자 스코어). 95.8% 결측. |
| `fn_effective_maturity` | numeric | double precision | - | 실질만기(년). 87.9% 결측. |
| `fn_nominal_maturity` | numeric | double precision | - | 명목만기(년). 87.9% 결측. fn_effective_maturity와 값이 같다. |
| `fn_average_maturity` | numeric | double precision | - | 평균잔존만기. 1,780건 전부 NULL이라 사실상 미사용 컬럼. |
| `fn_effective_duration` | numeric | double precision | - | 듀레이션. 1,780건 전부 NULL이라 사실상 미사용 컬럼. |
| `fn_modified_duration` | numeric | double precision | - | 수정듀레이션. 1,780건 전부 NULL이라 사실상 미사용 컬럼. |
| `fn_base_dt` | text | double precision | - | 펀더멘털 기준일. 값이 있는 행 전부 20260822. |
| `fn_portfolio_dt` | text | double precision | - | 포트폴리오 기준일(17종). 37.2% 결측. |
| `pd_curr_cd` | text | text | - | 상품통화코드. 값은 CURR_CD_KRW / CURR_CD_000 두 가지(원시 ISO 코드가 아니라 접두어가 붙은 형태). |
| `pd_curr_nm` | text | text | - | 상품통화명(한국원화/해당없음). |
| `pd_exg_mkt_cd` | text | text | - | 거래소코드. 전 행 EXG_MKT_NO_001 단일값. |
| `pd_exg_mkt_nm` | text | text | - | 거래소명. 전 행 '유가증권' 단일값(공백 패딩 있음). |
| `pd_mkt_id` | text | text | - | 상품거래시장코드. 전 행 STK 단일값. |
| `pd_mkt_nm` | text | text | - | 상품거래시장명. 사실상 '유가증권' 단일값(공백 패딩 있음). |
| `cu_upt_dt` | text | double precision | - | 변동갱신일자(YYYYMMDD). 최신값 20260824. 10.2% 결측. |
| `du_upt_dt` | text | double precision | - | 일간갱신일자(YYYYMMDD). 최신값 20260821. 10.2% 결측. |
| `wu_upt_dt` | text | double precision | - | 주간갱신일자. 값이 있는 행 전부 20260821. |

하위유형(subtype) 조건 14개가 쓰는 컬럼: `cu_strtegy`(3개: 실물복제→eq 실물복제, 합성복제→eq 합성복제, 액티브→eq 액티브); `cu_lev_fector`(2개: 레버리지→> 1, 인버스→< 0); `wu_inv_ast_type`(9개: 주식형→eq 주식, 주식 ETF→eq 주식, 주식ETF→eq 주식, 채권형→eq 채권…)

#### 해외ETF · `raw.pref02n001` (49열 정의, 카탈로그 개념 25개)

| 컬럼 | 원격 타입 | 로컬 타입 | 카탈로그 개념(별칭 포함) | 설명(로컬) |
|---|---|---|---|---|
| `pd_itm_no` | text | text | 상품코드 | 해외 ETF RIC(예: AAUA.K). 6,037건 전부 유일값. 결측 없음. |
| `pd_itm_no_ma` | text | text | - | 해외 ETF RIC(PDF 조인키). pd_itm_no와 값이 같다. |
| `pd_isin_cd` | text | text | - | ISIN 코드(예: US02072Q2755). 0.2% 결측. |
| `pd_abrv_nm` | text | text | 티커 | 상품약어명(티커, 예: AAUA). 결측 없음. 질문에서 VOO, QQQ처럼 티커로 부르면 이 컬럼으로 찾는다. |
| `pd_nm` | text | text | 상품명 | 상품명(영문 정식명). 결측 없음. |
| `pd_lipper_id` | text | text | - | Lipper 펀드코드. 0.2% 결측. |
| `pd_us_cik` | text | text | - | 미국 SEC CIK 번호(389종). 0.3% 결측. |
| `pd_grp_no` | text | text | 상품군 | 상품군종류. 값은 ETF(5,972)/ETN(65) 두 가지. |
| `cu_fund_mgmt_co` | text | text | 운용사 | 운용사(영문 382종). 0.2% 결측. |
| `cu_base_index` | text | text | 기초지수 | 기초지수(영문 1,850종). 0.2% 결측. 지수를 제공하지 않는 액티브 상품은 'Index is not provided by Management Company |
| `cu_strtegy` | text | text | 운용전략 | 운용전략(영문 자유서술 문장, 5,943종). 0.2% 결측. narrative 질문(운용 목표 설명 등)에 Vector 없이 RDB 텍스트로 바로 답할 수 있는 |
| `cu_index_repl_mthd` | text | text | 복제방법, 복제방식 | 인덱스 복제방법(Full/Optimized/Swap 등 4종). 60.1% 결측. |
| `cu_index_tracking_yn` | text | text | - | 인덱스 추적 여부. 값이 있는 행 전부 'Y'. 60.1% 결측. |
| `cu_inverse_short_yn` | text | text | - | 인버스 또는 숏 여부. 값이 있는 행 전부 'Y'이고 97.0% 결측이라, 결측이 곧 '인버스 아님'을 뜻한다. |
| `cu_etn_yn` | text | text | - | ETN 여부. 값이 있는 행 전부 'Y'이고 98.9% 결측. pd_grp_no로 판단하는 편이 낫다. |
| `cu_lev_fector` | numeric | text | 레버리지배수 | 레버리지 배수(2.0/-2.0/3.0 등 11종). 85.1% 결측이라 결측이 곧 배수 1배를 뜻한다. |
| `cu_charge_rt` | numeric | double precision | 총보수율, 총보수, 보수 | 연간보수율(%). 결측 없음. 국내ETF의 cu_charge_rt(87.8% 결측)와 달리 이 도메인은 전부 채워져 있다. |
| `wu_inv_ast_type` | text | text | 투자자산유형 | 투자자산군(영문 6종: Equity/Alternatives/Bond/Mixed Assets/Commodity/Money Market). 0.2% 결측. |
| `wu_inv_rgn` | text | text | 투자지역 | 투자지역(영문 59종, 예: United States of America/Global/Global Ex US). 국내ETF보다 훨씬 세분화되어 있어 '아시아' 같 |
| `wu_core_yn` | text | text | - | 핵심 ETF 여부. 값이 있는 행 전부 'N'이고 98.2% 결측이라 변별력이 없다. |
| `du_last_aum` | numeric | double precision | 순자산, AUM, 순자산총액 | 일간 순자산총액(거래통화 기준, 대부분 USD). 3.4% 결측. 이 도메인의 '순자산' 컬럼이다. |
| `du_last_nav` | numeric | double precision | - | 추정 주당 NAV. 87.4% 결측이라 실사용률이 낮다. |
| `pd_lst_stk_cnt` | numeric | double precision | 상장주식수 | 상장주식수. 결측 없음. |
| `pd_lst_price` | numeric | double precision | - | 액면가. 값이 0.0 아니면 0.01뿐이라 사실상 미사용. |
| `du_bpr` | numeric | double precision | - | 기준가. 0.2% 결측. |
| `du_clpr` | numeric | double precision | 종가 | 종가. 0.2% 결측. |
| `du_opr` | numeric | double precision | - | 시가. 0.2% 결측. |
| `du_hpr` | numeric | double precision | - | 고가. 0.2% 결측. |
| `du_lpr` | numeric | double precision | - | 저가. 0.2% 결측. |
| `ru_mkt_price` | numeric | double precision | - | 실시간 현재가. du_clpr와 값이 같다. |
| `ru_mkt_volume` | numeric | double precision | - | 실시간 거래량. du_vol_1d와 값이 같다. |
| `du_val_1d` | numeric | double precision | 거래대금 | 외화 거래대금. 0.2% 결측. |
| `du_vol_1d` | numeric | double precision | 거래량 | 거래량. 0.2% 결측. |
| `du_er_1d` | numeric | double precision | 1일수익률 | 1일 수익률(%). 0.2% 결측. 이 도메인에는 1개월/1년 같은 장기 수익률 컬럼이 없다. |
| `du_diff_rt` | numeric | double precision | - | 종가 대비 추정 NAV 괴리율(%). 6,037건 중 3건에만 값이 있어 사실상 미사용 컬럼. |
| `pd_exg_mkt_cd` | text | text | 상장거래소 | 거래소코드(AMX/NAS/NYS 위주, 정체 불명 코드 101/102가 소수). 이 값 자체가 '해외 상장'이라는 도메인 분류의 근거이기도 하다. 결측 없음. |
| `pd_mkt_id` | text | text | - | 거래소국가코드. 전 행 US 단일값. |
| `pd_curr_cd` | text | text | - | 펀드통화코드. USD가 대부분이고 INR이 소수. 0.2% 결측. |
| `pd_trd_ccy` | text | text | - | 거래통화코드. 전 행 USD 단일값. |
| `pd_sale_yn` | text | text | - | 판매여부. 값이 있는 행 전부 1.0 단일값이라 변별력이 없다(DOMAIN_SALE_POLICY 참고). |
| `pd_tr_yn` | text | text | - | 거래정지여부. 값이 있는 행 전부 0.0 단일값이라 변별력이 없다. |
| `pd_lstg_dt` | text | text | 설정일 | 설정일(YYYYMMDD 숫자, 예: 20070223). 결측 없음. |
| `du_clpr_base_dt` | text | double precision | - | 선택된 종가의 원천 기준일(109종). 최신값 20260821이지만 과거 일자가 섞여 있어 종목마다 종가 기준일이 다르다. |
| `du_clpr_src` | text | text | - | 선택된 종가 원천 컬럼 식별자. 전 행 'pd65n101.tday_clpr' 단일값. |
| `du_base_dt_match_yn` | text | text | - | NAV/종가 기준일 일치 여부. 값이 있는 행 전부 'N'이라, NAV 기준일과 종가 기준일이 다른 것이 정상 상태다. |
| `du_nav_base_dt` | text | text | - | NAV 원천 기준일. 전 행 20260822 단일값. |
| `du_upt_dt` | text | text | - | 일간갱신일자(108종). 최신값 20260822. |
| `cu_upt_dt` | text | text | - | 변동갱신일자. 전 행 20260822 단일값. |
| `wu_upt_dt` | text | text | - | 주간갱신일자. 전 행 20260822 단일값. |

하위유형(subtype) 조건 12개가 쓰는 컬럼: `cu_lev_fector`(2개: 레버리지→> 1, 인버스→< 0); `wu_inv_ast_type`(10개: 주식형→eq Equity, 주식 ETF→eq Equity, 주식ETF→eq Equity, 채권형→eq Bond…)

#### 펀드 · `raw.prfd01n001` (75열 정의, 카탈로그 개념 37개)

| 컬럼 | 원격 타입 | 로컬 타입 | 카탈로그 개념(별칭 포함) | 설명(로컬) |
|---|---|---|---|---|
| `itm_no` | text | text | 상품코드 | 종목번호(ISIN, 예: KR5010101611). 23,676건 전부 유일값. 결측 없음. |
| `itm_nm` | text | text | 상품명 | 종목명(정식). 결측 없음. |
| `itm_abrv_nm` | text | text | - | 종목약어명. 결측 없음. |
| `itm_eng_nm` | text | text | - | 종목영문명. 결측 없음. |
| `itm_eabrv_nm` | text | text | - | 종목영문약어명. 99.4% 결측이라 실사용률이 매우 낮다. |
| `std_itm_no` | text | text | - | 표준종목번호(ISIN). 2.2% 결측이고 공백 문자열이 섞여 있다. |
| `fss_itm_no` | text | text | - | 금융감독원 종목번호. 0.2% 결측. |
| `ksd_itm_no` | text | text | - | 예탁원 종목번호. 2.5% 결측, 공백 문자열 섞임. |
| `rptt_ksd_itm_no` | text | text | - | 대표 예탁원 종목번호. 같은 모펀드의 여러 클래스를 묶는 키로 쓸 수 있다. 0.5% 결측. |
| `mtco_itm_no` | text | text | - | 운용사 종목번호. 0.5% 결측. |
| `kofia_fd_ccd` | text | text | - | 금융투자협회 펀드분류코드(6,765종). 0.2% 결측. |
| `or_attr_desc` | text | text | 펀드유형 | 운용속성구분(14종: 주식형 5,231 / 채권형 4,472 / 재간접 3,652 / 채권혼합 2,989 / 파생상품 2,302 / 혼합자산 1,272 / 해당없 |
| `prvo_pbff_desc` | text | text | 공모사모구분 | 사모/공모 구분. 공모 14,716 / 사모 8,960. 결측 없음. 이전 배포본(사모 102건)과 달리 사모 비중이 38%라 공모펀드만 대상으로 하려면 이 조건 |
| `prvo_fd_desc` | text | text | - | 사모펀드 세부구분(해당없음/일반사모/일반사모(2015년전) 4종). 결측 없음. |
| `fd_ivst_rgn_desc` | text | text | 투자지역 | 펀드투자지역(9종: 국내 11,300 / 글로벌 5,925 / 해당없음 3,678 / 아시아 1,290 / 남미북미 815 / 유럽 329 / 이머징브릭스 283 |
| `ovrs_fd_desc` | text | text | 해외국내구분 | 해외펀드구분(국내 14,912 / 해외 6,961 / 국내외혼합 1,687 / 해당없음 116). fd_ivst_rgn_desc와 다른 축으로, 펀드 자체가 어디 |
| `fd_estb_ctry_cd` | text | text | - | 펀드설립국가코드(0/410/442 등 숫자 코드 7종). 이름 매핑 컬럼은 이 테이블에 없다. |
| `int_dvd_desc` | text | text | 이자배당구분 | 이자배당구분(배당 20,520 / 이자 2,809 / 해당없음 347). 결측 없음. |
| `pers_corp_desc` | text | text | - | 개인법인구분(해당없음/개인/법인). 결측 없음. |
| `hdge_fd_yn` | text | text | - | 헤지펀드 여부(0/1). 결측 없음. |
| `ofsfd_yn` | text | text | - | 역외펀드 여부(0/1). 결측 없음. |
| `fd_set_pcd` | text | text | - | 펀드설정유형코드(0/10/20). 결측 없음. |
| `pfiv_sale_cntl_tcd` | text | text | - | 전문투자자 판매제어 구분코드(0/1/3 등 4종). 결측 없음. |
| `frc_bpr_itm_yn` | text | text | - | 외화기준가종목 여부(0/1). 결측 없음. |
| `han_clas_nm` | text | text | 클래스명 | 클래스 한글 표기(195종, 예: 수수료미징구-온라인). 59.3% 결측. 클래스가 나뉜 펀드에만 값이 있다. |
| `han_clas_fee_type` | text | text | 수수료유형 | 클래스 수수료 부과 유형(수수료미징구 7,834 / 수수료선취 1,786 / 수수료후취 5). 59.3% 결측. |
| `han_clas_sales_channel` | text | text | 판매채널 | 클래스 판매채널(오프라인 6,048 / 온라인 3,548 / 직판 7). 59.4% 결측. |
| `han_clas_policies` | text | text | - | 클래스 부가 정책(33종, 예: 랩,펀드 / 보수체감 / 개인연금). 73.5% 결측. |
| `sale_yn` | text | text | 판매가능여부, 판매상태, 판매여부, 판매중, 판매가능 | 판매여부. 값은 판매중(10,962)/판매완료(12,714) 텍스트이고 0/1 플래그가 아니다. 결측 없음. |
| `thco_sale_yn` | text | text | - | 당사판매여부. 값이 있는 행 전부 'Y'이고 55.2% 결측이라 변별력이 낮다. |
| `sale_co_rwrd_r` | numeric | double precision | 판매회사보수 | 판매회사보수(%). 결측 없음. |
| `or_co_rwrd_r` | numeric | double precision | 운용보수 | 집합투자업자보수(운용보수, %). 결측 없음. |
| `trusc_rwrd_r` | numeric | double precision | 신탁보수 | 신탁업자보수(%). 결측 없음. |
| `ofwk_trus_rwrd_r` | numeric | double precision | 사무관리보수 | 일반사무관리보수(%). 결측 없음. 총보수를 구하려면 이 네 보수 컬럼을 더해야 하며, 합산 컬럼은 따로 없다. |
| `or_co_xtn_itt_cd` | text | text | - | 운용회사 대외기관코드(275종). 운용사 이름 컬럼은 이 테이블에 없다. 결측 없음. |
| `trusc_xtn_itt_cd` | text | text | - | 수탁회사 대외기관코드(50종). 0.2% 결측. |
| `fd_nast_suma` | numeric | double precision | 순자산, AUM, 순자산총액 | 펀드 순자산(원). 60.2% 결측. 이전 배포본(13.1% 결측)보다 결측이 크게 늘었으므로 정렬/필터 시 NULL 제외가 사실상 필수다. |
| `bns_bpr` | numeric | double precision | - | 매매기준가. 60.2% 결측. |
| `fd_sbpr` | numeric | bigint | - | 시가평가금액. 결측 없음이지만 0인 행이 많다. |
| `fd_prsv_r` | numeric | double precision | - | 보전율(%). 결측 없음. |
| `fd_mm1_ern_r` | numeric | double precision | 1개월수익률 | 1개월 수익률(%). 68.8% 결측. |
| `fd_mm3_ern_r` | numeric | double precision | 3개월수익률 | 3개월 수익률(%). 69.1% 결측. |
| `fd_mm6_ern_r` | numeric | double precision | 6개월수익률 | 6개월 수익률(%). 69.5% 결측. |
| `fd_mm18_ern_r` | numeric | double precision | - | 18개월 수익률(%). 70.9% 결측. |
| `fd_yr1_ern_r` | numeric | double precision | 1년수익률 | 1년 수익률(%). 70.3% 결측. |
| `fd_yr2_ern_r` | numeric | double precision | 2년수익률 | 2년 수익률(%). 71.5% 결측. |
| `fd_yr3_ern_r` | numeric | double precision | 3년수익률 | 3년 수익률(%). 72.6% 결측. |
| `fd_yr5_ern_r` | numeric | double precision | 5년수익률 | 5년 수익률(%). 74.7% 결측. |
| `fd_wk1_ern_r` | numeric | double precision | - | 1주일 수익률(%). 23,676건 전부 NULL이라 사실상 미사용 컬럼이다(이전 배포본에는 값이 있었다). |
| `zrin_fd_ivst_risk_gcd` | text | double precision | - | 제로인 펀드투자위험등급코드(1~6, 1이 최고위험). 63.3% 결측. |
| `zrin_fd_ivst_risk_grd_nm` | text | text | 위험등급 | 제로인 펀드투자위험등급명(높은 위험 3,023 / 다소 높은 위험 1,765 / 보통 위험 1,428 / 낮은 위험 1,193 / 매우 높은 위험 897 / 매우 |
| `zrin_btyp_nm` | text | text | - | 제로인 대유형명(18종, 예: MMF/기타/외화 MMF). 52.4% 결측. |
| `zrin_btyp_cd` | text | double precision | - | 제로인 대유형코드(18종). 52.4% 결측. |
| `zrin_ptn_nm` | text | text | - | 제로인 유형명(102종). 52.4% 결측. |
| `zrin_pcd` | text | double precision | - | 제로인 유형코드(104종). 52.4% 결측. |
| `zrin_attr_nms` | text | text | - | 제로인 속성명 목록(쉼표 구분, 예: 추가,국내,개방,국내위탁판매). 52.4% 결측. |
| `zrin_dmst_stk_cmst_rt` | numeric | double precision | 국내주식구성비율 | 국내주식 구성비율(%). 60.2% 결측. |
| `zrin_ovrs_stk_cmst_rt` | numeric | double precision | 해외주식구성비율 | 해외주식 구성비율(%). 60.2% 결측. |
| `zrin_dmst_bd_cmst_rt` | numeric | double precision | 국내채권구성비율 | 국내채권 구성비율(%). 60.2% 결측. |
| `zrin_ovrs_bd_cmst_rt` | numeric | double precision | 해외채권구성비율 | 해외채권 구성비율(%). 60.2% 결측. |
| `zrin_fd_cmst_rt` | numeric | double precision | - | 펀드 구성비율(재간접 비중, %). 60.2% 결측. |
| `zrin_liqt_cmst_rt` | numeric | double precision | - | 유동성 구성비율(%). 60.2% 결측. |
| `zrin_etc_ast_cmst_rt` | numeric | double precision | - | 기타자산 구성비율(%). 60.2% 결측. |
| `prfd_attr_cds` | text | text | - | 펀드별 속성코드 목록(쉼표 구분, 예: C101,V101,D102,C103). 52.4% 결측. |
| `prfd_attr_cnt` | text | bigint | - | 펀드별 속성 개수(0~13). 결측 없음. |
| `prfd_attr_search_text` | text | text | - | 상품검색용 속성 코드/명칭이 함께 들어간 텍스트(예: 'D102 국내위탁판매 V101 국내 C101 추가'). 52.4% 결측. LIKE 검색용으로 쓸 수 있다. |
| `bmrk_nm` | text | text | 벤치마크 | 벤치마크명(국문, 389종). 52.4% 결측. |
| `bmrk_eng_nm` | text | text | - | 벤치마크명(영문, 386종). 52.4% 결측. |
| `fd_last_dstb_r` | numeric | double precision | - | 최근 분배율(%). 54.1% 결측. |
| `fd_last_dstb_actg_bss_dt` | text | double precision | - | 최근 분배 회계기초일자(YYYYMMDD). 54.1% 결측. |
| `fd_last_dstb_actg_eot_dt` | text | double precision | - | 최근 분배 회계기말일자(YYYYMMDD). 54.1% 결측. |
| `curr_cd` | text | text | 통화 | 통화코드(KRW 23,147 / USD 453 / EUR 56 / JPY 15 / AUD 2 / GBP 2 / SEK 1). 결측 없음. |
| `exchdg_yn` | text | text | 환헤지여부 | 환헤지 여부(Y/N). 70.5% 결측. |
| `fd_price_bas_dt` | text | double precision | - | 펀드 기준가/수익률 기준일자(905종). 최신값 20260821이지만 과거 일자가 섞여 있어 종목마다 기준일이 다르다. 60.2% 결측. |
| `fd_daily_bas_dt` | text | double precision | - | 펀드 데일리정보 기준일자. fd_price_bas_dt와 같은 값. 60.2% 결측. |

하위유형(subtype) 조건 12개가 쓰는 컬럼: `or_attr_desc`(10개: 주식형→eq 주식형, 채권형→eq 채권형, 채권혼합→eq 채권혼합, 주식혼합→eq 주식혼합…); `prvo_pbff_desc`(2개: 공모→eq 공모, 사모→eq 사모)

### 3.3 JOIN 보강 테이블 정의 vs 원격

#### `enriched.etf_kr_enriched` AS ee ON ee.pd_itm_no = base.pd_itm_no — 원격 존재: **아니오**

| 사용 도메인 | 개념 | 컬럼 |
|---|---|---|
| 국내ETF | 총보수율 | `ee.charge_rt_final` |
| 국내ETF | 총보수 | `ee.charge_rt_final` |
| 국내ETF | 보수 | `ee.charge_rt_final` |

로컬 원천 CSV `data/enriched/etf_kr_enriched.csv`: 1,780행, 컬럼 12개: `pd_itm_no`, `pd_itm_no_ma`, `pd_grp_no`, `pd_abrv_nm`, `lseg_key`, `ter`, `replication`, `base_market`, `base_asset`, `hedge_type`, `charge_rt_final`, `charge_rt_source`

이름이 비슷한 원격 테이블: `core.etf_kr`(product_id, pd_itm_no, name, ticker, isin, manager, base_index, currency, listing_date, delisting_date, effective_as_of), `enriched.etf_kr`(product_id, pd_itm_no, name, ticker, isin, manager, base_index, currency, listing_date, delisting_date, effective_as_of) — 컬럼 구성이 달라 대체 불가.

### 3.4 로컬에만 있는 보강 CSV (`data/enriched/`)

| 파일 | 행수 | 컬럼 | 원격 적재 |
|---|---:|---|---|
| `bond_kr_enriched.csv` | 21,882 | pd_no, pd_exg_mkt, info_seq, crd_grd_norm, crd_grd_rank, crd_grd_source, remaining_days, maturity_bucket, is_krw, has_sale_info, is_sellable, source | 유사 이름 존재(내용 확인 필요) |
| `company_master.csv` | 118,709 | corp_code, corp_name, corp_name_norm, stock_code, source | 없음 |
| `etf_kr_enriched.csv` | 1,780 | pd_itm_no, pd_itm_no_ma, pd_grp_no, pd_abrv_nm, lseg_key, ter, replication, base_market, base_asset, hedge_type, charge_rt_final, charge_rt_source | 유사 이름 존재(내용 확인 필요) |
| `holding_code_map.csv` | 1,393 | holding_code_raw, holding_name, sec_type, corp_code, common_ticker, etf_isin, match_rule, source | 없음 |

## 4. 대조 결론

- 채권 `raw.prbd01n001`: 컬럼 집합 동일.
- 국내ETF `raw.pref01n001`: 컬럼 집합 동일.
- 해외ETF `raw.pref02n001`: 컬럼 집합 동일.
- 펀드 `raw.prfd01n001`: 컬럼 집합 동일.
- 보강 테이블 `enriched.etf_kr_enriched`는 원격에 없다. 이 테이블을 쓰는 카탈로그 개념은 실행 전 `utils.missing_join_tables`가 걸러 '보강 테이블 없음'으로 건너뛴다. 해결은 `data/enriched/` CSV를 원격에 적재(`src/kb/build_data_platform.py`, 쓰기 계정 필요)하거나 카탈로그를 원본 컬럼으로 되돌리는 것이다.
- 원격에는 로컬 로직이 쓰지 않는 `relations.*`(편입·자회사·테마), `enriched.product_master`·`security_master`, `vec.*`가 있다. Graph 스토어의 관계 데이터가 RDB에도 있으므로 Graph 경로가 막힐 때 RDB 조인으로 우회할 수 있다.