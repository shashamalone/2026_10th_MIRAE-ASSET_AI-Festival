# RDB DEFINITION V2.0

이 문서는 팀원과 Agent/LLM이 별도 구두 설명 없이 물리 구조와 의미 계약을 재구성할 수 있도록 만든 자급형 정의서입니다.
자동 생성 파일이므로 직접 편집하지 말고 `python src/kb/build_catalog_v2.py`를 실행합니다.
물리 정의의 정본은 [단일 카탈로그](../../src/kb/catalog_v2.py)와 [PostgreSQL DDL](../../sql/v2/001_platform_schema.sql)입니다. `vec.*` 상세는 [VectorDB 정의서](VECTORDB_DEFINITION_V2_0.md)가 소유합니다.

- 데이터 버전: `financial-products-2026-08-24`
- release ID: `financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38`
- 배포일: `2026-08-24`
- 외부 근거 cutoff: `2026-08-24`

## 이 문서를 읽는 순서

1. `범위와 엔진`에서 이 DB가 담당하는 계산을 확인합니다.
2. `식별자와 조인 지도`에서 기준 엔티티와 조인키를 정합니다.
3. `지표 의미 사전`과 `핵심 데이터 규칙`으로 단위·기준일·결측 의미를 적용합니다.
4. `테이블 목록`에서 grain을 고른 뒤 `물리 테이블 상세`의 컬럼명만 사용해 SQL을 만듭니다.
5. 결과에는 `LLM/Agent evidence 계약`의 식별자·출처·실질 기준일을 항상 포함합니다.

## 범위와 엔진

- 엔진: PostgreSQL 17
- 물리 스키마: `meta`, `raw`, `enriched`, `relations`
- 공개 호환 스키마: `core` 및 코드명 `raw.*` 뷰
- stage 배포: 동일 DB의 `*_next`에서 검증 후 트랜잭션으로 정식 이름에 승격
- API 계정: `agent_reader`; 읽기 전용, statement timeout 2초, 최대 100행
- 담당 연산: 정확 조회, 숫자 필터·정렬·집계, 상품·지표·관계의 물리 조인
- 비담당 연산: 자연어 의미 매핑은 VectorDB, 다중 홉 관계·온톨로지 유효성은 GraphDB가 담당

## 읽기 인터페이스

| API | 용도 |
|---|---|
| `GET /db/version` | dataset version, release/cutoff, snapshot hash |
| `GET /db/tables` / `GET /db/columns` / `GET /db/columns/{schema}/{table}` | 물리 테이블·컬럼 탐색 |
| `GET /db/stats` | raw·상품·관계·vector 행 수 |
| `GET /db/catalog` | Agent용 전체 schema catalog |
| `GET /db/coverage` | 상품별 holdings·문서·성과 확보 상태 |
| `POST /db`, `POST /db/sql` | 읽기 전용 SELECT/CTE 실행; `sql`/`query` 별칭 |
| `POST /db/sparql` | 읽기 전용 SPARQL; `sparql`/`query` 별칭 |

직접 연결과 API 모두 쓰기 쿼리를 허용하지 않습니다. 운영 쓰기·스키마 승격은 서버 운영자 계정만 수행합니다.

## 데이터 스냅샷 계약

- 전체 snapshot SHA-256: `ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38`
- 공백만 NULL로 변환하고 숫자 0과 내부 코드는 원문 그대로 보존합니다.
- 원천별 실질 기준일은 파일명 날짜가 아니라 실제 날짜축의 최댓값입니다.

| 코드 | 원천 파일 | 원천 행 | 적재 행 | 열 | PK | 실질 기준일 | SHA-256 |
|---|---|---:|---:|---:|---|---|---|
| PRBD01N001 | `prbd01n001_data.xlsx` | 21,882 | 21,882 | 58 | `pd_no, pd_exg_mkt, info_base_dt, info_seq` | 2026-08-21 | `574ae5d6c1d98704712c256ed5352cbaed065ea9c3a6eb7b2a52adb305fa9001` |
| PREF01N001 | `pref01n001_data.xlsx` | 1,780 | 1,780 | 98 | `pd_itm_no` | 2026-08-24 | `18c4329d8fc8768d030316816f3e6e48226a3c217db3354245b766a2c6f6c592` |
| PREF02N001 | `pref02n001_data.xlsx` | 6,037 | 6,037 | 49 | `pd_itm_no` | 2026-08-22 | `ca6a274aeaf3f884f2f7635d7802558bc6dabf408871ecb1f71e5a50d9d34067` |
| PRFD01N001 | `prfd01n001_data.xlsx` | 23,676 | 23,676 | 75 | `itm_no` | 2026-08-21 | `81b3ce3f1d5042b32fd52a76acff094fc5b8dd9fa36289af2fb54c195eb5d94c` |

## 스키마별 책임

| 스키마 | 책임 | 물리 테이블 | 뷰/MV |
|---|---|---:|---:|
| `meta` | snapshot, 적재 이력, 컬럼 카탈로그, 상품별 coverage | 4 | 0 |
| `raw` | 공식 XLSX의 컬럼·타입·grain 보존 | 4 | 4 |
| `enriched` | 공통 상품·지표·식별자와 도메인별 1상품 grain | 11 | 2 |
| `relations` | 문서·편입·분류·자회사·상품문서 관계 | 5 | 3 |
| `core` | 기존 Agent 호환 읽기 뷰 | 0 | 5 |

## 식별자와 조인 지도

`enriched.product_master.product_id`가 세 DB를 잇는 정규 식별자입니다. 원천 식별자를 직접 섞어 조인하지 않습니다.

| 상품유형 | `product_id` 규칙 | 원천 식별자 | 도메인 테이블 |
|---|---|---|---|
| 국내채권 | `bond_kr:{pd_no}` | `raw.bond_kr_master.pd_no` | `enriched.bond_kr_product`, `enriched.bond_kr_offer` |
| 국내 ETF | `etf_kr:{pd_itm_no}` | `raw.etf_kr_master.pd_itm_no` | `enriched.etf_kr` |
| 국내 ETN | `etn_kr:{pd_itm_no}` | `raw.etf_kr_master.pd_itm_no` | `enriched.etn_kr` |
| 해외 ETF | `etf_gl:{pd_itm_no}` | `raw.etf_gl_master.pd_itm_no` | `enriched.etf_gl` |
| 해외 ETN | `etn_gl:{pd_itm_no}` | `raw.etf_gl_master.pd_itm_no` | `enriched.etn_gl` |
| 공모펀드 | `fund:{itm_no}` | `raw.fund_pub_master.itm_no` | `enriched.fund` 및 `enriched.fund_pub` 뷰 |
| 사모펀드 | `fund:{itm_no}` | `raw.fund_pub_master.itm_no` | `enriched.fund` |

| 시작 테이블 | 조인 대상 | 조인 조건 | 의미 |
|---|---|---|---|
| `enriched.product_master p` | 도메인 테이블 `d` | `d.product_id = p.product_id` | 상품 공통 속성 + 유형별 속성 |
| `enriched.product_master p` | `enriched.product_metric m` | `m.product_id = p.product_id` | AUM·수익률·보수 등 장형 지표 |
| `enriched.product_master p` | `meta.product_coverage c` | `c.product_id = p.product_id` | holdings·문서·성과 확보 상태 |
| `enriched.product_master p` | `relations.product_classification c` | `c.product_id = p.product_id` | 지역·자산군·섹터·테마 분류 |
| `enriched.product_master p` | `relations.product_holding h` | `h.product_id = p.product_id` | 상품 편입증권과 비중 |
| `relations.product_holding h` | `enriched.security_master s` | `s.security_id = h.security_id` | 편입증권 표준명 |
| `enriched.security_master s` | `enriched.security_identifier i` | `i.security_id = s.security_id` | ISIN·티커·RIC 등 대체 식별자 |
| `relations.product_document pd` | `relations.source_document d` | `d.document_id = pd.document_id` | 상품별 공식 문서와 provenance |

같은 상품의 다중 행이 정상인 테이블(`bond_kr_offer`, `product_metric`, `product_holding`, `product_classification`)은 먼저 grain과 기준일을 제한한 뒤 조인합니다. 그렇지 않으면 행이 곱집합으로 부풀어납니다.

## 지표 의미 사전

`product_metric`은 `(product_id, metric_code, as_of, source, method)` grain입니다. 비교·랭킹에는 `is_available=true AND value IS NOT NULL AND value <> 0`을 모두 적용합니다.

| 상품군 | metric | 값 원천 | 실제 기준일 축 | 단위/주의 |
|---|---|---|---|---|
| 국내 ETF/ETN | `AUM` | `du_last_aum` | `du_upt_dt` | 원천 명시 통화; 0은 값 없음 |
| 국내 ETF/ETN | `RETURN_1Y` | `du_er_1y` | `du_upt_dt` | `%`; 0은 값 없음 |
| 국내 ETF/ETN | `EXPENSE_RATIO` | `cu_charge_rt` | `cu_upt_dt` | `%`; AUM/수익률과 기준일 축이 다름 |
| 해외 ETF/ETN | `AUM` | `du_last_aum` | `du_upt_dt` | 원천 명시 통화; 0은 값 없음 |
| 해외 ETF/ETN | `EXPENSE_RATIO` | `cu_charge_rt` | `cu_upt_dt` | `%` |
| 해외 ETF | `RETURN_1Y` | LSEG 조정가격/total-return | 관측 종료일 | 1년 관측창과 권한이 충족될 때만 외부 2순위 |
| 펀드 | `AUM` | `fd_nast_suma` | `fd_daily_bas_dt` | 원천 명시 통화; 0은 값 없음 |
| 펀드 | `RETURN_1Y` | `fd_yr1_ern_r` | `fd_price_bas_dt` | `%`; 0은 값 없음 |
| 펀드 | `EXPENSE_RATIO` | `ofwk_trus_rwrd_r + or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r` | `fd_price_bas_dt` | 네 구성요소가 모두 있을 때만 계산; `zrin_fd_cmst_rt`는 펀드구성비율이므로 절대 보수로 쓰지 않음 |

## 테이블 목록

| 스키마 | 테이블 | 종류 | grain | PK | 인덱스 | 상태 |
|---|---|---|---|---|---|---|
| `raw` | `bond_kr_master` | table | 채권×시장×정보기준일×판매 LOT | `pd_no, pd_exg_mkt, info_base_dt, info_seq` | pd_no,pd_exg_mkt,info_base_dt,info_seq | 구현=구현, 배포=미배포 |
| `raw` | `etf_kr_master` | table | 국내 ETF/ETN 상품 | `pd_itm_no` | pd_itm_no | 구현=구현, 배포=미배포 |
| `raw` | `etf_gl_master` | table | 해외 ETF/ETN 상품 | `pd_itm_no` | pd_itm_no | 구현=구현, 배포=미배포 |
| `raw` | `fund_pub_master` | table | 펀드 상품(공모·사모) | `itm_no` | itm_no | 구현=구현, 배포=미배포 |
| `meta` | `dataset_snapshot` | table | 데이터셋 빌드 스냅샷 | `snapshot_id` | PK만 | 구현=구현, 배포=미배포 |
| `meta` | `load_run` | table | 1회 적재 실행 | `run_id` | PK만 | 구현=구현, 배포=미배포 |
| `meta` | `column_catalog` | table | 물리 컬럼 1개 | `table_schema, table_name, ordinal_position` | PK만 | 구현=구현, 배포=미배포 |
| `meta` | `product_coverage` | table | 상품×스냅샷 | `product_id` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `product_master` | table | 공통 상품 1개 | `product_id` | product_type, name, source_table,source_key | 구현=구현, 배포=미배포 |
| `enriched` | `bond_kr_product` | table | 국내채권 pd_no 1개 | `product_id` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `bond_kr_offer` | table | 채권×시장×기준일×판매 LOT | `pd_no, exchange_market, info_base_dt, info_seq` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `etf_kr` | table | 국내 ETF 1개 | `product_id` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `etf_gl` | table | 해외 ETF 1개 | `product_id` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `etn_kr` | table | 국내 ETN 1개 | `product_id` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `etn_gl` | table | 해외 ETN 1개 | `product_id` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `fund` | table | 펀드 itm_no 1개 | `product_id` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `product_metric` | table | 상품×지표×기준일×출처×방법 | `metric_id` | product_id,metric_code, metric_code,value DESC WHERE is_available | 구현=구현, 배포=미배포 |
| `enriched` | `security_master` | table | 증권 1개 | `security_id` | PK만 | 구현=구현, 배포=미배포 |
| `enriched` | `security_identifier` | table | 증권×식별자 유형×값 | `security_id, id_type, id_value` | id_type,id_value | 구현=구현, 배포=미배포 |
| `relations` | `source_document` | table | 외부 근거 문서 1개 | `document_id` | PK만 | 구현=구현, 배포=미배포 |
| `relations` | `product_holding` | table | 상품×편입증권×기준일×문서 | `holding_id` | product_id,as_of, security_id,as_of | 구현=구현, 배포=미배포 |
| `relations` | `product_classification` | table | 상품×분류 유형×값×기준일 | `classification_id` | PK만 | 구현=구현, 배포=미배포 |
| `relations` | `company_subsidiary` | table | 기업×자회사×기준일×문서 | `relation_id` | PK만 | 구현=구현, 배포=미배포 |
| `relations` | `product_document` | table | 상품×문서×관계유형 | `product_id, document_id, relation_type` | PK만 | 구현=구현, 배포=미배포 |

## 뷰와 materialized view

| 이름 | 종류 | 원천 | 목적/필터 |
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
| `relations.etf_holding` | view | `relations.product_holding` | 구 관계명 호환 |
| `relations.etf_theme` | view | `relations.product_classification` | classification_type='theme' |
| `relations.company_subsidiary` | table | `relations.company_subsidiary` | 정식 이름이 구 계약과 동일 |
| `vec.doc_chunk` | view | `vec.document_chunk` | 구 벡터명 호환 |
| `vec.schema_index` | view | `vec.schema_terms_all` | 구 벡터명 호환 |
| `enriched.product_search` | materialized view | `product_master+product_metric+product_coverage` |  |

## 핵심 데이터 규칙

- `buyable_quantity`는 저장·표시 전용이며 구매가능 판정, 필터, 정렬에 사용하지 않습니다.
- 채권 구매가능 가정은 최신 정본 존재와 명시적 만기 여부만 사용하고 판정 규칙을 함께 저장합니다.
- 국내 원천의 ETF/ETN은 `pd_grp_no`로 분리하고 ETN에는 편입종목 개념을 적용하지 않습니다.
- 260824 펀드는 `itm_no`당 1행이며 공모·사모를 모두 보존하고 `fund_pub` 뷰만 공모를 노출합니다.
- 지표의 0/NULL/기준일 미확보는 `is_available=false`이며 랭킹과 비교에서 제외합니다.
- `product_coverage.unavailable`은 관계 미확보이며 ‘보유하지 않음’을 뜻하지 않습니다.
- 주최측에 존재하는 지표 축이 우선이며 축 자체가 없을 때만 cutoff를 통과한 외부값을 사용합니다.
- 해외 ETF의 `pd_lstg_dt` 공식 의미는 설정일이며 `inception_date`에 저장합니다. 실제 상장일로 답하지 않습니다.
- 내부 코드에 이름 컬럼이나 공식 코드표가 없으면 원문만 반환하고 의미를 추정하지 않습니다.

## 안전한 SQL 패턴

상품명 정확 조회 후 지표를 붙이는 기본 패턴입니다.

```sql
SELECT p.product_id, p.product_name, m.metric_code, m.value, m.unit,
       m.as_of, m.source, m.source_column
FROM enriched.product_master p
LEFT JOIN enriched.product_metric m ON m.product_id = p.product_id
WHERE p.product_name = %(product_name)s
ORDER BY m.metric_code, m.as_of DESC NULLS LAST;
```

TOP-N 지표는 0·결측·미확보를 먼저 제외합니다.

```sql
SELECT p.product_id, p.product_name, m.value, m.unit, m.as_of, m.source
FROM enriched.product_metric m
JOIN enriched.product_master p USING (product_id)
WHERE p.product_type = 'ETF_KR' AND m.metric_code = 'AUM'
  AND m.is_available AND m.value IS NOT NULL AND m.value <> 0
ORDER BY m.value DESC
LIMIT 10;
```

채권 판매가능 질의는 `buyable_quantity`를 조건으로 쓰지 않습니다. `is_assumed_purchasable`과 `purchasability_rule`을 함께 반환합니다. 편입 검색 결과가 0행이면 먼저 `meta.product_coverage.holdings_status`를 확인해 `available`일 때만 ‘보유하지 않음’으로 해석합니다.

## LLM/Agent evidence 계약

모든 답변 레코드는 최소한 `product_id`, 표시명, 사용한 물리 컬럼 또는 `metric_code`, `value`, `unit`, 실제 `as_of`, `source`를 보존합니다. 관계 답변은 `document_id` 또는 원천 관계 ID와 관계 `as_of`를 추가합니다.

- 값을 찾지 못하면 `NULL`을 임의의 0으로 바꾸지 말고 ‘값 없음’으로 답합니다.
- 이름 유사도만으로 상품·증권·기업 식별자를 합치지 않습니다. 식별자가 해소되지 않으면 `unresolved` 또는 ABSTAIN입니다.
- 코드 문자열의 뜻, 해외 ETF 설정일과 상장일, 관계 triple 부재를 추측하지 않습니다.
- Graph 후보를 RDB에 넘길 때 문자열로 `IN (...)`을 조립하지 말고 배열 파라미터 `product_id = ANY(%s)`를 사용합니다.
- 숫자 주장마다 서로 다른 실제 기준일 축을 유지합니다. 한 행의 snapshot 날짜를 모든 지표 날짜로 복사하지 않습니다.

## 물리 테이블 상세

### `raw.bond_kr_master`

- 종류: table
- 설명: PRBD01N001 공식 원천 21,882행
- grain: 채권×시장×정보기준일×판매 LOT
- PK: `pd_no, pd_exg_mkt, info_base_dt, info_seq`
- 인덱스: pd_no,pd_exg_mkt,info_base_dt,info_seq
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `after_tax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 개인 세후 운용수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 2 | `applied_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 민평수익률/민평금리 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 3 | `avg_annual_tax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 세후 연평균수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 4 | `bdbns_abl_chnl_nm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 채권매매가능채널구분명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 5 | `bdbns_abl_chnl_tcd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 채권매매가능채널구분코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 6 | `bd_inrt_tcd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 금리구분 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 7 | `bd_intp_tcd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 이자지급구분 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 8 | `bd_knd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 예탁원 기준 채권종류명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 9 | `bd_ofr_tcd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 모집구분 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 10 | `bd_tisu_a` | `numeric(26,8)` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 총발행금액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 11 | `buyable_quantity` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 매수가능수량 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 12 | `buy_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 매수수익률/매수금리 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 13 | `corp_after_tax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 법인 세후 투자수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 14 | `corp_pretax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 법인 세전 투자수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 15 | `cov` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 컨벡시티 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 16 | `crd_grd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 적용신용등급 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 17 | `crd_grd_dt` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 신용등급 적용일자(등급 미변경 시 과거 일자로 유지될 수 있음) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 18 | `curr_cd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 통화코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 19 | `depo_equiv_yield_154` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 예금환산수익률(세율 15.4 기준) | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 20 | `depo_equiv_yield_495` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 은행환산수익률(세율 49.5 기준) | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 21 | `dirty` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 이자부단가/Dirty Price | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 22 | `dur` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 듀레이션 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 23 | `eval_price` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 평가일단가/Clean Price 성격 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 24 | `exg_close_price` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 장내 채권종가 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 25 | `exg_close_price_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 장내 채권종가/종가수익률 기준일 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 26 | `exg_close_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 장내 종가수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 27 | `exrt_grte_ern_r` | `numeric(20,12)` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 만기보장수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 28 | `exrt_grte_ern_r_tcd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 만기보장수익률구분코드 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 29 | `exrt_rpy_r` | `numeric(20,12)` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 만기상환율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 30 | `info_base_dt` | `text` | N | 3 |  | 공식 문서 미표기 | info_base_dt | 판매/민평 공통 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 31 | `info_seq` | `bigint` | N | 4 |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 동일 종목/시장/기준일 내 판매 LOT 구분 순번 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 32 | `isu_bal_amt` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 발행잔액/발행금액잔액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 33 | `isu_dt` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 발행일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 34 | `mat_dt` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상환일자(영구채는 1차 콜행사개시일) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 35 | `ndy_applied_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 익일 민평수익률/민평금리 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 36 | `ndy_cov` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 익일 컨벡시티 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 37 | `ndy_dirty` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 익일 이자부단가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 38 | `ndy_dur` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 익일 듀레이션 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 39 | `ndy_eval_price` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 익일 평가일단가 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 40 | `pd_abrv_eng_nm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품영문약어명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 41 | `pd_abrv_nm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품약어명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 42 | `pd_ctry_cd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 국가코드: 종목번호 앞 2자리(KR 등) | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 43 | `pd_eng_nm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품영문명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 44 | `pd_exg_mkt` | `text` | N | 2 |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 거래구분 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 45 | `pd_nm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품명/채권명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 46 | `pd_no` | `text` | N | 1 |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품번호/채권종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 47 | `pd_pbcm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 발행기관/발행자명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 48 | `pd_pen_tr_yn` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 퇴직연금 편입 가능 여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 49 | `pd_risk_gcd` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품위험등급 원문 코드 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 50 | `pd_risk_nm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품위험등급명 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 51 | `pd_std_info_update` | `text` | Y |  |  | 공식 문서 미표기 | pd_std_info_update | 민평정보 기준일/최근 업데이트 일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 52 | `pref_tax_yield` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 세금우대 세후 운용수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 53 | `remaining_days` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 잔존일수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 54 | `sale_yield_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | sale_yield_base_dt | 판매수익률 기준일 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 55 | `srfc_irt` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 표면이자율/쿠폰금리 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 56 | `std_pd_mcls_nm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품중분류명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 57 | `std_pd_scls_nm` | `text` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 상품소분류명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 58 | `trade_price` | `double precision` | Y |  |  | 공식 문서 미표기 | info_base_dt,pd_std_info_update,sale_yield_base_dt | 매매단가(표준투입단가) | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |

### `raw.etf_kr_master`

- 종류: table
- 설명: PREF01N001 공식 원천 1,780행
- grain: 국내 ETF/ETN 상품
- PK: `pd_itm_no`
- 인덱스: pd_itm_no
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `cu_base_index` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 기초지수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 2 | `cu_charge_etc_rt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 기타비용요율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 3 | `cu_charge_rt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 총보수요율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 4 | `cu_fund_mgmt_co` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 운용사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 5 | `cu_lev_fector` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 배수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 6 | `cu_strtegy` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 운용전략 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 7 | `cu_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt | 변동갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 8 | `du_bpr` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 기준가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 9 | `du_chas_errt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 추적오차율 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 10 | `du_chas_errt_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 추적오차율 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 11 | `du_clpr` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 종가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 12 | `du_diff_rt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 괴리율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 13 | `du_diff_rt_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 괴리율 기준일 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 14 | `du_er_1d` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 수익률_1D | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 15 | `du_er_1m` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 수익률_1M | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 16 | `du_er_1y` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 수익률_1Y | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 17 | `du_er_3m` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 수익률_3M | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 18 | `du_er_6m` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 수익률_6M | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 19 | `du_er_ytd` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 수익률_YTD | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 20 | `du_hpr` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 고가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 21 | `du_last_aum` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 최종AUM | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 22 | `du_last_nav` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 최종NAV | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 23 | `du_lpr` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 시가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 24 | `du_nav_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | NAV 기준일 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 25 | `du_nav_rnf_amt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 전일NAV등락금액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 26 | `du_nav_yday` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 전일NAV | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 27 | `du_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | du_upt_dt | 일간갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 28 | `du_val_1d` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 일거래대금 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 29 | `du_val_1m` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 일거래대금평균_1M | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 30 | `du_val_5d` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 일거래대금평균_5D | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 31 | `du_vlty_1m` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 최근 20거래일 연환산 변동성(%) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 32 | `du_vlty_1y` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 최근 252거래일 연환산 변동성(%) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 33 | `du_vlty_3m` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 최근 60거래일 연환산 변동성(%) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 34 | `du_vlty_6m` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 최근 120거래일 연환산 변동성(%) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 35 | `du_vlty_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 변동성 산출 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 36 | `du_vol_1d` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 일거래량 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 37 | `du_vol_avg_1m` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 거래량평균_1M | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 38 | `du_vol_avg_5d` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 거래량평균_5D | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 39 | `fn_average_coupon` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 평균쿠폰이자율 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 40 | `fn_average_maturity` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 평균잔존만기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 41 | `fn_average_quality` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 평균신용품질 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 42 | `fn_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | fn_base_dt | 펀더멘털 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 43 | `fn_effective_duration` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 듀레이션 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 44 | `fn_effective_maturity` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 실질만기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 45 | `fn_modified_duration` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 수정듀레이션 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 46 | `fn_nominal_maturity` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 명목만기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 47 | `fn_portfolio_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 포트폴리오 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 48 | `pd_abrv_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품약어명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 49 | `pd_circ_net_tamt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 유통순자산총액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 50 | `pd_circ_stk_cnt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 유통주식수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 51 | `pd_curr_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품통화코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 52 | `pd_curr_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품통화명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 53 | `pd_divd_amt_ann` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 연간 추정 분배금 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 54 | `pd_divd_amt_pshr` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 주당 분배금(원천 우선, 없으면 회당 추정) | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 55 | `pd_dvid_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 분배정보 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 56 | `pd_dvid_cycl` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 분배주기(A/Q/M/S) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 57 | `pd_dvid_inc_dist` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 원천 성과배분/분배금 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 58 | `pd_dvid_nav` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 분배금 계산 기준 NAV | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 59 | `pd_dvid_pay_cnt` | `numeric(28,0)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 연간 지급횟수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 60 | `pd_dvid_pay_months` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 분배 지급월 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 61 | `pd_dvid_prc_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 분배금 계산 NAV 기준일 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 62 | `pd_dvid_tax_basis` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 분배 과세기준 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 63 | `pd_dvid_yield` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 연환산 분배수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 64 | `pd_exg_mkt_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 거래소코드 [공식 Nullable=NO이나 정본 NULL 3건을 손실 없이 허용] | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 65 | `pd_exg_mkt_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 거래소명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 66 | `pd_grp_no` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품군종류 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 67 | `pd_isin_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | Refinitiv ISIN | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 68 | `pd_itm_no` | `text` | N | 1 |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 69 | `pd_itm_no_ma` | `text` | N |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품번호_미래에셋 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 70 | `pd_lst_stk_cnt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품상장주식수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 71 | `pd_lste_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품거래종료일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 72 | `pd_lstg_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품거래가능일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 73 | `pd_mkt_id` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품거래시장코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 74 | `pd_mkt_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품거래시장 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 75 | `pd_net_tamt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 순자산총액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 76 | `pd_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 77 | `pd_pen_risk_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 연금거래위험구분 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 78 | `pd_pen_tr_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 연금거래가능여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 79 | `pd_ric` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | Refinitiv RIC | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 80 | `pd_risk_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품등급코드 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 81 | `pd_risk_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품등급명 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 82 | `pd_sale_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품판매여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 83 | `pd_sect_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | ETF 섹터코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 84 | `pd_spac_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | SPAC 여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 85 | `pd_stk_cnt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상장주식수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 86 | `pd_ticker` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | Refinitiv 티커 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 87 | `pd_tr_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 상품거래정지혀부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 88 | `ref_ast_type` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | refinitiv 자산유형 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 89 | `ref_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | ref_base_dt | refinitiv 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 90 | `ref_base_index` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | refinitiv 벤치마크 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 91 | `ref_fund_mgmt_co` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | refinitiv 운용사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 92 | `ref_geo_focus` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | refinitiv 투자지역 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 93 | `ru_mkt_price` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 현재가 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 94 | `ru_mkt_volume` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 거래량 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 95 | `wu_core_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 핵심ETF여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 96 | `wu_inv_ast_type` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 투자자산군 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 97 | `wu_inv_rgn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,fn_base_dt,ref_base_dt | 투자지역 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 98 | `wu_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | wu_upt_dt | 주간갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |

### `raw.etf_gl_master`

- 종류: table
- 설명: PREF02N001 공식 원천 6,037행
- grain: 해외 ETF/ETN 상품
- PK: `pd_itm_no`
- 인덱스: pd_itm_no
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `cu_base_index` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 기초지수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 2 | `cu_charge_rt` | `numeric(18,6)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 연간보수율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 3 | `cu_etn_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | ETN 여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 4 | `cu_fund_mgmt_co` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 운용사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 5 | `cu_index_repl_mthd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 인덱스 복제방법 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 6 | `cu_index_tracking_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 인덱스 추적 여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 7 | `cu_inverse_short_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 인버스 또는 숏 여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 8 | `cu_lev_fector` | `numeric(18,6)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 배수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 9 | `cu_strtegy` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 운용전략 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 10 | `cu_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt | 변동갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 11 | `du_base_dt_match_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | NAV/종가 기준일 일치 여부 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 12 | `du_bpr` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 기준가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 13 | `du_clpr` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 종가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 14 | `du_clpr_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | du_clpr_base_dt | 선택된 종가의 원천 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 15 | `du_clpr_src` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 선택된 종가 원천 컬럼 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 16 | `du_diff_rt` | `numeric(28,6)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 종가 대비 추정 NAV 괴리율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 17 | `du_er_1d` | `numeric(28,6)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 수익률_1D | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 18 | `du_hpr` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 고가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 19 | `du_last_aum` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 일간 순자산총액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 20 | `du_last_nav` | `numeric(28,6)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 추정 주당 NAV | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 21 | `du_lpr` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 저가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 22 | `du_nav_base_dt` | `text` | Y |  |  | 공식 문서 미표기 | du_nav_base_dt | NAV 원천 etf_reference 기준일 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 23 | `du_opr` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 시가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 24 | `du_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | du_upt_dt | 일간갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 25 | `du_val_1d` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 외화거래대금 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 26 | `du_vol_1d` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 거래량 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 27 | `pd_abrv_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 상품약어명_티커 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 28 | `pd_curr_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 펀드통화코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 29 | `pd_exg_mkt_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 거래소코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 30 | `pd_grp_no` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 상품군종류 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 31 | `pd_isin_cd` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | ISIN 코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 32 | `pd_itm_no` | `text` | N | 1 |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 해외 ETF RIC | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 33 | `pd_itm_no_ma` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 해외 ETF RIC_PDF 조인키 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 34 | `pd_lipper_id` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | Lipper 펀드코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 35 | `pd_lstg_dt` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 설정일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 36 | `pd_lst_price` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 액면가 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 37 | `pd_lst_stk_cnt` | `numeric(28,2)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 상장주식수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 38 | `pd_mkt_id` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 거래소국가코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 39 | `pd_nm` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 40 | `pd_sale_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 판매여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 41 | `pd_trd_ccy` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 거래통화코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 42 | `pd_tr_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 거래정지여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 43 | `pd_us_cik` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 미국 CIK | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 44 | `ru_mkt_price` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 실시간 현재가 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 45 | `ru_mkt_volume` | `numeric(28,8)` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 실시간 거래량 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 46 | `wu_core_yn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 핵심 ETF 여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 47 | `wu_inv_ast_type` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 투자자산군 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 48 | `wu_inv_rgn` | `text` | Y |  |  | 공식 문서 미표기 | cu_upt_dt,du_upt_dt,wu_upt_dt,du_clpr_base_dt,du_nav_base_dt | 투자지역 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 49 | `wu_upt_dt` | `text` | Y |  |  | 공식 문서 미표기 | wu_upt_dt | 주간갱신일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |

### `raw.fund_pub_master`

- 종류: table
- 설명: PRFD01N001 공식 원천 23,676행
- grain: 펀드 상품(공모·사모)
- PK: `itm_no`
- 인덱스: itm_no
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `bmrk_eng_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 벤치마크영문명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 2 | `bmrk_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 벤치마크명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 3 | `bns_bpr` | `numeric(38,15)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 매매기준가 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 4 | `curr_cd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 통화코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 5 | `exchdg_yn` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 환헤지여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 6 | `fd_daily_bas_dt` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt | 펀드데일리정보 기준일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 7 | `fd_estb_ctry_cd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드설립국가코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 8 | `fd_ivst_rgn_desc` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드투자지역구분코드 설명 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 9 | `fd_last_dstb_actg_bss_dt` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 최근 분배 회계기초일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 10 | `fd_last_dstb_actg_eot_dt` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 최근 분배 회계기말일자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 11 | `fd_last_dstb_r` | `numeric(20,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 최근 분배율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 12 | `fd_mm18_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 18개월수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 13 | `fd_mm1_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 1개월수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 14 | `fd_mm3_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 3개월수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 15 | `fd_mm6_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 6개월수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 16 | `fd_nast_suma` | `numeric(22,4)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 순자산 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 17 | `fd_price_bas_dt` | `text` | Y |  |  | 공식 문서 미표기 | fd_price_bas_dt | 펀드 기준가/수익률 기준일자 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 18 | `fd_prsv_r` | `numeric(20,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 보전율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 19 | `fd_sbpr` | `numeric(30,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 시가평가금액 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 20 | `fd_set_pcd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드설정유형코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 21 | `fd_wk1_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 1주일수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 22 | `fd_yr1_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 1년수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 23 | `fd_yr2_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 2년수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 24 | `fd_yr3_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 3년수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 25 | `fd_yr5_ern_r` | `numeric(30,2)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드 5년수익률 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 26 | `frc_bpr_itm_yn` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 외화기준가종목여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 27 | `fss_itm_no` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 금융감독원종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 28 | `han_clas_fee_type` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 클래스 수수료 부과 유형 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 29 | `han_clas_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 클래스 한글 표기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 30 | `han_clas_policies` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 클래스 부가 정책 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 31 | `han_clas_sales_channel` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 클래스 판매채널 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 32 | `hdge_fd_yn` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 헤지펀드여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 33 | `int_dvd_desc` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 이자배당구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 34 | `itm_abrv_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 종목약어명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 35 | `itm_eabrv_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 종목영문약어명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 36 | `itm_eng_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 종목영문명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 37 | `itm_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 종목명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 38 | `itm_no` | `text` | N | 1 |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 39 | `kofia_fd_ccd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 금융투자협회펀드분류코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 40 | `ksd_itm_no` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 예탁원종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 41 | `mtco_itm_no` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 운용사종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 42 | `ofsfd_yn` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 역외펀드여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 43 | `ofwk_trus_rwrd_r` | `numeric(20,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 일반사무관리보수 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 44 | `or_attr_desc` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 운용속성구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 45 | `or_co_rwrd_r` | `numeric(20,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 집합투자업자보수 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 46 | `or_co_xtn_itt_cd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 운용회사대외기관코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 47 | `ovrs_fd_desc` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 해외펀드구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 48 | `pers_corp_desc` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 개인법인구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 49 | `pfiv_sale_cntl_tcd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 전문투자자판매제어구분코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 50 | `prfd_attr_cds` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드별속성코드 목록(쉼표 구분) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 51 | `prfd_attr_cnt` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 펀드별속성 개수 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 52 | `prfd_attr_search_text` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 상품검색용 속성 코드/명칭 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 53 | `prvo_fd_desc` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 사모펀드구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 54 | `prvo_pbff_desc` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 사모/공모구분코드 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 55 | `rptt_ksd_itm_no` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 대표예탁원종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 56 | `sale_co_rwrd_r` | `numeric(20,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 판매회사보수 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 57 | `sale_yn` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 판매여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 58 | `std_itm_no` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 표준종목번호 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 59 | `thco_sale_yn` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 당사판매여부 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 60 | `trusc_rwrd_r` | `numeric(20,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 신탁업자보수 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 61 | `trusc_xtn_itt_cd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 수탁회사대외기관코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 62 | `zrin_attr_nms` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인속성명 목록(쉼표 구분) | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 63 | `zrin_btyp_cd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인대유형코드 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 64 | `zrin_btyp_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인대유형명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 65 | `zrin_dmst_bd_cmst_rt` | `numeric(26,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인국내채권구성비율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 66 | `zrin_dmst_stk_cmst_rt` | `numeric(26,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인국내주식구성비율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 67 | `zrin_etc_ast_cmst_rt` | `numeric(26,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인기타자산구성비율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 68 | `zrin_fd_cmst_rt` | `numeric(26,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인펀드구성비율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 69 | `zrin_fd_ivst_risk_gcd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인펀드투자위험등급코드 [공식 Nullable=NO이나 정본 NULL 14,987건을 손실 없이 허용] | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 70 | `zrin_fd_ivst_risk_grd_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인펀드투자위험등급명 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 71 | `zrin_liqt_cmst_rt` | `numeric(26,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인유동성구성비율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 72 | `zrin_ovrs_bd_cmst_rt` | `numeric(26,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인해외채권구성비율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 73 | `zrin_ovrs_stk_cmst_rt` | `numeric(26,12)` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인해외주식구성비율 | 빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 74 | `zrin_pcd` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인유형코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |
| 75 | `zrin_ptn_nm` | `text` | Y |  |  | 공식 문서 미표기 | fd_daily_bas_dt,fd_price_bas_dt | 제로인유형명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 공식 XLSX 값 그대로; 공백만 NULL; PK는 NOT NULL |

### `meta.dataset_snapshot`

- 종류: table
- 설명: 버전·배포일·도메인별 실질 기준일·8개 원천 해시
- grain: 데이터셋 빌드 스냅샷
- PK: `snapshot_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `snapshot_id` | `uuid` | N | 1 |  |  |  | 스냅샷 식별자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `dataset_version` | `text` | N |  |  |  |  | 데이터 버전 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `release_date` | `date` | N |  |  |  |  | 주최측 배포일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `cutoff_date` | `date` | N |  |  |  |  | 외부 근거 허용 상한 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `domain_as_of` | `jsonb` | N |  |  |  |  | 도메인별 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `source_files` | `jsonb` | N |  |  |  |  | 원천 파일명·행/열·SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `source_hash` | `text` | N |  |  |  |  | 전체 원천 manifest SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `built_at` | `timestamptz` | N |  |  |  |  | 빌드 완료 시각 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `meta.load_run`

- 종류: table
- 설명: 단계·시작/종료·행 수·검증 결과와 실패 사유
- grain: 1회 적재 실행
- PK: `run_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `meta.column_catalog`

- 종류: table
- 설명: 공식 설명·타입·단위·기준일·처리 규칙·출처 우선순위
- grain: 물리 컬럼 1개
- PK: `table_schema, table_name, ordinal_position`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `meta.product_coverage`

- 종류: table
- 설명: 관계·문서·성과 확보/미확보 상태와 사유
- grain: 상품×스냅샷
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `enriched.product_master`

- 종류: table
- 설명: 전 상품 공통 식별자와 유형·국내/해외·통화·활성 상태
- grain: 공통 상품 1개
- PK: `product_id`
- 인덱스: product_type, name, source_table,source_key
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `enriched.bond_kr_product`

- 종류: table
- 설명: 최신 offer에서 접은 상품 속성과 보수적 구매가능 가정
- grain: 국내채권 pd_no 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `pd_no` | `text` | N |  |  |  |  | 채권 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `name` | `text` | N |  |  |  |  | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `issuer` | `text` | Y |  |  |  |  | 발행사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `credit_rating` | `text` | Y |  |  |  |  | 신용등급 원문; NULL은 필터·랭킹 제외(국채 무등급을 최저등급으로 간주 금지) | NULL=unavailable; sovereign unrated is not default risk | 주최측(1순위) | 파생 |
| 6 | `currency` | `text` | Y |  |  |  |  | 통화 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `issue_date` | `date` | Y |  |  |  |  | 발행일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `maturity_date` | `date` | Y |  |  |  |  | 만기일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `risk_code` | `text` | Y |  |  |  |  | 위험등급 코드 원문 | 빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지 | 주최측(1순위) | 파생 |
| 10 | `risk_name` | `text` | Y |  |  |  |  | 위험등급명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `is_assumed_purchasable` | `boolean` | N |  |  |  |  | 최신 존재·명시 만기/종료만 제외 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 12 | `purchasable_rule` | `text` | N |  |  |  |  | BUYABLE_QUANTITY 미사용 판정 규칙 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 13 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 채권 정보 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `enriched.bond_kr_offer`

- 종류: table
- 설명: 채권 수익률·가격·판매 LOT; BUYABLE_QUANTITY는 저장 전용
- grain: 채권×시장×기준일×판매 LOT
- PK: `pd_no, exchange_market, info_base_dt, info_seq`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `enriched.etf_kr`

- 종류: table
- 설명: pd_grp_no='ETF'만 명시 분리
- grain: 국내 ETF 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 공통 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `pd_itm_no` | `text` | N |  |  |  |  | 원천 상품번호 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `name` | `text` | N |  |  |  |  | 상품명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `ticker` | `text` | Y |  |  |  |  | 국내 티커 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `isin` | `text` | Y |  |  |  |  | ISIN | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `manager` | `text` | Y |  |  |  |  | 운용사 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `base_index` | `text` | Y |  |  |  |  | 기초지수; 알려진 비값 문자열은 NULL이며 필터·랭킹 제외 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `currency` | `text` | Y |  |  |  |  | 통화 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `listing_date` | `date` | Y |  |  |  |  | 상장일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `delisting_date` | `date` | Y |  |  |  |  | 상장종료일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `effective_as_of` | `date` | N |  |  |  | effective_as_of | 실질 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `enriched.etf_gl`

- 종류: table
- 설명: pd_grp_no='ETF'만 명시 분리
- grain: 해외 ETF 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `enriched.etn_kr`

- 종류: table
- 설명: 국내 ETF 원천의 pd_grp_no='ETN' 분리
- grain: 국내 ETN 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `enriched.etn_gl`

- 종류: table
- 설명: 해외 ETF 원천의 pd_grp_no='ETN' 분리
- grain: 해외 ETN 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `enriched.fund`

- 종류: table
- 설명: 공모·사모 전체 보존; fund_pub 뷰에서 공모만 노출
- grain: 펀드 itm_no 1개
- PK: `product_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `enriched.product_metric`

- 종류: table
- 설명: AUM·수익률·보수 등 공통 지표와 값 미확보 상태
- grain: 상품×지표×기준일×출처×방법
- PK: `metric_id`
- 인덱스: product_id,metric_code, metric_code,value DESC WHERE is_available
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `enriched.security_master`

- 종류: table
- 설명: 편입증권·기업의 통합 식별자
- grain: 증권 1개
- PK: `security_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `security_id` | `text` | N | 1 |  |  |  | 결정적 증권 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `display_name` | `text` | N |  |  |  |  | 표시명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `security_type` | `text` | N |  |  |  |  | equity/bond/company/unknown | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `issuer_name` | `text` | Y |  |  |  |  | 발행사명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `country_code` | `text` | Y |  |  |  |  | 국가 코드 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `enriched.security_identifier`

- 종류: table
- 설명: ISIN·국내 티커·RIC·Bloomberg 표기 통합
- grain: 증권×식별자 유형×값
- PK: `security_id, id_type, id_value`
- 인덱스: id_type,id_value
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `security_id` | `text` | N | 1 | enriched.security_master.security_id |  |  | 증권 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `id_type` | `text` | N | 2 |  |  |  | ISIN/KR_TICKER/RIC/BLOOMBERG | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `id_value` | `text` | N | 3 |  |  |  | 식별자 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `is_primary` | `boolean` | N |  |  |  |  | 해당 유형의 대표 식별자 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `relations.source_document`

- 종류: table
- 설명: 문서명·발행기관·발행일·URL·원천 해시
- grain: 외부 근거 문서 1개
- PK: `document_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
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

### `relations.product_holding`

- 종류: table
- 설명: ETF·펀드 공통 편입관계; 미확보는 coverage로 분리
- grain: 상품×편입증권×기준일×문서
- PK: `holding_id`
- 인덱스: product_id,as_of, security_id,as_of
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `holding_id` | `text` | N | 1 |  |  |  | 결정적 관계 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `product_id` | `text` | N |  | enriched.product_master.product_id |  |  | 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `security_id` | `text` | N |  | enriched.security_master.security_id |  |  | 편입증권 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `weight` | `numeric` | Y |  |  | percent |  | 편입비중 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 5 | `unit` | `text` | N |  |  |  |  | 비중 단위 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `as_of` | `date` | N |  |  |  | as_of | 편입 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 7 | `source_document_id` | `text` | N |  | relations.source_document.document_id |  |  | 직접 근거 문서 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 8 | `source` | `text` | N |  |  |  |  | 운용사/DART 원천 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |

### `relations.product_classification`

- 종류: table
- 설명: 상품↔테마·섹터·지역 관계
- grain: 상품×분류 유형×값×기준일
- PK: `classification_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `classification_id` | `text` | N | 1 |  |  |  | 결정적 관계 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `product_id` | `text` | N |  | enriched.product_master.product_id |  |  | 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `classification_type` | `text` | N |  |  |  |  | theme/sector/region | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `classification_value` | `text` | N |  |  |  |  | 원천 분류값 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `as_of` | `date` | N |  |  |  | as_of | 분류 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `source_document_id` | `text` | Y |  | relations.source_document.document_id |  |  | 직접 근거 문서 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `source` | `text` | N |  |  |  |  | 원천 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `relations.company_subsidiary`

- 종류: table
- 설명: 기업↔자회사 n-ary 관계와 지분율
- grain: 기업×자회사×기준일×문서
- PK: `relation_id`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `relation_id` | `text` | N | 1 |  |  |  | 결정적 관계 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `parent_security_id` | `text` | N |  | enriched.security_master.security_id |  |  | 모회사 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `child_security_id` | `text` | N |  | enriched.security_master.security_id |  |  | 자회사 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `ownership_pct` | `numeric` | Y |  |  | percent |  | 지분율 | NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시 | 주최측(1순위) | 파생 |
| 5 | `as_of` | `date` | N |  |  |  | as_of | 공시 기준일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 6 | `source_document_id` | `text` | N |  | relations.source_document.document_id |  |  | DART 근거 문서 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 7 | `source` | `text` | N |  |  |  |  | 원천 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |

### `relations.product_document`

- 종류: table
- 설명: 상품과 투자설명서·보고서·구성내역 연결
- grain: 상품×문서×관계유형
- PK: `product_id, document_id, relation_type`
- 인덱스: PK만
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `product_id` | `text` | N | 1 | enriched.product_master.product_id |  |  | 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `document_id` | `text` | N | 2 | relations.source_document.document_id |  |  | 문서 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `relation_type` | `text` | N | 3 |  |  |  | prospectus/report/holdings | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## 적재·검증·권한

1. 정상 XLSX 8개 집합, SHA-256, 행·열, 헤더, PK, cutoff를 검사합니다.
2. `raw_next` 적재 후 `meta_next`, `enriched_next`, `relations_next`, `core_next`를 생성합니다.
3. PK 유일성, FK orphan, 지표 날짜축, 0/NULL, 구매가능 규칙을 검증합니다.
4. 모든 계층 검증 후 `*_next`를 정식 이름으로 승격하고 기존 정식 스키마는 `*_prev`로 보존합니다.
5. 승격 직후 [읽기 권한 SQL](../../sql/v2/100_readonly_grants.sql)을 다시 적용합니다.
