# Agent Architecture Specification — 2026-08-26

핵심은 기존 실험 결과에 따라 목표 구조를 조금 수정하는 것입니다. 특히 `Plan & Routing`을 LLM의 자유 판단으로 두면 실험 5의 실패를 반복하므로, HCX Planner는 “실행계획 후보”만 만들고 결정론적 Route Guard가 승인해야 합니다.



# 목표 (0824)

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



# 현재(0825)

- 현재는 graph_only, graph_then_rdb, Vector 경로가 선언만 되어 있고 활성화되어 있지 않음
- 실제 실행 가능한 경로는 rdb_only뿐

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

state 초기값 :

```json
{
      "question_id": "",
      "question": "...",
      "intent": {}, // 1단계
      "metadata_context": {}, // 2단계
      "plan": {}, // 2단계
      "route": {},
      "results": {},
      "evidence": [],
      "abstain": None,
      "trace": [],
      "answer": ""
  }
```

예시 입력 및 출력

```
입력 : 
python3 -c 'from agent.agent_core import ask; print(ask("VOO의 정식 상품명과  총보수를 알려줘"))'

출력: 
{'question_id': '', 
 'question': 'VOO의 정식 상품명과 총보수를 알려줘', 
 'retrieved_context': 
  [{'binding': 'etf_gl.product_code', 'label': '상품번호', 'source_table': 'raw.etf_gl_master', 'source_column':
   'pd_itm_no', 'as_of': '2026-08-21', 'as_of_basis': '종가 기준일(du_clpr_base_dt 최빈값); 행별 개별값 존재', 'source_kind': 'organizer'}, 
 {'binding': 'etf_gl.product_name', 'label': '정식 상품명', 'source_table': 'raw.etf_gl_master', 'source_column': 'pd_nm', 
'as_of': '2026-08-21', 'as_of_basis': '종가 기준일(du_clpr_base_dt 최빈값); 행별 개별값 존재', 'source_kind': 'organizer'}, {'binding': 'etf_gl.expense_ratio', 'label': '총보수', 'source_table': 'raw.etf_gl_master', 'source_column': 'cu_charge_rt', 'as_of': '2026-08-21', 'as_of_basis': '종가 기준일(du_clpr_base_dt 최빈값); 행별 개별값 존재', 'source_kind': 'organizer'}], 

'think_trace': 
 ["intent: task=lookup domain=['etf_gl'] entities=1 constraints=0", 
 "grounding: domain=etf_gl concepts=['fp:productCode', 'fp:productName', 'fp:expenseRatio', 'fp:productGroup'] unresolved=0", 
'validation: PASS', 
'route: rdb_only steps=1 — verified single-domain RDB capability',
 'rdb: rows=1 status=PASS', 'verify: PASS'],

 'answer': 
'상품번호=VOO [raw.etf_gl_master.pd_itm_no, 기준일 2026-08-21]; 
정식 상품명=Vanguard 500 Index Fund;ETF [raw.etf_gl_master.pd_nm, 기준일 2026-08-21]; 
총보수=0.02 [raw.etf_gl_master.cu_charge_rt, 기준일 2026-08-21]'
}
```



&nbsp;

## [단계별 state 출력]

### **① extract_query_frame -  Query Frame**

관련 코드: `agent/nodes.py:13`, `agent/query_frame.py:507`

- HyperCLOVA X HCX-007을 한 번 호출합니다.
- LLM 원본은 *raw, 결정적 보정 내역은* guard에 저장됩니다.
- 예외가 나면 빈 Frame과 _error를 생성하고 안전 중단으로 이어집니다.

State 업데이트:

- `agent_core.py:53-55`에서 **ask()**가 만드는 초기 **state는 11개 키를 전부 빈 값으로 미리 채운다.** 
- 이후 **각 노드는 자기가 채운 키만 dict**로 돌려주고, **LangGraph가 그걸 state**에 덮어쓴다.

```json
초기          {"intent": {}, "metadata_context": {}, "plan": {}, ...}
                     ↓ extract_query_frame 이 {"intent": frame, "trace": [...]} 반환
1단계 후      {"intent": {14필드}, "metadata_context": {}, ...}   ← 아직 빈 dict
```

입력:

```
state["question"]
```

출력:

query_frame(14개 필드)

```
# 전체 모양

{
  "intent": {
    // ① 어디를          ② 뭘
    "domain_candidates": [], "task": "",
    "targets": [], "entities": [],
    // ③ 어떻게 거르고 정렬
    "constraints": [], "relations": [], "ordering": [], "limit": null, "temporal": {},
    // ④ 뭘 보여줄까
    "requested_fields": [], "evidence_requirements": [], "computation": [],
    // ⑤ 조심할 것
    "ambiguity": [], "validation_targets": [],
    // ⑥ 교정 기록 (계약 14개 밖)
    "_guard": [], "_raw": {}
  },
  "trace": []   // query_frame 산출물 아님. nodes.py가 단계마다 한 줄씩 쌓는 로그
}

한 줄 요약: ①②로 대상을 잡고, ③으로 걸러 정렬하고, ④를 보여주고, ⑤에 걸리면 답하지 않는다.
```

```json
# clean ver 
{
      "intent": {
          ## 어디를 확인할 지(범위)
          "domain_candidates": [...], // 4개의 상품 중 선택 예) ["etf_kr"] (채권/국내ETF/해외ETF/펀드)
          "task": "lookup | filter_rank | relation | ...", // 질문 종류 파악 (조회·필터·관계·비교·설명·추천)
          ## 무엇을 확인 할 지(대상)
          "targets": [...], // 상품의 종류 4개
          "entities": [...], // 질문에 나온 고유명/상품,회사,role 등 예) KODEX 200

          ## 어떻게 거를 지 (조건)
          "constraints": [...], // 거르는 조건 묶음 예) 총보수 <= 0.20 %
          "relations": [...], // 따라갈 연결고리 예)  ["ETF","편입증권","기업"]
          "ordering": [...], // 정렬 기준과 방향 예)  순자산 desc
          "limit": None, // 몇 개 보여줄 지 예) 10
          "temporal": {...}, // 언제 기준 인지 예) latest_snapshot(최신) / 특정날짜 / 기간 / 미래

          ## 무엇을 보여줄 지(추가 조건) 
          "requested_fields": [...], // 질문에서 보여달라고 한 항목 예) 총보수, 1년 수익률 등
          "computation": [...], // 추가 계산의 필요 여부 예) 중복도, 집중도, 비교 등 
          "evidence_requirements": [...], // 근거로 대라고 한 것 예) 기준일, 상품 번호 등

          ## 답변 시 주의 조건(감점 방지)
          "ambiguity": [...], // 기준 점이 모호한 질의 일 경우 예) 안전한 채권, 좋은 채권
          "validation_targets": [...], // 실재로 존재하는지 확인이 필요, 유형별로 ABSTAIN 코드가 처리 예) AAAA  등급 채권

          ## 교정 기록(LLM실수 방지 가드레일) * LLM이 실수하면 guard()가 수정
          "_guard": [...], // 고친 내역 목록 예)  "단일값 in → =="
          "_raw": {...} // LLM 원본 예) 고치기 전 raw값
      },
      "trace": [...]  // query_frame 산출물 아님. nodes.py가 단계마다 한 줄씩 쌓는 로그
  }
```



```
# 주석/예시 ver
{
  "intent": {                        // = query_frame.extract() 반환 (14계약 + _guard/_raw)
    "domain_candidates": ["etf_kr"], // enum: bond_kr|etf_kr|etf_gl|fund_pub. 애매하면 복수
    "task": "filter_rank",           // recommendation>relation>comparison>explanation>filter_rank>lookup
                                     //  guard: entities 없는 lookup→filter_rank, relations 있으면→relation
    "targets": [                     // 찾는 "상품군"만. 고유명·수식어는 여기 아님
      { "text": "국내 ETF" }
    ],
    "entities": [                    // 질의에 나온 고유명, 원문 그대로
      { "text": "KODEX 200",
        "role": "product",           // product|share_class|company|issuer|index|theme|manager|ticker|model
        "match_mode": "exact" }      // exact 기본 / partial 은 "비슷한"·"관련" 명시 시만
    ],
    "requested_fields": [            // 보여달라고 한 속성, 자연어 그대로 (채점 제외 슬롯)
      { "text": "총보수" }
    ],
    "constraints": [                 // 거르는 조건 1개 = 항목 1개
      { "raw": "총보수 0.20% 이하",   // 질문 원문 조각
        "field_text": "총보수",       // 사용자의 말 그대로. 동의어로 바꾸지 않음
        "operator": "<=",            // >= <= > < == != in contains exists (사용자가 말한 축 기준!)
                                     //  guard: 별칭 교정 + 단일값 in → ==
        "value_text": null,          // 문자·범주 비교값
        "value_num": 0.20,           // 숫자 비교값 (단위는 분리)
        "unit": "%",                 // 사용자가 쓴 단위. 없으면 null
        "kind": "quantitative",      // quantitative|categorical|boolean|qualitative
        "grounding_status": "resolved" } // resolved|unresolved
                                     //  guard: qualitative+resolved 는 모순 → unresolved 강제
    ],
    "relations": [                   // 따라가야 하는 관계 경로. path 없으면 버림
      { "raw": "…가 편입한 기업",
        "path": ["ETF", "편입증권", "기업"] } // 한국어 개체명만. 영문 식별자 금지
    ],
    "ordering": [
      { "field_text": "순자산",       // 사용자의 말
        "direction": "desc" }        // 기본 desc. asc 는 "낮은/적은/저렴한 순" 명시 시만
    ],
    "limit": 10,                     // "상위 10개"→10, "가장 큰"→1. 없으면 null (0·음수도 null)
    "temporal": {
      "kind": "latest_snapshot",     // latest_snapshot(기본)|as_of|period|future
                                     //  guard: as_of 인데 as_of_text 에 숫자 없으면 latest_snapshot 강등
      "raw": null,                   // 시점 표현 원문
      "as_of_text": null,            // 지목한 날짜 원문 ("2026-08-24")
      "window_text": null            // 기간 구간 원문 ("최근 6개월")
    },
    "computation": [                 // 조회·필터를 넘는 별도 연산일 때만. enum 밖은 버림
      { "kind": "overlap_ratio",     // overlap_ratio|concentration|dedup|compare|count|rank
        "raw": "중복도" }             //  "상위 N"·"…순"은 여기 아님 → limit/ordering
    ],
    "evidence_requirements": ["기준일", "상품번호"], // 근거로 요구한 것 (문자열 나열)

    "ambiguity": [                   // 말에 "기준이 없다" 쪽
      { "span": "안전한",
        "type": "underspecified_criterion" } // |ambiguous_domain|ambiguous_entity|relation_vs_mention
    ],
    "validation_targets": [          // 말은 명확한데 "실재가 의심된다" 쪽 (ambiguity 와 반대 축)
      { "type": "taxonomy_value",    // →ABSTAIN_INVALID_TAXONOMY
                                     // temporal_existence →ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF
                                     // entity_existence   →ABSTAIN_ENTITY_NOT_FOUND
                                     // future_value       →ABSTAIN_FUTURE_DATA
                                     // relation_domain_range →ABSTAIN_DOMAIN_MISMATCH
        "raw": "AAAA 등급",           // 그렇게 본 원문 조각
        "entity": null,              // 실재 확인 대상 상품명
        "relation": null,            // 도메인 위반 의심 관계
        "as_of": null },             // 시점 확인 기준 문자열
      // 판정은 여기서 안 한다 — check_tbox/verify 노드가 ABSTAIN 결정
      // use_audit=True 면 별도 audit() 결과로 이 배열 전체가 대체됨 (현재 nodes.py 는 False)
    ],

    "_guard": ["단일값 in → ==: '자산유형'='주식'"], // guard 가 고친 내역. 조용한 오라우팅 방지
    "_raw": { }                      // LLM 원본 응답. 구조 유효성은 보정 전 이걸로 잰다
    // "_error": "…"                 // nodes.py 가 예외 시 empty_frame() 에 덧붙임
  },

  "trace": [                         // query_frame 산출물 아님. nodes.py 가 노드마다 append
    "intent: task=filter_rank domain=['etf_kr'] entities=1 constraints=1"
  ]
}
```

[참고] validation_targets

```
validation_targets는 "확인 필요"라고 표시만 한다. 
실제로 "확인할 수 없음"이라고 답할지(ABSTAIN)는 뒤 단계가 정한다. 
유형 5개가 각각 ABSTAIN 코드 하나로 이어진다:

taxonomy_value        없는 값을 걸었다        → ABSTAIN_INVALID_TAXONOMY
temporal_existence    기준일에 있었나         → ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF
entity_existence      그런 상품이 있나        → ABSTAIN_ENTITY_NOT_FOUND
future_value          아직 안 나온 값이다     → ABSTAIN_FUTURE_DATA
relation_domain_range "VOO가 발행한 회사채"   → ABSTAIN_DOMAIN_MISMATCH
```

[참고] _guard, _raw : LLM이 실수하면 guard()가 수정

```
"_guard": [...], -- 고친 내역 목록 예)  "단일값 in → =="
"_raw": {...} -- LLM 원본 예) 고치기 전 raq값

- 지목한 상품이 없는데 lookup이면 → filter_rank (조회할 대상이 없으니까)
- relations가 있으면 → relation
- qualitative("안전한")인데 resolved라고 하면 → unresolved (모순이라서)
- 날짜 없는 as_of → latest_snapshot
```

VOO 질의의 관측값:

```
intent: task=lookup domain=['etf_gl'] entities=1 constraints=0
```



### **② ground_query -  LogicalPlan**

관련 코드: `agent/nodes.py:27`, `tools/schema_context.py:137`, `tools/schema_context.py:241`

- 1단계가 "사용자의 말"로 남겨둔 것을, 검증된 매핑표를 보고 "실제 컬럼 + 온톨로지 개념"으로 바꿔 물리적 DB와 연결한다. DB에서 찾은 것은 확정, 확정된게 없다면 unresolved에 남겨 LLM이 채워서 답변하지 않도록 한다.
- 1단계의 intent분석에서 DB를 참조하지않고 Query_frame을 출력하여, 사용자의 intent 를 분석하는데에 집중했다면
- 2단계의 metadata_context에서는 `etf_kr.expense_ratio`  +  `fp:expenseRatio` 등을 연결하여 "물리 컬럼 + 온톨로지 개념"을 연결해 실제로 물리컬럼을 연결한다.
- 즉, 1단계가 금지당했던 일(영문 컬럼명·fp: URI 만들기)을 2단계가 검증된 매핑표(metadata/schema_bindings.json)를 보고진행한다. 여기서의 내용에 따라 mapping된 컬럼정보로 인해 SQL,SPARQL의 오류가 줄어든다.

```
intent (1단계)                  metadata_context / plan (2단계)
"총보수"              ──────▶   etf_gl.expense_ratio  +  fp:expenseRatio
"VOO"                 ──────▶   etf_gl.ticker == "VOO"  (exact)
(사용자가 말 안 함)     ──────▶   etf_gl.group == "ETF"   ← ETN 혼입 방지, 규칙이 강제 주입
(사용자가 말 안 함)     ──────▶   as_of 2026-08-21        ← 실질 기준일
```



핵심 동작:

- ① 근거 있는 물리적 DB 연결
  - 추측이 아니라 metadata/schema_bindings.json(검증된 logical↔physical 매핑)과 business_rules.json을 조회해서만 컬럼을 붙인다. 
  - 1단계가 fp:나 영문 컬럼명을 만드는 걸 금지당했던 이유가 여기서 해소된다.
- ② 사용자가 말 안 한 안전장치 주입
  - mandatory_filters(ETF에서 ETN 배제), default_order, ID tie-breaker, as_of 실질 기준일을 걸러낸다
- ③ 온톨로지 스키마 기록
  - `concepts에 fp: URI`를 모아 답변 evidence가 인용할 근거를 만든다.
- ④ 실패 사유 기록
  - 매핑이 없으면  unresolved에 사유를 적는다. 
  - 다음 노드(validate_query)가 이걸 보고 ABSTAIN을 결정한다.
- 여전히 안 하는 것: 
  - SQL 문자열 생성
    - LogicalPlan은 "무엇을 뽑을지"까지고, SELECT ... WHERE ... 조립은 4단계 `rdb.execute`의 일이다.



State 업데이트:

```
초기          {"intent": {}, "metadata_context": {}, "plan": {}, ...}
                     ↓ extract_query_frame 이 {"intent": frame, "trace": [...]} 반환
1단계 후      {"intent": {14필드}, "metadata_context": {}, ...}   ← 아직 빈 dict
                     ↓ ground_query 가 {"metadata_context": lp, "plan": lp, "trace": [...]} 반환
2단계 후      {"intent": {14필드}, "metadata_context": {LogicalPlan}, "plan": {LogicalPlan(같은 것)}, ...}
```

- plan과 metadata_context에는 같은 객체를 출력한다, 단 읽는 쪽이 다르다. metadata_context는 "근거를 붙인 논리"에 대한 증거고, plan은 "이렇게 데이터를 뽑아라"라는 명령이므로, 같은 객체를 2개의 state output에 기록한다.

```
metadata_context ──▶ validate_query   (nodes.py:36)  검증한다
plan             ──▶ select_route     (nodes.py:43)  실행 경로를 고른다──▶ rdb.execute      (nodes.py:56)  실행한다
```

- 2개를 따로 만들경우, 검증은 metadata_context에서 통과하지만, 실제 실행은 plan에서 진행하기에, `mandatory_filters(ETN 배제)`등의 필터링이 검증본에는 있고, 실행본에는 빠지는 사고가 생길 수있다. 추후에 둘이 실제로 갈라져야 할 일(예: metadata_context는 후보 여러 개를 담고 plan은 그중 하나로 확정)이 생기면, 그때 ground_query가 두 값을 명시적으로 따로 만든다.



출력 업데이트:

```
{
 "metadata_context": logical_plan,
 "plan": logical_plan,
 "trace": [...]
}
```



LogicalPlan 형식:

```json
// clean_ver
{
 "domain": "etf_gl",
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
              "binding": "etf_gl.group",
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

```
// 주석 ver
{
  // ─── 어디를 / 무엇을 ─────────────────────────────────────────
  "domain": "etf_gl",
  // 4개 중 하나로 확정. intent.domain_candidates 가 복수였어도 원문과 대조해 1개로 좁힌다.
  // 못 좁히면 → null + unresolved 채우고 나머지 전부 빈 값으로 즉시 반환 (schema_context.py:143)
  // intent: ["etf_kr","etf_gl"]  →  plan: "etf_gl"   ("VOO" 티커라서)

  "task": "lookup",
  // intent.task 를 그대로 복사만 한다. 여기서 재판정하지 않음.
  // 다만 task 에 따라 아래 동작이 갈린다:
  //   filter_rank·comparison  → order 비었으면 default_order 자동 주입
  //   fund_pub + comparison   → 운용사코드·대표코드 컬럼 자동 추가

  // ─── 어떤 상품을 지목했나 ────────────────────────────────────
  "entities": [
    { "mode": "exact",                 // exact | fund_classes (펀드 클래스 비교 전용)
      "binding": "etf_gl.ticker",      // 어느 컬럼으로 찾을지. 도메인+role 로 결정:
                                       //   etf_gl + role:ticker → etf_gl.ticker
                                       //   etf_kr               → etf_kr.short_name
                                       //   그 외                 → 그 도메인의 상품명 컬럼
      "value": "VOO" }                 // intent.entities[0].text 원문 그대로
  ],
  // ★ 지금은 첫 번째 엔티티 1개만 쓴다 (예외: fund_pub 클래스 비교는 stem+classes 로 묶음)
  //    intent: [{"text":"VOO","role":"ticker","match_mode":"exact"}]

  // ─── 무엇을 보여줄까 ─────────────────────────────────────────
  "select": [
    "etf_gl.product_code",   // 상품ID — 항상 자동 포함 (근거 표시 필수)
    "etf_gl.product_name",   // 상품명 — 항상 자동 포함
    "etf_gl.expense_ratio"   // ← intent.requested_fields "총보수" 가 붙은 결과
  ],
  // 출처: intent.requested_fields + intent.evidence_requirements 를 best_binding() 으로 매핑
  // 도메인별 자동 동반 컬럼:
  //   etf_kr.expense_ratio 뽑으면 → expense_source 동반 (총보수 81.9% 결측, 출처 표기 필요)
  //   bond.rating_rank 뽑으면     → credit_rating 앞에 삽입 (순위값만 보여주면 못 읽음)
  //   etf_gl 가격·거래량 질의     → close_date 동반 (실질 기준일 표기)

  // ─── 어떻게 거를까 ───────────────────────────────────────────
  "filters": [
    { "binding": "etf_gl.group",  // 물리 컬럼
      "operator": "==",           // intent.constraints 의 부등호. 여기서 물리 방향으로 뒤집힘
                                  //   intent  "신용등급 >= AA-"
                                  //   plan    bond.rating_rank <= 4   ← 축 반전은 이 단계의 일
      "value": "ETF" }            // 정규화된 값
  ],
  // ★ 두 출처가 합쳐진다:
  //   (a) mandatory_filters — 사용자가 말 안 해도 규칙이 강제 주입. 위 group=='ETF' 가 이것
  //       (국내ETF 마스터의 ETN 545종 혼입 차단)
  //   (b) intent.constraints — 사용자가 말한 조건. 매핑 실패하면 filters 가 아니라 unresolved 로
  //   중복은 _append_unique 로 제거. 엔티티와 값이 같은 constraint(모델의 중복 생성)는 버림

  // ─── 어떻게 정렬 / 몇 개 ─────────────────────────────────────
  "order": [],
  // intent.ordering 의 field_text 를 정렬 가능 컬럼으로 매핑 → {binding, direction, nulls?}
  //   매핑 실패 → unresolved "정렬 binding 미확정: …"
  //   비었는데 task 가 filter_rank·comparison → default_order 자동 주입
  //   있으면 → 맨 뒤에 상품ID asc 를 tie-breaker 로 추가 (같은 값일 때 결과 순서 고정)
  // 예: [{"binding":"etf_kr.aum","direction":"desc","nulls":"last"},
  //      {"binding":"etf_kr.product_code","direction":"asc"}]

  "limit": null,
  // intent.limit 을 그대로 복사. 변형 없음

  // ─── 못 박지 못한 것 ─────────────────────────────────────────
  "unresolved": [],
  // 조용히 빠지면 오답이 되는 것들을 여기 모은다. 다음 노드 validate_query 가 읽고 ABSTAIN 결정
  //   "Query Frame 추출 실패"        ← 1단계가 죽음 (_error 있음)
  //   "도메인 미확정: …"              ← 4개 중 어디인지 못 정함
  //   "정렬 binding 미확정: 샤프지수"  ← 그런 컬럼 없음
  //   constraint 매핑 실패 사유       ← _constraint() 가 돌려준 에러

  // ─── 근거로 인용할 개념 ──────────────────────────────────────
  "concepts": [
    "fp:productCode", "fp:productName", "fp:expenseRatio", "fp:productGroup"
  ],
  // select + filters + order 에서 실제로 쓴 binding 만 역참조해 fp: URI 로 모음 (중복 제거, 순서 보존)
  // ★ 실제로 참조된 것만 들어간다 — 답변 evidence 가 "무슨 개념에 근거했나"를 여기서 인용

  // ─── 언제 기준인가 ───────────────────────────────────────────
  "as_of": {
    "value": "2026-08-21",        // 배포일(08-24)이 아니라 도메인별 실질 기준일
    "basis": "종가 기준일..."      // 왜 그 날짜인지 (답변에 그대로 노출)
  }
  // intent.temporal 에서 오는 게 아니라 business_rules.json 의 domain_as_of[domain] 고정값
}
```



**[intent → plan 연결 흐름]**


| intent (사용자 말)                           | → plan (스키마) | 변환                                            |
| ---------------------------------------- | ------------ | --------------------------------------------- |
| domain_candidates 복수                     | domain 1개    | 원문과 대조해 좁힘                                    |
| task                                     | task         | 그대로 복사                                        |
| entities[0]                              | entities     | role→binding, text→value                      |
| requested_fields + evidence_requirements | select       | best_binding 매핑 + 동반컬럼                        |
| constraints                              | filters      | mandatory_filters 주입, 부등호 축 반전                |
| ordering                                 | order        | best_binding 매핑 + default_order + tie-breaker |
| limit                                    | limit        | 그대로 복사                                        |
| temporal                                 | —            | 안 씀. as_of는 규칙 파일 고정값                         |
| (매핑 실패 전부)                               | unresolved   | —                                             |
| (참조된 binding)                            | concepts     | —                                             |


 VOO 관측값:

```
grounding:
domain=etf_gl
  concepts=['fp:productCode', 'fp:productName',
            'fp:expenseRatio', 'fp:productGroup']
  unresolved=0
```



&nbsp;

## ③ validate_query — 실행 전 결정적 검증(python규칙)

관련 코드: `agent/nodes.py:35`, `tools/validate.py:15`

>  LLM을 쓰지 않고, 규칙만으로 "이 질문은 답하면 안 된다"를 확정한다. 걸리면 DB를 건드리기 전에 즉시 중단한다.



핵심 3가지:

- ① LLM 없음이 아닌 정규식과 규칙파일을 통해서 validation layer를 기반으로 검증한다.
  - 정규식 + 규칙 파일(metadata/business_rules.json)을 참조하여, 같은 질문은 항상 같은 판정이 나온다.
- ② 1단계 판단에서 잘못 의심했던 부분을 바로잡는다.
  - intent.validation_targets는 "확인 필요" 표시일 뿐이고, 여기서 원문과 LogicalPlan을 다시 본다(tools/validate.py:16 주석). 1단계가 놓쳐도 여기서 잡히고, 1단계가 잘못 의심해도 여기서 무시된다.
- ③ DB접속을 사전 차단시킨다.
  - 통과 못 하면 `select_route·execute_rdb·verify_results`를 건너뛰고 바로 render_answer를 출력한다 즉, DB 접속 자체를 안 한다.

```
ground_query ──▶ validate_query ──┬─ abstain 있음 ──▶ render_answer  (DB 안 감)
                                  └─ None        ──▶ select_route ──▶ execute_rdb ──▶ verify_results ──▶ render_answer
```



&nbsp;

검증 항목: 위에서부터 먼저 걸리는 하나에서 멈춘다, 순서가 곧 우선순위다. 하나 걸리면 즉시 return, 아래는 안 본다.

- 도메인 확정 여부
- 요청 날짜가 cutoff 이후인지
- 신용등급 허용값
- 미래 실현값
- 관계 domain/range
- 미해소 binding
- 데이터 snapshot이 cutoff 이후인지



#: 1

검증: 도메인 확정 여부

보는 것: plan.domain 이 null인가

나오는 code: ABSTAIN_UNRESOLVED_QUERY

관련 코드: tools/validate.py:18

────────────────────────────────────────

#: 2

검증: 요청 날짜가 cutoff 이후

보는 것: 원문에서 20xx-xx-xx 추출

나오는 code: ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF

관련 코드: tools/validate.py:24

────────────────────────────────────────

#: 3

검증: 신용등급 허용값

보는 것: 원문 신용등급 XX → rating_rank 19개에 있나

나오는 code: ABSTAIN_INVALID_TAXONOMY

관련 코드: tools/validate.py:31

────────────────────────────────────────

#: 4

검증: 미래 실현값

보는 것: 원문 20xx년 &gt; cutoff 연도 AND "확정" 포함

나오는 code: ABSTAIN_FUTURE_DATA

관련 코드: tools/validate.py:35

────────────────────────────────────────

#: 5

검증: 관계 domain/range

보는 것: etf_gl 인데 "발행한 회사채"

나오는 code: ABSTAIN_DOMAIN_MISMATCH

관련 코드: tools/validate.py:38

────────────────────────────────────────

#: 6

검증: 미해소 binding

보는 것: plan.unresolved 가 비었나

나오는 code: ABSTAIN_UNRESOLVED_QUERY

관련 코드: tools/validate.py:41

────────────────────────────────────────

#: 7

검증: 데이터 snapshot이 cutoff 이후

보는 것: [plan.as](http://plan.as)_of.value vs data_cutoff

나오는 code: ABSTAIN_CUTOFF_VIOLATION

관련 코드: tools/validate.py:44

────────────────────────────────────────

#: —

검증: 전부 통과

보는 것:

나오는 code: None

관련 코드: tools/validate.py:50



State 업데이트:

- validate_query는 abstain과 trace 2개를 반환한다.
- 1,2단계의 출력물인 `intent·metadata_context·plan`은 읽기 전용으로, 수정하지않는다 따라서 뒤 단계에서 그대로 읽힌다.

```
초기          {"abstain": None, ...}
↓ ground_query 가 metadata_context / plan 채움
2단계 후      {"metadata_context": {LogicalPlan}, "abstain": None, ...}
                     ↓ validate_query 가 {"abstain": …, "trace": [...]} 반환
3단계 후      {"abstain": {code·reason·evidence}  또는  None(통과), ...}
```



출력 업데이트 :

```
{
 "abstain": None | {
      "code": "ABSTAIN_...",
      "reason": "...",
      "evidence": [...]
      },
 "trace": [...]
  }
```

```
{
  "abstain": {
    // null 이면 통과 — 아무 규칙에도 안 걸렸다는 뜻 (tools/validate.py:50)
    "code": "ABSTAIN_CUTOFF_VIOLATION",
    // 왜 답하지 않는지의 유형. 사유를 구분해야 정답이 된다 (AGENTS.md "답변불가 판정")

    "reason": "etf_gl snapshot 2026-08-21가 cutoff 2026-07-11 이후입니다.",
    // 사람이 읽을 사유. 실제 값을 박아 넣어 "왜"가 답변에 그대로 나가게 한다

    "evidence": [
      { "as_of": "2026-08-21",      // 실제로 본 값
        "cutoff": "2026-07-11" }    // 비교 기준
      // 규칙마다 모양이 다르다:
      //   taxonomy  → {"source":"ontology/common.ttl","rule":"ratingRank 1(AAA)~19(C)"}
      //   관계 위반  → {"source":"ontology/bond_kr.ttl","rule":"issuedBy domain Bond"}
      //   미해소     → evidence 없이 reason 에 unresolved 문자열을 ";" 로 이어붙임
    ]
  },
  "trace": ["validation: ABSTAIN_CUTOFF_VIOLATION"]
  // 통과하면 "validation: PASS" (agent/nodes.py:38)
}
```



VOO 질의 실제 결과 : 

```
{
  "abstain": {
    "code": "ABSTAIN_CUTOFF_VIOLATION",              // 7번 규칙에서 걸림
    "reason": "etf_gl snapshot 2026-08-21가 cutoff 2026-07-11 이후입니다.",
    "evidence": [{ "as_of": "2026-08-21", "cutoff": "2026-07-11" }]
  },
  "trace": ["validation: ABSTAIN_CUTOFF_VIOLATION"]
}

>> 1~6은 전부 통과했다 — 도메인 etf_gl 확정, 원문에 날짜·등급·연도·"발행한 회사채" 없음, unresolved 빔. 마지막 7번에서 plan.as_of.value(2026-08-21)가 data_cutoff(2026-07-11)보다 뒤라 걸렸다.
이후 select_route·execute_rdb·verify_results를 건너뛰고 바로 render_answer로 간다.
```



&nbsp;

⚠ data_cutoff 수정 필요 &gt;&gt; 모두 2026-08-24로 수정완료

관련 코드: `metadata/business_rules.json:3`, `metadata/business_rules.json:4-9`

```
"data_cutoff": "2026-07-11",
"domain_as_of": {
  "bond_kr": {"value": "2026-08-21", ...},
  "etf_kr":  {"value": "2026-08-21", ...},
  "etf_gl":  {"value": "2026-08-21", ...},
  "fund_pub":{"value": "2026-08-21", ...}
}
```

4개 도메인 전부 2026-08-21 &gt; 2026-07-11 이므로, 7번 규칙이 질문 내용과 무관하게 항상 발동한다. VOO만의 문제가 아니라 이 파이프라인은 지금 어떤 질문에도 답하지 못한다.

원인은 data_cutoff가 07-11 배포본 시절 값 그대로라는 것이다. [AGENTS.md](http://AGENTS.md) 절대규칙 2는 기준일을 2026-08-24로 못박고 있고, domain_as_of의 basis도 전부 "2026-08-24 배포본"이라고 적혀 있다. query_[frame.py](http://frame.py):540의 audit 프롬프트에도 2026-07-11이 남아 있다.



&nbsp;

&nbsp;

---

## ④ select_route - 실행 가능한 것만 통과(python규칙)

관련 코드: `agent/nodes.py:42`, `tools/route.py:21`

> "답하면 안 되는가"(③)를 통과한 질문에 대해, 이제 "지금 우리가 실행할 수 있는가"를 묻는다. 
>
> 못 하면 못 한다고 말한다 — 되는 척 근사치를 내지 않는다.



- ③과 ④는 둘 다 ABSTAIN을 출력으로 가짐


|                  | 묻는 것     | 실패 뜻         | 예            |
| ---------------- | -------- | ------------ | ------------ |
| ③ validate_query | 답해도 되는가  | 질문·데이터가 잘못됨  | AAAA 등급, 미래값 |
| ④ select_route   | 답할 수 있는가 | 우리 구현이 아직 없음 | 그래프 경로 미구현   |




핵심 3가지:

- ① LLM 없고, ③과 마찬가지로 규칙만 설정한다.

- intent와 plan을 보고 4개 관문을 순서대로 통과시킨다.

- ②  Graph/Vector 경로는 enum에 이름만 있고 실제로는 안 나온다(tools/route.py:24 주석). 

- vertical slice가 통과하기 전까지 활성화하지 않는다는 뜻이다. 지금 나오는 값은 rdb_only 아니면 unsupported 둘뿐이다

- ③ 계약을 코드로 강제 — step 수 상한 3을 assert로 박아둔다(tools/route.py:41).

```
validate_query ─(통과)─▶ select_route ──┬─ rdb_only     ──▶ execute_rdb ──▶ verify_results ──▶ render_answer
                                        └─ unsupported  ──▶ render_answer  (DB 안 감)
분기 판정: agent/agent_core.py:15 — route.query_type == "rdb_only" 인지만 본다.
```

State 업데이트:

```
3단계 후      {"route": {}, "abstain": None, ...}
↓ select_route 가 {"route": …, "abstain": …, "trace": [...]} 반환
4단계 후      {"route": {query_type·execution_plan·reason}, "abstain": None 또는 {...}, ...}
```

                     

- route·abstain·trace 3개만 반환한다. abstain을 항상 반환하는 게 중요하다
- 통과하면 None으로 명시적으로 덮어써서, 앞 단계의 잔재가 남지 않는다.

출력 업데이트 :

```
{
  "route": {
    "query_type": "rdb_only",
    // enum 6개 (tools/route.py:7): rdb_only | tbox_validate_only | graph_only
    //                             | graph_then_rdb | graph_then_rdb_vector | unsupported
    // ★ 지금 실제로 나오는 건 rdb_only 와 unsupported 둘뿐. 나머지 4개는 예약된 이름

    "execution_plan": [
      { "id": "A",            // 단계 식별자
        "engine": "rdb",      // 어느 엔진이 실행할지 (rdb / graph / vector)
        "depends_on": [] }    // 선행 단계 id. 빈 배열 = 의존 없음, 바로 실행 가능
      // 최대 3단계 (MAX_PLAN_STEPS, tools/route.py:9) — assert 로 강제 (:41)
      // rdb_only 는 항상 1단계 고정. graph_then_rdb 가 열리면
      //   [{"id":"A","engine":"graph","depends_on":[]},
      //    {"id":"B","engine":"rdb","depends_on":["A"]}] 형태가 된다
    ],

    "reason": "verified single-domain RDB capability"
    // 왜 이 경로인지. unsupported 면 어느 관문에서 걸렸는지가 여기 들어가고
    // 그대로 abstain.reason 으로 복사된다 (agent/nodes.py:47)
  },

  "abstain": null,
  // rdb_only 면 null. unsupported 면 code + reason 2키만 (evidence 없음)

  "trace": ["route: rdb_only steps=1 — verified single-domain RDB capability"]
}
```

  정상 RDB 경로:

```
 {
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
}
```



  미지원이면:

```
{ "route": {
      "query_type": "unsupported",
      "execution_plan": [],
      "reason": "..."
  },
  "abstain": {
      "code": "ABSTAIN_UNSUPPORTED_ROUTE",
      "reason": "..."
  }}
```

  



통과 관문 4개 — 위에서부터 먼저 걸리는 하나. 전부 통과해야만 rdb_only가 나온다.


| #   | 관문            | 조건                                                 | reason                                | 관련 코드             |
| --- | ------------- | -------------------------------------------------- | ------------------------------------- | ----------------- |
| 1   | binding 완전 해소 | plan.domain 있고 plan.unresolved 비었는지                | "도메인 또는 binding이 해소되지 않았습니다."         | tools/route.py:29 |
| 2   | 단일 도메인        | intent.domain_candidates가 정확히 1개인가                 | "여러 상품 도메인을 함께 묻는 경로는 아직 지원하지 않습니다."  | tools/route.py:31 |
| 3   | 지원 task       | intent.task ∈ {lookup, filter_rank, comparison} 인가 | "현재 RDB가 지원하지 않는 task입니다: relation"   | tools/route.py:33 |
| 4   | 지원 계산         | intent.computation의 kind가 전부 {compare} 안인가         | "현재 지원하지 않는 계산입니다: ['overlap_ratio']" | tools/route.py:36 |
| —   | 전부 통과         | —                                                  | rdb_only                              | tools/route.py:38 |


막히는 task 3개는 relation(그래프 필요) · explanation · recommendation이고, 막히는 계산 5개는 overlap_ratio · concentration · dedup · count · rank입니다. 계산은 compare만 통과합니다. 이게 지금 RDB vertical slice의 실제 경계입니다.



route 출력 구조

```json
{
  "route": {
    "query_type": "rdb_only",
    "execution_plan": [
      { "id": "A",           // 단계 식별자
        "engine": "rdb",     // rdb / graph / vector
        "depends_on": [] }   // 선행 단계 id. 빈 배열 = 바로 실행 가능
      // 최대 3단계 (MAX_PLAN_STEPS, tools/route.py:9) — assert로 강제 (:41)
      // rdb_only는 항상 1단계
      // graph_then_rdb라면
      //   [{"id":"A","engine":"graph","depends_on":[]},
      //    {"id":"B","engine":"rdb","depends_on":["A"]}]
    ],
    "reason": "verified single-domain RDB capability"
    // 왜 이 경로인지. unsupported면 걸린 관문의 사유가 여기 들어가고
    // 그대로 abstain.reason으로 복사된다 (agent/nodes.py:47)
  },
  "abstain": null,
  // rdb_only면 null. unsupported면 code + reason 2키만 (evidence 없음)
  "trace": ["route: rdb_only steps=1 — verified single-domain RDB capability"]
}

```

미지원 예시

```json
// "삼성전자를 편입한 ETF 알려줘"  →  intent.task = "relation"
{
  "route": {
    "query_type": "unsupported",
    "execution_plan": [],   // 실행할 게 없으니 빈 배열
    "reason": "현재 RDB가 지원하지 않는 task입니다: relation"   // 3번 관문에서 걸림
  },
  "abstain": {
    "code": "ABSTAIN_UNSUPPORTED_ROUTE",   // 코드는 하나. 어느 관문인지는 reason이 말한다
    "reason": "현재 RDB가 지원하지 않는 task입니다: relation"   // route.reason 그대로 복사
    // ★ evidence 키가 없다 — ③의 ABSTAIN과 구조가 다름
  },
  "trace": ["route: unsupported steps=0 — 현재 RDB가 지원하지 않는 task입니다: relation"]
}

```

이 경우 render_answer로 직행하고 execute_rdb · verify_results는 실행되지 않습니다.



&nbsp;

&nbsp;

### ⑤ execute_rdb — LogicalPlan → 제한된 SELECT → evidence

  관련 코드: agent/nodes.py:53, tools/rdb.py:187, tools/rdb.py:94

 

>  ④가 rdb_only를 통과시킨 계획을, 검증된 binding만 써서 SQL로 컴파일해 실제로 조회하고, 각 값에 출처·기준일을 붙여 돌려준다.

   

  핵심 4가지:

  - ① 문자열 조립 금지 — psycopg.sql의 Identifier/SQL 조합으로만 쿼리를 만들고, 값은 전부 %s 파라미터로 나간다. 사용자 입력이 SQL 문법에 닿지 않는다.

  - ② 등록된 binding만 — 매핑표(schema_bindings.json)에 없는 binding은 컴파일 자체가 실패(ValueError)한다. 게다가 binding마다 usage가 있어 select/filter/sort 용도별로 따로 허가된다.

  - ③ 읽기 전용 + 타임아웃 — SET TRANSACTION READ ONLY + statement_timeout. 15초 응답 예산과 데이터 동결 규칙을 엔진 레벨에서 보장한다.

  - ④ evidence는 rows와 함께 나온다 — 답변 생성 단계가 나중에 지어내는 게 아니라, 컴파일 시점에 select한 컬럼마다 출처·기준일이 확정된다.

```
select_route ─(rdb_only)─▶ execute_rdb ──▶ verify_results ──▶ render_answer
                                │
                                └─ 3곳에서 ABSTAIN 가능 (엔티티 0건 / 행 초과 / 실행 실패
```

  

  출력 업데이트:

  

```
{  "results": {
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
}
```

State 업데이트:

- results 안에도 evidence가 있고 State 최상위에도 evidence가 있다 — 최상위 것이 주최측 응답 규격(retrieved_context)으로 그대로 나간다(agent/agent_core.py:47).

```
4단계 후      {"route": {rdb_only}, "results": {}, "evidence": [], "abstain": None, ...}
                     ↓ execute_rdb 가 {"results"·"evidence"·"abstain"·"trace"} 반환
5단계 후      {"results": {rows·columns·evidence·abstain}, "evidence": [...], "abstain": None 또는 {...}}
```

  



출력 : 

```
{
  "results": {
    "rows": [                              // 조회 결과. ABSTAIN 이면 빈 배열로 비운다
      { "pd_cd": "VOO", "pd_nm": "Vanguard S&P 500 ETF", "cu_charge_rt": 0.03 }
    ],
    "columns": ["pd_cd", "pd_nm", "cu_charge_rt"],
    // plan.select 순서 그대로의 물리 컬럼명 (tools/rdb.py:184)

    "evidence": [                          // select 한 컬럼 1개당 1건 (tools/rdb.py:177)
      { "binding": "etf_gl.expense_ratio", // LogicalPlan 의 논리 이름
        "label": "총보수",                  // 사람이 읽을 이름
        "source_table": "raw.etf_gl_master",// 출처 테이블
        "source_column": "cu_charge_rt",   // 출처 컬럼  ← AGENTS.md "모든 수치에 출처 컬럼"
        "as_of": "2026-08-21",             // plan.as_of.value 복사
        "as_of_basis": "종가 기준일...",    // 왜 그 날짜인지
        "source_kind": "organizer" }       // raw. 로 시작하면 organizer(주최측),
                                           // 아니면 derived_from_organizer(파생)
                                           // ← 주최측 우선 규칙을 답변에서 구분하기 위한 표시
    ],
    "abstain": null
  },

  "evidence": [ /* results.evidence 와 같은 것을 State 최상위로 올림 */ ],
  "abstain": null,
  "trace": ["rdb: rows=1 status=PASS"]     // ABSTAIN 이면 status=ABSTAIN
}
```



실행 순서


| #   | 단계           | 하는 일                                | 관련 코드            |
| --- | ------------ | ----------------------------------- | ---------------- |
| 1   | 타임아웃 설정      | SET statement_timeout               | tools/rdb.py:189 |
| 2   | 엔티티 해소       | 지목 상품이 실제 있는지 먼저 조회                 | tools/rdb.py:190 |
| 3   | 컴파일          | LogicalPlan → SQL + params          | tools/rdb.py:193 |
| 4   | 읽기 전용 트랜잭션   | SET TRANSACTION READ ONLY           | tools/rdb.py:195 |
| 5   | 조회 + dict 변환 | —                                   | tools/rdb.py:197 |
| 6   | 행 수 상한 검사    | —                                   | tools/rdb.py:200 |
| 7   | 반환           | rows · columns · evidence · abstain | tools/rdb.py:201 |


2가 3보다 먼저인 이유는 엔티티가 없으면 컴파일할 것도 없기 때문입니다. "KODEX 200"이 0건이면 ABSTAIN_ENTITY_NOT_FOUND로 즉시 끝나고 유사명으로 대체하지 않습니다 ([AGENTS.md](http://AGENTS.md) "완전일치 우선", 유사명 14~18건 존재).

ABSTAIN 3종


| 시점   | code                     | 조건                 | 관련 코드                                   |
| ---- | ------------------------ | ------------------ | --------------------------------------- |
| 조회 전 | ABSTAIN_ENTITY_NOT_FOUND | 완전일치 상품 0건         | tools/validate.py:53 ← tools/rdb.py:190 |
| 조회 후 | ABSTAIN_RESULT_TOO_LARGE | 행 수 상한 초과          | tools/validate.py:60 ← tools/rdb.py:200 |
| 예외   | ABSTAIN_EXECUTION_FAILED | 컴파일 · 연결 · 타임아웃 실패 | agent/nodes.py:57                       |




compile_plan은 "안 되는 것"을 조용히 무시하지 않고 전부 예외로 만듭니다.


| #   | 관문                | 실패 메시지                       | 관련 코드            |
| --- | ----------------- | ---------------------------- | ---------------- |
| 1   | 미해소 plan 거부       | "미해소 LogicalPlan은 컴파일할 수 없다" | tools/rdb.py:95  |
| 2   | 등록된 binding만      | "미등록 binding: …"             | tools/rdb.py:105 |
| 3   | SELECT 용도 허가      | "SELECT 금지 binding: …"       | tools/rdb.py:107 |
| 4   | 허용된 JOIN만         | "허용되지 않은 JOIN: A ↔ B"        | tools/rdb.py:120 |
| 5   | JOIN 개수 상한        | "JOIN 상한 초과"                 | tools/rdb.py:131 |
| 6   | entity mode 해소    | "해소되지 않은 entity mode: …"     | tools/rdb.py:150 |
| 7   | FILTER 용도 허가      | "FILTER 금지 binding: …"       | tools/rdb.py:154 |
| 8   | 지원 operator만 (6개) | "지원하지 않는 operator: …"        | tools/rdb.py:156 |
| 9   | SORT 용도 허가        | "SORT 금지 binding: …"         | tools/rdb.py:164 |
| 10  | 정렬 방향 ASC/DESC    | "정렬 방향 오류: …"                | tools/rdb.py:168 |
| 11  | LIMIT 안전 상한       | min(limit, max_rows)로 강제     | tools/rdb.py:175 |


3 · 7 · 9가 따로 있는 이유는 같은 컬럼이라도 용도별로 못 쓰는 경우가 있기 때문입니다. 괴리율 더미(전 종목 0.00)처럼 정렬하면 무의미한 순서가 나오는 컬럼을 usage로 막습니다.



&nbsp;

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





## 코드 

### ① extract_query_frame — Query Frame


| 항목                                    | 관련 코드                    |
| ------------------------------------- | ------------------------ |
| 노드 본체 (intent 반환)                     | agent/nodes.py:13        |
| 예외 시 empty_frame() + _error           | agent/nodes.py:17        |
| LLM 1회 호출 → guard                     | agent/query_frame.py:507 |
| 14필드 목록                               | agent/query_frame.py:72  |
| JSON 스키마 (슬롯 구조)                      | agent/query_frame.py:95  |
| 프롬프트 (슬롯별 규칙 정의)                      | agent/query_frame.py:137 |
| 빈 프레임 기본값                             | agent/query_frame.py:266 |
| guard() 결정적 후처리                       | agent/query_frame.py:316 |
| ↳ qualitative + resolved → unresolved | agent/query_frame.py:365 |
| ↳ 단일값 in → ==                         | agent/query_frame.py:370 |
| ↳ 날짜 없는 as_of → latest_snapshot       | agent/query_frame.py:407 |
| ↳ entities 없는 lookup → filter_rank    | agent/query_frame.py:449 |
| ↳ relations 있으면 (처리 내용 확인 필요)         | agent/query_frame.py:452 |
| validation_targets → ABSTAIN 코드 매핑    | agent/query_frame.py:64  |
| D4 누출 검사 (fp: · 영문 컬럼)                | agent/query_frame.py:459 |
| 3단계 Planner용 (항목명 확인 필요)              | agent/query_frame.py:478 |
| 별도 감사 프롬프트                            | agent/query_frame.py:540 |
| 별도 감사 호출 (use_audit=True)             | agent/query_frame.py:575 |




### ② ground_query — LogicalPlan


| 항목                                       | 관련 코드                       |
| ---------------------------------------- | --------------------------- |
| 노드 본체 (metadata_context · plan 동일 객체 반환) | agent/nodes.py:32           |
| ground(question, intent) 진입              | tools/schema_context.py:137 |
| 매핑표 로드 (schema · rules · binding)        | tools/schema_context.py:23  |
| LogicalPlan 최종 조립                        | tools/schema_context.py:241 |


LogicalPlan 키별


| LogicalPlan 키                         | 관련 코드                                         |
| ------------------------------------- | --------------------------------------------- |
| domain 확정                             | tools/schema_context.py:142                   |
| ↳ 1단계 실패 시                            | tools/schema_context.py:139                   |
| ↳ 도메인 미확정 시 조기 반환                     | tools/schema_context.py:143                   |
| select 기본 (ID · 상품명)                  | tools/schema_context.py:147                   |
| ↳ requested_fields · evidence 매핑      | tools/schema_context.py:148                   |
| ↳ etf_gl 가격질의 → close_date 동반         | tools/schema_context.py:156                   |
| ↳ etf_kr 총보수 → expense_source 동반      | tools/schema_context.py:159                   |
| ↳ bond rating_rank → credit_rating 동반 | tools/schema_context.py:212                   |
| ↳ fund_pub 비교 시 운용사 · 대표코드            | tools/schema_context.py:166                   |
| filters ← mandatory_filters 주입        | tools/schema_context.py:171                   |
| ↳ target_filters (문구 매칭 주입)           | tools/schema_context.py:181                   |
| ↳ intent.constraints 변환               | tools/schema_context.py:205 (_constraint :91) |
| ↳ 등급 축 반전 (AA- → rank ≤ 4)            | tools/schema_context.py:114                   |
| ↳ 중복 제거                               | tools/schema_context.py:85                    |
| entities 단일 엔티티 binding               | tools/schema_context.py:194                   |
| ↳ 펀드 클래스 묶음 (fund_classes)            | tools/schema_context.py:192                   |
| order 매핑 + nulls                      | tools/schema_context.py:216                   |
| ↳ default_order 자동 주입                 | tools/schema_context.py:228                   |
| ↳ ID tie-breaker                      | tools/schema_context.py:230                   |
| limit                                 | tools/schema_context.py:243                   |
| unresolved (정렬 미확정)                   | tools/schema_context.py:225                   |
| concepts (fp: URI 역참조)                | tools/schema_context.py:239                   |
| as_of (도메인별 실질 기준일)                   | tools/schema_context.py:244                   |


###   
  
③ validate_query — 실행 전 결정적 검증 (Python 규칙)

항목


| 항목                                             | 관련 코드                  |
| ---------------------------------------------- | ---------------------- |
| 노드 본체 (abstain 반환)                             | agent/nodes.py:35      |
| ↳ trace PASS / code 기록                         | agent/nodes.py:38      |
| validate_query(question, grounded) 진입          | tools/validate.py:15   |
| 매핑표 로드 (rules)                                 | tools/validate.py:17   |
| ABSTAIN 결과 생성 헬퍼 (code · reason · evidence 3키) | tools/validate.py:11   |
| 전부 통과 → None                                   | tools/validate.py:50   |
| 검증 실패 시 분기 (→ render_answer 직행)                | agent/agent_core.py:11 |


검증 항목별 (위에서부터 먼저 걸리는 하나)


| #   | 검증 항목                                                        | 나오는 code                          | 관련 코드                           |
| --- | ------------------------------------------------------------ | --------------------------------- | ------------------------------- |
| 1   | 도메인 확정 여부                                                    | ABSTAIN_UNRESOLVED_QUERY          | tools/validate.py:18            |
| 2   | 요청 날짜가 cutoff 이후                                             | ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF | tools/validate.py:24            |
| ↳   | 원문에서 20xx-xx-xx 추출                                           | —                                 | tools/validate.py:22            |
| ↳   | cutoff 값 로드 (data_cutoff)                                    | —                                 | tools/validate.py:21            |
| 3   | 신용등급 허용값                                                     | ABSTAIN_INVALID_TAXONOMY          | tools/validate.py:31            |
| ↳   | 원문 신용등급 XX 정규식                                               | —                                 | tools/validate.py:30            |
| ↳   | 허용값 19개 (rating_rank)                                        | —                                 | metadata/business_rules.json:10 |
| 4   | 미래 실현값 (20xx년 + "확정")                                        | ABSTAIN_FUTURE_DATA               | tools/validate.py:35            |
| ↳   | 원문 20xx년 추출                                                  | —                                 | tools/validate.py:34            |
| 5   | 관계 domain/range (etf_gl + "발행한 회사채")                         | ABSTAIN_DOMAIN_MISMATCH           | tools/validate.py:38            |
| 6   | 미해소 binding (plan.unresolved)                                | ABSTAIN_UNRESOLVED_QUERY          | tools/validate.py:41            |
| 7   | 데이터 snapshot이 cutoff 이후 ([plan.as](http://plan.as)_of.value) | ABSTAIN_CUTOFF_VIOLATION          | tools/validate.py:44            |


규칙 상수 (metadata)


| 항목                             | 관련 코드                           |
| ------------------------------ | ------------------------------- |
| data_cutoff (검증 2 · 4 · 7의 기준) | metadata/business_rules.json:3  |
| domain_as_of (검증 7의 비교 대상)     | metadata/business_rules.json:4  |
| rating_rank 19개 (검증 3의 허용 목록)  | metadata/business_rules.json:10 |


눈에 걸리는 게 두 개 있습니다. 1번과 6번이 같은 ABSTAIN_UNRESOLVED_QUERY를 쓰는데, 도메인 미확정과 binding 미해소는 원인이 달라서 로그에서 구분이 안 됩니다. 그리고 2번과 7번이 둘 다 cutoff를 보지만 code가 갈립니다. 사용자가 미래 날짜를 물은 건 2번이고, 우리 데이터가 cutoff보다 최신인 건 7번이라 성격이 반대입니다. 지금 모든 질의가 막히는 건 7번이니 business_rules.json:3만 고치면 풀립니다.



---

### ④ select_route - 실행 가능한 것만 통과(python규칙)


| 항목                           | 관련 코드                  |
| ---------------------------- | ---------------------- |
| 노드 본체 (route · abstain 반환)   | agent/nodes.py:42      |
| ↳ unsupported → ABSTAIN 변환   | agent/nodes.py:46      |
| 라우팅 후 분기 조건                  | agent/agent_core.py:15 |
| select_route(frame, plan) 본체 | tools/route.py:21      |
| ↳ unsupported 생성 헬퍼          | (원문 소실)                |
| 관문 1 — binding 미해소           | tools/route.py:29      |
| 관문 2 — 복수 도메인                | tools/route.py:31      |
| 관문 3 — 미지원 task              | tools/route.py:33      |
| 관문 4 — 미지원 계산                | tools/route.py:36      |
| rdb_only 결과 생성               | tools/route.py:38      |
| step 상한 assert               | tools/route.py:41      |
| MAX_PLAN_STEPS               | tools/route.py:9       |
| 지원 task 집합                   | tools/route.py:5       |
| 지원 계산 집합                     | tools/route.py:6       |
| query_type enum 6개           | tools/route.py:7       |
| 라우트 JSON 스키마                 | (원문 소실)                |




---

### ⑤ execute_rdb — LogicalPlan → 제한된 SELECT → evidence



관련 코드 인덱스


| 항목                                                  | 관련 코드                           |
| --------------------------------------------------- | ------------------------------- |
| 노드 본체 (results · evidence · abstain 반환)             | agent/nodes.py:53               |
| ↳ 예외 → ABSTAIN_EXECUTION_FAILED                     | agent/nodes.py:57               |
| ↳ trace rows / status                               | agent/nodes.py:61               |
| execute(plan) 진입                                    | tools/rdb.py:187                |
| ↳ 커넥션 (lru_cache 1개 재사용)                            | tools/rdb.py:28                 |
| ↳ statement_timeout 설정                              | tools/rdb.py:189                |
| ↳ 엔티티 해소 호출                                         | tools/rdb.py:190                |
| ↳ READ ONLY 트랜잭션                                    | tools/rdb.py:195                |
| ↳ 행 수 상한 검사                                         | tools/rdb.py:200                |
| resolve_entities 본체                                 | tools/rdb.py:64                 |
| ↳ 완전일치 count 조회                                     | tools/rdb.py:72                 |
| ↳ 펀드 클래스 ILIKE 확장                                   | tools/rdb.py:80                 |
| compile_plan 본체                                     | tools/rdb.py:94                 |
| ↳ 참조 binding 수집                                     | tools/rdb.py:99                 |
| ↳ 테이블 alias 할당                                      | tools/rdb.py:37 (_aliases)      |
| ↳ binding → SQL 식                                   | tools/rdb.py:50 (_binding_expr) |
| ↳ JOIN 조립                                           | tools/rdb.py:114                |
| ↳ SELECT 절                                          | tools/rdb.py:133                |
| ↳ WHERE — entities                                  | tools/rdb.py:137                |
| ↳ WHERE — filters                                   | tools/rdb.py:152                |
| ↳ ORDER BY (+ NULLS)                                | tools/rdb.py:160                |
| ↳ LIMIT                                             | tools/rdb.py:174                |
| ↳ evidence 생성                                       | tools/rdb.py:177                |
| ↳ CompiledQuery 반환                                  | tools/rdb.py:183                |
| operator 화이트리스트 6개                                  | tools/rdb.py:16                 |
| CompiledQuery 정의                                    | tools/rdb.py:19                 |
| 규칙 상수 (max_rows · max_joins · statement_timeout_ms) | metadata/business_rules.json    |


