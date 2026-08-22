# WBS — 공모펀드

> 실측 기준 2026-08-21 · 제출 마감 2026-09-06 23:59(`docs/spec_0818.md:508`) · 잔여 16일
> 모든 수치는 `data/csv/PRFD01N001_fund_pub_master_20260711.csv`(95,619행)와 `data/enriched/fund_pub_dedup.csv`(11,138행)를 pandas(`dtype=str, keep_default_na=False`)로 직접 세었다.

## 0. 한 줄 요약

공모펀드는 **외부 수집이 아니라 이미 가진 것을 안 쓰고 있는 상태**다 — 주최측이 6개 분류축의 정답 라벨 100건(`PRFD01N001_fund_pub_axis_sample_20260711.csv`)을 줬는데 그중 3축이 보유 컬럼만으로 100% 재현되고, 온톨로지 ABox에는 공모펀드에 적용 가능한 ObjectProperty 20개 중 7개·DatatypeProperty 14개 중 1개만 실려 있으며, **클래스 중복을 제거하지 않아 순자산이 3.33배 부풀려진 채 랭킹 질의에 들어간다.** 외부 데이터(편입내역·근거문서) 없이도 관련 8문항(8·9·10·19·20·21·25·26·30 중 21은 이미 '가능') 중 4문항의 감점 요인을 16일 안에 제거할 수 있고, 편입내역이 필요한 Q30은 대상 펀드가 실질 1종이라 범위를 좁히면 손이 닿는다.

---

## 1. 현재 상태 (실측 2026-08-21)

| 축 | 보유 | 결측·미확보 | 근거 파일 |
|---|---|---|---|
| 마스터 원본 | 95,619행 / 45컬럼. PK = (`itm_no`, `prfd_attr_cd`, `zrin_fd_ivst_risk_gcd`) | — | `data/csv/PRFD01N001_fund_pub_master_20260711.csv`, `..._schema_20260711.csv` |
| dedup 파생 | 11,138종(`itm_no` 단위) / 45컬럼 | 파싱 붕괴 행(`itm_no='"'`) 1건 배제 완료 | `data/enriched/fund_pub_dedup.csv`, `docs_data_layer/DATA_LAYER_PLAN.md:69` |
| **기준일** | **0컬럼.** 45컬럼 중 날짜형·갱신일 컬럼이 **하나도 없다**(정규식 `dt\|date\|ymd\|updt` 매칭 0건) | 순자산·수익률 6구간의 기준일을 데이터로 말할 방법이 없음 | `ontology/fund_pub.ttl:36-37`, `QUERY_COVERAGE_35.md:293` |
| **주최측 분류축 정답** | **axis_sample 100행 × 6축**(`axis_fundType`·`redemptionType`·`issuanceType`·`listingType`·`classDifferentiation`·`investorEligibility`) — 라벨된 정답 샘플 | 11,138종 전량 라벨은 없음. 규칙을 역산해야 함 | `data/csv/PRFD01N001_fund_pub_axis_sample_20260711.csv` |
| ├ 재현 가능(실측 100/100) | `axis_fundType`(`or_attr_desc` 매핑), `axis_listingType`(`ksd_itm_no ∈ etf.pd_itm_no`), `axis_investorEligibility`(`prvo_pbff_desc`) | — | 아래 §1.1 |
| ├ 재현 불완전 | `axis_classDifferentiation` 최선 규칙 **71/100** | `mtco_itm_no` 그룹크기 규칙은 **48/100** — `fund_pub.ttl:74`의 "재현 가능" 주장이 샘플로 반증됨 | 동 |
| └ 재현 불가 | `axis_redemptionType`(다수결 78% 대비 최고 신호 81.2%), `axis_issuanceType`(정답 99/100이 `AdditionalType` 단일값이라 신호 무의미) | `fd_set_pcd`·`kofia_fd_ccd` 20자리 전수 스캔에도 분리축 없음 | 동 |
| 값 결측률(11,138 기준) | 순자산 16.59% / 위험등급 23.10% / 환헤지 37.88% / 1년수익률 37.00% / 6M 34.10% / 3M 32.69% / 1M 32.03% / 1W 31.77% / 3Y 45.21% / 5Y 49.90% | `bmrk_nm`·`sale_yn`·`itm_nm`·`curr_cd`는 결측 0% | 본 실측 |
| 식별자 sentinel | `fss_itm_no='000000000000'` 3,022종(**27.1%**) — DART 펀드공시 조인키가 4건 중 1건 없음 | `rptt_ksd_itm_no` sentinel 476종, `mtco_itm_no='0000000'` 33종 | 본 실측, `fund_pub.ttl:169,181` |
| **클래스 그레인** | `mtco_itm_no` 정규화 그룹 **4,580개**(원값 4,660). 멀티클래스 그룹 1,661개 = **펀드 8,219종(73.8%)이 중복 축에 속함** | **순자산이 클래스가 아니라 모펀드 단위 값**이다 — 멀티클래스 그룹의 **74.1%(1,132/1,528)** 가 그룹 내 순자산 고유값 1종. 클래스 단위 합계 1,545.8조 vs 모펀드 단위 463.8조 = **3.33배 과대계상** | 본 실측 |
| 온톨로지 TBox | `fund_pub.ttl` 236줄 — 클래스 6·개체 17·ObjectProperty 6·DatatypeProperty 14, `rdfs:comment` 27 | — | `ontology/fund_pub.ttl` |
| **온톨로지 ABox** | `instances_fund_pub.ttl` — 11,115 `fp:PublicFund` + 23 `fp:Product`(사모 15 + 구분결측 8). **술어 13종뿐** | 적용 가능 ObjectProperty **20개 중 7개만 적재**, `fund_pub.ttl` DatatypeProperty **14개 중 1개(`ksdCode`)만 적재**. **수치(순자산·수익률)는 그래프에 0건** | 본 실측, §1.2 |
| ETF 동일상품 링크 | `fp:sameVehicleAs` **47종**(`fund.ksd_itm_no ∩ etf_kr.pd_itm_no`) | **단방향 적재.** `instances_etf_kr.ttl`에 0건 → ETF 노드에서 출발하는 SPARQL은 0건 반환. `owl:SymmetricProperty` 선언은 있으나 pyoxigraph는 추론 안 함 | `ontology/common.ttl:363-368`, 본 실측 |
| 편입내역 | **0행.** 45컬럼 중 편입종목 계열 컬럼 0개 | Q20·26·30 펀드측 전부 미충족 | `QUERY_COVERAGE_35.md:117,173` |
| 근거문서 | **0건.** `data/external/evidence_docs_recon/` 디렉터리만 존재(0바이트) | Q25(정책자료)·Q30(위험문서) 단독 blocking | `EXTERNAL_DATA_PLAN.md:44`, 본 실측 |
| 35문항 판정 | 관련 9문항 중 **가능 1**(21) / **부분 6**(8·9·10·19·20·26) / **불가 2**(25·30) | 상 난이도 '가능' 0건 | `QUERY_COVERAGE_35.md:151-153,162-164,168-169,173` |

### 1.1 주최측 6분류축 재현 실측 (샘플 100건 대조)

| 축 | 재현 규칙 | 정확도 | 판정 |
|---|---|---|---|
| `axis_fundType` | `or_attr_desc` → `{MMF→MoneyMarketFund, 임대형·대출형→RealEstateFund, 특별자산→SpecialAssetsFund, 혼합자산→MixedAssetsFund, 그 외 전부→SecuritiesFund}` | **100/100** | 확정 |
| `axis_listingType` | `ksd_itm_no ∈ etf_kr.pd_itm_no` → `Listed`(전량 47종), 그 외 `Unlisted` | **100/100** | 확정. `fund_pub.ttl:70`의 "부분 재현" 표현은 과소평가 |
| `axis_investorEligibility` | `prvo_pbff_desc='사모'` → `PrivateOffering`, 그 외 `PublicOffering` | **100/100** | 확정 |
| `axis_classDifferentiation` | 종목명 클래스 접미(`종류X`/`ClassX`) 정규식 | 71/100 (mtco 그룹크기 규칙은 48/100) | **미해결** |
| `axis_issuanceType` | — (정답 99/100이 `AdditionalType`) | 다수결 99/100 | 신호 없음 |
| `axis_redemptionType` | `fd_set_pcd`·`or_attr_desc`·`ovrs_fd_desc`·`pfiv_sale_cntl_tcd`·`kofia_fd_ccd` 20자리 전수 스캔 | 최고 81.2% (다수결 baseline 78%) | **재현 불가 확정** — `fund_pub.ttl:62`의 판단이 샘플로 뒷받침됨 |

**`axis_fundType`이 5값 체계라는 점이 결정적이다.** ABox는 `fp:FundType_FundOfFunds` 3,017종 + `fp:FundType_Derivative` 683종 = **3,700종(33.2%)** 을 주최측 정답축에 없는 값으로 싣고 있다. 샘플에서 `재간접` 16건·`06` 9건은 **전부 `SecuritiesFund`** 로 라벨돼 있어, `fund_pub.ttl:58`의 "'06'은 파생형" 해석과 어긋난다.

### 1.2 공모펀드 ABox 적재 현황 (술어별 실측)

`instances_fund_pub.ttl` 술어 전수 census:

| 적재됨 (7 ObjectProperty + 4 Datatype) | 건수 | | 미적재 ObjectProperty (13) | 채울 원천 |
|---|---:|---|---|---|
| `fp:hasCurrency` | 11,138 | | `fp:hasShareClass` | `mtco_itm_no` (보유) |
| `fp:hasInvestmentRegion` | 11,130 | | `fp:hasListingType` | `ksd_itm_no` (보유, 47종) |
| `fp:hasFundType` | 11,115 | | `fp:hasClassDifferentiation` | 규칙 미확정(71%) |
| `fp:hasInvestorEligibility` | 11,115 | | `fp:hasRedemptionType` | **원천 없음** |
| `fp:hasRiskGrade` | 8,565 | | `fp:hasIssuanceType` | **원천 없음** |
| `fp:hasAssetType` | 7,422 | | `fp:managedBy` | `or_co_xtn_itt_cd` 68종 — **코드만, 명칭표 없음** |
| `fp:sameVehicleAs` | 47(단방향) | | `fp:hasCustodian` | `trusc_xtn_itt_cd` 19종 — 동상 |
| `fp:productCode`/`Name`/`ShortName` | 11,138 | | `fp:tracksIndex` | `bmrk_nm` 390종(결측 0%) — 지수 노드 미생성 |
| `fp:ksdCode` | 11,078 | | `fp:hasMetricSnapshot` | 순자산·수익률 (보유, **그래프에 0건**) |
| | | | `fp:hasHolding` | **미확보** |
| | | | `fp:hasRisk` / `fp:supportedBy` | **문서 0건** |
| | | | `fp:hasReplicationMethod` / `fp:relatedToTheme` | 원천 없음 |

미적재 DatatypeProperty 13개(`fund_pub.ttl` 선언 14개 중 `ksdCode` 외 전부): `standardItemCode`·`fssCode`·`managerItemCode`·`representativeKsdCode`·`kofiaClassCode`·`fundAttributeCode`·`currencyHedged`·`overseasScope`·`eligibleInvestorType`·`saleStatus`·`soldByFirm`·`benchmarkName`·`riskGradeLabel`.
→ **Q9가 요구하는 벤치마크·개인법인구분, Q19가 요구하는 판매여부·환헤지가 전부 그래프에 없다.** 현재 상태에서 공모펀드 질의는 SPARQL 단독으로 성립하지 않고 반드시 RDB를 거쳐야 한다.

### 1.3 기존 문서와 어긋난 실측값 (인용 시 주의)

| 문서 | 기재 | 실측 |
|---|---|---|
| `QUERY_COVERAGE_35.md:112` | 미래에셋코어테크 "동일 모펀드 **14클래스**" | **10클래스** (`mtco=0536840`, `rptt=031910536840` 양쪽 모두 10) |
| `ontology/common.ttl:360` | "한 모펀드에 14클래스", "클래스 중복 제거 안 하면 순자산 8.54배" | 10클래스 / **3.33배**(8.54배는 dedup 이전 원본 행 그레인 수치이며 클래스 축과 다른 층위) |
| `ontology/fund_pub.ttl:74` | `axis_classDifferentiation`은 `mtco_itm_no` 그룹 크기로 "재현 가능" | 주최측 샘플 대조 **48/100** — 반증 |
| `ontology/fund_pub.ttl:58` | `or_attr_desc='06'` → 파생형 | 주최측 라벨은 `SecuritiesFund` (9/9) |
| `ontology/fund_pub.ttl` 주석 | 그룹핑 "11,139종 → 4,661그룹" | 정규화 후 **4,580그룹**(원값 4,660) |

---

## 2. 기획 — 채워야 할 것

| ID | 항목 | 왜 필요한가 (문항번호·배점) | 산출물 | 선행조건 | 규모 |
|---|---|---|---|---|---|
| **FUND-P1** | **스냅샷 기준일 응답 규칙 확정** — 공모펀드 수치에 `as_of=2026-07-11`(주최측 스냅샷)을 근거로 붙이되, "데이터에 기준일 컬럼이 없어 스냅샷 일자를 기준일로 표기한다"는 문장을 `retrieved_context`에 고정 삽입 | Q8(하1)·Q9(중2)·Q10(중2)·Q19(중2)·Q20(상3) 전부가 "기준일을 붙여줘"를 `required_evidence`로 요구하고, 5문항의 '부분' 판정 사유가 **오직 기준일 부재** 하나다(`QUERY_COVERAGE_35.md:151-153,162-163`). **배점 10** | 응답 템플릿 문구 1종 + `config.py` 상수 `FUND_AS_OF` | 없음 | **S** |
| **FUND-P2** | **클래스 중복 제거 규칙 확정** — 랭킹·합산 질의는 `mtco_itm_no` 정규화(`strip('"')`+`zfill(7)`) 그룹 단위로 집계하고 대표 클래스 1건만 노출, 나머지는 "동일 모펀드 N클래스"로 요약 | Q10은 동일 모펀드 판정 자체가 질문(중2), Q19·Q20·Q30은 "클래스 중복 제거"가 `required_evidence` 명문. 미적용 시 **Q19 상위 15건이 모펀드 3종의 반복**이 되고 순자산이 3.33배 부풀려진다 | 규칙 문서 1절 + 대표 클래스 선정 기준(순자산 최대 → `itm_no` 최소) | 없음 | **S** |
| **FUND-P3** | **주최측 6분류축 대응표 확정** — §1.1의 재현 규칙을 정본으로 고정하고, `FundType_FundOfFunds`/`Derivative`를 주최측 5값 체계의 하위(`skos:broader`)로 재배치. 재현 불가 2축(`redemptionType`·`issuanceType`)은 **트리플 생성 금지 + ABSTAIN 사유** 로 명문화 | Q8이 "펀드 유형을 알려줘"를 직접 묻는다(하1). 현재 3,700종(33.2%)이 주최측 정답축에 없는 값으로 답변된다. 개방형/폐쇄형 조건검색이 들어오면 근거 없이 답할 위험 | 대응표 1장 + `fund_pub.ttl` 주석 정정안 | 없음 | **S** |
| **FUND-P4** | **근거문서 수집 범위 확정** — 공모펀드 문서 축을 "전량"이 아니라 **질의에 이름이 나온 펀드로 한정**. 실측상 Q25 국민성장펀드 1모펀드(4클래스), Q30 우리반도체BIG2플러스 1모펀드(2클래스), Q20 국내투자 반도체 펀드 **1모펀드**뿐이다 | Q25(상3)·Q30(상3)이 '불가'인 사유가 전부 문서. 전량 수집은 16일에 불가능하나 **대상 3모펀드**면 가능 | 수집 대상 목록(모펀드 ID·문서 유형·출처) | 없음 | **S** |
| **FUND-P5** | **미해소 식별자 처리 방침** — `fss_itm_no` sentinel 3,022종(27.1%), `or_co_xtn_itt_cd`/`trusc_xtn_itt_cd` 코드-명칭 미해소를 `unresolved` 플래그로 표기하고 근거 추정 금지 | `spec_0818.md` 4.4절의 "미해결 식별자는 공란 유지 + `unresolved` 플래그, ABSTAIN 근거로 사용"을 공모펀드 축에 적용. 운용사명을 종목명에서 추측하면 거짓 근거가 된다 | 방침 1절 | 없음 | **S** |

---

## 3. 데이터 — 채워야 할 것

| ID | 항목 | 현재 상태 | 취득 방법 | as_of 제약 | 규모 |
|---|---|---|---|---|---|
| **FUND-D1** | **분류축 파생 테이블** `data/enriched/fund_pub_axis.csv` — 11,138종 × `axis_fundType`·`axis_listingType`·`axis_investorEligibility` 3축(+`*_source`) | 미생성. 재현 규칙은 §1.1에서 100/100 검증 완료 | **외부 수집 불필요.** 보유 컬럼 매핑만. `script/build_fund_dedup.py` 옆에 `build_fund_axis.py` 신설 | 원본 스냅샷 승계(2026-07-11) | **S** |
| **FUND-D2** | **모펀드 그룹 테이블** `data/relations/fund_share_class.csv` — (`parent_group_id`, `itm_no`, `is_representative`, `class_label`, `source`) 11,138행 | 미생성. `mtco_itm_no` 보유, 정규화 후 4,580그룹 | 내부 파생. FUND-P2 규칙 적용 | 동상 | **S** |
| **FUND-D3** | **공모펀드 편입내역** `data/relations/fund_holding.csv` — FUND-P4가 확정한 **대상 3모펀드 한정** | **0행.** 마스터에 편입종목 컬럼 0개(`QUERY_COVERAGE_35.md:117`) | 자산운용보고서·투자설명서 '주식/채권 보유내역' 표를 정적 PDF로 1회 취득 → 파싱. 조인키는 `fss_itm_no`(대상 3종 모두 sentinel 아님을 확인) | **as_of ≤ 2026-07-11** 문서만. 발행일 초과분 폐기 | **M** |
| **FUND-D4** | **근거문서 코퍼스** `data/external/evidence_docs_recon/fund_pub/` — Q25 정책자료(국민성장펀드), Q30 위험요인(우리반도체BIG2플러스) | 디렉터리만 존재, **0바이트** | 정적 PDF 1회 취득 + 사이드카 `{source, as_of, retrieved_at, url}`(`EXTERNAL_DATA_PLAN.md:28`). `fp:documentTitle`·`documentPublisher`·`documentPublishedDate`·`documentQuote`(`common.ttl:617-642`)를 채울 수 있는 형태로 청킹 | **as_of ≤ 2026-07-11**. 실시간 크롤링·API 금지 | **M** |
| **FUND-D5** | **벤치마크 → 지수 노드 매핑** `data/relations/product_index.csv` 펀드 파트 — `bmrk_nm` 390종을 `fp:Index` 노드로 정규화 | 미생성(`DATA_LAYER_PLAN.md:92`의 "다음 후보"). `bmrk_nm` 결측 0%지만 복합 벤치마크(`A 50% + B 50%`)가 다수이고 국내ETF `cu_base_index`와의 교집합은 17종뿐(`fund_pub.ttl:229`) | 내부 파생 + `skos:altLabel` 별칭표. 복합 벤치마크는 구성 지수별 분해 + 가중치 보존 | 원본 승계 | **M** |
| **FUND-D6** | **운용사·수탁사 코드 명칭표** — `or_co_xtn_itt_cd` 68종 / `trusc_xtn_itt_cd` 19종 | **코드만 보유, 명칭 컬럼 없음.** `fp:managedBy`·`fp:hasCustodian`(`common.ttl:290,298`)를 채울 수 없는 유일한 사유 | 금투협/금감원 기관 대외코드표 정적 취득. 미확보 시 FUND-P5에 따라 `unresolved` 유지 | as_of ≤ 2026-07-11 | **S** |

---

## 4. 개발 — 채워야 할 것

| ID | 항목 | 대상 파일 | 선행조건 | 규모 |
|---|---|---|---|---|
| **FUND-E1** | **ABox 확충 — 무비용 구간.** 이미 CSV에 있는 값으로 미적재 DatatypeProperty 13개 중 질의에 쓰이는 6개(`saleStatus`·`currencyHedged`·`benchmarkName`·`eligibleInvestorType`·`overseasScope`·`managerItemCode`)와 ObjectProperty 2개(`hasListingType`·`hasShareClass`)를 생성 | `script/build_ontology_instances.py` (펀드 블록 332~424행) | FUND-D1·D2 | **M** |
| **FUND-E2** | **`fp:sameVehicleAs` 역방향 트리플 47건 추가** — ETF 노드에서도 탐색되게. `owl:SymmetricProperty` 선언은 있으나 pyoxigraph는 추론하지 않는다(`spec_0818.md` 4.2절) | `script/build_ontology_instances.py:371` | 없음 | **S** |
| **FUND-E3** | **`fp:FundType` 개체 정정** — `FundOfFunds`·`Derivative`를 주최측 5값 체계 하위로 재배치(`skos:broader fp:FundType_Securities`). 3,700종의 답변 유형값이 바뀐다 | `ontology/fund_pub.ttl:56-92`, `script/build_ontology_instances.py` | FUND-P3 | **S** |
| **FUND-E4** | **RDB 적재 + 클래스 dedup 뷰** — `fund_pub_dedup`·`fund_pub_axis`·`fund_share_class`를 DuckDB에 싣고, 랭킹/합산 질의 전용 뷰 `v_fund_parent`(모펀드 1행)를 만든다. 순자산 합산은 이 뷰로만 | `kb/build_rdb.py` (`AGENT_STRUCTURE_0821.md:21`) | FUND-D1·D2, FUND-P2 | **M** |
| **FUND-E5** | **스키마 인덱스에 `fund_pub.ttl` `rdfs:comment` 27건 포함 + 갭 메우기** — 신규 선언(FUND-E1·E3)에도 주석을 달아야 2단계 Schema Retrieval이 공모펀드 축을 찾는다(`spec_0818.md` 4.3절, 1-B) | `kb/build_schema_index.py`, `ontology/fund_pub.ttl` | FUND-E1·E3 | **S** |
| **FUND-E6** | **`retrieved_context`에 펀드 기준일·클래스 규칙 자동 삽입** — 5필드 응답 스키마(`spec_0818.md:294`)의 `retrieved_context`/`think_trace`에 FUND-P1 문구와 "모펀드 N클래스 중 대표 1건" 표기를 넣는다 | `agent/agent_core.py`(`to_response()`), `agent/nodes.py`(`answer`) | FUND-P1·P2 | **S** |
| **FUND-E7** | **검증 추가** — ① 공모펀드 술어 수가 기대치 미만이면 실패 ② `mtco` 그룹 내 순자산 합산 금지 회귀 테스트 ③ `axis_*` 재현 규칙을 주최측 샘플 100건으로 회귀 검증(정확도 100 미만이면 실패) | `script/validate_ontology.py` | FUND-E1·E4 | **S** |
| **FUND-E8** | **펀드 편입내역 ABox 적재** — `fp:Holding` n-ary 노드(`common.ttl:313-317`)로 FUND-D3 결과를 싣고 `fp:supportedBy`로 FUND-D4 문서에 연결 | `script/build_ontology_instances.py` | FUND-D3·D4 | **M** |
| **FUND-E9** | **`fp:tracksIndex` 적재** — FUND-D5 매핑으로 펀드↔지수 연결 | `script/build_ontology_instances.py` | FUND-D5 | **S** |

---

## 5. 우선순위

| 순위 | ID | 왜 이 순서인가 |
|---|---|---|
| **P0** | FUND-P1 → FUND-E6 | 5문항(8·9·10·19·20)의 '부분' 판정 사유가 **기준일 부재 단 하나**다. 코드 변경은 상수 1개 + 템플릿 문구 1줄이고 배점 10점이 걸려 있다. **투입 대비 회수가 이 문서에서 가장 높다** |
| **P0** | FUND-P2 → FUND-D2 → FUND-E4 | 미적용 시 Q19 상위 15건이 모펀드 3종의 반복이 되고 순자산이 3.33배 부풀려진다. Q10은 이 판정 자체가 질문이고, Q20·Q30은 "클래스 중복 제거"가 `required_evidence` 명문이다. **틀린 답을 내는 구간이라 감점 방향** |
| **P0** | FUND-P3 → FUND-D1 → FUND-E3 | 주최측이 정답 라벨을 줬는데 3,700종(33.2%)이 그 체계에 없는 값으로 답변된다. 재현 규칙은 이미 100/100 검증돼 있어 남은 건 적용뿐 |
| **P0** | FUND-E1 → FUND-E5 → FUND-E7 | ABox에 `saleStatus`가 없으면 "판매 중인 공모펀드"(Q19)를 그래프에서 못 거른다. E5 없이는 2단계 Schema Retrieval이 새 술어를 못 찾아 E1이 사장된다. E7은 위 셋이 회귀하지 않게 잠그는 최소 장치 |
| **P1** | FUND-E2 | 47건짜리 한 줄 수정. Q21은 이미 '가능'이지만 ETF 방향 질의에서 0건이 나오는 함정을 없앤다 |
| **P1** | FUND-P4 → FUND-D3 → FUND-E8 | Q30(상3)을 '불가 → 부분/가능'으로 올리는 유일한 경로. 대상이 **우리반도체BIG2플러스 1모펀드**로 좁혀지므로 16일 안에 손이 닿는다. 다만 PDF 파싱이라 실패 시 되돌릴 시간이 필요해 P0로 올리지 않는다 |
| **P1** | FUND-D4 | Q25(상3)는 **문서가 유일한 blocking**이며 데이터 축은 이미 실물 확인됐다(4클래스, `rptt=031910539500`, 순자산 200,025,120,841). 정책 보도자료 1~2건이면 성립 |
| **P1** | FUND-P5 → FUND-D6 | 운용사 코드-명칭표를 못 구하면 `unresolved` 유지가 정답이다. 방침(P5)이 먼저고 취득(D6)은 부수적 |
| **P2** | FUND-D5 → FUND-E9 | `bmrk_nm`은 결측 0%지만 공모펀드 관련 35문항 중 벤치마크를 요구하는 것은 Q9뿐이고, Q9는 원문 문자열 그대로 제시해도 `required_evidence`("벤치마크")를 충족한다. 지수 노드 정규화는 근거 강화용 |

**16일 배분 가정** — P0 4묶음(S·S·S·M 규모, 합계 약 4일) → P1 4묶음(약 5일) → 나머지는 3·4단계 통합·검증에 남긴다. P0를 다 못 끝내면 P1 이하를 전부 버린다.

---

## 6. 하지 않기로 한 것

| 항목 | 왜 안 하는가 |
|---|---|
| **`axis_redemptionType`(개방형/폐쇄형) 값 부여** | 주최측 정답 100건 대조 결과 `fd_set_pcd`·`or_attr_desc`·`ovrs_fd_desc`·`pfiv_sale_cntl_tcd`·`kofia_fd_ccd` 20자리 전수 스캔에서 최고 순도 81.2%로, 다수결 baseline 78%와 사실상 같다. **근사 매핑은 거짓 근거를 만든다**(`docs/DECISIONS_Ontology.md` 공통 판단 기준). 트리플을 만들지 않고 ABSTAIN 근거로 남긴다 |
| **`axis_issuanceType`(추가형/단위형) 값 부여** | 정답 샘플 100건 중 99건이 `AdditionalType` 단일값이라 어떤 규칙도 검증할 수 없다. KOFIA 코드 부여기준 문서는 `EXTERNAL_DATA_PLAN.md:59`에서 이미 P3(blocking 0) |
| **`axis_classDifferentiation` 트리플 적재** | 최선 규칙 71/100. 4건 중 1건이 틀리는 값을 근거로 제시할 수 없다. **단, FUND-D2의 모펀드 그룹 테이블은 만든다** — 그룹 정보 자체는 Q10·19·20·30에 필요하고, "이 그룹에 N클래스가 있다"는 사실 기술은 정확하다. 주최측 라벨과 다른 것은 단일/멀티 **판정 라벨**뿐이다 |
| **공모펀드 편입내역 전량 수집(11,138종 / 4,580모펀드)** | 자산운용보고서 PDF 파싱 4,580건은 16일에 불가능하다. Q20이 요구하는 "국내 반도체 공모펀드"는 실측상 **모펀드 1종**(우리반도체BIG2플러스, `mtco=0005F29`)뿐이고 나머지 7종은 글로벌 투자다. Q26(SK하이닉스 편입 펀드)은 대상이 특정되지 않아 전량 수집이 필요하므로 **'부분' 유지**하고 "공모펀드 편입내역 미보유"를 근거로 명시한다 |
| **`fd_set_pcd`·`kofia_fd_ccd`를 분류 필터축으로 사용** | `kofia_fd_ccd`는 자리별 의미가 역추정 가설이고 20자리 전량 `0`인 행이 2,879종 + 결측 11종 = 2,890종(**25.9%**)(`fund_pub.ttl:187`). 식별자로만 싣는다 |
| **운용사명을 종목명 접두에서 추정** | `미래에셋…`·`삼성…` 접두는 판매사·브랜드명이지 `or_co_xtn_itt_cd`가 가리키는 운용사 법인과 1:1이 아니다. 코드표 없이 붙이면 `fp:managedBy`에 거짓 근거가 실린다 |
| **`fp:MetricSnapshot` 노드로 펀드 수치를 그래프에 적재** | 순자산·수익률은 DuckDB가 전담한다(`spec_0818.md` 4.1절 — 숫자 필터·정렬·집계는 RDB). 기준일 컬럼이 아예 없어 `MetricSnapshot`의 존재 이유(값+기준일 묶기, `common.ttl:138`)가 성립하지 않는다. 100만 트리플 구간에서 60초 예산만 소모한다 |
| **`hdge_fd_yn`·`ofsfd_yn`·`frc_bpr_itm_yn`·`bmrk_eng_nm`·`itm_eng_nm`·`itm_eabrv_nm` 적재** | 상수·중복 컬럼(`ofsfd_yn` 고유값 1종, `itm_eabrv_nm` 결측 99.84%). `fund_pub.ttl:42-43`에서 이미 배제 결정 |
| **`fss_itm_no` sentinel 3,022종의 DART 재매칭 시도** | 원천이 sentinel(`'000000000000'`)이라 조회할 키 자체가 없다. 이름 매칭은 오매칭 위험이 크고, FUND-D3가 3모펀드로 좁혀져 있어 실익이 없다 |
