# 6. RDB Vertical Slice 검증 결과

## 요약

- 측정일: **2026-08-24**
- 데이터 cutoff: **2026-07-11**
- 대상: RDB-only 예상질의 **14문항**
- Query Frame 모델: HyperCLOVA X `HCX-007`
- PostgreSQL 제한: read-only, statement timeout `2초`, 최대 `10,000행`
- 결론: **고정 Query Frame 이후 RDB 정확성·안전 계약은 PASS**
- 보류: **live HCX 가용성과 p95 15초는 통과로 판정할 수 없음**

주요 결과는 Static Plan 14/14, Required Schema Contract 14/14, Schema
Hallucination 0건, Evidence Completeness 14/14, LangGraph Contract PASS,
PostgreSQL Gold Exact 14/14다. 별도 live q018 관찰은 3회 중 1회만 정상
성공했으며, 두 번은 HCX API가 12초 안에 응답하지 않아 안전 ABSTAIN했다.

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

## 6. Live HCX E2E 관찰

q018 하나를 `agent.agent_core.ask()`로 실행해 HCX Query Frame부터 PostgreSQL,
evidence renderer까지 wall-clock을 관찰했다.

| 시도 | HCX timeout 설정 | 결과 | 응답시간 | Evidence |
|---:|---:|---|---:|---:|
| 1 | 12초 | 안전 ABSTAIN (`ReadTimeout`) | 12.093초 | 0 |
| 2 | 12초 | 안전 ABSTAIN (`ReadTimeout`) | 12.232초 | 0 |
| 3 | 13초 | 정상 성공 | 6.560초 | 10 |

세 시도 모두 공개 응답 5필드는 유지했다. timeout 시 빈 Frame으로 전체 상품을 조회하지
않고 `Query Frame 추출 실패`로 ABSTAIN했으므로 실패 안전성은 확인됐다. 다만 정상
답변 가용성은 이 관찰에서 1/3이며 표본도 하나의 질문 3회뿐이다. 따라서 다음 문장은
근거가 없다.

- `live p95 < 15초를 달성했다`
- `HCX 응답 지연이 안정화됐다`
- `14문항 live E2E 정확도가 14/14다`

검증된 사실은 **성공한 1회가 6.56초였고, 두 timeout도 추측 답변 대신 15초 안에
ABSTAIN했다**는 범위다.

## 7. 해석과 한계

### 확정할 수 있는 것

1. 고정된 14개 Query Frame 이후 현행 deterministic RDB 경로는 Gold 결과와 14/14 일치한다.
2. 허용되지 않은 schema identifier와 JOIN은 compiler 경계에서 실행되지 않는다.
3. 각 projection 컬럼은 source와 도메인 기준일을 갖는다.
4. 대표 invalid taxonomy/future value와 Query Frame timeout은 ABSTAIN한다.

### 아직 확정할 수 없는 것

1. offline 평가는 저장 Frame을 사용하므로 실시간 HCX 추출 안정성을 포함하지 않는다.
2. 고정 14문항 통과가 paraphrase나 처음 보는 RDB 질문의 일반화 성능을 뜻하지 않는다.
3. entity 미존재, DB 장애 등 모든 ABSTAIN 유형의 운영 빈도는 아직 측정하지 않았다.
4. Graph/Vector가 필요한 나머지 질문에는 이 결과를 확장 적용할 수 없다.

## 8. 다음 Promotion Gate

다음 단계에서는 코드를 더 늘리기 전에 현재 실행기로 아래만 추가 측정한다.

1. 14문항 live 반복 최소 3회: 성공률, answer correctness, p50/p95, timeout률
2. 의미를 유지한 holdout paraphrase: grounding 및 DB exact 일반화
3. ABSTAIN confusion matrix: 정상 질의 false abstain과 위험 질의 false answer
4. 위 조건 통과 후에만 Graph/Vector route를 별도 vertical slice로 추가

현재 판정은 **RDB-only offline accuracy/safety PASS, live stability NOT YET
PROMOTED**다.
