# 파이프라인 개선 스프린트 의사결정 리포트

작성일 2026-09-04 · 데이터 기준일 2026-08-24 · 기준 실험: 2026-09-03 latency/quality 측정

## 1. 회의 결론

- 현재 최대 속도 병목은 GraphDB 엔티티 해소(`graph_exec` p95 117.6초), 최대 품질 병목은 RDB SQL 생성(오답 89회차 중 52회차, 58.4%)이다.
- 이번 스프린트는 **Graph exact-label 인덱스·seed 재사용**과 **결정론적 SQL 매핑/검증**을 P0로 병행하고, 미검증 LLM 제거안은 A/B 통과 후에만 적용한다.
- 기존 6개 조치의 합산 추정치도 E2E p95 17.6초이므로, `verify_intent`/SQL 호출 축소와 `analyze_intent` 프롬프트 축소를 같은 재측정 게이트에서 검증해야 15초 달성 여부를 확정할 수 있다.
- 이번 스프린트에는 Graph 전체 재설계, VectorDB·Ontology 외부 데이터 추가 적재, 신규 DB/Agent/MCP/LSP 도입을 넣지 않는다.

## 2. LangGraph Pipeline 판단

**판정: LangGraph 재설계는 하지 않고 노드 내부 병목을 수정한다.** 독립 단계의 순차 실행 가능분은 p95 회차의 14.0%, 재시도·폴백은 E2E 합계의 9.8%이며, `plan_query`는 약 1ms이고 검색 엔진은 이미 `dispatch()`에서 준비된 엔진만 병렬 웨이브로 호출한다.

| 점검 항목 | 판정 및 측정 근거 | 조치 위치 |
|---|---|---|
| 불필요한 sequential node | `analyze_intent → verify_intent` 2회 LLM이 p95 19.6초. 단, `verify_intent`가 35/101회차를 수정했으므로 즉시 삭제는 위험 | `src/agent/graph.py::build_graph`, `src/agent/nodes.py::analyze_intent_node`, `verify_intent_node` |
| 모든 DB 일괄 호출 | 아님. `dispatch()`가 plan의 engine만 호출한다. Golden Set에서는 질의 요구 때문에 RDB 35/35, Graph 10/35, Vector 19/35가 실행됨 | `src/agent/graph.py::dispatch` 유지 |
| 불필요한 LLM router | `plan_query`의 LLM 폴백은 0회이고 규칙 기반 실행은 약 1ms라 병목 아님 | `src/agent/plan_query_db.py::plan_query_node` 유지 |
| DB query 생성 LLM | RDB에서 concept 2.0초 + draft 5.5초 + write 2.9초 + fix 3.0초가 누적되고, LLM 호출 전체가 E2E의 68.4% | `src/agent/utils.py`, `src/agent/nodes.py::_draft_query_description`, `_write_sql`, `_run_sql_with_retry` |
| 중복 retrieval | `resolve_frame_seed()`가 관계마다 동일 seed를 다시 해소하고 클래스별 5~9개 SPARQL을 순차 실행 | `src/agent/graph_logic/graph_entity.py`, `graph_orchestrator.py::run` |
| retry | SQL fix LLM 49회, 161.3초 누적. Graph plan/Oxigraph transport retry는 0회 | SQL을 실행 전 결정론적으로 검증해 fix 경로를 예외 처리로 축소 |
| serialization/state overhead | `merge` 0ms, plan/route 1ms 수준으로 병목 근거 없음 | 변경하지 않음 |
| 병렬 실행 후보 | 다중 RDB 도메인 5개 질의에서만 의미 있음. 단독 적용 예상 p95 회차 단축 11.0초, 평균 1.3초 | P1에서 `rdb_search_node`의 독립 `solo_steps` 병렬화 |
| cache 후보 | 데이터 기준일이 고정된 label/code→URI와 요청 내 동일 seed가 안전한 대상. 전체 LLM/검색 노드 캐시는 hit-rate 근거가 없음 | P0는 entity index/request cache만 적용, 범용 node cache는 P2 검토 |

## 3. External Data 필요성 판단

| 영역 | Data Gap | Retrieval/Logic Gap | 외부 데이터 필요 |
|---|---|---|---|
| Ontology / GraphDB | 편입·자회사·테마 이력 등 `external_required` Claim은 실제 부재(Q22·Q23·Q24·Q28) | exact/normalized label 해소가 클래스별 SPARQL scan을 반복하고 관계마다 seed를 재조회. Graph 원인 오답은 0/89 | **NO — 이번 스프린트** |
| VectorDB | `no_document` 5건(Q10·Q24 포함)은 문서 부재 | `no_product_match` 15건(Q6·Q7·Q29)은 `product_master` 완전일치/엔티티 해소 문제. Vector 원인 오답은 0/89 | **NO — 이번 스프린트** |

> **추가 데이터 구축보다 현재 로직 개선이 우선**이다. 부재 데이터는 향후 답변 범위 확장에는 필요하지만, 이번 측정의 1차 오답 원인이 아니므로 P0가 아니다.

## 4. Action Items

### P0 — 이번 스프린트에서 반드시 수행

| Priority | 문제 | Action Item | 대상 영역/파일 | 담당 영역 | 기대 효과 | 완료 기준 |
|---|---|---|---|---|---|---|
| P0 | Graph seed 해소가 관계당 p50 15.1초, p95 60.4초이며 SPARQL 339회 중 145회가 1초 초과 | 스토어 오픈 시 `rdfs:label`·`skos:altLabel`·상품/기업 코드의 exact/normalized key→URI 인덱스를 1회 구축하고, 동일 요청의 seed 결과를 관계 간 공유한다. 부분일치 fallback은 기존 ambiguity 규칙을 유지한다. | `src/agent/graph_logic/graph_entity.py::{_exact_candidates,_normalized_literal_candidates,resolve_entity,resolve_frame_seed,clear_entity_cache}`, `src/agent/graph_logic/graph_orchestrator.py::run` | Graph/RDF | A1 추정상 E2E p95 144.0→70.3초; 동일 seed 재조회 추가 제거 | Q10·Q23·Q26·Q27의 resolved/ambiguous/not_found 결과가 기준 실행과 동일하고, seed/SPARQL 호출 수와 E2E가 새 trace에 기록됨 |
| P0 | 코드값·별칭·금지 컬럼·필터 누락이 RDB 오답 52/89와 fix LLM 49회를 유발 | 코드값/별칭/판매정의/등급순서를 catalog에서 SQL AST로 결정론적으로 컴파일한다. 허용 테이블·컬럼만 통과시키고 `buyable_quantity` 조건, 공백 alias, 미등록 join을 실행 전에 차단한다. 상품명·발행사 조건과 전역 `sort.limit` 보존을 필수 검증한다. | `src/tools/rdb_schema.py::{ATTRIBUTE_CATALOG,DOMAIN_SALE_POLICY}`, `src/agent/utils.py::{apply_sale_policy,resolve_concepts_for_domain,build_resolved_schema}`, `src/agent/nodes.py::{_execute_target_step,_execute_merged_target_group,_run_sql_with_retry}` | RDB/Query Engine | FILTER_ERROR·STALE_DEFINITION·SyntaxError·필터 누락 감소, SQL fix 재시도 제거 | Q12·Q19 코드값, Q1·Q11·Q13 금지 컬럼, Q6·Q7·Q30 구문/테이블, Q26·Q27 발행사, Q10 limit 오류가 각 warm 3회에서 재발하지 않음 |
| P0 | RDB target 조회가 concept fallback→draft→write→fix의 3~4회 LLM 체인 | 카탈로그로 해소된 조건은 deterministic query builder로 실행하고, 미해결 표현만 HCX 단일 SQL 호출에 넘긴다. `draft`와 정상 경로의 `fix`를 제거하는 A/B를 수행한 뒤 품질 비저하가 확인될 때만 전환한다. | `src/agent/nodes.py::{_draft_query_description,_write_sql,_execute_target_step,_execute_entity_lookup_step}`, `src/agent/utils.py::_resolve_unknown_concepts_via_llm` | RDB/Agent | A3+A4 추정 p95 회차 25.2초 단축, 호출 수·429 위험 감소 | 카탈로그로 해소 가능한 Golden Claim에서 draft/concept/fix LLM 호출이 0이고, 전체 정답률이 기준 14.4%보다 낮아지지 않으며 Critical Fail이 증가하지 않음 |
| P0 | Query Frame p95 19.6초로 하위 목표 5초 초과; `verify_intent` 삭제의 품질 영향 미측정 | `analyze_intent` 프롬프트/스키마를 축소하고, `verify_intent`를 항상 호출하는 안과 deterministic guard 실패 시에만 호출하는 안을 A/B한다. 35/101 수정 사례를 오류 유형별로 회귀 테스트에 고정한다. | `src/agent/prompts.py`, `src/agent/nodes.py::{analyze_intent_node,verify_intent_node}`, `src/agent/intent_guard.py::guard_intent`, `src/agent/graph.py::build_graph` | Intent/Orchestration | A2 추정 p95 회차 10.9초 단축 및 prompt 축소로 잔여 2.6초 격차 대응 | 채택안의 Golden Set 정답률이 14.4%보다 낮아지지 않고 Critical Fail이 증가하지 않으며, Query Frame·E2E p50/p95가 새 trace에 기록됨 |
| P0 | ABSTAIN 문항이 정확한 사유를 전달하지 못해 15회 중 13회 실패 | taxonomy/domain/cutoff/미래값/엔티티 부재를 deterministic pre-check로 분류하고, 검색을 생략한 경우에도 subtype과 근거를 `blocking_reasons` 및 최종 답변에 전달한다. | `src/agent/intent_guard.py`, `src/agent/plan_query_db.py::plan_query_node`, `src/agent/nodes.py::{_build_retrieved_context,generate_answer_node}` | Policy/Answer | D 원인 22회차와 MISSING_EVIDENCE 13건 감소; 유효하지 않은 질의의 불필요 DB/LLM 호출 제거 | Q31~Q35가 각 warm 3회에서 기대 subtype(`ABSTAIN_INVALID_TAXONOMY`, `ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF`, `ABSTAIN_ENTITY_NOT_FOUND`, `ABSTAIN_FUTURE_DATA`, `ABSTAIN_DOMAIN_MISMATCH`)과 근거를 반환하고 허위 값이 없음 |
| P0 | 목록형 Q11·Q13·Q14가 2,048 token 초과로 3회 예외 | answer preview와 출력 스키마를 요청 필드·행 제한 중심으로 축소하고 생성 4초 상한/길이 초과 시 근거 보존 축약 fallback을 적용한다. 답변 생성 모델은 HCX를 유지한다. | `src/agent/nodes.py::{_build_answer_preview,generate_answer_node}`, `src/agent/prompts.py::ANSWER_SYSTEM_PROMPT` | Answer Generation | A6 추정 p95 회차 5.1초 단축, LengthFinishReasonError 제거 | Q11·Q13·Q14 warm 3회에서 답변 예외 0건이고 필수 Claim·기준일·출처가 유지됨 |
| P0 | 로드맵 추정만으로는 15초 달성을 확정할 수 없음 | 변경별 micro benchmark 후 35문항×warm 3회 E2E를 재실행하고, 기존 evaluator로 Claim·원인코드·429를 동일 방식 집계한다. | `test/pipline-test/latency/{run_latency.py,analyze.py,roadmap.py,build_golden_eval.py}` | QA/Performance | 추정치를 실측으로 교체하고 릴리스 여부 결정 | warm E2E p95 ≤15초, 15초 초과 회차 감소, 정답률 14.4% 이상, C/D/E/F 원인 오답 및 Critical Fail이 기준보다 감소 |

### P1 — P0 완료 후 수행

| Priority | 문제 | Action Item | 대상 영역/파일 | 담당 영역 | 기대 효과 | 완료 기준 |
|---|---|---|---|---|---|---|
| P1 | 다중 도메인 RDB `solo_steps`가 같은 노드 안에서 순차 실행 | 의존성이 없는 RDB 도메인 단계만 bounded parallel execution으로 전환하고 CLOVA 호출이 남은 경로에는 rate-limit guard를 적용한다. | `src/agent/nodes.py::rdb_search_node`, `_execute_target_step` | RDB/Orchestration | A5 추정 p95 회차 11.0초, 평균 1.3초 단축 | Q21·Q23·Q26·Q27·Q30 결과가 직렬 실행과 동일하고 단계·E2E 시간이 새 trace에서 감소 |
| P1 | Vector `no_product_match` 15건은 데이터 부재가 아니라 상품 식별 실패 | Graph/RDB와 같은 조직명·ticker·상품명 정규화 규칙을 `product_master` 해소에 적용하되 완전일치 우선·유사명 대체 금지를 유지한다. | `src/infrastructure/vector_db/client.py::resolve_product_ids`, `src/tools/vector_search.py::resolve_product_ids`, `src/agent/nodes.py::_vector_scope` | Vector/Entity Resolution | Q6·Q7·Q29의 검색 누락 감소 | 해당 3문항에서 의도한 product_id가 재현 가능하게 해소되고, 동명이의/유사명 오매칭 0건 |
| P1 | Graph·Vector의 부재 상태가 생성 단계에서 일반적인 “답변 불가”로 평탄화됨 | `external_required`·`no_document`·`no_hit`·`no_product_match`를 루브릭 failure/gap code로 보존해 partial answer에 노출한다. | `src/agent/nodes.py::{_describe_vector_status,_build_retrieved_context,generate_answer_node}` | Evidence/Answer | GENERATION_OMISSION 54건과 과잉 추론 7건 감소 | Q22·Q23·Q24·Q28·Q29에서 가능한 Claim은 답하고, 불가능 Claim은 정확한 gap code와 필요한 데이터 종류를 표시 |

### P2 — 후속 구조 개선

| Priority | 문제 | Action Item | 대상 영역/파일 | 담당 영역 | 기대 효과 | 완료 기준 |
|---|---|---|---|---|---|---|
| P2 | 반복 질의의 cache hit-rate와 stale 위험이 미측정 | 데이터 기준일·schema version·normalized query를 키로 하는 Graph/Vector read cache를 별도 실험하고, hit-rate와 무효화 정책이 확인된 범위에만 적용한다. | `src/agent/graph.py::build_graph`, Graph/Vector client | Platform | 반복 질의 지연·비용 감소 가능 | cache on/off 결과·정답 동일성, hit-rate, p50/p95, 기준일 변경 시 무효화가 측정됨 |
| P2 | 편입·자회사·테마 이력·문서의 실제 Data Gap은 남아 있음 | P0 이후 잔여 실패를 Claim 단위로 재집계하고, 오답 감소 예상치가 확인된 데이터셋만 `as_of ≤ 2026-08-24`로 수집한다. 주최측 충돌은 evidence에 기록한다. | `data/enriched/`, `ontology/`, `src/kb/build_graph_instances.py`, `src/kb/build_vectors.py` | Data/Ontology | 현재 답변 범위를 넘어서는 external-required Claim 확장 | 소스·실질 기준일·coverage·provenance가 검증되고 `validate_ontology.py`·`validate_external.py` 통과 |

## 5. 웹 조사 적용 판단

- LangGraph 공식 문서는 독립 노드 fan-out 병렬 실행과 node cache를 지원한다. 현재 `dispatch()`가 이미 엔진 병렬화를 사용하고 실측 병렬화 여지가 14.0%이므로, 이 기능은 P1의 다중 RDB 단계와 P2 cache에만 제한 적용한다. [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- PICARD는 잘못된 SQL 토큰을 파싱 단계에서 거부하는 constrained decoding의 효과를 보였다. HCX API에 동일 decoder를 붙이는 작업은 범위가 크므로 도입하지 않고, 같은 원칙을 실행 전 SQL AST allowlist로 구현한다. [PICARD, EMNLP 2021](https://aclanthology.org/2021.emnlp-main.779/)
- SQLGlot은 PostgreSQL SQL을 AST로 파싱·순회·생성할 수 있어 허용 테이블/컬럼, alias, 금지 조건을 결정론적으로 검사하는 후보이다. 라이브러리 채택 여부는 기존 의존성 추가 비용과 소규모 spike 결과로 결정한다. [SQLGlot 공식 문서](https://sqlglot.com/)
- CHESS는 schema/value retrieval과 schema selection으로 토큰을 줄일 수 있음을 보였지만 다중 에이전트 전체 도입은 현재 15초 목표와 맞지 않는다. catalog/value mapping만 참고하고 추가 Agent는 도입하지 않는다. [CHESS, arXiv 2024](https://arxiv.org/abs/2405.16755)
- Adaptive-RAG는 질의 복잡도에 따라 no/single/multi retrieval을 선택하는 접근을 검증했다. 현재 learned router를 추가하면 새 LLM/분류 비용이 생기므로, P0에서는 명확한 ABSTAIN과 route guard만 결정론적으로 처리한다. [Adaptive-RAG, NAACL 2024](https://aclanthology.org/2024.naacl-long.389/)

## 6. 회의에서 결정할 사항

1. **RDB의 카탈로그 해소 가능 경로는 LLM SQL 생성을 제거하고 deterministic query builder로 전환할 것인가?**
2. **`verify_intent`는 즉시 삭제하지 않고, conditional 호출 A/B가 품질 비열화를 통과한 경우에만 전환할 것인가?**
3. **Graph exact-label 인덱스와 요청 내 seed 공유를 이번 스프린트의 첫 구현 항목으로 확정할 것인가?**
4. **Ontology/VectorDB 외부 데이터 적재와 신규 DB/Agent/MCP/LSP 도입을 이번 스프린트에서 제외할 것인가?**
5. **릴리스 게이트를 warm E2E p95 ≤15초 + 기준 정답률 14.4% 이상 + Critical Fail 감소로 확정할 것인가?**

## 7. 작업 순서

`기준 trace 고정 → Graph exact-label 인덱스·seed 공유 → deterministic SQL builder·AST guard → Query Frame A/B → ABSTAIN/답변 길이 보정 → 단위·회귀 테스트 → 35문항×warm 3회 End-to-End 재측정 → P1 다중 RDB 병렬화`

## 8. 완료 조건

- Golden Set warm End-to-End p95 ≤ 15초.
- Golden Set 정답률은 기준 15/104(14.4%) 이상이며, C/D/E/F 원인 오답과 Critical Fail이 기준 대비 감소.
- Q1·Q6·Q7·Q10~Q13·Q19·Q26·Q27·Q30의 확인된 SQL 오류 패턴이 warm 3회에서 재발하지 않음.
- Q31~Q35가 정확한 ABSTAIN subtype·근거를 반환하고, Q11·Q13·Q14의 길이 초과 예외가 0건.
- 429는 루브릭대로 별도 집계하며 성능·정답률 분모에서 제외; 모든 근거의 `as_of`가 2026-08-24 이하.

## 근거 문서

- `test/pipline-test/2026-09-03_pipeline_latency_quality_report.md`
- `test/pipline-test/2026-09-03_pipeline_latency_quality_visual.ipynb`
- `test/pipline-test/golden_set_data_gap_evaluation_rubric.md`
- `test/pipline-test/latency/analysis_summary.json`, `roadmap.json`, `per_run_eval.jsonl`
