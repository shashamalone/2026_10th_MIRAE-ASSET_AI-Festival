# Graph cutover 검증 기록 (2026-09-06)

## 판정

`ontology-holdings-20260821-de30afc2bcd4` 번들이 원격 Graph 서비스에
replace 방식으로 전환됐다. 공개 API에서 manifest와 동일한 10개 named graph,
union 1,226,698 triples, 2026-08-21 편입관계 47,244건을 확인했다. 기존
7/10 데이터에 새 데이터를 덧붙인 것이 아니라 새 Docker volume을 만들어
검증한 뒤 포인터를 전환한 배포다.

| 항목 | 전환 전 | 전환 후 | 증감 |
|---|---:|---:|---:|
| union 고유 triple | 1,169,374 | 1,226,698 | +57,324 |
| ETF Holding | 47,016 | 47,244 | +228 |
| Holding 기준일 | 2026-07-10 | 2026-08-21 | 교체 |

## 57,324 triples 증가 원인

| 그래프 | 증가 | 구성 |
|---|---:|---|
| `abox/etf_kr` | +52,266 | 모든 Holding의 `supportedBy` +47,244; Document 723개 × 5 triples +3,615; Holding 순증 228개 × 5 구조 triples +1,140; `weight` 순증 +267 |
| `abox/company` | +5,056 | `Security` type +948; `securityCode` +948; 종목명·별칭 label +3,160 |
| `tbox/common` | +2 | 갱신된 공통 정의의 순증 |
| 합계 | **+57,324** | 중복 적재 없음 |

`new_security_nodes=831`은 완전히 새로 만들어진 증권 URI 수다. company
그래프의 type/code 증가 948건에는 이미 국내 ETF 상품 URI로 존재해 재사용된
117건도 포함된다. 따라서 831과 948의 차이는 중복 적재가 아니다.

## 공개 API 검증

검증 대상: `http://40.82.145.44:8000`

- `GET /health`: `readiness=true`, `graph_triples=1226698`
- `POST /db/sparql`: named graph 10개
- Holding 날짜 집계: `2026-08-21` 한 행, 47,244건
- RDB release: `financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38`
- Graph bundle archive SHA-256: `890500cc19f4d83203cee4a23130f6896eb1284643c1180cb844cdd66dfda395`

| named graph | triples |
|---|---:|
| `http://mafest.ai/graph/abox/bond_kr` | 264,465 |
| `http://mafest.ai/graph/abox/company` | 321,366 |
| `http://mafest.ai/graph/abox/etf_gl` | 56,541 |
| `http://mafest.ai/graph/abox/etf_kr` | 353,849 |
| `http://mafest.ai/graph/abox/fund_pub` | 227,934 |
| `http://mafest.ai/graph/tbox/bond_kr` | 351 |
| `http://mafest.ai/graph/tbox/common` | 1,033 |
| `http://mafest.ai/graph/tbox/etf_gl` | 122 |
| `http://mafest.ai/graph/tbox/etf_kr` | 790 |
| `http://mafest.ai/graph/tbox/fund_pub` | 247 |

## 롤백과 영수증

- 신규 활성 volume: `financial-agent-prep_oxigraph-holdings-20260821-de30afc2bcd4`
- 이전 활성·rollback volume: `financial-agent-prep_oxigraph-replace-20260901-00b5466f`
- rollback 기대 triple: 1,169,374
- cutover 시각: `2026-09-05T20:25:27+00:00`
- 원격 영수증: `/home/user1106/financial-agent-v2/shared/backups/graph-refresh-ontology-holdings-20260821-de30afc2bcd4/cutover-receipt.json`
- 이전 volume은 배포 스크립트가 삭제하지 않고 즉시 롤백 대상으로 보존한다.
- 영수증의 `status=cutover_passed`, bundle ID, archive SHA-256, 전환 전후
  volume, rollback volume, Holding·graph 집계를 인증된 원격 읽기로 확인했다.

## 애플리케이션 배포 전 상태

Graph 데이터 전환은 끝났지만 공개 Data API는 아직 `api_version=4.0.0`이고
`clova_configured=false`다. 이 값은 Graph 실패가 아니라 현재 Data API
컨테이너에 Clova 키가 주입되지 않았다는 뜻이다. Agent `/answer` 코드는 별도
배포·환경검증 후 단건 smoke와 Q1~Q35 각 1회 평가를 수행한다.
