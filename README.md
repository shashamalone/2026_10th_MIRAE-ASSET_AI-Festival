# 🏆 금융상품 Agent (Financial Product Analyst)

> 정형 금융상품 데이터를 Agent가 스스로 탐색·연산하고, 근거에 기반해 답변하는 Agent RAG·QA 구현

## 데이터 플랫폼 v2 (2026-08-24)

현재 데이터 정본은 정상 XLSX 8개로 구성된 `financial-products-2026-08-24`이며,
운영 경로는 PostgreSQL 17 + pgvector + Oxigraph + 읽기전용 FastAPI다. 과거
`2026-07-11` CSV를 설명하는 문서와 스크립트는 재현용 레거시 자료이며 v2 빌드에
사용하지 않는다.

```bash
python script/build_catalog_v2.py --check
python script/build_data_platform_v2.py --check
python script/build_vectors_v2.py --check
python script/validate_data_platform_v2.py
```

- 데이터 계약·현황: [`docs/docs_data_layer/CURRENT_DATA_BUILD_STRUCTURE.md`](docs/docs_data_layer/CURRENT_DATA_BUILD_STRUCTURE.md)
- 전체 테이블 정의: [`docs/docs_data_layer/TABLE_DEFINITION_V2_0.md`](docs/docs_data_layer/TABLE_DEFINITION_V2_0.md)
- 구현·운영 규약: [`docs/docs_data_layer/DATA_PLATFORM_V2_IMPLEMENTATION.md`](docs/docs_data_layer/DATA_PLATFORM_V2_IMPLEMENTATION.md)
- 제자리 배포·롤백: [`deploy/README_V2.md`](deploy/README_V2.md)

</br></br>
## 📌 프로젝트 개요

* **프로젝트명:** 금융상품 Agent (Financial Product Analyst)
* **개발기간:** [YYYY.MM.DD] ~ [YYYY.MM.DD] ([총 N주/개월])
* **팀원 구성:** [총 3명] (BE 1인, Agent 2인)
* **주최:** 제10회 미래에셋증권 AI Festival
* **필수 사항:** 🔒 LLM은 **HyperCLOVA X만 사용 가능** (다른 LLM 사용 시 평가대상 제외)

</br></br>

## 🎯 프로젝트 배경

주최 측 RDB 데이터에는 'ETF 구성 종목 정보' 등 관계형 정보가 빠져 있어, "삼성전자 포함된 ETF 알려줘" 같은 질문에 정형 데이터만으로는 답할 수 없습니다.

이를 해결하기 위해 비정형 데이터에서 온톨로지를 활용해 관계를 추출하고, 근거(Evidence) 없이는 답변하지 않는 Agent를 구현하는 것이 핵심 목표입니다. 특히 데이터로 확인 불가능한 정보(존재하지 않는 신용등급, 기준일 이후 상품 등)에 대한 임의 답변과 근거 없는 수익률 전망은 가장 치명적인 감점 요인이므로, 검증·근거 제시 로직을 파이프라인 전 구간에 내재화합니다.

**예상 사용자 질의 예시**
> "미국 증시에 상장된 주식형 ETF 중에서 총보수가 낮고 운용 규모가 큰 상품 3개만 비교해 주세요."

**출력 예시**
- **결론:** 조건에 부합하는 상품 3종
- **비교 항목:** 상품별 총보수 / 순자산(AUM) / 기초지수 비교
- **근거:** 해외ETF마스터, 데이터 기준일

**평가 포인트:** 정형 데이터 · 비교·연산 · 조건 해석 · 근거 표시

</br></br>

## ⚙️ 주요 기능

Agent의 4대 필수 구성요소입니다.

1. **정형·비정형 데이터 분석 & 정제 — 상품 도메인 특화 Ontology**
    * [Parsing] PDF, PPT 등 데이터를 Markdown으로 변환
    * [Ontology] 데이터를 종합하여 상품별 LLM 가이드라인(온톨로지) 제작

2. **금융상품 KnowledgeBase — RDB + Vector + Graph**
    * [Extraction] 정제된 데이터를 바탕으로 지식 추출
    * [EntityResolution] 불필요·모호한 데이터의 판별 및 정리

3. **Intent Analysis & Retrieval Engine — 질의 의도 분석과 검색 엔진**
    * [NL2SQL] 자연어 입력을 분석해 질의어(SQL)로 변환
    * [Retrieval] 우선순위·탐색 순서를 효과적으로 조정

4. **Answer Generator — 근거 기반 답변 생성**
    * [근거기반] 검색된 Evidence를 기반으로 정확한 답변 생성
    * [환각 방지] 데이터에 없는 내용은 추측하지 않음

</br></br>

---

## 🧑‍💻 개발 환경 및 기술 스택

### AI

HyperCLOVA X (필수, 유일 허용 LLM)

### Management Tool

Git

</br></br>

## 🚧 설계

### 📂 BackEnd Directory
```
[백엔드 폴더 구조를 텍스트로 붙여넣으세요]
```

</br></br></br>

---

## 📋 Task 관리

Agent의 4대 필수 구성요소를 기준으로 task를 구성합니다.

### 1. 정형·비정형 데이터 분석 & 정제 — 상품 도메인 특화 Ontology (`feature/ontology-definition`)

- **필수 제출 요건:**
  - 주최 측 Git 레포지토리에 소스 코드와 함께 도메인별 온톨로지가 필수로 포함되어야 함.
  - 포맷이 반드시 `.ttl`일 필요는 없으나, 온톨로지 규칙이 정의된 파일이 소스 내에 존재해야 함.
- **데이터 정합성 확보의 시작점:**
  - 주최 측 RDB 데이터에는 'ETF 구성 종목 정보' 등이 빠져 있음. 비정형 데이터에서 온톨로지를 활용해 관계를 추출하는 작업이 최우선으로 선행되어야 함.
  - 온톨로지라는 설계도가 Git에 먼저 커밋되어야 이후 지식 그래프 구축과 데이터 적재가 가능함.

### 2. 금융상품 KnowledgeBase — RDB + Vector + Graph (`feature/knowledge-base`)

- Task 1에서 정의한 온톨로지를 기반으로 RDB·Vector·Graph 세 계층에 데이터를 적재하여 지식 그래프를 구축.

### 3. Intent Analysis & Retrieval Engine + 답변 검증 레이어 (`feature/query-validation`)

- **감점 요인 원천 차단:**
  - 가장 치명적인 감점 요인은 '데이터로 확인 불가능한 정보에 대해 임의로 대답하는 것'(예: 존재하지 않는 신용등급, 기준일 이후의 상품 등)과 '근거 없는 수익률 전망'임.
- **기능 구현:**
  - LLM(하이퍼클로바X)에 질문을 바로 던지기 전에, 입력된 질문이 외부 근거 상한(2026-08-24)과 상품별 실질 기준일 범주에 존재하는지, 없는 상품을 묻고 있는지 검증하여 "확인할 수 없음"을 반환하는 밸리데이션 로직을 최초 파이프라인에 이식해야 함.

### 4. Answer Generator & API Response 규격화 (`feature/api-response-schema`)

- **평가 기준 충족:** API 호출 시 반드시 정답의 근거(출처)가 포함되어 응답해야 함.
- **기능 구현:** 쿼리 검색 결과와 원문 데이터 청크 정보를 매핑하여 `evidence` 필드를 포함해 리턴하는 API 인터페이스 규격을 최우선으로 통일해 두어야, 이후 프론트엔드나 평가 서버 연동 시 응답 지연(15초 초과) 문제를 예방하기 수월함.

</br></br>

---

## 😎 팀원 소개
| [역할] | [역할] | [역할] |
| :---: | :---: | :---: |
| [팀원 1](GitHub 프로필 링크) | [팀원 2](GitHub 프로필 링크) | [팀원 3](GitHub 프로필 링크) |
