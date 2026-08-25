-- raw_next 적재 후 결정적으로 enriched/relations/coverage를 생성한다.
-- 이 파일에는 buyable_quantity를 이용한 판매가능 판정이 없어야 한다.

INSERT INTO __ENRICHED__.product_master
WITH latest AS (
    SELECT DISTINCT ON (pd_no) *
    FROM __RAW__.bond_kr_master
    ORDER BY pd_no, info_base_dt DESC, info_seq DESC, pd_exg_mkt
)
SELECT
    'bond_kr:' || btrim(pd_no), 'PRBD01N001', btrim(pd_no), 'BOND', 'KR',
    btrim(pd_nm), NULLIF(btrim(pd_abrv_nm), ''), NULLIF(btrim(curr_cd), ''),
    (__META__.yyyymmdd(mat_dt) IS NULL OR __META__.yyyymmdd(mat_dt) > DATE '2026-08-24'),
    'latest snapshot presence; exclude only explicit maturity/listing end; BUYABLE_QUANTITY ignored',
    DATE '2026-08-24', __META__.yyyymmdd(info_base_dt)
FROM latest;

INSERT INTO __ENRICHED__.product_master
SELECT
    CASE btrim(pd_grp_no)
        WHEN 'ETF' THEN 'etf_kr:' || btrim(pd_itm_no)
        WHEN 'ETN' THEN 'etn_kr:' || btrim(pd_itm_no)
    END,
    'PREF01N001', btrim(pd_itm_no), btrim(pd_grp_no) || '_KR', 'KR',
    btrim(pd_nm), NULLIF(btrim(pd_abrv_nm), ''),
    NULLIF(regexp_replace(btrim(pd_curr_cd), '^CURR_CD_', ''), ''),
    (__META__.yyyymmdd(pd_lste_dt) IS NULL OR __META__.yyyymmdd(pd_lste_dt) > DATE '2026-08-24'),
    'latest snapshot presence; exclude only explicit listing end',
    DATE '2026-08-24', DATE '2026-08-24'
FROM __RAW__.etf_kr_master
WHERE btrim(pd_grp_no) IN ('ETF', 'ETN');

INSERT INTO __ENRICHED__.product_master
SELECT
    CASE btrim(pd_grp_no)
        WHEN 'ETF' THEN 'etf_gl:' || btrim(pd_itm_no)
        WHEN 'ETN' THEN 'etn_gl:' || btrim(pd_itm_no)
    END,
    'PREF02N001', btrim(pd_itm_no), btrim(pd_grp_no) || '_GL', 'GL',
    btrim(pd_nm), NULLIF(btrim(pd_abrv_nm), ''), NULLIF(btrim(pd_trd_ccy), ''),
    true,
    'latest snapshot presence; source has no explicit listing-end axis',
    DATE '2026-08-24', DATE '2026-08-22'
FROM __RAW__.etf_gl_master
WHERE btrim(pd_grp_no) IN ('ETF', 'ETN');

INSERT INTO __ENRICHED__.product_master
SELECT
    'fund:' || btrim(itm_no), 'PRFD01N001', btrim(itm_no),
    CASE btrim(prvo_pbff_desc) WHEN '공모' THEN 'FUND_PUB' ELSE 'FUND_PRIVATE' END,
    'KR', btrim(itm_nm), NULLIF(btrim(itm_abrv_nm), ''), NULLIF(btrim(curr_cd), ''),
    true,
    'latest snapshot presence; source has no explicit maturity/listing-end axis',
    DATE '2026-08-24', COALESCE(__META__.yyyymmdd(fd_price_bas_dt), DATE '2026-08-21')
FROM __RAW__.fund_pub_master
WHERE btrim(prvo_pbff_desc) IN ('공모', '사모');

INSERT INTO __ENRICHED__.bond_kr_product (
    product_id,pd_no,name,issuer,credit_rating,currency,issue_date,maturity_date,
    risk_code,risk_name,is_assumed_purchasable,purchasable_rule,effective_as_of
)
WITH latest AS (
    SELECT DISTINCT ON (pd_no) *
    FROM __RAW__.bond_kr_master
    ORDER BY pd_no, info_base_dt DESC, info_seq DESC, pd_exg_mkt
)
SELECT
    'bond_kr:' || btrim(pd_no), btrim(pd_no), btrim(pd_nm), NULLIF(btrim(pd_pbcm), ''),
    NULLIF(btrim(crd_grd), ''), NULLIF(btrim(curr_cd), ''),
    __META__.yyyymmdd(isu_dt), __META__.yyyymmdd(mat_dt),
    NULLIF(btrim(pd_risk_gcd), ''), NULLIF(btrim(pd_risk_nm), ''),
    (__META__.yyyymmdd(mat_dt) IS NULL OR __META__.yyyymmdd(mat_dt) > DATE '2026-08-24'),
    'latest snapshot presence; false only when explicit maturity/listing end <= 2026-08-24; BUYABLE_QUANTITY ignored',
    __META__.yyyymmdd(info_base_dt)
FROM latest;

INSERT INTO __ENRICHED__.bond_kr_offer
SELECT
    btrim(pd_no), btrim(pd_exg_mkt), __META__.yyyymmdd(info_base_dt), info_seq::integer,
    'bond_kr:' || btrim(pd_no), applied_yield, after_tax_yield, buy_yield,
    __META__.yyyymmdd(sale_yield_base_dt), eval_price, trade_price, buyable_quantity
FROM __RAW__.bond_kr_master;

INSERT INTO __ENRICHED__.etf_kr
SELECT
    'etf_kr:' || btrim(pd_itm_no), btrim(pd_itm_no), btrim(pd_nm),
    NULLIF(btrim(pd_ticker), ''), NULLIF(btrim(pd_isin_cd), ''),
    NULLIF(btrim(cu_fund_mgmt_co), ''), NULLIF(btrim(cu_base_index), ''),
    NULLIF(regexp_replace(btrim(pd_curr_cd), '^CURR_CD_', ''), ''),
    __META__.yyyymmdd(pd_lstg_dt), __META__.yyyymmdd(pd_lste_dt), DATE '2026-08-24'
FROM __RAW__.etf_kr_master WHERE btrim(pd_grp_no) = 'ETF';

INSERT INTO __ENRICHED__.etf_gl
SELECT
    'etf_gl:' || btrim(pd_itm_no), btrim(pd_itm_no), btrim(pd_nm),
    NULLIF(btrim(pd_abrv_nm), ''), NULLIF(btrim(pd_isin_cd), ''),
    NULLIF(btrim(cu_fund_mgmt_co), ''),
    CASE WHEN btrim(cu_base_index) ILIKE 'Index is not %' THEN NULL ELSE NULLIF(btrim(cu_base_index), '') END,
    NULLIF(btrim(pd_trd_ccy), ''), __META__.yyyymmdd(pd_lstg_dt), DATE '2026-08-22'
FROM __RAW__.etf_gl_master WHERE btrim(pd_grp_no) = 'ETF';

INSERT INTO __ENRICHED__.etn_kr
SELECT
    'etn_kr:' || btrim(pd_itm_no), btrim(pd_itm_no), btrim(pd_nm),
    NULLIF(btrim(pd_ticker), ''), NULLIF(btrim(pd_isin_cd), ''),
    NULLIF(btrim(cu_fund_mgmt_co), ''),
    NULLIF(regexp_replace(btrim(pd_curr_cd), '^CURR_CD_', ''), ''),
    __META__.yyyymmdd(pd_lstg_dt), __META__.yyyymmdd(pd_lste_dt), DATE '2026-08-24'
FROM __RAW__.etf_kr_master WHERE btrim(pd_grp_no) = 'ETN';

INSERT INTO __ENRICHED__.etn_gl
SELECT
    'etn_gl:' || btrim(pd_itm_no), btrim(pd_itm_no), btrim(pd_nm),
    NULLIF(btrim(pd_abrv_nm), ''), NULLIF(btrim(pd_isin_cd), ''),
    NULLIF(btrim(cu_fund_mgmt_co), ''), NULLIF(btrim(pd_trd_ccy), ''),
    __META__.yyyymmdd(pd_lstg_dt), DATE '2026-08-22'
FROM __RAW__.etf_gl_master WHERE btrim(pd_grp_no) = 'ETN';

INSERT INTO __ENRICHED__.fund
SELECT
    'fund:' || btrim(itm_no), btrim(itm_no), btrim(itm_nm), NULLIF(btrim(itm_abrv_nm), ''),
    btrim(prvo_pbff_desc), NULLIF(btrim(or_co_xtn_itt_cd), ''), NULLIF(btrim(bmrk_nm), ''),
    NULLIF(btrim(curr_cd), ''), COALESCE(__META__.yyyymmdd(fd_price_bas_dt), DATE '2026-08-21')
FROM __RAW__.fund_pub_master WHERE btrim(prvo_pbff_desc) IN ('공모', '사모');

-- 주최측 공통 지표. 0/NULL은 값 자체를 보존하되 is_available=false다.
INSERT INTO __ENRICHED__.product_metric
SELECT md5(product_id || '|AUM|' || as_of || '|PRBD01N001'), product_id, 'AUM', value, unit,
       as_of, 'PRBD01N001', 'isu_bal_amt', 'raw', value IS NOT NULL AND value <> 0,
       CASE WHEN value IS NULL THEN 'NULL' WHEN value = 0 THEN 'ZERO_AS_UNAVAILABLE' END, 1
FROM (
    SELECT 'bond_kr:' || btrim(pd_no) product_id, max(isu_bal_amt)::numeric value,
           COALESCE(NULLIF(btrim(curr_cd), ''), 'UNSPECIFIED') unit,
           __META__.yyyymmdd(info_base_dt) as_of
    FROM __RAW__.bond_kr_master GROUP BY pd_no, curr_cd, info_base_dt
) metric;

INSERT INTO __ENRICHED__.product_metric
SELECT md5(product_id || '|' || metric_code || '|' || as_of || '|PREF01N001'),
       product_id, metric_code, value, unit, as_of, 'PREF01N001', source_column, 'raw',
       value IS NOT NULL AND value <> 0,
       CASE WHEN value IS NULL THEN 'NULL' WHEN value = 0 THEN 'ZERO_AS_UNAVAILABLE' END, 1
FROM (
    SELECT 'etf_kr:' || btrim(pd_itm_no) product_id, metric_code, value,
           CASE WHEN metric_code = 'AUM' THEN COALESCE(NULLIF(regexp_replace(btrim(pd_curr_cd), '^CURR_CD_', ''), ''), 'UNSPECIFIED') ELSE 'percent' END unit,
           CASE WHEN metric_code = 'AUM' THEN DATE '2026-08-21' ELSE DATE '2026-08-21' END as_of,
           source_column
    FROM __RAW__.etf_kr_master
    CROSS JOIN LATERAL (VALUES
        ('AUM', du_last_aum::numeric, 'du_last_aum'),
        ('RETURN_1Y', du_er_1y::numeric, 'du_er_1y'),
        ('EXPENSE_RATIO', cu_charge_rt::numeric, 'cu_charge_rt')
    ) m(metric_code, value, source_column)
    WHERE btrim(pd_grp_no) = 'ETF'
) metric;

INSERT INTO __ENRICHED__.product_metric
SELECT md5(product_id || '|' || metric_code || '|' || as_of || '|PREF02N001'),
       product_id, metric_code, value, unit, as_of, 'PREF02N001', source_column, 'raw',
       value IS NOT NULL AND value <> 0,
       CASE WHEN value IS NULL THEN 'NULL' WHEN value = 0 THEN 'ZERO_AS_UNAVAILABLE' END, 1
FROM (
    SELECT 'etf_gl:' || btrim(pd_itm_no) product_id, metric_code, value,
           CASE WHEN metric_code = 'AUM' THEN COALESCE(NULLIF(btrim(pd_trd_ccy), ''), 'UNSPECIFIED') ELSE 'percent' END unit,
           DATE '2026-08-22' as_of, source_column
    FROM __RAW__.etf_gl_master
    CROSS JOIN LATERAL (VALUES
        ('AUM', du_last_aum::numeric, 'du_last_aum'),
        ('EXPENSE_RATIO', cu_charge_rt::numeric, 'cu_charge_rt')
    ) m(metric_code, value, source_column)
    WHERE btrim(pd_grp_no) = 'ETF'
) metric;

-- 해외ETF 원천에는 1년 수익률 축이 없다. 단순 종가로 대체하지 않고 미확보 행을 남긴다.
INSERT INTO __ENRICHED__.product_metric
SELECT md5(product_id || '|RETURN_1Y|2026-08-24|LSEG'), product_id, 'RETURN_1Y', NULL,
       'percent', DATE '2026-08-24', 'LSEG', 'adjusted_price_or_total_return',
       'not_collected', false, 'LSEG_ADJUSTED_OR_TOTAL_RETURN_FIELD_UNAVAILABLE', 2
FROM __ENRICHED__.product_master WHERE product_type = 'ETF_GL';

INSERT INTO __ENRICHED__.product_metric
SELECT md5(product_id || '|' || metric_code || '|' || as_of || '|PRFD01N001'),
       product_id, metric_code, value, unit, as_of, 'PRFD01N001', source_column, 'raw',
       value IS NOT NULL AND value <> 0,
       CASE WHEN value IS NULL THEN 'NULL' WHEN value = 0 THEN 'ZERO_AS_UNAVAILABLE' END, 1
FROM (
    SELECT 'fund:' || btrim(itm_no) product_id, metric_code, value,
           CASE WHEN metric_code = 'AUM' THEN COALESCE(NULLIF(btrim(curr_cd), ''), 'UNSPECIFIED') ELSE 'percent' END unit,
           COALESCE(__META__.yyyymmdd(fd_price_bas_dt), DATE '2026-08-21') as_of, source_column
    FROM __RAW__.fund_pub_master
    CROSS JOIN LATERAL (VALUES
        ('AUM', fd_nast_suma::numeric, 'fd_nast_suma'),
        ('RETURN_1Y', fd_yr1_ern_r::numeric, 'fd_yr1_ern_r'),
        ('EXPENSE_RATIO', zrin_fd_cmst_rt::numeric, 'zrin_fd_cmst_rt')
    ) m(metric_code, value, source_column)
    WHERE btrim(prvo_pbff_desc) IN ('공모', '사모')
) metric;

-- 상품 자체의 증권 식별자를 통합한다. 외부 편입종목 식별자는 관계 수집기가 추가한다.
INSERT INTO __ENRICHED__.security_master
SELECT product_id, name,
       CASE WHEN product_type LIKE 'ETF%' THEN 'etf'
            WHEN product_type LIKE 'ETN%' THEN 'etn'
            WHEN product_type = 'BOND' THEN 'bond' ELSE 'fund' END,
       NULL, market_scope
FROM __ENRICHED__.product_master;

INSERT INTO __ENRICHED__.security_identifier
SELECT product_id, 'SOURCE_KEY', source_key, true FROM __ENRICHED__.product_master;
INSERT INTO __ENRICHED__.security_identifier
SELECT product_id, 'ISIN', isin, true FROM __ENRICHED__.etf_kr WHERE isin IS NOT NULL
ON CONFLICT DO NOTHING;
INSERT INTO __ENRICHED__.security_identifier
SELECT product_id, 'KR_TICKER', ticker, true FROM __ENRICHED__.etf_kr WHERE ticker IS NOT NULL
ON CONFLICT DO NOTHING;
INSERT INTO __ENRICHED__.security_identifier
SELECT product_id, 'ISIN', isin, false FROM __ENRICHED__.etf_gl WHERE isin IS NOT NULL
ON CONFLICT DO NOTHING;
INSERT INTO __ENRICHED__.security_identifier
SELECT product_id, 'RIC', pd_itm_no, true FROM __ENRICHED__.etf_gl
ON CONFLICT DO NOTHING;

-- 주최측이 제공한 분류축만 관계로 만든다. 내부 코드 의미는 추측하지 않는다.
INSERT INTO __RELATIONS__.product_classification
SELECT md5(product_id || '|region|' || value), product_id, 'region', value, as_of, NULL, source
FROM (
    SELECT 'etf_kr:' || btrim(pd_itm_no) product_id, NULLIF(btrim(wu_inv_rgn), '') value,
           DATE '2026-08-21' as_of, 'PREF01N001.wu_inv_rgn' source
    FROM __RAW__.etf_kr_master WHERE btrim(pd_grp_no) = 'ETF'
    UNION ALL
    SELECT 'etf_gl:' || btrim(pd_itm_no), NULLIF(btrim(wu_inv_rgn), ''), DATE '2026-08-22',
           'PREF02N001.wu_inv_rgn' FROM __RAW__.etf_gl_master WHERE btrim(pd_grp_no) = 'ETF'
    UNION ALL
    SELECT 'fund:' || btrim(itm_no), NULLIF(btrim(fd_ivst_rgn_desc), ''),
           COALESCE(__META__.yyyymmdd(fd_price_bas_dt), DATE '2026-08-21'),
           'PRFD01N001.fd_ivst_rgn_desc' FROM __RAW__.fund_pub_master
) x WHERE value IS NOT NULL;

INSERT INTO __META__.product_coverage
SELECT
    p.product_id,
    CASE WHEN p.product_type IN ('BOND', 'ETN_KR', 'ETN_GL') THEN 'not_applicable'
         WHEN EXISTS (SELECT 1 FROM __RELATIONS__.product_holding h WHERE h.product_id=p.product_id) THEN 'available'
         ELSE 'unavailable' END,
    CASE WHEN p.product_type IN ('BOND', 'ETN_KR', 'ETN_GL') THEN '편입종목 개념 비적용'
         WHEN EXISTS (SELECT 1 FROM __RELATIONS__.product_holding h WHERE h.product_id=p.product_id) THEN '근거 문서 기반 편입내역 확보'
         ELSE '편입내역 미확보; 보유하지 않음으로 해석 금지' END,
    CASE WHEN EXISTS (SELECT 1 FROM __RELATIONS__.product_document d WHERE d.product_id=p.product_id) THEN 'available' ELSE 'unavailable' END,
    CASE WHEN EXISTS (SELECT 1 FROM __RELATIONS__.product_document d WHERE d.product_id=p.product_id) THEN '공식 문서 연결' ELSE '공식 문서 미수집' END,
    CASE WHEN EXISTS (
        SELECT 1 FROM __ENRICHED__.product_metric m
        WHERE m.product_id=p.product_id AND m.metric_code='RETURN_1Y' AND m.is_available
    ) THEN 'available' ELSE 'unavailable' END,
    CASE WHEN EXISTS (
        SELECT 1 FROM __ENRICHED__.product_metric m
        WHERE m.product_id=p.product_id AND m.metric_code='RETURN_1Y' AND m.is_available
    ) THEN '주최측 또는 허용된 외부 1년 수익률 확보' ELSE '1년 수익률 값 미확보' END,
    p.effective_as_of, NULL
FROM __ENRICHED__.product_master p;

CREATE MATERIALIZED VIEW __ENRICHED__.product_search AS
SELECT
    p.product_id, p.product_type, p.market_scope, p.name, p.short_name, p.currency,
    p.is_active, p.active_rule, p.effective_as_of,
    max(m.value) FILTER (WHERE m.metric_code='AUM' AND m.is_available) AS aum,
    max(m.unit) FILTER (WHERE m.metric_code='AUM' AND m.is_available) AS aum_unit,
    max(m.value) FILTER (WHERE m.metric_code='RETURN_1Y' AND m.is_available) AS return_1y,
    max(m.value) FILTER (WHERE m.metric_code='EXPENSE_RATIO' AND m.is_available) AS expense_ratio,
    c.holdings_status, c.holdings_reason, c.document_status, c.performance_status
FROM __ENRICHED__.product_master p
LEFT JOIN __ENRICHED__.product_metric m ON m.product_id=p.product_id
LEFT JOIN __META__.product_coverage c ON c.product_id=p.product_id
GROUP BY p.product_id, c.holdings_status, c.holdings_reason, c.document_status, c.performance_status;
CREATE UNIQUE INDEX product_search_id_idx ON __ENRICHED__.product_search(product_id);
CREATE INDEX product_search_name_idx ON __ENRICHED__.product_search(name);
CREATE INDEX product_search_rank_idx ON __ENRICHED__.product_search(product_type, return_1y DESC NULLS LAST);

-- 코드명·기존 Agent 호환 뷰.
CREATE VIEW __RAW__.prbd01n001 AS SELECT * FROM __RAW__.bond_kr_master;
CREATE VIEW __RAW__.pref01n001 AS SELECT * FROM __RAW__.etf_kr_master;
CREATE VIEW __RAW__.pref02n001 AS SELECT * FROM __RAW__.etf_gl_master;
CREATE VIEW __RAW__.prfd01n001 AS SELECT * FROM __RAW__.fund_pub_master;
CREATE VIEW __CORE__.bond_kr AS SELECT * FROM __ENRICHED__.bond_kr_product;
CREATE VIEW __CORE__.etf_kr AS SELECT * FROM __ENRICHED__.etf_kr;
CREATE VIEW __CORE__.etf_gl AS SELECT * FROM __ENRICHED__.etf_gl;
CREATE VIEW __CORE__.fund_pub AS SELECT * FROM __ENRICHED__.fund_pub;
CREATE VIEW __CORE__.etn AS
SELECT product_id, pd_itm_no, name, ticker, isin, issuer, currency, listing_date,
       delisting_date, effective_as_of, 'KR'::text market_scope
FROM __ENRICHED__.etn_kr
UNION ALL
SELECT product_id, pd_itm_no, name, ticker, isin, issuer, currency, listing_date,
       NULL::date, effective_as_of, 'GL'::text
FROM __ENRICHED__.etn_gl;
