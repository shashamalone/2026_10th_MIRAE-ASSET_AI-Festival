# Query Frame HCX Latency 단일변수 실험 결과

- 갱신 시각: 2026-08-25T13:50:52+09:00
- 모델/endpoint: `HCX-007` / `https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-007`
- 데이터 기준일: `2026-07-11`
- 목표: Query Frame 구조·RDB 정확성을 유지하면서 wall-clock 5초 이내
- 범위: 실험 전용 코드와 결과만 추가하며 운영 `src/**`는 변경하지 않음
- 결론 요약 :
  - 1. RDB 검색·SQL 실행·evidence 생성 경로는 성공했습니다.
  - 2. 실시간 HCX를 포함한 운영 안정성은 아직 실패입니다.
  - 3. 최종 실패 6건 중 5건은 SQL/RDB 오류가 아니라 API 429입니다.
  - 4. q006만 HCX Query Frame의 엔티티 해석 또는 grounding 문제입니다.
  - 5. 실험 후반에 429가 연속 발생한 점을 보면 호출량 제한 또는 queue window의 영향일 가능성이
  
         높습니다. 이는 현재 결과에 근거한 추론이며, 정확한 quota 정책 확인이 필요합니다.
  - 6. 현재 결과로는 “HCX 자체가 항상 5초보다 느리다”고 결론 내릴 수 없습니다. Qualification에서
  
         정상 응답한 9건은 모두 5초 이내였습니다. 다만 q013처럼 반복적으로 6~8초가 걸리는 복잡 질
  
         의도 확인됐습니다.
  
    

## 1. 측정 명세


| 지표                    | 측정 기준                                                                  | 의미                           |
| --------------------- | ---------------------------------------------------------------------- | ---------------------------- |
| Valid Query Frame ≤5s | HTTP 호출 시작부터 JSON parse·원본 schema·14필드 guard·TBox leak 검사를 5초 이내 통과    | intent 출력의 구조와 시간 목표를 동시에 충족 |
| Functional Success    | non-ABSTAIN + 실제 PostgreSQL Gold exact + evidence complete + 공개 응답 5필드 | 빠르기와 무관하게 RDB E2E가 정답을 반환    |
| Strict Success        | Valid Query Frame ≤5s AND Functional Success                           | 이 실험의 arm 선택 지표              |
| Completed latency     | HTTP 200 응답만의 wall-clock                                               | timeout·429를 빠른 응답으로 오인하지 않음 |
| Censored timeout      | timeout까지 기다린 wall-clock을 별도 기록                                        | 미완료 호출을 latency 표본에 섞지 않음    |
| HTTP 429/5xx          | 응답 상태별 개수                                                              | endpoint/queue 운영 안정성 확인     |


공통 조건은 HCX-007, temperature=0, topP=0.8, seed=0, thinking=none, non-streaming이다. 따라서 TTFT는 측정하지 않는다. 질문 본문·request body·인증값은 원자료에 저장하지 않는다.

## 2. 단계별 결과


| 단계            | Arm       | 시도/HTTP 200/429/timeout | Strict       | 완료 latency min/median/max(초) | 판정                      |
| ------------- | --------- | -----------------------: | ------------: | ----------------------------: | ----------------------- |
| prompt        | control   | 3/3/0/0                 | 2/3 (66.7%)  | 3.5302/4.6071/7.506          | control                 |
| prompt        | candidate | 3/3/0/0                 | 0/3 (0.0%)   | 5.2124/5.9246/6.6491         | control                 |
| token         | control   | 5/5/0/0                 | 1/5 (20.0%)  | 3.1201/5.1121/9.4974         | control                 |
| token         | candidate | 5/5/0/0                 | 1/5 (20.0%)  | 3.2833/5.5794/7.236          | control                 |
| schema        | control   | 5/5/0/0                 | 2/5 (40.0%)  | 3.4037/5.0464/7.4958         | control                 |
| schema        | candidate | 5/4/1/0                 | 1/5 (20.0%)  | 4.4253/5.4611/7.6519         | control                 |
| connection    | control   | 5/5/0/0                 | 3/5 (60.0%)  | 3.2314/4.9425/8.4779         | control                 |
| connection    | candidate | 5/4/1/0                 | 2/5 (40.0%)  | 2.559/4.3556/7.3483          | control                 |
| queue         | control   | 4/4/0/0                 | 0/4 (0.0%)   | 6.7696/6.8624/8.0117         | diagnostic only         |
| queue         | candidate | 4/4/0/0                 | 0/4 (0.0%)   | 6.8435/7.2194/7.4224         | diagnostic only         |
| timeout       | control   | 5/5/0/0                 | 3/5 (60.0%)  | 2.9918/4.684/6.917           | control                 |
| timeout       | candidate | 5/3/1/1                 | 3/5 (60.0%)  | 2.6485/2.8839/4.6575         | control                 |
| qualification | selected  | 14/9/5/0                | 8/14 (57.1%) | 2.6576/3.3461/4.7718         | runtime_candidate=false |


표의 시도 열은 `전체/HTTP 200/HTTP 429/timeout` 순서다. 모든 payload와 connection 후보는 선택 기준을 넘지 못해 control을 유지했다.

### 변수별 해석

- Prompt: 6,128자 control이 strict 2/3, 4,994자 축약안이 0/3이었다. 길이 축소만으로 개선되지 않았고 축약안에 downstream 회귀가 있었다.
- Token: 3,072 대 1,536은 5쌍 후 strict 1/5 대 1/5로 동률이었다.
- Schema: full 대 description 제거는 strict 2/5 대 1/5였으며 제거안에서 HTTP 429가 1건 발생했다.
- Connection: DNS 0.0098초로 병목이 아니었다. fresh strict 3/5, Session 2/5이고 Session arm에 HTTP 429가 1건 있었다.
- Queue: q013은 순차와 concurrency=2 모두 strict 0/4였다. 동시 실행은 두 요청의 wave wall time을 약 7초로 묶어 처리량만 높였고 개별 5초 SLA는 개선하지 않았다.
- Timeout: 13초와 5초 모두 strict 3/5였다. 5초 정책은 q013을 약 5.03초에 안전 종료했으나 원인 latency를 줄이지 않았다.

## 3. 현재 선택 구성

```json
{
  "prompt": "full",
  "max_completion_tokens": 3072,
  "schema": "full",
  "connection": "fresh",
  "timeout_seconds": 13
}
```

## 4. 판정 기준

- 각 payload/connection arm은 q003·q010·q013 각 3회로 시작하고, 차이가 0~1이면 q006·q018을 추가해 arm당 5회로 확장한다.
- 5쌍 후 candidate strict 성공 수가 더 많고 parse/schema/DB/evidence 회귀가 0일 때만 선택한다. 동률은 control이다.
- queue 단계는 동일 q013의 순차 4회와 concurrency=2 두 wave를 비교하는 진단이며 운영 설정으로 승격하지 않는다.
- 최종 14문항 모두 Query Frame ≤5초, functional+DB exact, 계약 오류 0, timeout/429/5xx 0이어야 runtime candidate다.

## 5. Qualification과 최종 판정

- Strict Success: 8/14 (57.1%)
- HTTP 200 응답: 9/14; 그중 Functional Success: 8/9
- 완료 응답 latency: min 2.6576초 / median 3.3461초 / max 4.7718초
- 안전 ABSTAIN: q006
  - ABSTAIN_ENTITY_NOT_FOUND 1건
- HTTP 429: q011, q012, q013, q017, q018
-  PostgreSQL deterministic 경로: Gold exact 14/14

최종 qualification 판정은 **FAIL — 재설계 필요**다. 정상 응답 9건은 모두 5초 이내였지만 q006의 의미/엔티티 해석 실패와 연속 429 5건 때문에 14/14 운영 통과 조건을 충족하지 못했다. 이번 표본에서는 prompt·token·schema·connection 변경이 5초 성공률을 높인다는 근거가 없으며, endpoint rate limit/queue 정책을 확인한 후 실험 간 cooldown을 둔 재검증이 필요하다.



## 6. 재현 파일

- 실행 코드: `evaluate_query_frame_latency.py`
- 호출 단위 원자료: `results/query_frame_latency_raw.jsonl`
- 단계 집계·선택 구성: `results/query_frame_latency_metrics.json`
- 기존 RDB E2E 기준 결과: `results/metrics.json`



## 다음 Action Items

1.  API 429 원인 분리

- 429 응답의 rate-limit 관련 header 확인
- CLOVA Studio 콘솔의 호출량·동시성·분당 제한 확인
- 단계 사이 cooldown을 둔 실행 스케줄 설계
- 동일 API key와 별도 key를 endpoint 분리로 오해하지 않도록 구분

  2. q006 기능 실패 단독 분석

- HCX가 생성한 entity text·role·match mode 확인
- ABSTAIN_ENTITY_NOT_FOUND가 Query Frame 오류인지, 엔티티 정규화 오류인지 분리

  

  3. Cooldown 적용 재qualification

- API 제한 조건을 확인한 후  재실험
  -   - 동시성 1
  -   - 자동 retry 없음
  -   - 호출 간 고정 cooldown
  -   - 14문항 각 1회 스모크
  -   - 통과 가능성이 확인되면 문항별 3회 안정성 검증
  -   - 실패 문항만 최대 5회 확장

  4. 운영 설정 승격 조건 유지

- 다음 조건을 모두 만족하기 전에는 src/**에 실험 설정을 반영하지 않습니다.
  -   - Valid Query Frame ≤5초: 14/14
  -   - Functional + DB Gold exact: 14/14
  -   - evidence/응답 계약 오류: 0
  -   - timeout/429/5xx: 0
  -   - q006 엔티티 실패 해결

  