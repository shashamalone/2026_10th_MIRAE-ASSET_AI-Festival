# 속성별 저장소 매핑 (PROPERTY_STORAGE_MAP)

> 2026-08-22 · 생성물 — 직접 편집하지 말고 `python3 script/build_storage_map.py`로 재생성한다.
> 산출: `docs_data_layer/PROPERTY_STORAGE_MAP.csv` (136행)

## 왜 만들었나

TBox는 `fp:` 속성을 **136개** 선언하지만, 인스턴스 빌더가 그래프에 실제로 넣는 것은 **37개**뿐이다.
나머지 99개는 성격이 갈리는데 그 구분이 지금까지 `build_ontology_instances.py` 독스트링의
산문("넣지 않는 것: 파생 플래그는 RDB 담당")에만 있었다.

2단계 스키마 검색은 `rdfs:comment`를 임베딩하므로 **136개가 전부 후보로 뜬다.** 라우터가
`fp:ratingRank`를 골라 SPARQL을 쏘면 0행이 돌아오고, 그게 "확인할 수 없음"으로 나가면
**답할 수 있는 질문에 오답을 내는 것**이다. `vec.schema_index.storage` 컬럼이 이걸 막으라고
있는 자리인데 값을 채울 소스가 없었다. 이 표가 그 소스다.

## 컬럼

| 컬럼 | 뜻 |
|---|---|
| `storage` | 어느 엔진이 담당하는가 — `graph` / `rdb` / `vector` / `none` |
| `availability` | **지금 조회 가능한가** — `loaded`(그래프 적재됨) / `raw`(VM `raw.*`에 있음) / `derived-not-deployed`(파생 계층 빌드 선행) / `pending-embedding` / `pending-collection` / `unavailable` |
| `derivation` | 파생 테이블의 **재현 가능성** — `pure` / `external` / `planned` |
| `domain_caveat` | 도메인별로 가용성이 갈리는 경우의 원문 인용 |
| `source_tables` `source_columns` | TBox의 `fp:sourceTable`·`fp:sourceColumn` 원문 |
| `comment` | `rdfs:comment` 전문 — 모든 판정의 근거 |

`storage`와 `availability`를 나눈 이유: **"RDB 담당"과 "지금 RDB에서 뽑을 수 있다"는 다르다.**
`fp:ratingRank`는 `storage=rdb`지만 `availability=derived-not-deployed`다.

## 분포

| storage | 개수 | | availability | 개수 | | derivation | 개수 |
|---|---:|---|---|---:|---|---|---:|
| `rdb` | 83 | | `raw` | 63 | | (해당없음) | 100 |
| `graph` | 37 | | `loaded` | 37 | | `pure` | 20 |
| `none` | 9 | | `derived-not-deployed` | 20 | | `planned` | 8 |
| `vector` | 7 | | `unavailable` | 9 | | `external` | 8 |
| | | | `pending-collection` | 6 | | | |
| | | | `pending-embedding` | 1 | | | |

## 바로 쓸 수 있는 것 4가지

### ① 답변불가 화이트리스트 9개 — LLM 호출 0회로 판정

`storage=none`인 9개는 **데이터 자체가 없어** 인스턴스를 만들 수 없다. 근거는 전부
`rdfs:comment`에 명시돼 있다("현재 데이터로 값을 채울 수 없다").

```
belongsToIndustry  hasCollateralType  hasCustodian  hasDistributionType
hasIssuanceType    hasIssuerCategory  hasRedemptionType  hasUnderlyingScope  subsidiaryOf
```

그라운딩이 이 중 하나에 걸리면 **즉시 답변불가**다. 검색도 LLM도 돌릴 필요가 없다.
예: "월배당 ETF" → `hasDistributionType` → 배당 컬럼 전량 무효 → 답변불가.

### ② 🔴 도메인별 부분 가용성 9건 — 조용한 오답의 최대 원인

같은 속성이 **어떤 도메인에서는 되고 어떤 도메인에서는 안 된다.** 이건 "0행"으로 나타나기
때문에 "해당 상품 없음"과 구분되지 않는다. **반드시 답변불가로 갈라야 한다.**

| 속성 | 안 되는 도메인 |
|---|---|
| `return1Y` | **해외ETF** — `du_er_1d` 전량 0 미계산. 해외ETF 성과 질의는 답변 불가 |
| `leverageFactor` | 해외ETF 전량 결측 → 국내ETF에서만 정형 필터 |
| `onSale` | 해외ETF 전량 1 → 필터로 기능하지 못함 |
| `tradingSuspended` | 해외ETF 전량 0 → 축 자체가 없음 |
| `hasRiskGrade` | 해외ETF에 위험등급 컬럼 없음 |
| `coreProduct` | 해외ETF Y가 0건 |
| `expenseRatio` | ETN (총보수 개념 없음) |
| `hasHolding` | ETN (편입종목 개념 없음) |
| `agencyRatings` | 평가기관명이 데이터에 없어 3항 관계로 완전 분해 불가 |

**패턴이 보인다 — 위험의 대부분이 해외ETF에 몰려 있다.** "수익률 좋은 ETF" 같은 질의가
도메인 구분 없이 들어오면 해외ETF는 조용히 빠지고, 그 사실이 답변에 드러나지 않는다.

### ③ `derivation=pure` 20개 — raw만으로 즉시 복구 가능

`bond_kr_enriched`·`etf_kr_enriched`·`fund_pub_dedup`·`etf_theme` 4개 테이블은 생산
스크립트가 **`data/csv` 원본만 읽는다.** 외부 의존이 없으므로 `raw.*`에서 SQL 계산 컬럼으로
바로 되살릴 수 있다. `isSellable`·`ratingRank`·`remainingDays`·`maturityBucket` 등이 여기 속한다.

### ④ 🔴 `derivation=external` 8개 — 재현 불가, 파일을 받아야 한다

`company_master`·`company_subsidiary`(DART), `etf_holding`(운용사 사이트), `document`는
외부 수집분이다. **지금 재수집하면 8/18 수집분과 결과가 달라진다** — 운용사 사이트가 상장폐지
종목을 지우기 때문이다(생존편향, 25종). 재빌드가 아니라 **산출된 `instances_*.ttl` 5파일 자체를
전달·보관**해야 한다.

## 개별 속성 주의사항

### 🔴 `remainingDays` — 원본값을 쓰지 말 것

`PRBD01N001`의 `REMAINING_DAYS` 원본은 **어느 기준일과도 맞지 않는다**(2026-08-22 실측).

| 비교 기준 | 원본 − 실제 잔존일수 (평균) |
|---|---:|
| 채권 실질 기준일 2026-02-24 | +118일 |
| 공식 데이터 기준일 2026-07-11 | +255일 |

역산하면 **2025-10월 말께 산출된 값**이다. 그대로 쓰면 만기가 지난 채권이 "판매 가능"으로
잡힌다 — 실제로 "판매가능 AA-이상 원화채권"에서 **41건의 만기 경과 채권이 섞여 68건이
27건으로 부풀었다.** `maturity_date` 기준으로 재계산하고 원본은 `remaining_days_raw`로 보존한다.

`fp:isSellable`·`fp:maturityBucket`도 잔존일수에 의존하므로 같은 영향을 받는다.

## 한계

- `availability=raw`는 "**컬럼이 `raw.*`에 있다**"는 뜻이지 "값이 쓸 만하다"가 아니다.
  더미·sentinel 문제는 `domain_caveat`와 `comment`, 그리고 `AGENTS.md` 함정 표를 함께 봐야 한다.
- `UNFILLABLE`·`DOC_LAYER` 두 집합만 사람이 정했다. 나머지는 TBox와 빌더 소스에서 기계적으로
  뽑는다. 두 집합의 판정 근거는 각 행의 `comment` 컬럼에 원문 그대로 실려 있으니 검증 가능하다.
- `hasCustodian`은 기관코드 18종이 `raw`에 있으나 **코드↔사명 매핑표가 없어** `none`으로 뒀다.
  "수탁회사가 국민은행인 펀드"에 답할 수 없다는 실질 기준을 따른 것이다. 코드 자체를 답에 쓸
  수 있게 되면 재분류 대상이다.
