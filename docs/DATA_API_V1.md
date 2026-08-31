# Financial Data Raw Query API

> 파일명은 기존 링크 호환 때문에 유지하지만 API `/v1` 경로는 T-107에서 제거됐다.

## 목적

DB 담당자는 PostgreSQL과 Oxigraph를 하나의 읽기 전용 HTTP API로 제공한다. Agent는
`/db/catalog`로 물리 스키마와 업무 정의를 확인한 뒤 질문에 맞는 SQL 또는 SPARQL
원문을 생성한다. 과거 curated `/v1/*`와 JSON wrapper 형식은 사용하지 않는다.

현재 데이터 release는
`financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38`다.

## 경로

| 메서드와 경로 | 용도 |
|---|---|
| `GET /health` | RDB·Graph·release 준비 상태 |
| `GET /db/version` | exact release 확인 |
| `GET /db/stats` | 주요 RDB/Vector 테이블 행 수 |
| `GET /db/tables` | 조회 가능한 schema와 table 목록 |
| `GET /db/columns?table_schema=...&table_name=...` | 물리 컬럼·타입 |
| `GET /db/catalog?table_schema=...&table_name=...` | 설명·단위·기준일·PK/FK·grain |
| `POST /db/sql` | UTF-8 `text/plain` SQL 원문 실행 |
| `POST /db/sparql` | UTF-8 `text/plain` SPARQL 원문 실행 |

`POST /db`, `/db/coverage`, `/db/columns/{schema}/{table}`, 모든 `/v1/*`는 제거됐다.

## 요청 계약

본문은 JSON이 아니라 쿼리 문자열 자체다.

```http
POST /db/sql
Content-Type: text/plain; charset=utf-8

SELECT product_id, name
FROM enriched.product_master
WHERE name = 'KODEX 200'
LIMIT 20
```

```http
POST /db/sparql
Content-Type: text/plain; charset=utf-8

PREFIX fp: <http://mafest.ai/product#>
SELECT ?product
WHERE { ?product a fp:ETF }
LIMIT 20
```

응답 형식은 두 경로가 같다.

```json
{
  "columns": ["product_id", "name"],
  "rows": [{"product_id": "etf_kr:...", "name": "KODEX 200"}],
  "row_count": 1,
  "truncated": false,
  "elapsed_ms": 12.345
}
```

JSON wrapper를 보내면 `415`, 빈 본문·잘못된 UTF-8은 `400`, 1MB 또는 100,000자를
넘으면 `413`이다. SQL 파라미터 객체는 더 이상 받지 않으므로 Agent가 문자열
리터럴을 만들 때 PostgreSQL escaping을 정확히 적용해야 한다.

## 보호 장치

- SQL은 `SELECT`/`WITH` 읽기 질의만 허용한다.
- SPARQL은 조회 질의만 허용하며 update와 `SERVICE`를 거부한다.
- SQL statement timeout은 최대 2초, Graph 요청 timeout은 최대 10초다.
- 결과는 최대 100행이며 초과분은 `truncated=true`로 표시한다.
- 공개 테스트는 분당 요청 수, 요청 본문 크기, 만료시간을 제한한다.
- DB 계정은 `agent_reader` 읽기 전용 role을 사용한다.

이 제한은 팀 Agent가 만든 잘못된 쿼리가 DB를 변경하거나 전체 서비스를 오래
점유하지 못하게 하는 운영 안전장치다.

## Union default graph

Oxigraph는 `serve-read-only --union-default-graph`로 실행한다. 따라서 다음 bare
SPARQL이 모든 named graph를 기본 조회 대상으로 사용한다.

```sparql
SELECT (COUNT(*) AS ?triples)
WHERE { ?s ?p ?o }
```

T-107 배포 계약의 예상 결과는 `1,628,311` triples다. `GRAPH ?g { ... }`를 직접
쓴 질의도 계속 동작한다. Graph volume은 Vector DB 배포 handoff 이후 별도
versioned volume으로 Stage하고, 정확한 count 검증 뒤에만 활성 pointer를 바꾼다.

## Python Agent 사용

```python
from tools.data_api import FinancialDataClient

client = FinancialDataClient.from_env()
client.db_version()
catalog = client.catalog(table_schema="enriched", table_name="product_master")
rows = client.sql(
    "SELECT product_id,name FROM enriched.product_master "
    "WHERE name='KODEX 200' LIMIT 20"
)
graph = client.sparql(
    "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }"
)
```

환경변수:

- `FINANCIAL_DATA_API_URL=http://40.82.145.44:8000` — 테스트 VM
- `FINANCIAL_DATA_RELEASE_ID=financial-products-2026-08-24@...` — 권장 release pin
- `FINANCIAL_DATA_API_TIMEOUT_SECONDS=3` — 기본값 3초, 최대 10초

제출 VM에서는 공개 IP 대신 같은 Compose network의 내부 서비스 URL을 사용한다.
외부에는 최종 Agent endpoint만 노출한다.
