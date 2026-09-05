# 외부 데이터 구축 플랜 (사이드 트랙)

작성일 2026-09-05 · 데이터 기준일 2026-08-24 · 근거: 골든셋 `external_needed` 열, 2026-09-03 측정, 2026-09-05 계획 리뷰 §5·§9

## 0. 왜 지금은 P2인가

2026-09-03 측정에서 오답 89회차 중 "그래프 데이터 부재"(A)·"벡터 검색 실패"(B)가 1차 원인인 회차는 0건이다. 지금 틀리는 이유는 RDB SQL 생성과 답변 생성이고, 데이터가 없어서 틀리는 것이 아니다. 그래서 스프린트 P0에는 넣지 않았다.

다만 골든셋 35문항 중 8문항(Q22·Q23·Q24·Q26·Q27·Q28·Q29·Q30)은 P0를 전부 끝내도 **해외 ETF·펀드 편입내역은 없어 산출 불가**가 정답 상한이다. 그 위로 올라가려면 아래 데이터가 필요하다. 이 문서는 P0와 병행해 준비만 해 두고, P0 재측정이 끝난 뒤 적재 여부를 결정하기 위한 것이다.

**2026-09-05 실측 정정.** 초안의 "fp:Holding 인스턴스 0건"은 틀렸다. Oxigraph 스토어에 국내 ETF 711종·47,016건의 `fp:Holding`(as_of 2026-07-10)과 `fp:SubsidiaryRelation` 30,097건이 이미 적재돼 있고, "SK하이닉스를 편입한 ETF"를 결정적 plan과 같은 SPARQL로 직접 조회하면 118종(삼성전자 132종)이 나온다. 09-03 측정의 Graph abstain은 데이터 부재가 아니라 (a) 스토어에 `fp:supportedBy`·`fp:Document` 트리플이 0건이라(TTL에는 47,016건 존재) 컴파일러가 붙이는 evidence 컬럼이 비어 `abstain_evidence_missing`으로 떨어진 것, (b) intent가 회사명을 `product` 역할로 넘겨 Company 클래스를 시도조차 안 한 `abstain_entity_not_found`(SK하이닉스·LG에너지솔루션)다. 둘 다 Graph 로직·스토어 재빌드 이슈이며 외부데이터 수집으로 풀리는 것이 아니다. 진짜 데이터 공백은 해외 ETF·펀드 편입, 해외 증권(캠브리콘·엔비디아)의 Company 노드, 국내 편입의 08-24분 스토어 미반영이다.

## 1. 필요한 데이터 (골든셋 역산)

| 데이터 | 막힌 문항 | 골든셋이 지목한 출처 | 온톨로지 수용처 |
|---|---|---|---|
| **국내 ETF 편입종목**(종목·비중·기준일) | Q22·Q24·Q26·Q28·Q30 | 운용사 사이트 6곳(TIGER·KODEX·RISE·ACE·PLUS·SOL). 조인키 `pd_itm_no`(ISIN) | `fp:Holding` (n-ary: weight·asOf·supportedBy) — **스토어에 711종 47,016건 적재(as_of 2026-07-10)**. `data/relations/etf_holding.csv`는 828종 82,699행(07-10분 47,016 + 08-24분 35,683)이나 08-24분은 TTL·스토어 미반영. 비중 결측 1,178행, 증권코드 공란 1,280건 |
| **해외 ETF 편입종목** | Q22·Q28·Q29 | SEC N-PORT. `pd_us_cik` 389개 있음, 시리즈ID 추가 필요 | 같은 `fp:Holding` — 인스턴스 0건 |
| **공모펀드 편입종목** | Q10·Q30 | 자산운용보고서(운용사·협회) | 같은 `fp:Holding` — 인스턴스 0건 |
| **기업 지배구조(모자회사)** | Q24·Q27 | DART 타법인출자현황(`otrCprInvstmntSttus`) | `fp:SubsidiaryRelation` — **스토어에 30,097건 적재**(`data/relations/company_subsidiary.csv`, 모회사 2,325개, as_of 2025-04-17~2026-08-14) |
| **편입종목 ↔ 기업 매핑** | Q22·Q24·Q26 | 종목코드→기업(DART corp_code). `src/data/enriched/holding_code_map.csv` 1,393행 | `fp:issuedByCompany` — 증권 11,879종 중 1,306종(11%)만 연결. 해외 증권(캠브리콘·엔비디아 등)은 Company 노드 자체가 없음 |
| **테마 부여 이력**(시점) | Q23 | LSEG themes 스냅샷 시계열 또는 뉴스·공시 이벤트 일자 | `fp:MetricSnapshot` 또는 테마 관계에 asOf |
| **위험요인·전략 원문** | Q24·Q27·Q28 | 투자설명서·운용보고서 텍스트 | VectorDB `vec.document_chunk` (현재 9,055청크, 대부분 `risk` 섹션) |

## 2. 절대 조건

1. **`as_of ≤ 2026-08-24`.** 편입내역·지분관계·테마 전부 수집 시점이 아니라 **데이터 자체의 기준일**이 08-24 이하여야 한다. N-PORT는 분기 보고라 2026-06-30 기준분이 마지막이다. 운용사 PDF는 08-24 이전 날짜의 파일만 쓴다.
2. **주최측 데이터 우선.** 편입내역의 ETF 식별·AUM·기준일은 주최측 테이블 값을 쓰고, 외부값과 다르면 evidence에 상충을 기록한다.
3. **생존편향 명시.** 운용사 사이트는 상장폐지 종목을 지웠다(AGENTS.md 함정: 25종 0행). 확보 실패는 "편입종목 미확보"로 남기고, 조용히 "편입 안 함"으로 흘러가면 안 된다.
4. **`data/csv/` 불변.** 수집물은 `data/enriched/` 또는 `data/relations/`에 두고, 재생성 산출물은 `artifacts/`.
5. **완전일치 원칙.** 종목명→기업 매핑에서 유사명 대체 금지. 매핑 실패는 미매핑으로 남긴다.

## 3. 단계별 플랜

| 단계 | 내용 | 산출물 | 검증 | 규모 (human / CC) |
|---|---|---|---|---|
| E0 | 커버리지 조사: 골든셋 8문항이 실제로 요구하는 ETF·펀드 목록을 뽑고, 각 상품의 08-24 이전 편입내역 공시가 존재하는지 확인. 확보 가능 비율을 먼저 수치로 낸다 | `docs/external_coverage_YYYYMMDD.md` | 상품별 O/X 표 | 1일 / 2시간 |
| E1 | 국내 ETF 편입종목 **갱신·보강**(신규 수집 아님): `data/relations/etf_holding.csv`에 이미 있는 08-24분 35,683행을 TTL·스토어에 반영하고, 증권코드 공란 1,280건·비중 결측 1,178행·6개 운용사 밖 ETF의 커버리지 공백을 채운다 | CSV + provenance | `validate_external.py`: as_of ≤ 08-24, 비중 합 90~110%, ISIN 존재 | 1일 / 반일 |
| E2 | 편입종목→기업 매핑: `holding_code_map.csv`(1,393행) 보강(KRX 종목코드→DART corp_code 완전일치). 현재 `fp:issuedByCompany`는 증권 11%만 연결 | CSV | 매핑률·미매핑 목록 | 1일 / 3시간 |
| E3 | DART 지분관계 **보강**: `company_subsidiary.csv` 30,097행이 이미 있으므로 Q24·Q27 대상 기업(에코프로·LG에너지솔루션)의 누락 자회사만 점검 | 같은 CSV | as_of·출처 검증 | 반일 / 2시간 |
| E4 | 스토어 재빌드: `build_graph_instances.py`는 Holding·SubsidiaryRelation·Document(supportedBy) 생성 로직을 이미 갖고 있다. TTL 재생성 → `build_graph.py`로 Oxigraph 재빌드해 `fp:supportedBy`·`fp:Document` 0건 상태를 해소 | ttl + 스토어 | `validate_ontology.py`, `?h fp:supportedBy ?d` 건수 = Holding 건수, seed 인덱스 캐시 자동 무효화 확인 | 반일 / 2시간 |
| E5 | 해외 ETF N-PORT: VOO·IVV·SPY 등 골든 언급 상품부터 시리즈ID 확보 → 2026-06-30 기준 편입종목 | CSV | as_of, 비중 합 | 2일 / 반일 |
| E6 | 재측정: 8문항 warm 3회. "산출 불가"에서 "산출"로 바뀐 Claim 수와 정답률 변화 | trace + 표 | 기존 하네스 | 2시간 |

E0가 먼저다. 확보 가능 비율이 낮으면(예: 08-24 이전 공시가 절반도 안 되면) E1 이후를 축소한다.

## 4. 스키마 (`fp:Holding`, `ontology/instances_etf_kr.ttl` 실제 적재 형태)

```
fpi:etf-{pd_itm_no}
    fp:hasHolding      fpi:hold-{pd_itm_no}-{holding_code}-{seq} .   # 상품 → 편입관계 (common.ttl 314행)

fpi:hold-{pd_itm_no}-{holding_code}-{seq}
    a fp:Holding ;
    fp:holdingSecurity fpi:sec-{holding_code} ;      # 편입관계 → 증권 (320행)
    fp:weight          "26.92"^^xsd:decimal ;        # 비중(%) (561행)
    fp:asOf            "2026-07-10"^^xsd:date ;      # 편입 기준일 (568행, ≤ 2026-08-24)
    fp:sourceId        "KODEX" ;                     # 원천 운용사
    fp:supportedBy     fpi:doc-{hash} .              # 근거 문서 (371행)

fpi:doc-{hash}
    a fp:Document ;
    fp:documentTitle "KODEX 반도체 구성종목 현황 (2026-07-10)" ;
    fp:documentPublisher "..." ;
    fp:documentPublishedDate "2026-07-10"^^xsd:date ;
    fp:documentQuote "{...원천 행 JSON...}" .

fpi:sec-{holding_code}
    a fp:Security ; rdfs:label "SK하이닉스" ; fp:securityCode "000660" ;
    fp:issuedByCompany fpi:corp-{dart_corp_code} .   # 증권 → 기업 (326행)
```

`fp:sourceTable`·`fp:sourceColumn`은 인스턴스가 아니라 `common.ttl`의 속성(TBox) 애노테이션이다. 해외 ETF·펀드 편입(E5)도 이 형태를 그대로 쓴다. `graph_plan.py`의 `company_holding_etf_plan`·`subsidiary_holding_etf_plan`이 쓰는 술어(`fp:issuedByCompany`, `fp:holdingSecurity`, `fp:hasHolding`, `fp:weight`)와 일치함을 확인했다.

## 5. 파이프라인 연결 (적재 후 바뀌는 것)

- Graph: `graph_plan.py`의 편입·자회사 관계 계획은 이미 있고 스토어에 행도 있다(SK하이닉스 118종). 그런데도 abstain이 나는 원인은 두 가지다. (1) `compile_graph_plan`이 Holding 노드에 `fp:asOf`·`fp:sourceId`·`fp:supportedBy`·`fp:documentTitle`을 evidence 컬럼으로 붙이고 `resolve_evidence`가 하나라도 None이면 abstain하는데, 현재 스토어에 `fp:supportedBy`·`fp:Document`가 0건이다(TTL에는 47,016건·46,961노드 존재 — 스토어 최초 sst가 08-25, TTL 재생성이 08-26이므로 재빌드 누락으로 **추정**). 09-03 trace의 `evidence 누락 행` 19회가 이것이다. E4 재빌드로 해소된다. (2) intent가 "SK하이닉스"·"LG에너지솔루션"을 `product` 역할로 넘겨 `graph_entity.py`의 역할→클래스 표(`product` → ETF·PublicFund·Bond·ETN·Product)가 Company를 시도하지 않는다. 이건 외부데이터가 아니라 P0의 intent/엔티티 해소 이슈다. 진짜 데이터 공백으로 not_found가 맞는 것은 캠브리콘(Company 노드 없음)과 S&P 500(지수 엔티티 없음)뿐이다.
- Graph→RDB 핸드오프: `_apply_graph_handoff`가 `entity_codes`를 `상품코드 IN (...)` 조건으로 넘긴다. 편입 ETF 코드가 여기로 흐른다.
- 답변: `_build_retrieved_context`가 Graph evidence(source_table·source_column·as_of)를 이미 인용한다.
- seed 인덱스: 스토어 재빌드 시 mtime이 바뀌어 `artifacts/graph_entity_index.pkl`이 자동 재생성된다(15초).

## 6. 하지 않는 것

- 뉴스 크롤링으로 "테마 연결 이력"을 만드는 일. 08-24 이후 기사가 섞이면 룩어헤드다. Q23은 테마 스냅샷 시계열이 없으면 "시점 축 부재"로 답하는 것이 정답이다.
- 편입내역을 LLM에게 추정시키는 일.
- 08-24 이후 기준일 데이터로 "최신"을 채우는 일.

## 7. 성공 기준

- E1 커버리지: 골든 8문항이 지목한 국내 ETF의 편입내역 확보율 ≥ 80% (E0에서 수치 확정).
- `validate_external.py`·`validate_ontology.py` 통과, 모든 행 `as_of ≤ 2026-08-24`.
- 재측정에서 Q22·Q24·Q26·Q28 중 최소 2문항이 "산출 불가"에서 "부분 산출" 이상으로 이동하고, A·B 원인 오답이 새로 생기지 않는다.
