-- 금융상품 데이터 플랫폼 v2 비원천 스키마.
-- __META__/__ENRICHED__/__RELATIONS__/__VEC__는 빌더가 *_next로 치환한다.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS __META__;
CREATE SCHEMA IF NOT EXISTS __ENRICHED__;
CREATE SCHEMA IF NOT EXISTS __RELATIONS__;
CREATE SCHEMA IF NOT EXISTS __VEC__;
CREATE SCHEMA IF NOT EXISTS __CORE__;

CREATE TABLE __META__.dataset_snapshot (
    snapshot_id uuid PRIMARY KEY,
    dataset_version text NOT NULL,
    release_date date NOT NULL,
    cutoff_date date NOT NULL,
    domain_as_of jsonb NOT NULL,
    source_files jsonb NOT NULL,
    source_hash text NOT NULL UNIQUE,
    built_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE __META__.load_run (
    run_id uuid PRIMARY KEY,
    snapshot_id uuid NOT NULL REFERENCES __META__.dataset_snapshot(snapshot_id),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running', 'passed', 'failed')),
    phase text NOT NULL,
    source_rows jsonb NOT NULL DEFAULT '{}'::jsonb,
    loaded_rows jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text
);

CREATE TABLE __META__.column_catalog (
    table_schema text NOT NULL,
    table_name text NOT NULL,
    ordinal_position integer NOT NULL,
    column_name text NOT NULL,
    data_type text NOT NULL,
    is_nullable boolean NOT NULL,
    description text NOT NULL,
    unit text NOT NULL,
    as_of_column text NOT NULL,
    zero_null_rule text NOT NULL,
    source_priority text NOT NULL,
    transform_expression text NOT NULL,
    implementation_status text NOT NULL,
    deployment_status text NOT NULL,
    pk_ordinal integer,
    fk_target text NOT NULL,
    grain text NOT NULL,
    PRIMARY KEY (table_schema, table_name, ordinal_position),
    UNIQUE (table_schema, table_name, column_name)
);

CREATE OR REPLACE FUNCTION __META__.yyyymmdd(value text)
RETURNS date
LANGUAGE sql
IMMUTABLE
RETURNS NULL ON NULL INPUT
AS $$
    WITH normalized AS (
        SELECT regexp_replace(split_part(btrim(value), ' ', 1), '\.0+$', '') AS v
    )
    SELECT CASE
        WHEN v ~ '^[0-9]{8}$' AND to_char(to_date(v, 'YYYYMMDD'), 'YYYYMMDD') = v
        THEN to_date(v, 'YYYYMMDD')
        WHEN v ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
         AND to_char(to_date(v, 'YYYY-MM-DD'), 'YYYY-MM-DD') = v
        THEN to_date(v, 'YYYY-MM-DD')
        ELSE NULL
    END FROM normalized
$$;

CREATE TABLE __ENRICHED__.product_master (
    product_id text PRIMARY KEY,
    source_table text NOT NULL,
    source_key text NOT NULL,
    product_type text NOT NULL CHECK (
        product_type IN ('BOND', 'ETF_KR', 'ETF_GL', 'ETN_KR', 'ETN_GL', 'FUND_PUB', 'FUND_PRIVATE')
    ),
    market_scope text NOT NULL CHECK (market_scope IN ('KR', 'GL')),
    name text NOT NULL,
    short_name text,
    currency text,
    is_active boolean NOT NULL,
    active_rule text NOT NULL,
    snapshot_date date NOT NULL,
    effective_as_of date NOT NULL,
    UNIQUE (source_table, source_key)
);
CREATE INDEX product_master_type_idx ON __ENRICHED__.product_master(product_type);
CREATE INDEX product_master_name_idx ON __ENRICHED__.product_master(name);

CREATE TABLE __ENRICHED__.bond_kr_product (
    product_id text PRIMARY KEY REFERENCES __ENRICHED__.product_master(product_id),
    pd_no text NOT NULL UNIQUE,
    name text NOT NULL,
    issuer text,
    credit_rating text,
    currency text,
    issue_date date,
    maturity_date date,
    risk_code text,
    risk_name text,
    is_assumed_purchasable boolean NOT NULL,
    purchasable_rule text NOT NULL,
    effective_as_of date NOT NULL
);

CREATE TABLE __ENRICHED__.bond_kr_offer (
    pd_no text NOT NULL,
    exchange_market text NOT NULL,
    info_base_dt date NOT NULL,
    info_seq integer NOT NULL,
    product_id text NOT NULL REFERENCES __ENRICHED__.product_master(product_id),
    applied_yield double precision,
    after_tax_yield double precision,
    buy_yield double precision,
    sale_yield_base_dt date,
    eval_price double precision,
    trade_price double precision,
    buyable_quantity numeric(26,8),
    PRIMARY KEY (pd_no, exchange_market, info_base_dt, info_seq)
);
COMMENT ON COLUMN __ENRICHED__.bond_kr_offer.buyable_quantity IS
    '저장 전용. 구매가능 판정·필터·정렬에 절대 사용하지 않는다.';

CREATE TABLE __ENRICHED__.etf_kr (
    product_id text PRIMARY KEY REFERENCES __ENRICHED__.product_master(product_id),
    pd_itm_no text NOT NULL UNIQUE,
    name text NOT NULL,
    ticker text,
    isin text,
    manager text,
    base_index text,
    currency text,
    listing_date date,
    delisting_date date,
    effective_as_of date NOT NULL
);

CREATE TABLE __ENRICHED__.etf_gl (
    product_id text PRIMARY KEY REFERENCES __ENRICHED__.product_master(product_id),
    pd_itm_no text NOT NULL UNIQUE,
    name text NOT NULL,
    ticker text,
    isin text,
    manager text,
    base_index text,
    currency text,
    inception_date date,
    effective_as_of date NOT NULL
);

CREATE TABLE __ENRICHED__.etn_kr (
    product_id text PRIMARY KEY REFERENCES __ENRICHED__.product_master(product_id),
    pd_itm_no text NOT NULL UNIQUE,
    name text NOT NULL,
    ticker text,
    isin text,
    issuer text,
    currency text,
    listing_date date,
    delisting_date date,
    effective_as_of date NOT NULL
);

CREATE TABLE __ENRICHED__.etn_gl (
    product_id text PRIMARY KEY REFERENCES __ENRICHED__.product_master(product_id),
    pd_itm_no text NOT NULL UNIQUE,
    name text NOT NULL,
    ticker text,
    isin text,
    issuer text,
    currency text,
    inception_date date,
    effective_as_of date NOT NULL
);

CREATE TABLE __ENRICHED__.fund (
    product_id text PRIMARY KEY REFERENCES __ENRICHED__.product_master(product_id),
    itm_no text NOT NULL UNIQUE,
    name text NOT NULL,
    short_name text,
    offering_type text NOT NULL CHECK (offering_type IN ('공모', '사모')),
    manager_org_code text,
    benchmark text,
    currency text,
    effective_as_of date NOT NULL
);

CREATE VIEW __ENRICHED__.fund_pub AS
SELECT * FROM __ENRICHED__.fund WHERE offering_type = '공모';

CREATE TABLE __ENRICHED__.product_metric (
    metric_id text PRIMARY KEY,
    product_id text NOT NULL REFERENCES __ENRICHED__.product_master(product_id),
    metric_code text NOT NULL,
    value numeric,
    unit text NOT NULL,
    as_of date,
    source text NOT NULL,
    source_column text NOT NULL,
    method text NOT NULL,
    is_available boolean NOT NULL,
    unavailable_reason text,
    source_priority smallint NOT NULL CHECK (source_priority IN (1, 2)),
    UNIQUE (product_id, metric_code, as_of, source, method)
);
CREATE INDEX product_metric_lookup_idx
    ON __ENRICHED__.product_metric(product_id, metric_code, source_priority);
CREATE INDEX product_metric_rank_idx
    ON __ENRICHED__.product_metric(metric_code, value DESC)
    WHERE is_available;

CREATE TABLE __ENRICHED__.security_master (
    security_id text PRIMARY KEY,
    display_name text NOT NULL,
    security_type text NOT NULL,
    issuer_name text,
    country_code text
);

CREATE TABLE __ENRICHED__.security_identifier (
    security_id text NOT NULL REFERENCES __ENRICHED__.security_master(security_id),
    id_type text NOT NULL,
    id_value text NOT NULL,
    is_primary boolean NOT NULL,
    PRIMARY KEY (security_id, id_type, id_value)
);
CREATE INDEX security_identifier_value_idx
    ON __ENRICHED__.security_identifier(id_type, id_value);

CREATE TABLE __RELATIONS__.source_document (
    document_id text PRIMARY KEY,
    title text NOT NULL,
    publisher text NOT NULL,
    published_at date NOT NULL CHECK (published_at <= DATE '__CUTOFF_DATE__'),
    url text NOT NULL,
    source_hash text NOT NULL,
    source_type text NOT NULL,
    as_of date CHECK (as_of <= DATE '__CUTOFF_DATE__'),
    ingested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (source_hash)
);

CREATE TABLE __RELATIONS__.product_holding (
    holding_id text PRIMARY KEY,
    product_id text NOT NULL REFERENCES __ENRICHED__.product_master(product_id),
    security_id text NOT NULL REFERENCES __ENRICHED__.security_master(security_id),
    weight numeric,
    unit text NOT NULL DEFAULT 'percent',
    as_of date NOT NULL CHECK (as_of <= DATE '__CUTOFF_DATE__'),
    source_document_id text NOT NULL REFERENCES __RELATIONS__.source_document(document_id),
    source text NOT NULL,
    UNIQUE (product_id, security_id, as_of, source_document_id)
);
CREATE INDEX product_holding_product_idx ON __RELATIONS__.product_holding(product_id, as_of);
CREATE INDEX product_holding_security_idx ON __RELATIONS__.product_holding(security_id, as_of);

CREATE TABLE __RELATIONS__.product_classification (
    classification_id text PRIMARY KEY,
    product_id text NOT NULL REFERENCES __ENRICHED__.product_master(product_id),
    classification_type text NOT NULL CHECK (classification_type IN ('theme', 'sector', 'region', 'asset_type')),
    classification_value text NOT NULL,
    as_of date NOT NULL CHECK (as_of <= DATE '__CUTOFF_DATE__'),
    source_document_id text REFERENCES __RELATIONS__.source_document(document_id),
    source text NOT NULL,
    UNIQUE (product_id, classification_type, classification_value, as_of, source)
);

CREATE TABLE __RELATIONS__.company_subsidiary (
    relation_id text PRIMARY KEY,
    parent_security_id text NOT NULL REFERENCES __ENRICHED__.security_master(security_id),
    child_security_id text NOT NULL REFERENCES __ENRICHED__.security_master(security_id),
    ownership_pct numeric,
    as_of date NOT NULL CHECK (as_of <= DATE '__CUTOFF_DATE__'),
    source_document_id text NOT NULL REFERENCES __RELATIONS__.source_document(document_id),
    source text NOT NULL,
    UNIQUE (parent_security_id, child_security_id, as_of, source_document_id)
);

CREATE TABLE __RELATIONS__.product_document (
    product_id text NOT NULL REFERENCES __ENRICHED__.product_master(product_id),
    document_id text NOT NULL REFERENCES __RELATIONS__.source_document(document_id),
    relation_type text NOT NULL CHECK (relation_type IN ('prospectus', 'report', 'holdings', 'policy', 'other')),
    PRIMARY KEY (product_id, document_id, relation_type)
);

CREATE TABLE __META__.product_coverage (
    product_id text PRIMARY KEY REFERENCES __ENRICHED__.product_master(product_id),
    holdings_status text NOT NULL CHECK (holdings_status IN ('available', 'unavailable', 'not_applicable')),
    holdings_reason text NOT NULL,
    document_status text NOT NULL CHECK (document_status IN ('available', 'unavailable')),
    document_reason text NOT NULL,
    performance_status text NOT NULL CHECK (performance_status IN ('available', 'unavailable')),
    performance_reason text NOT NULL,
    as_of date NOT NULL,
    source_document_id text REFERENCES __RELATIONS__.source_document(document_id)
);

CREATE TABLE __VEC__.bond_schema_terms (
    term_uri text PRIMARY KEY,
    label text NOT NULL,
    comment text NOT NULL,
    alt_labels text[] NOT NULL DEFAULT '{}',
    content text NOT NULL,
    content_hash text NOT NULL,
    embedding_model text NOT NULL CHECK (embedding_model = 'bge-m3'),
    embedding_dim smallint NOT NULL CHECK (embedding_dim = 1024),
    embedding vector(1024) NOT NULL,
    UNIQUE (content_hash, embedding_model)
);

CREATE TABLE __VEC__.schema_terms_all (
    term_uri text PRIMARY KEY,
    label text NOT NULL,
    comment text NOT NULL,
    alt_labels text[] NOT NULL DEFAULT '{}',
    content text NOT NULL,
    content_hash text NOT NULL,
    embedding_model text NOT NULL CHECK (embedding_model = 'bge-m3'),
    embedding_dim smallint NOT NULL CHECK (embedding_dim = 1024),
    embedding vector(1024) NOT NULL,
    UNIQUE (content_hash, embedding_model)
);

CREATE TABLE __VEC__.document_chunk (
    chunk_id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES __RELATIONS__.source_document(document_id),
    product_id text REFERENCES __ENRICHED__.product_master(product_id),
    page_number integer,
    citation_text text NOT NULL,
    chunk_text text NOT NULL,
    published_at date NOT NULL CHECK (published_at <= DATE '__CUTOFF_DATE__'),
    source_url text NOT NULL,
    content_hash text NOT NULL,
    embedding_model text NOT NULL CHECK (embedding_model = 'bge-m3'),
    embedding_dim smallint NOT NULL CHECK (embedding_dim = 1024),
    embedding vector(1024) NOT NULL,
    UNIQUE (content_hash, embedding_model)
);
CREATE INDEX document_chunk_document_idx ON __VEC__.document_chunk(document_id);
CREATE INDEX document_chunk_product_idx ON __VEC__.document_chunk(product_id);
