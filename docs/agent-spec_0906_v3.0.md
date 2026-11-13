# 금융상품 Agent 스펙 명세서 — 2026-09-06 / v3.0

## 문서 기준과 읽는 방법

이 문서는 09-06 현재 작업 트리의 **구현 명세**다. [08-26 v2.0](agent-spec_0826_v2.0.md)의 변경 비교표 → 전체 흐름 → 단계별 계약·예시 → 검증·후속 순서를 따른다. 기존 문서의 실험 수치나 권장 구조를 현재 구현으로 간주하지 않고, `src/agent/`의 Python 코드 14개 파일 전체 6,015줄을 읽어 다시 작성했다. 직접 의존하는 스키마·DB 클라이언트·테스트도 대조했다.

| 항목 | 기준 |
|---|---|
| 명세 작성 기준일 | 2026-09-06 KST |
| 데이터 cutoff | 2026-08-24. 명세 작성일과 데이터 기준일은 다르다 |
| 브랜치 | `fix/intent-abstain-answer` |
| HEAD | `b2bfd449984f27aaa36a15da93f50c452636ee61` |
| 코드 범위 | 저장소 루트의 `agent/`가 아니라 `src/agent/` 전체 |
| 미커밋 구현 포함 | `src/agent/nodes.py`, `src/agent/prompts.py` |
| 문서 검증 | 09-06 로컬 단위 테스트. 원격 DB·HCX E2E를 새로 측정한 문서가 아님 |

이하 **구현**은 실행 코드로 확인한 사실, **제약**은 그 코드가 보장하지 못하는 부분, **과거 실측**은 링크한 당시 기록을 뜻한다. 일부 파일 상단 주석에는 과거 상태가 남아 있으므로 함수 본문과 실제 파일 존재 여부를 우선했다. 예를 들어 `utils.py`의 “로컬 Postgres”, `graph_entity.py`의 “company_master.csv 없음”, `graph_schema.py`의 “인덱스를 만들면 자동 임베딩 연결” 설명은 현재 상태를 정확히 표현하지 않는다.

미커밋 파일의 읽기 시점 SHA-256:

```text
nodes.py   9068efc54f64f740da9bfe585bfcd3b972a458443a58519243c4f7c86a04afaf
prompts.py 1cdb88a7f35d2e3304e247d6acc42e025a680b4e92244a6bae8332f17675e073
```

## 1. 커밋 이력과 08-26 설계 대비 변경

### 1.1 현재 HEAD에 반영된 Agent 변경

`git log -- src/agent`의 현재 브랜치 이력을 기준으로 정리했다. 다른 브랜치·stash에만 있는 커밋은 구현 완료의 근거로 사용하지 않는다.

| 날짜 | 커밋 | 현재 구조에 반영된 변화 |
|---|---|---|
| 08-27 | `fc7897c` | 현행 `src/` 레이아웃으로 교체 |
| 09-02 | `6a78c89` | RDB·Graph 통합 구조, 관계 의존 계획·웨이브 실행·핸드오프 기반 |
| 09-03 | `a10be80` | Graph 저장소 3단계 연결 전환, pgvector 검색 연결 |
| 09-03 | `5632892` | 요청 주제에 맞는 Vector 섹션 제한과 답변 근거 반영 |
| 09-03 | `3161c6b` | Graph 경로·import 오류 수정 |
| 09-03 | `92d760d` | 답변 HCX timeout 30초 → 90초 |
| 09-05 | `ef8f59d` | Graph 정규형·세그먼트 엔티티 인덱스와 캐시 |
| 09-05 | `40eac15` | 카탈로그 기반 SQL 결정론 컴파일, 상품명→Graph 코드 해소, 원격 테이블 존재 확인 등 |
| 09-05 | `c622235` | 원격 text 숫자·날짜 컬럼 비교/정렬 CAST, 로컬 타입 정의 정정 |
| 09-05 | `b2bfd44` | 현재 HEAD. 원격 DB와 로컬 RDB 스키마 비교 문서·스크립트 추가 |

현재 작업 트리에는 별도로 답변 행 예산, 빈 답변 재시도·행 나열 fallback, 항목별 미산출 사유, 수치 기준일 footer, 상품명 누락 보정이 추가되어 있다. 이 부분과 답변 프롬프트 변경은 **미커밋 구현**이며, HEAD만 checkout하면 동일한 답변 동작이 재현되지 않는다. 관련 `test_answer_generation.py`도 읽기 시점에는 미추적 파일이다.

### 1.2 권장 설계와 실제 구현의 차이

| 08-26 문서의 설계 | 09-06 실제 구현 | 판정 |
|---|---|---|
| HCX Query Frame 1회 | `analyze_intent`와 `verify_intent`를 항상 순서대로 호출; 각각 뒤에 규칙 보정 | 변경 구현 |
| 모든 질문의 TBox Vector Top-3 grounding | 공통 전처리 노드 없음. RDB는 Python 카탈로그, Graph는 lexical schema fragment | 미구현/대체 |
| 통합 `SemanticSchemaContext` | RDB `resolved_schema`와 Graph `SchemaFragment`가 별개 | 부분 구현 |
| 검증된 capability ID만 조합하는 Planner | `relation`·도메인별 규칙 계획, 모호한 출발점만 HCX 보조 | 다른 계약 |
| 전역 Route Guard, 최대 3단계 | 관계 참조 검증·실행 준비 판단은 있음. 전역 capability whitelist/3단계 상한 없음 | 일부만 구현 |
| LLM이 raw SQL을 생성하지 않음 | 결정론 컴파일 우선이나 SQL 초안·생성·수정 LLM fallback 유지 | 불일치 |
| Graph는 미배선 | 고정 4종 plan과 HCX GraphLogicalPlan, SPARQL 실행까지 연결 | 구현 |
| Vector는 실행 불가 | 상품·섹션 범위 pgvector 문서 검색과 coverage 상태 연결 | 구현 |
| 15초 초과 시 결정적 fallback | 전역 deadline 없음. 답변 fallback은 예외·빈 답변 기준 | 미구현 |
| 모든 관계·수치의 완전한 evidence 검증 | Graph 관계 evidence 검사, Vector 메타데이터, RDB SQL·도메인 날짜 요약; 통합 검증 없음 | 부분 구현 |

## 2. 전체 실행 구조와 모듈 책임

```text
사용자 입력 {question, question_id?, max_sql_retries?}
  ↓
① receive_question                  질문 수신 로그
  ↓
② analyze_intent [HCX-007] → guard_intent
  ↓
③ verify_intent  [HCX-007] → guard_intent
  ↓
④ plan_query                       규칙 계획; 모호한 관계 출발점만 HCX
  ↓
⑤ dispatch / ready_step_ids         depends_on 결과가 준비된 엔진 선택
  ├─ rdb_search    카탈로그 → SQL compiler / HCX fallback → SQL API
  ├─ graph_search  seed → fragment → plan 검증 → SPARQL → evidence
  └─ vector_search 상품 ID → coverage → 임베딩 → pgvector
       각 검색 노드 완료 → ⑤ 재평가 → 다음 웨이브
  ↓ 준비된 단계 없음
⑥ merge_results                    RDB target + Graph 행 + Vector 청크
  ↓
⑦ generate_answer                  HCX 답변 / 결정론 fallback + footer
  ↓
END: state.answer에 5개 필드의 JSON 문자열
```

진입점은 [graph.py](../src/agent/graph.py)의 `app = build_graph()`다. 9개 노드로 조립한 LangGraph이며, 이 디렉터리에 FastAPI 라우터·HTTP 응답 endpoint·대화 메모리 구현은 없다. 기본 사용 계약은 단일 질문 실행이다.

### 2.1 전수 확인 파일 목록

| 파일 (`src/agent/` 기준) | 줄 수 | 책임 |
|---|---:|---|
| [graph.py](../src/agent/graph.py) | 120 | 노드 조립, 웨이브 라우팅, 전역 `app` |
| [state.py](../src/agent/state.py) | 101 | `ChatbotState`, 결과·로그 reducer, 준비 단계 판정 |
| [get_clova.py](../src/agent/get_clova.py) | 40 | HCX 설정·키 이름 연결, 지연 생성 임베더 |
| [intent_guard.py](../src/agent/intent_guard.py) | 334 | Intent 연산자·관계·테마·출력항목 규칙 보정 |
| [plan_query_db.py](../src/agent/plan_query_db.py) | 612 | 관계 위상 정렬, RDB/Graph/Vector 단계·의존·UNION 그룹 계획 |
| [nodes.py](../src/agent/nodes.py) | 1,587 | 노드 실행·SQL 재시도·핸드오프·검색·병합·답변 |
| [prompts.py](../src/agent/prompts.py) | 363 | 분석·검수·관계 출발점·Graph plan·컬럼 해소·SQL 초안/생성/수정·답변 프롬프트 9종 |
| [sql_builder.py](../src/agent/sql_builder.py) | 355 | 조건·필드·정렬·JOIN·UNION용 SQL 결정론 컴파일 |
| [utils.py](../src/agent/utils.py) | 874 | 판매 정책·상품명/개념 해소·스키마 조립·HTTP SQL 실행 |
| [graph_logic/graph_engine.py](../src/agent/graph_logic/graph_engine.py) | 28 | `OxigraphClient` 공유 인스턴스의 SPARQL·트리플 수 facade |
| [graph_logic/graph_entity.py](../src/agent/graph_logic/graph_entity.py) | 578 | 이름/코드→URI, 클래스별 seed 해소, 정규형 인덱스·캐시 |
| [graph_logic/graph_ids.py](../src/agent/graph_logic/graph_ids.py) | 74 | NFKC·법인격·조직 약칭 정규화와 검증된 표기 변형 |
| [graph_logic/graph_plan.py](../src/agent/graph_logic/graph_plan.py) | 436 | 타입 검증, evidence 부착 SPARQL 컴파일, 고정 plan 4종 |
| [graph_logic/graph_orchestrator.py](../src/agent/graph_logic/graph_orchestrator.py) | 513 | Graph seed/fragment/plan/실행/evidence, 테마 후보 통합 |
| 합계 | 6,015 | `__init__.py` 없는 namespace package |

### 2.2 상태와 외부 호출 계약

| 상태 키 | 의미 |
|---|---|
| `question`, `question_id` | 질문 문자열, 선택 식별자. 답변 생성 시 식별자 기본값 `Q-UNKNOWN` |
| `max_sql_retries` | SQL **총 실행 시도 수**. 기본 3; 이름과 달리 최초 실행에 추가 3회를 뜻하지 않음 |
| `intent` | 분석·검수·규칙 보정된 개념 구조 |
| `plan`, `route` | 실행 단계 목록과 요약. 관계 순환·끊긴 참조면 둘 다 `None` |
| `step_results` | `step_id → 엔진 결과`. reducer가 얕은 dict 병합; 같은 키면 뒤 값이 덮음 |
| `merged_rows` | 답변 입력 행 목록. 상품의 유일 개수를 뜻하지 않음 |
| `answer` | 최종 응답 객체를 직렬화한 JSON **문자열** |
| `trace` | 노드가 추가한 문자열 로그 목록. `operator.add`로 누적 |

```python
import json
from agent.graph import app

result = app.invoke({"question_id": "Q4", "question": "KODEX 200의 순자산을 알려줘"})
response = json.loads(result["answer"])
```

`PYTHONPATH=src` 또는 동등한 모듈 경로 설정이 필요하다. import 시 HCX 클라이언트가 생성되므로 관련 패키지·인증 설정도 필요하다. `TypedDict(total=False)`는 정적 타입 설명이며 입력값의 완전한 런타임 검증기는 아니다.

## 3. 질문 분석과 Intent 보정

근거: [nodes.py](../src/agent/nodes.py)의 `analyze_intent_node`, `verify_intent_node`, [intent_guard.py](../src/agent/intent_guard.py), [schemas.py](../src/tools/schemas.py).

### 3.1 Intent 출력 구조

| 필드 | 계약과 소비 방식 |
|---|---|
| `raw_question` | 원문. 테마 보정·모호한 관계 출발점 판정에 사용 |
| `task` | `lookup / filter_rank / relation / comparison / explanation / recommendation` |
| `product_domain[]` | `{domain, subtype[]}`. domain은 채권·국내ETF·해외ETF·펀드 |
| `target_entities[]` | `{surface_form, entity_type}`. type은 `product_name / company / theme / unknown` |
| `conditions[]` | `attribute, operator, value, value_2, applies_to, domain, time_window_relative, kind, grounding_status` |
| `relations[]` | `id, subject_domain, relation, object_entity, object_ref, time_window_relative, entity_role, path[]` |
| `sort` | `attribute, order, limit, domains[]`. limit은 문자열 |
| `output_requirements` | `fields[]` 정형 요청, `narrative_topics[]` 서술 요청 |
| `answer_format` | `list / narrative / list_with_narrative` |

LLM 조건 연산자 enum은 `eq / gte / lte / between / contains`다. 이후 코드가 만드는 상품코드 조건에는 내부 연산자 `in`이 추가된다. Intent의 relation은 개념명이며 `fp:` 술어를 직접 실행하는 계약이 아니다.

### 3.2 분석·검수 순서

1. HCX가 `INTENT_ANALYSIS_JSON_SCHEMA` 구조화 출력을 생성한다.
2. `guard_intent`가 규칙 보정하고 trace에 변경 사유를 남긴다.
3. 별도의 HCX 검수가 원문과 1차 결과를 대조해 누락 조건·관계 등을 수정한다.
4. 다시 `guard_intent`를 적용한 결과로 계획한다.

검수 생략 fast path나 feature flag는 없다. 두 HCX 호출은 노드 내부에서 예외를 잡지 않으므로 호출·파싱 실패가 전체 실행을 중단시킬 수 있다.

### 3.3 결정론 보정 범위

- 연산자·정렬 별칭을 정규화한다. 단일 값의 `in`은 `eq`로 바꾼다.
- 정성 조건의 `grounding_status=resolved`를 `unresolved`로 고친다. 다만 후속 RDB가 이 표지만으로 실행을 차단하지는 않는다.
- `object_ref`와 `object_entity`가 동시에 있으면 참조를 남기고 이름을 비운다.
- `편입/보유/포함/편입종목` 조건은 `holds`, `자회사/계열사/출자` 조건은 `subsidiary_of` 관계로 옮긴다. 정해진 단어와 정확히 일치할 때만 수행한다.
- 기존 theme 관계가 없으면 원문의 `OO 테마/섹터` 표현을 `tagged_with` 관계로 추가한다. 이미 관계에 있는 동일 테마 조건은 제거한다.
- 출력 요청에서 빈 문자열·도메인명 자체를 제거한다.
- 관계가 있으면 `comparison`을 제외한 task를 `relation`으로 맞춘다.

**제약:** 이 guard는 전역 답변불가 판정기가 아니다. 미래 실현값·기준일 이후 출시·상품 부재·도메인 위반을 공통 enum으로 분류하거나, 원문의 모든 조건이 Intent에 보존됐는지 증명하지 않는다. 구형 문서의 `LEAK` 검사도 현재 파이프라인에는 없다.

## 4. Plan & Routing과 웨이브 실행

근거: [plan_query_db.py](../src/agent/plan_query_db.py), [state.py](../src/agent/state.py), [graph.py](../src/agent/graph.py).

### 4.1 계획 생성 규칙

| 대상 | 단계 생성 조건 | 단계 ID·의존 |
|---|---|---|
| Graph | relation 하나당 하나 | `graph_<relation id>`; `object_ref`가 가리킨 Graph 단계에 의존 |
| RDB 선행 조회 | 이름·참조 없는 관계를 HCX가 RDB 출발로 판정하고 지원 도메인을 반환 | `rdb_pre_<id>`, `role=entity_lookup`; 해당 Graph가 대기 |
| RDB 최종 조회 | target 조건·정렬·출력 필드·하위유형·상품명 중 하나 이상 | `rdb_<domain>`, `role=target`; 관련 terminal Graph에만 의존 |
| Vector | 서술 주제가 있거나 narrative 계열 answer_format | `vector_narrative`; RDB target들이 있으면 그 전부, 없으면 terminal Graph들에 의존 |

상품 도메인만 있고 위 RDB trigger가 하나도 없으면 RDB 단계가 생기지 않는다. 복수 도메인은 중복을 합치고 subtype 합집합을 사용한다. `conditions.domain`이 있으면 해당 도메인에만, 없으면 각 도메인에 공통 적용한다.

Graph의 `subject_domain`이 Company/기업 등 비상품이면 RDB와 독립이다. 국내ETF 등 특정 도메인이면 그 도메인만, `ETF`이면 요청된 국내·해외ETF만 기다린다. 빈 값·미인식 표기는 요청 도메인 전체에 적용된다. terminal은 다른 relation의 `object_ref`로 참조되지 않는 관계다.

### 4.2 단계 예시

다음은 실행 계약 설명용 예시이며 실제 조회 결과가 아니다.

```json
[
  {"step_id": "graph_R1", "engine": "graph", "depends_on": [],
   "relation": {"id": "R1", "subject_domain": "국내ETF", "relation": "holds",
                "object_entity": "삼성전자", "object_ref": "", "entity_role": "company"}},
  {"step_id": "rdb_국내ETF", "engine": "rdb", "role": "target",
   "domain": "국내ETF", "depends_on": ["graph_R1"],
   "conditions": [], "subtype": [], "product_name_entities": [],
   "fields": ["순자산"], "sort": {"attribute": "순자산", "order": "desc", "limit": "5"}}
]
```

### 4.3 라우팅 상태와 실제 병렬 범위

`route`에는 `needs_graph/rdb/vector`, `domains`, `supported_domains`, `rdb_required_but_blocked`, `needs_merge_rank`, `merge_group_step_ids`, `sort_limit`, LLM 출발점 판정 기록과 `blocking_reasons`가 담긴다.

실제 dispatch는 요약 플래그보다 `plan + step_results`를 사용한다. 결과 키가 존재하면 성공·실패 상태와 무관하게 done이며, 모든 의존 키가 존재한 미실행 단계가 ready다. 준비된 서로 다른 엔진은 LangGraph에서 병렬로 실행할 수 있지만 **같은 엔진의 복수 단계는 해당 노드의 for-loop에서 순차 실행**한다. 준비 단계가 없으면 merge로 이동한다.

관계 참조 순환·끊긴 참조는 plan 생성 실패다. 반면 `blocking_reasons`는 대체로 설명용 경고이며 남은 실행을 일괄 차단하지 않는다. 전역 plan 최대 3단계 제한이나 타입 기반 엔진 간 핸드오프 검증기는 없다.

## 5. Semantic Schema와 RDB 실행 계약

근거: [utils.py](../src/agent/utils.py), [sql_builder.py](../src/agent/sql_builder.py), [rdb_schema.py](../src/tools/rdb_schema.py), `nodes._execute_target_step`.

### 5.1 도메인과 물리 binding

| 도메인 | 현재 Agent 기본 테이블 | 상품코드 | 상품명 | 현재 코드의 도메인 대표 날짜 |
|---|---|---|---|---|
| 채권 | `raw.prbd01n001` | `pd_no` | `pd_nm` | 2026-08-21 |
| 국내ETF | `raw.pref01n001` | `pd_itm_no` | `pd_nm` | 2026-08-22 |
| 해외ETF | `raw.pref02n001` | `pd_itm_no` | `pd_nm` | 2026-08-22 |
| 펀드 | `raw.prfd01n001` | `itm_no` | `itm_nm` | 2026-08-21 |

이 표는 **현재 Agent 카탈로그**다. 로컬 빌더의 `raw.fund_pub_master` 등 이름으로 자동 전환하지 않는다. 원격/로컬 이름·타입 차이는 [09-05 DB 비교 문서](docs_DB/2026-09-05_remote_vs_local_db_schema.md)를 함께 본다. 날짜는 `DOMAIN_AS_OF`의 대표값으로, 모든 행·수치의 실제 기준일을 조회해서 정한 값이 아니다. 특히 국내ETF의 `wu_upt_dt`, `ref_base_dt`, `cu_upt_dt`는 서로 다를 수 있다.

`AttributeSpec`은 컬럼, 값 타입, 값 순서, 허용 범주, 플래그 참 조건, 설명, 선택적 JOIN 테이블·별칭·조건, 조직명 여부를 담는다. 국내ETF 총보수율은 `enriched.etf_kr_enriched AS ee`의 `ee.charge_rt_final`로 LEFT JOIN한다. 테이블 이름을 선언했다고 원격 DB에 실제 존재하는 것은 아니다.

### 5.2 RDB target 처리 순서

```text
판매가능 정책 적용
 → 상품명 Graph 해소 → 성공하면 상품코드 IN
 → 조건·정렬·필드·필수 상품명 개념 수집
 → 카탈로그 exact/공백제거·소문자 매핑 → 미해소 개념만 HCX 컬럼 선택
 → subtype·ordinal·조직명·필드·JOIN을 resolved_schema로 조립
 → 미해소 필수 개념 / 무효 조건 / 원격 보강 테이블 부재면 skip
 → 원격 기본 테이블 컬럼 타입 조회·캐시
 → compile_sql
      성공: 결정론 SQL
      None: HCX 자연어 초안 → HCX SQL
 → SQL API 실행 → 실패 시 HCX SQL 수정 후 재실행
```

`resolved_schema`의 필드는 `domain, table, conditions, sort, fields, unresolved_concepts, invalid_conditions, notes, joins`다. 조건·정렬·필수 상품명 미해소는 단계 중단이고, 출력용 필드만 미해소면 그 필드를 제외하고 사유를 남긴다. subtype 매핑 부재도 해당 조건을 제외하고 계속한다. 값이 빈 조건은 경고 출력 후 건너뛴다.

컬럼 fallback은 실제 컬럼 설명 목록을 HCX에 제공하지만, 반환 컬럼의 목록 포함 여부와 `confidence`를 코드에서 재검사하지 않는다. 반환값은 `value_type=unknown`으로 저장된다. 따라서 이를 “검증된 binding만 사용하는 실행”이라고 표현할 수 없다.

### 5.3 결정론 SQL compiler

| 입력 유형 | 컴파일 규칙 |
|---|---|
| ordinal 조건 | 카탈로그의 오름차순 `value_order`에서 값을 선택해 `IN`; AA- 이상은 AA-, AA0, AA+, AAA |
| ordinal 정렬 | 값 순서를 `CASE WHEN` 순번으로 바꿔 정렬 |
| 숫자·단위 | 한국어 만/억/조 등 숫자 해석, `%`는 표시 수치 그대로. 기간은 1년=365일·1개월=30일 |
| 통화 불일치 | 값과 컬럼 설명의 통화가 다르면 `None`; 환율 변환 구현이 아니라 LLM fallback |
| 날짜 | YYYYMMDD 수치 비교. 연·월은 구간 비교; 월 말일은 `31`로 표현하는 수치 경계 |
| 원격 text 숫자·날짜 | `CAST(... AS NUMERIC)` 적용. 타입 불명일 때 날짜는 강제 CAST |
| 플래그·범주 | `true_condition`, Y/N 또는 정규화된 `known_values` 사용 |
| 조직명 | 검증된 약칭 변형별 `TRIM(column) LIKE '%값%'`를 OR |
| 국내ETF | `pd_grp_no` 조건이 없으면 `pd_grp_no='ETF'` 자동 추가 |
| 무효 컬럼 | `buyable_quantity`를 조건·정렬·출력에서 제거하고 메모 |
| 정렬·절단 | 정렬 컬럼 `IS NOT NULL`, `NULLS LAST`; 유효 숫자 limit이고 허용된 경우만 LIMIT |

compiler는 filter/sort/select 중심이다. 독립된 집계·중복률·자기조인·CTE 의미 계획기는 없다. 표현할 수 없는 조건이 하나라도 있으면 전체 compile 결과가 `None`이다. 다만 compiler에 도달하기 전에 제외된 subtype·빈 조건까지 복구하거나 원문 누락을 검출하는 것은 아니다.

### 5.4 실행·재시도·교차 도메인 순위

- `get_pg_connection()`은 psycopg2가 아니라 `requests.Session`을 반환한다. SQL 원문을 `POST /db/sql`, `text/plain; charset=utf-8`로 보낸다. 전송 전에 `%`를 `%%`로 치환한다.
- 응답이 list면 그대로, dict면 `rows/result/results/data`의 list를 선택한다. 서버의 총건수·페이지·truncation 메타데이터는 보존하지 않는다.
- SQL 실행은 기본 **총 3회**, 실패 사이 `_fix_sql`이 HCX로 SQL을 재작성한다. 결정론 SQL도 실행 오류가 나면 이 수정 경로를 탄다. 수정 SQL의 AST·필수조건 보존을 다시 검증하는 단계는 없다.
- RDB 결과에는 `rows, count, sql, assumptions, sql_attempts, sql_retry_log`와 성공 경로에 따라 `sql_source, sql_draft_nl`이 담긴다. skip은 `skipped_reason`, 실패는 `error`다. 모든 단계가 동일한 필드를 갖는 것은 아니다.
- 공통 정렬 그룹은 `UNION ALL`로 `code/name/domain/sort_value` 4열을 맞추고 바깥에서 정렬·LIMIT한다. 결과는 대표 step 하나에만 담고 나머지는 `merged_into`로 표시한다. 추가 요청 필드는 이 모드에서 제외된다.
- 같은 웨이브에 준비된 그룹 멤버가 2개 이상이면 그 멤버를 합친다. 전체 그룹이 모두 준비됐는지 검사하지 않으며, 1개면 개별 조회한다. 웨이브가 갈린 결과를 merge 노드에서 다시 전역 정렬하지 않는다.

### 5.5 엔진 간 핸드오프 제약

| 경로 | 현재 동작 | 보장하지 못하는 부분 |
|---|---|---|
| Graph → 단독 RDB target | 의존 Graph들의 `entity_codes`를 중복 제거해 상품코드 IN 주입 | 여러 관계 조건의 **합집합**이며 교집합 아님. 코드가 없으면 원래 step 그대로 실행 |
| Graph → UNION RDB 그룹 | 그룹 실행으로 바로 진입 | `_apply_graph_handoff`가 호출되지 않아 Graph 코드 필터가 빠짐 |
| RDB entity_lookup → Graph | 계획상 선행 RDB 조회·대기는 가능 | Graph frame이 RDB 결과를 seed로 읽지 않음. 이름 없는 관계는 `abstain_no_seed_text` |

Graph 상태가 실패·빈 결과여도 done으로 취급되므로 후속 RDB가 관계 필터 없이 실행될 수 있다. 따라서 Graph 실패 후 얻은 일반 상품 목록을 “그 관계를 만족하는 상품”으로 확정해서는 안 된다. 현재 파이프라인 전체가 이 경계를 강제하지 못한다.

## 6. Graph 엔티티 해소·스키마·실행

### 6.1 Entity resolver

좁은 규칙부터 `exact → 기업 정규화 exact → 정규형/슬래시 세그먼트 exact → 선택적 partial 후보 → 공백으로 분리된 말미 상품군 토큰 제거 후 재시도` 순서로 찾는다. 후보 수는 행 수가 아닌 고유 URI 수다.

| 상태 | 의미 |
|---|---|
| `resolved` | 유일 후보; `uri, class_uri, canonical_name, names, codes, match_mode` 추가 |
| `ambiguous` | 후보 2개 이상; 일반 Graph 실행 중단 |
| `partial_candidates` | `allow_partial=True`일 때만 후보 제시; 일반 seed 자동 확정 아님 |
| `not_found` | 후보 없음 |

`entity_role`이 클래스 탐색 순서를 정한다. 예를 들어 company는 Company→Security→Organization, product는 ETF→PublicFund→Bond→ETN→Product, ticker는 ETF→ETN→Security→Product다. issuer·manager·share_class·theme·index도 별도 순서가 있다. 첫 resolved 또는 ambiguous에서 멈춘다.

기업 정규화는 `data/enriched/company_master.csv` 후보 중 실제 Graph에 존재하는 Company만 사용한다. **09-06 워크스페이스에는 이 CSV가 존재**하므로 상단의 파일 부재 주석을 현행 제약으로 옮기지 않는다.

정규형 인덱스는 11개 클래스에 대해 공백·하이픈·밑줄 제거와 `/`의 연속 세그먼트를 색인한다. 후보 URI를 좁힌 뒤 원래 SPARQL에 `VALUES`를 붙여 최종 행을 얻는다. 프로세스 메모리 캐시와 `artifacts/graph_entity_index.pkl`을 사용하며, 파일 캐시는 스토어 경로·최신 mtime·버전·클래스 서명으로 판정한다. 구축 실패 시 SPARQL 전체 스캔으로 돌아간다. `clear_entity_cache()`는 메모리와 실패 기록을 초기화한다.

RDB 상품명 호출자는 이 resolver에서 실패·모호성·장애가 나도 이름 조건을 `contains`로 조회한다. 이는 resolver의 엄격한 Graph seed 정책과 다르며, 유사 상품 자동 반환을 막는 전역 보장이 아니다.

### 6.2 TBox grounding와 SchemaFragment

[graph_schema.py](../src/tools/graph_schema.py)는 `common.ttl / bond_kr.ttl / etf_kr.ttl / etf_gl.ttl / fund_pub.ttl`을 읽어 class·property·domain/range·출처 애노테이션 카탈로그를 만든다. 질의 lexical 점수와 명시 seed class로 fragment를 고르고, 호출부는 2홉·클래스 예산 18·속성 예산 60을 전달한다. 반환 필드는 `seed_classes, classes, properties, selection_mode, class_hits`다. 이 예산을 전역 plan guard로 해석하지 않는다.

현재 `artifacts/graph_schema_index.json`은 없다. 따라서 기본 경로는 `lexical_fallback+explicit`이다. `_vector_hits`는 파일이 없거나 fingerprint가 다르면 lexical로 넘어가며, **유효한 인덱스가 있어도 임베딩 클라이언트가 미연결이라 `NotImplementedError`**를 낸다. 별도 `vec.schema_terms_all` 검색 도구는 존재하지만 이 Graph fragment 경로에 연결되지 않는다.

### 6.3 고정 plan과 HCX plan

| 고정 plan | 구조 |
|---|---|
| `subsidiary_relation_plan` | Company → SubsidiaryRelation → 자회사 Company |
| `company_holding_etf_plan` | Company ← Security ← Holding ← ETF |
| `subsidiary_holding_etf_plan` | Company → SubsidiaryRelation → Company ← Security ← Holding ← ETF |
| `theme_membership_plan` | Theme ← `relatedToTheme` ← ETF |

`graph_search_node`는 관계 체인의 중간 단계를 실행하지 않고 `chained`로 기록한다. terminal에서 최초 `object_entity`로 거슬러 올라가 seed를 만든다. frame은 entities와 limit=100을 채우며, relations·requested_fields·constraints는 빈 배열이다. **step에 저장된 관계 조건·상대 기간·path를 그대로 Graph plan의 조건으로 컴파일하지 않는다.**

일반 고정 plan은 관계 이름만이 아니라 **질문 전체**의 자회사/출자·편입/보유/포함·ETF 표현으로 선택한다. 따라서 독립 요청이 섞인 질문에서는 다른 요청의 키워드가 plan 선택에 영향을 줄 수 있다. 고정 plan 검증 실패 시 HCX plan으로 재선택하지 않고 중단한다.

고정 경로가 없으면 HCX가 fragment enum에 제한된 `nodes/edges/outputs/limit` GraphLogicalPlan을 생성한다. 생성과 검증을 포함해 최대 3회 시도한다. node ID·alias의 표기만 결정론 보정하며, 의미·방향을 임의 변경하지 않는다.

### 6.4 Graph Plan Guard와 evidence

- 필수 seed, 유일하고 안전한 node ID·output alias, 선언된 노드 참조, seed와 연결된 그래프인지 검사한다.
- class/property 존재·fragment 포함·ObjectProperty/DatatypeProperty 구분·domain/range·하위 클래스 호환을 검사한다.
- output이 비거나 seed label만 반환하는 plan을 거절한다. datatype output이 ABox 전체에서 0건이면 거절하되, 이 존재 확인 자체가 실패하면 TBox 판정만으로 계속한다.
- edge 최대 8개, limit 1~500을 검사한다. HCX 생성 schema는 nodes 9·edges 8·outputs 12개 상한도 안내한다. 전체 파이프라인 단계 수와는 별개다.
- Holding·MetricSnapshot·SubsidiaryRelation·Risk 노드에는 `asOf/sourceId/supportedBy/documentTitle`을 자동 투영하고 `asOf ≤ 2026-08-24`를 건다.
- 실행 후 필요한 evidence 컬럼 중 `None`이 있으면 행을 답변에 쓰지 않고 `abstain_evidence_missing`으로 처리한다. 관계 evidence 클래스가 없는 조회는 사용 술어의 TBox `sourceTable/sourceColumn`과 `snapshot@2026-08-24`를 사용한다.

문서 발행일·발행기관·인용문 속성 상수는 있지만 실제 자동 필수 투영은 위 4종이다. 문서 발행일 cutoff까지 자동 검증하는 것으로 설명하면 안 된다. evidence 클래스가 있는 0행 조회는 누락 행이 없어 `empty`로 반환될 수 있다.

### 6.5 테마 전용 경로와 transport

theme role은 `run_theme_membership`으로 간다. partial·ambiguous를 포함한 실제 Theme 후보마다 고정 plan을 실행하고 행을 이어 붙인다. 코드 목록은 중복 제거하지만 동일 ETF의 여러 테마 행은 남는다. 일부 후보 실패는 trace에 남기고 성공 결과는 유지한다. candidate별 limit이며 최종 합계에 전역 limit을 다시 걸지 않는다.

Graph 연결은 [OxigraphClient](../src/infrastructure/graph_db/client.py)가 담당한다.

```text
OXIGRAPH_REMOTE_STORE_PATH (마운트된 파일시스템)
 → 로컬 read-only 스토어 (기본 artifacts/oxigraph)
 → OXIGRAPH_FALLBACK_ENDPOINT 또는 OXIGRAPH_ENDPOINT
```

스토어 가용성 장애만 다음 연결로 넘어간다. 정상 빈 결과·잘못된 SPARQL은 failover 사유가 아니다. 실행 게이트는 SERVICE·쓰기 키워드를 차단하고 SELECT/ASK만 받는다. 기본 결과 상한 10,000행이며 로컬은 초과 오류, HTTP는 해당 행 수로 절단한다. 인덱스 구축만 `max_rows=None`으로 전체 조회한다.

### 6.6 Graph 결과 상태

| 상태 | 의미 |
|---|---|
| `ok`, `empty`, `chained` | 결과 있음, 결과 0행, terminal에 포함될 중간 단계 |
| `abstain_no_seed_text` | 관계 주체 이름 없음 |
| `abstain_entity_not_found`, `abstain_entity_ambiguous` | seed 부재·모호성 |
| `abstain_schema_unresolved` | TBox fragment 생성 실패 |
| `abstain_invalid_graph_plan` | 고정 plan 또는 HCX 시도 검증 실패 |
| `abstain_graph_execution_failed` | compile/실행 실패 |
| `abstain_evidence_missing` | 필요한 evidence 부재 |
| `abstain_exception` | 노드 최외곽에서 잡은 예외 |

orchestrator의 상세 `attempts/schema_fragment/graph_plan/trace`는 반환되지만, 노드는 그중 `status/rows/entity_codes/evidence/entity/sparql/note`만 step 결과에 보존한다. 모든 내부 실패 상세가 최종 trace·답변에 남는 계약은 아니다.

## 7. Vector content 검색 계약

근거: `nodes._run_vector_step`, [vector_search.py](../src/tools/vector_search.py), [VectorDBClient](../src/infrastructure/vector_db/client.py).

### 7.1 검색 순서와 제한

1. Intent의 상품명과 의존 RDB 행의 코드·이름, Graph의 entity_codes를 모은다. 코드 후보와 이름 후보 각각 최대 50개다.
2. `enriched.product_master`의 `source_key/name` 완전일치 OR로 product_id 최대 50개를 해소한다.
3. `vec.product_coverage`를 조회해 matched 계열·unavailable·download_failed·unknown으로 요약한다.
4. 최대 3개 topics와 fields에서 요청 섹션 힌트를 만든다. 원문에서 직접 섹션을 추정하지 않는다.
5. topic별 `원문 + topic`, topic이 없으면 원문을 임베딩하여 검색한다. 여러 topic 검색은 순차 호출이다.
6. chunk_id별 최고 점수만 남기고 cosine 점수 **0.45 이상**을 답변 후보로 사용한다.

| 요청 표현 | `section_type` |
|---|---|
| 전략·투자목적·운용목표·운용방침 | `objective_strategy` |
| 위험·리스크 | `risk` |
| 기초지수·비교지수·벤치마크·추적 | `base_index` |

기본 top-k는 검색당 5, client 허용 범위는 1~20이다. 상품을 지목했으나 product_id가 하나도 해소되지 않으면 `no_product_match`로 중단한다. 반대로 처음부터 상품 스코프가 없으면 전체 문서 검색을 허용한다. 여러 상품 중 일부만 해소된 경우 미해소 상품별 실패를 따로 보장하지 않는다.

### 7.2 물리 데이터와 임베딩

`vec.document_chunk`와 `vec.chunk_embedding`을 content_hash·embedding_model·model_revision으로 조인한다. `vec.document_product` EXISTS로 상품 범위를 제한해 문서-상품 다대다로 인한 검색 청크 중복을 피한다. 모델 `bge-m3`, 차원 1024를 고정 필터로 사용한다.

청크는 `chunk_id/document_id/section_type/citation_text/chunk_text/score/effective_as_of/published_at/source_url/product_ids`로 정규화한다. 검색 SQL은 날짜 컬럼을 반환하지만 **cutoff WHERE 조건이 없고 노드에서도 재검사하지 않는다.** 검색 시점의 미래정보 차단은 현재 구현만으로 보장되지 않는다.

`DATABASE_URL` 또는 `PGDATABASE`가 있으면 직접 PostgreSQL 연결, 없으면 RDB SQL API를 사용한다. 직접 연결 실패 시 API로 재시도하는 failover가 아니다. `VECTOR_DB_TIMEOUT`은 connect_timeout이며 SQL statement 전체 시간 제한이 아니다.

### 7.3 상태 계약

| 상태 | 판정 |
|---|---|
| `ok` | 임계값 이상 청크 존재. 일부 주제 미확보여도 가능 |
| `low_confidence` | 검색 결과는 있으나 전부 0.45 미만 |
| `no_product_match` | 지목한 상품 후보를 product_master에서 전혀 해소하지 못함 |
| `no_document` | 해소 상품의 matched=0이며 unavailable/download_failed 존재, 검색 결과 없음 |
| `topic_not_covered` | 결과가 없고 요청 섹션 힌트 존재; 섹션 자체의 부재를 별도 COUNT로 증명한 것은 아님 |
| `no_hit` | 나머지 빈 검색 |
| `abstain_vector_unavailable` | 임베딩·DB 등 예외 |

`topic_coverage.requested/uncovered`를 별도 기록한다. coverage 판정은 검색된 청크의 섹션 집합 기준이며 **상품별×주제별 완전성 검사**는 아니다. status=ok 하나만으로 요청 항목 전체를 답할 수 있다고 판단하면 안 된다.

## 8. 결과 병합·Evidence 기반 답변

### 8.1 병합

`merge_results_node`는 RDB target 행, 모든 Graph 행, Vector 청크 행을 합친다. RDB entity_lookup 행은 제외한다. `_domain`, `_step_id`로 출처를 태그하며 UNION 행은 자체 domain을 우선한다. Graph가 RDB 필터 입력으로 쓰였어도 원래 Graph 행을 제거하지 않는다.

Vector 행에는 출처문서·섹션·인용·기준일·출처URL·상품ID·유사도가 들어가며 본문은 400자로 절단한다. 전문은 step_results에 남는다. 여기서 공통 상품키 JOIN, 도메인 간 중복 제거, 추가 순위 계산은 하지 않는다.

### 8.2 최종 응답 객체

```json
{
  "question_id": "질문 식별자",
  "question": "원문",
  "retrieved_context": "실제 SQL·도메인 기준일·Graph 관계/evidence·Vector 인용 요약",
  "think_trace": "실행 로그에 근거한 짧은 처리 요약",
  "answer": "근거 데이터에 기반한 한국어 답변"
}
```

`question_id/question/retrieved_context`는 코드가 채운다. HCX는 `think_trace/answer`만 구조화 출력한다. `think_trace`는 실행 기록 요약 용도로 프롬프트에서 제한하며, 별도 내부 추론 수집 기능은 없다. 최종 객체는 JSON 문자열로 `state.answer`에 들어간다.

`retrieved_context`에는 RDB의 도메인·반환 건수·대표 날짜·SQL, Graph 상태·관계·evidence 개수 또는 첫 TBox 출처, Vector 상태·메모·최대 2개 청크 인용을 담는다. 모든 행의 근거 문서 전문이나 수치별 sourceColumn 매핑을 최종 객체에 구조화하는 계약은 아니다.

### 8.3 답변 생성과 미커밋 보강

- merged_rows가 비면 HCX를 호출하지 않고 답변불가 JSON을 만든다. 라우트 사유·Vector 상태·RDB skipped_reason 등을 붙인다. 모든 RDB `error`와 모든 Graph 오류 원인이 답변 사유에 포함되지는 않는다.
- 행이 있으면 기본 10행, 명시 sort.limit은 최대 20행으로 preview를 만든다. 도메인별로 예산을 나눈 후 남는 예산을 채운다. 도메인마다 최소 1행을 배정하므로 요청 예산이 도메인 수보다 작으면 예산을 초과할 수 있다.
- HCX에 요청 항목, 문서 근거 상태, Intent 조건 요약, 실제 SQL assumptions, 실행 로그, preview를 전달한다. 원문 조건 요약이 실제 실행 보증은 아니므로 assumptions·핸드오프 제약과 함께 해석해야 한다.
- 빈 배열·기호뿐인 답변 또는 **30자 미만 답변**을 무효로 보고, 예외와 함께 재시도 대상에 둔다. 최대 2회이며 다음 예산은 `max(3, budget // 2)`다. 첫 limit이 1~2이면 재시도 예산이 오히려 3이 될 수 있다.
- 예외 클래스 이름에 `RateLimit`이 있으면 즉시 재시도를 멈춘다. 계속 실패하면 마지막 preview를 코드로 행 나열한다. 길이가 충분하지만 의미·값이 틀린 답변을 검출하는 검증기는 아니다.
- RDB 제외 필드 메모·Graph abstain·Vector 미확보 신호로 항목 상태를 만들고, 미산출 사유 footer를 코드로 붙인다. 미산출 신호가 없는 항목은 기본 `산출`이므로 실제 값 존재를 증명하는 판정은 아니다.
- 소수 결과에서 상품명이 답변에 하나도 없으면 상품명 목록을 앞에 붙인다. RDB 행이 있으면 도메인 대표 수치 날짜와 배포일 footer를 붙인다.

Graph abstain 사유 중 편입·자회사 관계는 고정 문구로 “주최측 원천에 없어 외부 데이터가 필요함”을 덧붙인다. 이 문구는 현재 외부 데이터 전체의 존재 여부를 조회한 결론이 아니다. 발행사 관계는 RDB가 대체할 수 있다는 가정으로 미산출 추가에서 제외하며, 실제 대체 성공을 검사하지 않는다.

## 9. 설정·운영·성능 계약

### 9.1 LLM과 연결 설정

| 설정 | 기본값·동작 |
|---|---|
| Intent/검수/계획/SQL | HCX-007, temperature=0, thinking effort=none, max_tokens=2048, timeout=25초 |
| 답변 | HCX-007, 동일 생성 설정, timeout=90초 |
| 인증 키 이름 | `CLOVASTUDIO_API_KEY → CLOVA_API_KEY → clova` 순서로 읽어 SDK 이름 연결 |
| 임베딩 | `CLOVA_EMBEDDING_MODEL`, 기본 bge-m3; 출력 1024차원 검사 |
| RDB | `RDB_API_BASE_URL`, 선택 `RDB_API_KEY`, `RDB_API_TIMEOUT` 기본 30초 |
| Graph | remote/local store 경로와 fallback endpoint; `OXIGRAPH_TIMEOUT` 기본 60초(HTTP) |
| Vector | `VECTOR_SCHEMA=vec`, `DATABASE_URL` 또는 `PGDATABASE`와 PG 접속 변수, `VECTOR_DB_TIMEOUT=3` |

인증 값은 명세에 싣지 않는다. 임베딩 생성 모델을 환경변수로 바꿔도 Vector 검색의 모델 필터는 bge-m3 고정이므로 차원이 같다는 이유만으로 모델 변경 호환성을 보장하지 않는다.

패키지 선언은 [requirements.txt](../requirements.txt)를 따른다. 주요 선언은 langchain-naver 0.1.1, langgraph 1.2.11, pyoxigraph 0.5.10, rdflib 7.6.0이며 이 문서 작성 환경의 설치 버전 검증 결과를 뜻하지 않는다.

### 9.2 15초 목표의 현재 상태

**E2E 15초는 목표이며 현재 런타임 보장이나 통과 판정이 아니다.** 분석·검수 2회가 항상 있고, 행이 있는 보통 경로는 답변 HCX까지 최소 3회의 직렬 LLM 호출을 거친다. 미해소 컬럼, SQL fallback·수정, Graph 생성, 답변 재시도로 호출이 늘어난다. 전체 요청 deadline·남은 시간 전달·전역 호출량 제한·타임아웃 시 즉시 공통 fallback은 없다. 캐시 최초 구축도 cold 지연에 포함될 수 있다.

| 근거 기록 | 당시 수치 | 해석 한계 |
|---|---|---|
| [09-03 E2E 리포트](../test/pipline-test/2026-09-03_pipeline_latency_quality_report.md) | warm p50 25.0초, p95 144.0초; 품질 15/104회차 | Graph 인덱스·결정론 SQL·현재 답변 보강 이전 기준선 |
| [09-05 리뷰 §12](../test/pipline-test/2026-09-05_pipeline_plan_eng_review.md) | Q10 seed 61,000ms→84ms, E2E 140.8초→29.7초 | 변경 전 warm p50과 변경 후 1회 비교; 현재 전체 p95 아님 |
| 같은 문서 §12-B | Q4 E2E 19.4초→10.3초, RDB 9.9초→0.9초; Q18 E2E 43.1초 | 선택 문항 1회 기록. SQL 개선과 E2E 목표 달성은 별개 |

09-05 Lane C trace 파일도 있으나 현재 작업 트리 전체를 고정한 35문항 반복 검증의 대체 자료로 사용하지 않았다. 과거 문서의 “완료/미커밋” 표시는 당시 기록이며 현재 반영 상태는 §1의 git 기준을 따른다.

## 10. 데이터 규칙 준수 상태와 미충족 사항

이 절은 새 기능 제안이 아니라 현재 스펙의 한계다. 원천 데이터를 재프로파일링하거나 코드·온톨로지를 수정해서 해결한 결과가 아니다.

| 규칙·계약 | 확인된 구현 | 남은 차이 |
|---|---|---|
| 질의 분석·답변은 NCP HyperCLOVA X | 활성 LLM 클라이언트 HCX-007 | 규칙·행 나열 fallback을 제외한 별도 모델 경로 없음 |
| 데이터 cutoff 08-24 | Graph 관계 asOf 필터, snapshot 상수 | Vector 검색 cutoff 없음; RDB 전역 행 날짜 필터·문서 발행일 검증 없음 |
| 주최측 우선·충돌 기록 | 답변 프롬프트에서 RDB 우선·충돌 언급 지시 | 자동 충돌 탐지·구조화 conflict evidence 없음 |
| 완전일치·유사명 대체 금지 | Graph resolver, 성공한 RDB 코드 해소, Vector ID 해소 | RDB 해소 실패 후 상품명 LIKE·말미 토큰 제거 fallback |
| ETN 혼입 제외 | 결정론 SQL의 국내ETF 기본 필터, Graph ETF 타입 게이트 | LLM SQL fallback·수정 후에는 같은 조건의 코드 검증 없음 |
| 펀드 그레인 | `raw.prfd01n001`, itm_no 카탈로그 | 저장소 지침의 물리명과 다름; Agent에서 원천 1행=1펀드 유일성 검사 없음 |
| 채권 복합키 | 카탈로그 보강 정보에 `(pd_no,pd_exg_mkt,info_seq)` 기록 | 기본 SELECT의 유일 상품 처리·중복 제거·복합키 evidence 강제 없음 |
| 괴리율·추적오차 사용 금지 | 금지 컬럼 집합은 buyable_quantity만 | rdb_schema는 du_diff_rt/du_chas_errt를 사용 가능한 개념으로 등록. AGENTS.md와 상충하므로 사용 승인 근거로 해석 불가 |
| 해외ETF 지수 sentinel NULL 처리 | 카탈로그에 sentinel 설명 | 공통 sentinel 정규화 없이 text 값 조회 가능 |
| 국채 정상 무등급 | ordinal 조건의 NULL은 IN에 포함되지 않음 | Agent의 UnratedByDesign/RatingUnknown 명시 분리·표기 없음 |
| 총보수 보강 | 국내ETF charge_rt_final JOIN·테이블 존재 검사 | 원격 테이블 부재면 해당 단계 skip; 자동 데이터 보강 없음 |
| 수치마다 실제 날짜·출처 컬럼 | SQL와 도메인 날짜 요약·footer | 수치/행별 날짜·컬럼의 구조화 검증 및 답변 인용 완전성 검사 없음 |
| 관계 조건 충족 후 후속 조회 | Graph→RDB 코드 IN | 빈 Graph 결과 미차단, 복수 조건 합집합, UNION 경로 필터 누락 |
| 시간 구간·다단계 관계 | Intent·plan에 상대 기간/관계 조건 저장 | terminal frame에서 버려져 “최근 6개월 이력” 등으로 실행 보장 불가 |
| 5종 답변불가 사유 분리 | ordinal AAAA 검증, Graph 타입·seed 오류 등 부분 사유 | 공통 ABSTAIN subtype 없고 일부 오류가 최종 답변에서 소실 |
| 미확보 ≠ 미편입 | Vector coverage와 Graph abstain 일부 설명 | 전체 관계 coverage 검사·빈 검색 의미 구분을 끝까지 강제하지 않음 |

추가로, 조회 결과의 `count`·답변 “전체 M건”은 API가 돌려준 행과 Graph·Vector 병합 행을 센 값이다. 서버 절단·Graph limit·복수 관계·문서 청크가 섞인 상황에서 전체 모집단 또는 고유 상품 수로 해석하면 안 된다. 원격 결과 절단 여부를 client가 보존하지 않는 점도 함께 고려해야 한다.

## 11. 검증 결과와 재현 범위

### 11.1 이번 작성 중 수행한 검증 — 2026-09-06

| 명령 | 결과 | 범위 |
|---|---|---|
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s script/agent_test -p 'test_*.py'` | **71개 통과** | SQL 컴파일, 도메인 기준일, 답변 생성, Vector 노드·근거 전달; 외부 호출 mock |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s script/graph_db -p 'test_*.py'` | **27개 통과, 1개 skip** | Graph transport 전환·엔티티 인덱스 계약. 실 스토어 회귀는 opt-in이라 skip |

총 99개 테스트 중 98개 통과, 1개 skip이다. 답변 보강 테스트는 현재 미커밋/미추적 테스트를 포함한다. 이 결과는 네트워크 서비스 가용성·최종 정답률·15초 충족을 입증하지 않는다.

### 11.2 수행하지 않은 검증

- HCX·원격 SQL/pgvector·원격 Graph를 사용하는 새 E2E 및 35문항 반복 품질·지연 측정.
- `RUN_STORE_REGRESSION=1` 실제 Oxigraph 인덱스/스캔 동등성 회귀. 기존 09-05 결과는 §9의 과거 실측으로만 인용.
- 원천 데이터 재프로파일링과 전체 데이터 날짜·sentinel·유일키 재검증.
- `validate_ontology.py`, `validate_external.py`: 이번 변경은 명세서 추가뿐이며 온톨로지·외부 데이터는 변경하지 않아 실행하지 않음.

### 11.3 다음 명세 갱신의 확인 순서

1. §5.5의 핸드오프와 §10의 규칙 상충을 회귀 fixture로 확인해, 실행 가능한 범위와 차단해야 할 범위를 고정한다.
2. 미커밋 답변 보강의 반영 커밋을 확정하고 코드·테스트·데이터 스냅샷을 함께 식별한다.
3. 같은 고정 버전으로 전체 골든셋을 재측정해 품질·15초·429 결과를 분리한다.
4. 그 결과를 확인한 뒤에만 이 문서의 “부분 구현/미충족”을 “검증 완료”로 변경한다.

현재 Agent는 HCX 의도 분석·검수와 규칙 계획, RDB·Graph·Vector 조회, 근거 기반 답변 생성이 연결된 구현이다. 운영 계약의 충족 여부는 검색 엔진 연결 여부와 별개이며, §10의 제한을 포함한 상태가 09-06 명세의 기준이다.
