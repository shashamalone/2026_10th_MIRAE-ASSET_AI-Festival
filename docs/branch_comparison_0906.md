# 현재 브랜치와 feat/final-0906 비교 및 README 통합

비교일: 2026-09-10. 원격을 fetch한 뒤 확인했다. 이 문서는 코드 검토 결과이며 기능 우열이나 실서비스 품질을 실측한 결과는 아니다.

## 결론

**차이가 크다.** 

- 공통 LangGraph 파이프라인을 사용하지만 SQL 컴파일·스키마 검증·근거 구성과 Graph 연결 동작이 달라졌고, final은 개발 문서·테스트·빌더를 대거 제거한 제출용 트리다. 
- final을 그대로 덮어쓰면 현재 브랜치의 개발·검증 자산과 미커밋 작업이 사라질 수 있다.

## 비교 기준


| 기준                           | 커밋                                         |
| ---------------------------- | ------------------------------------------ |
| 현재 fix/intent-abstain-answer | `b2bfd449984f27aaa36a15da93f50c452636ee61` |
| 최신 원격 main                   | `9afbae339db997c3d7ccdab9b07d5a49dcef708d` |
| 원격 feat/final-0906           | `4075a8c002f76fadd18048bcd1b92e9d9eaa053e` |
| 로컬 main (최신 아님)              | `cae749def3a31041c479438831aeb34360bd9ee6` |
| 현재/final 공통 조상               | `ba8040a42c2d487142271e184059bb17b7cb1154` |


README 통합 원본은 최신 `origin/main:README.md`와 `origin/feat/final-0906:README.md`다. 기존 작업 트리 README의 메타데이터 이동 설명과 추가 질의 예시도 검토했다. 브랜치 checkout·merge·commit은 수행하지 않았다.

## 정량 비교

- 현재 브랜치에만 있는 커밋: **22개**, final에만 있는 커밋: **71개**. merge 커밋을 포함한 도달 가능성 기준이며 독립 기능 개수는 아니다.
- HEAD → final 전체: **143파일, +2,142,345 / -212,642줄**.
- 핵심 런타임(`src/agent`, `src/tools`, `src/infrastructure`): **23파일, +4,362 / -1,227줄**.
- 수백만 줄 차이의 주원인은 `ontology/instances_*.ttl` 5개 추가다. 줄 수만으로 코드 변경 규모를 판단하면 과장된다.
- `data/` 경로의 추적 파일 차이는 없다. 다만 별도 경로인 `src/data/enriched/`의 CSV 4개는 final에서 삭제됐다.

파일 상태 집계(HEAD → final): A 10개, D 109개, M 23개, R 1개. R은 이동 감지다.

## 주요 차이와 영향


| 영역       | 현재 HEAD                                  | final                                              | 통합 시 확인 사항                             |
| -------- | ---------------------------------------- | -------------------------------------------------- | -------------------------------------- |
| 실행 그래프   | 의존성 웨이브 스케줄러                             | 같은 구조, graph.py 차이는 주석·공백 위주                       | 스케줄러 전체 재구현으로 볼 차이는 아님                 |
| RDB SQL  | `agent/sql_builder.py`                   | 해당 파일 삭제, `tools/catalog_sql.py` 추가                | 컴파일 계약과 호출부를 함께 비교해야 함                 |
| 스키마 통제   | `rdb_schema.py` 중심                       | `schema_snapshot.py`, `sql_guard.py` 추가 및 카탈로그 변경  | 물리 스키마 검증 기능의 도입 범위 확인                 |
| 의도·답변    | intent_guard/nodes/prompts/utils         | 네 파일 모두 의미 있는 변경, `evidence_contract.py` 추가        | 조건 보존·표시 규칙·답변 불가 처리 회귀 확인             |
| 관계 근거    | Graph 결과와 답변 경로                          | `holdings_provenance.py` 추가, Graph orchestrator 변경 | 편입종목 출처와 관계 handoff 검증                 |
| Graph 연결 | 기본 로컬 저장소 확인 후 endpoint                  | endpoint만 설정하면 직접 HTTP 조회                          | 연결 지연·폴백 테스트 필요                        |
| Graph 집계 | default/named graph를 UNION으로 집계          | named graph만 집계                                    | 서버 union-default-graph 설정에 따른 중복 집계 차이 |
| Vector   | 기존 상품 식별·문서 검색                           | client/vector_search 변경 및 short_name 조회 보완         | 검색 범위·상품 식별 회귀 확인                      |
| 데이터·빌더   | `src/kb`의 빌더·검증기, `src/data/enriched` 유지 | kb는 config만 남고 빌더·CSV 제거, ABox TTL 추가              | final은 재생성·유지보수 자산이 크게 축소됨             |
| 문서·평가    | docs/EDA/goldset/script/test 자산 유지       | 추적된 해당 자산 대거 삭제                                    | README에 남은 경로를 그대로 사용하면 실패             |
| 저장소 규칙   | AGENTS.md·로컬 스킬 추적                       | 삭제                                                 | 현재 규칙을 유지하며 필요한 변경만 선별할 필요             |


## 기존 미커밋 작업

작업 시작 시 추적 파일 **11개(+487/-468줄)**에 변경이 있었다. 아래 목록의 `??` 파일들은 위 커밋 간 통계에 포함되지 않는다. `nodes.py`의 답변 구성 변경, `prompts.py`, 추가 답변 테스트, 메타데이터 이동은 final 변경과 겹칠 수 있으므로 병합 시 별도 검토 대상이다.

```text
M README.md
 M docs/agent-spec_0825_v1.0.md
 D metadata/business_rules.json
 D metadata/schema_bindings.json
 M script/agent_test/test_vector_search_node.py
 M src/agent/nodes.py
 M src/agent/prompts.py
 M test/gragh-test/baseline_0826.ipynb
 M test/gragh-test/gragh-test_0830.ipynb
 M test/pipline-test/latency/analyze.py
 M test_agent_v2.0.ipynb
?? docs/agent-spec_0906_v3.0.md
?? ppt/
?? script/agent_test/test_answer_generation.py
?? script/build_ontology_instances.py
?? script/collect_etf_holdings.py
?? script/validate_ontology.py
?? test/gragh-test/business_rules.json
?? test/gragh-test/schema_bindings.json
?? test/pipline-test/2026-09-05_lane_c_answer_visual.ipynb
?? test/pipline-test/latency/run_laneC_c12_0905.log
?? test/pipline-test/latency/run_laneC_c12b_0905.log
?? test/pipline-test/latency/run_laneC_q31_0905.log
?? test/pipline-test/latency/traces_laneC_c12_0905.jsonl
?? test/pipline-test/latency/traces_laneC_c12b_0905.jsonl
?? test/pipline-test/latency/traces_laneC_q31_0905.jsonl
?? "\354\230\244\353\245\230\354\236\254\355\230\204.ipynb"
```

이번 작업에서는 README와 이 비교 문서만 작성했다. 기존 README의 원문은 `/tmp/readme-0906-review/README.before.md`에 보관했다(임시 보관이며 저장소 제출물은 아님).

## README 통합 판단


| 원본 내용                                 | 통합 결과                                              |
| ------------------------------------- | -------------------------------------------------- |
| main의 프로젝트 배경·4대 구성요소·질의 예시           | 프로젝트 소개와 기능 표로 통합                                  |
| main의 미작성 기간·팀원·폴더 자리표시자, 중복 섹션       | 제거                                                 |
| main의 2026-07-11 기준일·모든 LLM 금지 표현     | AGENTS.md에 맞게 2026-08-24 및 의도 분석·답변 생성의 모델 제한으로 수정 |
| main의 RDB-only 설명·Graph 미구현 설명        | 현재 소스의 RDB/Graph/Vector 구현과 SQL 폴백 설명으로 갱신         |
| final의 설치·환경변수·app.invoke·웨이브 스케줄러 설명 | 현재 브랜치 구현에 맞춰 통합                                   |
| final의 live 스키마 통제 설명                 | 현재에는 해당 모듈이 없으므로 현재 기능으로 소개하지 않음                   |
| final의 serve_answer·API 테스트 안내        | final 최신 트리와 현재 모두 파일이 없어 실행 안내에서 제외               |
| final의 `--output-dir` 채점 옵션           | 현재 analyze.py에 없어 제거하고 기존 산출물 덮어쓰기 동작 설명           |
| final의 Graph 기본 timeout 3초            | 실제 코드·.env.example의 60초로 정정                        |
| final의 배포 수치·문서 커버리지·지원 OS/버전 단정      | 현재 환경에서 재검증하지 않은 값이므로 보장 문구에서 제외                   |
| 삭제되거나 이동된 문서 링크                       | 현재 파일 경로로 교체                                       |


## 재현 명령

```bash
git rev-list --left-right --count HEAD...origin/feat/final-0906
git diff --stat HEAD origin/feat/final-0906
git diff --shortstat HEAD origin/feat/final-0906 -- src/agent src/tools src/infrastructure
git log --oneline --left-right HEAD...origin/feat/final-0906
git diff --name-status HEAD origin/feat/final-0906
git diff
```

## 후속 코드 통합 시 권장 순서

1. 기존 미커밋 작업을 먼저 별도 커밋 또는 백업으로 보존한다.
2. SQL·스키마 계약, Graph·편입 근거, 답변·의도 규칙을 관련 호출부와 함께 기능 단위로 통합한다.
3. 현재 테스트 자산으로 회귀를 확인하고, DB·LLM을 연결한 골든셋 품질·15초 응답 평가를 수행한다.
4. final의 삭제·데이터 추가 커밋은 제출 범위와 재생성 정책을 별도 확인한 뒤 반영한다.

## 이번 작업의 검증 결과

- `git diff --check -- README.md`: 통과.
- README 로컬 링크 16개: 모두 존재. 두 문서의 코드 펜스 짝 확인 통과.
- `PYTHONDONTWRITEBYTECODE=1 python3 script/agent_test/test_sql_builder.py`: 30개 테스트 통과.
- 실제 LLM·DB E2E, 배포 API, 브랜치 간 성능·정확도 비교는 미실행. 문서만 변경했으며 온톨로지·외부 데이터는 변경하지 않았다.

