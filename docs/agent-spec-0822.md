# 에이전트 파일 구조 (LangGraph) — 확정 v2 · 2026-08-22

> **2026-08-24 현행 정정:** RDB는 DuckDB가 아니라 PostgreSQL로 구현됐다. Graph는
> TBox/ABox TTL 생성·검증까지만 완료됐고 pyoxigraph loader/runtime은 목표 구조다.
> 데이터 구축 현행은 `docs/docs_data_layer/CURRENT_DATA_BUILD_STRUCTURE.md`를 우선한다.

 `TBox Vector Grounding → Semantic Schema Context → Plan & Routing` 구조

## 0. v1 → v2 주요 변경


| 변경            | v1            | v2                                                    |
| ------------- | ------------- | ----------------------------------------------------- |
| Schema Vector | FAISS         | **PostgreSQL + pgvector**                             |
| Vector 대상     | TBox + 확장 검토  | **comment가 풍부한 TBox 중심**                              |
| 코드리스트 91건     | Vector 포함 검토  | **Schema Vector에서 제외**                                |
| 2단계 출력        | `schema_hits` | `schema_hits` + 이후 `metadata_context` 구성              |
| 2→3단계         | 바로 Planner    | **Semantic Schema Context 단계 추가 후보**                  |
| RDB Schema 연결 | Planner 판단    | **Physical Schema + TBox + Business Context 실험 후 결정** |
| Planner 역할    | DB 구조까지 추론 가능 | **검증된 source context 기반 실행계획 생성**                     |
| Action 3      | 코드리스트 검색 실험   | **NL2SQL + Semantic Schema Context A/B/C 실험**         |


221 혼합 인덱스 실험에서 기존 TBox 용어끼리의 Top-1 역전은 0건이었지만, 신규 코드값이 상위 슬롯을 점유하면서 Top-5 comment 근거 커버리지가 100%→68.6%로 감소했다. 따라서 Schema Vector는 TBox 의미 grounding에 집중한다.

---

# 1. 최종 트리 구조

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

`tools/[graph.py](http://graph.py)`는 `tools.graph`이므로 사용 가능하다.

---

# 2. MVP — 채권 기준

현재 채권 MVP는 먼저 다음 구조로 간다.

```text
repo/
├── src/
│   ├── agent/
│   │   ├── agent_core.py
│   │   ├── nodes.py
│   │   └── state.py
│   │
│   ├── tools/
│   │   ├── bond_schema.py          # pgvector TBox 검색
│   │   └── validate.py
│   │
│   ├── kb/
│   │   └── build_bond_index.py     # bond.ttl → pgvector
│   │
│   ├── api.py
│   ├── config.py
│   └── clova.py
│
├── ontology/
│   └── bond.ttl
│
├── artifacts/
├── script/
│   └── test_bond_agent.py
│
├── vectordb_test/
├── requirements.txt
└── .env
```

### pgvector 이전 시 제거

```text
artifacts/bond.faiss
faiss-cpu
FAISS load/search 코드
```

### 유지할 검색 대상

```text
TBox concept / property
+
rdfs:comment가 존재하는 의미 단위
```

### Schema Vector에서 제외

```text
AAA
AA-
A
BB
장기
담보부
미국
주식
...
```

이들은 후속 ABox / RDB Value Resolution 대상

---

# 3. 전체 Agent 파이프라인

## 1단계 — Query Understanding

LLM으로 질문을 의미 단위로 분해한다.

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
  "domain": "bond",
  "entities": [],
  "conditions": [
    "회사채",
    "신용등급 AA- 이상",
    "잔존기간 3년 이하"
  ],
  "sort": "매수수익률 DESC"
}
```

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

## 현재 상태

**Action 3에서 구조 검증 예정.**

2단계까지는:

```text
fp:ratingRank
fp:remainingDays
fp:buyYield
```

라는 **논리 의미**만 안다.

하지만 Planner가 SQL을 만들려면:

```text
어느 DB?
어느 table?
어느 column?
무슨 datatype?
어떤 비교 규칙?
```

이 필요하다.

따라서 Planner 이전에 `metadata_context`를 구성하는 구조를 검증한다.

---

## metadata_context 후보

```json
{
  "concept_uri": "fp:ratingRank",
  "label": "신용등급 서열",
  "business_meaning": "신용등급의 우열 비교용 서열",
  "sources": [
    {
      "engine": "rdb",
      "path": "raw.bond_master.rating_rank",
      "datatype": "INTEGER",
      "usage": ["FILTER", "SORT"],
      "business_rule": "등급 범위 비교는 문자열이 아니라 rating_rank를 사용"
    }
  ]
}
```

Graph도 동일하다.

```json
{
  "concept_uri": "fp:issuedBy",
  "sources": [
    {
      "engine": "graph",
      "predicate": "fp:issuedBy"
    },
    {
      "engine": "rdb",
      "path": "raw.bond_master.issuer_name"
    }
  ]
}
```

Vector도:

```json
{
  "concept_uri": "fp:riskFactor",
  "sources": [
    {
      "engine": "vector",
      "collection": "content_embeddings",
      "filter": {
        "document_type": "risk_report"
      }
    }
  ]
}
```

---

# 6. Action 3에서 결정할 것

Semantic Schema Context 깊이는 아직 확정하지 않는다.

세 조건을 비교한다.

```text
A. Physical Schema Only

B. Physical Schema
   + TBox Meaning

C. Physical Schema
   + TBox Meaning
   + Business Context / Binding Rule
```

즉 최종적으로 아래 중 어디까지 Planner 앞에서 확정할지 실험으로 결정한다.

```text
logical concept
        ↓
physical schema
        ↓
business rule
        ↓
Planner
```

---

# 7. 3단계 — Plan &amp; Routing

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

Action 3에서 C 구조가 유의하게 좋다면 Planner는 **검증된 metadata_context 내부 source만 사용**하게 한다.

---

# 8. Planner 출력

```json
{
  "execution_plan": [
    {
      "id": "A",
      "engine": "graph",
      "query": "...",
      "depends_on": []
    },
    {
      "id": "B",
      "engine": "vector",
      "query": "...",
      "depends_on": []
    },
    {
      "id": "C",
      "engine": "rdb",
      "query": "SELECT ...",
      "depends_on": ["A"]
    }
  ],
  "query_type": "Graph_RDB_Vector"
}
```

Schema:

```python
_PLAN_JSON_SCHEMA = {
    "title": "execution_plan",
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "engine": {
                        "type": "string",
                        "enum": ["graph", "rdb", "vector"],
                    },
                    "query": {"type": "string"},
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "id",
                    "engine",
                    "query",
                    "depends_on"
                ],
            },
        }
    },
    "required": ["steps"],
}
```

---

# 9. 전체 Routing 유형

현재 예상평가 35문항 기준:


| 유형  | 구조                   | 건수     |
| --- | -------------------- | ------: |
| 유형1 | RDB 단독               | 14     |
| 유형2 | Graph → RDB          | 4      |
| 유형3 | Graph → RDB + Vector | 2      |
| 유형4 | Graph 다단계 → 순차 전체    | 8      |
| 유형5 | Graph 단독             | 2      |
| 유형6 | TBox 검증 단독           | 5      |
|     | 합계                   | **35** |


Action 3에서는 이 35문항을 그대로 **Plan &amp; Routing 평가셋**으로 사용한다.

RDB step이 실제 존재하는 문항만 별도로 NL2SQL 평가한다.

---

# 10. 최신 State

```python
class State(TypedDict):
    question_id: str
    question: str

    # 1단계
    intent: dict

    # 2단계
    schema_hits: list[dict]

    # 2.5단계
    metadata_context: list[dict]

    # 3단계
    plan: dict

    # 실행
    results: dict

    # 근거
    evidence: dict

    # 내부 추적
    trace: list[str]

    # 실패
    abstain: dict | None

    # 최종 답변
    answer: str
```

### `metadata_context`

최신 구조에서 추가되는 핵심 State다.

```text
TBox meaning
+
Physical Source
+
Business Context
```

를 Planner에게 넘긴다.

---

# 11. ABSTAIN 코드

기존 5종 유지.

```text
INVALID_TAXONOMY
AFTER_AS_OF
NOT_FOUND
FUTURE_VALUE
DOMAIN_VIOLATION
```

예:

```text
AAAA 등급
→ INVALID_TAXONOMY

2027년 확정 수익률
→ FUTURE_VALUE

VOO가 발행한 회사채
→ DOMAIN_VIOLATION
```

---

# 12. 최신 노드 구조

Action 3 결과에서 Semantic Schema Context가 채택된다는 가정의 목표 구조:


| 노드                       | 단계  | LLM               | Tool                              |
| ------------------------ | --- | ----------------- | --------------------------------- |
| `classify_intent`        | 1   | HCX-DASH-002      | -                                 |
| `guard_intent`           | 1   | 0                 | -                                 |
| `check_tbox`             | 검증  | 0                 | `validate.*`                      |
| `ground_schema`          | 2   | Embedding         | `schema_search`                   |
| `build_metadata_context` | 2.5 | **0 또는 Resolver** | `schema_context`                  |
| `plan`                   | 3   | HCX-007           | -                                 |
| `execute`                | 실행  | 0                 | `sql`, `sparql`, `content_search` |
| `verify`                 | 검증  | 0                 | deterministic validation          |
| `answer`                 | 답변  | HCX-007           | -                                 |


기존 8개 → **목표 9개 노드**가 된다.

단, `build_metadata_context`의 최종 구현 방식은 Action 3에서 결정한다.

---

# 13. 최신 LangGraph 후보

```text
START
  ↓
classify_intent
  ↓
guard_intent
  ├─ unanswerable_check
  │      ↓
  │   check_tbox
  │      ├─ FAIL → answer
  │      └─ PASS
  │
  ↓
ground_schema
  ↓
build_metadata_context
  ↓
plan
  ↓
execute
  ↓
verify
  ├─ FAIL → answer(abstain)
  └─ PASS
        ↓
      answer
        ↓
       END
```

코드 형태:

```python
graph = StateGraph(State)

graph.add_node("classify_intent", classify_intent)
graph.add_node("guard_intent", guard_intent)
graph.add_node("check_tbox", check_tbox)

graph.add_node("ground_schema", ground_schema)
graph.add_node("build_metadata_context", build_metadata_context)

graph.add_node("plan", plan)
graph.add_node("execute", execute)
graph.add_node("verify", verify)
graph.add_node("answer", answer)
```

---

# 14. 기술스택 최신안


| 계층             | Engine                    | 상태         |
| -------------- | ------------------------- | ---------- |
| RDB            | PostgreSQL                | live DB 12테이블·PK/FK 20개 검증 완료 |
| Graph          | pyoxigraph                | 목표 — TTL 생성·검증만 구현 |
| TBox Vector    | **PostgreSQL + pgvector** | FAISS → 이전 |
| Content Vector | Vector Store              | 미구현        |
| LLM Query Frame | HCX-007                  | 현재 RDB vertical slice에서 사용 |
| Planner        | 검증된 metadata 기반 결정적 plan | 별도 Planner LLM 미사용 |
| Answer         | 결정적 evidence renderer  | `ANSWER_MODEL=HCX-005`는 현재 slice에서 미사용 |


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

Action 3에서 C안이 채택되면 아래 구조로 간다.

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

`build_schema_[catalog.py](http://catalog.py)`가 DB introspection으로 생성한다.

---

## 사람이 정의하거나 검증해야 할 가능성이 높은 부분

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

초기에는:

```text
metadata/schema_bindings.json
```

으로 관리 가능.

이후 필요하면:

```text
Agentic Schema Resolver
→ deterministic validator
→ verified binding registry
```

구조를 추가한다.

---

# 17. 역할 경계 최종안

```text
Intent
= 사용자가 무엇을 원하는가

TBox Grounding
= 어떤 금융 개념인가

Semantic Schema Context
= 그 개념과 관련된 실제 데이터는 어디 있고
  어떻게 사용해야 하는가

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

# 18. 앞으로의 Action 순서

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
← 지금 진행

Action 3
Semantic Schema Context / NL2SQL 실험
A. Schema Only
B. Schema + TBox
C. Schema + TBox + Business Context

Action 4
실험 결과에 따라
metadata_context 구조 확정

Action 5
Plan & Routing 구현

Action 6
RDB / Graph / Vector 실제 실행 연결

Action 7
35문항 E2E 검증
```

---

## 한 줄 구조

최신 구조

```text
Query Understanding
→ TBox Vector Grounding
→ Semantic Schema Context
→ Plan & Routing
→ RDB / Graph / Vector Execution
→ Validation
→ Evidence-based Answer
```
