# GRAPHDB DEFINITION V2.0

자동 생성 파일입니다. 직접 편집하지 말고 `python src/kb/build_catalog_v2.py`를 실행합니다.
의미 정의의 정본은 [TBox TTL 5개](../../ontology/)이며 ABox 생성 규칙은 [Graph 빌더](../../src/kb/build_graph_v2.py)가 소유합니다.

- 데이터 버전: `financial-products-2026-07-11`
- 배포일: `2026-07-11`
- 외부 근거 cutoff: `2026-07-11`

## 범위와 엔진

- 엔진: Oxigraph, SPARQL 1.1 읽기 전용 서비스
- ontology namespace: `fp: <http://mafest.ai/product#>`
- instance namespace: `fpi: <http://mafest.ai/instance/>`
- TBox와 ABox는 별도 named graph로 벌크 로드하며 런타임에 TTL을 파싱하지 않습니다.
- ABox 트리플 수는 입력 관계 데이터에 따라 달라지므로 정의서에 고정하지 않고 `graph_manifest.json`과 `/health`로 확인합니다.

## TBox 요약

- 전체 TBox 트리플: 2,619
- grounding term(`rdfs:comment` 보유): 189
- 클래스: 55
- ObjectProperty: 45
- DatatypeProperty: 94
- 통제어휘 개체: 297

| TBox 파일 | named graph | 트리플 | 역할 |
|---|---|---:|---|
| [`common.ttl`](../../ontology/common.ttl) | `http://mafest.ai/graph/tbox/common` | 1,058 | 공통 상품·문서·관계·분류·위험등급 어휘 |
| [`bond_kr.ttl`](../../ontology/bond_kr.ttl) | `http://mafest.ai/graph/tbox/bond_kr` | 387 | 국내채권 속성·등급·만기·담보·발행 어휘 |
| [`etf_kr.ttl`](../../ontology/etf_kr.ttl) | `http://mafest.ai/graph/tbox/etf_kr` | 790 | 국내 ETF/ETN 분류·거래·위험 속성 |
| [`etf_gl.ttl`](../../ontology/etf_gl.ttl) | `http://mafest.ai/graph/tbox/etf_gl` | 136 | 해외 ETF/ETN 전략·설정일·식별 속성 |
| [`fund_pub.ttl`](../../ontology/fund_pub.ttl) | `http://mafest.ai/graph/tbox/fund_pub` | 248 | 공모펀드·클래스·판매·수익률 속성 |

## ABox named graph와 원천

| ABox 파일 | named graph | 주요 원천 | 포함 개체/관계 |
|---|---|---|---|
| `instances_bond_kr.ttl` | `http://mafest.ai/graph/abox/bond_kr` | `enriched.product_master` | `fp:Bond` 상품 |
| `instances_etf_kr.ttl` | `http://mafest.ai/graph/abox/etf_kr` | 상품·`relations.product_classification` | `fp:KoreanETF`, `fp:KoreanETN`, 분류 |
| `instances_etf_gl.ttl` | `http://mafest.ai/graph/abox/etf_gl` | 상품·`relations.product_classification` | `fp:GlobalETF`, `fp:GlobalETN`, 분류 |
| `instances_fund_pub.ttl` | `http://mafest.ai/graph/abox/fund_pub` | 상품·`relations.product_classification` | `fp:PublicFund`, 분류 |
| `instances_company.ttl` | `http://mafest.ai/graph/abox/company` | 문서·편입·자회사·상품문서 관계 | 기업, 증권, 문서, n-ary 관계 |

사모펀드는 RDB에 보존하지만 현재 ABox 상품 클래스에는 올리지 않습니다. 미확보 관계는 triple 부재를 비보유로 해석하지 않고 `meta.product_coverage`에서 상태를 확인합니다.

## RDB → ABox 상품 매핑

| `product_type` | RDF 클래스 | ABox 파일 | URI 규칙 |
|---|---|---|---|
| `BOND` | `fp:Bond` | `instances_bond_kr.ttl` | `fpi:{product_id}` |
| `ETF_KR` | `fp:KoreanETF` | `instances_etf_kr.ttl` | `fpi:{product_id}` |
| `ETN_KR` | `fp:KoreanETN` | `instances_etf_kr.ttl` | `fpi:{product_id}` |
| `ETF_GL` | `fp:GlobalETF` | `instances_etf_gl.ttl` | `fpi:{product_id}` |
| `ETN_GL` | `fp:GlobalETN` | `instances_etf_gl.ttl` | `fpi:{product_id}` |
| `FUND_PUB` | `fp:PublicFund` | `instances_fund_pub.ttl` | `fpi:{product_id}` |

## 관계와 분류 매핑

| RDB 원천/유형 | RDF 구조 | 대상 클래스 | provenance |
|---|---|---|---|
| `product_classification.theme` | `fp:relatedToTheme` | `fp:Theme` | 선택적 `fp:hasDocument` |
| `product_classification.sector` | `fp:hasSector` | `fp:Sector` | 선택적 `fp:hasDocument` |
| `product_classification.region` | `fp:hasInvestmentRegion` | `fp:InvestmentRegion` | 선택적 `fp:hasDocument` |
| `product_classification.asset_type` | `fp:hasAssetType` | `fp:AssetType` | 선택적 `fp:hasDocument` |
| `product_holding` | 상품 → `fp:hasHolding` → `fp:Holding` → `fp:holdingSecurity` → 증권 | `fp:Holding` | `fp:weight`, `fp:asOf`, `fp:supportedBy`, `fp:sourceId` |
| `company_subsidiary` | 모기업 → `fp:hasSubsidiary` → `fp:SubsidiaryRelation` → `fp:subsidiaryCompany` → 자회사 | `fp:SubsidiaryRelation` | `fp:ownershipPct`, `fp:asOf`, `fp:supportedBy`, `fp:sourceId` |
| `product_document` | 상품 → `fp:hasDocument` → 문서 | `fp:Document` | 문서명·발행기관·발행일·URL |

## URI 안정성 규칙

- 상품: `fpi:{product_id}`
- 분류: `fpi:classification:{classification_type}:{classification_value}`
- 증권/기업: `fpi:security:{security_id}`
- 문서: `fpi:document:{document_id}`
- 편입관계: `fpi:holding:{holding_id}`
- 자회사관계: `fpi:subsidiary:{relation_id}`
- URI 구성요소는 UTF-8 percent encoding하며 입력 정렬과 triple 정렬로 같은 입력에서 byte-for-byte 같은 TTL을 생성합니다.

## 클래스 정의

| 클래스 | 라벨 | 상위 클래스 | disjointWith | 설명 | 원천 TTL |
|---|---|---|---|---|---|
| `fp:AssetManager` | 운용사 | fp:Organization | - | ETF·펀드의 집합투자업자(ETN은 발행 증권사). fp:managedBy의 range다. 국내ETF는 문자열(97종, 오염 55건), 공모펀드는 기관코드(or_co_xtn_itt_cd 67종)라 코드↔사명 매핑표가 있어야 레이블을 붙일 수 있다. | common.ttl |
| `fp:AssetType` | 투자자산군 | - | - | 주식·채권·원자재 등 자산군 개체. 도메인별 값 체계가 다르므로 공식 이름이 검증된 대응만 통합하고 원본 표기는 skos:altLabel로 보존한다. | common.ttl |
| `fp:Bond` | 채권 | fp:Product, fp:Security | - | 국내채권(PRBD01N001) 종목. 상품이자 편입 대상 증권이므로 fp:Product와 fp:Security를 동시에 상속한다. fp:issuedBy의 유일한 domain이다. | common.ttl |
| `fp:BondIssuerType` | 채권 발행주체 유형 | - | - | 주최측 axis_issuerType. 원본 STD_PD_MCLS_NM(회사채·특수채·국공채 등 6종)에서 재현 가능하다. | bond_kr.ttl |
| `fp:Brand` | ETF 브랜드 | - | - | KODEX·TIGER·RISE·ACE·PLUS·SOL·KIWOOM 등 상품 브랜드. 'TIGER ETF' 같은 자연어 질의의 대응축이며 pd_abrv_nm의 선두 토큰이 유일 소재다. ETF는 영문 브랜드, ETN은 한글 증권사명으로 배타적으로 갈린다. | etf_kr.ttl |
| `fp:ClassDifferentiation` | 클래스 구분 | - | - | 주최측 axis_classDifferentiation(단일클래스/멀티클래스). 공식 fp:managerItemCode가 유효한 경우 그룹 원소 수로 재현한다. | fund_pub.ttl |
| `fp:CollateralType` | 담보 유형 | - | - | 주최측 axis_collateralType. 공식 이름 컬럼에 담보·보증 의미가 명시되지 않으면 내부 코드나 후순위·유동화 표기만으로 추정하지 않으며, 근거 부족 시 답변 불가로 처리한다. | bond_kr.ttl |
| `fp:Company` | 기업 | fp:Organization | - | 일반 사업회사. 편입증권의 발행 주체이며 자회사·산업·테마 탐색의 허브다. 인스턴스는 DART corpCode 마스터(data/enriched/company_master.csv)로 식별하며, 채권 발행사·자회사 관계·편입증권 발행사로 참조되는 기업만 생성한다. | common.ttl |
| `fp:CorporateBond` | 회사채 | fp:Bond | - | 일반 기업·금융회사 발행 채권. 신용평가 대상의 등급 결측은 fp:RatingUnknown으로 표시하며 임의 등급을 채우지 않는다. axis 개체 fp:IssuerType_Corporate에 대응한다. | bond_kr.ttl |
| `fp:CouponType` | 이표 유형 | - | - | 주최측 axis_couponType. SRFC_IRT=0(무이표)과 BD_KND의 전환·변동금리 표기로 대부분 재현 가능하다. | bond_kr.ttl |
| `fp:CreditRating` | 신용등급 | - | - | AAA~C 19단계 신용등급 **개체**. fp:ratingRank(1=AAA … 19=C)로 서열을 준다. 용법 두 가지: ① 'AA- 이상' 조건검색은 fp:ratingRank <= 4 비교로 처리한다(문자열 사전순 비교 금지). ② 'AAAA 등급' 같은 질의는 해당 **개체가 부재**하므로 ABSTAIN_INVALID_TAXONOMY로 판정한다. rank 체계는 data/enriched/bond_kr_enriched.csv의 crd_grd_rank와 동일하다. **개체 부재(AAAA)와 미평가 상태(fp:UnratedByDesign)는 전혀 다르다** — 전자는 허용 분류체계에 없는 값이라 질의 자체가 성립하지 않고(ABSTAIN), 후자는 유효한 상태값이라 '미평가(국채)'로 표기해 답변한다. 등급 조건 질의에서 국채는 등급 필터에서 제외하되 결과 표기에는 '미평가'로 남긴다. | common.ttl |
| `fp:Currency` | 통화 | - | - | 표시·거래 통화 개체(ISO 4217). 채권 CURR_CD, 펀드 curr_cd, 해외ETF pd_trd_ccy의 공통 range다. | common.ttl |
| `fp:Custodian` | 수탁회사 | fp:Organization | - | 펀드 재산을 보관·관리하는 신탁업자(trusc_xtn_itt_cd 18종, 시중은행 중심). 코드↔사명 매핑표 미확보 상태다. | common.ttl |
| `fp:DistributionType` | 분배 유형 | - | - | 주최측 axis_distributionType(분배형/TR형). **배당 관련 3컬럼이 전량 무효**라 원본에서 재현 불가하며, 상품명의 'TR' 토큰 파싱으로만 부분 추정된다. 추정값은 근거가 약하므로 답변 시 추정임을 명시한다. | etf_kr.ttl |
| `fp:Document` | 근거문서 | - | - | 공시·투자설명서·운용보고서·정책자료 등 관계와 주장을 지지하는 문서. fp:supportedBy의 range다. 문서명·발행기관·발행일·근거 문장이 답변 근거 계약의 필수 항목이다. | common.ttl |
| `fp:ETF` | 상장지수펀드 | fp:Product, fp:Security | fp:Bond | 거래소 상장 지수연동 펀드. 2026-07-11 정본의 국내 1,202종·해외 5,587종이 이 클래스다. 국내/해외는 fp:KoreanETF·fp:GlobalETF로 분리하며 편입종목 개념이 있으므로 fp:hasHolding의 domain에 포함된다. | common.ttl |
| `fp:ETN` | 상장지수증권 | fp:Product, fp:Security | fp:Bond, fp:ETF | 발행 증권사의 채무증권. 2026-07-11 정본의 국내 532종·해외 59종이 ETF와 한 파일에 혼재하므로 pd_grp_no로 분리한다. **편입종목·NAV·총보수 개념이 없어 fp:hasHolding의 domain에서 제외**하며 fp:ETF와 서로소다. | common.ttl |
| `fp:FundType` | 펀드 유형 | - | - | 주최측 axis_fundType(증권·MMF·혼합자산·부동산·특별자산). 공식 or_attr_desc 이름을 사용하며 이름 없이 남은 내부 코드는 의미를 추정하거나 필터에 사용하지 않는다. | fund_pub.ttl |
| `fp:GlobalETF` | 해외 ETF | fp:ETF | - |  | common.ttl |
| `fp:GlobalETN` | 해외 ETN | fp:ETN | - |  | common.ttl |
| `fp:GovernmentBond` | 국공채 | fp:Bond | - | 국채·지방채·통안채 등 정부·중앙은행 발행 채권. 공식 분류와 CRD_GRD 결측이 함께 확인되면 fp:UnratedByDesign으로 처리하고 등급 서열 필터에서는 제외하되 결과에 '미평가'로 표시한다. axis 개체 fp:IssuerType_Government에 대응한다. | bond_kr.ttl |
| `fp:Holding` | 편입관계 | - | - | 상품이 특정 증권을 편입한 사실을 나타내는 **n-ary 중간 노드**. 편입비중(fp:weight)·편입기준일(fp:asOf)·근거문서(fp:supportedBy)가 검증된 관계만 생성한다. 미수집은 '비보유'가 아니라 meta.product_coverage의 '편입내역 미확보'다. | common.ttl |
| `fp:Index` | 지수 | - | - | ETF의 기초지수 또는 펀드의 벤치마크. 지수명 표기가 도메인마다 달라(국내ETF cu_base_index와 펀드 bmrk_nm의 교집합 17종뿐) 별칭은 skos:altLabel로 묶는다. 펀드 벤치마크(391종)에는 'MSCI ACWI CR 50% + 종합채권01Y 50%' 같은 복합 벤치마크가 있어 지수 노드 다대다 연결이 필요하다. | common.ttl |
| `fp:Industry` | 산업 | - | - | 기업이 속한 산업 분류. fp:belongsToIndustry의 range. 현재 데이터에 산업 분류축이 없어 인스턴스는 외부 수집 대상이다. | common.ttl |
| `fp:InvestmentRegion` | 투자지역 | - | - | 투자 대상 지역 개체. 국내ETF·해외ETF·펀드의 공식 지역 이름을 보존하며, 국가→상위지역 대응은 검증된 매핑이 있을 때만 추가한다. | common.ttl |
| `fp:InvestorEligibility` | 투자자 자격 | - | - | 주최측 axis_investorEligibility(공모/사모). 원본 prvo_pbff_desc의 공식 이름을 그대로 사용하며 사모는 fp:PublicFund ABox에서 제외하고 RDB에는 보존한다. | fund_pub.ttl |
| `fp:IssuanceMarket` | 발행시장 | - | - | 주최측 axis_issuanceMarket. 공식 국가 이름 대응이 없는 PD_CTRY_CD 원문 코드만으로 시장 의미를 추정하지 않는다. | bond_kr.ttl |
| `fp:IssuanceType` | 설정 유형 | - | - | 주최측 axis_issuanceType(추가형/단위형). fd_set_pcd의 공식 이름 대응이 없어 코드 의미를 추정하지 않으며, 검증된 코드표를 확보하기 전에는 값을 부여하지 않는다. | fund_pub.ttl |
| `fp:Issuer` | 발행기관 | fp:Organization | - | 채권 발행 주체(PRBD01N001.PD_PBCM). fp:issuedBy의 range이며 법인격·음차 표기가 다를 수 있으므로 검증된 식별자나 정규화 사전 없이 기업을 병합하지 않는다. | common.ttl |
| `fp:IssuerCategory` | 발행사 업종 구분 | - | - | 주최측 axis_issuerCategory(금융/비금융/국가/지방/공기업). **현재 데이터로 값을 채울 수 없다** — 발행사명(PD_PBCM) 문자열만 있고 업종 분류 컬럼이 없다. 값 부여에는 DART 기업개황 등 외부 기업 마스터가 필요하다. 클래스·속성은 선언해 두되 인스턴스에 값을 넣지 않는다. | bond_kr.ttl |
| `fp:KoreanETF` | 국내 ETF | fp:ETF | - |  | common.ttl |
| `fp:KoreanETN` | 국내 ETN | fp:ETN | - |  | common.ttl |
| `fp:LeverageType` | 레버리지 유형 | - | - | 주최측 axis_leverageType. 원본 cu_lev_fector(배수, 음수=인버스)에서 완전히 재현된다. 레버리지·인버스 질의의 유일한 정형축이다. | etf_kr.ttl |
| `fp:ListingType` | 상장 구분 | - | - | 주최측 axis_listingType(상장/비상장). 직접 공식 컬럼이 없으므로 검증된 외부 근거가 없으면 값을 생성하거나 비상장으로 추정하지 않는다. | fund_pub.ttl |
| `fp:ManagementStrategy` | 운용전략 | - | - | 주최측 axis_strategy(패시브/액티브). 원본 cu_strtegy 한 컬럼이 이 축과 복제방식(fp:ReplicationMethod) 두 축을 동시에 공급한다 — '액티브'는 Active, '실물복제'·'합성복제'는 Passive로 매핑한다. **'C' 409건은 전부 ETN**(ETN에 ETF 전략코드 미적용)이라 ETF 필터 후 자동 소거된다. | etf_kr.ttl |
| `fp:MaturityClass` | 만기 구분 | - | - | 주최측 axis_maturityClass. fp:remainingDays(파생)에서 재현 가능하다. | bond_kr.ttl |
| `fp:MetricSnapshot` | 수치 스냅샷 | - | - | 특정 시점의 가변 수치(NAV·AUM·수익률·가격) 1건. 도메인·상품·지표별 기준일이 다를 수 있어 값과 기준일을 한 노드로 묶는다. 시점 불변 속성은 상품 노드에 직접 붙이고 가변 수치만 이 클래스로 뺀다. | common.ttl |
| `fp:MunicipalBond` | 지방채 | fp:GovernmentBond | - | 지방자치단체 발행 채권(공모지방채·지역개발 계열). 국공채의 하위이므로 등급 미평가가 정상인 범위에 포함된다. axis 개체 fp:IssuerType_Municipal에 대응한다. | bond_kr.ttl |
| `fp:Organization` | 기관 | - | - | 법인·기관의 상위 클래스. 발행사·운용사·수탁사·일반 기업이 하위다. 원본은 기관명 문자열이라 법인격 표기 흔들림(한국투자/한국투자증권(주), BlackRock Fund Advisors/LP)이 있어 skos:altLabel로 별칭을 흡수한다. | common.ttl |
| `fp:Product` | 금융상품 | - | - | 판매·거래 가능한 금융상품의 최상위 클래스. 채권·ETF·ETN·공모펀드가 모두 이 클래스의 하위다. 상품번호(fp:productCode)로 식별한다. | common.ttl |
| `fp:PublicFund` | 공모펀드 | fp:Product | fp:Bond, fp:ETF, fp:ETN | 국내 공모펀드 종목(PRFD01N001 itm_no 단위 11,115종). **공모 한정 클래스다** — 95,619개 클래스 속성 행을 (itm_no, prfd_attr_cd) 그레인으로 보존하고 사모 15종은 RDB enriched.fund에 보존하되 이 클래스의 ABox에서는 제외한다. | common.ttl |
| `fp:RatingBand` | 신용등급 대역 | - | - | 주최측 axis_creditRating(AAAGrade·AAGrade·AGrade·NotRated). fp:CreditRating 19단계를 묶은 **거친 대역**이다. 'AA- 이상' 질의는 이 대역만으로 처리하면 안 되고 반드시 fp:ratingRank 서열로 판정해야 한다(AAGrade에는 AA+·AA·AA-가 섞여 있다). | bond_kr.ttl |
| `fp:RatingStatus` | 신용등급 상태 | - | - | 신용등급이 **없는 이유**를 구분하는 상태 개체. 등급 개체(fp:CreditRating)가 아니므로 fp:ratingRank를 부여하지 않으며 서열 비교에 끼어들지 않는다. 공식 상품분류로 평가 대상 아님이 명시된 경우와 단순 결측을 구분한다. | common.ttl |
| `fp:RedemptionType` | 환매 유형 | - | - | 주최측 axis_redemptionType(개방형/폐쇄형). **현재 데이터로 값을 채울 수 없다** — 환매 가능 여부를 나타내는 컬럼이 없다. fd_set_pcd(3값)는 코드 의미가 미확정이라 대용할 수 없다. 클래스·속성은 선언하되 값을 부여하지 않는다. | fund_pub.ttl |
| `fp:ReplicationMethod` | 복제방식 | - | - | 지수 복제 방식 개체. 국내ETF cu_strtegy(실물복제/합성복제/액티브)와 해외ETF cu_index_repl_mthd(Full/Optimized/Swap/Other)를 통합한다. Swap=합성복제 대응. | common.ttl |
| `fp:Risk` | 위험요인 | - | - | 상품·기업·산업에 결부된 위험요인. 반드시 fp:supportedBy로 cutoff가 검증된 근거 문서를 동반해야 하며, 미확보 상태는 meta.product_coverage에 남기고 근거 없는 위험 주장은 생성하지 않는다. | common.ttl |
| `fp:RiskGrade` | 투자위험등급 | - | - | 1(최고위험)~6(최저위험) 공통 위험등급 개체. 채권 PD_RISK_GCD, 국내ETF pd_risk_cd(PD_RISK_GCD_1x 접두 제거), 공모펀드 zrin_fd_ivst_risk_gcd(제로인)는 **명칭 체계는 다르나 코드 서열이 모두 '1=최고위험'으로 일치**하므로 단일 개체 6개로 통합한다. | common.ttl |
| `fp:Sector` | 섹터 | - | - |  | common.ttl |
| `fp:Security` | 증권 | - | - | ETF·펀드가 편입할 수 있는 증권(주식·채권 등). fp:Holding의 대상이며, fp:issuedByCompany로 발행 기업에 연결된다. 인스턴스는 data/relations/etf_holding.csv(국내ETF 4사 편입종목)에서 생성한다. 해외ETF·펀드 편입분은 미확보(N-PORT·운용보고서 수집 대상). | common.ttl |
| `fp:ShareClass` | 펀드 클래스 | fp:PublicFund | - | 동일 모(母)펀드의 판매보수 체계별 종류(A/C/C-P/C-Pe/F 등). 클래스도 개별 itm_no로 판매되는 상품이므로 fp:PublicFund의 하위다. 모펀드 연결은 공식 mtco_itm_no가 유효한 경우에만 사용한다. | common.ttl |
| `fp:SpecialBond` | 특수채 | fp:Bond | - | 특별법에 따라 설립된 법인이 발행하는 채권. 신용평가 대상의 등급 결측은 fp:RatingUnknown으로 표시하며 임의 등급을 채우지 않는다. axis 개체 fp:IssuerType_Special에 대응한다. | bond_kr.ttl |
| `fp:SubsidiaryRelation` | 출자관계 | - | - | 기업이 타법인에 출자한 사실을 나타내는 **n-ary 중간 노드**. 지분율(fp:ownershipPct)·공시 기준일(fp:asOf)·출처(fp:sourceId)·근거문서를 동반해야 하므로 모회사→자회사 단순 관계로 표현하지 않는다. 식별자가 검증되지 않은 동명이인은 임의로 연결하지 않는다. | common.ttl |
| `fp:Theme` | 테마 | - | - | 투자 테마(반도체·AI·방산 등). 상품·기업이 fp:relatedToTheme로 연결된다. 외부 근거의 기준일·출처 문서가 검증된 관계만 ABox에 생성하며 미수집 상품은 coverage unavailable로 남긴다. | common.ttl |
| `fp:TradingMarket` | 유통시장 구분 | - | - | 장내(거래소)·장외(장외중개) 유통 구분. 공식 PD_EXG_MKT 이름을 원문 그대로 사용한다. | bond_kr.ttl |
| `fp:UnderlyingScope` | 기초자산 범위 | - | - | 주최측 axis_underlyingScope(시장대표/섹터·테마/개별종목). 공식 기초지수·섹터 이름 또는 cutoff가 검증된 외부 근거가 없으면 값을 생성하지 않으며 테마 관계만으로 범위를 추정하지 않는다. | etf_kr.ttl |

## ObjectProperty 정의

| 속성 | 라벨 | domain | range | 설명 | 원천 TTL |
|---|---|---|---|---|---|
| `fp:belongsToIndustry` | 산업 소속 | fp:Company | fp:Industry | 기업 → 산업 분류. 현재 산업 분류축 데이터가 없다. | common.ttl |
| `fp:hasAssetType` | 투자자산군 | fp:Product | fp:AssetType | 상품 → 자산군 개체. 국내ETF wu_inv_ast_type(한글 8종)·해외ETF wu_inv_ast_type(영문 6종)·공모펀드 or_attr_desc를 통합 개체로 매핑한다. | common.ttl |
| `fp:hasBondIssuerType` | 발행주체 유형 | fp:Bond | fp:BondIssuerType | 채권 → 발행주체 유형 개체. STD_PD_MCLS_NM 6종을 4개 축 개체로 매핑한다(외화채권-회사채·외화채권-금융채는 회사채로 접는다). | bond_kr.ttl |
| `fp:hasBrand` | 브랜드 | (fp:ETF ∪ fp:ETN) | fp:Brand | 상품 → 브랜드 개체. pd_abrv_nm 선두 토큰에서 파생하며, 운용사 문자열 오염 55건(운용사 자리에 상품 전체 명칭이 들어간 행)을 교차검증·복구하는 수단이기도 하다. | etf_kr.ttl |
| `fp:hasClassDifferentiation` | 클래스 구분 | fp:PublicFund | fp:ClassDifferentiation | 펀드 → 단일/멀티클래스 개체. mtco_itm_no 그룹 크기에서 파생한다. | fund_pub.ttl |
| `fp:hasCollateralType` | 담보 유형 | fp:Bond | fp:CollateralType | 채권 → 담보 유형 개체. **현재 데이터에 담보·보증 분류축이 없어 대부분의 종목에 값을 넣을 수 없다.** 담보·보증 조건검색은 답변 불가로 처리한다. | bond_kr.ttl |
| `fp:hasCouponType` | 이표 유형 | fp:Bond | fp:CouponType | 채권 → 이표 유형 개체. SRFC_IRT=0은 결측이 아니라 무이표(할인채)를 뜻한다. | bond_kr.ttl |
| `fp:hasCreditRating` | 신용등급 보유 | (fp:Bond ∪ fp:Issuer) | fp:CreditRating | 채권·발행사 → 신용등급 개체. 'AA- 이상' 조건은 연결된 개체의 fp:ratingRank <= 4로 판정하며 등급 미부여와 단순 결측은 fp:ratingStatus로 구분한다. | common.ttl |
| `fp:hasCurrency` | 표시통화 | fp:Product | fp:Currency | 상품 → 통화 개체. 원천 통화 코드를 그대로 연결하며 서로 다른 통화의 AUM·가격은 환산 근거 없이 합산하거나 비교하지 않는다. | common.ttl |
| `fp:hasCustodian` | 수탁회사 | fp:PublicFund | fp:Custodian | 공모펀드 → 수탁(신탁)회사. 기관코드 18종이며 코드↔사명 매핑표 미확보 상태다. | common.ttl |
| `fp:hasDistributionType` | 분배 유형 | fp:ETF | fp:DistributionType | ETF → 분배 유형 개체. **배당 컬럼 전량 무효**라 상품명 'TR' 토큰 추정 외에는 근거가 없다. '월배당 ETF' 질의는 답변 불가다. | etf_kr.ttl |
| `fp:hasDocument` | 상품 근거문서 | fp:Product | fp:Document |  | common.ttl |
| `fp:hasFundType` | 펀드 유형 | fp:PublicFund | fp:FundType | 펀드 → 유형 개체. or_attr_desc 11종을 매핑하며 '06'은 파생형으로 해석한다. | fund_pub.ttl |
| `fp:hasHolding` | 편입관계 보유 | (fp:ETF ∪ fp:PublicFund) | fp:Holding | 상품 → 편입관계 노드(n-ary). 편입비중·기준일·근거문서를 달아야 하므로 상품→증권 직결 관계를 쓰지 않는다. **fp:ETN은 편입종목 개념이 없어 domain에서 제외**한다. 외부 근거가 없으면 관계를 만들지 않고 coverage에 미확보 사유를 남긴다. | common.ttl |
| `fp:hasInvestmentRegion` | 투자지역 | fp:Product | fp:InvestmentRegion | 상품 → 투자지역 개체. 해외ETF는 59종 국가 단위라 국가→지역 상위 매핑이 필요하다. | common.ttl |
| `fp:hasInvestorEligibility` | 투자자 자격 | fp:PublicFund | fp:InvestorEligibility | 펀드 → 공모/사모 개체. 사모는 fp:PublicFund ABox에서 배제하되 RDB의 offering_type에 원문과 판정 근거를 남긴다. | fund_pub.ttl |
| `fp:hasIssuanceMarket` | 발행시장 | fp:Bond | fp:IssuanceMarket | 채권 → 발행시장 개체. PD_CTRY_CD의 공식 이름 대응이 검증된 경우에만 연결한다. | bond_kr.ttl |
| `fp:hasIssuanceType` | 설정 유형 | fp:PublicFund | fp:IssuanceType | 펀드 → 설정 유형 개체. **현재 데이터로 값을 채울 수 없다**(fd_set_pcd 코드 의미 미확정, KOFIA 코드표 필요). | fund_pub.ttl |
| `fp:hasIssuerCategory` | 발행사 업종 구분 | fp:Issuer | fp:IssuerCategory | 발행사 → 업종 구분 개체. **현재 데이터로 값을 채울 수 없다**(발행사명 문자열만 존재). 외부 기업 마스터 수집 전까지 인스턴스에 값을 부여하지 않는다. | bond_kr.ttl |
| `fp:hasLeverageType` | 레버리지 유형 | (fp:ETF ∪ fp:ETN) | fp:LeverageType | 상품 → 레버리지 유형 개체. cu_lev_fector 배수값(1/2/-2/-1/3/-3/-0.5/1.5/-1.5)에서 매핑한다. | etf_kr.ttl |
| `fp:hasListingType` | 상장 구분 | fp:PublicFund | fp:ListingType | 펀드 → 상장 구분 개체. 공식 문서나 검증된 외부 근거가 있을 때만 생성하며 미확보를 비상장으로 바꾸지 않는다. | fund_pub.ttl |
| `fp:hasManagementStrategy` | 운용전략 | (fp:ETF ∪ fp:PublicFund) | fp:ManagementStrategy | 상품 → 패시브/액티브 개체. 공식 이름 컬럼이나 검증된 문서가 있을 때만 연결하며 복제방식 결측으로 액티브 여부를 추정하지 않는다. | etf_kr.ttl |
| `fp:hasMaturityClass` | 만기 구분 | fp:Bond | fp:MaturityClass | 채권 → 만기 구분 개체. 실제 기준일과 만기일로 계산한 fp:maturityBucket에서 매핑하며 만기경과를 별도 상태로 유지한다. | bond_kr.ttl |
| `fp:hasMetricSnapshot` | 수치 스냅샷 보유 | fp:Product | fp:MetricSnapshot | 상품 → 시점 가변 수치 노드. 기준일이 다른 수치를 한 답변에 섞을 때 각각의 fp:asOf를 함께 제시하기 위한 경로다. | common.ttl |
| `fp:hasRatingBand` | 신용등급 대역 | fp:Bond | fp:RatingBand | 채권 → 등급 대역 개체(주최측 axis). 조건검색은 이 대역이 아니라 fp:hasCreditRating + fp:ratingRank로 판정한다. | bond_kr.ttl |
| `fp:hasRedemptionType` | 환매 유형 | fp:PublicFund | fp:RedemptionType | 펀드 → 환매 유형 개체. **현재 데이터로 값을 채울 수 없다.** 개방형·폐쇄형 조건검색은 근거 부족으로 답변 불가다. | fund_pub.ttl |
| `fp:hasReplicationMethod` | 복제방식 | (fp:ETF ∪ fp:PublicFund) | fp:ReplicationMethod | 상품 → 복제방식 개체. ETF/ETN을 먼저 공식 상품유형으로 분리하고 공식 복제방식 이름이 있는 경우만 연결하며 결측을 액티브·비추종으로 추정하지 않는다. | common.ttl |
| `fp:hasRisk` | 위험요인 보유 | (fp:Product ∪ fp:Company ∪ fp:Industry) | fp:Risk | 상품·기업·산업 → 위험요인. 반드시 fp:supportedBy 근거 문서를 동반해야 한다. | common.ttl |
| `fp:hasRiskGrade` | 투자위험등급 | fp:Product | fp:RiskGrade | 상품 → 위험등급 개체(1~6). 채권·국내ETF·공모펀드 세 도메인이 같은 서열이라 교차 비교가 가능하다. 해외ETF에는 위험등급 컬럼이 없다. | common.ttl |
| `fp:hasSector` | 투자 섹터 | fp:Product | fp:Sector |  | common.ttl |
| `fp:hasShareClass` | 클래스 보유 | fp:PublicFund | fp:ShareClass | 대표(모)펀드 → 종류별 클래스. 최신 원본은 itm_no 1행 그레인이므로 상품 수를 별도 dedup하지 않는다. 그룹핑은 공식 fp:managerItemCode(mtco_itm_no)가 유효한 경우에만 수행한다. | common.ttl |
| `fp:hasSubsidiary` | 출자관계 보유 | fp:Company | fp:SubsidiaryRelation | 모회사 → 출자관계 노드(n-ary). 지분율 기준이 관계마다 다르므로 전이성(owl:TransitiveProperty)은 선언하지 않는다. 손자회사 탐색은 다단계 질의로 처리한다. | common.ttl |
| `fp:hasTradingMarket` | 유통시장 구분 | fp:Bond | fp:TradingMarket | 채권 → 장내·장외 개체. 원본 PD_EXG_MKT를 그대로 매핑한다. | bond_kr.ttl |
| `fp:hasUnderlyingScope` | 기초자산 범위 | fp:ETF | fp:UnderlyingScope | ETF → 기초자산 범위 개체. 공식 이름 또는 cutoff가 검증된 투자설명서 근거가 있을 때만 부여한다. | etf_kr.ttl |
| `fp:holdingSecurity` | 편입증권 | fp:Holding | fp:Security | 편입관계 노드 → 편입된 증권. fp:hasHolding·fp:weight·fp:asOf와 함께 하나의 편입 사실을 구성한다. | common.ttl |
| `fp:issuedBy` | 발행사 | fp:Bond | fp:Issuer | 채권 → 발행기관. **domain이 fp:Bond로만 한정된다.** 'VOO(ETF)가 직접 발행한 회사채' 같은 질의는 주어가 fp:ETF이고 fp:ETF는 fp:Bond와 owl:disjointWith이므로 도메인 위반이 확정되어 ABSTAIN(엔티티 유형이 관계의 도메인·레인지와 불일치)으로 판정한다. ETF의 발행 주체를 묻는 질의는 fp:managedBy로 유도한다. | common.ttl |
| `fp:issuedByCompany` | 증권 발행기업 | fp:Security | fp:Company | 편입증권 → 발행 기업. ETF→편입증권→기업→자회사→산업/테마 경로의 두 번째 간선이며, 검증된 증권 식별자와 기업 식별자 대응이 있을 때만 생성한다. | common.ttl |
| `fp:managedBy` | 운용사 | (fp:ETF ∪ fp:ETN ∪ fp:PublicFund) | fp:AssetManager | ETF·ETN·펀드 → 운용사(ETN은 발행 증권사). 채권은 운용사 개념이 없으므로 domain에서 제외한다. | common.ttl |
| `fp:ratingStatus` | 신용등급 상태 | (fp:Bond ∪ fp:Issuer) | fp:RatingStatus | 등급이 없을 때 그 이유를 구분한다. 공식 STD_PD_MCLS_NM이 국공채 또는 개인투자용국채이고 CRD_GRD가 결측이면 fp:UnratedByDesign, 그 밖의 결측은 fp:RatingUnknown, 등급이 있으면 fp:Rated다. 등급 조건 질의에서 미평가 종목은 서열 필터에서 제외하되 결과에 '미평가'로 표시하며, 존재하지 않는 등급 문자열에 대한 ABSTAIN_INVALID_TAXONOMY와 혼동하지 않는다. | common.ttl |
| `fp:relatedToTheme` | 테마 연관 | (fp:Product ∪ fp:Company) | fp:Theme | 상품·기업 → 테마. 주최측 분류축 또는 published_at/as_of가 2026-07-11 이하로 검증된 공식 문서만 근거로 쓴다. 상품명에 테마어가 있다는 사실만으로 관계를 확정하지 않는다. | common.ttl |
| `fp:sameVehicleAs` | 동일 상품 | fp:Product | fp:Product | 표기·데이터셋이 달라도 공식 식별자로 동일 운용 실체가 검증된 상품을 잇는 대칭 관계. fp:ETF와 fp:PublicFund는 owl:disjointWith이므로 owl:sameAs로 병합하지 않고 별개 노드를 유지한다. | common.ttl |
| `fp:subsidiaryCompany` | 피출자 기업 | fp:SubsidiaryRelation | fp:Company | 출자관계 노드 → 피출자(자회사) 기업. fp:hasSubsidiary·fp:ownershipPct·fp:asOf와 함께 하나의 출자 사실을 구성한다. | common.ttl |
| `fp:subsidiaryOf` | 자회사 관계 | fp:Company | fp:Company | 자회사 → 모회사 단순 관계. v2 ABox는 지분율·기준일·출처를 보존하기 위해 fp:SubsidiaryRelation n-ary 구조를 사용하며 이 속성으로 직접 인스턴스를 만들지 않는다. | common.ttl |
| `fp:supportedBy` | 근거문서 | (fp:Holding ∪ fp:MetricSnapshot ∪ fp:Risk) | fp:Document | 관계·주장 → 이를 지지하는 문서. 근거가 없는 관계는 답변에 포함하지 않는다. 문서에 함께 언급되었다는 사실만으로 편입·모자회사·테마 관계를 확정하지 않는다. | common.ttl |
| `fp:tracksIndex` | 기초지수 추종 | (fp:ETF ∪ fp:ETN ∪ fp:PublicFund) | fp:Index | ETF·ETN → 기초지수, 펀드 → 벤치마크. 공식 이름이 있는 경우만 연결하고 복합 벤치마크를 분해하려면 구성 근거를 별도로 검증한다. 지수명 별칭은 검증된 표기만 skos:altLabel로 묶는다. | common.ttl |

## DatatypeProperty 정의

| 속성 | 라벨 | domain | range | 공식 원천 | 설명 | 원천 TTL |
|---|---|---|---|---|---|---|
| `fp:agencyRatings` | 평가사 신용등급(원문) | fp:Bond | xsd:string | PRBD01N001.PD_EVCO_CRD_GRD | 여러 평가사 등급을 콤마로 이어 붙인 원문. 단일 등급으로 임의 축약하지 않고 일치 여부를 별도 표기하며, 평가기관명 자체가 없으면 (채권, 평가기관, 등급) 관계를 추정하지 않는다. | bond_kr.ttl |
| `fp:appliedYield` | 적용수익률 | fp:Bond | xsd:decimal | PRBD01N001.APPLIED_YIELD | 평가에 적용된 시장수익률(%). 0/NULL은 값 없음으로 표시하고 비교·랭킹에서 제외한다. | bond_kr.ttl |
| `fp:asOf` | 기준일 | (fp:Holding ∪ fp:MetricSnapshot ∪ fp:SubsidiaryRelation) | xsd:date | derived:relations.derived:relations.as_of | 시점 가변 관계·수치의 기준일. **시점을 모르는 관계는 비워 두고 추정 날짜를 채워 넣지 않는다**(거짓 기준일 방지). etf_theme 관계가 이에 해당한다. | common.ttl |
| `fp:baseAsset` | 기초 자산 | fp:ETF | xsd:string | derived:etf_kr_enriched.derived:etf_kr_enriched.base_asset | 기초자산 종류(LSEG 보강). wu_inv_ast_type과 교차검증용으로 함께 제시한다. | etf_kr.ttl |
| `fp:baseMarket` | 기초 시장 | fp:ETF | xsd:string | derived:etf_kr_enriched.derived:etf_kr_enriched.base_market | 기초자산이 속한 시장(국내·해외 등). 주최측 축이 없을 때만 cutoff가 검증된 외부 근거로 보강한다. | etf_kr.ttl |
| `fp:benchmarkName` | 벤치마크명(원문) | fp:PublicFund | xsd:string | PRFD01N001.bmrk_nm | 비교지수 원문(391종, 결측 0%). **복합 벤치마크('MSCI ACWI CR 50% + 종합채권01Y 50%')가 다수**라 fp:tracksIndex로 지수 노드에 연결할 때는 구성 지수별로 분해해 다중 연결하고 가중치를 보존한다. 국내ETF cu_base_index와의 교집합은 17종뿐이라 별칭 매핑(skos:altLabel)이 필요하며, 영문명(bmrk_eng_nm)은 1:1 대응이라 별도 속성으로 싣지 않고 별칭으로만 흡수한다. | fund_pub.ttl |
| `fp:bondKind` | 채권종류 | fp:Bond | xsd:string | PRBD01N001.BD_KND | 상환구조·발행주체 기준 세분류 39종(일반회사채·할부금융채·유동화회사채·MBS·Conduit회사채 등). 구조화 상품 식별의 유일 축이며 결측 924건이다. | bond_kr.ttl |
| `fp:bondMajorClass` | 표준상품 대분류 | fp:Bond | xsd:string | PRBD01N001.STD_PD_MCLS_NM | 공식 채권 1차 분류 이름. 내부 코드 의미를 추정하지 않고 fp:bondMinorClass의 상위 계층으로 사용한다. | bond_kr.ttl |
| `fp:bondMinorClass` | 표준상품 소분류 | fp:Bond | xsd:string | PRBD01N001.STD_PD_SCLS_NM | 대분류 하위 2차 분류 16종(일반사채·공사채·특수은행채·국고채 등). 대분류와 계층 관계를 이룬다. | bond_kr.ttl |
| `fp:brandName` | 브랜드명 | fp:Brand | xsd:string | derived:etf_kr_brand.derived:etf_kr_brand.brand | 브랜드 개체의 명칭. pd_abrv_nm 선두 토큰에서 파생한다. | etf_kr.ttl |
| `fp:buyYield` | 매수수익률 | fp:Bond | xsd:decimal | PRBD01N001.BUY_YIELD | 채권 offer의 매수 기준 수익률(%). 0/NULL은 값 없음으로 비교·랭킹에서 제외하고 출처 컬럼과 기준일을 함께 제시한다. | bond_kr.ttl |
| `fp:buyableQuantity` | 매수가능수량 | fp:Bond | xsd:decimal | PRBD01N001.BUYABLE_QUANTITY | 원천 BUYABLE_QUANTITY의 저장 전용 값. 0과 NULL을 원본 그대로 보존하지만 **구매가능·판매가능 판정, 필터, 정렬 또는 실행계획에 사용하지 않는다**. | bond_kr.ttl |
| `fp:cikCode` | SEC CIK 코드 | (fp:ETF ∪ fp:ETN) | xsd:string | PREF02N001.pd_us_cik | SEC EDGAR 등록번호. N-PORT 구성종목 취득 경로지만 트러스트 단위 코드라 이것만으로 개별 ETF를 특정하지 않고 Series ID 등 공식 식별자를 함께 검증한다. | etf_gl.ttl |
| `fp:closePriceBaseDate` | 종가 기준일 | (fp:ETF ∪ fp:ETN) | xsd:date | PREF02N001.du_clpr_base_dt | 종가 기준일. 86종으로 분산되어 stale 종목이 섞여 있으므로 '현재 가격' 질의에서 이 값을 반드시 함께 제시한다. | etf_gl.ttl |
| `fp:coreProduct` | 핵심상품 선정 여부 | fp:ETF | xsd:boolean | PREF01N001.wu_core_yn | 당사 선정 핵심 ETF(Y 88건, 전부 ETF). '추천 ETF' 질의의 유일한 내부 근거다. 해외ETF는 Y가 0건이라 같은 필터를 적용할 수 없다. | etf_kr.ttl |
| `fp:corpCode` | DART 고유번호 | fp:Organization | xsd:string | derived:company_master.derived:company_master.corp_code | 금융감독원 DART 기업 고유번호 8자리. 기업 URI와 공시 근거 문서를 연결하는 키다. 고유번호를 특정하지 못한 이름은 동명이인 가능성이 있으므로 임의 기업 URI로 병합하지 않는다. | common.ttl |
| `fp:couponRate` | 표면금리 | fp:Bond | xsd:decimal | PRBD01N001.SRFC_IRT | 액면 대비 연 이표율(%). **0은 결측이 아니라 무이표(할인채)**를 뜻한다. | bond_kr.ttl |
| `fp:creditRatingLabel` | 신용등급 표기 | fp:Bond | xsd:string | PRBD01N001, derived:bond_kr_enriched.CRD_GRD, derived:bond_kr_enriched.crd_grd_norm | 정규화된 대표 신용등급 문자열(AA0→AA, C0→C). 결측은 fp:ratingStatus로 미평가 대상과 데이터 결손을 구분해 답하며 서열 비교는 이 문자열이 아니라 fp:hasCreditRating 개체의 fp:ratingRank로 한다. | bond_kr.ttl |
| `fp:currencyHedged` | 환헤지 여부 | fp:PublicFund | xsd:boolean | PRFD01N001.exchdg_yn | 환헤지 적용 여부. 공식 Y/N 값만 조건축으로 사용하고 결측을 국내투자나 미적용으로 추정하지 않으며 그 밖의 값은 원문 보존 후 필터에서 제외한다. | fund_pub.ttl |
| `fp:delistingDate` | 거래종료일 | (fp:ETF ∪ fp:ETN) | xsd:date | PREF01N001.pd_lste_dt | 상장폐지·만기일. 유효한 날짜만 파싱하고 sentinel은 원문 보존 후 날짜 비교에서 제외한다. ETN의 명시적 종료 판정에 사용한다. | etf_kr.ttl |
| `fp:documentPublishedDate` | 문서 발행일 | fp:Document | xsd:date | derived:document.derived:document.published_date | 근거 문서의 발행일. 2026-07-11 이후 문서는 전체 빌드를 실패시키며 답변 근거로 쓰지 않는다. | common.ttl |
| `fp:documentPublisher` | 발행기관 | fp:Document | xsd:string | derived:document.derived:document.publisher | 근거 문서의 발행기관. | common.ttl |
| `fp:documentQuote` | 근거 문장 | fp:Document | xsd:string | derived:document.derived:document.quote | 관계·주장을 직접 지지하는 인용 문장. | common.ttl |
| `fp:documentTitle` | 문서명 | fp:Document | xsd:string | derived:document.derived:document.title | 근거 문서의 제목. 답변 근거 계약의 필수 항목. | common.ttl |
| `fp:duration` | 듀레이션 | fp:Bond | xsd:decimal | PRBD01N001.DUR | 금리 민감도. 0/NULL은 값 없음으로 표시하고 듀레이션 비교에서 제외한다. 익일 계열과 다른 민감도 지표는 별도 축으로 혼합하지 않는다. | bond_kr.ttl |
| `fp:eligibleInvestorType` | 개인·법인 구분 | fp:PublicFund | xsd:string | PRFD01N001.pers_corp_desc | 공식 가입 대상 투자자 이름. 개인 가입 가능 여부는 명시된 이름이 있을 때만 판정한다. | fund_pub.ttl |
| `fp:exchangeCode` | 상장 거래소 코드 | (fp:ETF ∪ fp:ETN) | xsd:string | PREF02N001.pd_exg_mkt_cd | 거래소 시장 원문 코드. 공식 코드 이름 대응이 없으면 의미를 추정하거나 거래소 필터에 사용하지 않는다. | etf_gl.ttl |
| `fp:expenseRatio` | 총보수요율 | (fp:ETF ∪ fp:PublicFund) | xsd:decimal | PREF01N001, PREF02N001.cu_charge_rt | 연 총보수(%). 국내·해외ETF 주최측 cu_charge_rt 축을 1순위로 쓴다. 0/NULL은 값 없음이며, 주최측에 축 자체가 있는 국내ETF 총보수를 외부 값으로 덮지 않는다. ETN에는 총보수 개념이 없어 domain에서 제외한다. | common.ttl |
| `fp:expenseRatioSource` | 총보수 출처 | fp:ETF | xsd:string | derived:etf_kr_enriched.derived:etf_kr_enriched.charge_rt_source | 총보수 값이 주최측 원본(RDB)인지 외부 보완(LSEG)인지 표시. 답변 evidence에 그대로 인용한다. | common.ttl |
| `fp:fssCode` | 금감원 종목번호 | fp:PublicFund | xsd:string | PRFD01N001.fss_itm_no | 금융감독원 코드(DART 펀드공시 조인키). 공식 sentinel 값은 유효 식별자로 쓰지 않고 결측 상태로 보존한다. | fund_pub.ttl |
| `fp:fundAttributeCode` | 펀드별 속성코드 | fp:PublicFund | xsd:string | PRFD01N001.derived:fund_pub_dedup.prfd_attr_cds, prfd_attr_cd | 원본 복합 PK의 2축(228종). 실체계는 2종 — 영문1+숫자3(210종)과 ISO 3166 3자리 국가코드(17종)다. '해외' 1종은 파싱 붕괴 행의 잔재이므로 체계로 취급하지 않는다. dedup 테이블에서는 prfd_attr_cds로 집약된다. | fund_pub.ttl |
| `fp:hasSaleInfo` | 판매정보 보유 여부 | fp:Bond | xsd:boolean | enriched:bond_kr_offer.applied_yield, buy_yield, trade_price | 판매 관련 offer 측정값 존재 여부. 정보성 coverage일 뿐 구매가능 가정에는 사용하지 않는다. | bond_kr.ttl |
| `fp:hedgeType` | 환헤지 유형 | fp:ETF | xsd:string | derived:etf_kr_enriched.derived:etf_kr_enriched.hedge_type | 환헤지·환노출 구분(LSEG 보강). 원본에는 대응 컬럼이 없어 외부 보완값이며 fp:sourceId로 출처를 함께 표시한다. | etf_kr.ttl |
| `fp:inceptionDate` | 설정일 | (fp:GlobalETF ∪ fp:GlobalETN) | xsd:date | PREF02N001.pd_lstg_dt | 해외 ETF/ETN의 설정일. PREF02 pd_lstg_dt는 공식 정의상 상장일이 아니므로 listingDate로 노출하지 않는다. | etf_gl.ttl |
| `fp:indexName` | 지수명 | fp:Index | xsd:string | PREF01N001, PREF02N001, PRFD01N001.bmrk_nm, cu_base_index | 지수·벤치마크 명칭. 해외ETF cu_base_index의 'Index is not provided by Management Company'·'Index is not available on Lipper Database' 계열 문장은 **값이 아니라 sentinel**이므로 결측으로 처리하고 지수 노드를 만들지 않는다. | common.ttl |
| `fp:indexTrackingUnavailable` | 기초지수 미제공 여부 | fp:ETF | xsd:boolean | PREF02N001.cu_base_index | cu_base_index가 'Index is not provided by Management Company' 또는 'Index is not available on Lipper Database' 계열 sentinel이면 true다. sentinel을 NULL로 처리해 '기초지수 미제공'과 '비추종'을 구분한다. | etf_gl.ttl |
| `fp:internalCode` | 사내 단축코드 | (fp:ETF ∪ fp:ETN) | xsd:string | PREF01N001.pd_itm_no_ma | 미래에셋 사내 코드(A305080·Q760014 형식). 앞 한 글자를 뗀 값이 LSEG 메타 조인키(lseg_key)라 외부 보완 데이터 결합의 실무 키다. | etf_kr.ttl |
| `fp:isInverse` | 인버스·숏 여부 | fp:ETF | xsd:boolean | PREF02N001.cu_inverse_short_yn | 인버스·숏 상품 플래그(Y 171건, 결측=일반형). cu_lev_fector가 전량 결측이라 **해외ETF 인버스 질의의 유일한 정형축**이다. 배수(2X·3X)는 상품명·전략 텍스트 파싱으로만 추정된다. | etf_gl.ttl |
| `fp:isSellable` | 현재 매수 가능 여부 | fp:Bond | xsd:boolean | enriched:bond_kr_product.is_assumed_purchasable, purchasable_rule | v2의 보수적 구매가능 가정. 최신 데이터에 존재하면서 명시적으로 만기·리스팅 종료되지 않은 경우만 true다. BUYABLE_QUANTITY·통화·판매수익률을 판정에 사용하지 않으며 근거 규칙을 함께 반환한다. | bond_kr.ttl |
| `fp:isinCode` | ISIN 코드 | (fp:ETF ∪ fp:ETN) | xsd:string | PREF02N001.pd_isin_cd | 국제증권식별번호. 외부 holdings 조인의 표준키다. **중복 50종이 존재하므로 유일키(owl:InverseFunctionalProperty)로 선언하지 않는다.** 티커 변경 후 구 레코드가 남은 잔재이며, 상품 URI는 반드시 fp:productCode(pd_itm_no)로 구성한다. | etf_gl.ttl |
| `fp:issueDate` | 발행일 | fp:Bond | xsd:date | PRBD01N001.ISU_DT | YYYYMMDD 원본. **sentinel '0' 336건을 결측으로 제외한 뒤 파싱**한다. | bond_kr.ttl |
| `fp:issuedAmount` | 발행잔액 | fp:Bond | xsd:decimal | PRBD01N001.ISU_BAL_AMT | 발행 잔존 원금(원). 규모 필터축. 0 값이 다수 존재하며 상환 완료 잔재일 가능성이 있어 0은 별도 취급한다. | bond_kr.ttl |
| `fp:kofiaClassCode` | 금투협 펀드분류코드 | fp:PublicFund | xsd:string | PRFD01N001.kofia_fd_ccd | 금융투자협회 분류코드. 공식 코드 이름 대응이 없으므로 의미를 추정하거나 분류 필터로 쓰지 않고 원문 식별자로만 보존한다. | fund_pub.ttl |
| `fp:ksdCode` | 예탁원 종목번호 | fp:PublicFund | xsd:string | PRFD01N001.ksd_itm_no | 예탁결제원 코드. 상품 식별과 공식 식별자 교차검증에 사용하며 값이 없거나 중복이면 임의로 동일 상품 관계를 만들지 않는다. | fund_pub.ttl |
| `fp:leverageFactor` | 레버리지 배수 | (fp:ETF ∪ fp:ETN) | xsd:decimal | PREF01N001.cu_lev_fector | 지수 대비 배수. **음수는 인버스**를 뜻한다(-2 = 인버스 2배). 해외ETF는 이 컬럼이 전량 결측이라 국내ETF에서만 정형 필터가 가능하다. | etf_kr.ttl |
| `fp:lipperId` | Lipper 펀드 ID | (fp:ETF ∪ fp:ETN) | xsd:string | PREF02N001.pd_lipper_id | LSEG Lipper 식별자. 외부 펀드 DB 조인키이며 ISIN 중복 50종과 동일 종목군에서 50건 중복한다. 유일키로 쓰지 않는다. | etf_gl.ttl |
| `fp:listingDate` | 상장일 | (fp:ETF ∪ fp:ETN) | xsd:date | PREF01N001.pd_lstg_dt | 거래 가능 개시일. '최근 상장 ETF' 질의축이다. | common.ttl |
| `fp:managerItemCode` | 운용사 종목번호 | fp:PublicFund | xsd:string | PRFD01N001.mtco_itm_no | 클래스 → 모펀드 그룹핑의 공식 키. 내부 코드의 의미를 추측하거나 임의 보정하지 않고 원문을 보존하며 공백·명시 sentinel은 관계 생성에서 제외한다. | fund_pub.ttl |
| `fp:maturityBucket` | 잔존만기 구간 | fp:Bond | xsd:string | derived:bond_kr_enriched.derived:bond_kr_enriched.maturity_bucket | 만기경과 / 1년미만 / 1-3년 / 3-5년 / 5-10년 / 10년이상 / 미상(파생). fp:hasMaturityClass 개체 매핑의 소재다. | bond_kr.ttl |
| `fp:maturityDate` | 만기일 | fp:Bond | xsd:date | PRBD01N001.MAT_DT | 잔존만기 계산의 기준. 유효한 날짜만 파싱하고 sentinel·영구채 표기는 원문 보존 후 별도 상태로 처리한다. 구매가능 가정에는 실제 기준일 대비 명시적 만기 종료만 사용한다. | bond_kr.ttl |
| `fp:metricName` | 수치 항목명 | fp:MetricSnapshot | xsd:string | derived:metric_snapshot.derived:metric_snapshot.metric_name | 스냅샷이 담는 수치의 이름(nav, aum, return_1y 등). | common.ttl |
| `fp:metricUnit` | 수치 단위 | fp:MetricSnapshot | xsd:string | derived:metric_snapshot.derived:metric_snapshot.metric_unit | KRW·USD·percent 등. 도메인 간 순자산 비교 시 단위 변환의 근거다. | common.ttl |
| `fp:metricValue` | 수치 값 | fp:MetricSnapshot | xsd:decimal | derived:metric_snapshot.derived:metric_snapshot.metric_value | 스냅샷 수치의 값. 단위는 fp:metricUnit으로 함께 제시한다. | common.ttl |
| `fp:navBaseDate` | NAV 기준일 | fp:ETF | xsd:date | PREF02N001.du_nav_base_dt | NAV 산출 기준일. 종가 기준일과 같다고 가정하지 않으며 가격과 NAV를 함께 제시할 때 각 원천 기준일을 별도로 표기한다. | etf_gl.ttl |
| `fp:netAssets` | 순자산총액 | fp:Product | xsd:decimal | PREF01N001, PREF02N001, PRFD01N001.du_last_aum, fd_nast_suma, pd_net_tamt | 규모 질의의 표준축. v2 product_metric은 국내·해외ETF du_last_aum, 펀드 fd_nast_suma, 채권 isu_bal_amt를 원천 통화와 기준일로 함께 저장한다. 0/NULL은 비교·랭킹에서 값 없음이며 통화가 다르면 환산 근거 없이 합산하지 않는다. | common.ttl |
| `fp:onSale` | 판매 가능 여부 | fp:Product | xsd:boolean | PREF01N001.pd_sale_yn | 당사 판매 가능 여부. 코드값은 공식 이름 컬럼/설명 없이 의미를 추측하지 않는다. 채권의 v2 구매가능 가정은 최신 정본 존재와 명시 만기·리스팅 종료만 사용하며 BUYABLE_QUANTITY를 사용하지 않는다. | common.ttl |
| `fp:organizationName` | 기관명 | fp:Organization | xsd:string | PRBD01N001, PREF01N001, PREF02N001.PD_PBCM, cu_fund_mgmt_co | 기관 정규 명칭. 원본 문자열은 법인격 표기가 흔들리므로(한국투자/한국투자증권(주), BlackRock Fund Advisors/LP) 정규화 후 값을 넣고 원표기는 skos:altLabel로 남긴다. | common.ttl |
| `fp:overseasScope` | 해외투자 구분 | fp:PublicFund | xsd:string | PRFD01N001.ovrs_fd_desc | 공식 투자 대상 소재 이름. fp:hasInvestmentRegion과 함께 사용하되 결측·내부 코드를 임의 지역으로 매핑하지 않는다. | fund_pub.ttl |
| `fp:ownershipPct` | 지분율 | fp:SubsidiaryRelation | xsd:decimal | derived:company_subsidiary.derived:company_subsidiary.ownership_pct | 기말 지분율(%). 결측은 트리플 자체를 생성하지 않고 0으로 채우지 않는다. 지분율만으로 지배 여부를 단정하지 않으며 답변에는 fp:asOf 공시 기준일을 함께 제시한다. | common.ttl |
| `fp:pensionRiskCategory` | 연금 위험자산 구분 | (fp:ETF ∪ fp:ETN) | xsd:string | PREF01N001.pd_pen_risk_nm | 연금계좌 편입 시 위험자산 한도(70%) 판정 구분(위험자산 788 / 안전자산 214). **'N' 732건은 구분값이 아니라 '연금거래 불가'**이며 fp:pensionTradable=false와 정확히 대응하므로 분류값으로 해석하면 안 된다. | etf_kr.ttl |
| `fp:pensionTradable` | 연금계좌 거래 가능 | (fp:ETF ∪ fp:ETN) | xsd:boolean | PREF01N001.pd_pen_tr_yn | 연금저축·IRP 계좌 매매 가능 여부. 공식 Y/N 값만 조건축으로 사용하고 결측은 가능·불가능으로 추정하지 않는다. | etf_kr.ttl |
| `fp:productCode` | 상품번호 | fp:Product | xsd:string | PRBD01N001, PREF01N001, PREF02N001, PRFD01N001.PD_NO, itm_no, pd_itm_no | 도메인별 정본 식별자. 채권 PD_NO(ISIN형 12자리, 중복 0), 국내ETF pd_itm_no(중복 0), 해외ETF pd_itm_no(로이터 RIC, 중복 0), 공모펀드 itm_no. 상품 URI의 소재다. | common.ttl |
| `fp:productGroup` | 상품군 종류 | (fp:ETF ∪ fp:ETN) | xsd:string | PREF01N001, PREF02N001.pd_grp_no | ETF / ETN 판별의 **유일 신뢰축**. 이 값으로 fp:ETF·fp:ETN 클래스를 확정한 뒤 모든 집계를 수행한다. | etf_kr.ttl |
| `fp:productName` | 상품명 | fp:Product | xsd:string | PRBD01N001, PREF01N001, PREF02N001, PRFD01N001.PD_NM, itm_nm, pd_nm | 정식 명칭. 자연어 질의가 상품을 지목하는 주 통로이므로 **완전일치를 우선**하고 부분일치 유사명으로 대체하지 않는다('KODEX 200' 부분일치 14건, 'KODEX AI로봇' 유사명 18건이 오탐 원인). | common.ttl |
| `fp:productShortName` | 상품약어명 | fp:Product | xsd:string | PREF01N001, PREF02N001, PRFD01N001.itm_abrv_nm, pd_abrv_nm | 축약 명칭. 국내ETF는 선두 토큰이 브랜드(KODEX/TIGER/RISE…), 해외ETF는 미국 티커, 펀드는 클래스 접미를 포함한다. | common.ttl |
| `fp:ratingAgencyCount` | 평가사 등급 개수 | fp:Bond | xsd:integer | derived:bond_kr_enriched.derived:bond_kr_enriched.evco_grd_count | PD_EVCO_CRD_GRD에 담긴 등급 개수(파생). 1개 이하면 일치 판정이 불가능하다. | bond_kr.ttl |
| `fp:ratingAgreement` | 평가사 등급 일치 여부 | fp:Bond | xsd:string | derived:bond_kr_enriched.derived:bond_kr_enriched.evco_grd_agree | 복수 평가사 등급이 모두 같으면 Y, 다르면 N, 판정 불가면 공란(파생). 등급 불일치 286건은 답변 시 함께 표기해야 한다. | bond_kr.ttl |
| `fp:ratingRank` | 신용등급 서열 | fp:CreditRating | xsd:integer | derived:bond_kr_enriched.derived:bond_kr_enriched.crd_grd_rank | 1=AAA(최상) … 19=C(최하). 'AA- 이상'은 fp:ratingRank <= 4로 판정한다. data/enriched/bond_kr_enriched.csv의 crd_grd_rank와 동일 체계이므로 RDB 선필터와 온톨로지 판정 결과가 일치한다. | common.ttl |
| `fp:remainingDays` | 잔존일수 | fp:Bond | xsd:integer | derived:bond_kr_enriched.REMAINING_DAYS, derived:bond_kr_enriched.remaining_days | 기준일 대비 만기까지 일수. '잔존 3년 이내' 질의축이며 3년 = 1,095일로 환산한다. 음수는 만기 경과이므로 구매가능 가정에서 제외하며 평가 cutoff는 2026-07-11이다. | bond_kr.ttl |
| `fp:representativeKsdCode` | 대표 예탁원 종목번호 | fp:PublicFund | xsd:string | PRFD01N001.rptt_ksd_itm_no | 대표(모)펀드 예탁원 코드. 공식 sentinel은 유효 식별자에서 제외하며 그룹핑은 유효한 fp:managerItemCode가 있을 때만 수행한다. | fund_pub.ttl |
| `fp:return18M` | 18개월 수익률 | fp:PublicFund | xsd:decimal | PRFD01N001.fd_mm18_ern_r | 최근 18개월 수익률(%). ETF에는 없는 구간이라 domain을 펀드로 한정한다. | common.ttl |
| `fp:return1M` | 1개월 수익률 | fp:Product | xsd:decimal | PREF01N001, PRFD01N001.du_er_1m, fd_mm1_ern_r | 최근 1개월 수익률(%). 원문 값을 보존하며 0/NULL은 product_metric.is_available=false로 비교·랭킹에서 제외한다. | common.ttl |
| `fp:return1W` | 1주 수익률 | fp:Product | xsd:decimal | PRFD01N001.fd_wk1_ern_r | 최근 1주 수익률(%). 공모펀드에만 존재한다. | common.ttl |
| `fp:return1Y` | 1년 수익률 | fp:Product | xsd:decimal | PREF01N001, PRFD01N001, external:LSEG.adjusted_price_or_total_return, du_er_1y, fd_yr1_ern_r | 최근 1년 수익률(%). 국내ETF du_er_1y와 펀드 fd_yr1_ern_r를 우선한다. 해외ETF는 주최측에 1년 축이 없어 LSEG get_history의 조정가격 또는 total-return 계열이 권한상 확보될 때만 계산하며 단순 종가로 대체하지 않는다. | common.ttl |
| `fp:return2Y` | 2년 수익률 | fp:PublicFund | xsd:decimal | PRFD01N001.fd_yr2_ern_r | 최근 2년 수익률(%). 공모펀드 전용 구간. | common.ttl |
| `fp:return3M` | 3개월 수익률 | fp:Product | xsd:decimal | PREF01N001, PRFD01N001.du_er_3m, fd_mm3_ern_r | 최근 3개월 수익률(%). 원문 값을 보존하며 0/NULL은 비교·랭킹에서 제외한다. | common.ttl |
| `fp:return3Y` | 3년 수익률 | fp:PublicFund | xsd:decimal | PRFD01N001.fd_yr3_ern_r | 최근 3년 수익률(%). 공모펀드 전용 구간. | common.ttl |
| `fp:return5Y` | 5년 수익률 | fp:PublicFund | xsd:decimal | PRFD01N001.fd_yr5_ern_r | 최근 5년 수익률(%). 결측 원인을 설정기간으로 추정하지 않고 값 없음으로 표시한다. | common.ttl |
| `fp:return6M` | 6개월 수익률 | fp:Product | xsd:decimal | PREF01N001, PRFD01N001.du_er_6m, fd_mm6_ern_r | 최근 6개월 수익률(%). 원문 값을 보존하며 0/NULL은 비교·랭킹에서 제외한다. | common.ttl |
| `fp:returnYTD` | 연초이후 수익률 | fp:ETF | xsd:decimal | PREF01N001.du_er_ytd | 연초 이후 수익률(%). 국내ETF에만 존재한다. | common.ttl |
| `fp:riskGradeLabel` | 위험등급명(제로인) | fp:PublicFund | xsd:string | PRFD01N001.zrin_fd_ivst_risk_grd_nm | 제로인 위험등급명. 원문을 보존하고 공식 코드와 이름이 함께 검증된 경우만 정규화하며 서열 비교는 fp:hasRiskGrade 개체의 fp:riskGradeLevel로 한다. | fund_pub.ttl |
| `fp:riskGradeLevel` | 위험등급 수준 | fp:RiskGrade | xsd:integer | PRBD01N001, PREF01N001, PRFD01N001.PD_RISK_GCD, pd_risk_cd, zrin_fd_ivst_risk_gcd | 1=최고위험 … 6=최저위험. 채권·국내ETF·공모펀드 세 도메인의 서열 방향이 모두 같다. | common.ttl |
| `fp:saleStatus` | 판매 상태 | fp:PublicFund | xsd:string | PRFD01N001.sale_yn | 공식 판매상태 이름. 성과 측정값 0/NULL은 판매상태와 무관하게 값 없음으로 표시하고 랭킹에서 제외한다. | fund_pub.ttl |
| `fp:securityCode` | 증권 종목코드 | fp:Security | xsd:string | derived:etf_holding.derived:etf_holding.holding_code_raw | 편입증권의 식별 코드. 국내 종목은 6자리 ticker, 그 외는 원천 표기(ISIN·Bloomberg 티커)를 그대로 쓴다. **KR7로 시작하는 국내 ISIN은 ticker6(KR7247540008 → 247540)로 접어 같은 증권을 한 노드로 합친다** — 접지 않으면 같은 종목이 운용사별로 다른 노드가 되어 '이 종목을 담은 ETF' 질의가 누락된다. | common.ttl |
| `fp:soldByFirm` | 당사 취급 여부 | fp:PublicFund | xsd:boolean | PRFD01N001.thco_sale_yn | 당사 판매 취급 여부. 공식 Y/N만 사용하며 결측을 미취급으로 해석하지 않고 알 수 없음으로 보존한다. | fund_pub.ttl |
| `fp:sourceId` | 출처 식별자 | (fp:Holding ∪ fp:MetricSnapshot ∪ fp:SubsidiaryRelation) | xsd:string | derived:relations.derived:relations.source | 관계·수치의 출처 표시(RDB=주최측 값, LSEG 등=외부 보완). 관계 테이블의 source 컬럼을 그대로 승계한다. | common.ttl |
| `fp:standardItemCode` | 표준종목번호 | fp:PublicFund | xsd:string | PRFD01N001.std_itm_no | 보조 식별자. 형식 혼재·결측·중복 가능성이 있으므로 정본 식별자로 쓰지 않고 fp:productCode = itm_no를 사용한다. | fund_pub.ttl |
| `fp:strategyText` | 투자전략 원문 | fp:ETF | xsd:string | PREF02N001.cu_strtegy | enum이 아니라 서술형 투자전략 문단이다. 국내ETF의 동명 코드 컬럼과 이름만 같고 성격이 다르므로 정형 필터로 쓰지 않고 문서 청크·벡터 검색의 근거 텍스트로 소비한다. | etf_gl.ttl |
| `fp:themeName` | 테마명 | fp:Theme | xsd:string | derived:etf_theme.derived:etf_theme.theme | 테마 명칭. 원천 표기를 그대로 쓴다('우주항공/방산'처럼 슬래시 결합 테마가 있어 '우주'·'항공' 분리 검색은 성립하지 않는다). | common.ttl |
| `fp:ticker` | 티커 | (fp:ETF ∪ fp:ETN) | xsd:string | PREF02N001.pd_abrv_nm | 미국 상장 티커(VOO·SPY·BND 등). 자연어 질의의 주요 식별 표현이지만 중복 가능성이 있어 단독 URI로 쓰지 않고 RIC·ISIN 등과 함께 확인한다. | etf_gl.ttl |
| `fp:tradingSuspended` | 거래정지 여부 | (fp:ETF ∪ fp:ETN) | xsd:boolean | PREF01N001.pd_tr_yn | 거래상태 코드. 공식 이름/설명에 따라 해석하고 내부 코드값 0을 임의로 정상·정지 의미에 매핑하지 않는다. | etf_kr.ttl |
| `fp:validFrom` | 유효 시작일 | (fp:Holding ∪ fp:MetricSnapshot) | xsd:date | derived:relations.derived:relations.valid_from | 관계·수치가 유효해지는 시점. 기간 필터 질의('2026년 상반기에 새로 편입된')에 필요하다. | common.ttl |
| `fp:validTo` | 유효 종료일 | (fp:Holding ∪ fp:MetricSnapshot) | xsd:date | derived:relations.derived:relations.valid_to | 관계·수치가 만료되는 시점. 값이 없으면 현재 유효로 해석한다. | common.ttl |
| `fp:weight` | 편입비중 | fp:Holding | xsd:decimal | derived:etf_holding.derived:etf_holding.weight | 편입관계의 비중(%). 확보된 행에서만 fp:asOf 기준일과 출처 문서와 함께 제시하며 미확보를 0으로 대체하지 않는다. | common.ttl |

## 통제어휘와 허용값

질의값 검증은 아래 명명 개체의 존재 여부와 등급/레벨 속성을 사용합니다. 없는 값을 유사값으로 대체하지 않습니다.

| 유형 | 개체 | 라벨 | 정렬·코드 속성 | 원천 TTL |
|---|---|---|---|---|
| fp:AssetType | `fp:AssetType_Alternative` | 대체투자 | - | common.ttl |
| fp:AssetType | `fp:AssetType_Bond` | 채권 | - | common.ttl |
| fp:AssetType | `fp:AssetType_Commodity` | 원자재 | - | common.ttl |
| fp:AssetType | `fp:AssetType_Currency` | 통화 | - | common.ttl |
| fp:AssetType | `fp:AssetType_Equity` | 주식 | - | common.ttl |
| fp:AssetType | `fp:AssetType_MixedAsset` | 혼합자산 | - | common.ttl |
| fp:AssetType | `fp:AssetType_MoneyMarket` | 단기자금 | - | common.ttl |
| fp:AssetType | `fp:AssetType_Other` | 기타 | - | common.ttl |
| fp:AssetType | `fp:AssetType_RealEstate` | 부동산 | - | common.ttl |
| fp:BondIssuerType | `fp:IssuerType_Corporate` | 회사채 | - | bond_kr.ttl |
| fp:BondIssuerType | `fp:IssuerType_Government` | 국공채 | - | bond_kr.ttl |
| fp:BondIssuerType | `fp:IssuerType_Municipal` | 지방채 | - | bond_kr.ttl |
| fp:BondIssuerType | `fp:IssuerType_Special` | 특수채 | - | bond_kr.ttl |
| fp:ClassDifferentiation | `fp:ClassDiff_Multi` | 멀티클래스 | - | fund_pub.ttl |
| fp:ClassDifferentiation | `fp:ClassDiff_Single` | 단일클래스 | - | fund_pub.ttl |
| fp:CollateralType | `fp:Collateral_Guaranteed` | 보증 | - | bond_kr.ttl |
| fp:CollateralType | `fp:Collateral_Secured` | 담보부 | - | bond_kr.ttl |
| fp:CollateralType | `fp:Collateral_Subordinated` | 후순위 | - | bond_kr.ttl |
| fp:CollateralType | `fp:Collateral_Unsecured` | 무담보 | - | bond_kr.ttl |
| fp:CouponType | `fp:Coupon_Convertible` | 전환형 | - | bond_kr.ttl |
| fp:CouponType | `fp:Coupon_Fixed` | 고정금리 | - | bond_kr.ttl |
| fp:CouponType | `fp:Coupon_Floating` | 변동금리 | - | bond_kr.ttl |
| fp:CouponType | `fp:Coupon_Zero` | 무이표(할인채) | - | bond_kr.ttl |
| fp:CreditRating | `fp:Rating_A` | A | fp:ratingRank=6 | common.ttl |
| fp:CreditRating | `fp:Rating_AA` | AA | fp:ratingRank=3 | common.ttl |
| fp:CreditRating | `fp:Rating_AAA` | AAA | fp:ratingRank=1 | common.ttl |
| fp:CreditRating | `fp:Rating_AAm` | AA- | fp:ratingRank=4 | common.ttl |
| fp:CreditRating | `fp:Rating_AAp` | AA+ | fp:ratingRank=2 | common.ttl |
| fp:CreditRating | `fp:Rating_Am` | A- | fp:ratingRank=7 | common.ttl |
| fp:CreditRating | `fp:Rating_Ap` | A+ | fp:ratingRank=5 | common.ttl |
| fp:CreditRating | `fp:Rating_B` | B | fp:ratingRank=15 | common.ttl |
| fp:CreditRating | `fp:Rating_BB` | BB | fp:ratingRank=12 | common.ttl |
| fp:CreditRating | `fp:Rating_BBB` | BBB | fp:ratingRank=9 | common.ttl |
| fp:CreditRating | `fp:Rating_BBBm` | BBB- | fp:ratingRank=10 | common.ttl |
| fp:CreditRating | `fp:Rating_BBBp` | BBB+ | fp:ratingRank=8 | common.ttl |
| fp:CreditRating | `fp:Rating_BBm` | BB- | fp:ratingRank=13 | common.ttl |
| fp:CreditRating | `fp:Rating_BBp` | BB+ | fp:ratingRank=11 | common.ttl |
| fp:CreditRating | `fp:Rating_Bm` | B- | fp:ratingRank=16 | common.ttl |
| fp:CreditRating | `fp:Rating_Bp` | B+ | fp:ratingRank=14 | common.ttl |
| fp:CreditRating | `fp:Rating_C` | C | fp:ratingRank=19 | common.ttl |
| fp:CreditRating | `fp:Rating_CC` | CC | fp:ratingRank=18 | common.ttl |
| fp:CreditRating | `fp:Rating_CCC` | CCC | fp:ratingRank=17 | common.ttl |
| fp:Currency | `fp:Currency_EUR` | 유로 | - | common.ttl |
| fp:Currency | `fp:Currency_JPY` | 일본 엔 | - | common.ttl |
| fp:Currency | `fp:Currency_KRW` | 한국 원 | - | common.ttl |
| fp:Currency | `fp:Currency_USD` | 미국 달러 | - | common.ttl |
| fp:DistributionType | `fp:Distribution_Distributing` | 분배형 | - | etf_kr.ttl |
| fp:DistributionType | `fp:Distribution_TotalReturn` | 토탈리턴(TR) | - | etf_kr.ttl |
| fp:FundType | `fp:FundType_Derivative` | 파생형 | - | fund_pub.ttl |
| fp:FundType | `fp:FundType_FundOfFunds` | 재간접형 | - | fund_pub.ttl |
| fp:FundType | `fp:FundType_MixedAssets` | 혼합자산형 | - | fund_pub.ttl |
| fp:FundType | `fp:FundType_MoneyMarket` | MMF | - | fund_pub.ttl |
| fp:FundType | `fp:FundType_RealEstate` | 부동산형 | - | fund_pub.ttl |
| fp:FundType | `fp:FundType_Securities` | 증권형 | - | fund_pub.ttl |
| fp:FundType | `fp:FundType_SpecialAssets` | 특별자산형 | - | fund_pub.ttl |
| fp:InvestmentRegion | `fp:Region_Americas` | 남미·북미 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_Asia` | 아시아 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_China` | 중국 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_Domestic` | 국내 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_Emerging` | 이머징·브릭스 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_Europe` | 유럽 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_Global` | 글로벌 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_GlobalExUS` | 글로벌(미국제외) | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_India` | 인도 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_Japan` | 일본 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_MEA` | 중동·아프리카 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_Overseas` | 해외 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_US` | 미국 | - | common.ttl |
| fp:InvestmentRegion | `fp:Region_Vietnam` | 베트남 | - | common.ttl |
| fp:InvestorEligibility | `fp:Eligibility_Private` | 사모 | - | fund_pub.ttl |
| fp:InvestorEligibility | `fp:Eligibility_Public` | 공모 | - | fund_pub.ttl |
| fp:IssuanceMarket | `fp:Market_Domestic` | 국내 발행 | - | bond_kr.ttl |
| fp:IssuanceMarket | `fp:Market_Foreign` | 해외 발행 | - | bond_kr.ttl |
| fp:IssuanceType | `fp:Issuance_Additional` | 추가형 | - | fund_pub.ttl |
| fp:IssuanceType | `fp:Issuance_Unit` | 단위형 | - | fund_pub.ttl |
| fp:IssuerCategory | `fp:IssuerCat_Financial` | 금융 회사 | - | bond_kr.ttl |
| fp:IssuerCategory | `fp:IssuerCat_NonFinancial` | 비금융 회사 | - | bond_kr.ttl |
| fp:IssuerCategory | `fp:IssuerCat_Other` | 기타 | - | bond_kr.ttl |
| fp:IssuerCategory | `fp:IssuerCat_Sovereign` | 국가 | - | bond_kr.ttl |
| fp:IssuerCategory | `fp:IssuerCat_SovereignAgency` | 공공기관 | - | bond_kr.ttl |
| fp:IssuerCategory | `fp:IssuerCat_SubSovereign` | 지방정부 | - | bond_kr.ttl |
| fp:LeverageType | `fp:Leverage_2X` | 레버리지 2배 | - | etf_kr.ttl |
| fp:LeverageType | `fp:Leverage_3X` | 레버리지 3배 | - | etf_kr.ttl |
| fp:LeverageType | `fp:Leverage_Inverse1X` | 인버스 1배 | - | etf_kr.ttl |
| fp:LeverageType | `fp:Leverage_Inverse2X` | 인버스 2배 | - | etf_kr.ttl |
| fp:LeverageType | `fp:Leverage_Inverse3X` | 인버스 3배 | - | etf_kr.ttl |
| fp:LeverageType | `fp:Leverage_Standard` | 일반(1배) | - | etf_kr.ttl |
| fp:ListingType | `fp:Listing_Listed` | 상장 | - | fund_pub.ttl |
| fp:ListingType | `fp:Listing_Unlisted` | 비상장 | - | fund_pub.ttl |
| fp:ManagementStrategy | `fp:Strategy_Active` | 액티브 | - | etf_kr.ttl |
| fp:ManagementStrategy | `fp:Strategy_Passive` | 패시브 | - | etf_kr.ttl |
| fp:MaturityClass | `fp:Maturity_LongTerm` | 장기 | - | bond_kr.ttl |
| fp:MaturityClass | `fp:Maturity_Matured` | 만기경과 | - | bond_kr.ttl |
| fp:MaturityClass | `fp:Maturity_MidTerm` | 중기 | - | bond_kr.ttl |
| fp:MaturityClass | `fp:Maturity_ShortTerm` | 단기 | - | bond_kr.ttl |
| fp:RatingBand | `fp:RatingBand_A` | A등급 | - | bond_kr.ttl |
| fp:RatingBand | `fp:RatingBand_AA` | AA등급 | - | bond_kr.ttl |
| fp:RatingBand | `fp:RatingBand_AAA` | AAA등급 | - | bond_kr.ttl |
| fp:RatingBand | `fp:RatingBand_BBB` | BBB등급 | - | bond_kr.ttl |
| fp:RatingBand | `fp:RatingBand_NotRated` | 무등급 | - | bond_kr.ttl |
| fp:RatingBand | `fp:RatingBand_Specul` | 투기등급 | - | bond_kr.ttl |
| fp:RatingStatus | `fp:Rated` | 등급 보유 | - | common.ttl |
| fp:RatingStatus | `fp:RatingUnknown` | 등급 정보 없음 | - | common.ttl |
| fp:RatingStatus | `fp:UnratedByDesign` | 미평가(평가 대상 아님) | - | common.ttl |
| fp:RedemptionType | `fp:Redemption_ClosedEnded` | 폐쇄형 | - | fund_pub.ttl |
| fp:RedemptionType | `fp:Redemption_OpenEnded` | 개방형 | - | fund_pub.ttl |
| fp:ReplicationMethod | `fp:Replication_Active` | 액티브 | - | common.ttl |
| fp:ReplicationMethod | `fp:Replication_Other` | 기타 | - | common.ttl |
| fp:ReplicationMethod | `fp:Replication_Physical` | 실물복제 | - | common.ttl |
| fp:ReplicationMethod | `fp:Replication_Synthetic` | 합성복제 | - | common.ttl |
| fp:RiskGrade | `fp:RiskGrade_1` | 매우 높은 위험(1등급) | fp:riskGradeLevel=1 | common.ttl |
| fp:RiskGrade | `fp:RiskGrade_2` | 높은 위험(2등급) | fp:riskGradeLevel=2 | common.ttl |
| fp:RiskGrade | `fp:RiskGrade_3` | 다소 높은 위험(3등급) | fp:riskGradeLevel=3 | common.ttl |
| fp:RiskGrade | `fp:RiskGrade_4` | 보통 위험(4등급) | fp:riskGradeLevel=4 | common.ttl |
| fp:RiskGrade | `fp:RiskGrade_5` | 낮은 위험(5등급) | fp:riskGradeLevel=5 | common.ttl |
| fp:RiskGrade | `fp:RiskGrade_6` | 매우 낮은 위험(6등급) | fp:riskGradeLevel=6 | common.ttl |
| fp:Theme | `fp:Theme_2차전지` | 2차전지 | fp:themeName=2차전지 | etf_kr.ttl |
| fp:Theme | `fp:Theme_5G` | 5G | fp:themeName=5G | etf_kr.ttl |
| fp:Theme | `fp:Theme_AI` | AI | fp:themeName=AI | etf_kr.ttl |
| fp:Theme | `fp:Theme_AI(인공지능)_운용` | AI(인공지능) 운용 | fp:themeName=AI(인공지능) 운용 | etf_kr.ttl |
| fp:Theme | `fp:Theme_AI전력` | AI전력 | fp:themeName=AI전력 | etf_kr.ttl |
| fp:Theme | `fp:Theme_All_Weather` | All Weather | fp:themeName=All Weather | etf_kr.ttl |
| fp:Theme | `fp:Theme_CSI` | CSI | fp:themeName=CSI | etf_kr.ttl |
| fp:Theme | `fp:Theme_Cash_Cows` | Cash Cows | fp:themeName=Cash Cows | etf_kr.ttl |
| fp:Theme | `fp:Theme_ChiNext` | ChiNext | fp:themeName=ChiNext | etf_kr.ttl |
| fp:Theme | `fp:Theme_DowJones` | DowJones | fp:themeName=DowJones | etf_kr.ttl |
| fp:Theme | `fp:Theme_ESG종합` | ESG종합 | fp:themeName=ESG종합 | etf_kr.ttl |
| fp:Theme | `fp:Theme_EuroStoxx50` | EuroStoxx50 | fp:themeName=EuroStoxx50 | etf_kr.ttl |
| fp:Theme | `fp:Theme_FTSE_China_A50` | FTSE China A50 | fp:themeName=FTSE China A50 | etf_kr.ttl |
| fp:Theme | `fp:Theme_IPO/M&A` | IPO/M&A | fp:themeName=IPO/M&A | etf_kr.ttl |
| fp:Theme | `fp:Theme_IT섹터` | IT섹터 | fp:themeName=IT섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_K-뉴딜` | K-뉴딜 | fp:themeName=K-뉴딜 | etf_kr.ttl |
| fp:Theme | `fp:Theme_K-반도체` | K-반도체 | fp:themeName=K-반도체 | etf_kr.ttl |
| fp:Theme | `fp:Theme_KOSDAQ` | KOSDAQ | fp:themeName=KOSDAQ | etf_kr.ttl |
| fp:Theme | `fp:Theme_KOSDAQ150` | KOSDAQ150 | fp:themeName=KOSDAQ150 | etf_kr.ttl |
| fp:Theme | `fp:Theme_KOSDAQ글로벌` | KOSDAQ글로벌 | fp:themeName=KOSDAQ글로벌 | etf_kr.ttl |
| fp:Theme | `fp:Theme_KOSPI` | KOSPI | fp:themeName=KOSPI | etf_kr.ttl |
| fp:Theme | `fp:Theme_KOSPI200` | KOSPI200 | fp:themeName=KOSPI200 | etf_kr.ttl |
| fp:Theme | `fp:Theme_KRX300` | KRX300 | fp:themeName=KRX300 | etf_kr.ttl |
| fp:Theme | `fp:Theme_MMF` | MMF | fp:themeName=MMF | etf_kr.ttl |
| fp:Theme | `fp:Theme_MSCI_Korea` | MSCI Korea | fp:themeName=MSCI Korea | etf_kr.ttl |
| fp:Theme | `fp:Theme_Moat(경제적해자)` | Moat(경제적해자) | fp:themeName=Moat(경제적해자) | etf_kr.ttl |
| fp:Theme | `fp:Theme_Nifty50` | Nifty50 | fp:themeName=Nifty50 | etf_kr.ttl |
| fp:Theme | `fp:Theme_Nikkei225` | Nikkei225 | fp:themeName=Nikkei225 | etf_kr.ttl |
| fp:Theme | `fp:Theme_S&P500` | S&P500 | fp:themeName=S&P500 | etf_kr.ttl |
| fp:Theme | `fp:Theme_TDF` | TDF | fp:themeName=TDF | etf_kr.ttl |
| fp:Theme | `fp:Theme_TRF` | TRF | fp:themeName=TRF | etf_kr.ttl |
| fp:Theme | `fp:Theme_e커머스` | e커머스 | fp:themeName=e커머스 | etf_kr.ttl |
| fp:Theme | `fp:Theme_美인기주식` | 美인기주식 | fp:themeName=美인기주식 | etf_kr.ttl |
| fp:Theme | `fp:Theme_가치주` | 가치주 | fp:themeName=가치주 | etf_kr.ttl |
| fp:Theme | `fp:Theme_건설` | 건설 | fp:themeName=건설 | etf_kr.ttl |
| fp:Theme | `fp:Theme_게임` | 게임 | fp:themeName=게임 | etf_kr.ttl |
| fp:Theme | `fp:Theme_경기소비재섹터` | 경기소비재섹터 | fp:themeName=경기소비재섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_고배당` | 고배당 | fp:themeName=고배당 | etf_kr.ttl |
| fp:Theme | `fp:Theme_고수익채권` | 고수익채권 | fp:themeName=고수익채권 | etf_kr.ttl |
| fp:Theme | `fp:Theme_구리` | 구리 | fp:themeName=구리 | etf_kr.ttl |
| fp:Theme | `fp:Theme_구조화` | 구조화 | fp:themeName=구조화 | etf_kr.ttl |
| fp:Theme | `fp:Theme_국공채` | 국공채 | fp:themeName=국공채 | etf_kr.ttl |
| fp:Theme | `fp:Theme_그룹주` | 그룹주 | fp:themeName=그룹주 | etf_kr.ttl |
| fp:Theme | `fp:Theme_글로벌` | 글로벌 | fp:themeName=글로벌 | etf_kr.ttl |
| fp:Theme | `fp:Theme_글로벌반도체` | 글로벌반도체 | fp:themeName=글로벌반도체 | etf_kr.ttl |
| fp:Theme | `fp:Theme_금` | 금 | fp:themeName=금 | etf_kr.ttl |
| fp:Theme | `fp:Theme_금융` | 금융 | fp:themeName=금융 | etf_kr.ttl |
| fp:Theme | `fp:Theme_금융섹터` | 금융섹터 | fp:themeName=금융섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_금채굴기업` | 금채굴기업 | fp:themeName=금채굴기업 | etf_kr.ttl |
| fp:Theme | `fp:Theme_기타_귀금속` | 기타 귀금속 | fp:themeName=기타 귀금속 | etf_kr.ttl |
| fp:Theme | `fp:Theme_기타_대표지수` | 기타 대표지수 | fp:themeName=기타 대표지수 | etf_kr.ttl |
| fp:Theme | `fp:Theme_기타_아시아` | 기타 아시아 | fp:themeName=기타 아시아 | etf_kr.ttl |
| fp:Theme | `fp:Theme_기후변화솔루션` | 기후변화솔루션 | fp:themeName=기후변화솔루션 | etf_kr.ttl |
| fp:Theme | `fp:Theme_나스닥100` | 나스닥100 | fp:themeName=나스닥100 | etf_kr.ttl |
| fp:Theme | `fp:Theme_농산물` | 농산물 | fp:themeName=농산물 | etf_kr.ttl |
| fp:Theme | `fp:Theme_농업` | 농업 | fp:themeName=농업 | etf_kr.ttl |
| fp:Theme | `fp:Theme_단기금리` | 단기금리 | fp:themeName=단기금리 | etf_kr.ttl |
| fp:Theme | `fp:Theme_단기채` | 단기채 | fp:themeName=단기채 | etf_kr.ttl |
| fp:Theme | `fp:Theme_대만` | 대만 | fp:themeName=대만 | etf_kr.ttl |
| fp:Theme | `fp:Theme_대형주` | 대형주 | fp:themeName=대형주 | etf_kr.ttl |
| fp:Theme | `fp:Theme_독일` | 독일 | fp:themeName=독일 | etf_kr.ttl |
| fp:Theme | `fp:Theme_동일가중` | 동일가중 | fp:themeName=동일가중 | etf_kr.ttl |
| fp:Theme | `fp:Theme_러셀2000` | 러셀2000 | fp:themeName=러셀2000 | etf_kr.ttl |
| fp:Theme | `fp:Theme_러시아` | 러시아 | fp:themeName=러시아 | etf_kr.ttl |
| fp:Theme | `fp:Theme_레버리지2X` | 레버리지2X | fp:themeName=레버리지2X | etf_kr.ttl |
| fp:Theme | `fp:Theme_로봇` | 로봇 | fp:themeName=로봇 | etf_kr.ttl |
| fp:Theme | `fp:Theme_리쇼어링` | 리쇼어링 | fp:themeName=리쇼어링 | etf_kr.ttl |
| fp:Theme | `fp:Theme_리츠` | 리츠 | fp:themeName=리츠 | etf_kr.ttl |
| fp:Theme | `fp:Theme_리튬` | 리튬 | fp:themeName=리튬 | etf_kr.ttl |
| fp:Theme | `fp:Theme_만기매칭형채권` | 만기매칭형채권 | fp:themeName=만기매칭형채권 | etf_kr.ttl |
| fp:Theme | `fp:Theme_멀티팩터` | 멀티팩터 | fp:themeName=멀티팩터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_메타버스` | 메타버스 | fp:themeName=메타버스 | etf_kr.ttl |
| fp:Theme | `fp:Theme_멕시코` | 멕시코 | fp:themeName=멕시코 | etf_kr.ttl |
| fp:Theme | `fp:Theme_명품` | 명품 | fp:themeName=명품 | etf_kr.ttl |
| fp:Theme | `fp:Theme_모멘텀` | 모멘텀 | fp:themeName=모멘텀 | etf_kr.ttl |
| fp:Theme | `fp:Theme_모빌리티` | 모빌리티 | fp:themeName=모빌리티 | etf_kr.ttl |
| fp:Theme | `fp:Theme_물` | 물 | fp:themeName=물 | etf_kr.ttl |
| fp:Theme | `fp:Theme_물가연동채권` | 물가연동채권 | fp:themeName=물가연동채권 | etf_kr.ttl |
| fp:Theme | `fp:Theme_미국` | 미국 | fp:themeName=미국 | etf_kr.ttl |
| fp:Theme | `fp:Theme_미국달러` | 미국달러 | fp:themeName=미국달러 | etf_kr.ttl |
| fp:Theme | `fp:Theme_미디어/엔터` | 미디어/엔터 | fp:themeName=미디어/엔터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_바이오테크` | 바이오테크 | fp:themeName=바이오테크 | etf_kr.ttl |
| fp:Theme | `fp:Theme_밸류체인` | 밸류체인 | fp:themeName=밸류체인 | etf_kr.ttl |
| fp:Theme | `fp:Theme_버퍼형` | 버퍼형 | fp:themeName=버퍼형 | etf_kr.ttl |
| fp:Theme | `fp:Theme_베타전략` | 베타전략 | fp:themeName=베타전략 | etf_kr.ttl |
| fp:Theme | `fp:Theme_베트남` | 베트남 | fp:themeName=베트남 | etf_kr.ttl |
| fp:Theme | `fp:Theme_변동금리채` | 변동금리채 | fp:themeName=변동금리채 | etf_kr.ttl |
| fp:Theme | `fp:Theme_변동성` | 변동성 | fp:themeName=변동성 | etf_kr.ttl |
| fp:Theme | `fp:Theme_부동산섹터` | 부동산섹터 | fp:themeName=부동산섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_비만치료` | 비만치료 | fp:themeName=비만치료 | etf_kr.ttl |
| fp:Theme | `fp:Theme_빅데이터` | 빅데이터 | fp:themeName=빅데이터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_빅테크` | 빅테크 | fp:themeName=빅테크 | etf_kr.ttl |
| fp:Theme | `fp:Theme_사이버보안` | 사이버보안 | fp:themeName=사이버보안 | etf_kr.ttl |
| fp:Theme | `fp:Theme_사회책임` | 사회책임 | fp:themeName=사회책임 | etf_kr.ttl |
| fp:Theme | `fp:Theme_산업재섹터` | 산업재섹터 | fp:themeName=산업재섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_삼성전자` | 삼성전자 | fp:themeName=삼성전자 | etf_kr.ttl |
| fp:Theme | `fp:Theme_선진국` | 선진국 | fp:themeName=선진국 | etf_kr.ttl |
| fp:Theme | `fp:Theme_성장주` | 성장주 | fp:themeName=성장주 | etf_kr.ttl |
| fp:Theme | `fp:Theme_소부장` | 소부장 | fp:themeName=소부장 | etf_kr.ttl |
| fp:Theme | `fp:Theme_소비` | 소비 | fp:themeName=소비 | etf_kr.ttl |
| fp:Theme | `fp:Theme_소재섹터` | 소재섹터 | fp:themeName=소재섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_소프트웨어` | 소프트웨어 | fp:themeName=소프트웨어 | etf_kr.ttl |
| fp:Theme | `fp:Theme_소형주` | 소형주 | fp:themeName=소형주 | etf_kr.ttl |
| fp:Theme | `fp:Theme_손실제한` | 손실제한 | fp:themeName=손실제한 | etf_kr.ttl |
| fp:Theme | `fp:Theme_수소` | 수소 | fp:themeName=수소 | etf_kr.ttl |
| fp:Theme | `fp:Theme_신흥국` | 신흥국 | fp:themeName=신흥국 | etf_kr.ttl |
| fp:Theme | `fp:Theme_아메리카` | 아메리카 | fp:themeName=아메리카 | etf_kr.ttl |
| fp:Theme | `fp:Theme_아시아퍼시픽` | 아시아퍼시픽 | fp:themeName=아시아퍼시픽 | etf_kr.ttl |
| fp:Theme | `fp:Theme_알리바바` | 알리바바 | fp:themeName=알리바바 | etf_kr.ttl |
| fp:Theme | `fp:Theme_애플` | 애플 | fp:themeName=애플 | etf_kr.ttl |
| fp:Theme | `fp:Theme_액티브` | 액티브 | fp:themeName=액티브 | etf_kr.ttl |
| fp:Theme | `fp:Theme_양자컴퓨터` | 양자컴퓨터 | fp:themeName=양자컴퓨터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_에너지섹터` | 에너지섹터 | fp:themeName=에너지섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_엔` | 엔 | fp:themeName=엔 | etf_kr.ttl |
| fp:Theme | `fp:Theme_엔비디아` | 엔비디아 | fp:themeName=엔비디아 | etf_kr.ttl |
| fp:Theme | `fp:Theme_여행/레저` | 여행/레저 | fp:themeName=여행/레저 | etf_kr.ttl |
| fp:Theme | `fp:Theme_우선주` | 우선주 | fp:themeName=우선주 | etf_kr.ttl |
| fp:Theme | `fp:Theme_우주항공/방산` | 우주항공/방산 | fp:themeName=우주항공/방산 | etf_kr.ttl |
| fp:Theme | `fp:Theme_운송` | 운송 | fp:themeName=운송 | etf_kr.ttl |
| fp:Theme | `fp:Theme_원유` | 원유 | fp:themeName=원유 | etf_kr.ttl |
| fp:Theme | `fp:Theme_원유/가스기업` | 원유/가스기업 | fp:themeName=원유/가스기업 | etf_kr.ttl |
| fp:Theme | `fp:Theme_원자력` | 원자력 | fp:themeName=원자력 | etf_kr.ttl |
| fp:Theme | `fp:Theme_월배당` | 월배당 | fp:themeName=월배당 | etf_kr.ttl |
| fp:Theme | `fp:Theme_유럽` | 유럽 | fp:themeName=유럽 | etf_kr.ttl |
| fp:Theme | `fp:Theme_유틸리티섹터` | 유틸리티섹터 | fp:themeName=유틸리티섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_은` | 은 | fp:themeName=은 | etf_kr.ttl |
| fp:Theme | `fp:Theme_인도` | 인도 | fp:themeName=인도 | etf_kr.ttl |
| fp:Theme | `fp:Theme_인도네시아` | 인도네시아 | fp:themeName=인도네시아 | etf_kr.ttl |
| fp:Theme | `fp:Theme_인버스` | 인버스 | fp:themeName=인버스 | etf_kr.ttl |
| fp:Theme | `fp:Theme_인버스2X` | 인버스2X | fp:themeName=인버스2X | etf_kr.ttl |
| fp:Theme | `fp:Theme_인터넷` | 인터넷 | fp:themeName=인터넷 | etf_kr.ttl |
| fp:Theme | `fp:Theme_인프라` | 인프라 | fp:themeName=인프라 | etf_kr.ttl |
| fp:Theme | `fp:Theme_일본` | 일본 | fp:themeName=일본 | etf_kr.ttl |
| fp:Theme | `fp:Theme_자산배분` | 자산배분 | fp:themeName=자산배분 | etf_kr.ttl |
| fp:Theme | `fp:Theme_장기채` | 장기채 | fp:themeName=장기채 | etf_kr.ttl |
| fp:Theme | `fp:Theme_재간접` | 재간접 | fp:themeName=재간접 | etf_kr.ttl |
| fp:Theme | `fp:Theme_저탄소` | 저탄소 | fp:themeName=저탄소 | etf_kr.ttl |
| fp:Theme | `fp:Theme_전기` | 전기 | fp:themeName=전기 | etf_kr.ttl |
| fp:Theme | `fp:Theme_정방향` | 정방향 | fp:themeName=정방향 | etf_kr.ttl |
| fp:Theme | `fp:Theme_조선/해운` | 조선/해운 | fp:themeName=조선/해운 | etf_kr.ttl |
| fp:Theme | `fp:Theme_종합_멀티에셋` | 종합 멀티에셋 | fp:themeName=종합 멀티에셋 | etf_kr.ttl |
| fp:Theme | `fp:Theme_종합주식` | 종합주식 | fp:themeName=종합주식 | etf_kr.ttl |
| fp:Theme | `fp:Theme_종합채권` | 종합채권 | fp:themeName=종합채권 | etf_kr.ttl |
| fp:Theme | `fp:Theme_주식+채권` | 주식+채권 | fp:themeName=주식+채권 | etf_kr.ttl |
| fp:Theme | `fp:Theme_주주가치` | 주주가치 | fp:themeName=주주가치 | etf_kr.ttl |
| fp:Theme | `fp:Theme_중국` | 중국 | fp:themeName=중국 | etf_kr.ttl |
| fp:Theme | `fp:Theme_중기채` | 중기채 | fp:themeName=중기채 | etf_kr.ttl |
| fp:Theme | `fp:Theme_중형주` | 중형주 | fp:themeName=중형주 | etf_kr.ttl |
| fp:Theme | `fp:Theme_지배구조` | 지배구조 | fp:themeName=지배구조 | etf_kr.ttl |
| fp:Theme | `fp:Theme_차이나H` | 차이나H | fp:themeName=차이나H | etf_kr.ttl |
| fp:Theme | `fp:Theme_차이나과창판` | 차이나과창판 | fp:themeName=차이나과창판 | etf_kr.ttl |
| fp:Theme | `fp:Theme_채권+리츠` | 채권+리츠 | fp:themeName=채권+리츠 | etf_kr.ttl |
| fp:Theme | `fp:Theme_철강` | 철강 | fp:themeName=철강 | etf_kr.ttl |
| fp:Theme | `fp:Theme_초단기채권` | 초단기채권 | fp:themeName=초단기채권 | etf_kr.ttl |
| fp:Theme | `fp:Theme_친환경` | 친환경 | fp:themeName=친환경 | etf_kr.ttl |
| fp:Theme | `fp:Theme_친환경에너지` | 친환경에너지 | fp:themeName=친환경에너지 | etf_kr.ttl |
| fp:Theme | `fp:Theme_커버드콜` | 커버드콜 | fp:themeName=커버드콜 | etf_kr.ttl |
| fp:Theme | `fp:Theme_코리아밸류업` | 코리아밸류업 | fp:themeName=코리아밸류업 | etf_kr.ttl |
| fp:Theme | `fp:Theme_퀄리티` | 퀄리티 | fp:themeName=퀄리티 | etf_kr.ttl |
| fp:Theme | `fp:Theme_클라우드컴퓨팅` | 클라우드컴퓨팅 | fp:themeName=클라우드컴퓨팅 | etf_kr.ttl |
| fp:Theme | `fp:Theme_탄소배출권` | 탄소배출권 | fp:themeName=탄소배출권 | etf_kr.ttl |
| fp:Theme | `fp:Theme_태양광` | 태양광 | fp:themeName=태양광 | etf_kr.ttl |
| fp:Theme | `fp:Theme_테슬라` | 테슬라 | fp:themeName=테슬라 | etf_kr.ttl |
| fp:Theme | `fp:Theme_토탈리턴` | 토탈리턴 | fp:themeName=토탈리턴 | etf_kr.ttl |
| fp:Theme | `fp:Theme_통신서비스섹터` | 통신서비스섹터 | fp:themeName=통신서비스섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_팔란티어` | 팔란티어 | fp:themeName=팔란티어 | etf_kr.ttl |
| fp:Theme | `fp:Theme_핀테크` | 핀테크 | fp:themeName=핀테크 | etf_kr.ttl |
| fp:Theme | `fp:Theme_필수소비재섹터` | 필수소비재섹터 | fp:themeName=필수소비재섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_한국` | 한국 | fp:themeName=한국 | etf_kr.ttl |
| fp:Theme | `fp:Theme_항셍` | 항셍 | fp:themeName=항셍 | etf_kr.ttl |
| fp:Theme | `fp:Theme_항셍테크` | 항셍테크 | fp:themeName=항셍테크 | etf_kr.ttl |
| fp:Theme | `fp:Theme_헬스케어섹터` | 헬스케어섹터 | fp:themeName=헬스케어섹터 | etf_kr.ttl |
| fp:Theme | `fp:Theme_혁신기업` | 혁신기업 | fp:themeName=혁신기업 | etf_kr.ttl |
| fp:Theme | `fp:Theme_화장품` | 화장품 | fp:themeName=화장품 | etf_kr.ttl |
| fp:Theme | `fp:Theme_환헤지` | 환헤지 | fp:themeName=환헤지 | etf_kr.ttl |
| fp:Theme | `fp:Theme_회사채` | 회사채 | fp:themeName=회사채 | etf_kr.ttl |
| fp:TradingMarket | `fp:TradingMarket_Exchange` | 장내 | - | bond_kr.ttl |
| fp:TradingMarket | `fp:TradingMarket_OTC` | 장외 | - | bond_kr.ttl |
| fp:UnderlyingScope | `fp:Scope_MarketRepresentative` | 시장대표 | - | etf_kr.ttl |
| fp:UnderlyingScope | `fp:Scope_SectorTheme` | 섹터·테마 | - | etf_kr.ttl |
| fp:UnderlyingScope | `fp:Scope_SingleStock` | 개별종목 | - | etf_kr.ttl |

## 검증과 대표 SPARQL

- TBox/ABox 10개 TTL 파싱, 클래스·속성 존재, domain/range, n-ary 필수 predicate를 검사합니다.
- 모든 ABox subject URI가 `http://mafest.ai/instance/`로 시작하는지 검사합니다.
- 외부 근거가 없는 편입·자회사·문서 관계는 생성하지 않습니다.
- named graph별 triple 수와 SHA-256은 빌드 시 생성되는 `artifacts/graph_v2/graph_manifest.json`이 정본입니다.

```sparql
PREFIX fp: <http://mafest.ai/product#>
SELECT ?product ?name ?classification WHERE {
  GRAPH <http://mafest.ai/graph/abox/etf_kr> {
    ?product a fp:KoreanETF ;
             fp:productName ?name ;
             fp:hasAssetType ?classification .
  }
}
LIMIT 100
```
