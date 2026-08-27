

## 1. 실행 형식

구현 위치는 agent/agent_[core.py](http://core.py):19입니다.



### 현재

- 현재는 graph_only, graph_then_rdb, Vector 경로가 선언만 되어 있고 활성화되어 있지 않음
- 실제 실행 가능한 경로는 rdb_only뿐입니다.

```
사용자 질문
→ extract_query_frame : HCX-007 Query Frame       ← 생성형 LLM 호출
→ ground_query : 정적 metadata grounding   ← Python 규칙
→ validate_query : Validator                 ← Python 규칙
→ Rselect_route : oute                     ← Python 규칙
→ SQL compiler/RDB 실행     ← 결정론적
→ 답변 출력                 ← 현재는 Python 문자열 생성
```

호출 인터페이스:

```python
from agent.agent_core import ask
  response = ask(
      question="VOO의 정식 상품명과 총보수를 알려줘",
      question_id=""
  )
```

내부 실행:

```
ask(question)
    ↓
초기 State 생성
    ↓
APP.invoke(initial_state)
    ↓
extract_query_frame
    ↓
ground_query
    ↓
validate_query
    ├─ ABSTAIN → render_answer → END
    └─ PASS
         ↓
       select_route
         ├─ rdb_only → execute_rdb → verify_results → render_answer → END
         └─ 그 외    → render_answer → END
    ↓
  to_response(final_state)
```

### 목표

```
Query Understanding : HCX-007 Query Frame 출력 (생성형 LLM 호출)
→ TBox Vector Grounding : Vector 검색
→ Semantic Schema Context (verified binding/capability) :metadata grounding +  Validator  
→ Plan & Routing (생성형 LLM 호출)
→ executor-private RDB / Graph / Vector compilation & execution
→ Validation
→ Evidence-based Answer
```

```text
2단계 : TBox Vector Grounding : Vector 검색

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

검색 결과:
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

```json
2단계 : Semantic Schema Context (verified binding/capability) :

출력 : 
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

```text
3단계 : Plan & Routing (생성형 LLM 호출)
이미 확보된 의미와 사용 가능한 데이터 source를 보고 어떤 엔진을 어떤 순서로 호출할지 결정

Planner가 주로 판단할 것은:
RDB 단독인가?
Graph가 선행되어야 하는가?
Vector evidence가 필요한가?
병렬 실행 가능한가?
어떤 결과가 다음 step 입력인가?
```



## 2. 전체 State 구조

  agent/state.py:6:

```
class State(TypedDict):
    question_id: str
    question: str
    intent: dict          # 1단계 Query Frame (agent/query_frame.py, 14필드)
    metadata_context: dict  # verified binding으로 grounding된 LogicalPlan 후보
    plan: dict            # 물리 SQL 문자열이 없는 LogicalPlan
    route: dict           # query_type enum + 최대 3단계 constrained execution plan
    results: dict         # rows/columns/evidence/abstain
    evidence: list        # 최종 응답에 노출할 source/as_of 근거
    abstain: dict | None  # 결정적 validator의 실패 사유
    trace: list           # 노드가 남기는 관측 기록. 주최측 규격의 think_trace 로 나간다
    answer: str
```

## 3. 단계별 State 출력

- HyperCLOVA X HCX-007을 한 번 호출합니다.
- LLM 원본은 *raw, 결정적 보정 내역은* guard에 저장됩니다.
- 예외가 나면 빈 Frame과 _error를 생성하고 안전 중단으로 이어집니다.

### ① extract_query_frame

  입력

```
state["question"]
```

  출력 업데이트

```
{  
"intent": {
      "domain_candidates": [...],
      "task": "lookup | filter_rank | relation | ...",
      "targets": [...],
      "entities": [...],
      "requested_fields": [...],
      "constraints": [...],
      "relations": [...],
      "ordering": [...],
      "limit": None,
      "temporal": {...},
      "computation": [...],
      "evidence_requirements": [...],
      "ambiguity": [...],
      "validation_targets": [...],
      "_guard": [...],
      "_raw": {...}
  },
  "trace": [...]
}
```



### ② ground_query

  출력 업데이트:

```
{ 
"metadata_context": logical_plan,
  "plan": logical_plan,
  "trace": [...]
}
```

  LogicalPlan 형식:

```
{"domain": "etf_gl",
  "task": "lookup",
  "entities": [
      {
          "mode": "exact",
          "binding": "etf_gl.ticker",
          "value": "VOO"
      }
  ],
  "select": [
      "etf_gl.product_code",
      "etf_gl.product_name",
      "etf_gl.expense_ratio"
  ],
  "filters": [
      {
          "binding": "etf_[gl.group](http://gl.group)",
          "operator": "==",
          "value": "ETF"
      }
  ],
  "order": [],
  "limit": None,
  "unresolved": [],
  "concepts": [
      "fp:productCode",
      "fp:productName",
      "fp:expenseRatio",
      "fp:productGroup"
  ],
  "as_of": {
      "value": "2026-08-21",
      "basis": "종가 기준일..."
  }
}
```

  metadata_context와 plan에는 현재 같은 객체가 들어갑니다.

  VOO 관측값:

  grounding: domain=etf_gl

  concepts=['fp:productCode', 'fp:productName',

```
VOO 관측값:
grounding: domain=etf_gl

  concepts=['fp:productCode', 'fp:productName',       
 'fp:expenseRatio', 'fp:productGroup']
```

  unresolved=0

  관련 코드: tools/schema_context.py:137

### ③ validate_query

  출력 업데이트:

  {

```
  "abstain": None | {

      "code": "ABSTAIN_...",

      "reason": "...",

      "evidence": [...]

  },

  "trace": [...]
```

  }

  검증 항목:

- 도메인 확정 여부
- 요청 날짜가 cutoff 이후인지
- 신용등급 허용값
- 미래 실현값
- 관계 domain/range
- 미해소 binding
- 데이터 snapshot이 cutoff 이후인지

  VOO 질의의 실제 결과:

  {

```
  "abstain": {

      "code": "ABSTAIN_CUTOFF_VIOLATION",

      "reason": (

          "etf_gl snapshot 2026-08-21가 "

          "cutoff 2026-07-11 이후입니다."

      ),

      "evidence": [

          {

              "as_of": "2026-08-21",

              "cutoff": "2026-07-11"

          }

      ]

  }
```

  }

  이후 select_route, execute_rdb, verify_results를 건너뛰고 바로 render_answer로 이동합니다.

### ④ select_route

  검증을 통과했을 때만 실행됩니다.

  정상 RDB 경로:

  {

```
  "route": {

      "query_type": "rdb_only",

      "execution_plan": [

          {

              "id": "A",

              "engine": "rdb",

              "depends_on": []

          }

      ],

      "reason": "verified single-domain RDB capability"

  },

  "abstain": None,

  "trace": [...]
```

  }

  미지원이면:

  {

```
  "route": {

      "query_type": "unsupported",

      "execution_plan": [],

      "reason": "..."

  },

  "abstain": {

      "code": "ABSTAIN_UNSUPPORTED_ROUTE",

      "reason": "..."

  }
```

  }

  관련 코드: tools/route.py:21

### ⑤ execute_rdb

  출력 업데이트:

  {

```
  "results": {

      "rows": [

          {

              "pd_itm_no": "...",

              "pd_nm": "...",

              "cu_charge_rt": ...

          }

      ],

      "columns": [

          "pd_itm_no",

          "pd_nm",

          "cu_charge_rt"

      ],

      "evidence": [

          {

              "binding": "etf_gl.product_name",

              "label": "정식 상품명",

              "source_table": "raw.etf_gl_master",

              "source_column": "pd_nm",

              "as_of": "2026-08-21",

              "as_of_basis": "...",

              "source_kind": "organizer"

          }

      ],

      "abstain": None

  },

  "evidence": [...],

  "abstain": None,

  "trace": [...]
```

  }

  실행 순서는 다음과 같습니다.

  완전일치 Entity 존재 확인

  → LogicalPlan을 제한된 SELECT SQL로 컴파일

  → READ ONLY 트랜잭션 실행

  → 행 수 검증

  → evidence 생성

  관련 코드: tools/rdb.py:187

### ⑥ verify_results

  결과 컬럼과 evidence 컬럼 순서를 비교합니다.

  정상:

  {

```
  "abstain": None,

  "trace": [..., "verify: PASS"]
```

  }

  불일치:

  {

```
  "abstain": {

      "code": "ABSTAIN_EVIDENCE_MISMATCH",

      "reason": "결과 컬럼과 evidence 계약 불일치: ..."

  },

  "trace": [..., "verify: ABSTAIN_EVIDENCE_MISMATCH"]
```

  }

### ⑦ render_answer

  세 가지 출력 경로가 있습니다.

  ABSTAIN:

  {

```
  "answer": "확인할 수 없음: {reason}"
```

  }

  정상 실행이지만 0건:

  {

```
  "answer": "주어진 조건과 완전일치하는 상품을 확인할 수 없습니다."
```

  }

  정상 결과:

  정식 상품명=... [raw.etf_gl_master.pd_nm, 기준일 2026-08-21];

  총보수=... [raw.etf_gl_[master.cu](http://master.cu)_charge_rt, 기준일 2026-08-21]

  답변 생성에는 LLM을 사용하지 않고 문자열 템플릿만 사용합니다.

## 4. 외부 최종 응답 형식

  to_response()는 내부 State 전체를 반환하지 않고 아래 5개 필드만 노출합니다.

  {

```
  "question_id": "",

  "question": "...",

  "retrieved_context": state["evidence"],

  "think_trace": state["trace"],

  "answer": state["answer"]
```

  }

  따라서 현재 실행 결과는:

  {

```
  "question_id": "",

  "question": "VOO의 정식 상품명과 총보수를 알려줘",

  "retrieved_context": [],

  "think_trace": [

      "intent: task=lookup domain=['etf_gl'] entities=1 constraints=0",

      "grounding: domain=etf_gl concepts=[...] unresolved=0",

      "validation: ABSTAIN_CUTOFF_VIOLATION"

  ],

  "answer": (

      "확인할 수 없음: etf_gl snapshot 2026-08-21가 "

      "cutoff 2026-07-11 이후입니다."

  )
```

  }

## 5. 현재 확인된 핵심 문제

  제공된 저장소 규칙은 cutoff를 2026-08-24로 정의하지만, 실제 런타임 설정은 아직 2026-07-11입니다.

- 런타임 cutoff: /mnt/c/Users/rladl/Desktop/2026_MIRAE_ASSET_AI-Festival/2026_10th_MIRAE-ASSET_AI-Festival/metadata/business_rules.json:3
- 데이터 snapshot: 같은 파일의 2026-08-21
- 차단 코드: tools/validate.py:43

  그 결과 현재는 모든 도메인의 2026-08-21 snapshot이 검증 단계에서 차단되어, 정상적인 질의도 RDB 실행까지 도달하지 못합니다.

  또한 ABSTAIN 검증 근거는 state["abstain"]["evidence"]에 있지만, 최종 retrieved_context는 state["evidence"]만 사용하므로 현재 응답에서는

  cutoff 근거가 빈 배열로 노출됩니다.

