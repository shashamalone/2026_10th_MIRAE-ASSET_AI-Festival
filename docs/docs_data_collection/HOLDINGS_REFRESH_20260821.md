# 국내 ETF 편입종목 2026-08-21 갱신 기록

검증일: 2026-09-06 (Asia/Seoul)
작업: T-146 / `codex-t146-holdings-0906`

## 결론

기존 운영 Graph의 편입관계 47,016건은 모두 `as_of=2026-07-10`이었다. 이는
주최측 2026-08-24 파일이 잘못 적재된 것이 아니라, 주최측 파일 자체에 ETF
편입종목이 없어 7/10에 별도 수집한 운용사 공시를 사용했기 때문이다.

이번 갱신은 주최측 `PREF01N001` 1,780행(ETF 1,235종, ETN 545종)을 상품
정본으로 유지하고, 그중 KODEX/TIGER/RISE/ACE ETF의 운용사별 8/21
편입내역만 다시 수집한다. `8/24`는 배포본 cutoff이고 편입관계의 실제 날짜가
아니므로 Graph의 `fp:asOf`는 검증된 `2026-08-21`로 기록한다.

## 입력과 판정 규칙

| 항목 | 값 |
|---|---|
| 공식 2026-08-24 XLSX 보존 영역 | `data/ai-festival2026_금융상품Agent_DtataSet260824/` (읽기 전용) |
| 해시 대조용 로컬 사본 | `data/data/csv/pref01n001_data.xlsx` (운영 입력 아님) |
| 주최측 원본 XLSX SHA-256 | `18c4329d8fc8768d030316816f3e6e48226a3c217db3354245b766a2c6f6c592` |
| 상품 정본 | `data/snapshots/legacy-build-2026-08-24/data/csv/PREF01N001_etf_kr_master_20260824.csv` |
| 상품 정본 SHA-256 | `89359782d5b021e5bf87809147405b1d228f41dd83929936504bf4a7718d1509` |
| 상품 정본 행 | 1,780 |
| 편입 기준일 | 2026-08-21 |
| cutoff | 2026-08-24 |
| 이전 Graph | Holding 47,016건, 711개 ETF, 모두 2026-07-10 |

해시 대조용 XLSX 사본은 운영 `/db/version`에 기록된
`PREF01N001.data_sha256`과 일치한다. 하지만 `data/data/`는 작업공간 정책상
legacy 참고영역이므로 운영 적재나 재생성 입력으로 사용하지 않는다. 실제
Graph 생성은 공식 원본을 정규화해 불변 보존한
`data/snapshots/legacy-build-2026-08-24/.../PREF01N001_etf_kr_master_20260824.csv`를
상품 식별 입력으로 사용했다.

대상은 상품 정본에서 `pd_grp_no='ETF'`이고 약어 첫 토큰이 네 브랜드인
상품이다. `pd_lste_dt <= 20260821`인 상품은 해당 스냅샷 시점에 종료된
상품이므로 “수집 실패”가 아니라 비대상으로 기록한다. 응답이 비어 있거나
운용사 목록에서 식별되지 않는 활성 상품만 실패로 센다.

날짜 증거는 KODEX의 `pdf.gijunYMD`, ACE의 `pdfList[].std_DT`를 응답
본문에서 직접 대조한다. TIGER와 RISE는 날짜가 들어간 운용사 문서
엔드포인트(`fixDate`, `searchDate`)에 요청하고, 응답 행 수와 원문 해시를
함께 보존한다. 모든 raw에는 URL, 회수시각, 기준일 증거, 행 수, SHA-256이
있는 sidecar가 따라간다.

## 수집 결과

| 운용사 | 8/21 활성 대상 | 검증 공시 | 미확보 | 편입 행 |
|---|---:|---:|---:|---:|
| KODEX | 240 | 240 | 0 | 18,024 |
| TIGER | 231 | 231 | 0 | 14,521 |
| RISE | 142 | 142 | 0 | 8,394 |
| ACE | 112 | 110 | 2 | 6,305 |
| 합계 | **725** | **723** | **2** | **47,244** |

8/21 전에 거래가 끝난 25종은 비대상으로 분리했다. 검증된 723종은 모두
동일한 기준일이고 상품별 비중 합계 95~105% 이탈은 0종이다. 최종 관계
CSV SHA-256은
`91c0604899cea2eb3ecb3adae86e03cf13c3df302429f45b270ba8430c9c93a8`이다.

미확보 2종은 다음과 같다. 둘 다 HTTP 오류나 날짜를 현재값으로 대체한 것이
아니라, ACE가 요청한 8/21에 `pdfList=[]`를 반환해 관계 부재 여부를 판정할 수
없는 경우다.

| 상품코드 | 상품명 | 처리 |
|---|---|---|
| KR70233A0001 | ACE 삼성전자SK하이닉스플러스채권혼합50 | 미확보, Holding 생성 안 함 |
| KR7265690008 | ACE 러시아MSCI(합성) | 미확보, Holding 생성 안 함 |

Cambricon 표기는 세 식별자 계열(`688256 C1 Equity`, `688256 CH`,
`CNE1000041R8`)로 14개 ETF에서 확인됐다. Q22가 요구하는 중국·반도체
교집합 세 상품은 KODEX 10.42%, RISE 13.25%, TIGER 8.82%이며 모두
`as_of=2026-08-21`이다.

## Graph 생성 규칙

1. 검증된 이전 10개 TBox/ABox bundle을 읽기 전용 baseline으로 연다.
2. `instances_etf_kr`에서 기존 `fp:hasHolding` 간선과 `fp:Holding` 노드만 제거한다.
3. 검증된 관계 CSV로 Holding, weight, asOf, sourceId를 결정적으로 재생성한다.
4. 상품별 운용사 공시 Document를 만들고 모든 Holding에 `fp:supportedBy`를 연결한다.
5. 기존 기업·테마·분류·상품 triple은 유지한다. 새 증권 식별자만 company ABox에 추가한다.
6. 파일별 SHA-256, triple 수, union 고유 triple 수를 manifest에 기록한다.

로컬 최종 bundle은 `ontology-holdings-20260821-de30afc2bcd4`다. Holding
47,244건, 근거 Document 723건, `supportedBy` 47,244건을 포함하며 10개
named graph의 union은 1,226,698 triples이다. 같은 입력으로 두 번 생성해
10개 RDF 파일의 SHA-256 차이가 0건이고 bundle ID도 동일함을 확인했다.
로컬 질의에서 7/10 Holding은 0건, 8/21 Holding은 47,244건이었다.

## 원격 전환 규칙

새 bundle은 새 Docker volume에 먼저 적재한다. 정확히 10개 named graph,
default graph 0건, manifest와 동일한 graph별 수, Holding 기준일이 오직
2026-08-21인지 확인하기 전에는 운영 포인터를 바꾸지 않는다. 기존 활성
volume은 삭제하지 않고 rollback 대상으로 보존한다. 전환 후 public
`/db/sparql`에서도 날짜와 건수를 다시 확인한다.

원격 cutover는 2026-09-05T20:25:27Z에 완료됐다. 이전 활성 volume
`financial-agent-prep_oxigraph-replace-20260901-00b5466f`은 삭제하지 않고
rollback 대상으로 보존했으며, 신규 활성 volume은
`financial-agent-prep_oxigraph-holdings-20260821-de30afc2bcd4`다. 공개
`/health`와 `/db/sparql`에서 10개 named graph, union 1,226,698 triples,
2026-08-21 Holding 47,244건을 재확인했다. 원격 영수증은
`/home/user1106/financial-agent-v2/shared/backups/graph-refresh-ontology-holdings-20260821-de30afc2bcd4/cutover-receipt.json`이며,
배포 archive SHA-256은
`890500cc19f4d83203cee4a23130f6896eb1284643c1180cb844cdd66dfda395`다.

## 범위와 남은 차이

이 작업은 Graph 편입관계 갱신이다. PostgreSQL의
`relations.product_holding` 46,951건(2026-07-10)은 별도 데이터 플랫폼
release 없이는 바뀌지 않는다. Agent의 Q22 관계 경로는 Graph를 사용하므로
이번 전환으로 최신화되지만, 두 저장소의 기준일 차이는 후속 RDB release 전까지
명시적으로 남긴다.
