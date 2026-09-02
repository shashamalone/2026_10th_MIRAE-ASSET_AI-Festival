# 결정 대기 목록 (온톨로지 적재)

> 최종 갱신 2026-08-21 · 근거: `python3 script/build_ontology_instances.py` 실행 출력
> 이 문서는 **사람이 골라야 하는 것**만 담는다. 코드로 자동 판정할 수 있는 것은 여기 없다.

## 배경 한 줄

원본 엑셀은 `위험등급: 5`, `투자지역: 남미/북미` 처럼 **현장 표기**로 적혀 있고,
온톨로지 사전은 `RiskGrade_5`, `Region_Americas` 라는 **표준 항목**으로 정의돼 있다.
둘을 잇는 것이 코드리스트 적재이고, 아래는 그 과정에서 **자동으로 못 잇는 것들**이다.

---

## 1. 결정 대기 4건

| # | 상황 | 규모 | 선택지 A | 선택지 B | 미결 시 영향 |
|---|---|---:|---|---|---|
| D1 | 레버리지 배수 `±0.5`·`±1.5`에 대응 항목이 사전에 없다. `etf_kr.ttl:100` 주석은 9종을 인지하는데 개체는 6개뿐 — **주석과 개체가 어긋나 있다** | 6종목 | 개체 3종 신설 (`Leverage_InverseHalf` 등) | 가까운 배수로 근사 매핑 후 근거에 명시 | 해당 6종목의 레버리지 질의가 누락 |
| D2 | `maturity_bucket`의 `미상` — 만기일이 sentinel(`0`/`99991231`)이라 만기 자체를 모르는 채권 | 319건 | `fp:Maturity_Unknown` 신설 | 트리플 생략(현재 상태) | **"만기 정보 없음"을 근거로 말할 수 없다.** 답변불가 판정의 근거가 사라짐 |
| D3 | 지방채가 대분류(`STD_PD_MCLS_NM`)에선 전부 `국공채`로 뭉쳐 있고, 지방채 성격은 소분류(`STD_PD_SCLS_NM`: 지역개발 1,266 / 도시철도 240 / 공모지방채 125)에만 있다. `fp:IssuerType_Municipal`이 0건인 이유 | 1,631건 | `hasBondIssuerType`의 `sourceColumn`에 소분류 추가 | 그대로 둠 | 지방채 질의 불가 |
| D4 | 해외ETF `wu_inv_rgn`은 국가 단위 59종(`Brazil`·`Korea`·`Canada`…)인데 사전은 지역 14개뿐. `common.ttl`의 `fp:InvestmentRegion` 주석이 이미 "국가→지역 매핑 필요"라고 예고 | 59종 | 국가→지역 매핑표 작성 | 그대로 둠 | "미국 ETF"는 되고 "브라질 ETF"는 안 됨 |

**공통 판단 기준:** 근사 매핑은 답변에 **거짓 근거**를 만든다. 애매하면 트리플을 만들지 않는 쪽이 안전하다 —
단 D2는 예외다. 트리플이 없으면 "모른다"는 사실 자체를 근거로 제시할 수 없기 때문이다.

---

## 2. 미매핑 원장 (4,193건 / 55종)

빌더가 **매 실행마다 전량 출력**한다. 조용히 버리지 않는다.

| 값 | 건수 | 성격 | 조치 |
|---|---:|---|---|
| `재간접` (AssetType 축) | 3,022 | 자산군이 아니라 **투자구조**. `FundType_FundOfFunds`로는 이미 연결됨 | **불필요** — 정상 |
| `06` (or_attr_desc) | 686 | 코드 잔재. 종목명이 주식-파생형·레버리지로 흩어져 자명한 대응 없음 | 보류 |
| `미상` (maturity_bucket) | 319 | → D2 | 결정 대기 |
| `0` (PD_RISK_GCD) | 58 | 0등급 개체 없음. 대부분 회사채·등급 결측 | 보류 |
| 해외 국가명 (`Brazil` 9, `Asia Pacific ex Japan` 8, `Korea` 7 …) | ~100 | → D4 | 결정 대기 |
| 기타 | 나머지 | 코드 잔재·결측 | 보류 |

---

## 3. 이미 해결된 것 (참고 — 같은 실수를 반복하지 않기 위해)

| 사건 | 무엇이었나 | 어떻게 잡았나 |
|---|---|---|
| **domain 위반 89건** | 사전에는 항목별 **적용 대상**이 정해져 있다. `hasFundType`은 공모펀드 전용인데 사모펀드 15건에, `hasReplicationMethod`는 ETF·펀드 전용인데 ETN 59건에 붙였다 (15×2 + 59 = 89) | `script/validate_ontology.py`가 자동으로 검출. 139만 건 중 89건이라 사람 눈으로는 불가능 |
| **표층형 충돌** | `AA-`를 신용등급 대역(`RatingBand_AA`)의 표기로 넣으면, 같은 문자열이 이미 개별 등급(`CreditRating`)의 표기라 사전이 두 항목을 가리킨다 | 사전 대신 **최장 접두 규칙**으로 처리 (`AAA`→`AA`→`A`) |
| **결정성 붕괴 위험** | 사전을 읽는 순서가 실행마다 달라지면 출력 TTL이 매번 바뀌어, "지난주 대비 뭐가 바뀌었나"를 볼 수 없게 된다 | 정렬 강제 + 충돌 시 즉시 중단 |

### 왜 domain 위반이 치명적인가

평가 문항에 **"VOO의 발행사를 알려줘"** 가 있다. VOO는 ETF이고 '발행사'는 채권에만 쓰는 개념이라,
우리는 *"확인할 수 없음"* 으로 답해 점수를 받기로 했다.
**우리 데이터가 그 규칙을 어기고 있으면 그 판정의 근거가 무너진다.**

---

## 4. 참고 — 확인 방법

```bash
# 적재 + 미매핑 원장 출력
python3 script/build_ontology_instances.py

# 검증 (domain/range 위반, 개체 수 대조, SPARQL 스팟체크)
python3 script/validate_ontology.py ; echo "exit=$?"
#   ↑ 파이프(| tail 등)를 거치면 $? 가 파이프 마지막 명령의 코드를 잡는다. 반드시 직접 실행할 것.
```

---

## 5. 온톨로지 엔지니어링 구현 개요

> 아래 내용은 [금융상품 온톨로지 엔지니어링 정의서](../../ontology_engineering_guide.html)의 요약을 이 문서에 반영한 것이다. 기존의 결정 대기 목록과 미매핑 원장은 유지하고, 현재 구현된 TBox·ABox·관계·검증 계약을 추가로 기록한다.

### 5.1 TBox의 목적과 범위

TBox는 금융상품 질의에서 상품 유형, 관계 방향, 허용된 분류, 근거 요건을 고정하는 의미 모델이다. 숫자 필터·집계는 RDB가 수행하고, Graph는 다중 홉 관계와 domain/range 제약을 담당한다.

현재 TBox는 `build_graph.py`가 생성하지 않는다. `ontology/*.ttl`의 5개 파일이 사람이 설계·관리하는 TBox이며, `build_ontology_instances.py`가 ABox를 생성하고 `build_graph.py`가 TBox와 ABox를 Oxigraph Store에 적재한다.

### 5.2 5개 TBox TTL과 namespace

| 파일 | 역할 | 주요 범위 |
|---|---|---|
| `ontology/common.ttl` | 공통 상위 스키마 | Product, Security, Organization, Document, Holding, 공통 분류·관계 |
| `ontology/bond_kr.ttl` | 국내채권 | 채권 유형, 발행사, 만기, 쿠폰, 담보, 신용등급 |
| `ontology/etf_kr.ttl` | 국내 ETF/ETN | ETF·ETN 분리, 레버리지, 운용전략, 복제방식, 테마 |
| `ontology/etf_gl.ttl` | 해외 ETF/ETN | 티커, ISIN, CIK, 투자전략, 인버스, 설정일 |
| `ontology/fund_pub.ttl` | 공모펀드 | 펀드 유형, 클래스, 환헤지, 판매상태, 투자자격, 벤치마크 |

```turtle
@prefix fp:  <http://mafest.ai/product#> .
@prefix fpi: <http://mafest.ai/instance/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
```

`fp:`는 TBox 클래스·property·통제어휘를 식별하고, `fpi:`는 상품·기업·관계·문서 인스턴스를 식별한다. 도메인별 TTL은 `owl:imports`로 `fp-common`을 가져온다.

### 5.3 Class 계층과 인스턴스 생성 기준

```text
fp:Product
├── fp:Bond
├── fp:ETF
├── fp:ETN
└── fp:PublicFund
```

- `Bond`와 `ETF`는 상품인 동시에 `Security`의 하위 개념이다.
- `PublicFund`는 공모펀드만 나타내며, `prvo_pbff_desc='사모'`인 행은 이 클래스에 넣지 않는다.
- `ShareClass`는 `PublicFund`의 하위로서 판매 클래스별 개별 종목을 표현한다.
- `Company`, `Issuer`, `AssetManager`, `Custodian`은 `Organization`의 역할별 하위 클래스다.
- `Holding`, `SubsidiaryRelation`, `Document`, `MetricSnapshot`은 시점·비중·소유비율·근거가 필요한 사실을 표현한다.
- 국내 ETF는 `pd_grp_no='ETF'`로 제한하고, ETN은 ETF와 별도 Class로 생성한다.
- 기업은 모든 기업을 무조건 복제하지 않고 편입·발행·자회사 관계에서 참조되는 기업을 생성한다.

### 5.4 Object Property 설계와 사용 조건

| Domain | Predicate | Range | 사용 조건 |
|---|---|---|---|
| `Bond` | `fp:issuedBy` | `Issuer` | 채권 전용. ETF에 적용하면 domain 위반 |
| `ETF ∪ ETN ∪ PublicFund` | `fp:managedBy` | `AssetManager` | 채권에는 사용하지 않음 |
| `ETF ∪ PublicFund` | `fp:hasHolding` | `Holding` | ETN 제외, 상품→증권 직결 금지 |
| `Holding` | `fp:holdingSecurity` | `Security` | 편입관계 중간 노드에서만 사용 |
| `Security` | `fp:issuedByCompany` | `Company` | 편입증권의 발행기업 연결 |
| `Product ∪ Company` | `fp:relatedToTheme` | `Theme` | 현재 국내 ETF 테마 관계 중심 |
| `Holding ∪ SubsidiaryRelation ∪ MetricSnapshot ∪ Risk` | `fp:supportedBy` | `Document` | 관계·주장에 근거문서 필요 |
| `Product` | `fp:sameVehicleAs` | `Product` | 동일 상품 연결. `owl:sameAs`는 사용하지 않음 |

관계 방향은 질의의 주체에서 대상으로 향한다. 예를 들어 ETF 편입 경로는 다음과 같다.

```text
ETF → hasHolding → Holding → holdingSecurity → Security → issuedByCompany → Company
```

`fp:sameVehicleAs`는 `owl:SymmetricProperty`로 선언되어 있다. 그러나 런타임 추론에 의존하지 않으므로 양방향 탐색이 필요한 경우 양쪽 triple을 직접 생성하거나 질의에서 양방향 경로를 명시한다. `fp:subsidiaryOf`는 지분율과 투자목적의 차이 때문에 `owl:TransitiveProperty`로 선언하지 않는다.

### 5.5 Datatype Property와 값 제약

Datatype property는 가능한 주체를 좁게 선언한다. 예를 들어 `maturityDate`는 Bond, `ticker`는 ETF/ETN, `saleStatus`는 PublicFund에 귀속한다.

| 타입 | 예시 | RDF datatype |
|---|---|---|
| 문자열 | `productName`, `ticker`, `organizationName` | `xsd:string` |
| 날짜 | `issueDate`, `maturityDate`, `asOf` | `xsd:date` |
| 수치 | `weight`, `couponRate`, `ownershipPct` | `xsd:decimal` |
| 논리값 | `isInverse`, `isSellable`, `currencyHedged` | `xsd:boolean` |
| 순서값 | `ratingRank` | `xsd:integer` |

모든 `owl:DatatypeProperty`에는 `fp:sourceTable`과 `fp:sourceColumn`을 기록한다. 파생값은 `derived:파일명.컬럼명`으로 구분한다. 전량 dummy인 괴리율·추적오차와 의미가 확인되지 않은 코드는 질의용 property로 노출하지 않는다.

### 5.6 Graph Relation Pattern

#### 기업-자회사

```text
Company → hasSubsidiary → SubsidiaryRelation
                              ├─ subsidiaryCompany → Company
                              ├─ ownershipPct
                              ├─ asOf
                              └─ supportedBy → Document
```

자회사 관계는 DART 원천과 접수일을 근거로 만들며, 출자 사실이 있다고 해서 모두 지배 자회사로 해석하지 않는다.

#### ETF-Holding-Security

```text
ETF → hasHolding → Holding
                     ├─ holdingSecurity → Security
                     ├─ weight
                     ├─ asOf
                     └─ supportedBy → Document
```

편입비중·기준일·근거문서를 Holding 노드에 함께 둔다. 현재 국내 ETF 편입관계가 중심이며 해외 ETF·펀드 편입분은 별도 수집 대상이다.

#### 상품-발행사·상품-테마

- 채권: `Bond → issuedBy → Issuer`
- 편입증권: `Security → issuedByCompany → Company`
- 테마: `Product → relatedToTheme → Theme`

ETF의 운용사를 채권 발행사로 연결하지 않도록 `issuedBy`, `managedBy`, `issuedByCompany`를 분리한다. `etf_theme.as_of`가 공란이면 기간 질의의 날짜 근거로 사용하지 않는다.

#### 관계-근거문서

`Holding`, `SubsidiaryRelation`, `MetricSnapshot`, `Risk`는 `fp:supportedBy`를 통해 `Document`에 연결한다. 문서에는 문서명·발행기관·발행일·근거 인용문이 있어야 하며, 문서에 함께 언급된 것만으로 관계를 새로 추론하지 않는다.

### 5.7 Semantic Definition과 포함/제외

Class는 원천 컬럼명이 아니라 질의에서 구분되어야 하는 금융상품·기관·관계·분류 개념이다. Property의 `rdfs:comment`에는 적용 대상, 원천 컬럼, 결측·sentinel 처리, 답변 가능성에 영향을 주는 규칙을 기록한다.

포함 대상은 질의 필터·조인·관계 탐색에 필요한 식별자·분류·수치·기준일·근거 속성이다. 제외 대상은 전량 dummy, 의미 미확정 코드, 룩어헤드 값, 근거 없는 추정 매핑, RDB에서 더 정확히 처리하는 파생 플래그다.

### 5.8 자연어–Ontology Term Mapping

| 자연어 표현 | Ontology term | 추가 조건 |
|---|---|---|
| 채권·회사채·국채 | `Bond`, `CorporateBond`, `GovernmentBond` | 원천 분류 및 하위 클래스 확인 |
| ETF·상장지수펀드 | `ETF` | 국내 질의는 ETN 제외 |
| 펀드·공모펀드 | `PublicFund` | 공모 조건 적용 |
| 기업·회사·모회사·자회사 | `Company` | `corpCode` 우선 |
| 발행사·발행기업 | `issuedBy` 또는 `issuedByCompany` | 주체가 Bond인지 Security인지 구분 |
| 운용사·관리회사 | `managedBy` | 상품 유형별 domain 확인 |
| 구성종목·편입종목 | `hasHolding` → `holdingSecurity` | Holding의 기준일·근거 확인 |
| 자회사·출자관계 | `hasSubsidiary` → `SubsidiaryRelation` | 지분율·투자목적 확인 |
| 관련 테마 | `relatedToTheme` | 기간 근거가 없으면 기준일 미상 |

“AA- 이상”은 `fp:ratingRank <= 4`로 해석한다. `AAAA`는 허용된 CreditRating 개체가 없으므로 `ABSTAIN_INVALID_TAXONOMY` 대상이다. “미평가 국채”는 `RatingStatus=UnratedByDesign`으로 표현한다. 근사 매핑은 거짓 근거를 만들 수 있으므로 사용하지 않는다.

### 5.9 URI·Entity Identifier·동일성

| 엔티티 | URI 패턴 |
|---|---|
| 국내채권 | `fpi:bond-{pd_no}` |
| 국내 ETF | `fpi:etfkr-{pd_itm_no}` |
| 해외 ETF/ETN | `fpi:etfgl-{pd_itm_no}` |
| 펀드 | `fpi:fund-{itm_no}` |
| 기업 | `fpi:corp-{corp_code}` |
| 증권 | `fpi:sec-{정규화 코드}` |
| 관계 | `fpi:hold-...`, `fpi:sub-...` |

상품 canonical ID는 원천 식별자를 사용한다. 채권 RDB join은 `(pd_no,pd_exg_mkt,info_seq)`를 보존하고, 펀드는 `itm_no`가 단독키다. 기업은 DART `corp_code`가 최우선이다.

펀드 KSD code와 국내 ETF `pd_itm_no`가 일치하는 47종은 `sameVehicleAs`로 연결하지만 ETF와 펀드 URI를 병합하지 않는다. 두 Class가 disjoint이므로 `owl:sameAs`를 사용하면 모순이 생긴다.

기업명은 법인격·한글 음차를 정규화한다. 예를 들어 `에스케이하이닉스(주)`와 `SK하이닉스`는 정규화 후 비교하되, DART code가 없으면 불확실한 동명이인 병합을 하지 않는다.

### 5.10 Source → Ontology Mapping

| 원천 | 변환 | Graph 대상 |
|---|---|---|
| `PRBD01N001` | raw + `bond_kr_enriched` | Bond, 등급, 만기, 발행사 |
| `PREF01N001` | ETF/ETN 필터 + `etf_kr_enriched` | 국내 ETF, 테마, Holding |
| `PREF02N001` | `pd_grp_no` 분리 | 해외 ETF/ETN |
| `PRFD01N001` | `itm_no` 직접 사용 | 공모 PublicFund, 사모 Product |
| DART/KIND 및 관계 CSV | 기업명·코드 정규화 | Company, Security, SubsidiaryRelation |

대표적인 column mapping은 다음과 같다.

| Property | Source table | Source column |
|---|---|---|
| `fp:issuedBy` | `PRBD01N001` | `pd_pbcm` |
| `fp:hasMaturityClass` | `derived:bond_kr_enriched` | `maturity_bucket` |
| `fp:hasRiskGrade` | 도메인별 원천 | risk code 컬럼 |
| `fp:relatedToTheme` | `derived:etf_theme` | `theme` |
| `fp:weight` | `data/relations/etf_holding` | `weight` |

URI에 사용할 수 없는 문자는 UTF-8 percent encoding을 적용하고, 한글은 가독성을 위해 유지한다. builder는 정렬된 입력으로 결정적 TTL을 생성하며 매핑 실패 건수를 출력한다.

### 5.11 Validation과 현재 실행 상태

현재 검증은 SHACL(pySHACL)이 아니라 Python validator와 Oxigraph SPARQL 검사로 구현되어 있다.

- TBox 5개 Turtle 파싱 및 도메인 파일의 `owl:imports`
- 모든 typed property의 domain/range
- 모든 Class·Property·통제어휘 개체의 `rdfs:label`
- 모든 datatype property의 `sourceTable/sourceColumn`
- `issuedBy` domain=Bond 단독, ETF–Bond disjoint
- 신용등급 rank 1~19, `AAAA` 부재, 등급 상태 개체 분리
- 테마 176종 및 ABox 개체·관계 수와 CSV 행수 대조
- 관계별 `supportedBy` 문서와 cutoff 준수
- Company→Subsidiary→Security→Holding→ETF 대표 경로 spot check

TBox의 cardinality를 OWL restriction이나 SHACL shape로 전면 선언하지는 않았다. 대신 validator가 cutoff 내 관계의 evidence 1개, 문서 필수 속성, ABox 수량, 관계 방향을 계약으로 검사한다.

### 5.12 대표 Mapping 사례

질의 “에코프로의 자회사가 편입된 ETF는?”은 다음 경로로 매핑한다.

```text
Company(에코프로)
 → hasSubsidiary → SubsidiaryRelation
 → subsidiaryCompany → Company(에코프로비엠)
 ← issuedByCompany ← Security(247540)
 ← holdingSecurity ← Holding
 ← hasHolding ← ETF
```

최종 응답에는 ETF 목록뿐 아니라 Holding의 비중·기준일·source, 자회사 관계의 기준일·DART 문서, 그리고 데이터가 부족한 경우 그 사유를 함께 전달한다.

### 5.13 현재 미구현·주의사항 요약

- `build_graph.py`는 TBox 생성기가 아니라 TBox+ABox를 Oxigraph에 적재하는 빌더다.
- Graph Store와 SPARQL runtime은 `pyoxigraph` 설치 및 Store 생성이 필요하다.
- 해외 ETF·공모펀드 편입관계는 아직 데이터 갭이다.
- 해외 편입증권 Entity Resolution과 일부 KR7 ISIN 정규화는 RDB·Graph 경로 간 일관성 점검이 필요하다.
- `etf_theme.as_of`는 미상이며, `fpi:sec--`와 같이 코드가 `-`인 편입증권은 단일 노드 병합 위험이 있다.
- D1~D4 결정이 끝나기 전에는 대응 개체를 임의로 신설하거나 근사 매핑하지 않는다.
