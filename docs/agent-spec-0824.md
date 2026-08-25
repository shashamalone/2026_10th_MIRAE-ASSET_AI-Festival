# 에이전트 파일 구조 (LangGraph) — 현행 v3 · 2026-08-25

> **현행 기준:** RDB는 PostgreSQL이다. Graph는 TBox/ABox TTL 생성·검증까지만
> 완료됐고 pyoxigraph loader/runtime은 목표 구조다. Action 3 A/B/C는 모두 운영
> 기준에 실패했고, 현재 검증된 범위는 저장 Query Frame 이후의 RDB-only 14문항
> vertical slice다. 데이터 구축 현행은
> `docs/docs_data_layer/CURRENT_DATA_BUILD_STRUCTURE.md`를 우선한다.

 `TBox Vector Grounding → Semantic Schema Context → Plan & Routing` 구조

## 0. v1 → v3 주요 변경


| 변경            | v1            | v3                                                    |
| ------------- | ------------- | ----------------------------------------------------- |
| Schema Vector | FAISS         | **PostgreSQL + pgvector**                             |
| Vector 대상     | TBox + 확장 검토  | **comment가 풍부한 TBox 중심**                              |
| 코드리스트 91건     | Vector 포함 검토  | **Schema Vector에서 제외**                                |
| 2단계 출력        | `schema_hits` | TBox 의미 후보. 현행 RDB slice에서는 아직 호출하지 않음              |
| 2→3단계         | 바로 Planner    | **2.5단계 필요성 확인. 최소 verified context 계약은 Action 4에서 검증** |
| RDB Schema 연결 | Planner 판단    | **Planner가 물리 schema를 만들지 않고 binding ID를 executor가 해소**   |
| Planner 역할    | DB 구조까지 추론 가능 | 현행 RDB slice는 LLM Planner 없이 결정적 LogicalPlan을 사용             |
| Action 3      | 실험 전 상태       | **A/B/C 완료. 어느 조건도 운영 채택하지 않음**                        |
| RDB slice    | 없음            | 저장 Frame 이후 DB exact 14/14, evidence 14/14, hallucination 0       |
| Live 상태      | 없음            | stability 7/70(10%), latency qualification 8/14. 운영 SLA 미달        |


221 혼합 인덱스 실험에서 기존 TBox 용어끼리의 Top-1 역전은 0건이었지만, 신규 코드값이 상위 슬롯을 점유하면서 Top-5 comment 근거 커버리지가 100%→68.6%로 감소했다. 따라서 Schema Vector는 TBox 의미 grounding에 집중한다.

---

# 1. 현행·목표 트리 구조

```text
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
│   │   ├── schema_context.py        # Query Frame → verified RDB context
│   │   ├── content.py              # [미구현 목표] 콘텐츠 Vector 검색
│   │   └── validate.py             # TBox/domain/value 검증 → ABSTAIN
│   │
│   ├── kb/                         # 빌드 타임 코드
│   │   ├── build_rdb.py            # CSV/enriched/relations → PostgreSQL
│   │   ├── build_graph.py          # [미구현 목표] ontology/*.ttl → Oxigraph
│   │   ├── build_bond_index.py     # TBox comment → pgvector
│   │   ├── build_schema_catalog.py # RDB table/column/type/PK/FK catalog 생성
│   │   ├── build_content_index.py  # [미구현 목표] Content Vector Index
│   │   └── ids.py                  # [미구현 목표] 식별자 정규화 단일 구현
│   │
│   ├── api.py                      # [미구현 목표] FastAPI 진입점
│   ├── config.py                   # 경로·DB·모델·k·시간예산 상수
│   └── clova.py                    # HyperCLOVA X client
│
├── data/                           # 원천/가공 데이터
│   ├── csv/
│   ├── enriched/
│   └── relations/
│
├── ontology/                       # TBox / ABox TTL
│   ├── bond_kr.ttl
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
│   ├── test_rdb_vertical_slice.py
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

`__init__.py`는 만들지 않는다.

```
src/       = 실행·빌드 로직
data/      = 실제 데이터
ontology/  = 의미 모델
metadata/  = 의미 ↔ 물리 스키마 연결정보
artifacts/ = 빌드 결과
script/    = 실행/검증
docs/      = 명세/실험 기록
```

### 주의

루트에 아래 이름을 만들지 않는다.

```text
langgraph/
langgraph.py
graph.py
```

pip package `langgraph`와 충돌하기 때문이다.

`src/tools/graph.py`는 `tools.graph`이므로 사용 가능하다.

---

# 2. 현재 구현 범위 — RDB-only vertical slice

현행 LangGraph는 채권 설명용 Vector MVP가 아니라 4개 도메인의 RDB-only 14문항을
실행하는 vertical slice다.

```text
HCX-007 Query Frame 1회
→ schema_context 결정적 grounding
→ validation
→ binding ID 기반 LogicalPlan
→ 제한된 PostgreSQL SELECT
→ evidence 검증
→ 결정적 답변 렌더링
```

- 대상: `q001`, `q002`, `q003`, `q005`~`q013`, `q017`, `q018`
- 데이터: PostgreSQL 12테이블, binding 74개, verified JOIN 2개
- 저장 Query Frame 이후: DB Gold exact 14/14, evidence 14/14, schema hallucination 0
- 현행 LangGraph는 `bond_schema.py`의 TBox Vector Search를 호출하지 않는다.
- Graph/Content engine, multi-engine Planner, FastAPI는 아직 구현하지 않았다.
- 근거: `vectordb_test/6_rdb_vertical_slice/6_1_result_rdb_vertical_slice.md`

Schema Vector의 검색 대상은 계속 다음으로 제한한다.

```text
rdfs:comment가 있는 TBox concept/property
```

AAA·AA-·미국·주식 같은 코드값 91개는 Schema Vector에서 제외하고 RDB value 또는
TBox taxonomy 검증 대상으로 다룬다. FAISS 산출물과 `faiss-cpu`는 pgvector 이전과
함께 제거됐다.

---

# 3. 전체 Agent 파이프라인

## 1단계 — Query Understanding

HCX-007 1회로 질문을 Semantic Query Frame v1의 14필드로 분해한다. 별도 audit
LLM은 현행 RDB slice에서 사용하지 않는다.

```text
사용자 질문
        ↓
대상
조건
행위
정렬
수치조건
엔티티
```

예:

```text
"AA- 이상이면서 잔존기간 3년 이하인 회사채를
매수수익률 순으로 보여줘"
```

↓

```json
{
  "domain_candidates": ["bond_kr"],
  "task": "filter_rank",
  "requested_fields": [{"text": "상품명"}, {"text": "매수수익률"}],
  "entities": [],
  "constraints": [
    {"field_text": "신용등급", "operator": ">=", "value_text": "AA-"},
    {"field_text": "잔존기간", "operator": "<=", "value_num": 3, "unit": "년"}
  ],
  "ordering": [{"field_text": "매수수익률", "direction": "desc"}],
  "limit": 10,
  "temporal": {"mode": "latest_snapshot"},
  "validation_targets": []
}
```

Query Frame은 의미 후보이며 schema 권위가 아니다. timeout/error면 빈 Frame에 오류를
기록하고 `ABSTAIN_UNRESOLVED_QUERY`로 DB 실행을 중단한다. 저장 Frame은 downstream
14문항 검증에 충분했지만 live stability strict success는 7/70(10%)였다. 후속 단일변수
실험의 qualification은 8/14였고, 최종 실패 6건은 HTTP 429 5건과 q006 entity 실패
1건이었다. HTTP 200 정상 응답 9건은 모두 5초 이내였으므로 HCX가 항상 5초보다
느리다고 결론 내리지 않는다. rate limit/cooldown 재검증과 q006 분석은 Action 4와
분리한 upstream 작업이다. 근거는
`vectordb_test/6_rdb_vertical_slice/6_2_result_query_frame_latency.md`를 따른다.

---

# 4. 2단계 — TBox Ontology Grounding

목적:

> **사용자의 표현을 데이터가 측정할 수 있는 논리 개념으로 번역**

pgvector에는 TBox의 설명이 풍부한 concept/property를 저장한다.

예:

```text
"신용도가 높은"
        ↓
fp:CreditRating
fp:ratingRank

"3년 이하 남은"
        ↓
fp:remainingDays

"수익률 높은 순"
        ↓
fp:buyYield
```

검색 결과:

```json
{
  "schema_hits": [
    {
      "term_uri": "fp:ratingRank",
      "label": "신용등급 서열",
      "comment": "신용등급 간 우열을 비교하기 위한 서열값",
      "score": 0.62
    },
    {
      "term_uri": "fp:remainingDays",
      "label": "잔존일수",
      "comment": "기준일에서 만기일까지 남은 일수",
      "score": 0.59
    }
  ]
}
```

### 목표와 현행의 차이

위 `Query Understanding → TBox Vector Grounding → 2.5단계`는 목표 경로다. 현행
RDB slice의 `schema_context.ground()`는 `schema_hits`나 TBox comment를 입력받지
않는다. 질문·Query Frame의 field text를 74개 RDB binding alias에 직접 대조한 뒤,
선택된 binding의 `concept_uri`를 사후 수집한다.

따라서 현재 검증 완료 범위는 다음뿐이다.

```text
저장 Query Frame
→ RDB binding/LogicalPlan
→ PostgreSQL 실행
```

TBox Vector URI를 입력으로 받아 RDB/Graph/Vector source를 해소하는 전체 2→2.5
경로는 Action 4의 검증 대상이다.

### 검색 정책

```text
Vector Search = 주 검색

Top-3 후보 전달

RRF = 기본 경로 제외

FTS = 필요 시 정확 용어 보조

0.45
= noise floor
≠ answerability 판정
```

---

# 5. 2.5단계 — Semantic Schema Context

## Action 3 결과와 아키텍처 결정

Action 3은 아래 세 조건을 비교했고 모두 운영 기준에 실패했다.

| 지표 | A Physical | B +TBox | C +Binding/Rule |
|---|---:|---:|---:|
| Table Accuracy | 19.0% | 26.2% | **40.5%** |
| Required Column Recall | 36.8% | 32.0% | 36.6% |
| SQL Executability | 19.0% | 23.8% | 22.6% |
| Execution Accuracy | 0.0% | 0.0% | 0.0% |
| Hallucinated Schema Rate | 59.5% | 48.8% | **42.9%** |
| Engine Selection Accuracy | 13.3% | 12.4% | **24.8%** |
| Dependency Accuracy | 23.8% | 19.0% | 21.0% |

C는 table 후보와 hallucination을 상대적으로 개선했지만 실행 결과는 0%였다. 따라서
full physical schema와 binding hint를 LLM prompt에 넣는 방식은 채택하지 않는다.
결정은 다음과 같다.

```text
Planner-facing: 질문별 최소 stable binding ID와 논리 조건만 전달
Executor-private: binding ID를 실제 schema.table.column/JOIN으로 해소
Validator: registry 밖 identifier와 rule을 실행 전에 차단
```

상세 근거는 `vectordb_test/5_semantic_schema_nl2sql/4_result.md`를 따른다.

## Action 4 목표 계약

Action 4는 **2.5단계 자체의 출력 계약·선별·경계 검증**이다. Planner 구현이나
Graph/Content engine 구축 단계가 아니다. 목표 `metadata_context`는 다음 한 객체로
고정한다.

```json
{
  "version": 1,
  "domain": "bond_kr",
  "task": "filter_rank",
  "concepts": ["fp:ratingRank", "fp:remainingDays", "fp:buyYield"],
  "bindings": [
    {
      "id": "bond.rating_rank",
      "label": "신용등급 서열",
      "datatype": "integer",
      "unit": "rank",
      "usage": ["select", "filter", "sort"]
    },
    {
      "id": "bond.remaining_days",
      "label": "잔존일수",
      "datatype": "integer",
      "unit": "day",
      "usage": ["select", "filter"]
    },
    {
      "id": "bond.buy_yield",
      "label": "매수수익률",
      "datatype": "numeric",
      "unit": "%",
      "usage": ["select", "filter", "sort"]
    }
  ],
  "entities": [],
  "filters": [
    {"binding": "bond.rating_rank", "operator": "<=", "value": 4},
    {"binding": "bond.remaining_days", "operator": "<=", "value": 1095}
  ],
  "order": [
    {"binding": "bond.buy_yield", "direction": "desc", "nulls": "last"}
  ],
  "limit": 10,
  "required_capabilities": ["rdb"],
  "as_of": {"value": "2026-02-24", "cutoff": "2026-07-11"},
  "unresolved": []
}
```

### Planner-facing 허용 정보

```text
stable binding ID
concept/label
logical datatype·unit·usage
정규화된 entity/filter/order/limit
required capability
as_of/cutoff
unresolved
```

### Planner-facing 금지 정보

```text
physical schema.table.column
SQL/SPARQL 문자열
DB alias와 JOIN key/cardinality
전체 74-binding catalog
forbidden column 목록
DSN·timeout·row cap·source priority 내부값
```

실제 `table`, `column`, JOIN key는 `metadata/schema_bindings.json`과
`metadata/business_rules.json`의 executor-private registry에만 둔다. Executor는
binding ID를 `psycopg.sql.Identifier`로 컴파일하고 값은 parameter binding한다.

## 현행 구현과 목표 계약의 차이

현재 `schema_context.ground()`는
`domain/task/entities/select/filters/order/limit/unresolved/concepts/as_of`를 반환하는
LogicalPlan 후보다. `ground_query`는 같은 객체를 `metadata_context`와 `plan`에 동시에
넣는다. Action 4에서는 두 객체를 분리한다.

또한 현행 resolver에는 다음 한계가 있다.

- `best_binding()`은 exact-only가 아니라 정규화 substring heuristic이다.
- 74개 binding은 RDB scalar 중심이고 verified JOIN은 2개뿐이다.
- relation table, Graph predicate, Content Vector collection binding은 아직 없다.
- TBox comment/business meaning은 runtime context에 실리지 않는다.
- 따라서 현행을 완성된 multi-engine Semantic Schema Context라고 부르지 않는다.

## Action 4 범위

### 포함

- `metadata_context`와 `LogicalPlan` 분리
- 질문별 최소 binding selection과 단위·등급 방향·필수 필터·정렬 정규화
- planner-facing payload와 executor-private registry 경계 검증
- RDB 14문항 및 저장 35문항에서 지원/미지원 capability 표시
- 미구현 Graph/Vector source를 만들지 않고 `required_capabilities` 또는 `unresolved`로 표시
- LLM·DB 없이 같은 입력에서 동일 context를 생성하는 결정성 검증

### 제외

- Query Frame prompt/model/timeout 조정
- 자유 NL2SQL과 Planner prompt 실험
- Graph Store/SPARQL, Content Index/Retrieval 구현
- 답변 품질, API/concurrency, ontology/ABox 확장
- `data/csv/` 수정과 cutoff 이후 데이터 수집

## Action 4 Acceptance Gate

1. Catalog: 12 tables, 74 bindings, 2 joins, forbidden binding 0, TBox integrity PASS.
2. RDB 14 저장 Frame: context 14/14, unresolved 0, required binding recall 100%.
3. q011/q013 등급 방향·1095일·매수가능, q012 ETF 상태, q017 큰 수/단위,
   q018 `NULLS LAST` 규칙 PASS.
4. Planner-facing payload의 `table`, `column`, SQL, physical JOIN key, full catalog 누출 0.
5. 동일 Frame+metadata 반복 결과 byte-identical 100%, local resolver p95 ≤50ms 기록.
6. 미지원 capability에 가짜 Graph/Vector source 생성 0, 완전일치 상품 유사 대체 0.
7. 기존 RDB Static/Schema/Evidence/DB exact 14/14 회귀 유지.

Action 4 합격은 live HCX SLA 합격을 의미하지 않는다. Query Frame latency는 별도
upstream qualification으로 관리한다.

### 2026-08-25 Baseline Blocker

현재 `data/csv` 배포본 파일명은 `*_20260824.csv`지만 `src/kb/build_rdb.py`의
`raw_types()`는 `*_schema_20260711.csv`를 찾고 있어 catalog `--check`가 metadata
검증 전에 `StopIteration`으로 중단된다. Action 4 시작 전에 다음을 만족해야 한다.

1. 파일 탐색을 현 배포본과 일치시키되 `data/csv` 값은 수정하지 않는다.
2. 파일명의 배포일과 값의 `as_of`를 구분하고 실제 값이 cutoff `2026-07-11`을
   넘지 않는지 다시 검증한다.
3. Gate 1의 catalog 검증을 재통과한 뒤 그 snapshot hash를 Action 4 입력으로 고정한다.

---

# 7. 3단계 — Plan &amp; Routing

## 현행과 목표

현행 RDB slice에는 별도 HCX Planner가 없다. Engine은 RDB로 고정되고,
`schema_context.ground()`가 LogicalPlan 후보를 만들며 `rdb.compile_plan()`이
allowlist SQL을 생성한다.

Planner의 핵심 책임은:

> **이미 확보된 의미와 사용 가능한 데이터 source를 보고 어떤 엔진을 어떤 순서로 호출할지 결정**

이다.

Planner가 주로 판단할 것은:

```text
RDB 단독인가?
Graph가 선행되어야 하는가?
Vector evidence가 필요한가?
병렬 실행 가능한가?
어떤 결과가 다음 step 입력인가?
```

---

## Planner가 하지 않도록 지향하는 것

검증 없이:

```text
"아마 raw.bond.rating_rank겠지"
```

처럼 존재하지 않거나 잘못된 schema를 창작하는 것.

Action 3 결과에 따라 Planner는 **검증된 metadata_context의 binding ID와 capability만
사용**해야 한다. physical identifier나 raw query는 각 executor가 private registry로
생성한다.

---

# 8. Plan 출력 원칙

현행 RDB LogicalPlan 예시는 다음과 같다.

```json
{
  "domain": "bond_kr",
  "select": ["bond.product_code", "bond.product_name", "bond.buy_yield"],
  "filters": [
    {"binding": "bond.rating_rank", "operator": "<=", "value": 4}
  ],
  "order": [
    {"binding": "bond.buy_yield", "direction": "desc", "nulls": "last"}
  ],
  "limit": 10,
  "unresolved": []
}
```

SQL은 State나 Planner 출력에 저장하지 않고 executor 내부 `CompiledQuery`에서만
생성한다. Action 3의 `execution_plan[].query` free-form 계약은 폐기한다.

Action 5에서 multi-source plan을 설계할 때도 외부 계약은 아래 수준으로 제한한다.

```text
engine + operation + binding IDs + depends_on
```

Graph/Vector operation의 상세 wire schema는 해당 executor가 구현되기 전에는 확정하지
않는다.

---

# 9. 전체 Routing 유형

Action 3 Gold가 가정한 예상평가 35문항 분류:


| 유형  | 구조                   | 건수     |
| --- | -------------------- | ------: |
| 유형1 | RDB 단독               | 14     |
| 유형2 | Graph → RDB          | 4      |
| 유형3 | Graph → RDB + Vector | 2      |
| 유형4 | Graph 다단계 → 순차 전체    | 8      |
| 유형5 | Graph 단독             | 2      |
| 유형6 | TBox 검증 단독           | 5      |
|     | 합계                   | **35** |


이 표는 runtime capability가 아니라 Action 3의 plan-only Gold 분류다. Graph/Vector
실행은 측정되지 않았고 현행 runtime engine은 RDB뿐이다. Action 3의 C도 Engine
Selection 24.8%, Dependency 21.0%였으므로 이 분류를 구현 완료로 해석하지 않는다.

---

# 10. 최신 State

```python
class State(TypedDict):
    question_id: str
    question: str
    intent: dict
    metadata_context: dict
    plan: dict
    results: dict
    evidence: list
    abstain: dict | None
    trace: list[str]
    answer: str
```

### `metadata_context`

Action 4에서 `plan`과 분리할 핵심 State다. 현행 State에는 `schema_hits`가 없고,
`ground_query`가 동일 객체를 `metadata_context`와 `plan`에 넣고 있다.

```text
TBox concept
+
최소 logical binding/context
+
capability·as_of·unresolved
```

Physical locator는 executor-private registry에 둔다.

---

# 11. ABSTAIN 코드

현행 코드가 반환하는 ABSTAIN 코드는 다음과 같다.

```text
ABSTAIN_INVALID_TAXONOMY
ABSTAIN_ENTITY_NOT_FOUND
ABSTAIN_FUTURE_DATA
ABSTAIN_DOMAIN_MISMATCH
ABSTAIN_UNRESOLVED_QUERY
ABSTAIN_RESULT_TOO_LARGE
ABSTAIN_EXECUTION_FAILED
ABSTAIN_EVIDENCE_MISMATCH
```

예:

```text
AAAA 등급
→ ABSTAIN_INVALID_TAXONOMY

2027년 확정 수익률
→ ABSTAIN_FUTURE_DATA

VOO가 발행한 회사채
→ ABSTAIN_DOMAIN_MISMATCH
```

기준일 이후 출시 판정용 `ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF`는 목표 계약이지만 현행
validator에는 아직 구현되지 않았다. 출시일 근거가 없으면 날짜를 추정하지 않고
`ABSTAIN_UNRESOLVED_QUERY`로 처리한다.

---

# 12. 최신 노드 구조

현행 RDB slice는 6노드다.


| 노드 | 단계 | LLM | Tool |
|---|---|---|---|
| `extract_query_frame` | 1 | HCX-007 1회 | `query_frame` |
| `ground_query` | 현행 2.5 | 0 | `schema_context` |
| `validate_query` | 검증 | 0 | `validate` |
| `execute_rdb` | 실행 | 0 | `rdb.execute` |
| `verify_results` | 검증 | 0 | evidence contract |
| `render_answer` | 답변 | 0 | deterministic renderer |

`search_bond_schema`, Graph/Content, HCX Planner/answer는 현재 graph에 없다.
`validate_query`도 완성된 ontology validator가 아니라 taxonomy·future year·일부 domain
문구·unresolved 중심의 제한 구현이다. 상품 완전일치 부재는 executor에서 판정한다.

Action 4에서는 `ground_query` 내부 책임을 TBox grounding과
`build_metadata_context`로 논리적으로 분리해 2.5 계약을 검증한다. 노드 수를 늘리는
것 자체는 acceptance가 아니다.

---

# 13. 현행 LangGraph와 Action 4 목표 경계

```text
START
  ↓
extract_query_frame
  ↓
ground_query
  ↓
validate_query
  ├─ ABSTAIN → render_answer
  └─ execute_rdb → verify_results → render_answer
                                      ↓
                                     END
```

Action 4의 검증 경계:

```text
Query Frame/TBox URI
→ deterministic build_metadata_context
→ planner-facing context
```

Action 4는 이 지점까지만 검증한다. 이후 multi-source Planner와 실행 노드는 Action
5·6에서 별도로 추가한다.

---

# 14. 기술스택 최신안


| 계층              | Engine                    | 상태                                     |
| --------------- | ------------------------- | -------------------------------------- |
| RDB             | PostgreSQL                | live DB 12테이블·PK/FK 20개 검증 완료          |
| Graph           | pyoxigraph                | 목표 — TTL 생성·검증만 구현                     |
| TBox Vector     | **PostgreSQL + pgvector** | FAISS → 이전                             |
| Content Vector  | Vector Store              | 미구현                                    |
| LLM Query Frame | HCX-007                   | 현재 RDB vertical slice에서 사용             |
| Planner         | 검증된 metadata 기반 결정적 plan  | 별도 Planner LLM 미사용                     |
| Answer          | 결정적 evidence renderer     | `ANSWER_MODEL=HCX-005`는 현재 slice에서 미사용 |


### Schema Vector

```text
bge-m3
1024 dimensions
cosine
pgvector <=> operator
```

130개 규모에서는 ANN이 필요 없다.

```text
Exact cosine / Seq Scan
```

으로 충분하다.

---

# 15. Semantic Schema Context의 데이터 출처

Executor-private registry는 이미 다음 두 파일로 관리한다.

- `metadata/schema_bindings.json`: version 1, 4 domains, 74 RDB bindings, JOIN 2개
- `metadata/business_rules.json`: cutoff/as_of, rating rank 19개, ETF 필수 필터,
  범주값·정렬·금지 컬럼 3개, max rows 10,000, max joins 3, timeout 2,000ms

## 자동 생성 가능

```text
RDB catalog
- table
- column
- datatype
- PK
- FK
- nullable
```

`src/kb/build_schema_catalog.py`는 live DB introspection이 아니라
`src.kb.build_rdb.TABLES` manifest에서 catalog를 생성한다. 이어 metadata의 table,
column, TBox URI, JOIN key, forbidden column과 fund dedup grain을 검증한다.

---

## 사람이 정의하고 검증해야 하는 부분

```text
business rule
unit
filter direction
join semantics
source priority
```

예:

```text
AA- 이상
→ 문자열 비교 X
→ ratingRank 사용
```

---

## Binding 관리

현재:

```text
metadata/schema_bindings.json
```

을 정본으로 사용한다. Action 4는 새 Agentic Resolver를 만들지 않고 이 registry의
최소 projection과 결정성을 먼저 검증한다. Graph/Vector source가 실제 구현된 뒤에만
해당 binding을 추가한다.

금지:

```text
미구현 source를 가짜 path/predicate/collection으로 등록
LLM이 registry에 없는 table·column·JOIN을 생성
전체 registry를 Planner prompt에 전달
```

---

# 16. 역할 경계 최종안

```text
Intent
= 사용자가 무엇을 원하는가

TBox Grounding
= 어떤 금융 개념인가

Semantic Schema Context
= 어떤 verified binding/capability로 조회할 수 있는가

Executor Registry
= binding ID를 실제 physical source와 안전 규칙으로 변환

Plan & Routing
= 어떤 source를 어떤 순서로 조회할 것인가

Execution
= SQL / SPARQL / Vector Search 실행

Validation
= 실행 결과가 ontology / data rule을 위반하지 않는가

Answer
= 검증된 evidence만 이용해 답변
```

---

# 17. 앞으로의 Action 순서

```text
Action 1
pgvector 가능성 검증
✅ 완료

Action 2
130 → 221 TBox/코드값 혼합 영향 검증
✅ 완료
→ Mixed Index 사용하지 않음

Action 2.5
FAISS runtime → pgvector runtime migration
✅ 완료

Action 3
Semantic Schema Context / NL2SQL 실험
A. Schema Only
B. Schema + TBox
C. Schema + TBox + Business Context
✅ 완료
→ A/B/C 모두 운영 채택 안 함

RDB vertical slice
저장 Query Frame 이후 deterministic binding/execution 검증
✅ DB exact 14/14, evidence 14/14, hallucination 0
⚠ live HCX strict success 7/70(10%)

Query Frame latency isolation
✅ 단일변수 실험 완료
→ 선택 구성 변경 근거 없음
→ qualification 8/14, HTTP 429 5건, q006 entity 실패 1건
→ runtime candidate 승격 실패

Query Frame cooldown/quota 재qualification
🚧 Action 4와 분리한 upstream 작업

Action 4
2.5단계 Semantic Schema Context 계약 검증
→ metadata_context / LogicalPlan 분리
→ 최소 binding ID와 capability만 Planner-facing
→ physical locator는 executor-private

Action 5
제한된 multi-source Plan & Routing 설계·검증

Action 6
Graph / Content engine 구축 후 실제 실행 연결

Action 7
35문항 E2E 검증
```

---

## 한 줄 구조

최신 구조

```text
Query Understanding
→ TBox Vector Grounding
→ Semantic Schema Context (verified binding/capability)
→ Plan & Routing
→ executor-private RDB / Graph / Vector compilation & execution
→ Validation
→ Evidence-based Answer
```
