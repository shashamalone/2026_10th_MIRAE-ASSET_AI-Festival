# WBS — 국내채권

> **현행 정정(2026-08-24):** 아래는 2026-08-21 시점의 계획 기록이다. RDB는 현재
> PostgreSQL 빌더로 대체됐다. 최신 구축 상태는 `../docs_data_layer/CURRENT_DATA_BUILD_STRUCTURE.md`를 따른다.

## 0. 한 줄 요약

채권은 4개 도메인 중 데이터가 가장 두껍다(42,394종, 원본 결측이 거의 없음). **주최측이 준 정답지 100건 대조 결과 적재된 5축 평균 89.5%**이고, 남은 일은 (a) 미배선 3축 적재, (b) 만기분류 파생 규칙 수정, (c) 채권 MVP에서 실측된 환각 차단이다. **`axis_collateralType`이 원본으로 재현 가능함이 실증되어 Q14의 '불가' 판정을 재검토해야 한다.**

---

## 1. 현재 상태 (실측 2026-08-21)

### 1-1. 코드리스트 축 — 주최측 정답지 100건 대조
근거: `python3 script/score_codelist_axes.py` / `data/csv/PRBD01N001_bond_kr_axis_sample_20260711.csv`

| 축 | 적재 | 정답 일치 | 남은 오류 |
|---|---:|---:|---|
| `axis_creditRating` | 100 | **100.0%** | — (최장 접두 규칙이 정확) |
| `axis_issuanceMarket` | 100 | 99.0% | `DomesticMarket→Market_Foreign` 1 |
| `axis_issuerType` | 100 | 98.0% | `SpecialBond→Corporate` 1, `MunicipalBond→Government` 1 |
| `axis_currency` | 99 | 96.0% | `KRW→Currency_USD` **4** |
| `axis_maturityClass` | 99 | **54.5%** | `MidTerm→Matured` 17, `MidTerm→ShortTerm` 12 |
| `axis_couponType` | 0 | — | **미배선** |
| `axis_collateralType` | 0 | — | **미배선** |
| `axis_issuerCategory` | 0 | — | **미배선** |

### 1-2. 미배선 3축의 재현 가능성 (실측)

| 축 | 정답 분포 | 원본으로 재현되나 |
|---|---|---|
| `axis_collateralType` | Unsecured 92 / Secured 6 / Guaranteed 1 / Subordinated 1 | **된다.** `bd_knd` 교차 결과 `유동화회사채`→Secured **6/6**, `일반특수법인채`→Guaranteed 1/1. Subordinated는 종목명 `(후)` 표기로 판별 가능(Q3 예시 `현대해상화재보험7(후)(콜/후)`) |
| `axis_couponType` | FixedCoupon 95 / Floating 2 / Zero 2 / Convertible 1 | **부분.** `SRFC_IRT=0`→Zero 2·Convertible 1, `>0`→Fixed 94·Floating 2. 단순 규칙(0→Zero, >0→Fixed)으로 96/100. Floating·Convertible은 종목명 파싱 필요 |
| `axis_issuerCategory` | Financial 52 / NonFinancial 43 / SubSovereign 2 / Sovereign 1 / SovereignAgency 1 / Other 1 | **미확인.** `pd_pbcm`(발행사명)·`std_pd_mcls_nm` 조합 검토 필요 |

### 1-3. 채권 MVP PoC (`script/test_bond_agent.py`)
| 항목 | 결과 |
|---|---|
| end-to-end 실행 | 4/4 통과, 3.9~8.9초 |
| 스키마 인덱스 | 130 resource × 1024차원 (`bond_kr.ttl` + `common.ttl`) |
| 검색 정확도 | "듀레이션"·"위험등급" 1위 적중. score floor 0.45로 노이즈 4건→0건 |
| **환각** | **4문항 중 2문항**에서 comment 밖 문장 생성 (예: `fp:duration` 주석은 "금리 민감도"까지인데 "금리 상승 시 가격 하락"까지 단정) |
| intent enum | 4건 중 2건이 `SCHEMA_SEARCH` 대신 `"용어 검색"` 등 자유 문자열 |

---

## 2. 기획 — 채워야 할 것

| ID | 항목 | 왜 필요한가 | 산출물 | 선행조건 | 규모 |
|---|---|---|---|---|---|
| BOND-P1 | **답변 근거 계약 확정** — 검색된 comment 밖 문장을 어디까지 허용할지 문장 단위 기준 | MVP 실측 환각 2/4. 대회 규칙상 "근거 없는 단정"은 **감점 직결**(과제설명 p7) | 판정 기준표 + 위반 예시 | — | S |
| BOND-P2 | **Q14 재판정** — '불가'(담보·보증 등급 조건검색) → '가능' 승격 검토 | §1-2 실측으로 `bd_knd` 재현 가능. 현재 불가 4문항 중 1건이 열린다 | `QUERY_COVERAGE_35.md` 갱신 | BOND-D1 | S |
| BOND-P3 | **만기 미상 319건 응답 규칙** | 만기일이 sentinel(`0`/`99991231`)이라 실제로 모르는 채권. "확인할 수 없음"을 근거와 함께 말해야 함 | 응답 템플릿 | D-결정(`Maturity_Unknown` 신설 여부) | S |
| BOND-P4 | **intent 스키마 강제 방식 결정** | 프롬프트만으론 enum이 안 지켜짐(2/4). structured outputs(HCX-007) vs 후처리 가드 | 결정 기록 | — | S |
| BOND-P5 | **채권 답변 근거 필드 매핑** — `retrieved_context`에 무엇을 넣을지 | 주최측 응답 5필드 고정. 상품번호·기준일·사용 컬럼이 필수 근거(35문항 `required_evidence`) | 필드 매핑표 | — | S |

---

## 3. 데이터 — 채워야 할 것

| ID | 항목 | 현재 상태 | 취득 방법 | as_of 제약 | 규모 |
|---|---|---|---|---|---|
| BOND-D1 | `hasCollateralType` 적재 | 0건 | `bd_knd` 규칙(`유동화회사채`→Secured, `일반특수법인채`→Guaranteed) + 종목명 `(후)`→Subordinated. **정답지 100건으로 검증** | 내부 파생 | S |
| BOND-D2 | `hasCouponType` 적재 | 0건 | `SRFC_IRT=0`→Zero, `>0`→Fixed 기본. 종목명에서 Floating/Convertible 추출 | 내부 파생 | S |
| BOND-D3 | `hasIssuerCategory` 적재 | 0건 | `pd_pbcm`·`std_pd_mcls_nm` 조합 규칙 역산 | 내부 파생 | M |
| BOND-D4 | **`maturity_bucket` 파생 규칙 수정** | 정답 일치 **54.5%** | `build_bond_enrichment.py`의 잔존만기 계산이 주최측과 불일치. `MidTerm`이 `Matured`(17)·`ShortTerm`(12)로 흘러감 — 기준일 처리 재검토 | 내부 파생 | M |
| BOND-D5 | `axis_currency` 오류 4건 조사 | 96.0% | `KRW`가 `Currency_USD`로 적재된 4건. 원본 확인 | 내부 파생 | S |
| BOND-D6 | `IssuerType_Municipal` 채우기 | 0건 | 지방채가 대분류에선 전부 `국공채`. 소분류(지역개발 1,266 / 도시철도 240 / 공모지방채 125)를 `sourceColumn`에 추가 | 내부 파생 | S |
| BOND-D7 | 채권 RDB(DuckDB) 적재 | 미착수 | `data/csv` 원본 + `bond_kr_enriched` 2테이블 | 내부 파생 | S |

---

## 4. 개발 — 채워야 할 것

| ID | 항목 | 대상 파일 | 선행조건 | 규모 |
|---|---|---|---|---|
| BOND-E1 | **답변 검증 노드** — 생성 문장이 comment에 근거하는지 대조 후 미근거 문장 제거 | `src/agent/nodes.py` (신규 노드) | BOND-P1 | M |
| BOND-E2 | intent enum 가드 — 후처리로 허용값 밖이면 보정 | `src/agent/nodes.py` | BOND-P4 | S |
| BOND-E3 | 미배선 3축 빌더 배선 | `script/build_ontology_instances.py` | BOND-D1~D3 | S |
| BOND-E4 | **채권 RDB 질의 함수** `sql()` | `src/kb/build_rdb.py` (신규) | BOND-D7 | M |
| BOND-E5 | **정답지 회귀 게이트 상시화** — `score_codelist_axes.py`를 CI 성격으로 | `script/score_codelist_axes.py` (존재) | — | S |
| BOND-E6 | score floor 튜닝 — 현재 0.45 고정값 | `src/config.py` | 골든셋 | S |

---

## 5. 우선순위

| 순위 | ID | 왜 이 순서인가 |
|---|---|---|
| **P0** | BOND-P1 → BOND-E1 | 환각은 **감점 직결**이고 이미 실측됐다(2/4). 다른 무엇을 고쳐도 이게 남으면 점수를 잃는다 |
| **P0** | BOND-D4 | 만기분류 54.5%는 **틀린 답을 자신 있게 내는** 상태다. 미배선(0%)보다 나쁘다 |
| **P0** | BOND-E5 | 정답지 회귀 게이트. 이게 없으면 아래 작업들이 개선인지 퇴행인지 모른다 |
| P1 | BOND-D1 → BOND-P2 | Q14 불가 → 가능 승격. 재현 가능성이 실증됐고 규모 S다 |
| P1 | BOND-D2, D5, D6 | 전부 S. 정답지로 즉시 검증 가능 |
| P1 | BOND-D7 → BOND-E4 | 유형1(RDB 단독) 14문항 중 채권이 다수. 2단계 스코프 |
| P1 | BOND-P4 → BOND-E2 | intent 불안정은 라우팅 오류로 번진다 |
| P2 | BOND-D3 | `issuerCategory` 재현 규칙 미확인. 요구 문항이 적다 |
| P2 | BOND-P3, BOND-E6 | 소규모·후순위 |
| P2 | BOND-P5 | 4단계(Answer Generator) 소관 |

---

## 6. 하지 않기로 한 것

| 항목 | 왜 안 하는가 |
|---|---|
| `RatingBand`·`MaturityClass`·`LeverageType`에 수치 서열값 부여 | 원본에 이미 숫자가 있다(`crd_grd_rank`·`remaining_days`·`cu_lev_fector`). `DATA_LAYER_PLAN.md` 규칙대로 **정렬은 RDB가 한다** |
| 채권 근거 문서(투자설명서) 수집 | 채권 문항에서 문서를 요구하는 건 소수. ETF·펀드 축의 blocking(8문항)이 더 크다 |
| SHACL 검증 도입 | `pyshacl` 신규 의존성이고 139만 트리플에서 느리다. 검증 항목이 소수라 **SPARQL ASK**로 충분 |
| 채권 편입종목·발행사 관계 확장 | 채권은 발행사 1:1이라 다단계 관계 탐색 대상이 아니다. 그 축은 `WBS_EQUITY.md` 소관 |
| `Rating_*` 19개체에 한글 altLabel 추가 | 등급 기호(`AAA`·`BBB-`)라 한글 표층형이 불필요하다. 정답 대조 100% |

---

## 참고 — 확인 명령

```bash
python3 script/build_ontology_instances.py    # 적재 + 미매핑 원장
python3 script/validate_ontology.py ; echo $?  # domain/range 위반 (파이프 금지)
python3 script/score_codelist_axes.py          # 주최측 정답지 대조
python3 src/kb/build_bond_index.py                 # 채권 스키마 벡터 인덱스
python3 script/test_bond_agent.py              # 채권 MVP end-to-end
```
