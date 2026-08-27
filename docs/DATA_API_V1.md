# Financial Data API V1 — Agent 연동 계약

## 역할 경계와 현재 상태

DB 담당자는 V2 PostgreSQL·Graph·문서 벡터를 읽는 `/v1` API와 Python 클라이언트를 제공한다. LangGraph의 질문 해석, `bge-m3` 질문 임베딩, HyperCLOVA X 답변 생성, 최종 `POST /query`는 Agent 담당이다. Agent에는 DB DSN이나 DB 비밀번호를 전달하지 않는다.

이 문서가 작성된 시점에 V2 Stage는 `cutover_ready`이지만, T-105의 실제 cutover 완료 로그는 별도 확인 대상이다. `/health`가 다음 값을 모두 만족하기 전에는 V1 API를 배포하지 않는다.

- `readiness=true`
- `release_id=financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38`
- RDB와 Graph snapshot hash 일치
- load run `passed/cutover_ready`

## 공개 API

| 경로 | 계약 |
|---|---|
| `GET /health` | RDB·Graph·release 정렬 상태와 임시 공개 만료 정보 |
| `GET /v1/release` | release/cutoff와 canonical·demo vector 상태 |
| `GET /v1/capabilities` | 35문항별 `ready/partial/gap` API coverage |
| `POST /v1/products/search` | `exact` 우선. 유사상품 대체는 호출자가 명시한 경우만 허용 |
| `POST /v1/products/query` | 허용된 지표·연산자만 사용하는 필터·정렬 |
| `GET /v1/products/{product_id}` | 공통·도메인 속성, 지표, 실제 기준일, coverage |
| `POST /v1/products/compare` | 최대 20개 상품·3개 지표 비교. 단위 혼합은 `UNIT_MISMATCH` |
| `GET /v1/products/{product_id}/holdings` | 편입비중·기준일·문서 provenance. 미수집은 빈 보유로 해석하지 않음 |
| `POST /v1/relations/traverse` | 허용된 최대 3-hop 기업·자회사·편입·발행·문서 경로 |
| `POST /v1/ontology/validate` | 등급, cutoff, 관계 domain 검증과 ABSTAIN 코드 |
| `POST /v1/evidence/semantic-search` | Agent가 만든 1024차원 질문 벡터로 demo 문서 검색 |

모든 V1 응답은 `release_id`, `snapshot_hash`, `data`, `coverage`, `evidence`, `elapsed_ms`, `truncated`, `meta`를 반환한다. 공개 프로필의 요청 본문은 1MB, 결과는 100행, DB statement는 2초, 관계 깊이는 3으로 제한한다.

조건검색 허용 필드는 `AUM`, `RETURN_1Y`, `EXPENSE_RATIO`, `MATURITY_DATE`, `CREDIT_RATING_RANK`, `ASSUMED_PURCHASABLE`, `BUY_YIELD`다. AUM 필터·정렬에는 통화가 반드시 필요하다. `buyable_quantity`는 저장 전용이므로 구매가능 판정에 사용하지 않는다.

예시:

```json
POST /v1/products/query
{
  "product_types": ["ETF_KR"],
  "currency": "KRW",
  "filters": [{"field": "AUM", "op": "gte", "value": 500000000000}],
  "sort_by": "AUM",
  "sort_order": "desc",
  "limit": 10
}
```

```json
POST /v1/relations/traverse
{
  "start_entity_id": "dart:00536541",
  "path": ["parent_of", "held_by_product"],
  "as_of": "latest",
  "limit": 20
}
```

## Agent 사용법

로컬 테스트에서는 `FINANCIAL_DATA_API_URL=http://40.82.145.44:8000`을 사용한다. 같은 VM으로 옮긴 뒤에는 공개 IP 대신 Compose 내부 서비스 URL을 사용한다. release mismatch를 조기에 잡으려면 `FINANCIAL_DATA_RELEASE_ID`도 설정한다.

```python
import clova
from tools.data_api import FinancialDataClient

client = FinancialDataClient.from_env()
product = client.search_products("KODEX 200", match="exact")
query_vector = clova.embed("이 상품의 공식 위험요인은 무엇인가?")
evidence = client.semantic_search(query_vector, top_k=2)
```

클라이언트 timeout 기본값은 3초이며 POST 요청을 자동 재시도하지 않는다. Agent 전체 15초 예산 안에서 검색·검증·답변 생성을 끝낸다.

## 외부문서 2건 demo index

정식 `vec.*`는 130개/189개/전체 문서의 all-or-none 계약이므로 부분 적재하지 않는다. `vec_demo`에 정책자료 1건과 위험자료 1건, 각 1개 청크만 저장한다. 이 인덱스는 항상 `index_status=demo`, `production_ready=false`, `seed_count=2`로 표시된다.

고정 후보는 다음과 같다.

1. 금융위원회, 2026-05-06, [국민참여형 국민성장펀드 보도자료](https://www.fsc.go.kr/no010101/86834)
2. 미래에셋자산운용, 2024-11-08, [TIGER MSCI Korea TR 공식 상품자료 PDF](https://www.tigeretf.com/upload/etf/20241108075220009535.pdf)

원문과 UTF-8 추출 텍스트를 `artifacts/demo_vectors/sources/`에 둔다. 템플릿을 같은 `artifacts/demo_vectors/`로 복사하고 다음 명령으로 해시가 채워진 manifest를 만든다.

```bash
python deploy/data_api_v1/prepare_demo_manifest.py \
  artifacts/demo_vectors/demo_manifest.template.json \
  artifacts/demo_vectors/manifest.json
python -m kb.build_demo_vectors_v2 \
  --manifest artifacts/demo_vectors/manifest.json --check
```

위험 문서의 `product_id`는 적재 직전에 exact search로 `TIGER MSCI Korea TR`과 실제 canonical ID가 일치하는지 확인한다. 원문 SHA-256, 추출 텍스트 SHA-256, 청크 SHA-256, 공식 HTTPS host, 발행일 cutoff, 인용문의 추출 원문 포함 여부 중 하나라도 틀리면 적재하지 않는다.

VM에서는 `DEMO_VECTOR_APPLY_ACK=APPLY_TWO_OFFICIAL_DOCUMENTS`를 명시한 뒤 `deploy/data_api_v1/seed_demo_vectors.sh`를 실행한다. 이 단계에서만 HyperCLOVA `bge-m3` corpus embedding을 최대 2회 호출한다. 질문 embedding은 계속 Agent가 담당한다.

## 35문항 검증과 배포

현재 API coverage는 `ready 14 / partial 18 / gap 3`이다. `partial`과 `gap`은 API 장애가 아니라 실제 데이터·근거 공백을 뜻한다. 특히 Q23은 사건 이력, Q29는 해외 ETF holdings, Q30은 공모펀드 holdings가 없어 제출 정답을 만들 수 없다. Q31~35의 taxonomy/entity/future/domain ABSTAIN 경로는 우선 검증 대상이다.

대표 smoke set은 정확 상품 조회, 지표 조건검색, ETF holdings, 모회사→자회사→ETF, 정책·위험 의미검색, `AAAA`/VOO ABSTAIN 여섯 종류다. 대표 질의를 통과한 뒤 35문항 전체를 실행하여 `통과 / 데이터 부족 / 문서 부족 / Agent 로직 오류`로 분리한다. `GET /v1/capabilities`가 35건을 반환하더라도 35/35 제출 준비 완료를 의미하지 않는다.

테스트 VM 배포는 다음 환경을 요구한다.

- `COMPOSE_PROJECT_NAME=financial-agent-prep`
- `V2_CUTOVER_CONFIRMED=V2_RELEASE_IS_ACTIVE`
- `PUBLIC_TEST_EXPIRES_AT` — UTC ISO-8601, 기본 운영 기간 7일
- 읽기전용 `DATABASE_URL`; PostgreSQL 5432와 Oxigraph 7878은 외부 미공개

`deploy/data_api_v1/deploy_public_test.sh`는 먼저 기존 V2 health를 검증한 다음 public curated API를 `:8000`, SQL/SPARQL debug API를 `127.0.0.1:8001`에 띄운다. 공개 API는 분당 60요청으로 제한되고 `/db/sql`·`/db/sparql`은 404를 반환한다.

T-105 DB/Graph cutover부터 연속 수행하려면 Windows PowerShell에서 다음 명령을 실행한다. 이 테스트 VM은 이미 guarded read-only `/db`가 공개되어 있으므로 명시적인 위험 인자가 필요하다. T-106 검증이 끝나면 공개 `/db*`는 404로 닫힌다. SSH 비밀번호는 로컬 터미널 프롬프트에만 입력한다.

```powershell
.\deploy\data_api_v1\deploy_vm_full.ps1 `
  -AcceptExistingPublicReadOnlyDbRisk `
  -PublicTestExpiresAt '2026-08-29T23:59:00+09:00'
```

T-105가 이미 완료된 경우 위 실행기는 cutover를 건너뛴다. T-106만 다시 설치하려면 `deploy_vm.ps1`을 직접 실행한다.

설치기는 활성 Graph volume이 `financial-agent-prep_oxigraph-next-2026-08-24-57c4edc`인지 확인하고 Graph 서비스를 재생성하지 않은 채 API 컨테이너만 교체한다. T-105가 아직 완료되지 않았거나 정본 행 수가 다르면 배포를 거부한다.

제출 VM에서는 public-test overlay와 host port를 사용하지 않는다. Data API는 Compose 내부 DNS로만 Agent에 제공하고 외부에는 HTTPS Agent `POST /query`만 공개한다.

이전에 채팅에 노출된 CLOVA 키는 폐기·재발급한다. 새 키는 VM/Agent 비밀 환경변수에만 저장하며 manifest, 로그, 코드, 채팅에 기록하지 않는다.
