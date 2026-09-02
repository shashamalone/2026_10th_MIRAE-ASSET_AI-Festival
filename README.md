# 🏆 금융상품 Agent (Financial Product Analyst)

> 정형 금융상품 데이터를 Agent가 스스로 탐색·연산하고, 근거에 기반해 답변하는 Agent RAG·QA 구현

## 📌 프로젝트 개요

- **프로젝트명:** 금융상품 Agent (Financial Product Analyst)
- **개발기간:** [YYYY.MM.DD] ~ [YYYY.MM.DD] ([총 N주/개월])
- **팀원 구성:** [총 3명] (BE 1인, Agent 2인)
- **주최:** 제10회 미래에셋증권 AI Festival
- **필수 사항:** 🔒 LLM은 **HyperCLOVA X만 사용 가능** (다른 LLM 사용 시 평가대상 제외)



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

---

## ⚙️ 주요 기능

### Agent의 4대 필수 구성요소

1. **정형·비정형 데이터 분석 &amp; 정제 — 상품 도메인 특화 Ontology**
  - [Parsing] PDF, PPT 등 데이터를 Markdown으로 변환
    - [Ontology] 데이터를 종합하여 상품별 LLM 가이드라인(온톨로지) 제작
2. **금융상품 KnowledgeBase — RDB + Vector + Graph**
  - [Extraction] 정제된 데이터를 바탕으로 지식 추출
    - [EntityResolution] 불필요·모호한 데이터의 판별 및 정리
3. **Intent Analysis &amp; Retrieval Engine — 질의 의도 분석과 검색 엔진**
  - [NL2SQL] 자연어 입력을 분석해 질의어(SQL)로 변환
    - [Retrieval] 우선순위·탐색 순서를 효과적으로 조정
4. **Answer Generator — 근거 기반 답변 생성**
  - [근거기반] 검색된 Evidence를 기반으로 정확한 답변 생성
    - [환각 방지] 데이터에 없는 내용은 추측하지 않음

### RDB vertical slice (현재 구현 범위)

데이터 구축 현행과 전달용 정의서는 아래 문서를 기준으로 한다.

- [현재 데이터 구축 프로세스와 DB 구조](docs/docs_data_layer/CURRENT_DATA_BUILD_STRUCTURE.md)
- [DB Table 정의서 v1.0](docs/docs_data_layer/TABLE_DEFINITION_V1_0.md)

현재 RDB와 Schema Vector는 PostgreSQL·pgvector 빌더가 구현돼 있다. Graph는 TBox/ABox
TTL 생성·검증 단계이며 pyoxigraph runtime은 아직 구현되지 않았다.

평가 질문 중 RDB만으로 답할 수 있는 14문항(`q001~q003`, `q005~q013`,
`q017~q018`)은 다음 경로로 실행한다.

`HyperCLOVA X QueryFrame → verified metadata grounding → deterministic validation → LogicalPlan → constrained PostgreSQL SELECT → evidence 응답`

- QueryFrame은 의미 후보이며 SQL 컬럼·조인의 권위가 아니다. 실제 매핑은
`metadata/schema_bindings.json`과 `metadata/business_rules.json`으로 제한한다.
- 존재하지 않는 등급, 미래 확정값, 도메인 위반, 완전일치 상품 부재 및 실행 오류는
추측하지 않고 `ABSTAIN`(`확인할 수 없음`)한다.
- 응답 필드는 `question_id`, `question`, `retrieved_context`, `think_trace`, `answer`로 고정한다.
- 이 단계에서는 Graph/Vector 검색과 자유 생성 NL2SQL을 사용하지 않는다.

```bash
python3 src/kb/build_schema_catalog.py --check
python3 script/test_rdb_vertical_slice.py
python3 script/test_rdb_vertical_slice.py --db
```



### 실행방법

```
python3 -c 'from agent.agent_core import ask; print(ask("VOO의 정식 상품명과 총보수를 알려줘"))'
```

- 하
  - 현대해상화재보험7(후)(콜/후)의 채권 종류, 발행사, 신용등급, 만기구분, 듀레이션을 알려줘. 원본 등급값과 온톨로지 분류값을 함께 제시해줘.
  - AA- 이상이면서 잔존기간 3년 이하인 회사채를 매수수익률 순으로 보여줘
- 중
  - 우리반도체BIG2플러스의 C-P와 C-Pe 클래스가 동일한 모펀드의 클래스인지 확인하고, 클래스별 종목번호·판매 여부·순자산·수익률을 비교해줘. 동일 펀드 판정에 사용한 대표종목번호를 근거로 제시해줘.
- 상
  - 최근 6개월 동안 우주항공 테마와 연결된 이력이 있는 ETF를 정리해줘. 현재 편입 관계와 단순 뉴스 언급을 구분하고, ETF→편입기업→산업/테마→근거문서 경로, 사건일, 문서명과 인용 근거를 제시해줘.



---

## 🧑‍💻 개발 환경 및 기술 스택

### AHyperCLOVA X (필수, 유일 허용 LLM)

### Management Tool

Git  

&lt;/br&gt;&lt;/br&gt;  

---

## 🚧 설계

### 📂 BackEnd Directory

[백엔드 폴더 구조를 텍스트로 붙여넣으세요]



---



&nbsp;

## 📋 Task 관리

Agent의 4대 필수 구성요소를 기준으로 task를 구성합니다.

### 1. 정형·비정형 데이터 분석 &amp; 정제 — 상품 도메인 특화 Ontology (`feature/ontology-definition`)

- **필수 제출 요건:**  
  - 주최 측 Git 레포지토리에 소스 코드와 함께 도메인별 온톨로지가 필수로 포함되어야 함.  
  - 포맷이 반드시 `.ttl`일 필요는 없으나, 온톨로지 규칙이 정의된 파일이 소스 내에 존재해야 함.
- **데이터 정합성 확보의 시작점:**  
  - 주최 측 RDB 데이터에는 'ETF 구성 종목 정보' 등이 빠져 있음. 비정형 데이터에서 온톨로지를 활용해 관계를 추출하는 작업이 최우선으로 선행되어야 함.  
  - 온톨로지라는 설계도가 Git에 먼저 커밋되어야 이후 지식 그래프 구축과 데이터 적재가 가능함.

### 2. 금융상품 KnowledgeBase — RDB + Vector + Graph (`feature/knowledge-base`)

- Task 1에서 정의한 온톨로지를 기반으로 RDB·Vector·Graph 세 계층에 데이터를 적재하여 지식 그래프를 구축.

### 3. Intent Analysis &amp; Retrieval Engine + 답변 검증 레이어 (`feature/query-validation`)

- **감점 요인 원천 차단:**  
  - 가장 치명적인 감점 요인은 '데이터로 확인 불가능한 정보에 대해 임의로 대답하는 것'(예: 존재하지 않는 신용등급, 기준일 이후의 상품 등)과 '근거 없는 수익률 전망'임.
- **기능 구현:**  
  - LLM(하이퍼클로바X)에 질문을 바로 던지기 전에, 입력된 질문이 기준일(2026-07-11) 이전 데이터 범주에 존재하는지, 없는 상품을 묻고 있는지 검증하여 "확인할 수 없음"을 반환하는 밸리데이션 로직을 최초 파이프라인에 이식해야 함.

### 4. Answer Generator &amp; API Response 규격화 (`feature/api-response-schema`)

- **평가 기준 충족:** API 호출 시 반드시 정답의 근거(출처)가 포함되어 응답해야 함.  
- **기능 구현:** 쿼리 검색 결과와 원문 데이터 청크 정보를 매핑하여 `evidence` 필드를 포함해 리턴하는 API 인터페이스 규격을 최우선으로 통일해 두어야, 이후 프론트엔드나 평가 서버 연동 시 응답 지연(15초 초과) 문제를 예방하기 수월함.



---

## 😎 팀원 소개


| [역할]                  | [역할]                  | [역할]                  |
| :---------------------: | :---------------------: | :---------------------: |
| [팀원 1](GitHub 프로필 링크) | [팀원 2](GitHub 프로필 링크) | [팀원 3](GitHub 프로필 링크) |


