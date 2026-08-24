# Action 3 — Semantic Schema Context 기반 NL2SQL · Plan & Routing 실험 설계서

- 작성일: 2026-08-22
- 대체 대상: 기존 Action 3 — 코드리스트 91건 전용 질의셋 실험
- 목적: **Ontology Grounding 이후 Planner에게 어떤 수준의 RDB / Graph / Vector 메타데이터를 제공해야 SQL 및 실행계획 오류를 최소화할 수 있는지 검증**
- 핵심 비교: **Schema Only vs Schema + TBox vs Schema + TBox + Business Context**
- 최종 적용 위치: `Ontology Grounding → Semantic Schema Context → Plan & Routing`

---

## 1. 배경

현재 Agent는 다음 1~2단계를 우선 구축하고 있다.

```text
① Query Understanding
   사용자 질의를 대상 / 조건 / 행위로 분해
        ↓
② Ontology Grounding
   TBox rdfs:comment 기반 Vector Search
   자연어 표현을 fp: ontology concept로 grounding
        ↓
③ Plan & Routing
   GraphDB / RDB / VectorDB 실행계획 생성
```

현재 2단계 Vector DB에는 **TBox의 설명이 풍부한 ontology concept**만 넣는 방향이 적절하다는 것이 확인되었다.

코드리스트 성격의 값 91건을 동일 Vector Index에 추가한 실험에서는 다음이 발생했다.

- 기존 TBox 용어 간 실제 순위 역전: 0건
- 신규 코드값이 상위 검색 슬롯을 점유
- Recall@3: 96.7% → 90.0%
- Top-5 comment 근거 커버리지: 100% → 68.6%
- Noise FP: 25% → 50%

따라서 다음 단계의 핵심 문제는 **ABox 값까지 TBox Vector DB에 넣는 것**이 아니라 다음이다.

> **TBox에서 grounding된 논리적 의미를 실제 RDB table.column, Graph predicate, Vector source와 어떻게 연결해 Planner에게 제공할 것인가?**

---

## 2. 실험 목적

이번 Action 3는 다음 세 질문에 답한다.

### Q1. RDB 물리 스키마만 주면 Planner가 정확한 SQL을 생성할 수 있는가?

예:

```text
raw.bond_master
- credit_rating
- rating_rank
- remaining_days
- buy_yield
```

만 제공했을 때 자연어 조건을 올바른 컬럼과 연산으로 연결하는지 측정한다.

### Q2. 물리 스키마에 TBox의 비즈니스 의미를 함께 주면 SQL 정확도가 개선되는가?

예:

```text
fp:ratingRank
"신용등급 비교용 서열. 등급의 우열 비교에 사용한다."

+

raw.bond_master.rating_rank
INTEGER
```

를 함께 제공했을 때 `"AA- 이상"`을 단순 문자열 비교가 아니라 `rating_rank` 기반 조건으로 변환할 수 있는지 측정한다.

### Q3. TBox 의미뿐 아니라 실제 사용 규칙까지 제공해야 안정적인가?

예:

```text
fp:ratingRank
business_rule:
- 신용등급 범위 비교에는 원문 문자열 비교가 아니라 rating_rank 사용
- AA- 이상의 방향은 ontology에 정의된 서열 규칙 사용
```

까지 제공했을 때 SQL 실행 정확도와 hallucination이 얼마나 개선되는지 측정한다.

---

## 3. 검증할 최종 구조

```text
① Query Understanding
        ↓
② TBox Ontology Grounding
        ↓
②-1 Semantic Schema Context Retrieval
        ├─ Physical RDB Schema
        ├─ TBox Business Meaning
        ├─ Physical Binding 후보
        ├─ Filter / Join / Value Rule
        ├─ Graph Predicate
        └─ Vector Source
        ↓
③ Plan & Routing
        ↓
④ SQL / SPARQL / Vector Search 실행
        ↓
⑤ Validation
        ↓
⑥ Answer
```

중요:

```text
TBox Vector Search
≠
RDB Schema Search
```

TBox Vector DB는 계속 **자연어 → 논리 개념 grounding** 역할만 한다.

이번 실험은 TBox 결과와 Physical Schema를 **Planner 입력 단계에서 어떻게 결합할지**를 결정하기 위한 것이다.

---

## 4. 가설

### H1 — Schema Only는 부족하다

물리 스키마만 제공하면 다음 오류가 발생할 가능성이 높다.

- 의미가 유사한 컬럼 오선택
- 문자열 값과 정렬용 numeric 컬럼 혼동
- 잘못된 filter 방향
- 존재하지 않는 table / column hallucination
- JOIN 관계 오선택

예:

```text
질문:
"AA- 이상 채권"

잘못된 SQL 후보:
WHERE credit_rating >= 'AA-'
```

문법적으로는 실행될 수 있지만 금융 의미상 잘못된 비교가 될 수 있다.

### H2 — Schema + TBox는 의미 해석을 개선한다

Planner에게 물리 스키마와 함께 `fp:CreditRating`, `fp:ratingRank`, `fp:remainingDays` 등의 ontology comment / domain / range를 제공하면 컬럼 선택과 조건 해석이 개선될 것으로 예상한다.

단, TBox와 Physical Schema 사이의 명시적 binding을 제공하지 않으므로 여전히 mapping 오류가 발생할 수 있다.

### H3 — Schema + TBox + Business Context가 가장 안정적이다

논리 의미와 물리 schema뿐 아니라 아래까지 제공하면 SQL 실행 정확도가 가장 높고 hallucination이 가장 낮을 것으로 예상한다.

- ontology concept ↔ table.column mapping
- filter rule
- join rule
- unit
- value resolution rule
- source priority

---

## 5. 실험군

동일한 질문, 동일한 LLM, 동일한 DB, 동일한 temperature 조건에서 **Planner 입력 context만 변경**한다.

### A — Physical Schema Only

Planner에게 RDB 구조만 제공한다.

```json
{
  "table": "raw.bond_master",
  "columns": [
    {"name": "credit_rating", "type": "VARCHAR"},
    {"name": "rating_rank", "type": "INTEGER"},
    {"name": "remaining_days", "type": "INTEGER"},
    {"name": "buy_yield", "type": "DOUBLE"}
  ]
}
```

제공:

- table name
- column name
- datatype
- PK / FK
- nullable 여부

제외:

- ontology comment
- business meaning
- concept ↔ column binding
- filter / join rule
- sample SQL

**목적:** 기본 NL2SQL baseline 측정.

### B — Physical Schema + TBox

A 조건에 **2단계 Ontology Grounding 결과**를 추가한다.

```json
{
  "grounded_concepts": [
    {
      "concept_uri": "fp:ratingRank",
      "label": "신용등급 서열",
      "description": "신용등급 간 우열을 비교하기 위한 서열값."
    },
    {
      "concept_uri": "fp:remainingDays",
      "label": "잔존일수",
      "description": "기준일 현재 만기일까지 남은 일수."
    }
  ],
  "physical_schema": {
    "table": "raw.bond_master",
    "columns": [
      {"name": "credit_rating", "type": "VARCHAR"},
      {"name": "rating_rank", "type": "INTEGER"},
      {"name": "remaining_days", "type": "INTEGER"},
      {"name": "buy_yield", "type": "DOUBLE"}
    ]
  }
}
```

중요: **명시적인 `fp:ratingRank → raw.bond_master.rating_rank` binding은 제공하지 않는다.**

Planner가 TBox 의미와 Physical Schema를 보고 연결해야 한다.

**목적:** Ontology 의미 자체가 schema linking / SQL generation에 주는 효과 측정.

### C — Physical Schema + TBox + Business Context

B 조건에 **Semantic Schema Context**를 추가한다.

```json
{
  "metadata_context": [
    {
      "concept_uri": "fp:ratingRank",
      "label": "신용등급 서열",
      "business_meaning": "신용등급의 우열 비교에 사용하는 정렬용 값.",
      "sources": [
        {
          "engine": "rdb",
          "path": "raw.bond_master.rating_rank",
          "datatype": "INTEGER",
          "usage": ["FILTER", "SORT"],
          "business_rule": "신용등급 범위 비교는 원등급 문자열이 아니라 rating_rank를 사용한다."
        }
      ]
    },
    {
      "concept_uri": "fp:remainingDays",
      "label": "잔존일수",
      "business_meaning": "기준일 현재 만기까지 남은 일수.",
      "sources": [
        {
          "engine": "rdb",
          "path": "raw.bond_master.remaining_days",
          "datatype": "INTEGER",
          "unit": "day",
          "usage": ["FILTER", "SELECT"]
        }
      ]
    }
  ]
}
```

**목적:** 논리 schema + 물리 schema + 실제 사용규칙을 결합한 최종 후보 구조 검증.

---

## 6. Semantic Schema Context 최소 필드

C 조건의 context는 다음 형태를 권장한다.

```json
{
  "concept_uri": "fp:expenseRatio",
  "label": "총보수요율",
  "business_meaning": "상품 보유에 발생하는 연간 총 비용 비율.",
  "sources": [
    {
      "engine": "rdb",
      "path": "raw.etf_master.total_expense_ratio",
      "datatype": "DOUBLE",
      "unit": "%",
      "usage": ["SELECT", "FILTER", "SORT"],
      "filter_rule": null,
      "join_rule": null
    }
  ]
}
```

| 필드 | 의미 |
|---|---|
| `concept_uri` | TBox에서 grounding된 논리 개념 |
| `label` | 사람이 보는 용어 |
| `business_meaning` | 금융·업무 의미 |
| `engine` | `rdb`, `graph`, `vector` |
| `path` | 실제 물리 source |
| `datatype` | RDB 자료형 |
| `unit` | %, KRW, day 등 |
| `usage` | SELECT / FILTER / SORT / JOIN |
| `filter_rule` | 범위·등급·상태 판정 규칙 |
| `join_rule` | 다른 table 또는 engine과 연결 규칙 |

---

## 7. 테스트 데이터

기존 `2026_expected_queries.md`의 35문항을 정본으로 사용한다.

```text
전체       35
ANSWER     30
ABSTAIN     5
```

질의셋은 수정하지 않는다.

---

## 8. 테스트를 두 층으로 분리

35문항 전부를 NL2SQL 정확도로 평가하면 안 된다. Graph-only 또는 TBox validation-only 질의에는 SQL 자체가 필요 없기 때문이다.

### Test A — NL2SQL Context Test

대상: **RDB가 실제 실행계획에 포함되는 질문만 사용**

현재 예상 Routing 분류 기준:

| 유형 | 건수 | NL2SQL 평가 |
|---|---:|---|
| RDB 단독 | 14 | 포함 |
| Graph → RDB | 4 | 포함 |
| Graph → RDB + Vector | 2 | 포함 |
| Graph 다단계 → 순차전체 | 8 | 포함 |
| Graph 단독 | 2 | 제외 |
| TBox 검증 단독 | 5 | 제외 |

최대 **28문항**을 NL2SQL 평가 대상으로 사용한다.

단, 각 문항의 실제 gold plan에서 RDB step이 존재하는지 다시 확인한 뒤 최종 N을 확정한다.

### Test B — Multi-Source Plan & Routing Test

대상: **35문항 전체**

평가 대상:

```text
RDB
Graph
Vector
```

중 어떤 engine이 필요한지, 어떤 순서로 호출해야 하는지 측정한다.

---

## 9. NL2SQL Gold 작성

각 RDB 대상 질문에 대해 SQL 문자열 하나를 gold로 고정하지 않는다. SQL은 표현이 여러 가지일 수 있기 때문이다.

대신 다음 구조를 gold로 정의한다.

```json
{
  "question_id": "q013",
  "required_tables": ["raw.bond_master"],
  "required_columns": [
    "product_name",
    "issuer",
    "credit_rating",
    "rating_rank",
    "remaining_days",
    "buy_yield",
    "buyable_qty"
  ],
  "required_filters": [
    "asset_type = CORPORATE_BOND",
    "buyable_qty > 0",
    "rating_rank satisfies AA- or better",
    "remaining_days <= 1095"
  ],
  "required_sort": ["buy_yield DESC"],
  "required_limit": 10
}
```

최종 평가는 생성 SQL을 실행한 결과와 gold result set을 비교한다.

---

## 10. NL2SQL 평가 지표

### 10.1 Table Accuracy

필요한 RDB table을 모두 선택했는가.

### 10.2 Column Recall

답변과 조건에 필요한 컬럼을 모두 사용했는가.

특히 다음을 구분한다.

```text
SELECT column
FILTER column
SORT column
JOIN column
```

### 10.3 Filter Semantic Accuracy

가장 중요한 지표 중 하나다.

예: `"AA- 이상"`에 대해 단순 문자열 비교가 아니라 ontology / business rule이 정의한 올바른 비교를 했는지 확인한다.

### 10.4 Join Accuracy

필요한 table 간 join의 key / direction / cardinality가 올바른지 평가한다.

### 10.5 SQL Executability

생성 SQL이 실제 DB에서 오류 없이 실행되는 비율.

### 10.6 Execution Accuracy

가장 중요한 최종 지표.

```text
생성 SQL 실행 결과
vs
Gold Query 실행 결과
```

를 비교한다.

PASS/FAIL 평가에서는 이 지표를 최우선으로 사용한다.

### 10.7 Hallucinated Schema Rate

존재하지 않는 table / column / join key를 생성한 비율.

목표: **0%**

---

## 11. Multi-Source Routing 평가

35문항 전체에 대해 각 질문의 gold execution graph를 만든다.

예:

```text
q013
RDB
```

```text
q024
Graph
  ↓
RDB
  ↓
Vector
```

### 11.1 Engine Selection Accuracy

필요한 engine 집합이 맞는지 평가한다.

### 11.2 Dependency Accuracy

순서가 필요한 경우 `depends_on`이 정확한지 평가한다.

### 11.3 Parallelization Accuracy

서로 독립적인 작업을 불필요하게 순차화하는지 평가한다.

### 11.4 Unnecessary Engine Call Rate

필요하지 않은 engine을 추가 호출하는지 측정한다.

---

## 12. Planner 출력 스키마

기존 구조를 유지한다.

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
      "engine": "rdb",
      "query": "...",
      "depends_on": ["A"]
    }
  ],
  "query_type": "유형2_Graph순차RDB"
}
```

이번 실험에서는 `think_trace` 내용은 평가하지 않는다.

---

## 13. 통제 조건

A/B/C 비교에서 다음 조건은 반드시 동일하게 유지한다.

- HyperCLOVA X 모델
- temperature
- system prompt
- user question
- ontology version
- DB snapshot
- Graph snapshot
- Vector content snapshot
- data cutoff: `2026-07-11`
- Planner JSON schema
- 최대 token budget
- 실행 timeout

변수는 오직 **Planner에 제공되는 metadata context 수준**이다.

---

## 14. 반복 실행

LLM 출력 변동을 고려해 각 질문·조건을 최소 3회 실행한다.

예:

```text
28 RDB questions
× 3 context conditions
× 3 runs
= 최대 252 NL2SQL runs
```

비용이 부담되면 1차는 1회 전체 실행 후, 결과 차이가 큰 문항만 3회 반복한다.

---

## 15. 성공 기준

C가 다음 경향을 보이면 최종 구조 후보로 채택한다.

```text
Execution Accuracy
C > B > A
```

그리고:

```text
Hallucinated Schema Rate = 0%
```

를 목표로 한다.

권장 최소 기준:

| 지표 | 목표 |
|---|---:|
| SQL Executability | ≥ 95% |
| Execution Accuracy | ≥ 90% |
| Required Column Recall | ≥ 95% |
| Hallucinated Schema | 0% |
| Engine Selection Accuracy | ≥ 95% |
| Dependency Accuracy | ≥ 95% |

절대 기준은 1차 실측 결과를 보고 조정하되, 세 조건 간 상대 비교는 반드시 유지한다.

---

## 16. 결과 해석 규칙

### A ≈ B ≈ C

Ontology / Business Context가 실질적으로 필요 없을 가능성.

→ 구조 단순화 검토.

### B > A, C ≈ B

TBox 의미만으로 충분.

→ 별도 Business Binding Registry를 대규모로 구축할 필요 없음.

### C >> B > A

예상하는 결과.

→ Planner 이전에 `Semantic Schema Context`를 제공하는 구조 채택.

### C가 높은 정확도지만 유지보수 비용이 과도함

다음 구조 검토:

```text
Agentic Schema Resolver
        ↓
deterministic validation
        ↓
verified binding cache
```

새 physical schema가 추가될 때만 mapping 후보를 생성하고 검증된 mapping을 재사용한다.

---

## 17. Error Taxonomy

각 실패를 아래 중 하나로 분류한다.

```text
E1  Wrong Table
E2  Wrong Column
E3  Missing Column
E4  Wrong Filter Operator
E5  Wrong Business Rule
E6  Wrong Join
E7  Hallucinated Schema
E8  Wrong Engine
E9  Wrong Dependency
E10 Missing Engine
E11 Unnecessary Engine
E12 SQL Syntax Error
E13 Correct SQL / Wrong Result due to data
```

A/B/C에서 어떤 오류군이 감소하는지 비교한다.

---

## 18. 실험 산출물

권장 구조:

```text
vectordb_test/
└── action3_semantic_schema/
    ├── README.md
    ├── build_physical_schema_catalog.py
    ├── build_semantic_context.py
    ├── gold/
    │   ├── expected_queries_35.json
    │   ├── gold_nl2sql.json
    │   └── gold_routing.json
    ├── contexts/
    │   ├── schema_only.json
    │   ├── schema_tbox.json
    │   └── schema_tbox_business.json
    ├── run_nl2sql_eval.py
    ├── run_routing_eval.py
    ├── evaluate_sql.py
    ├── evaluate_routing.py
    └── results/
        ├── nl2sql_raw.json
        ├── routing_raw.json
        ├── action3_result.md
        └── error_cases.json
```

---

## 19. 구현 순서

### Step 1 — Gold Plan 작성

35문항 각각에 대해 다음을 사람이 검토해 고정한다.

```text
required engines
required order
required tables
required columns
required filters
required evidence
```

### Step 2 — Physical Schema Catalog 생성

RDB에서 자동 추출한다.

최소:

```text
table
column
datatype
PK/FK
```

가능하면 DB comment / nullable / unit까지 포함한다.

### Step 3 — A Context 생성

Physical Schema만 제공한다.

### Step 4 — B Context 생성

Action 2의 TBox Grounding 결과를 Physical Schema와 함께 제공한다.

**명시적 binding은 넣지 않는다.**

### Step 5 — C Context 생성

다음을 연결한다.

```text
TBox concept
↔
physical source
+
business meaning
+
filter / join / value rules
```

### Step 6 — NL2SQL A/B/C 실행

RDB가 필요한 질문만 동일 조건으로 실행한다.

### Step 7 — SQL 실제 실행

문자열 유사도가 아니라 DB에서 SQL을 실행한다.

```text
syntax
execution
result set
```

을 모두 기록한다.

### Step 8 — 35문항 Routing 실행

RDB / Graph / Vector의 선택, 순서, dependency를 평가한다.

### Step 9 — Error Analysis

A/B/C별 Error Taxonomy를 집계한다.

예:

```text
Schema Only
E2 Wrong Column      8
E5 Business Rule     7
E7 Hallucination     3

Schema + TBox
E2 Wrong Column      3
E5 Business Rule     5
E7 Hallucination     1

Schema + TBox + Business
E2 Wrong Column      0
E5 Business Rule     1
E7 Hallucination     0
```

### Step 10 — Architecture Decision

실험 결과에 따라 다음 중 하나를 확정한다.

```text
Option A
TBox → Planner

Option B
TBox + Physical Schema → Planner

Option C
TBox → Semantic Schema Context → Planner
```

C가 채택되더라도 mapping 작성 방식을 바로 전부 수동화하지 않는다.

다음 Action에서:

```text
Static Binding Registry
vs
Agentic Resolver + Validator + Cache
```

를 별도로 비교한다.

---

## 20. 이번 Action에서 하지 않는 것

```text
- 코드리스트 91건을 TBox Vector Index에 재삽입
- 91개 전체 rdfs:comment 작성
- embedding model 변경
- RRF 재튜닝
- HNSW 튜닝
- 최종 Answer Prompt 최적화
- Planner reasoning trace 평가
- 자동 Binding Registry 업데이트
```

목적은 오직:

> **Planner에게 어떤 metadata context를 줘야 SQL 및 routing 오류가 가장 적어지는가**

를 결정하는 것이다.

---

## 21. 최종 판정 질문

Action 3 완료 시 아래에 답할 수 있어야 한다.

1. RDB schema만 제공해도 충분한가?
2. TBox business meaning을 추가하면 어떤 오류가 줄어드는가?
3. 명시적인 semantic binding / business rule까지 제공해야 하는가?
4. Planner는 physical schema 연결을 스스로 판단해도 되는가?
5. RDB / Graph / Vector multi-source 계획을 정확한 순서로 만들 수 있는가?

---

## 22. 최종 목표 Architecture 후보

이번 실험에서 C가 우세하면 다음 구조를 채택한다.

```text
Query
  ↓
① Query Understanding
  ↓
② TBox Ontology Grounding
  ↓
②-1 Semantic Schema Context
     ├─ ontology meaning
     ├─ RDB table.column
     ├─ Graph predicate
     ├─ Vector source
     └─ business / join / filter rules
  ↓
③ Plan & Routing
  ↓
④ Execute
     ├─ SQL
     ├─ SPARQL
     └─ Vector Search
  ↓
⑤ Validation
  ↓
⑥ Answer
```

---

## 한 문장 요약

> **Action 3는 “RDB 스키마만 제공”, “RDB 스키마 + TBox 의미”, “RDB 스키마 + TBox 의미 + 비즈니스 실행규칙” 세 조건을 동일 예상질의로 비교하여, Planner가 물리 스키마를 얼마나 스스로 판단하게 할지 실증적으로 결정하는 실험이다.**
