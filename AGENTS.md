# AGENTS.md

2026 미래에셋 AI Festival — **금융상품 Agent(Agentic RAG·QA)** 과제 저장소.
정형 금융상품 데이터를 온톨로지·지식그래프로 구조화하고, 근거에 기반해 답변하는 에이전트를 만든다.

작업 규칙(계획 위임·커밋 언어)은 `CLAUDE.md`를 따른다. 이 문서는 **프로젝트 사실**을 다룬다.

## 절대 규칙

1. **LLM은 HyperCLOVA X만 사용 가능.** 다른 모델을 쓰면 평가 대상에서 제외된다.
2. **데이터 기준일은 2026-07-11.** 외부 수집 데이터는 반드시 `as_of ≤ 2026-07-11`. 이후 시점이 섞이면 미래정보 유출(look-ahead)이다.
3. **주최측 데이터가 항상 우선.** 외부 데이터와 상충하면 주최측 값을 쓰고, 상충 사실을 evidence에 기록한다.
4. **근거 없는 답변 금지.** 데이터로 확인 불가한 질의는 "확인할 수 없음"으로 답해야 정답이다. 추측하면 감점된다.
5. **`data/csv/`는 동결.** 원본 변환본만 두고 값 수정·컬럼 추가·파생물 저장 모두 금지.

## 디렉터리

```
data/csv/        원본 xlsx → CSV 변환본 (동결)
data/enriched/   파생 테이블 (재그레인·스칼라 보강)
data/relations/  롱포맷 관계 테이블 (주어ID, 목적어, source, as_of)
data/external/   외부 수집 원천 + 사이드카 {원본파일명}.meta.json
ontology/*.ttl   제출 필수 — common + bond_kr/etf_kr/etf_gl/fund_pub
EDA/*.py         실행 스크립트 (build_/collect_/validate_)
EDA/src/*.py     jupytext 노트북 소스 전용
EDA/docs/*.md    문서
expected_question/  예상 평가 질문 35문항
```

`data/`는 gitignore 대상이다. **모든 데이터 산출물은 스크립트로 재생성 가능해야 한다.**

## 명령

```bash
python3 EDA/convert_xlsx_to_csv.py      # 원본 xlsx → data/csv (최초 1회)
python3 EDA/build_fund_dedup.py         # 펀드 롱포맷 → 1펀드 1행
python3 EDA/build_etf_enrichment.py     # LSEG 보강 + ETF↔테마 관계
python3 EDA/build_bond_enrichment.py    # 등급 서열·잔존만기·판매가능
python3 EDA/collect_etf_holdings.py     # 운용사 4사 편입종목 수집
python3 EDA/build_etf_holding.py        # → data/relations/etf_holding.csv
python3 EDA/build_data_inventory.py     # 데이터 구조 스냅샷 갱신
python3 EDA/validate_external.py        # as_of 기준일 가드 (실패 시 exit 1)
python3 EDA/validate_ontology.py        # TTL 파싱·domain/range·Q35 판정 검증
```

데이터 구조를 바꿨으면 `build_data_inventory.py`를 재실행해 `EDA/docs/DATA_INVENTORY.md`를 함께 커밋한다. 이 파일의 `git diff`가 변경 이력이다.

## 반드시 알아야 할 데이터 함정

집계나 필터를 작성하기 전에 이 목록을 확인하라. 전부 실측으로 확인된 것이며, 놓치면 조용히 오답이 된다.

| 함정 | 내용 | 대응 |
|---|---|---|
| **펀드 그레인** | 95,619행 = 11,139펀드. `(itm_no, prfd_attr_cd)`가 유일키라 펀드당 평균 8.6행 중복 | `fund_pub_dedup.csv` 사용. 미처리 시 순자산 **8.54배 과대** |
| **ETN 혼입** | 국내ETF 마스터에 ETN 532종(30.7%) | `pd_grp_no=='ETF'` 필터. ETN은 편입종목 개념 자체가 없음 |
| **괴리율 더미** | `du_diff_rt`·`du_chas_errt` 전 종목 `0.00` (결측 아닌 미계산) | 사용 금지. 필요하면 종가/NAV로 재계산하고 그 사실을 명시 |
| **실질 기준일 불일치** | 파일명은 07-11이나 채권은 2026-02-24, ETF는 06-15/16 | 근거 표시에 테이블별 실질 기준일을 쓴다 |
| **문자열 sentinel** | 해외ETF `cu_base_index` 겉보기 결측 0.14% → 실제 48.1%(`Index is not provided...` 등 문장형) | 명시적 NULL 처리 |
| **국채 무등급** | 국공채·개인투자용국채는 신용등급 100% 결측이나 **정상**(평가 대상 아님) | `UnratedByDesign`과 `RatingUnknown`을 구분. 등급 필터에서 제외하되 "미평가"로 표기 |
| **총보수 결측** | 국내ETF `cu_charge_rt` 81.9% 결측, 있는 값도 다수가 `0.0` 더미 | `etf_kr_enriched.csv`의 `charge_rt_final` 사용(LSEG `ter`로 91.4% 보완) |
| **깨진 행** | 공모펀드에 `itm_no='"'`인 1행이 CSV 파싱 붕괴로 값이 밀림 | 행 단위 배제. 컬럼별 예외처리 금지 |
| **엔티티 표기** | 발행사는 `에스케이하이닉스(주)`·`(주)엘지에너지솔루션` 형태. `SK하이닉스`로 검색하면 0건 | 정규화 후 매칭 |
| **룩어헤드 컬럼** | KODEX 현재가·등락, TIGER 등락률은 조회일과 무관하게 오늘 값 | 관계 테이블에 절대 넣지 않는다 |
| **생존편향** | 운용사 사이트는 상장폐지 종목을 제거해 과거 조회도 0행(24종) | "편입종목 미확보"로 명시. 조용히 빠지면 "편입 안 함" 오답 |

## 온톨로지

`fp:` = `http://mafest.ai/product#`. Turtle 형식, `@prefix rdfs:` 선언 필수.

설계 결정 4가지를 유지하라.

- **n-ary 패턴**: 편입 관계는 `fp:Holding` 중간 클래스(weight·asOf·supportedBy). 단순 property에 비중·기준일을 못 단다.
- **domain/range 엄격 선언**: `fp:issuedBy` domain은 `fp:Bond` 단독. "VOO가 발행한 회사채" 질의를 **도메인 위반으로 판정**하기 위한 것이다.
- **신용등급은 순서 있는 개체**: `fp:ratingRank` 1(AAA)~19(C). "AA- 이상" = `rank <= 4`, "AAAA" = **개체 부재**로 판정.
- **출처 애노테이션**: 모든 DatatypeProperty에 `fp:sourceTable`·`fp:sourceColumn`. 답변 evidence가 이를 인용한다.

보조/제외 등급 컬럼(괴리율 등)은 온톨로지에 올리지 않는다 — "값이 있다"는 잘못된 신호가 된다.

## 답변 생성 시

- 모든 수치에 **기준일과 출처 컬럼**을 붙인다. 관계에는 `as_of`와 근거 문서를 붙인다.
- 상품명은 **완전일치 우선**. `KODEX 200` 부분일치 14건, `KODEX AI로봇` 유사명 18건이 존재하므로 유사명 대체는 금지다.
- 답변불가 판정은 사유를 구분한다: 허용값 위반(AAAA) / 기준일 이후 출시 / 상품 부재 / 미래 실현값 / 도메인 위반.
- 응답 15초 이내가 평가 항목이다. 연산·필터는 RDB가 끝내고 LLM은 자연어 포장만 한다.

## 문서

| 문서 | 내용 |
|---|---|
| `EDA/docs/EDA_REPORT.md` | 4개 도메인 실측 분석, 답변 가능/불가 질의 |
| `EDA/docs/COLUMN_GUIDE.md` | 207컬럼 설명서 + 온톨로지 등급 + enum 값 |
| `EDA/docs/DATA_LAYER_PLAN.md` | 계층·파일명·출처 규칙의 **단일 기준** |
| `EDA/docs/EXTERNAL_DATA_PLAN.md` | 외부데이터 우선순위(35문항 blocking 기준) |
| `EDA/docs/QUERY_COVERAGE_35.md` | 35문항 커버리지 매트릭스 |
| `EDA/docs/HOLDINGS_COLLECTION_DESIGN.md` | 편입종목 수집 설계·운용사 비교 |
| `EDA/docs/DATA_INVENTORY.md` | 자동 생성. 직접 편집 금지 |
