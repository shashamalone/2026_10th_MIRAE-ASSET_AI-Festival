# 팀원·LLM용 DB/테이블 정의서

대상 release: `financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38`

이 문서는 Agent가 데이터 구조를 이해하고 맞춤 SQL/SPARQL을 안전하게 생성하기 위한 짧은 런타임 정의서다. 전체 499개 컬럼의 타입·NULL·PK/FK·단위·기준일·설명은 API의 `/db/catalog` 또는 아래 정본을 사용한다.

- [RDB 전체 정의서](../../docs/docs_data_layer/RDB_DEFINITION_V2_0.md)
- [전체 컬럼 정의서](../../docs/docs_data_layer/TABLE_DEFINITION_V2_0.md)
- [GraphDB 정의서](../../docs/docs_data_layer/GRAPHDB_DEFINITION_V2_0.md)
- [VectorDB 정의서](../../docs/docs_data_layer/VECTORDB_DEFINITION_V2_0.md)
- [기계 판독 schema catalog](../../metadata/schema_catalog.json)
- [Data API 계약](../../docs/DATA_API_V1.md)

## 1. Agent가 DB를 선택하는 기준

| 질문 유형 | 사용 DB/API | 이유 |
|---|---|---|
| 상품 정확 조회, 수치 필터, TOP-N, 집계 | PostgreSQL `/db/sql` 또는 curated `/v1/products/*` | 숫자·단위·날짜를 정확하게 처리 |
| 편입→기업→자회사 같은 다중 홉, 클래스·domain/range | Oxigraph `/db/sparql` 또는 `/v1/relations/traverse` | 관계와 ontology 제약을 탐색 |
| 자연어를 schema 용어에 연결, 문서 인용 검색 | pgvector `vec.*` 또는 `/v1/evidence/semantic-search` | 의미 유사도 검색 |
| 일반적인 팀 Agent 기능 | `/v1/*` | 검증된 필드·연산자·evidence 계약이 내장됨 |
| `/v1`에 없는 맞춤 질의 | guarded read-only `/db/*` | Agent가 schema-aware SQL/SPARQL 생성 |

현재 canonical vector는 `pending`이며 0행이다. 따라서 RDB와 Graph는 사용 가능하지만 vector hit에 의존하는 답변은 아직 만들면 안 된다.

## 2. Query 생성 전 discovery 순서

LLM prompt에 499개 컬럼을 한 번에 넣지 않는다. 다음 순서를 고정한다.

1. `GET /db/version`으로 exact release를 고정한다.
2. `GET /db/tables`로 41개 canonical object 중 후보를 고른다.
3. `GET /db/catalog?table_schema=enriched&table_name=product_master`처럼 필요한 테이블만 조회한다.
4. grain, PK/FK, 단위, 기준일, NULL/0 규칙을 확인한 뒤 SQL/SPARQL을 생성한다.
5. 결과의 `product_id`, 물리 컬럼 또는 `metric_code`, 값, 단위, `as_of`, `source`를 답변 evidence까지 보존한다.

Base URL:

```text
http://40.82.145.44:8000
```

Python 예:

```python
from tools.data_api import FinancialDataClient

client = FinancialDataClient(
    "http://40.82.145.44:8000",
    expected_release_id=(
        "financial-products-2026-08-24@"
        "ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38"
    ),
)

tables = client.tables()
catalog = client.catalog(table_schema="enriched", table_name="product_master")
rows = client.sql(
    "SELECT product_id,name,effective_as_of "
    "FROM enriched.product_master WHERE name=%(name)s LIMIT 20",
    {"name": "KODEX 200"},
)
```

## 3. 공통 식별자와 조인 지도

`enriched.product_master.product_id`가 RDB, GraphDB와 VectorDB를 잇는 정규 상품 ID다.

| 상품 유형 | `product_id` 규칙 | 원천 키 | 도메인 테이블 |
|---|---|---|---|
| 국내채권 | `bond_kr:{pd_no}` | `pd_no` | `enriched.bond_kr_product` |
| 국내 ETF | `etf_kr:{pd_itm_no}` | `pd_itm_no` | `enriched.etf_kr` |
| 국내 ETN | `etn_kr:{pd_itm_no}` | `pd_itm_no` | `enriched.etn_kr` |
| 해외 ETF | `etf_gl:{pd_itm_no}` | `pd_itm_no` | `enriched.etf_gl` |
| 해외 ETN | `etn_gl:{pd_itm_no}` | `pd_itm_no` | `enriched.etn_gl` |
| 공모·사모펀드 | `fund:{itm_no}` | `itm_no` | `enriched.fund` |

| 시작 | 대상 | 조인 조건 |
|---|---|---|
| `enriched.product_master p` | 도메인 테이블 `d` | `d.product_id = p.product_id` |
| `p` | `enriched.product_metric m` | `m.product_id = p.product_id` |
| `p` | `meta.product_coverage c` | `c.product_id = p.product_id` |
| `p` | `relations.product_classification c` | `c.product_id = p.product_id` |
| `p` | `relations.product_holding h` | `h.product_id = p.product_id` |
| `h` | `enriched.security_master s` | `s.security_id = h.security_id` |
| `s` | `enriched.security_identifier i` | `i.security_id = s.security_id` |
| `relations.product_document pd` | `relations.source_document d` | `d.document_id = pd.document_id` |

`bond_kr_offer`, `product_metric`, `product_holding`, `product_classification`은 한 상품에 여러 행이 정상이다. 먼저 metric/type/as-of를 제한하지 않고 서로 조인하면 곱집합이 생긴다.

## 4. PostgreSQL 스키마와 테이블

### 4.1 `meta`: release와 데이터 품질

| 테이블 | 행 | grain / PK | Agent 용도 |
|---|---:|---|---|
| `meta.dataset_snapshot` | 1 | 데이터셋 빌드 1건 / `snapshot_id` | release, source file hash, 도메인별 실질 기준일 확인 |
| `meta.load_run` | 1 | 적재 실행 1건 / `run_id` | `passed/cutover_ready` 확인 |
| `meta.column_catalog` | 499 | 물리 컬럼 1개 / `table_schema,table_name,ordinal_position` | LLM용 설명·타입·단위·NULL·PK/FK·grain |
| `meta.product_coverage` | 51,990 | 상품×현재 snapshot / `product_id` | holdings·문서·성과 미확보 상태 판정 |

`product_coverage.holdings_status`는 `available`, `unavailable`, `not_applicable`이다. 0행을 “보유하지 않음”으로 답하기 전에 반드시 이 값을 확인한다.

### 4.2 `raw`: 주최측 원형

| base table | 행 | grain / PK | 용도 |
|---|---:|---|---|
| `raw.bond_kr_master` | 21,882 | 채권×시장×정보기준일×판매 LOT / `pd_no,pd_exg_mkt,info_base_dt,info_seq` | 공식 채권 58컬럼 원문 |
| `raw.etf_kr_master` | 1,780 | 국내 ETF/ETN 상품 / `pd_itm_no` | 공식 국내 ETF·ETN 98컬럼 원문 |
| `raw.etf_gl_master` | 6,037 | 해외 ETF/ETN 상품 / `pd_itm_no` | 공식 해외 ETF·ETN 49컬럼 원문 |
| `raw.fund_pub_master` | 23,676 | 공모·사모 펀드 상품 / `itm_no` | 공식 펀드 75컬럼 원문 |

코드명 호환 view는 `raw.prbd01n001`, `raw.pref01n001`, `raw.pref02n001`, `raw.prfd01n001`이다. 신규 Agent는 읽기 쉬운 `*_master` 이름을 우선 사용한다.

### 4.3 `enriched`: 상품·지표·식별자

| 테이블/view | 행 | grain / PK | 주요 역할 |
|---|---:|---|---|
| `enriched.product_master` | 51,990 | 공통 상품 1개 / `product_id` | 유형, 이름, 통화, 활성, 실질 기준일의 시작점 |
| `enriched.bond_kr_product` | 20,497 | 채권 `pd_no` 1개 / `product_id` | 발행사, 등급, 만기, 보수적 구매가능 가정 |
| `enriched.bond_kr_offer` | 21,882 | 채권×시장×기준일×판매 LOT / composite PK | 수익률·판매 LOT 상세 |
| `enriched.etf_kr` | 1,235 | 국내 ETF 1개 / `product_id` | 티커, ISIN, 운용사, 기초지수 |
| `enriched.etf_gl` | 5,972 | 해외 ETF 1개 / `product_id` | 티커, ISIN, 운용사, 설정일 |
| `enriched.etn_kr` | 545 | 국내 ETN 1개 / `product_id` | ETF 원천에서 ETN 분리 |
| `enriched.etn_gl` | 65 | 해외 ETN 1개 / `product_id` | 해외 원천에서 ETN 분리 |
| `enriched.fund` | 23,676 | 펀드 1개 / `product_id` | 공모 14,716 + 사모 8,960 보존 |
| `enriched.fund_pub` | 14,716 | `enriched.fund` 중 공모 / view | 공모펀드 호환 조회 |
| `enriched.product_metric` | 113,146 | 상품×지표×기준일×출처×방법 / `metric_id` | AUM, 1년 수익률, 보수 등 장형 지표 |
| `enriched.security_master` | 71,953 | 증권·기업 1개 / `security_id` | 편입증권과 기업 표준 ID·표시명 |
| `enriched.security_identifier` | 87,558 | 증권×식별자 유형×값 / composite PK | ISIN, KR_TICKER, RIC, BLOOMBERG 매핑 |

실제 `product_type` 허용값과 현재 건수는 `BOND` 20,497, `ETF_KR` 1,235, `ETN_KR` 545, `ETF_GL` 5,972, `ETN_GL` 65, `FUND_PUB` 14,716, `FUND_PRIVATE` 8,960이다.

`product_metric`의 핵심 컬럼은 `metric_code`, `value`, `unit`, `as_of`, `source`, `source_column`, `method`, `is_available`, `unavailable_reason`, `source_priority`다. 랭킹에는 `is_available AND value IS NOT NULL AND value <> 0`을 적용하고, AUM은 통화가 같은 행끼리만 비교한다.

### 4.4 `relations`: 근거가 있는 관계

| 테이블/view | 행 | grain / PK | 주요 역할 |
|---|---:|---|---|
| `relations.source_document` | 2,345 | 외부 근거 문서 1개 / `document_id` | 발행기관·발행일·URL·원문 hash |
| `relations.product_holding` | 46,951 | 상품×증권×기준일×문서 / `holding_id` | 편입비중과 직접 provenance |
| `relations.product_classification` | 61,744 | 상품×분류 유형×값×기준일 / `classification_id` | `asset_type` 30,872 + `region` 30,872 |
| `relations.company_subsidiary` | 8,866 | 기업×자회사×기준일×문서 / `relation_id` | 지분율, DART 근거 |
| `relations.product_document` | 711 | 상품×문서×관계유형 / composite PK | 상품과 holdings 문서 연결 |
| `relations.etf_holding` | 46,951 | `product_holding` 호환 view | 기존 Agent 이름 호환 |
| `relations.etf_theme` | 현재 분류 source 기준 사용 안 함 | `classification_type='theme'` view | theme 데이터가 있을 때만 사용 |

holdings는 `weight`, `unit`, `as_of`, `source_document_id`, `source`를 함께 반환한다. 자회사는 `parent_security_id`, `child_security_id`, `ownership_pct`, `as_of`, `source_document_id`를 함께 반환한다.

### 4.5 `vec`: pgvector 계약

| 테이블/view | 현재 행 | grain / PK | 역할 |
|---|---:|---|---|
| `vec.bond_schema_terms` | 0 | 채권 TBox term 1개 / `term_uri` | common+bond schema grounding |
| `vec.schema_terms_all` | 0 | 전체 TBox term 1개 / `term_uri` | 전체 ontology grounding |
| `vec.document_chunk` | 0 | 문서 청크 1개 / `chunk_id` | 상품별 공식 문서 의미 검색 |
| `vec.schema_index` | 0 | `schema_terms_all` view | 기존 이름 호환 |
| `vec.doc_chunk` | 0 | `document_chunk` view | 기존 이름 호환 |

모델 계약은 HyperCLOVA `bge-m3`, 1024차원, cosine distance다. 현재 0행이므로 vector 질의를 사실 확인 경로로 사용하지 않는다.

### 4.6 `core`: 기존 Agent 호환 view

| view | 원천 | 용도 |
|---|---|---|
| `core.bond_kr` | `enriched.bond_kr_product` | 채권 호환 읽기 |
| `core.etf_kr` | `enriched.etf_kr` | 국내 ETF 호환 읽기 |
| `core.etf_gl` | `enriched.etf_gl` | 해외 ETF 호환 읽기 |
| `core.etn` | `enriched.etn_kr UNION ALL enriched.etn_gl` | 국내·해외 ETN 통합 읽기 |
| `core.fund_pub` | `enriched.fund_pub` | 공모펀드 호환 읽기 |

신규 맞춤 쿼리는 의미가 더 명확한 `enriched`와 `relations`를 우선한다.

## 5. GraphDB 정의

엔진은 Oxigraph이며 namespace는 다음과 같다.

```sparql
PREFIX fp: <http://mafest.ai/product#>
PREFIX fpi: <http://mafest.ai/instance/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
```

### 5.1 TBox named graph

| graph | triples | 역할 |
|---|---:|---|
| `http://mafest.ai/graph/tbox/common` | 1,058 | 공통 상품·문서·관계·분류·통제어휘 |
| `http://mafest.ai/graph/tbox/bond_kr` | 387 | 채권 등급·만기·담보·발행 어휘 |
| `http://mafest.ai/graph/tbox/etf_kr` | 790 | 국내 ETF/ETN 분류·거래·위험 어휘 |
| `http://mafest.ai/graph/tbox/etf_gl` | 136 | 해외 ETF/ETN 전략·설정일·식별 어휘 |
| `http://mafest.ai/graph/tbox/fund_pub` | 248 | 공모펀드·클래스·판매·수익률 어휘 |

TBox 합계는 2,619 triples다. 클래스 55개, ObjectProperty 45개, DatatypeProperty 94개, 통제어휘 개체 297개다.

### 5.2 ABox named graph

| graph | triples | 주요 내용 |
|---|---:|---|
| `http://mafest.ai/graph/abox/bond_kr` | 81,974 | 채권 상품 |
| `http://mafest.ai/graph/abox/etf_kr` | 9,628 | 국내 ETF·ETN과 분류 |
| `http://mafest.ai/graph/abox/etf_gl` | 36,200 | 해외 ETF·ETN과 분류 |
| `http://mafest.ai/graph/abox/fund_pub` | 88,338 | 공모펀드와 분류 |
| `http://mafest.ai/graph/abox/company` | 439,248 | 기업, 증권, 문서, holding·subsidiary n-ary 관계 |

ABox 합계는 정확히 655,388 triples다. 편입·자회사·문서 관계는 `abox/company`에 있으므로 상품 graph와 함께 조회한다. default graph에 의존하지 않는다.

상품 URI `fpi:{product_id}`의 `{product_id}`는 RDB 값과 같다. 관계 URI와 provenance 구조는 다음과 같다.

- holding: 상품 → `fp:hasHolding` → `fp:Holding` → `fp:holdingSecurity` → 증권
- subsidiary: 모기업 → `fp:hasSubsidiary` → `fp:SubsidiaryRelation` → `fp:subsidiaryCompany` → 자회사
- document: 상품 → `fp:hasDocument` → `fp:Document`

## 6. 안전한 SQL/SPARQL 예시

정확 상품 조회:

```json
POST /db/sql
{
  "sql": "SELECT product_id,name,product_type,effective_as_of FROM enriched.product_master WHERE name=%(name)s LIMIT 20",
  "params": {"name": "KODEX 200"}
}
```

동일 통화 AUM TOP-N:

```sql
SELECT p.product_id, p.name, m.value, m.unit, m.as_of,
       m.source, m.source_column
FROM enriched.product_metric m
JOIN enriched.product_master p USING (product_id)
WHERE p.product_type = 'ETF_KR'
  AND m.metric_code = 'AUM'
  AND m.unit = 'KRW'
  AND m.is_available
  AND m.value IS NOT NULL
  AND m.value <> 0
ORDER BY m.value DESC
LIMIT 10
```

상품 graph 조회:

```json
POST /db/sparql
{
  "sparql": "PREFIX fp: <http://mafest.ai/product#> SELECT ?product ?name WHERE { GRAPH <http://mafest.ai/graph/abox/etf_kr> { ?product a fp:KoreanETF ; fp:productName ?name . FILTER(?name = 'KODEX 200') } } LIMIT 20"
}
```

SQL은 `SELECT`/`WITH` 한 statement만 허용한다. 문자열을 직접 붙이지 말고 `%(name)s`와 `params`를 사용한다. SPARQL은 `SELECT`, `ASK`, `CONSTRUCT`, `DESCRIBE`만 사용하며 `SERVICE`를 포함한 update·원격 실행은 거부된다.

## 7. LLM이 반드시 지킬 데이터 규칙

- 상품명은 완전일치를 먼저 시도한다. 유사상품으로 임의 대체하지 않는다.
- 숫자마다 실제 `as_of`와 `source`를 유지한다. release date를 모든 지표 날짜로 복사하지 않는다.
- `NULL`을 0으로 바꾸지 않는다. 지표의 0은 다수 원천에서 미계산 sentinel이므로 비교·랭킹에서 제외한다.
- `buyable_quantity`는 표시 전용이다. 채권 구매가능 판정에는 `is_assumed_purchasable`와 `purchasability_rule`을 사용한다.
- 국내·해외 master에는 ETF와 ETN이 함께 있으므로 `product_type` 또는 분리된 도메인 테이블을 사용한다.
- 펀드는 `itm_no`가 상품 키다. 공모 14,716과 사모 8,960을 임의 dedup하거나 사모를 버리지 않는다.
- 국채의 신용등급 NULL은 정상적인 무등급일 수 있다. 최저등급으로 간주하지 않는다.
- 해외 ETF `inception_date`는 공식 컬럼 의미상 설정일이며 실제 상장일로 답하지 않는다.
- holdings 미확보를 비보유로 해석하지 않는다. `meta.product_coverage`를 먼저 본다.
- Graph triple 부재만으로 관계가 없다고 단정하지 않는다. coverage와 근거 문서를 함께 확인한다.
- 값이나 식별자를 데이터에서 확인할 수 없으면 추측하지 않고 ABSTAIN/“확인할 수 없음”으로 답한다.

## 8. API 제한과 제출 전환

- 결과 최대 100행
- SQL statement timeout 2초
- Graph timeout 10초
- 요청 본문 1MB
- 분당 60요청/IP
- POST 자동 재시도 금지
- DDL/DML, multi-statement, `COPY`, SQL 주석 우회, SPARQL update 차단

팀 테스트용 공개 `/db`는 2026-09-20 23:59 KST에 만료된다. 제출 환경에서는 Data API를 Agent와 같은 VM/Compose 내부 DNS로만 연결하고 공개 `/db*`를 404로 차단한다. 외부에는 최종 Agent `POST /query`와 필요한 health 경로만 HTTPS로 공개한다.
