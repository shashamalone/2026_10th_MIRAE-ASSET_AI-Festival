# AGENTS.md

## 프로젝트 개요

2026 미래에셋 AI Festival 금융상품 Agent(Agentic RAG·QA) 과제 저장소다. 정형 금융상품 데이터를 온톨로지·지식그래프로 구조화하고, 근거에 기반해 답변하는 에이전트를 만든다.

## 빠른 실행 명령

의존성 설치:

```bash
pip install -r requirements.txt
```

스키마 카탈로그 점검:

```bash
python src/kb/build_schema_catalog.py --check
```

RDB vertical-slice 테스트:

```bash
python script/test_rdb_vertical_slice.py
python script/test_rdb_vertical_slice.py --db
```

온톨로지 검증:

```bash
python script/validate_ontology.py
python script/validate_external.py
```

## 에이전트 역할

에이전트는 이 저장소의 금융상품 데이터·온톨로지·메타데이터를 우선 사용하고, 검색된 Evidence에 근거해 구현·검증한다. 확인되지 않은 값은 추측하지 않으며, 복잡한 작업은 코드 수정 전에 구현 계획을 작성하고 사용자에게 요약한 뒤 진행한다.

## 작업 및 검증 규칙

- 변경 전 관련 문서, 데이터 스키마, 기존 테스트를 먼저 확인한다.
- 계획이 필요한 작업은 여러 파일 기능 구현·리팩토링, 아키텍처 결정, 스키마 변경, 대규모 이동·삭제다. 오타나 한 파일의 소규모 수정은 별도 계획 없이 처리한다.
- 계획의 각 단계를 끝낼 때마다 해당 테스트나 실행 확인을 수행한다.
- 계획 밖의 리팩토링·추상화·범위 확장을 하지 않는다.
- `__init__.py`는 만들지 않는다. Python namespace package 구조를 유지한다.

## 코드 스타일

- Python 기존 모듈 구조와 명명 규칙을 따른다.
- 실행·빌드 로직은 `src/`, 데이터는 `data/`, 스크립트는 `script/`, 문서·실험 기록은 `docs/`에 둔다.
- 식별자 정규화는 `src/kb/ids.py`의 단일 구현을 사용한다.
- 새 기능은 관련 테스트를 추가하고 실행한다.

## 테스트 지침

- 변경과 관련된 테스트를 반드시 실행한다.
- 데이터 계층을 건드린 경우 스키마 카탈로그와 RDB vertical slice를 우선 실행한다.
- 온톨로지나 외부 데이터를 변경한 경우 `validate_ontology.py`와 `validate_external.py`를 실행한다.
- 테스트 결과와 실행하지 못한 검증이 있으면 최종 보고에 명시한다.

## 변경·커밋 지침

- `data/csv/`는 동결 영역이다. 값 수정, 컬럼 추가, 파생물 저장을 금지한다.
- 재생성 가능한 산출물은 `artifacts/`에 두며 제출용 스키마와 생성물의 커밋 규칙을 유지한다.
- 커밋 메시지는 Conventional Commits 형식(예: `feat:`, `fix:`, `docs:`, `test:`)을 따른다.
- PR에는 변경 목적, 영향 범위, 실행한 검증 명령과 결과를 적는다.

## 절대 규칙

1. **LLM은 HyperCLOVA X만 사용 가능.** 다른 모델을 쓰면 평가 대상에서 제외된다.
2. **데이터 기준일은 2026-08-24.** 외부 수집 데이터는 반드시 `as_of ≤ 2026-08-24`. 이후 시점이 섞이면 미래정보 유출(look-ahead)이다.
3. **주최측 데이터가 항상 우선.** 외부 데이터와 상충하면 주최측 값을 쓰고, 상충 사실을 evidence에 기록한다.
4. **근거 없는 답변 금지.** 데이터로 확인 불가한 질의는 "확인할 수 없음"으로 답해야 정답이다. 추측하면 감점된다.
5. `data/csv/`는 동결된 원본 변환본만 두며 값 수정·컬럼 추가·파생물 저장을 금지한다.

## 디렉터리

[데이터 관리]

```
data/csv/        원본 xlsx → CSV 변환본 (동결)
data/enriched/   파생 테이블 (재그레인·스칼라 보강)
data/relations/  롱포맷 관계 테이블 (주어ID, 목적어, source, as_of)
data/external/   외부 수집 원천 + 사이드카 {원본파일명}.meta.json
ontology/*.ttl   제출 필수 — 스키마 5파일(common + 4도메인, 커밋) + instances_*.ttl 5파일(생성물, gitignore)
script/*.py      실행 스크립트 (build_/collect_/validate_/test_)
EDA/src/*.py     jupytext 노트북 소스 전용
docs/docs_data_layer/      데이터 계층 문서
docs/docs_data_collection/ 수집 설계 문서
expected_qa/        예상 평가 질문·정답 35문항 단일 정본
```



[에이전트 관리]

```
repo/
├── src/                            # 핵심 애플리케이션 코드
│   │
│   ├── agent/                      # LangGraph — 상태·노드·그래프
│   │   ├── agent_core.py           # StateGraph 조립·compile, run(question), to_response()
│   │   ├── nodes.py                # Agent 노드 함수. Tool은 tools/에서 import
│   │   └── state.py                # State TypedDict + ABSTAIN 코드
│   │
│   ├── tools/                      # 런타임 Tool / Engine
│   │   ├── rdb.py                  # LogicalPlan -> evidence rows          PostgreSQL
│   │   ├── graph.py                # [미구현 목표] sparql(...)             pyoxigraph
│   │   ├── bond_schema.py          # schema_search(...)                    pgvector (TBox)
│   │   ├── schema_context.py        # TBox → Physical/Business Context
│   │   ├── content.py              # [미구현 목표] 콘텐츠 Vector 검색
│   │   └── validate.py             # TBox/domain/value 검증 → ABSTAIN
│   │
│   ├── kb/                         # 빌드 타임 코드
│   │   ├── build_rdb.py            # CSV/enriched/relations → PostgreSQL
│   │   ├── build_graph.py          # [미구현 목표] ontology/*.ttl → Oxigraph
│   │   ├── build_bond_index.py     # TBox comment → pgvector
│   │   ├── build_schema_catalog.py # RDB table/column/type/PK/FK catalog 생성
│   │   ├── build_content_index.py  # [미구현 목표] Content Vector Index
│   │   └── ids.py                  # 식별자 정규화 단일 구현
│   │
│   ├── api.py                      # FastAPI 진입점
│   ├── config.py                   # 경로·DB·모델·k·시간예산 상수
│   └── clova.py                    # HyperCLOVA X client
│
├── data/                           # 원천/가공 데이터
│   ├── csv/
│   ├── enriched/
│   └── relations/
│
├── ontology/                       # TBox / ABox TTL
│   ├── bond.ttl
│   └── ...
│
├── metadata/                       # Semantic Schema Context 관련 정적 메타데이터
│   ├── business_rules.json         # filter/join/unit/value 규칙
│   └── schema_bindings.json        # 검증된 logical ↔ physical mapping
│
├── artifacts/                      # 재생성 가능한 빌드 산출물 (gitignore)
│   ├── oxigraph/
│   └── ...
│
├── script/                         # 실행·평가·운영 스크립트
│   ├── test_agent.py
│   └── ...
│
├── vectordb_test/                  # pgvector/검색 실험 및 과거 baseline
│   └── ...
│
├── docs/                           # 명세·실험 보고서
│   └── ...
│
├── requirements.txt
├── .env
└── README.md
```

`__init__.py`는 만들지 않는다 (namespace package로 충분)
src/       = 실행·빌드 로직
data/      = 실제 데이터
ontology/  = 의미 모델
metadata/  = 의미 ↔ 물리 스키마 연결정보
artifacts/ = 빌드 결과
script/    = 실행/검증
docs/      = 명세/실험 기록

## 반드시 알아야 할 데이터 함정

집계나 필터를 작성하기 전에 이 목록을 확인하라. 전부 실측으로 확인된 것이며, 놓치면 조용히 오답이 된다.


| 함정               | 내용                                                                              | 대응                                                                |
| ---------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **펀드 그레인**       | 08-24 배포본 23,676행 = 23,676펀드. `itm_no`가 단독 유일키이고 `prfd_attr_cds`는 원천에 이미 집약됨    | `raw.fund_pub_master` 직접 사용. 07-11용 `fund_pub_dedup.csv`는 사용 금지   |
| **ETN 혼입**       | 국내ETF 마스터에 ETN 545종(30.6%)                                                      | `pd_grp_no=='ETF'` 필터. ETN은 편입종목 개념 자체가 없음                        |
| **괴리율 더미**       | `du_diff_rt`·`du_chas_errt` 전 종목 `0.00` (결측 아닌 미계산)                             | 사용 금지. 필요하면 종가/NAV로 재계산하고 그 사실을 명시                                |
| **실질 기준일 불일치**   | 배포일은 08-24이나 채권·ETF·펀드 주요 수치의 실질 기준일은 2026-08-21                                | 근거 표시에 테이블·행별 실질 기준일을 쓴다                                          |
| **문자열 sentinel** | 해외ETF `cu_base_index` 겉보기 결측 0.14% → 실제 48.1%(`Index is not provided...` 등 문장형) | 명시적 NULL 처리                                                       |
| **국채 무등급**       | 국공채·개인투자용국채는 신용등급 100% 결측이나 **정상**(평가 대상 아님)                                    | `UnratedByDesign`과 `RatingUnknown`을 구분. 등급 필터에서 제외하되 "미평가"로 표기    |
| **총보수 결측**       | 국내ETF `cu_charge_rt` 81.9% 결측, 있는 값도 다수가 `0.0` 더미                               | `etf_kr_enriched.csv`의 `charge_rt_final` 사용(LSEG `ter`로 91.4% 보완) |
| **채권 복합키**       | 08-24 배포본은 `pd_no` 단독 중복이 있음                                                    | `(pd_no,pd_exg_mkt,info_seq)`를 행 유일키와 enriched join key로 사용       |
| **엔티티 표기**       | 발행사는 `에스케이하이닉스(주)`·`(주)엘지에너지솔루션` 형태. `SK하이닉스`로 검색하면 0건                          | 정규화 후 매칭                                                          |
| **룩어헤드 컬럼**      | KODEX 현재가·등락, TIGER 등락률은 조회일과 무관하게 오늘 값                                         | 관계 테이블에 절대 넣지 않는다                                                 |
| **생존편향**         | 운용사 사이트는 상장폐지 종목을 제거해 과거 조회도 0행(25종)                                            | "편입종목 미확보"로 명시. 조용히 빠지면 "편입 안 함" 오답                               |


## 온톨로지

`fp:` = `http://mafest.ai/product#`. Turtle 형식, `@prefix rdfs:` 선언 필수.

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


| 문서                                                        | 내용                              |
| --------------------------------------------------------- | ------------------------------- |
| `EDA/EDA_REPORT.md`                                       | 4개 도메인 실측 분석, 답변 가능/불가 질의       |
| `docs/docs_data_layer/COLUMN_GUIDE.md`                    | 207컬럼 설명서 + 온톨로지 등급 + enum 값    |
| `docs/docs_data_layer/DATA_LAYER_PLAN.md`                 | 계층·파일명·출처 규칙의 **단일 기준**         |
| `docs/docs_data_collection/EXTERNAL_DATA_SOURCES.md`      | **데이터 소스 목록** — 출처·URL·용도·구성·제약 |
| `docs/docs_data_collection/EXTERNAL_DATA_PLAN.md`         | 외부데이터 우선순위(35문항 blocking 기준)    |
| `docs/QUERY_COVERAGE_35.md`                               | 35문항 커버리지 매트릭스                  |
| `docs/docs_data_collection/HOLDINGS_COLLECTION_DESIGN.md` | 편입종목 수집 설계·운용사 비교               |
| `docs/docs_data_layer/DATA_INVENTORY.md`                  | 자동 생성. 직접 편집 금지                 |


### Agent의 4대 필수 구성요소

1. **정형·비정형 데이터 분석 &amp; 정제 — 상품 도메인 특화 Ontology**
  - [Parsing] PDF, PPT 등 데이터를 Markdown으로 변환
  - [Ontology] 데이터를 종합하여 상품별 LLM 가이드라인(온톨로지) 제작
2. **금융상품 KnowledgeBase — RDB + Vector + Graph**
  - [Extraction] 정제된 데이터를 바탕으로 지식 추출
  - [EntityResolution] 불필요·모호한 데이터의 판별 및 정리
3. **Intent Analysis &amp; Retrieval Engine — 질의 의도 분석과 검색 엔진**
  - [NL2SQL] 자연어 입력을 분석해 질의어(SQL)로 변환
  - [Retrieval] 우선순위·탐색 순서를 효과적으로 조정
4. **Answer Generator — 근거 기반 답변 생성**
  - [근거기반] 검색된 Evidence를 기반으로 정확한 답변 생성
  - [환각 방지] 데이터에 없는 내용은 추측하지 않음

