# 현재 데이터 구축 프로세스와 DB 구조

> 주최측 배포본: 2026-08-24 · 외부 데이터 허용 상한: `as_of <= 2026-08-24`

실제 빌더와 생성물을 기준으로 한 현행 구조다. 파일 통계는 자동 생성되는 `DATA_INVENTORY.md`, 물리 스키마는 `table_definition_v1_0.csv`를 정본으로 삼는다.

## 1. 현재 상태

| 계층 | 구현 상태 | 검증 기준 |
|---|---|---|
| PostgreSQL RDB | `raw`·`enriched`·`relations` 11테이블 | PK/FK 19개, cutoff 위반 0 |
| Schema Vector | `bond_schema_terms` 130건, `schema_terms_all` 188건 | 1024차원, embedding NULL 0 |
| Graph schema | TBox 5파일 커밋 | rdflib 검증 |
| Graph instances | ABox `instances_*.ttl` 5파일 생성 | `validate_ontology.py` |
| Graph runtime | pyoxigraph loader·SPARQL 엔진 | 미구현 |
| Content Vector | 후보 데이터만 식별 | 미구현 |

현재 상태는 **TBox/ABox TTL 생성 완료**이며 GraphDB 구축 완료로 표현하지 않는다.

## 2. 데이터 흐름

```mermaid
flowchart LR
    A[주최측 08-24 Excel 8개] -->|convert_xlsx_to_csv.py| B[data/csv 동결 CSV 8개]
    X[외부 원천 + meta.json] --> C[build/collect scripts]
    B --> C
    C --> D[data/enriched 4개]
    C --> E[data/relations 3개]
    B --> F[PostgreSQL 11 tables]
    D --> F
    E --> F
    B --> G[build_ontology_instances.py]
    D --> G
    E --> G
    G --> H[TBox 5 + ABox 5 TTL]
    H --> I[pgvector TBox index]
    H -. target .-> J[pyoxigraph Graph Store]
```

`data/csv/`는 읽기 전용이다. 수치 집계·필터·정렬은 RDB가 수행하고, 관계는 롱포맷 CSV와 n-ary RDF로 표현한다.

## 3. 주최측 원천

| 도메인 | master 행×열 | 엔티티와 그레인 | 실질 기준일 |
|---|---:|---|---|
| 국내채권 | 21,882 × 58 | 20,497종목; PK `(pd_no,pd_exg_mkt,info_seq)` | 2026-08-21 |
| 국내 ETF/ETN | 1,780 × 98 | ETF 1,235 / ETN 545; `pd_itm_no` | 가격 08-21 / 속성 08-24 / Refinitiv 08-22 |
| 해외 ETF/ETN | 6,037 × 49 | ETF 5,972 / ETN 65; `pd_itm_no` | 종가 08-21 / 갱신 08-22 |
| 국내 펀드 | 23,676 × 75 | 공모 14,716 / 사모 8,960; `itm_no` | 2026-08-21 최빈 |

원천은 master·schema 각 1개씩 총 8개 CSV다. 08-24 배포본에는 axis sample이 없다. 국내 ETF의 `pd_itm_no='KR'` 오염 1행은 적재에서 제외되어 DB 행수는 1,779다.

## 4. 파생·관계 산출물

| 파일 | 행×열 | 역할 | 생성기 |
|---|---:|---|---|
| `bond_kr_enriched.csv` | 21,882 × 12 | 등급 rank, 잔존일수, 통화·구매가능 | `build_bond_enrichment.py` |
| `etf_kr_enriched.csv` | 1,780 × 12 | LSEG 보수·복제방식 보완 | `build_etf_enrichment.py` |
| `company_master.csv` | 118,709 × 5 | DART/KIND 기업 식별자 | `build_company_relations.py` |
| `holding_code_map.csv` | 1,393 × 8 | 편입코드→기업·ETF 연결 | `build_holding_code_map.py` |
| `etf_holding.csv` | 47,016 × 7 | ETF 편입관계 | `build_etf_holding.py` |
| `etf_theme.csv` | 5,646 × 4 | ETF 테마관계 | `build_etf_enrichment.py` |
| `company_subsidiary.csv` | 30,097 × 10 | 기업 출자관계 | `build_company_relations.py` |

펀드 master는 이미 1행=1펀드다. 별도 dedup 파일이나 builder를 사용하지 않는다.

외부 provenance는 정책 상한과 구분한다. ETF 편입관계의 실제 `as_of=2026-07-10`, DART/KIND 원천의 `as_of=2026-07-11`, 자회사 관계의 행별 공시일은 그대로 유지한다. `etf_theme.as_of`는 확인되지 않아 NULL이다.

## 5. PostgreSQL RDB

| schema | table | DB rows | columns | PK |
|---|---|---:|---:|---|
| raw | bond_kr_master | 21,882 | 58 | `(pd_no,pd_exg_mkt,info_seq)` |
| raw | etf_kr_master | 1,779 | 98 | `pd_itm_no` |
| raw | etf_gl_master | 6,037 | 49 | `pd_itm_no` |
| raw | fund_pub_master | 23,676 | 75 | `itm_no` |
| enriched | bond_kr_enriched | 21,882 | 12 | `(pd_no,pd_exg_mkt,info_seq)` |
| enriched | etf_kr_enriched | 1,779 | 12 | `pd_itm_no` |
| enriched | company_master | 118,709 | 5 | `corp_code` |
| enriched | holding_code_map | 1,393 | 8 | `holding_code_raw` |
| relations | etf_theme | 5,646 | 4 | `(pd_itm_no,theme)` |
| relations | etf_holding | 47,016 | 8 | `holding_id` identity |
| relations | company_subsidiary | 30,097 | 11 | `relation_id` identity |

RDB 물리 컬럼은 identity 2개를 포함해 340개다. pgvector 정의 12개를 합친 통합 정의서는 352행이다.

## 6. 품질 규칙

1. 채권 종목 수는 `COUNT(DISTINCT pd_no)`로 계산한다.
2. `buyable_quantity`는 무효다. 구매가능은 원화·만기 미도래로 판단한다.
3. 국내 ETF는 `pd_grp_no='ETF'`, 공모펀드는 `prvo_pbff_desc='공모'`를 적용한다.
4. 펀드 보수 4종은 천분율이므로 합계 후 10으로 나눠 %로 표시한다.
5. 원천·외부 값이 충돌하면 주최측을 우선하고 충돌 사실을 evidence에 남긴다.
6. 기준일 불명·전량 결측·무효 컬럼은 근거로 사용하지 않는다.

## 7. 재구축 순서

```bash
python3 script/build_bond_enrichment.py
python3 script/build_etf_enrichment.py
python3 script/build_company_relations.py
python3 script/build_holding_code_map.py
python3 script/build_data_inventory.py
python3 src/kb/build_rdb.py
python3 src/kb/build_schema_catalog.py
python3 script/build_ontology_instances.py
python3 script/validate_external.py
python3 script/validate_ontology.py
python3 script/test_rdb_vertical_slice.py --db
```

앞의 세 enrichment는 서로 독립이고 `holding_code_map`만 `company_master` 뒤에 실행한다. RDB는 모든 파생 산출물이 완성된 뒤 적재한다.

## 8. 남은 구현 Gap

- pyoxigraph Graph Store와 SPARQL runtime
- 해외 ETF·공모펀드 편입종목 수집
- content vector index
- 외부 snapshot의 cutoff 이하 최신본 자동 선택
