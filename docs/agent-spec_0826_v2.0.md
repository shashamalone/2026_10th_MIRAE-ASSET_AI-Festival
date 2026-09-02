# 실험 적용 권장 최종 구조(0826)

무엇을 바꾸는가 — 대체 대상


| 위치                   | 현재                           | 문제                                             |
| -------------------- | ---------------------------- | ---------------------------------------------- |
| tools/validate.py:30 | 정규식 신용등급 `([A-Z]{1,4}[+-]?)` | "AAAA등급 회사채"는 잡지만 "트리플A보다 높은"은 못 잡는다           |
| tools/validate.py:38 | 문자열 `"발행한 회사채" in question`  | 다른 도메인 위반 표현을 전부 놓친다                           |
| tools/validate.py:35 | `"확정" in question`           | 미래값 판정이 단어 하나에 걸려 있다                           |
| tools/route.py:33    | task 3종만 통과                  | relation · explanation · recommendation이 전부 막힘 |
| tools/route.py:39    | 1단계 고정                       | execution_plan이 실질적으로 상수다                      |


절대 바꾸지 말 것 — LLM Planner를 넣어도 유지


| #   | 항목                                    | 이유                                                                                               |
| --- | ------------------------------------- | ------------------------------------------------------------------------------------------------ |
| 1   | compile_plan 11개 관문 (tools/rdb.py:94) | LLM이 뭘 계획하든 등록된 binding · 허용된 JOIN · usage 허가를 넘어설 수 없다. Planner는 LogicalPlan까지만, 컴파일은 지금 코드가 한다 |
| 2   | evidence 생성 (tools/rdb.py:177)        | 출처 컬럼 · 기준일은 조회 시점에 확정된다. LLM이 나중에 붙이면 지어낸 근거다                                                   |
| 3   | LEAK 누출 검사 (agent/query_frame.py:459) | 1단계가 fp: 나 물리 컬럼을 만들지 않는다는 경계                                                                    |
| 4   | 결정적 fallback                          | LLM 호출이 실패하거나 15초를 넘기면 규칙 경로로 되돌아간다                                                              |


권장 순서


| 단계  | 내용                                                                                              |
| --- | ----------------------------------------------------------------------------------------------- |
| 1   | 계약부터 고정. `validate_query(question, grounded) -&gt; dict                                         |
| 2   | 규칙 먼저 → 걸리면 즉시 ABSTAIN (LLM 호출 안 함). 규칙 통과 → LLM이 한 번 더 본다. 반대로 하면 안 된다                         |
| 3   | LLM은 판정이 아니라 후보 제시. audit() 교훈대로 "해당 없음"을 enum 첫 값으로 준다 (안 주면 정밀도 8.6%까지 하락)                    |
| 4   | route 확장은 graph_only → graph_then_rdb 순으로 하나씩. 실측 통과한 것만 enum에서 연다. MAX_PLAN_STEPS=3 assert는 유지 |
| 5   | 측정 없이 머지 금지. 같은 35문항으로 비교해 RDB 14문항이 하나라도 퇴행하면 롤백                                               |


첫 커밋 제안은 tools/[validate.py](http://validate.py)에 LLM 경로를 규칙 7개 뒤 8번째로 붙이되 기본은 off. 베이스라인 대비 diff가 한눈에 보이고 되돌리기도 플래그 하나입니다.

세 가지만 짚겠습니다.

1. 2단계와 3단계가 충돌할 여지가 있습니다. "규칙이 확신하는 건 LLM이 뒤집지 못한다"와 "LLM이 후보를 제시한다"를 같이 두려면 권한 경계를 한 줄로 못 박아야 합니다. LLM은 규칙이 "모름"으로 남긴 구간에서만 판정권을 갖고, 규칙이 이미 PASS나 ABSTAIN을 낸 항목은 건드리지 않는 식입니다.
2. 5단계의 베이스라인은 코드보다 먼저 저장해두세요. 플래그 off 상태의 35문항 결과를 파일로 커밋해두면 이후 비교가 자동이 됩니다. 지금 cutoff 때문에 전부 ABSTAIN이 나오는 상태라면 그 상태가 베이스라인이 되어버리니, business_rules.json:3을 먼저 고친 뒤에 뜨는 게 순서입니다.
3. [route.py](http://route.py):39의 "1단계 고정"은 지금 푸는 게 아닙니다. graph capability가 catalog에 등록되기 전까지는 execution_plan이 상수인 게 정상이고, 4단계에서 graph_only가 열릴 때 같이 풀면 됩니다.

```text
사용자 질문
  ↓
① HCX-007 Query Frame
  ↓
② TBox Vector Grounding
   - 원문 + 추출 슬롯별 검색
   - Top-3 의미 후보
  ↓
③ Semantic Schema Context
   - TBox 후보 검증
   - RDB binding
   - Graph capability/path
   - Vector content domain
  ↓
④ Plan & Routing
   ├─ 단순·검증 경로: deterministic fast path
   └─ 복합 경로: HCX가 capability 조합 후보 생성
  ↓
⑤ Deterministic Route Guard
   - capability whitelist
   - dependency/type 검증
   - cutoff/evidence 검증
  ↓
⑥ Engine compiler/executor
   ├─ RDB LogicalPlan → SQL → PostgreSQL
   ├─ GraphLogicalPlan → SPARQL → pyoxigraph
   └─ VectorPlan → entity-scoped content retrieval
  ↓
⑦ 결과·Evidence 검증
  ↓
⑧ Evidence-based Answer
```

## 1. TBox Vector Grounding에 적용할 실험 결과

실험 2에서 확인된 결과는 다음과 같습니다.

- Strict Top-1: 75.0%
- Recall@3: 96.7%
- 1·2위 점수 차이 0.02 미만: 30%

따라서 TBox 검색 결과 하나를 확정값으로 쓰면 안 됩니다.

```json
{
  "schema_hits": [
    {
      "term_uri": "fp:ratingRank",
      "score": 0.62,
      "rank": 1
    },
    {
      "term_uri": "fp:creditRatingLabel",
      "score": 0.60,
      "rank": 2
    },
    {
      "term_uri": "fp:hasCreditRating",
      "score": 0.58,
      "rank": 3
    }
  ]
}
```

이 단계의 책임은 “가능성 있는 의미 후보 검색”까지입니다. `fp:ratingRank`를 최종 실행 개념으로 확정하는 것은 다음 단계가 담당해야 합니다.

실험 3 결과에 따라 다음도 분리해야 합니다.

- TBox concept index: class/property/comment
- 코드값 resolver: AAA, AA-, 주식형, 채권형 등
- Entity resolver: VOO, 에코프로, KODEX 200 등
- Vector content index: 문서·공시·위험요인

코드리스트 91건을 TBox 인덱스에 섞었을 때 Recall@3가 96.7%에서 90.0%로 떨어졌기 때문에 하나의 인덱스로 합치면 안 됩니다.

## 2. Semantic Schema Context 출력 수정

제시한 구조에서는 TBox 검색 결과와 Semantic Schema Context 결과가 동일합니다. 이렇게 되면 physical binding 단계가 빠집니다.

Semantic Schema Context에는 최소한 다음 정보가 추가돼야 합니다.

```json
{
  "concept_candidates": [
    {
      "term_uri": "fp:ratingRank",
      "score": 0.62,
      "verified": true
    }
  ],
  "verified_bindings": [
    {
      "concept_uri": "fp:ratingRank",
      "engine": "rdb",
      "binding_id": "bond.rating_rank",
      "table": "enriched.bond_kr_enriched",
      "column": "crd_grd_rank",
      "allowed_operations": ["select", "filter", "sort"],
      "business_rule": "AA- 이상은 rating_rank <= 4"
    }
  ],
  "available_capabilities": [
    {
      "capability_id": "bond_filter_by_rating_and_remaining_days",
      "engine": "rdb",
      "input_types": ["fp:Bond"],
      "output_types": ["fp:Bond"],
      "status": "verified"
    }
  ],
  "unresolved": []
}
```

Graph 관계라면 다음처럼 나와야 합니다.

```json
{
  "concept_uri": "fp:hasHolding",
  "engine": "graph",
  "capability_id": "company_to_holding_etf",
  "path_id": "company_issued_security_inverse_holding_etf",
  "required_evidence": [
    "fp:asOf",
    "fp:sourceId",
    "fp:supportedBy"
  ]
}
```

즉, 역할은 다음처럼 구분됩니다.

```text
TBox Vector Grounding
= 무슨 의미일 가능성이 높은가

Semantic Schema Context
= 그 의미를 실제로 어느 엔진에서 어떤 검증된 계약으로 실행할 수 있는가
```

## 3. Query Frame에 적용할 실험 결과

실험 4 결과에 따라 Query Frame의 모든 값을 같은 수준으로 신뢰하면 안 됩니다.


| 슬롯                     | 실험 결과          | 적용 방법                     |
| ---------------------- | --------------: | ------------------------- |
| JSON/schema            | 35/35          | 계약값 사용                    |
| operator/unit/temporal | 100%           | 계약값 사용 후 business rule 변환 |
| task                   | 97.1%          | Guard 후 사용                |
| constraints            | R/P 75.8/78.1% | 원문·metadata로 재검증          |
| relation endpoints     | 50%            | Graph path 확정에 직접 사용 금지   |
| computation recall     | 50%            | capability catalog로 재검증   |
| validation 유형          | 60%            | ABSTAIN 확정에 직접 사용 금지      |


특히 Query Frame의 다음 출력은 힌트여야 합니다.

```json
{
  "relations": [
    {
      "path": ["에코프로", "자회사", "ETF"]
    }
  ]
}
```

이 값으로 바로 SPARQL을 만들면 안 되고, `company_to_subsidiary_holding_etf` 같은 검증된 capability를 찾아야 합니다.

TBox 검색 입력도 Query Frame만 사용하지 않고 다음을 합쳐야 합니다.

```text
원문 전체 검색 결과
+
requested_fields별 검색
+
constraints.field_text별 검색
+
relations.raw별 검색
```

## 4. Planner LLM에 적용할 실험 5 결과

실험 5에서 자유형 Planner는 운영 불가 수준이었습니다.

- Engine Selection Accuracy: 24.8%
- Dependency Accuracy: 21.0%
- SQL Executability: 22.6%
- Execution Accuracy: 0%
- Hallucinated Schema Rate: 42.9%

따라서 HCX Planner가 다음을 생성하게 하면 안 됩니다.

- 실제 테이블명·컬럼명
- JOIN 조건
- raw SQL
- raw SPARQL
- 임의 Graph predicate
- 임의 Vector index
- 자유로운 engine 이름

Planner는 검증된 capability ID만 조합해야 합니다.

```json
{
  "query_type": "graph_then_rdb",
  "steps": [
    {
      "id": "G1",
      "engine": "graph",
      "capability_id": "company_to_subsidiary_holding_etf",
      "inputs": {
        "entity_ref": "E1"
      },
      "depends_on": []
    },
    {
      "id": "R1",
      "engine": "rdb",
      "capability_id": "etf_latest_aum_rank",
      "inputs": {
        "entity_ids_from": "G1"
      },
      "depends_on": ["G1"]
    }
  ]
}
```

여기서 Planner는 “무슨 순서로 capability를 실행할지”만 판단합니다. SQL과 SPARQL은 보지 못합니다.

## 5. 모든 질문에서 Planner LLM을 호출하면 안 되는 이유

실험 6에서 이미 HCX Query Frame 한 번만으로도 다음 문제가 있었습니다.

- 실시간 stability timeout 62/70
- qualification HTTP 429 5건
- 정상 완료 latency 약 2.66~4.77초
- Query Frame 목표 5초
- 전체 E2E 목표 15초

여기에 Planner HCX 호출을 무조건 한 번 더 넣으면 429 가능성과 latency가 증가합니다.

따라서 fast path가 필요합니다.

```text
단일 도메인 + 검증된 RDB capability
  → Planner HCX 생략
  → rdb_only 결정

단일 검증 Graph capability
  → Planner HCX 생략
  → graph_only 결정

여러 capability·engine 조합 필요
  → HCX Planner 호출
  → Route Guard 승인
```

즉, Planner LLM은 범용성 확보를 위한 복합질문에만 사용하고, 이미 검증된 단순 경로는 결정론적으로 실행하는 것이 적절합니다.

Planner를 모든 질문에서 반드시 호출하고 싶다면 운영 코드에 바로 넣지 말고 다음 A/B 실험을 먼저 해야 합니다.

```text
A: deterministic fast path
B: HCX constrained Planner + Route Guard
```

측정 대상은 route 정확도뿐 아니라 429와 전체 15초 성공률까지 포함해야 합니다.

## 6. Route Guard가 최종적으로 검사할 항목

HCX Planner 출력은 다음 조건을 모두 통과해야 합니다.

- `query_type`이 고정 enum에 포함
- 모든 `capability_id`가 catalog에 존재
- capability의 engine과 step engine이 일치
- 입력·출력 entity type이 다음 step과 연결
- dependency에 cycle이 없음
- step 수 최대 3개
- 요청 필드가 선택한 capability로 충족 가능
- RDB table·column이 verified binding에 포함
- Graph class·predicate·path가 whitelist에 포함
- external evidence `as_of ≤ 2026-08-24`
- Organizer 값과 충돌하면 Organizer 우선
- evidence가 필요한 관계에 `supportedBy` 존재
- 비활성 Vector capability를 선택하지 않음

하나라도 실패하면 임의 수정해 실행하기보다 `ABSTAIN_UNSUPPORTED_PLAN`으로 중단하는 편이 안전합니다.

## 7. Executor에 적용할 실험 결과

### RDB

실험 6에서 저장 Query Frame 이후 다음이 통과했습니다.

- Static plan coverage 14/14
- PostgreSQL Gold exact 14/14
- Schema hallucination 0건
- Evidence completeness 14/14

따라서 현재 deterministic RDB compiler는 유지합니다. HCX Planner가 SQL을 만들도록 되돌리면 안 됩니다.

### Graph

실험 7에서 검증된 것은 다음 capability입니다.

```text
Company
 → SubsidiaryRelation
 → Company
 ← Security
 ← Holding
 ← ETF
```

pyoxigraph 실행과 `supportedBy` 계약은 통과했지만, 현재 Agent route에는 연결되지 않았습니다. 먼저 이를 catalog capability로 일반화한 후 `graph_only` branch에 연결해야 합니다.

단, 실험 7은 기존 `2026-07-11` cutoff로 측정됐으므로 현재 기준인 `2026-08-24`로 Store를 다시 만들고 재검증해야 합니다.

### Vector content

Vector content 검색은 아직 코드·corpus·Gold·실행 정확도가 없습니다. 따라서 Planner enum에 이름이 있더라도 다음 조건을 만족하기 전까지 실행 불가로 둬야 합니다.

- 문서 corpus 확정
- 문서별 source/as_of 메타데이터
- entity-scoped retrieval
- Recall@K/NDCG
- evidence quote 정확도
- cutoff 검증

## 8. 기준일 적용 정정

기존 실험 요약 문서에는 `2026-07-11` 기준이 남아 있지만 현재 저장소 계약은 `2026-08-24`입니다.

따라서:

- RDB 주요 수치 `as_of=2026-08-21`: 현재 기준에서는 사용 가능
- 외부 데이터: `as_of ≤ 2026-08-24`
- Graph builder/SPARQL/business rule의 `2026-07-11`: 수정 및 재검증 필요
- 과거 실험 결과: 당시 조건의 결과로 보존하되 운영 승격 판정은 새 cutoff로 재실행

## 9. 권장 구현 순서

1. cutoff 단일 정본을 `2026-08-24`로 통일
2. 전체 5개 TBox를 대상으로 Vector Grounding 구축
3. TBox concept·코드값·entity·content index 분리
4. `SemanticSchemaContext` 출력 계약 구현
5. RDB verified binding을 capability 형식으로 이전
6. Q24 관계를 첫 Graph capability로 등록
7. deterministic fast-path routing 구현
8. HCX constrained Planner를 복합질문에만 추가
9. Planner Route Guard 구현
10. `graph_only` 실행 연결 및 검증
11. `graph_then_rdb` entity handoff 검증
12. Vector content 별도 실험 후 연결
13. 35문항 전체 E2E 및 15초 운영 안정성 재측정

최종적으로 적용해야 할 핵심 원칙은 다음 한 줄입니다.

> HCX는 질문의 의미와 capability 조합 후보를 만들고, 실제 데이터 위치·경로·SQL·SPARQL·실행 허용 여부는 검증된 metadata와 결정론적 코드가 통제해야 합니다.

