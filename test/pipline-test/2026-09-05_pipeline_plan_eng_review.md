# 파이프라인 개선 스프린트 계획 — 엔지니어링 리뷰

리뷰일 2026-09-05 · 대상 `test/pipline-test/2026-09-04_pipeline_action_items_meeting_report.md` · 브랜치 `fix/graph-seed-latency`(코드 변경 전) · 근거 실측 2026-09-03 latency/quality 측정

## 결론 요약

1. **계획의 P0 1번은 겨냥점이 틀렸다.** 계획은 "exact-label 인덱스"를 만들자고 하는데, 직접 측정한 결과 exact 조회는 이미 2~251ms다. 느린 것은 그다음 단계인 정규형 스캔(`_normalized_literal_candidates`)으로 한 번에 2.6~6.1초이고, 5단계 type-suffix 재시도가 이를 두 배로 늘린다. Q10의 seed 1회 61초는 정확히 "클래스 5개 × 2패스 × 6초"다. 계획대로 exact 인덱스를 먼저 만들면 p95가 거의 줄지 않는다.
2. **P0 2번(AST 가드)과 3번(결정론 빌더)은 같은 규칙을 두 곳에 쓴다.** 빌더가 만든 SQL은 금지 컬럼을 쓸 수 없으므로 가드는 LLM 폴백 경로에만 필요하다. 결정: 빌더 우선, 가드는 폴백에만.
3. **테스트가 0건이다.** 계획이 고치는 `resolve_entity`·`_write_sql`·`ATTRIBUTE_CATALOG`를 건드리는 단위 테스트가 없다. 유일한 검증이 2시간짜리 골든셋 재측정이다. 결정: 구현 커밋마다 unittest, `resolve_entity`는 회귀 fixture 의무.
4. **P0 7개 중 주인 있는 것은 2개다.** Query Frame·ABSTAIN·답변 길이 3개는 Graph도 RDB도 아니고, P0 7개 중 5개가 `nodes.py`(1,334줄)를 고친다. 결정: 세 번째 브랜치를 만들고 병합 순서를 Graph → RDB → Intent/Answer로 고정한다.
5. **A/B 두 건 + 재측정을 전부 E2E로 하면 CLOVA 대기만 10시간이다.** 결정: A/B는 단계별 미니셋(intent 단계만, RDB 문항만), E2E는 마지막 1회. 게이트는 "정답률 14.4% 이상"이 아니라 원인별(C 52→26 이하, Critical 15→7 이하, A·B 0 유지, p95 ≤15s)로 건다.
6. 범위는 줄이지 않는다. 항목 수는 측정 근거가 있어 정당하다. 문제는 개수가 아니라 겨냥점·주인·순서였다.
7. **외부 의견(Codex)이 규칙 위반 2건과 순서 모순 1건을 추가로 잡았다.** 상품명을 무조건 `contains`로 매칭하는 코드(`utils.py:131-134`)는 AGENTS.md 완전일치 원칙 위반이고, RDB 근거에 기준일 08-24를 일괄 표기하는 코드(`nodes.py:1170`)는 실질 기준일 08-21과 어긋난다. 로드맵 17.6초에는 P1 항목 A5가 들어 있어 A5 없이는 p95 20.2초(추정)다. 세 건 모두 계획에 반영한다(T12~T14).

## 1. 리뷰 방법

- Step 0 범위 확인 → 아키텍처 → 코드 품질 → 테스트 → 성능 순으로 진행했고, 이슈마다 사용자 결정을 받았다(D1·D2·이슈 1~4).
- 계획이 지목한 파일 11개와 심볼 16개가 실제로 존재하는지 대조했다. 전부 존재한다.
- 계획의 핵심 가정(exact 조회가 느리다)을 실제 Oxigraph 스토어(1,169,374 트리플)에서 직접 측정해 검증했다.
- 외부 의견은 Codex(`model_reasoning_effort=high`, read-only)로 별도 실행했다. §9 참조.

## 2. 검증한 사실

### 2.1 Graph 엔티티 해소 경로별 실측 (2026-09-05, mirea python, 로컬 Oxigraph)

| 입력 | 클래스 | 1단계 exact ms | 3단계 normalized ms |
|---|---|---:|---:|
| KODEX 200 | ETF | 251 | 6,053 |
| 에스케이하이닉스 | Company | 2 | (해당 없음) |
| 삼성전자 | Security | 2 | 5,775 |
| 우주항공/방산 | Theme | 18 | 2,582 |

- `resolve_frame_seed` 전체: role=issuer "에스케이하이닉스" 616ms resolved, role=product "KODEX 200" 3ms resolved. **이름이 1단계에서 잡히면 seed는 1초 안에 끝난다.**
- 2026-09-03 trace의 SPARQL 468건 분포: p50 16ms, p90 9,229ms, p95 11,891ms, max 30,102ms. 1초 초과 198건, 5초 초과 118건. 두 무리(16ms / 5~20초)로 갈리며, 앞은 exact, 뒤는 normalized 스캔이다.

### 2.2 seed 비용이 61초가 되는 경로

`graph_entity.py:241 resolve_entity` → 1단계 exact 실패 → 3단계 `_normalized_literal_candidates`(클래스 전체 스캔 + `FILTER(REPLACE(LCASE(...)))`, 색인 불가) → 4단계 없음 → **5단계 `graph_entity.py:309`에서 말미 토큰을 떼고 1~4단계를 재실행**. `resolve_frame_seed`는 `_ROLE_CLASS_ORDER`(`:323`)를 따라 role=product면 클래스 5개(ETF·PublicFund·Bond·ETN·Product)를 순서대로 시도하고 5개 전부 `NORMALIZED_CLASSES`에 속한다.

```
seed 1회 (role=product, exact 실패 시)
  for cls in [ETF, PublicFund, Bond, ETN, Product]:      # 5개
      exact(cls)          ~0.2s
      normalized(cls)     ~6s   <── 병목
      type-suffix 재시도 → exact + normalized 다시  ~6s   <── ×2
  = 5 × 2 × 6s ≈ 60s
```

실측 회차별 seed 합계: Q10 2회 122.8s(=61s/회), Q26 5회 117.3s, Q22 4회 92.5s, Q23 2회 70.8s, Q27 3회 55.6s.

### 2.3 계획이 놓친 사실 정정

| 계획 문면 | 실제 |
|---|---|
| "exact/normalized label 해소가 클래스별 SPARQL scan을 반복" (§3) | exact는 `_exact_candidates`(`:133`)가 UNION 리터럴 일치로 이미 색인을 탄다. 스캔은 normalized만이다 |
| "관계마다 동일 seed를 재조회" (§2 중복 retrieval) | `graph_orchestrator.run()`(`:323`)이 terminal 단계당 1회 seed를 부른다. 중간 단계는 `nodes.py:638` graph_search_node가 `chained`로 건너뛴다. 재조회는 terminal 관계가 여럿일 때만 생기고, exact가 잡히면 회당 1초 미만이라 인덱스 뒤에는 부차적이다 |
| "Graph exact-label 인덱스·seed 공유"가 작업 순서 첫 항목 (§7) | 첫 항목은 **normalized·segment 키 인덱스**여야 한다. exact 인덱스만 먼저 만들면 시간이 줄지 않는다 |

## 3. 이슈와 결정

### 이슈 1 — Graph 인덱스 범위 [Architecture, P0, confidence 9/10] → **결정 A: 정규형 + 세그먼트 키 모두 색인**

- 근거 코드: `graph_entity.py:210-233` `_normalized_literal_candidates`는 `?entity rdf:type ?actual_class . ?actual_class rdfs:subClassOf* fp:{class}`로 클래스 전체를 바인딩한 뒤 `FILTER(_segment_match(...))`로 걸러낸다. 리터럴 제약이 WHERE 패턴에 없어 색인을 쓸 수 없다.
- 지켜야 할 계약: `graph_entity.py:203 _segment_match`는 `"/"` 구분자 경계 일치다. `우주항공/방산` 테마가 `우주항공`으로 잡혀야 한다. 정규형 키만 dict에 넣으면 이 경로가 조용히 사라진다. `graph_entity.py:160 _rows_to_candidates`의 모호성 판정은 행 수가 아니라 **고유 entity 수**다. 인덱스도 URI 단위로 접어 세야 한다.
- 설계 요지: 스토어 오픈 시 클래스별로 `name/label/alt/code`를 1회 스캔해 `(class, normalized_key) → {uri...}`와 `(class, segment_key) → {uri...}` 두 dict를 만든다. `_normalized_literal_candidates`가 SPARQL 대신 이 dict를 조회하고 `_rows_to_candidates`와 같은 형태로 후보를 만든다. `resolve_entity`의 4단계 순서와 반환 규격은 그대로 둔다. `_company_master`가 이미 `lru_cache(maxsize=1)`로 같은 패턴을 쓰고 있어(`:96`) 관례가 있다.
- 부수 효과: type-suffix 재시도가 dict 조회 2회로 줄어 별도 제거가 필요 없다. seed 공유(요청 내 `(text, role)` 캐시)는 `graph_orchestrator.run`에 얹되, 인덱스 뒤에는 효과가 작으므로 후순위다.
- 인덱스 구축 실패 시 SPARQL 경로로 폴백해야 한다. 비어 있는 인덱스는 전부 `not_found`를 내는 **조용한 실패**다(§7 실패 모드 F1).
- 효과 추정(추정): seed 61초 → 1초 미만. Graph 포함 28회차 p95 176.7s → 보고서 로드맵 A1 가정(seed 500ms)과 같은 70초대.

### 이슈 2 — SQL 가드와 빌더 중복 [Code Quality, P0, confidence 8/10] → **결정 A: 빌더 우선, AST 가드는 LLM 폴백에만**

- 근거: RDB 오답 52회차의 패턴은 넷이다. 플래그 코드값 리터럴(Q12·Q19·Q25·Q30), 폐기 컬럼 `buyable_quantity`(Q1·Q11·Q13), 한글 별칭 공백·없는 테이블(Q6·Q7·Q30), 발행사 필터 누락(Q26·Q27). 앞의 셋은 `rdb_schema.py:1241 ATTRIBUTE_CATALOG`·`:204 DOMAIN_SALE_POLICY`·`:1356 SUBTYPE_CONDITION_MAP`에 이미 값이 있어 빌더가 쓰면 발생할 수 없다.
- 이미 있는 것: `utils.py:51 apply_sale_policy`가 판매가능 조건을 결정론으로 처리하고, `nodes.py:137 _execute_target_step`이 이를 첫 단계로 호출한다(`:140`). 빌더는 이 자리에 얹으면 된다.
- 규칙: 빌더는 **미해소 조건이 하나라도 있으면 SQL을 내지 말고 LLM 폴백으로 넘긴다**. 빈 WHERE로 전 행을 돌려주는 것이 가장 위험한 조용한 오답이다(§7 F4).
- 발행사 필터 누락(Q26·Q27)은 카탈로그 값이 아니라 "질문의 엔티티가 WHERE에 들어갔는가"의 문제다. 빌더가 `frame.entities`를 필수 조건으로 취급해야 한다.
- sqlglot: mirea에 30.17.0이 설치돼 있으나 `requirements.txt`에 없다. 가드에 쓰면 선언을 추가한다. 가드 범위가 LLM 폴백으로 줄면 sqlglot 없이 정규식 허용 목록으로도 충분할 수 있다. spike 하루로 결정한다.

### 이슈 3 — 테스트 부재 [Tests, P0, confidence 9/10] → **결정 A: 구현 커밋마다 unittest + 회귀 fixture**

- 현황: `script/graph_db·vector_db·agent_test`에 unittest 51개. `graph_entity`·`_write_sql`·`_fix_sql`·`ATTRIBUTE_CATALOG`를 건드리는 테스트 0개. 프레임워크는 표준 `unittest`, repo 루트에서 `python script/...py`로 실행, `sys.path.insert(src)`.
- **철칙(묻지 않고 계획에 넣음)**: `resolve_entity`는 기존 동작을 바꾸는 변경이라 회귀 테스트 의무. Q10·Q23·Q26·Q27의 seed 텍스트 + Company/Security/Theme 대표 1건씩으로 현재 SPARQL 경로의 `status/uri/match_mode/candidate_count`를 fixture로 고정하고, 인덱스 경로가 같은 값을 내는지 대조한다.
- 관례: `script/graph_db/test_client_failover.py`의 `FakeClient`처럼 실 스토어 없이 mock으로 돈다. 인덱스 테스트는 소형 in-memory 트리플(수십 개)로 구축·조회를 검증한다.

### 이슈 4 — A/B 비용과 릴리스 게이트 [Performance/Process, P1, confidence 8/10] → **결정 A: A/B는 단계별 미니셋, 게이트는 원인별**

- 근거: 35문항×3회 warm 1바퀴 약 2시간(CLOVA 60k tok/min, 문항당 ~27k 예약). A/B 2건 × 2바퀴 + 재측정 1바퀴 = 10시간 대기.
- verify_intent A/B: intent 단계만 35문항 실행(문항당 LLM 1~2회, 약 20분). `verify_intent`가 intent를 바꾼 35/101회차를 fixture로 고정하고, 조건부 호출안이 그 35건을 몇 건 놓치는지 센다.
- draft 제거 A/B: Graph 미포함 RDB 문항 25개만, rdb 단계까지만 실행.
- 게이트(원인별): warm p95 ≤ 15s · C 원인 오답 52 → 26 이하 · Critical Fail 회차 15 → 7 이하 · A·B 원인 0 유지 · Q31~Q35 ABSTAIN subtype 정확. "정답률 14.4% 이상"은 아무것도 고치지 않아도 통과하는 게이트라 뺀다. 반감 목표는 경험치이므로 미달 시 "수치가 틀린 것"과 "개선이 덜 된 것"을 구분해 기록한다.

### 질문으로 올리지 않은 발견

- `verify_intent`가 35/101회차에서 intent를 바꿨다는 사실만 있고, **그 수정이 정답에 기여했는지는 미측정**이다. intent가 바뀐 회차와 안 바뀐 회차의 정답률을 trace에서 바로 뽑을 수 있다. A/B 전에 이것부터 보면 A/B가 필요 없을 수도 있다.
- P0 4번의 "`analyze_intent` 프롬프트 축소로 잔여 2.6초 대응"은 보고서에서도 근거 없는 (추정)이었다. prompt 3,940 tok을 절반으로 줄이면 2초 내외라는 가정만 있다. 게이트에 넣지 않는다.
- P0 5번 ABSTAIN: `intent_guard.py:275 guard_intent`와 `plan_query_db.py:346~595 blocking_reasons` 배관이 이미 있다. 새 컴포넌트가 아니라 subtype 분류를 `blocking_reasons`에 구조화해 넣고 `generate_answer_node`(`nodes.py:1253`, `:1260`에서 읽음)가 그대로 답변에 쓰게 하는 일이다. Q31은 RDB 노드가 이미 "AAAA는 유효값 아님"을 `skipped_reason`으로 냈는데 generate가 버렸다. 데이터는 있고 전달만 끊긴 경우다.
- P0 6번 답변 길이: 예외 3회차(Q11·Q13·Q14)는 전부 목록형이다. `_build_answer_preview`(`nodes.py:1208`) 예산 20행을 요청 필드 수에 맞춰 줄이는 것만으로 대부분 해결될 가능성이 크다. 4초 상한은 timeout이 아니라 max_tokens 축소로 구현해야 한다(원인이 길이였다).

## 4. 이미 존재하는 것 (재사용 대상)

| 존재하는 것 | 위치 | 계획의 취급 |
|---|---|---|
| exact 일치 UNION 쿼리(색인 사용) | `graph_entity.py:133 _exact_candidates` | 계획이 "느리다"고 오판. 그대로 둔다 |
| `lru_cache` 기반 정규형 사전 패턴 | `graph_entity.py:96 _company_master` | 인덱스 구현의 관례로 따른다 |
| 판매가능 조건 결정론 처리 | `utils.py:51 apply_sale_policy`, `rdb_schema.py:204 DOMAIN_SALE_POLICY` | 빌더의 첫 규칙으로 재사용 |
| 속성 카탈로그·서브타입 조건·SQL 주의사항 | `rdb_schema.py:1241 ATTRIBUTE_CATALOG`, `:1356 SUBTYPE_CONDITION_MAP`, `:1263 DOMAIN_SQL_CAVEATS` | 빌더의 입력. 계획은 재사용을 명시했다 |
| intent 결정론 가드·차단 사유 배관 | `intent_guard.py:275 guard_intent`, `plan_query_db.py blocking_reasons` | ABSTAIN subtype을 여기에 실으면 된다. 새 pre-check 모듈 불필요 |
| mock 기반 unittest 관례 | `script/graph_db/test_client_failover.py FakeClient` | 새 테스트의 본보기 |
| E2E 계측 하네스·채점기 | `test/pipline-test/latency/` | 재측정에 그대로 사용 |
| sqlglot 30.17.0 | mirea 환경(requirements 미선언) | 채택 시 선언 추가 |

계획이 불필요하게 새로 만들려는 것은 없다. 다만 "SQL AST로 컴파일"(P0 2번)은 빌더(P0 3번)와 통합해야 한다(이슈 2).

## 5. NOT in scope (이번 스프린트에서 제외, 사유)

- Graph 전체 재설계, 온톨로지·VectorDB 외부 데이터 추가 적재: 원인 A·B 오답 0건이라 정답률에 기여하지 않는다(계획 §1·§3과 동일).
- LangGraph 노드 재배선: 독립 단계 순차 실행분 14.0%, 폴백 9.8%, 라우팅 오답 24.7%로 세 임계 미달(보고서 §5.2).
- 범용 노드 캐시(P2): hit-rate 근거 없음.
- `analyze_intent` 프롬프트 축소: 효과 추정에 근거 없음. 측정 후 결정.
- Vector `no_product_match` 정규화(P1): 오답 1차 원인이 아님. P0 뒤로.
- HCX constrained decoding(PICARD류): API에 붙일 수 없음.
- 새 의존성 도입 일반: sqlglot만 spike 뒤 결정.

## 6. 테스트 커버리지 다이어그램

```
CODE PATHS                                                   USER FLOWS / 회귀
[+] src/agent/graph_logic/graph_entity.py                    [+] Graph 라우트 문항 (Q10·Q22·Q23·Q26·Q27·Q29·Q35)
  ├── build_entity_index()  (신규)                             ├── [GAP] [→E2E] seed 61s → <1s, 결과 동일
  │   ├── [GAP] 정규형 키 / 세그먼트 키 생성                     └── [GAP]        Graph 원인 오답 0 유지
  │   ├── [GAP] 클래스 폐쇄(subClassOf*) 반영
  │   ├── [GAP] 빈 스토어·구축 실패 → SPARQL 폴백               [+] RDB 오답 4패턴 회귀
  │   └── [GAP] 언어태그(@ko) 라벨 정규화                        ├── [GAP] Q12·Q19·Q25·Q30 플래그 코드값
  ├── _normalized_literal_candidates() (수정)                   ├── [GAP] Q1·Q11·Q13 buyable_quantity 차단
  │   ├── [GAP] CRITICAL 회귀: 기존 SPARQL 결과와 동일          ├── [GAP] Q6·Q7·Q30 별칭 공백·미등록 테이블
  │   ├── [GAP] 세그먼트 일치 (우주항공/방산 ← 우주항공)          └── [GAP] Q26·Q27 발행사 필터 필수
  │   └── [GAP] ambiguous = 고유 entity 수 (행 수 아님)
  └── resolve_entity() 5단계 type-suffix                     [+] ABSTAIN 5문항
      └── [GAP] 재시도가 dict 조회로 대체됨                        └── [GAP] Q31~Q35 subtype·근거 전달
[+] src/agent/graph_logic/graph_orchestrator.py
  └── run(): 요청 내 seed 캐시 (text, role)                    [+] 목록형 답변 길이
      └── [GAP] 같은 요청 2회째 호출 시 SPARQL 0회                └── [GAP] Q11·Q13·Q14 LengthFinishReasonError 0
[+] src/agent/utils.py / nodes.py  SQL 빌더 (신규)
  ├── [GAP] 카탈로그 조건 → WHERE 컴파일                       [+] verify_intent 조건부 호출
  ├── [GAP] CRITICAL 미해소 조건 있으면 SQL 미생성·LLM 폴백        └── [GAP] [→EVAL] intent 수정 35/101 사례 fixture
  ├── [GAP] entities 조건 누락 시 거부
  └── [GAP] sort.limit 보존                                   LLM 프롬프트 변경 (ANSWER_SYSTEM_PROMPT, SQL_*):
[+] AST 가드 (LLM 폴백 경로)                                    [GAP] [→EVAL] 골든 Claim 채점기로 before/after
  ├── [GAP] 허용 테이블·컬럼 외 거부
  ├── [GAP] 금지 컬럼·공백 별칭 거부
  └── [GAP] 정상 SQL 오탐 0 (기존 정답 Q2·Q8·Q9 SQL 통과)

COVERAGE: 0/24 paths tested (0%)  |  GAPS: 24 (2 E2E, 2 eval, 2 CRITICAL 회귀)
기존 테스트 51개는 vector/graph client·vector node에 한정 — 이 계획의 경로는 하나도 덮지 않음
```

## 7. 실패 모드 (신규 코드 경로별)

| # | 경로 | 실제 실패 시나리오 | 테스트 | 에러 처리 | 사용자에게 | 판정 |
|---|---|---|---|---|---|---|
| F1 | 엔티티 인덱스 구축 | 스토어 경로 오류·부분 적재로 인덱스가 비거나 일부 클래스 누락 → 모든 조회 `not_found` | 없음 → 추가 | 없음 → SPARQL 폴백 필수 | "엔티티를 찾을 수 없음"으로 **조용히** 오답 | **critical gap** |
| F2 | 세그먼트 키 | 구분자가 `/` 외(`·`, `,`)인 라벨 → 기존과 다른 결과 | 회귀 fixture로 잡음 | 해당 없음 | 조용히 not_found | 회귀 테스트로 방어 |
| F3 | 요청 내 seed 캐시 | 같은 text·다른 role을 같은 키로 봄 | 추가 | 키에 role 포함 | 잘못된 seed로 조용한 오답 | 테스트로 방어 |
| F4 | SQL 빌더 | 카탈로그에 없는 조건을 조용히 버리고 빈 WHERE로 전 행 반환 | 없음 → 추가 | 없음 → 미해소 시 폴백 강제 | 관련 없는 수백 행이 답변에 | **critical gap** |
| F5 | AST 가드 | 정상 SQL을 오탐으로 차단 | 기존 정답 SQL 통과 테스트 | 차단 시 답변 불가 | 명시적 "확인할 수 없음" | 보이는 실패, 허용 |
| F6 | 답변 축약 fallback | 길이 초과 시 근거·기준일이 잘림 | Claim 채점기 | 없음 | 근거 없는 답(UNGROUNDED) 위험 | 채점기로 방어 |
| F7 | ABSTAIN pre-check | 정상 질의를 ABSTAIN으로 오분류 | Q1~Q30 회귀 | 없음 | 답할 수 있는데 거부 | E2E로 방어 |
| F8 | verify_intent 조건부 | guard가 못 잡는 intent 오류 통과 | 35/101 fixture | 없음 | 조용한 라우팅 오답 | fixture로 방어 |

critical gap 2건(F1·F4)은 구현 시 폴백을 반드시 넣고 테스트로 고정한다.

## 8. 병렬화 전략

| 단계 | 모듈 | 의존 |
|---|---|---|
| G. Graph 인덱스·seed 캐시 | `src/agent/graph_logic/` | — |
| R. SQL 빌더·가드 | `src/tools/rdb_schema.py`, `src/agent/utils.py`, `src/agent/nodes.py`(rdb 함수) | — |
| I. Intent·ABSTAIN·답변 길이 | `src/agent/intent_guard.py`, `plan_query_db.py`, `prompts.py`, `nodes.py`(analyze/verify/generate) | — |
| T. 단위 테스트 | `script/graph_db/`, `script/agent_test/` | 각 레인 안에서 함께 |
| M. 재측정 | `test/pipline-test/latency/` | G·R·I 병합 후 |

- Lane A `fix/graph-seed-latency`: G. **`nodes.py`를 건드리지 않는다**(graph_search_node는 그대로 run()을 호출). 독립.
- Lane B `fix/rdb-sql-generation`: R.
- Lane C `fix/intent-abstain-answer`(신설): I.
- 실행 순서: A ∥ B ∥ C 병렬 → **A 먼저 병합**(충돌 없음) → B 병합 → C를 B 위에 리베이스 후 병합 → M.
- **충돌 플래그**: B와 C가 모두 `nodes.py`를 건드린다. B는 `:117~:500` rdb 함수, C는 `:63~:116` intent 노드와 `:1208~` generate 노드로 영역이 갈리지만 같은 파일이다. 먼저 끝나는 쪽이 base에 올리고 다른 쪽이 리베이스한다.

## 9. 외부 의견 (Codex, 독립 리뷰)

Codex(`codex exec`, `model_reasoning_effort=high`, read-only, 별도 컨텍스트)에 계획 원문과 §3까지의 결정 요지를 주고 "리뷰가 놓친 것만" 찾게 했다. 원문 그대로 옮긴다.

```
CODEX SAYS (plan review — outside voice):
════════════════════════════════════════════════════════════
치명도 순이다.

1. P0 게이트가 구조적으로 통과 불가능하다. 17.6초 추정에는 A5 병렬화가 포함됐는데, A5는 P1이며 P0 재측정 뒤에 실행된다. A5 제외 추정치는 약 28.6초다. 작업 순서와 완료 조건이 모순이다.
2. 15초를 측정할 뿐 보장하지 않는다. 현재 timeout은 Plan 25초, Answer 90초, RDB 30초다(get_clova.py:21, utils.py:655). 요청 전체 deadline, 남은 시간 전파, 취소 정책이 없다. "생성 4초 상한"은 구현 위치조차 빠졌다.
3. 릴리스 품질 기준이 무의미하게 낮다. 정답률 14.4% 유지면 85.6%가 틀려도 출시된다. 같은 35문항으로 구현과 평가를 반복하므로 과적합도 보장된다. 기존 PASS 무회귀, Claim별 필수 통과, 패러프레이즈·미관측 세트가 필요하다.
4. Graph 인덱스 사양이 기존 의미를 보존하지 못한다. 현재 검색은 organizationName, productName, productShortName, themeName, documentTitle, 여러 코드 속성과 클래스 상속 폐쇄를 사용한다(graph_entity.py:62). 계획의 label/altLabel/상품·기업 코드만 인덱싱하면 후보 집합이 달라진다.
5. 인덱스 생명주기가 없다. "스토어 오픈 시" 훅이 대상 파일 어디에도 없고, 현재 캐시 삭제는 회사 CSV 하나만 비운다(graph_entity.py:185). 런타임 스캔은 지연을 시작 시점으로 옮길 뿐이며 멀티워커마다 중복된다. 고정 스냅샷이면 release-id 기반 오프라인 인덱스 산출물이 더 단순하다.
6. 요청 캐시의 전달 경로가 없다. orchestrator.run()은 relation마다 독립 호출된다(nodes.py:714). 전역 캐시는 요청 캐시가 아니다. 상태에 캐시를 싣거나 resolved seed를 전달해야 하며, 키에는 최소 text·role·class·match mode가 필요하다.
7. SQL 컴파일에 필요한 의미 정보가 카탈로그에 없다. AttributeSpec은 단위 변환·문자열 비교 방식·중복 grain을 구조화하지 않고 상당 부분을 note 문장에 둔다(rdb_schema.py:87). 연→일, 원↔달러, %, 날짜, 채권 복합키를 deterministic builder가 추론할 수 없다. typed transform을 먼저 정의해야 한다. SQLGlot도 현재 의존성에 없다.
8. 상품 완전일치 규칙을 현재 RDB 경로가 이미 위반한다. 상품명을 무조건 contains로 바꾼다(utils.py:132). "상품명 필터 보존"은 이 오매칭을 보존한다. 먼저 exact entity→상품코드로 해소하고 코드 조건을 생성해야 한다.
9. 교차 도메인 UNION은 과설계이면서 정보를 버린다. 현재 구현은 요청 필드를 강제로 폐기하고 상품코드만 남긴다(nodes.py:226). 동일 단위로 정규화한 뒤 도메인별 TOP N을 조회하고 Python에서 합쳐 TOP N을 고르면 충분하다.
10. ABSTAIN pre-check가 순환 논리다. taxonomy·명백한 미래 날짜·ontology domain 위반은 조회 전 판정 가능하지만, entity 부재와 기준일 당시 미출시는 마스터 조회 없이는 알 수 없다. 또한 blocking_reasons는 문자열 경고일 뿐이고 RDB skipped_reason은 빈 결과 답변에 전달되지 않는다. {subtype, evidence, source, as_of} 형태의 typed outcome이 필요하다.
11. 기준일 검증이 잘못됐다. 현재 모든 RDB 근거를 일괄 2026-08-24로 표기한다(nodes.py:1170). 실제 값은 08-21/22이고 펀드는 행별 날짜도 다르다(rdb_schema.py:138). as_of ≤ cutoff만 검사하면 거짓 08-24 표기가 그대로 통과한다.
12. 429 제외와 warm 직렬 측정은 운영 성능을 숨긴다. 실패 요청을 분모에서 빼면 실패율이 오를수록 p95가 좋아질 수 있다. 7초 간격 단일 실행은 실제 동시 요청·토큰 한도를 검증하지 않는다. latency, availability, throughput을 별도 게이트로 둬야 한다.
════════════════════════════════════════════════════════════
```

### 9.1 검증 결과

Codex 주장을 소스에서 하나씩 확인했다. 확인하지 않은 것은 채택하지 않았다.

| # | 판정 | 확인 내용 |
|---|---|---|
| 1 | **신규, 수치 정정** | `roadmap.py`를 A5 제외로 재계산: p95 **20.2초(추정)**, 15초 초과 20회차, 잔여 Q11·Q13·Q16·Q18·Q20·Q23·Q24·Q26·Q27·Q28. Codex의 28.6초는 틀렸지만 "P1 항목 없이는 P0 게이트를 못 넘는다"는 결론은 맞다 |
| 2 | **신규, 사실** | `get_clova.py:21-22` timeout 25/90, `utils.py:655` RDB 30. 요청 전체 deadline·잔여 예산 전파 코드 없음 |
| 3 | 일치·보강 | 이슈 4와 같은 결론. "기존 PASS 15회차 무회귀"와 Claim 단위 통과 조건은 게이트에 추가할 가치가 있다 |
| 4 | 일치 | 이슈 1의 설계는 `_class_spec`의 name/code 속성을 모두 포함한다. 계획 문면의 "label·altLabel·코드"만으로는 부족하다는 지적은 맞다 |
| 5 | 일치·대안 | `clear_entity_cache`(`:185`)가 company CSV만 비우는 것 확인. 오프라인 산출물 대안은 D3에서 **미채택**(런타임 구축 유지) |
| 6 | 일치·보강 | T2의 캐시 키를 `(text, role, class)`로 하고 state 경로로 전달한다는 구체화 |
| 7 | **신규, 사실** | `rdb_schema.py:87 AttributeSpec` 필드는 column·value_type·note·value_order. 단위·변환 필드 없음. D3에서 선행 작업으로 **미채택**. T4 구현 시 단위 변환은 빌더 밖(LLM 폴백)으로 남는 잔여 위험 |
| 8 | **신규, 사실, 규칙 위반** | `utils.py:131-134`가 `product_name_entities`를 무조건 `contains`로 변환. AGENTS.md "완전일치 우선, 유사명 대체 금지" 위반 |
| 9 | 의견 | `nodes.py:226` 확인. 설계 대안으로 P2 후보에 기록, 채택 안 함 |
| 10 | 일치·보강 | §3의 Q31 관찰과 같다. typed outcome 형태는 T8에 반영 |
| 11 | **신규, 사실, 규칙 위반** | `nodes.py:1167-1170`이 모든 RDB 근거에 `DATA_SNAPSHOT_DATE`(08-24)를 일괄 표기. AGENTS.md 함정 표 "실질 기준일 불일치" 항목 그대로 |
| 12 | **신규, 부분 동의** | 429 분모 제외는 루브릭 §13 규정이지만 가용성 지표를 따로 두지 않으면 왜곡된다는 지적은 맞다. 동시 요청 부하 측정은 이번 범위 밖 |

### 9.2 CROSS-MODEL TENSION

- **A5 순서**: 리뷰는 로드맵 수치를 그대로 인용했다. Codex는 P1 항목이 P0 게이트 수치에 들어간 모순을 짚었다. 재계산으로 Codex가 맞음을 확인했고 수치만 정정했다.
- **인덱스 생명주기**: 리뷰는 런타임 1회 구축(+SPARQL 폴백). Codex는 release-id 오프라인 산출물. 스냅샷이 고정(2026-08-24)이라 Codex 안이 더 단순한 것은 사실이나, 사용자가 런타임 구축을 유지하기로 했다.
- **빌더 선행 조건**: 리뷰는 카탈로그 값으로 충분하다고 봤다. Codex는 단위·변환 타입이 없어 빌더가 절반만 된다고 봤다. 사실이다. 사용자가 선행 작업 없이 진행하기로 했으므로, 단위가 걸린 조건(AUM 1천억 달러 등)은 빌더가 폴백으로 넘기는 것으로 T4 규칙에 명시한다.
- **429 처리**: 루브릭은 분모 제외를 요구하고 Codex는 왜곡을 지적한다. 둘 다 맞다. 분모 제외는 유지하고 429 발생률을 별도 게이트로 둔다.

### 9.3 D3 결정 (사용자)

- **채택 A**: A5를 P0로 올리거나 게이트를 단계화. 429 발생률을 availability 게이트로 분리. 기존 PASS 15회차 무회귀 조건 추가.
- **채택 B**: 상품명 contains → entity exact 해소 후 상품코드 조건(T12). RDB 근거 기준일을 테이블별 실질 기준일로(T13).
- **P1로 이관 C**: 요청 전체 15초 예산 전파.
- **미채택 D**: AttributeSpec typed transform 선행, 오프라인 인덱스 산출물. 잔여 위험은 9.1의 #5·#7에 기록.

## 10. Implementation Tasks

각 항목은 위 발견에서 직접 나왔다. P1은 배포 차단, P2는 같은 브랜치에서, P3는 후속.

- [ ] **T1 (P1, human: ~2일 / CC: ~2시간)** — graph_logic — 정규형·세그먼트 키 엔티티 인덱스를 스토어 오픈 시 1회 구축하고 `_normalized_literal_candidates`가 이를 조회하게 한다. 구축 실패 시 SPARQL 폴백.
  - Surfaced by: 이슈 1, §2.1 실측(normalized 2.6~6.1s), F1
  - Files: `src/agent/graph_logic/graph_entity.py`
  - Verify: `python script/graph_db/test_entity_index.py` (T3), Q10 seed 1회 < 1s
- [ ] **T2 (P2, human: ~반일 / CC: ~30분)** — graph_logic — `graph_orchestrator.run`에 요청 단위 `(text, role)` seed 캐시.
  - Surfaced by: §2.3 정정(terminal 관계가 여럿일 때만 재조회), F3
  - Files: `src/agent/graph_logic/graph_orchestrator.py`
  - Verify: 같은 요청 2회째 seed에서 SPARQL 0회
- [ ] **T3 (P1, human: ~1일 / CC: ~1시간)** — tests — `script/graph_db/test_entity_index.py`: 회귀 fixture(Q10·Q23·Q26·Q27 seed 텍스트 + 클래스 대표) 결과 동일성, 세그먼트 일치, 고유 entity 수 계약, 빈 인덱스 폴백, type-suffix 경로.
  - Surfaced by: 이슈 3 철칙, F1·F2
  - Files: `script/graph_db/test_entity_index.py`
  - Verify: 실 스토어 없이 통과
- [ ] **T4 (P1, human: ~3일 / CC: ~4시간)** — rdb — 결정론 SQL 빌더: 카탈로그로 해소되는 조건을 WHERE로 컴파일, `apply_sale_policy` 뒤에 삽입, 미해소 조건이 있으면 SQL 미생성·LLM 폴백, `frame.entities`를 필수 조건으로.
  - Surfaced by: 이슈 2, F4
  - Files: `src/agent/utils.py`, `src/agent/nodes.py`(`_execute_target_step`, `_execute_merged_target_group`)
  - Verify: T6
- [ ] **T5 (P2, human: ~1일 / CC: ~1시간)** — rdb — LLM 폴백 경로 전용 SQL 가드(허용 테이블·컬럼, 금지 컬럼, 공백 별칭). sqlglot 채택은 spike 반일 후 결정, 채택 시 `requirements.txt` 선언.
  - Surfaced by: 이슈 2
  - Files: `src/agent/nodes.py`(`_run_sql_with_retry` 앞), `requirements.txt`
  - Verify: 기존 정답 Q2·Q8·Q9 SQL 통과, 4패턴 SQL 차단
- [ ] **T6 (P1, human: ~1일 / CC: ~1시간)** — tests — `script/agent_test/test_sql_builder.py`: Q12·Q19 코드값, Q1·Q11·Q13 금지 컬럼, Q6·Q7 별칭·테이블, Q26·Q27 발행사, Q10 limit, 미해소 조건 폴백.
  - Surfaced by: 이슈 3, F4
  - Files: `script/agent_test/test_sql_builder.py`
  - Verify: LLM·DB 없이 통과
- [ ] **T7 (P1, human: ~반일 / CC: ~20분)** — process — 세 번째 브랜치 `fix/intent-abstain-answer` 생성, 병합 순서 Graph → RDB → Intent 고정, Lane A는 `nodes.py` 불변 규칙.
  - Surfaced by: D2, §8
  - Files: 브랜치·PR 설명
  - Verify: `git diff --name-only` 로 Lane A에 nodes.py 없음
- [ ] **T8 (P2, human: ~1일 / CC: ~1시간)** — intent — ABSTAIN subtype을 `guard_intent`에서 분류해 `blocking_reasons`에 구조화하고 `generate_answer_node`가 답변에 그대로 쓰게 한다. RDB `skipped_reason`(Q31)도 같은 경로로.
  - Surfaced by: §3 "질문으로 올리지 않은 발견", F7
  - Files: `src/agent/intent_guard.py`, `src/agent/plan_query_db.py`, `src/agent/nodes.py`(generate)
  - Verify: Q31~Q35 subtype 5종 반환
- [ ] **T9 (P2, human: ~반일 / CC: ~30분)** — answer — `_build_answer_preview` 예산을 요청 필드·행 수에 맞춰 축소, 길이 초과 시 max_tokens 축소 fallback.
  - Surfaced by: §3, F6
  - Files: `src/agent/nodes.py`, `src/agent/prompts.py`
  - Verify: Q11·Q13·Q14 예외 0, Claim 채점 유지
- [ ] **T10 (P2, human: ~반일 / CC: ~30분)** — measurement — verify_intent 기여도 사전 분석(intent 변경 회차 vs 미변경 회차 정답률, 기존 trace), 이후 intent 단계만 A/B 미니셋, RDB 문항 25개 draft A/B 미니셋.
  - Surfaced by: 이슈 4
  - Files: `test/pipline-test/latency/analyze.py`(집계 추가), 미니셋 러너
  - Verify: A/B 합계 1시간 이내
- [ ] **T11 (P1, human: ~2시간 / CC: ~2시간 대기)** — measurement — 병합 후 35문항×warm 3회 E2E 1회. 원인별 게이트(p95 ≤15s, C 52→≤26, Critical 15→≤7, A·B 0, Q31~35 subtype).
  - Surfaced by: 이슈 4
  - Files: `test/pipline-test/latency/`
  - Verify: `analysis_summary.json` 게이트 값

- [ ] **T12 (P1, human: ~1일 / CC: ~1시간)** — rdb — 상품명 조건을 `contains`가 아니라 entity exact 해소 → 상품코드 조건으로 생성. 완전일치 실패 시 유사명 대체 없이 "상품 부재" 사유로 넘긴다.
  - Surfaced by: §9 Codex #8 검증, AGENTS.md "상품명은 완전일치 우선" (`utils.py:131-134`)
  - Files: `src/agent/utils.py`, T4 빌더
  - Verify: Q4 "KODEX 200"이 부분일치 14건이 아니라 1건으로 해소, 기존 정답 Q2·Q8·Q9 무회귀
- [ ] **T13 (P1, human: ~반일 / CC: ~20분)** — evidence — RDB 근거 기준일을 `DATA_SNAPSHOT_DATE` 일괄이 아니라 도메인 테이블별 실질 기준일(채권·ETF 08-21 등)로 표기. `DOMAIN_TABLE_INFO`에 기준일 필드를 두고 `_build_retrieved_context`가 읽는다.
  - Surfaced by: §9 Codex #11 검증, AGENTS.md 함정 "실질 기준일 불일치" (`nodes.py:1167-1170`)
  - Files: `src/tools/rdb_schema.py`, `src/agent/nodes.py`
  - Verify: Q2 답변 근거에 채권 실질 기준일이 표기됨
- [ ] **T14 (P1, human: ~1시간 / CC: ~10분)** — plan — 계획서 §7·§8 정정: A5를 P0로 올리거나 P0 게이트를 "A5 전 20초 / A5 후 15초" 2단계로. 429 발생률을 availability 게이트로 분리. 기존 PASS 15회차 무회귀를 완료 조건에 추가.
  - Surfaced by: §9 Codex #1·#3·#12 검증, A5 제외 재계산 p95 20.2s(추정)
  - Files: `test/pipline-test/2026-09-04_pipeline_action_items_meeting_report.md`
  - Verify: §8 완료 조건에 세 항목이 들어 있음

_Performance 섹션에서 별도 신규 코드 태스크 없음(성능 개선은 T1·T4에 포함). 요청 전체 15초 예산 전파(Codex #2)는 P1로 이관, 태스크 미생성._

## 11. 아키텍처 다이어그램 (코드 주석에 넣을 것)

`graph_entity.py` 파일 상단 또는 `resolve_entity` docstring:

```
resolve_entity(text, class)
  1 exact ──────────── SPARQL UNION 리터럴 일치 (색인, ~10ms)
  2 normalized_exact ─ Company 계열만, _company_master dict
  3 normalized/segment ─ [변경 전] SPARQL 전체 스캔 + FILTER (~6s)
                         [변경 후] _entity_index[(class, key)] dict 조회 (~0ms)
                         키 = normalize(text) 와 "/" 세그먼트 각각
  4 partial ─────────── allow_partial 때만
  5 type-suffix 재시도 ─ 말미 토큰 제거 후 1~4 반복 (변경 후엔 dict 2회)
  ambiguous 판정 = 고유 entity URI 수 (행 수 아님)
  인덱스 구축 실패 → 3단계는 기존 SPARQL로 폴백
```

## 12. 구현 진행 (2026-09-05, Lane A `fix/graph-seed-latency`)

T1·T3 완료. `nodes.py`는 건드리지 않았다.

- `src/agent/graph_logic/graph_entity.py`: 3단계 `_normalized_literal_candidates`가 프로세스 내 인덱스(`_entity_index`, class → 세그먼트 키 → entity URI)로 후보 entity를 좁힌 뒤, 원래 SPARQL에 `VALUES ?entity`만 얹어 실행한다. FILTER의 행 단위 적용·DISTINCT·행 순서(canonical_name)를 Oxigraph가 그대로 결정하므로 결과가 스캔 판과 같다. 인덱스 미스는 SPARQL을 호출하지 않는다. 구축 실패 시 스캔 판으로 폴백하고 실패 사유를 기록한다(F1 해소). 구축 15.6s는 `artifacts/graph_entity_index.pkl`(14MB, 스토어 경로·mtime 서명)로 남겨 다음 프로세스는 0.5s에 읽는다.
- `src/infrastructure/graph_db/client.py`, `graph_engine.py`: `max_rows` 인자 추가. 기본 10,000행 상한은 유지하고 인덱스 구축만 `None`으로 전체를 읽는다.
- `script/graph_db/test_entity_index.py`: 가짜 스토어 unittest 16개(세그먼트 연속 구간, 클래스 폐쇄, 고유 entity 모호성, 행 단위 FILTER, 폴백, type-suffix, 캐시 무효화). `RUN_STORE_REGRESSION=1`이면 실 스토어에서 fixture 13건(Q10·Q23·Q26·Q27 seed 텍스트 포함)을 스캔 판과 완전 비교한다. 첫 실행에서 canonical_name 차이 2건을 잡아 설계를 VALUES 방식으로 바꿨고, 재실행은 전부 일치했다.

| 측정 | 개선 전 (warm p50) | 개선 후 (1회) |
|---|---:|---:|
| seed 1회 (Q10, role=product, not_found) | 61,000ms | 84ms |
| Q10 graph 노드 | 107.6s | 0.9s |
| Q10 E2E | 140.8s | 29.7s |
| Q23 graph 노드 / E2E | 91.7s / 146.0s | 0.2s / 20.0s |
| Q26 graph 노드 / E2E | 108.2s / 176.7s | 0.2s / 72.0s |
| Q27 graph 노드 | 54.4s | 0.1s (E2E는 SQL fix 429로 미측정) |

남은 E2E 시간은 전부 RDB(LLM SQL 체인)와 Query Frame이다. Lane B·C 대상이다. T2(요청 내 seed 캐시)는 seed가 ms 단위가 되어 필요성이 사라졌으므로 보류한다.

실행한 검증: `python script/graph_db/test_entity_index.py`(16 pass, 1 skip), `WSLENV=RUN_STORE_REGRESSION RUN_STORE_REGRESSION=1 python script/graph_db/test_entity_index.py RealStoreRegressionTest`(pass, 96s), `python script/graph_db/test_client_failover.py`(11 pass), `run_latency.py --rounds 1 --ids Q10,Q23,Q26,Q27`(trace `latency/traces_after_T1_graph.jsonl`).

## 13. 완료 요약

- Step 0 범위: 7개 유지 + 겨냥점·주인·순서 확정 (D2 = B)
- Architecture: 1건 (이슈 1, A 채택)
- Code Quality: 1건 (이슈 2, A 채택)
- Tests: 다이어그램 작성, 24 gaps (CRITICAL 회귀 2)
- Performance/Process: 1건 (이슈 4, A 채택)
- NOT in scope: 작성
- What already exists: 작성
- Failure modes: critical gap 2 (F1 인덱스 빈 폴백, F4 빌더 빈 WHERE)
- Outside voice: Codex 실행. 12건 중 5건 일치, 7건 신규(전부 소스 검증). 채택 A·B(4건 → T12~T14), C는 P1 이관, D는 미채택
- Parallelization: 3 lanes 병렬, 병합 순서 A→B→C, nodes.py 충돌 플래그 1
- Lake Score: 4/6 결정이 완전한 선택지 (D1·D2·이슈1~4는 전부 완전안, D3에서 C·D 미채택)
- TODOS.md: 저장소에 없음. 후속 후보는 §5 NOT in scope와 §9.3의 C·D 항목이며 사용자 판단으로 파일을 만들지 않았다

### 미해결 결정

없음. D3에서 C(15초 예산 전파)는 P1 이관, D(typed transform 선행·오프라인 인덱스)는 미채택으로 결정됐다. 미채택의 잔여 위험은 §9.1 #5·#7에 적었다.
