# 금융상품 데이터 플랫폼 V2 인수 문서

검증 기준일: 2026-08-27 (Asia/Seoul)

이 문서는 팀원이 테스트 Agent를 바로 연결할 수 있도록 현재 VM 배포 상태, 데이터 출처, 저장 위치와 데이터베이스별 적재 결과를 정리한다. 물리 컬럼과 쿼리 생성 규칙은 별도 [Agent DB 스키마 인수 문서](AGENT_DB_SCHEMA_HANDOFF.md)를 사용한다.

## 1. 현재 서비스 상태

| 항목 | 현재 값 |
|---|---|
| 팀 테스트 URL | `http://40.82.145.44:8000` |
| API 버전 | `3.0.0` |
| 데이터 release | `financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38` |
| snapshot SHA-256 | `ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38` |
| readiness | `true` |
| load run | 정확히 1건, `passed / cutover_ready` |
| 임시 공개 만료 | `2026-08-29T14:59:00Z` = `2026-08-29 23:59 KST` |
| 공개 범위 | `:8000`의 `/v1/*`와 guarded read-only `/db*` |
| 외부 차단 | PostgreSQL `5432`, Oxigraph `7878`은 외부 TCP 접속 불가로 확인 |
| canonical vector | `pending`, 세 테이블 모두 0행 |
| HyperCLOVA | Data API에는 미설정. DB 조회에는 영향 없음 |

현재 모드는 팀 내부 시연을 위한 임시 HTTP 공개 모드다. 인증과 TLS가 없는 테스트 URL이므로 비밀·개인정보를 요청에 넣지 않는다. 만료 후 `/health`를 제외한 요청은 `503 PUBLIC_TEST_EXPIRED`로 닫힌다. 제출 VM에서는 `/db*`를 공개하지 않고 Agent와 Data API를 같은 Compose 네트워크에 배치한다.

간단 확인:

```powershell
Invoke-RestMethod http://40.82.145.44:8000/health
Invoke-RestMethod http://40.82.145.44:8000/v1/release
Invoke-RestMethod http://40.82.145.44:8000/db/version
```

Agent 설정:

```text
FINANCIAL_DATA_API_URL=http://40.82.145.44:8000
FINANCIAL_DATA_RELEASE_ID=financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38
```

팀원에게 PostgreSQL DSN, DB 비밀번호 또는 Oxigraph 포트를 전달하지 않는다.

## 2. VM 파일과 런타임 위치

| 구분 | VM 위치 또는 이름 | 상태/용도 |
|---|---|---|
| 업로드 수신 | `/home/user1106/financial-agent-v2/incoming/` | checksum 검증 전후 배포 파일 |
| 주최측 정본 | `/home/user1106/financial-agent-v2/shared/data/official/2026-08-24/` | XLSX 8개, 읽기 전용 입력 |
| 팀 legacy evidence | `/home/user1106/financial-agent-v2/shared/data/legacy/2026-07-11/` | 6,971파일, 감사·근거 재사용 후보 |
| V2 데이터 플랫폼 release | `/home/user1106/financial-agent-v2/releases/57c4edc96bd5cebe7703bb717480b0ebd935b39d/` | Stage와 cutover에 사용한 코드 |
| 현재 Data API release | `/home/user1106/financial-agent-v2/releases/ad7a3adb766ad7020368a16425f5e0529a3b5a03/` | API-only 배포 소스 |
| 백업 루트 | `/home/user1106/financial-agent-v2/shared/backups/` | PostgreSQL dump, Graph archive, cutover journal |
| Compose project | `financial-agent-prep` | 기존 VM 프로젝트 유지 |
| PostgreSQL volume | `financial-agent-prep_postgres-data-pg17` | 활성 PostgreSQL 17 데이터 |
| 활성 Graph volume | `financial-agent-prep_oxigraph-next-2026-08-24-57c4edc` | 검증 후 승격된 V2 Graph |
| 이전 Graph volume | `financial-agent-prep_oxigraph-data` | rollback/evidence용 보존 |

`.env`는 release별로 권한 `600`을 유지하며 비밀값은 VM에서만 관리한다. archive와 backup을 임의로 삭제하지 않는다.

## 3. 데이터 출처와 우선순위

### 3.1 주최측 제공 데이터: 운영 정본

주최측 2026-08-24 XLSX 8개는 데이터 파일 4개와 스키마 파일 4개다. 이 집합만 `raw`의 정본 입력으로 사용했다. `__MACOSX`와 AppleDouble 파일은 제외했다.

| 코드 | 데이터 파일 | 스키마 파일 | raw 테이블 | 적재 행 | 열 | PK | 실질 기준일 |
|---|---|---|---|---:|---:|---|---|
| `PRBD01N001` | `prbd01n001_data.xlsx` | `prbd01n001_schema.xlsx` | `raw.bond_kr_master` | 21,882 | 58 | `pd_no, pd_exg_mkt, info_base_dt, info_seq` | 2026-08-21 |
| `PREF01N001` | `pref01n001_data.xlsx` | `pref01n001_schema.xlsx` | `raw.etf_kr_master` | 1,780 | 98 | `pd_itm_no` | 2026-08-24 |
| `PREF02N001` | `pref02n001_data.xlsx` | `pref02n001_schema.xlsx` | `raw.etf_gl_master` | 6,037 | 49 | `pd_itm_no` | 2026-08-22 |
| `PRFD01N001` | `prfd01n001_data.xlsx` | `prfd01n001_schema.xlsx` | `raw.fund_pub_master` | 23,676 | 75 | `itm_no` | 2026-08-21 |
| 합계 | 데이터 4개 | 스키마 4개 | 4개 base table | **53,375** | 280 | - | - |

공백만 `NULL`로 바꾸고 숫자 `0`과 내부 코드는 원문 그대로 보존했다. 주최측 데이터와 외부 근거가 충돌하면 주최측 값을 우선한다.

### 3.2 팀 제공 legacy evidence: 선별 재사용

2026-07-11 legacy bundle 6,971파일은 운영 `raw`에 그대로 적재하지 않았다. 이전 master CSV는 현행 정본과 grain·행 수·스키마가 다르고, legacy 채권 CSV는 manifest hash 불일치가 있으므로 조회 원천으로 사용하면 안 된다.

다음 조건을 통과한 관계 근거만 현행 ID로 다시 연결했다.

- `as_of`/`published_at <= 2026-08-24`
- 원문과 sidecar의 SHA-256·URL·날짜 검증
- `enriched.product_master.product_id` 또는 표준 `security_id`로 식별 가능
- 합계·소계·sentinel과 룩어헤드 필드 제외
- 관계 부재와 미수집 상태를 구분

현재 운영에 반영된 legacy 계열 근거는 다음과 같다.

| 근거 종류 | `source_document` | 파생 관계 | 관계 행 | 기준일 |
|---|---:|---|---:|---|
| 운용사 holdings 공시 (`KODEX`, `TIGER`, `RISE`, `ACE`) | 711 | `relations.product_holding` | 46,951 | 2026-07-10 |
| OpenDART `otrCprInvstmntSttus` | 1,634 | `relations.company_subsidiary` | 8,866 | 2025-04-17 ~ 2026-07-10 |
| 합계 | **2,345** | - | **55,817** | cutoff 이내 |

`relations.product_classification` 61,744행은 legacy 외부 수집이 아니라 주최측 `PREF01N001`, `PREF02N001`, `PRFD01N001` 컬럼에서 파생했다. 6,971파일 전체가 DB에 들어간 것이 아니며, 사용되지 않은 파일도 provenance 감사와 재현을 위해 archive에 보존한다.

## 4. PostgreSQL 적재 결과

엔진은 PostgreSQL 17 + pgvector다. 정식 스키마는 `meta`, `raw`, `enriched`, `relations`, `vec`, `core`이며 `*_next`는 stage 검증 뒤 정식 이름으로 승격됐다.

### 4.1 스키마별 요약

| 스키마 | 역할 | 현재 핵심 수치 |
|---|---|---|
| `meta` | release, 적재 이력, 컬럼 카탈로그, coverage | snapshot 1, load run 1, catalog 499, coverage 51,990 |
| `raw` | 공식 XLSX 원형 보존 | base 4개 53,375행 + 코드명 호환 view 4개 |
| `enriched` | 공통 상품, 도메인 상품, 지표, 표준 증권 ID | 상품 51,990, 지표 113,146, 증권 71,953 |
| `relations` | 편입·분류·자회사·문서 관계 | holdings 46,951, classifications 61,744, subsidiaries 8,866 |
| `vec` | `bge-m3` 1024차원 schema/document 검색 계약 | 현재 0행, `pending` |
| `core` | 기존 Agent 호환 읽기 view | 5개 view, 별도 데이터 복제 없음 |

### 4.2 상품 유형별 현황

| `product_type` | 상품 수 | 비고 |
|---|---:|---|
| `BOND` | 20,497 | raw 21,882 offer를 `pd_no` 상품 grain으로 접음 |
| `ETF_KR` | 1,235 | 국내 원천에서 `pd_grp_no`로 ETF 분리 |
| `ETN_KR` | 545 | 국내 원천에서 ETN 분리 |
| `ETF_GL` | 5,972 | 해외 원천에서 ETF 분리 |
| `ETN_GL` | 65 | 해외 원천에서 ETN 분리 |
| `FUND_PUB` | 14,716 | 공모 |
| `FUND_PRIVATE` | 8,960 | 사모도 운영 RDB에 보존 |
| 합계 | **51,990** | `enriched.product_master` |

### 4.3 주요 물리 테이블 실측

| 테이블 | 행 수 |
|---|---:|
| `enriched.bond_kr_offer` | 21,882 |
| `enriched.product_metric` | 113,146 |
| `enriched.security_master` | 71,953 |
| `enriched.security_identifier` | 87,558 |
| `relations.source_document` | 2,345 |
| `relations.product_holding` | 46,951 |
| `relations.product_classification` | 61,744 |
| `relations.company_subsidiary` | 8,866 |
| `relations.product_document` | 711 |

coverage는 holdings `available` 711상품, `unavailable` 30,172상품, `not_applicable` 21,107상품이다. holdings가 0행일 때 `available`인 경우에만 “보유하지 않음”으로 해석한다.

## 5. GraphDB 적재 결과

Graph 엔진은 Oxigraph다. default graph는 사용하지 않으며 TBox와 ABox를 named graph로 분리했다.

| named graph | triples | 구분 |
|---|---:|---|
| `http://mafest.ai/graph/abox/bond_kr` | 81,974 | ABox |
| `http://mafest.ai/graph/abox/company` | 439,248 | ABox |
| `http://mafest.ai/graph/abox/etf_gl` | 36,200 | ABox |
| `http://mafest.ai/graph/abox/etf_kr` | 9,628 | ABox |
| `http://mafest.ai/graph/abox/fund_pub` | 88,338 | ABox |
| **ABox 합계** | **655,388** | 운영 health 계약 |
| `http://mafest.ai/graph/tbox/common` | 1,058 | TBox |
| `http://mafest.ai/graph/tbox/bond_kr` | 387 | TBox |
| `http://mafest.ai/graph/tbox/etf_kr` | 790 | TBox |
| `http://mafest.ai/graph/tbox/etf_gl` | 136 | TBox |
| `http://mafest.ai/graph/tbox/fund_pub` | 248 | TBox |
| **TBox 합계** | **2,619** | ontology 계약 |
| **전체 named graph 합계** | **658,007** | ABox + TBox |

`fpi:` 상품 URI에서 접두사를 제거한 값은 RDB `product_id`와 같다. 사모펀드는 RDB에는 있지만 현재 ABox 상품 클래스에는 올리지 않았다.

## 6. VectorDB 상태

`vec.bond_schema_terms`, `vec.schema_terms_all`, `vec.document_chunk`의 DDL과 `vector(1024)` 계약은 배포됐지만 현재 행 수는 모두 0이다. `bge-m3` 벡터를 all-or-none으로 재사용할 수 없어서 의도적으로 `pending` 상태를 유지했다.

따라서 현재 팀 테스트에서 다음은 가능하다.

- RDB 숫자 필터·정렬·집계
- Graph 관계 탐색과 ontology 검증
- `/v1` curated 기능과 `/db` 맞춤 SQL/SPARQL

다음은 아직 운영 준비가 아니다.

- canonical vector 의미 검색
- `POST /v1/evidence/semantic-search`의 실제 문서 검색 결과
- Data API 자체의 HyperCLOVA 답변 생성

Vector가 비어 있다는 사실을 “근거 문서가 없다”로 해석하지 않는다. Agent가 vector 기능을 요구하면 별도 embedding release가 필요하다.

## 7. 운영 검증 결과와 제한

2026-08-27 외부 공개 경로에서 다음을 재검증했다.

- `/health`: `status=ok`, `readiness=true`, API `3.0.0`
- `/v1/release`: exact release와 snapshot 일치
- `/db/version`, `/db/stats`, `/db/tables`: 200, canonical object 41개
- `/db/catalog`: 499개 컬럼 메타데이터 제공
- `/db/sql`: SELECT/CTE만 허용, 최대 100행, DB timeout 2초
- `/db/sparql`: 읽기 질의만 허용, Graph timeout 10초
- 분당 60요청, 요청 본문 1MB
- API 포트 `8000`만 외부 접근 가능; `5432`, `7878` 차단 확인

이번 Data API 배포는 기존 데이터를 다시 적재하지 않고 이미 승격된 PostgreSQL·Graph를 읽도록 API 컨테이너만 교체했다.

## 8. 팀 전달 체크리스트

1. Base URL과 exact release ID를 Agent 환경변수에 넣는다.
2. Agent 시작 시 `/health`의 `readiness`, `/v1/release`의 `release_id`를 확인한다.
3. 일반 질의는 `/v1/*`, 맞춤 SQL/SPARQL이 필요한 질의만 `/db/*`를 사용한다.
4. `/db/tables` → 필터된 `/db/catalog` → 파라미터화된 `/db/sql` 순서로 query context를 만든다.
5. 결과에 `product_id`, 값, 단위, 실제 `as_of`, 출처와 문서 ID를 보존한다.
6. 2026-08-29 23:59 KST 전에 테스트를 끝내거나 운영자가 만료를 갱신해 API를 재배포한다.
7. 제출 VM에서는 `/db`를 외부에 공개하지 않고 `/v1` 또는 최종 Agent `/query`만 공개한다.

이전에 채팅에 노출된 CLOVA 키는 사용하지 말고 폐기·재발급한다. 새 키는 Agent/VM의 비밀 환경변수에만 저장한다.
