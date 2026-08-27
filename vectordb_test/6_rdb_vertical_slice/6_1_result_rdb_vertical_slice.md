# 6. RDB Vertical Slice 검증 결과

## 요약

- 측정일: **2026-08-24**
- 데이터 cutoff: **2026-07-11**
- 대상: RDB-only 예상질의 **14문항**
- Query Frame 모델: HyperCLOVA X `HCX-007`
- PostgreSQL 제한: read-only, statement timeout `2초`, 최대 `10,000행`
- 결론: **고정 Query Frame 이후 RDB 정확성·안전 계약은 PASS**
- Live 운영 안정성: **FAIL — 재설계 필요**

주요 결과는 Static Plan 14/14, Required Schema Contract 14/14, Schema
Hallucination 0건, Evidence Completeness 14/14, LangGraph Contract PASS,
PostgreSQL Gold Exact 14/14다. 반면 새 live 실험은 스모크 strict success 0/14,
안정성 7/70(10%), paraphrase 일반화 2/14(14.29%)로 Query Frame 5초 목표와
운영 성공률을 충족하지 못했다. 기능적으로 성공한 시도의 DB exact와 evidence는
통과했지만 HCX timeout이 전체 실패의 대부분을 차지했다.

## 1. 실험 질문

이 실험은 다음 질문에 답한다.

> 1단계 Query Frame을 받은 뒤 현행 `src/**` 코드가 허용된 schema와 business
> rule만으로 PostgreSQL 질의를 만들고, Gold SQL과 동일한 결과와 추적 가능한
> evidence를 반환하는가?

따라서 Query Frame 슬롯 자체의 정확성은 선행 실험
`vectordb_test/4_query_frame_v1`의 측정 대상이다. 여기서는 저장된 HCX-007 Frame을
고정 입력으로 사용해 이후 grounding·validation·compiler·execution·render 경로를
격리 검증한다.

## 2. 대상과 데이터 snapshot

| 도메인 | 문항 | 주요 유형 |
|---|---|---|
| 국내채권 | q001, q002, q003, q011, q013 | 완전일치 조회, JOIN, 등급 서열, 잔존일수, 순위 |
| 국내ETF | q005, q012 | 완전일치 조회, ETN 제외, 판매·거래·연금 상태 필터 |
| 해외ETF | q006, q007, q017, q018 | 티커 조회, 자산/지역 필터, 큰 수, 보수, AUM 정렬 |
| 공모펀드 | q008, q009, q010 | dedup grain, 클래스 비교, 대표/모펀드 식별자 |

입력 snapshot은 `results/metrics.json`에 SHA-256으로 고정했다. 측정 당시 worktree가
dirty였으므로 commit SHA를 재현 근거로 사용하지 않고 다음 네 파일 해시를 사용한다.

| 입력 | SHA-256 앞 12자리 |
|---|---|
| 저장 Query Frame | `e57dd4f918ca` |
| Gold NL2SQL | `671c7298ce4c` |
| Schema bindings | `6a8ae73605fa` |
| Business rules | `7a80c5c25fc0` |

PostgreSQL 사전검사에서는 12개 테이블, PK/FK 20개, cutoff 위반 0건을 확인했다.
실질 기준일은 도메인별로 채권 `2026-02-24`, 국내ETF `2026-06-15`, 해외ETF
NAV `2026-06-14`, 공모펀드 snapshot `2026-07-11`을 사용한다.

## 3. 테스트 코드와 검증 경계

`evaluate.py`는 별도 채점 로직을 재구현하지 않고
`script/test_rdb_vertical_slice.py`의 회귀 함수를 호출한다.

| 계층 | 검증 대상 | 코드 |
|---|---|---|
| Metadata | binding이 실제 12개 테이블 컬럼과 TBox URI에 존재하는지, 금지 컬럼·펀드 raw grain이 없는지 | `src/kb/build_schema_catalog.py` |
| Grounding | 자연어 슬롯을 verified binding, 단위, 범주값, 등급 rank, 기준일로 변환 | `src/tools/schema_context.py` |
| Validation | invalid taxonomy, future value, domain mismatch, unresolved query를 ABSTAIN | `src/tools/validate.py` |
| Compiler/DB | allowlisted SELECT/JOIN, parameter binding, read-only 실행, timeout/row limit | `src/tools/rdb.py` |
| Orchestration | 성공 시 DB 실행, ABSTAIN 시 DB 미실행, 결과/evidence 검증 | `src/agent/agent_core.py`, `nodes.py` |
| Oracle 비교 | 생성 결과와 Gold SQL의 columns 및 rows exact 비교 | `script/test_rdb_vertical_slice.py` |

Gold는 테스트 oracle에서만 읽는다. 운영 경로가 질문 ID에 따른 Gold SQL을 선택하거나
Gold 결과를 답변에 사용하는 코드는 없다.

## 4. 지표 정의와 결과

### 4.1 Static Plan Coverage — 14/14 PASS

**측정 기준:** 각 문항에 대해 도메인이 하나로 확정되고 `unresolved=[]`인
LogicalPlan이 생성돼 compiler에 전달 가능한지 assertion한다.

**지표 의미:** Query Frame의 자연어 슬롯이 실제 실행 가능한 filter/select/order/
entity binding으로 모두 해소됐는지를 나타낸다. SQL 결과 정확성을 직접 보장하지는
않으므로 DB Execution Accuracy와 함께 해석한다.

### 4.2 Required Schema Contract — 14/14 PASS

**측정 기준:** 계획이 참조하는 물리 테이블 집합이 Gold `required_tables`와 정확히
같고, Gold `required_columns.all`이 계획의 SELECT·FILTER·SORT·entity 컬럼 집합에
모두 포함되는지 검사한다.

**지표 의미:** 필요한 테이블과 컬럼을 빠뜨리지 않았는지 측정한다. 테이블은 exact-set
이므로 불필요한 테이블을 추가해도 실패한다. 컬럼은 required inclusion이므로 추가된
허용 컬럼 자체는 직접 감점하지 않는다.

### 4.3 Schema Hallucination — 0건 PASS

**측정 기준:** LogicalPlan의 모든 binding을 `schema_bindings.json`과 대조하고,
compiler는 등록되지 않은 binding, usage가 허용되지 않은 SELECT/FILTER/SORT 및
allowlist에 없는 JOIN을 거부한다.

**지표 의미:** LLM이 생성한 가상의 테이블·컬럼·JOIN이 실행 SQL로 침투하는지를
측정한다. 값 자체의 의미 정확성은 Required Schema/DB Execution 지표가 보완한다.

### 4.4 Evidence Completeness — 14/14, 100% PASS

**측정 기준:** 결과 projection의 모든 컬럼에 `source_table`, `source_column`, `as_of`,
`as_of_basis`, `source_kind`가 생성되고, 실행 후 실제 result columns와 evidence의
source column 순서가 같은지 검사한다.

**지표 의미:** 답변의 모든 반환값을 원천 또는 주최측 기반 파생 컬럼과 기준일로
추적할 수 있는지 나타낸다. evidence 존재가 값의 정답을 보장하는 것은 아니므로 Gold
결과 비교를 별도로 수행한다.

### 4.5 LangGraph Contract — PASS

**측정 기준:** mock DB를 사용한 정상 q001은 RDB 노드를 실행하고 evidence가 있는
5필드 응답을 반환해야 한다. 존재하지 않는 등급 `AAAA`를 묻는 q031은 RDB 노드가
호출되면 즉시 실패하도록 mock하고, 실제로는 validation에서
`ABSTAIN_INVALID_TAXONOMY`로 분기하는지 검사한다.

공개 응답 필드는 다음 다섯 개로 고정한다.

```text
question_id, question, retrieved_context, think_trace, answer
```

**지표 의미:** ABSTAIN이 문구에 그치지 않고 실행 제어를 실제로 중단하며, 정상 경로만
DB를 호출하는지 검증한다. 미래 확정값 q034는 `ABSTAIN_FUTURE_DATA`도 별도 assertion한다.

### 4.6 DB Execution Accuracy — 14/14 PASS

**측정 기준:** 동일 PostgreSQL snapshot에서 현행 compiler 결과와 Gold SQL을 각각
실행한다. 양쪽 result column 집합이 같아야 하며, `order_sensitive=true` 문항은 행
sequence, 나머지는 중복을 보존한 multiset이 정확히 같아야 통과한다.

```text
DB Execution Accuracy = exact 결과 일치 문항 수 / 14 = 14 / 14
```

**지표 의미:** 스키마 구조가 그럴듯한 수준을 넘어 최종 반환 데이터가 oracle과 같은지
측정한다. q018 최초 실패에서는 `ORDER BY ... DESC`의 PostgreSQL 기본 NULL 정렬이
Gold의 `NULLS LAST`와 달랐으며, 명시적 정렬에도 verified default NULL 정책을 적용해
수정한 뒤 14/14가 됐다.

## 5. 문항별 결과

| 문항 | 도메인/핵심 검증 | Static | Evidence | DB exact |
|---|---|---:|---:|---:|
| q001 | 채권 완전일치·원천 속성 | PASS | PASS | PASS |
| q002 | 채권 raw↔enriched JOIN·잔존일수 | PASS | PASS | PASS |
| q003 | 원등급↔정규화 등급·만기구분 | PASS | PASS | PASS |
| q005 | 국내ETF raw↔enriched·보수 보강 | PASS | PASS | PASS |
| q006 | 해외ETF 티커·가격/AUM 기준일 | PASS | PASS | PASS |
| q007 | 해외ETF 자산·지역·전략 원문 | PASS | PASS | PASS |
| q008 | 공모펀드 dedup grain·수익률 | PASS | PASS | PASS |
| q009 | 공모펀드 범주 속성·순자산 | PASS | PASS | PASS |
| q010 | 펀드 클래스 canonical 완전일치 | PASS | PASS | PASS |
| q011 | `AA- 이상 → rank <= 4`·매수가능 | PASS | PASS | PASS |
| q012 | ETF/ETN 분리·판매/정지/연금 상태 | PASS | PASS | PASS |
| q013 | 3년→1,095일·수익률 NULLS LAST·Top 10 | PASS | PASS | PASS |
| q017 | 1천억→100,000,000,000·미국 주식형 | PASS | PASS | PASS |
| q018 | 해외 채권형·보수·AUM NULLS LAST·Top 10 | PASS | PASS | PASS |

## 6. Live 실험 판정 기준

각 attempt는 HCX Query Frame을 정확히 한 번 호출한다. 자동 재시도나 audit LLM은
사용하지 않는다.

| 판정 | 조건 |
|---|---|
| Functional Success | non-ABSTAIN + DB Gold exact + evidence complete + 공개 응답 5필드 |
| Query Frame SLA Pass | Query Frame wall-clock `≤5초` |
| Strict Success | Functional Success와 Query Frame SLA를 모두 만족 |

HTTP timeout은 현행 운영 설정인 13초를 유지했다. 5초는 측정 목표이며, 5초를 넘겨
응답한 호출도 기능 결과를 끝까지 확인한 뒤 `query_frame_over_5s`로 실패 집계했다.
실험 도중 timeout·prompt·model·retry 정책은 변경하지 않았다.

## 7. 1차 Smoke — 실패 질문 유형 선별

14문항을 각 1회 실행했다. 시간대 비교는 하지 않았다.

| 지표 | 결과 |
|---|---:|
| 전체 attempt | 14 |
| Functional Success | 1/14 (7.14%) |
| Query Frame ≤5초 | 0/14 (0%) |
| Strict Success | 0/14 (0%) |
| Query Frame timeout | 13/14 (92.86%) |
| Query Frame p50 / p95 | 13.0585초 / 13.096초 |
| E2E p50 / p95 | 13.064초 / 13.100초 |

q008만 기능적으로 성공했지만 Query Frame 5.584초로 strict success는 아니었다.

| 실패 질문 유형 | 실패 문항 | 주요 failure code |
|---|---|---|
| single_product_lookup | q001, q002, q003, q005, q006, q007, q008, q009 | timeout 7, over-5s 1 |
| same_vehicle_comparison | q010 | timeout 1 |
| filtered_ranking | q011, q012, q013, q017, q018 | timeout 5 |

모든 유형에서 실패했으므로 특정 의미 유형의 문제라고 결론 내릴 수 없다. 공통 upstream
HCX timeout이 지배적인 패턴이다. timeout은 모두 빈 Frame으로 전체 조회하지 않고
`ABSTAIN_UNRESOLVED_QUERY`로 안전 종료됐다.

## 8. 2차 Stability — 3회에서 필요 시 5회

각 문항을 먼저 3회 실행하고, 실패·ABSTAIN·5초 초과가 한 번이라도 있으면 2회를
추가했다. 14문항 모두 확장 조건에 해당해 총 70회가 됐다.

| 지표 | 결과 |
|---|---:|
| 전체 attempt | 70 |
| Functional Success | 8/70 (11.43%) |
| Query Frame ≤5초 | 7/70 (10.00%) |
| Strict Success | 7/70 (10.00%) |
| Query Frame timeout | 62/70 (88.57%) |
| Query Frame p50 / p95 | 13.056초 / 13.110초 |
| E2E p50 / p95 | 13.059초 / 13.112초 |

| 문항 | Functional | ≤5초 | Strict | Query Frame min / median / max(초) |
|---|---:|---:|---:|---|
| q001 | 1/5 | 1/5 | 1/5 | 4.312 / 13.076 / 13.128 |
| q002 | 2/5 | 2/5 | 2/5 | 3.945 / 13.050 / 13.065 |
| q003 | 1/5 | 1/5 | 1/5 | 2.687 / 13.065 / 13.307 |
| q005 | 1/5 | 1/5 | 1/5 | 3.063 / 13.072 / 13.110 |
| q006 | 0/5 | 0/5 | 0/5 | 13.056 / 13.063 / 13.235 |
| q007 | 1/5 | 1/5 | 1/5 | 3.054 / 13.046 / 13.056 |
| q008 | 0/5 | 0/5 | 0/5 | 13.042 / 13.047 / 13.058 |
| q009 | 0/5 | 0/5 | 0/5 | 13.054 / 13.056 / 13.071 |
| q010 | 1/5 | 1/5 | 1/5 | 4.742 / 13.047 / 13.068 |
| q011 | 1/5 | 0/5 | 0/5 | 7.119 / 13.055 / 13.078 |
| q012 | 0/5 | 0/5 | 0/5 | 13.050 / 13.053 / 13.066 |
| q013 | 0/5 | 0/5 | 0/5 | 13.046 / 13.069 / 13.072 |
| q017 | 0/5 | 0/5 | 0/5 | 13.043 / 13.058 / 13.074 |
| q018 | 0/5 | 0/5 | 0/5 | 13.045 / 13.056 / 13.067 |

성공한 8회 중 7회는 5초 이내였고, q011 한 번은 DB exact/evidence가 맞았지만
7.119초가 걸렸다. 기능 성공 시 DB mismatch와 evidence 실패는 0건이었다.
`strict_success_rate=10% < 95%`이므로 `redesign_recommended=true`다.

## 9. 3차 Generalization — 의미 보존 Paraphrase

각 원문에서 상품명·티커, 숫자·단위, 연산자, 정렬·limit, 요청 필드를 유지하고 어순과
조사만 바꾼 paraphrase 14개를 각 1회 실행했다.

| 지표 | 결과 |
|---|---:|
| 전체 attempt | 14 |
| Functional Success | 3/14 (21.43%) |
| Query Frame ≤5초 | 2/14 (14.29%) |
| Strict Success | 2/14 (14.29%) |
| Query Frame timeout | 10/14 (71.43%) |
| Query Frame p50 / p95 | 13.053초 / 13.079초 |
| E2E p50 / p95 | 13.056초 / 13.082초 |
| Base 핵심 plan 동등 | 3/14 (21.43%) |

- q001_p1, q007_p1: strict success, DB exact, evidence 및 plan 동등성 통과
- q011_p1: 기능·DB·evidence·plan은 통과했으나 Query Frame 6.276초로 SLA 실패
- q013_p1: 8.320초 후 `ABSTAIN_UNRESOLVED_QUERY`
- 나머지 10건: Query Frame HTTP timeout 후 안전 ABSTAIN

일반화 성공률이 낮지만 timeout이 다수를 차지하므로 paraphrase 의미 처리 능력만의
실패율로 해석할 수 없다. 성공한 3건은 모두 base Gold DB 결과와 핵심 plan이 같았다.

## 10. 이전 q018 단건 관찰

새 5초 목표 실험과 섞지 않고 `legacy_q018_observation`으로 보존했다.

| 시도 | HTTP timeout | 결과 | 응답시간 |
|---:|---:|---|---:|
| 1 | 12초 | timeout 안전 ABSTAIN | 12.093초 |
| 2 | 12초 | timeout 안전 ABSTAIN | 12.232초 |
| 3 | 13초 | 정상 성공 | 6.560초 |

## 11. 최종 판정과 다음 단계

### 통과

1. 저장 Query Frame 이후 deterministic RDB 경로: Gold exact 14/14
2. Schema hallucination 0건, evidence completeness 100%
3. HCX timeout 시 DB를 실행하지 않고 안전 ABSTAIN
4. 이번 live 실험에서 기능 성공한 호출의 DB exact/evidence 계약

### 실패

1. Query Frame 5초 SLA: 안정성 단계 7/70(10%)
2. Live Functional Success: 안정성 단계 8/70(11.43%)
3. Live Strict Success: 안정성 단계 7/70(10%)
4. Paraphrase Strict Success: 2/14(14.29%)

따라서 현재 판정은 **RDB deterministic path PASS, 실시간 HCX 포함 운영 안정성
FAIL, 재설계 필요**다. 다음 실험은 이번 결과를 고정한 뒤 HCX latency 원인을 먼저
분리해야 한다. prompt 길이·출력 schema/token·API endpoint/queue·timeout 정책 중
하나만 독립변수로 바꾸어 비교하며, 안정성 결과를 개선하기 전에 Graph/Vector 범위로
확장하지 않는다.

후속 단일변수 실험의 명세·실행 결과는
[`6_2_result_query_frame_latency.md`](6_2_result_query_frame_latency.md)에 분리해 누적한다.
