# Team Development Guide

이 문서는 팀 개발 규칙을 설명합니다.
외부 기여 안내가 아니라, 팀원이 같은 방식으로 이슈를 만들고 브랜치를 나누고 PR을 검토하기 위한 기준입니다.

현재 저장소의 Python runtime/test 코드는 Python 3.10+를 최소 실행 버전으로 사용합니다.

## 1. **브랜치 전략**

GitFlow를 따릅니다.

```
feature/*, fix/*  →  dev  →  main

```

- `main` 직접 커밋은 금지합니다. 모든 변경은 **PR + 최소 1명 리뷰 승인** 후 머지합니다.
- 작업은 `feature/*`(신규 기능), `fix/*`(버그 수정) 등 목적별 브랜치에서 진행합니다.
- 기본 개발 브랜치는 `dev`입니다.
- `main`은 안정 기준 브랜치로 사용합니다.
- 일반 작업은 `dev`에서 분기한 작업 브랜치에서 진행합니다.
- 별도 합의가 없으면 PR 대상 브랜치는 `dev`입니다.
- `main`, `dev`에 직접 커밋하지 않습니다.

## 2. Issue Rules

작업 시작 전 가능한 한 Issue를 먼저 만듭니다.

이 저장소는 다음 이슈 타입을 사용합니다.

- `[Bug]`: 재현 가능한 결함, 회귀, 크래시, 예상과 다른 동작
- `[Feature]`: 사용자 가치가 있는 기능 추가 또는 개선
- `[Task]`: 유지보수, 리팩터링, 문서, 설정, 조사, 정리 작업



### 라벨 운영 원칙

- 이슈 제목 prefix는 `[Bug]`, `[Feature]`, `[Task]` 세 가지만 사용합니다.
- 세부 성격은 제목이 아니라 label로 구분합니다.
  - `[Bug]` 이슈는 기본적으로 `bug` label을 사용합니다.
  - `[Feature]` 이슈는 기본적으로 `enhancement` label을 사용합니다.
  - `[Task]` 이슈는 필요에 따라 `chore`, `refactor`, `documentation`, `test`, `ci` 같은 label을 함께 사용합니다.
- 하나의 이슈가 여러 성격을 가지면 label을 복수로 붙일 수 있습니다.
  - 예: `[Task] API 사용법 문서 정리` + `documentation`
  - 예: `[Task] 로그인 서비스 테스트 보강` + `test`
  - 예: `[Task] GitHub Actions 워크플로 정리` + `ci`

### Issue 작성 원칙

- 제목은 타입 prefix를 사용합니다.
  - 예: `[Bug] 로그인 실패`
  - 예: `[Feature] 토큰 자동 갱신`
  - 예: `[Task] 백엔드 설정 정리`
- 본문에는 문제 또는 배경, 목표, 범위, 완료 조건을 구체적으로 적습니다.
- 완료 조건은 검증 가능한 체크리스트로 작성합니다.
- 관련 자료, 의존성, 차단 요소가 있으면 함께 남깁니다.
- GitHub 이슈 입력 형식은 `.github/ISSUE_TEMPLATE/{bug,feature,task}.yml`을 사용합니다.



## **3. 커밋 메시지**

한국어로 `타입: 설명` 형식을 사용합니다. 타입은 다음 중 하나입니다.

`feat` · `fix` · `docs` · `chore` · `refactor` · `test`

- 예) `feat: 스트레스 시나리오 금리 충격 추가`

기본 흐름:

1. Issue 생성 또는 기존 Issue 확인
2. `dev`에서 작업 브랜치 생성
3. 작업 및 검증 수행
4. PR 생성 후 리뷰
5. `dev`로 병합
6. 필요 시 `main` 반영

## 4. Branch Naming

브랜치 이름은 작업 성격과 목적이 드러나게 작성합니다.

### 권장 형식

- `feature/<short-name>`
- `fix/<short-name>`
- `chore/<short-name>`
- `docs/<short-name>`
- `refactor/<short-name>`
- `test/<short-name>`
- `ci/<short-name>`

예

- `feature/auth-token-refresh`
- `fix/login-timeout`
- `chore/update-env-example`



### 규칙

- 소문자와 하이픈(`-`)을 사용합니다.
- 한 브랜치에는 한 가지 목적의 변경만 담습니다.
- 관련 없는 수정은 같은 브랜치에 섞지 않습니다.

## 5. Pull Request Rules

모든 변경은 Pull Request로 제출합니다.

### PR 작성 원칙

- PR 제목은 변경 성격이 드러나는 prefix를 사용합니다.
  - 예: `feat: add auth token refresh`
  - 예: `fix: handle expired access token`
  - 예: `chore: update backend env defaults`
- PR 본문은 저장소 템플릿을 사용합니다.
- 관련 이슈는 `Closes #번호` 또는 `Refs #번호`로 연결합니다.
- 변경 사항은 diff 나열이 아니라 결과 중심으로 요약합니다.
- 리뷰어가 특히 봐야 할 부분은 `Review Focus`에 적습니다.
- PR 입력 형식은 `.github/PULL_REQUEST_TEMPLATE.md`를 사용합니다.

### **PR 전 체크리스트**

PR을 올리기 전 로컬에서 아래를 확인해 주세요. (자세한 항목은 PR 템플릿에 있습니다.)

- 그래프 실행: `python scripts/run_[graph.py](http://graph.py) --auto-approve` 완주
- 자동 테스트: `pytest` 통과
- `.env` · API 키 · 비밀번호 등 비밀 정보를 커밋에 포함하지 않음
- 커밋 메시지가 `타입: 설명` 컨벤션을 따름

## 6. Validation

코드, 설정, 스키마, 동작 변경이 있는 PR에는 검증 내용을 반드시 남깁니다.

검증 기록 원칙:

- 실행한 테스트 명령 또는 수동 확인 절차를 적습니다.
- 실행하지 않은 검증이 있으면 `Not run`에 이유를 적습니다.
- 문서 변경만 있으면 문서 변경임을 명시합니다.
- 위험이 있으면 영향 범위와 롤백 방법을 함께 적습니다.
- Python runtime/test 검증은 3.10+ 인터프리터 기준으로 실행합니다.

예:

- `pytest backend/tests` - pass
- `npm run build` - pass
- `Not run: e2e tests - frontend 화면이 아직 없음`



## 7. Review and Merge

- 작성자는 PR 설명과 검증 내용을 먼저 채웁니다.
- 리뷰어는 변경 목적, 범위, 검증, 위험도를 함께 봅니다.
- 리뷰 코멘트는 병합 전에 반영하거나 사유를 남깁니다.
- 특별한 사유가 없으면 PR을 통해서만 브랜치에 반영합니다.



## 8. Scope Control

한 PR에는 하나의 목적만 담는 것을 원칙으로 합니다.

좋은 예:

- 인증 토큰 갱신 로직 추가
- 이슈 템플릿 구조 개선
- 백엔드 프로젝트 설정 파일 정리

좋지 않은 예:

- 기능 추가 + 대규모 리팩터링 + 문서 정리 + unrelated fix를 한 PR에 혼합

변경 범위가 커지면 Issue와 PR을 나눕니다.

