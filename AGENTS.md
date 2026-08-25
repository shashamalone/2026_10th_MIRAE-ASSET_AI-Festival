# [AGENTS.md](http://AGENTS.md)

2026 미래에셋 AI Festival **금융상품 Agent(Agentic RAG·QA)** 과제 저장소.
정형 금융상품 데이터를 온톨로지·지식그래프로 구조화하고, 근거에 기반해 답변하는 에이전트를 만든다.

## 절대 규칙

1. **LLM은 HyperCLOVA X만 사용 가능.** 다른 모델을 쓰면 평가 대상에서 제외된다.
2. **현재 정본 release/cutoff는 2026-08-24.** 주최측이 2026-08-25 제공한
   `ai-festival2026_금융상품Agent_DtataSet260824`의 정상 XLSX 8개가 우선이며,
   외부 수집 데이터는 반드시 `as_of/published_at ≤ 2026-08-24`여야 한다.
3. **주최측 데이터가 항상 우선.** 외부 데이터와 상충하면 주최측 값을 쓰고, 상충 사실을 evidence에 기록한다.
4. **근거 없는 답변 금지.** 데이터로 확인 불가한 질의는 "확인할 수 없음"으로 답해야 정답이다. 추측하면 감점된다.
5. 주최측 XLSX 8개는 읽기 전용 정본이다. `__MACOSX/._*`는 제외한다.
   `../data/data`의 20260711 CSV·enriched·relations·external은 legacy 참고자료이며
   새 식별자·출처·cutoff 검증 없이 운영 DB에 직접 적재하지 않는다.
6. 어려운 작업은 상위 모델로 계획 먼저 진행한다, 아래에 해당하는 **복잡한 작업**은 코드를 수정하기 전에 `planner` 서브에이전트(Opus로 실행됨)에게 구현 계획을 먼저 받는다
  - 여러 파일에 걸친 기능 구현/리팩토링
  - 아키텍처·설계 결정이 필요한 작업
  - 요구사항이 모호하거나 접근 방식이 여러 개인 작업
  - 실패 시 되돌리기 어려운 작업 (스키마 변경, 대규모 이동/삭제 등)
  - planner가 반환한 계획을 사용자에게 요약해 보여준 뒤 실행한다. 계획과 다르게 진행해야 하면 이유를 말한다.
  - **단순 작업**(오타 수정, 한 파일 소규모 수정, 단순 질문)은 planner 없이 바로 처리한다 — 과한 위임 금지.
7. 실행 규칙

- 계획의 각 단계를 완료할 때마다 검증(테스트/실행 확인)을 한다.
- 계획에 없던 범위 확장(추가 리팩토링, 불필요한 추상화)을 하지 않는다.



## 디렉터리

[데이터 관리]

```
../data/ai-festival2026_금융상품Agent_DtataSet260824/  현재 주최측 XLSX 정본 8개
../data/data/    legacy 20260711 참고자료(운영 정본 아님)
data/enriched/   파생 테이블 (재그레인·스칼라 보강)
data/relations/  롱포맷 관계 테이블 (주어ID, 목적어, source, as_of)
data/external/   외부 수집 원천 + 사이드카 {원본파일명}.meta.json
ontology/*.ttl   제출 필수 — 스키마 5파일(common + 4도메인, 커밋) + instances_*.ttl 5파일(생성물, gitignore)
EDA/*.py         실행 스크립트 (build_/collect_/validate_)
EDA/src/*.py     jupytext 노트북 소스 전용
docs_raw/            EDA 산출 문서 (EDA_REPORT·COLUMN_GUIDE·QUERY_COVERAGE_35)
docs_data_layer/     데이터 계층 문서 (DATA_LAYER_PLAN·EXTERNAL_DATA_PLAN·EXTERNAL_DATA_SOURCES·DATA_INVENTORY)
docs_data_collection/ 수집 설계 문서 (HOLDINGS_COLLECTION_DESIGN)
expected_question/  예상 평가 질문 35문항
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
│   │   ├── rdb.py                  # sql(query) -> list[dict]              DuckDB
│   │   ├── graph.py                # sparql(query) -> list[dict]           pyoxigraph
│   │   ├── schema.py               # schema_search(...) -> list            pgvector (TBox)
│   │   ├── schema_context.py        # TBox → Physical/Business Context
│   │   ├── content.py              # content_search(...) -> list           콘텐츠 Vector 검색
│   │   └── validate.py             # TBox/domain/value 검증 → ABSTAIN
│   │
│   ├── kb/                         # 빌드 타임 코드
│   │   ├── build_rdb.py            # CSV/enriched/relations → DuckDB
│   │   ├── build_graph.py          # ontology/*.ttl → Oxigraph
│   │   ├── build_schema_index.py   # TBox comment → pgvector
│   │   ├── build_schema_catalog.py # RDB table/column/type/PK/FK catalog 생성
│   │   ├── build_content_index.py  # 서술형 데이터 → Content Vector Index
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
| **펀드 그레인**       | 260824 정본은 23,676행이며 `itm_no`가 유일키. 공모 14,716·사모 8,960을 모두 보존한다.             | 20260711의 `(itm_no, prfd_attr_cd)` dedup 규칙을 새 정본에 적용하지 않는다.       |
| **ETN 혼입**       | 국내 마스터에 ETF 1,235종과 ETN 545종, 해외 마스터에 ETF 5,972종과 ETN 65종이 함께 있다.          | `pd_grp_no`로 ETF/ETN을 명시 분리한다. ETN은 편입종목 미확보를 비보유로 해석하지 않는다. |
| **괴리율 더미**       | `du_diff_rt`·`du_chas_errt` 전 종목 `0.00` (결측 아닌 미계산)                             | 사용 금지. 필요하면 종가/NAV로 재계산하고 그 사실을 명시                                |
| **실질 기준일 불일치**   | release는 08-24지만 채권은 08-21, 국내ETF 지표는 08-21/분류는 최대 08-24, 해외ETF는 08-22, 펀드는 08-21이다. | 수치별 실제 날짜축을 evidence에 사용하고 release date로 대체하지 않는다.             |
| **문자열 sentinel** | 해외ETF `cu_base_index` 겉보기 결측 0.14% → 실제 48.1%(`Index is not provided...` 등 문장형) | 명시적 NULL 처리                                                       |
| **국채 무등급**       | 국공채·개인투자용국채는 신용등급 100% 결측이나 **정상**(평가 대상 아님)                                    | `UnratedByDesign`과 `RatingUnknown`을 구분. 등급 필터에서 제외하되 "미평가"로 표기    |
| **총보수 결측**       | 국내ETF `cu_charge_rt` 81.9% 결측, 있는 값도 다수가 `0.0` 더미                               | `etf_kr_enriched.csv`의 `charge_rt_final` 사용(LSEG `ter`로 91.4% 보완) |
| **legacy 깨진 파일** | `../data/data/csv`의 20260711 채권 CSV는 manifest SHA-256과 불일치한다.                         | legacy raw를 정본 또는 배포 입력으로 사용하지 않는다.                              |
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


| 문서                                                   | 내용                              |
| ---------------------------------------------------- | ------------------------------- |
| `docs_raw/EDA_REPORT.md`                             | 4개 도메인 실측 분석, 답변 가능/불가 질의       |
| `docs_raw/COLUMN_GUIDE.md`                           | 207컬럼 설명서 + 온톨로지 등급 + enum 값    |
| `docs_data_layer/DATA_LAYER_PLAN.md`                 | 계층·파일명·출처 규칙의 **단일 기준**         |
| `docs_data_layer/EXTERNAL_DATA_SOURCES.md`           | **데이터 소스 목록** — 출처·URL·용도·구성·제약 |
| `docs_data_layer/EXTERNAL_DATA_PLAN.md`              | 외부데이터 우선순위(35문항 blocking 기준)    |
| `docs_raw/QUERY_COVERAGE_35.md`                      | 35문항 커버리지 매트릭스                  |
| `docs_data_collection/HOLDINGS_COLLECTION_DESIGN.md` | 편입종목 수집 설계·운용사 비교               |
| `docs_data_layer/DATA_INVENTORY.md`                  | 자동 생성. 직접 편집 금지                 |

