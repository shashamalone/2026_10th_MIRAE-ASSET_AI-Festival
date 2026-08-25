# RDB Vertical Slice Test

## 1. 목적과 범위

Query Frame이 단독으로 그럴듯한지를 다시 측정하는 실험이 아니다. 저장된 Query
Frame을 시작점으로 실제 운영 모듈이 검증된 물리 스키마에 grounding하고,
PostgreSQL 결과와 evidence를 정확히 반환하는지 검증한다.

대상은 RDB만으로 완결되는 다음 14문항이다.

```text
q001 q002 q003 q005 q006 q007 q008 q009
q010 q011 q012 q013 q017 q018
```

Graph/Vector 검색, 관계 질의, 35문항 전체 coverage 및 최종 자연어 문장 품질은 이
실험 범위가 아니다.

## 2. 검증 대상 파이프라인

```text
HyperCLOVA X Query Frame 1회
  → verified metadata grounding
  → deterministic validation / ABSTAIN
  → LogicalPlan
  → allowlisted PostgreSQL SELECT
  → 결과/evidence 검증
  → deterministic answer render
```

Query Frame은 의미 후보일 뿐 SQL 권위가 아니다. 운영 시 물리 컬럼과 JOIN은
`metadata/schema_bindings.json` 및 `metadata/business_rules.json`에 등록된 항목만
사용한다. 실험에서 사용하는 저장 Query Frame과 gold는 평가 입력이며, 운영
`src/**` 코드는 gold 파일을 읽지 않는다.

## 3. 안전 계약

| 항목 | 측정 기준 | 의미 |
|---|---|---|
| 스키마 allowlist | 모든 SELECT·FILTER·SORT·JOIN 식별자가 verified binding에 존재 | LLM이 만든 테이블·컬럼이 SQL로 진입하는 것을 차단 |
| 파라미터 바인딩 | 사용자 값은 `%s` parameter로 전달 | SQL injection과 문자열 조립 오류 방지 |
| 읽기 전용 실행 | PostgreSQL read-only transaction | 평가 실행이 데이터를 변경하지 않음 |
| 시간·크기 상한 | statement timeout 2초, 결과 10,000행, JOIN 최대 3개 | 15초 응답 예산과 과도한 조회 보호 |
| 데이터 기준일 | `as_of ≤ 2026-07-11` | 미래정보 유출 방지 |
| 데이터 함정 | 펀드 dedup, 국내 ETF `pd_grp_no='ETF'`, 괴리율 dummy 컬럼 금지 | 알려진 조용한 오답 방지 |
| 완전일치 | 지목 상품은 canonical name/ticker 완전일치 | 유사 상품 대체 방지 |
| ABSTAIN | 미해소 조건·허용값 위반·미래값·도메인 위반·상품 부재·실행 실패 시 중단 | 근거 없는 답변 방지 |
| Evidence | projection 전 컬럼에 source table·column·as_of 존재 | 모든 반환값의 추적 가능성 확보 |

## 4. 평가 지표

| 지표 | 계산/판정 | 통과 기준 | 지표의 의미 |
|---|---|---:|---|
| Static Plan Coverage | unresolved가 없는 LogicalPlan 수 / 14 | 14/14 | Query Frame을 실행 가능한 계획으로 grounding했는가 |
| Required Schema Contract | Gold required table exact-set 및 required columns 포함 문항 수 / 14 | 14/14 | 필요한 물리 스키마를 빠짐없이, 불필요한 테이블 없이 선택했는가 |
| Schema Hallucination | catalog에 없는 identifier를 참조한 계획 수 | 0 | 존재하지 않는 스키마를 만들지 않았는가 |
| Evidence Completeness | 결과 projection 전 컬럼의 source table·column·as_of 완비 문항 수 / 14 | 14/14 | 답변 값 전부가 근거와 연결되는가 |
| LangGraph Contract | 정상 시 RDB 실행, ABSTAIN 시 미실행, 공개 응답 5필드 assertion | PASS | 제어 흐름이 안전 정책을 실제로 강제하는가 |
| DB Execution Accuracy | 생성 계획과 Gold SQL 결과의 컬럼 집합 및 행 sequence/multiset exact 일치 | 14/14 | 실제 PostgreSQL 최종 결과가 정답 oracle과 같은가 |
| Query Frame SLA | HCX Query Frame 1회 wall-clock | `≤5초` | RDB 이전 intent 단계가 운영 시간예산을 만족하는가 |
| Live E2E Latency | HCX 호출 시작부터 5필드 응답까지 wall-clock | 시도별 15초 미만 | 모델/API 변동을 포함한 실제 응답 시간 |

DB 결과 비교는 `order_sensitive=true`이면 행 순서를 포함하고, 아니면 행의 multiset을
비교한다. DB 14/14는 이 고정 문항과 동일 snapshot에 대한 계약 테스트이지, 임의
질의 일반화 정확도가 아니다.

## 5. 정본과 재현성

이 폴더에는 운영 코드·gold·metadata 복사본을 두지 않는다.

| 역할 | 정본 |
|---|---|
| Query Frame 입력 | `vectordb_test/4_query_frame_v1/results/frames_HCX-007_audit.jsonl` |
| 일반화 입력 | `vectordb_test/6_rdb_vertical_slice/paraphrases.jsonl` |
| 질문·Gold SQL | `vectordb_test/5_semantic_schema_nl2sql/gold/` |
| 논리↔물리 binding | `metadata/schema_bindings.json` |
| business/safety rule | `metadata/business_rules.json` |
| 실제 회귀 assertion | `script/test_rdb_vertical_slice.py` |
| 운영 실행 코드 | `src/agent/**`, `src/tools/**` |

`results/metrics.json`은 위 입력의 SHA-256을 함께 기록한다. 저장 Query Frame 파일명에
`audit`가 포함돼 있지만 현행 agent는 `use_audit=False`이며, audit 판정을 실행 권위로
사용하지 않는다.

## 6. 실행 방법

저장소 루트에서 실행한다.

```bash
# metadata/catalog/TBox 정합성
python3 src/kb/build_schema_catalog.py --check

# 네트워크·DB 없이 static + LangGraph contract
python3 vectordb_test/6_rdb_vertical_slice/evaluate.py

# 로컬 PostgreSQL에서 Gold exact 비교 추가
python3 vectordb_test/6_rdb_vertical_slice/evaluate.py --db

# 1차: 14문항 각 1회, 실패 질문 유형 분류
python3 vectordb_test/6_rdb_vertical_slice/evaluate.py --smoke --write-results

# 2차: 각 3회, 실패·5초 초과 문항만 총 5회
python3 vectordb_test/6_rdb_vertical_slice/evaluate.py --stability --write-results

# 3차: 의미 보존 paraphrase 14문항 각 1회
python3 vectordb_test/6_rdb_vertical_slice/evaluate.py --generalization --write-results

# 확인한 결과로 metrics.json을 갱신할 때만 사용
python3 vectordb_test/6_rdb_vertical_slice/evaluate.py --db --write-results
```

`--db`에는 적재된 PostgreSQL이 필요하고 세 live 단계에는 PostgreSQL과 `.env`의
CLOVA key가 모두 필요하다. live 각 attempt는 HCX를 한 번만 호출하고 자동 재시도하지 않는다.
기본 실행은 외부 호출을 하지 않으며, `--write-results`가 없으면 고정 결과 파일을
덮어쓰지 않는다.

### Live 3단계 판정

1. 스모크는 시간대를 비교하지 않고 `single_product_lookup`,
   `same_vehicle_comparison`, `filtered_ranking` 중 어떤 유형이 어떤 failure code로
   실패했는지만 집계한다.
2. 안정성은 문항별 3회로 시작한다. 한 번이라도 기능 실패, ABSTAIN, Query Frame
   5초 초과, DB/evidence/응답 계약 실패가 있으면 해당 문항만 총 5회로 확장한다.
3. 일반화는 원문과 숫자·단위·연산자·정렬·limit·요청 필드가 같은 paraphrase를
   base Gold 및 핵심 LogicalPlan과 비교한다.

`functional_success`는 non-ABSTAIN·DB Gold exact·evidence complete·응답 5필드가
모두 참인 경우다. `strict_success`는 여기에 Query Frame `≤5초`까지 만족해야 한다.
성공률이 낮으면 이 실험에서는 `redesign_recommended`만 기록하고, prompt·timeout·
모델·재시도 정책 변경은 별도 후속 실험으로 분리한다.

## 7. 파일

- `evaluate.py`: 기존 회귀 테스트를 호출하는 얇은 실행기
- `paraphrases.jsonl`: Gold를 복사하지 않은 의미 보존 일반화 입력 14개
- `results/metrics.json`: 기계 판독 가능한 확정 결과와 입력 해시
- `6_1_result_rdb_vertical_slice.md`: 측정 결과, 실패 관찰, 해석과 다음 단계

## 8. Query Frame HCX latency 단일변수 후속 실험

기존 live 실패의 주원인인 HCX timeout/5초 초과를 `prompt → token → schema →
connection → queue → timeout` 순서로 한 변수씩 비교한 뒤, 선택 구성을 RDB 14문항으로
qualification한다. 운영 `src/**`는 이 실험에서 변경하지 않는다.

```bash
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --dry-run
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage prompt --write-results
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage token --write-results
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage schema --write-results
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage connection --write-results
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage queue --write-results
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage timeout --write-results
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage qualification --write-results
```

각 stage는 중복 실행을 거부하며 자동 재시도하지 않는다. 초기 arm당 3회에서 판정이
불충분하면 arm당 5회로 확장한다. queue 단계는 동일 endpoint의 순차/동시 요청 진단일
뿐 운영 설정으로 선택하지 않는다. 상세 명세와 누적 결과는
[`6_2_result_query_frame_latency.md`](6_2_result_query_frame_latency.md), 호출 단위 원자료와
집계는 `results/query_frame_latency_raw.jsonl`,
`results/query_frame_latency_metrics.json`에 기록한다.
