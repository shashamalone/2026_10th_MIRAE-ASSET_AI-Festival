# Team Development Guide

팀원이 같은 방식으로 이슈를 만들고 브랜치를 나누고 PR을 검토하기 위한 내부 규칙입니다. Python runtime/test는 3.10+ 기준입니다.

## 1. 브랜치 전략 (GitFlow)

```
feature/*, fix/*  →  dev  →  main
```

- `main`, `dev` 직접 커밋 금지. 모든 변경은 **PR + 리뷰 승인 1건 이상** 후 머지.
- `dev`에서 작업 브랜치를 분기하고, 별도 합의가 없으면 PR 대상은 `dev`.
- `main`은 안정 기준 브랜치.

### 브랜치 이름

- 형식: `<type>/<short-name>` — `feature`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`
- 예: `feature/auth-token-refresh`, `fix/login-timeout`
- 소문자+하이픈 사용, 한 브랜치=한 목적.

## 2. Issue Rules

작업 시작 전 가능한 한 Issue를 먼저 만듭니다. 형식은 `.github/ISSUE_TEMPLATE/{bug,feature,task}.yml`.

- 제목 prefix는 `[Bug]` / `[Feature]` / `[Task]` 셋 중 하나만 사용. 세부 성격은 제목이 아니라 label로 구분합니다.
  - `[Bug]` → `bug`, `[Feature]` → `enhancement`, `[Task]` → 필요 시 `chore`/`refactor`/`documentation`/`test`/`ci`를 함께 부여
- 본문: 문제/배경, 목표, 범위, 검증 가능한 완료 조건(체크리스트)을 적고, 관련 자료·의존성·차단 요소가 있으면 함께 남깁니다.

## 3. 커밋 메시지

`타입: 설명` (한국어), 타입은 `feat`·`fix`·`docs`·`chore`·`refactor`·`test` 중 하나.


예) `feat: 스트레스 시나리오 금리 충격 추가`

작업 흐름: Issue 생성 → `dev`에서 브랜치 생성 → 작업/검증 → PR → `dev` 병합 → 필요 시 `main` 반영.

## 4. Pull Request

- PR 입력 형식은 `.github/PULL_REQUEST_TEMPLATE.md` 사용.
- 제목은 커밋과 동일한 타입 prefix (`feat: add auth token refresh`).
- 관련 이슈는 `Closes #번호` / `Refs #번호`로 연결.
- 본문은 diff 나열이 아니라 결과 중심으로 요약하고, 리뷰어가 봐야 할 부분은 `Review Focus`에 명시.

### PR 전 체크리스트

- `python scripts/run_graph.py --auto-approve` 완주
- `pytest` 통과
- `.env`·API 키 등 비밀 정보 미포함
- 커밋 메시지 컨벤션 준수

## 5. Validation

코드·설정·스키마·동작 변경이 있는 PR에는 검증 내용을 남깁니다.

- 실행한 테스트 명령 또는 수동 확인 절차 기록 (미실행 항목은 `Not run: 이유`)
- 문서 변경만 있으면 그 사실을 명시
- 위험이 있으면 영향 범위와 롤백 방법도 기록
- Python 검증은 3.10+ 인터프리터 기준

예: `pytest backend/tests` - pass / `Not run: e2e tests - frontend 화면 없음`

## 6. Review &amp; Merge

- 작성자가 PR 설명·검증 내용을 먼저 채우고, 리뷰어는 목적/범위/검증/위험도를 함께 확인합니다.
- 리뷰 코멘트는 병합 전 반영하거나 사유를 남깁니다.
- 브랜치 반영은 PR을 통해서만 (특별한 사유 없는 한).

## 7. Scope Control

한 PR = 하나의 목적. 기능 추가 + 리팩터링 + 문서 정리 + 무관한 fix를 한 PR에 섞지 않습니다. 범위가 커지면 Issue/PR을 나눕니다.