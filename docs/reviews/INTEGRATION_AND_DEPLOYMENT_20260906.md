# 통합·배포 준비 기록 (2026-09-06)

## 통합 기준

- 답변·Q22 수정 기준: `9f7c967` (`T-148`→`T-149`→`T-150` 포함)
- 팀 로컬 `dev`: `65ba853`
- 원격 `origin/dev`: `a10649e`
- `origin/dev`는 선행 병합 `ae711d2`를 통해 답변 수정 계열에 이미 포함돼 있다.
- 이번 통합은 팀 로컬 `dev`의 7개 후속 커밋을 병합한다.

## 병합한 팀 작업

- 평가용 `GET /answer` API 서버와 계약 테스트
- ETF 편입내역 문서 provenance 인덱스·조회 모듈
- 답변 근거에 편입내역 문서명·기준일·URL 연결
- Graph triple count의 HTTP/store 이중 계상 수정
- 속성 저장소 매핑·답변불가 규칙·공식 질의 커버리지 문서와 생성기
- `.env` 시크릿 제외 및 제출용 README

`src/agent/nodes.py` 충돌은 다음을 모두 보존하도록 수동 해결했다.

- 최신 답변 표면 규칙: 물리 컬럼·단계 ID 미노출, 중복 사유 묶기, dict형 서술 제거
- 팀원 provenance 연결: Graph 편입 행을 문서 사이드카와 대조
- provenance 표시는 내부 태그 `[Graph:출처]` 대신 `편입내역 문서 근거`로 사용자 친화화

## Python 버전

현재 회귀 검증은 사용자의 로컬 Python 3.13으로 수행한다. README는 특정 3.11만 요구하지 않고 `3.11 이상`, 현재 검증 버전 `3.13`으로 정정했다.

## Claude tester 명령 확인

확인한 mailbox 명령:

- `fce4dbb7-8782-4e34-944f-2ed548194e74`: 답변 문구 3개, 동일 사유 묶기, 내부 단계·컬럼 제거, `retrieved_context` 사용자화, Q22 복구, 중복 유료 실행 금지.
- `e5a2149c-1e70-49cd-b072-3cb152b2a55e`: T-146 원격 Graph 재적재 STOP. Q22는 기존 Graph에 이미 데이터가 있고 원인은 이름·의도 해소이므로, 답변 계층→Q22→dev 병합·배포를 먼저 하고 T-146은 마감 후로 연기.

해당 우선순위에 따라 원격 Graph에는 쓰기 작업을 하지 않았다. SSH 비밀번호 입력 전에 중단해 원격 상태는 변경되지 않았다.

## Graph 재적재 상태

원격 Graph는 현재 2026-07-10 편입 스냅샷이다. 재적재용 로컬 후보는 T-146에서 이미 생성·검증했다.

- 커밋: `ef30473`
- 후보 번들: `ontology-holdings-20260821-de30afc2bcd4`
- 대상 상품: 723/725
- 편입 관계: 47,244건
- 기준일: 2026-08-21
- 검증: 205 passed, 23 subtests passed

그러나 마감 전 원격 cutover는 기존 Q24 정상 경로를 깨뜨릴 위험이 있고 Q22 해결의 선행조건도 아니므로, Claude tester의 STOP 지시를 유지한다. 이 문서 작성 시점에 원격 재적재 완료라고 표시하지 않는다.

## 배포 전 검증

- catalog SQL·답변 계약
- Graph runtime
- KB config path
- `/answer` API 계약
- holdings provenance 무결성·조회·degraded 동작
- 통합 커밋에 `origin/dev`와 로컬 `dev`가 모두 조상인지 확인

배포는 이 통합 커밋 검증 뒤 별도 작업으로 수행하고, 배포 SHA·health·단건 smoke 결과를 추가 기록한다.
