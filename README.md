# 금융상품 Agent — Financial Product Analyst

미래에셋 AI Festival 2026 제출작. 정형 금융상품 데이터(국내채권·국내ETF·해외ETF·공모펀드)에 대해 자연어 질의를 받아 **RDB · GraphDB · VectorDB를 상황에 맞게 라우팅**하고, 검색된 근거를 인용해 답변한다.

핵심 설계는 **온톨로지를 문서가 아니라 런타임 통제 계층으로 쓰는 것**이다. 온톨로지가 "무엇을 물을 수 있는가"를 정의하고, live 스키마 스냅샷이 "실제로 무엇이 존재하는가"를 정의한다. 두 정본을 분리하고 계약으로 묶어, 존재하지 않는 테이블·컬럼을 모델이 지어내는 경로를 구조적으로 차단한다.

---

## 요구 환경

| 항목 | 버전 |
|---|---|
| Python | **3.11** (평가 실행 기준) |
| OS | Windows / Linux / macOS |

의존성은 `requirements.txt`에 고정되어 있다.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

주요 패키지: `langgraph==1.2.11`, `langchain-naver==0.1.1`, `pyoxigraph==0.5.10`, `rdflib==7.6.0`, `psycopg2-binary==2.9.12`, `requests==2.34.2`

---

## 환경 변수

`.env.example`을 복사해 값을 채운다. `.env`는 커밋 대상이 아니다.

```bash
cp .env.example .env
```

| 변수 | 필수 | 설명 |
|---|---|---|
| `CLOVA_API_KEY` | ✅ | NCP CLOVA Studio API 키. 의도 분석·답변 생성에 사용. `CLOVASTUDIO_API_KEY`도 인식 |
| `CLOVA_EMBEDDING_MODEL` | | 임베딩 모델. 기본 `bge-m3` (1024차원). **VectorDB 적재 시 쓴 모델과 반드시 일치** |
| `RDB_API_BASE_URL` | | RDB 조회용 SQL API. `POST /db/sql`에 `text/plain`으로 쿼리 전송 |
| `RDB_API_TIMEOUT` | | 기본 30초 |
| `DATABASE_URL` 또는 `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` | | VectorDB(pgvector) 직접 연결. 둘 중 한 방식만 |
| `VECTOR_SCHEMA` | | 기본 `vec`. 청크 테이블은 `vec.document_chunk` |
| `OXIGRAPH_FALLBACK_ENDPOINT` | | GraphDB SPARQL 엔드포인트. **경로까지 포함**해야 한다 (예: `http://<host>:55001/query`) |
| `OXIGRAPH_LOCAL_STORE_PATH` | | 로컬 Oxigraph store 디렉터리를 쓸 경우 |
| `OXIGRAPH_TIMEOUT` | | 기본 3초. 응답 시간 목표 때문에 짧게 유지 |

### GraphDB 연결 순서

`OxigraphClient`는 3단계로 폴백한다. 먼저 성공하는 것을 쓴다.

```
OXIGRAPH_REMOTE_STORE_PATH   파일 직접 (read-only)
  → OXIGRAPH_LOCAL_STORE_PATH  파일 직접 (read-only)
    → OXIGRAPH_FALLBACK_ENDPOINT  HTTP (표준 SPARQL 1.1 Protocol)
```

HTTP 경로는 표준 SPARQL 1.1을 말하는 Oxigraph 서버를 전제한다. `Content-Type: application/sparql-query`로 POST하고 `application/sparql-results+json`을 받는다.

---

## 실행

`src/`가 import 루트다. `PYTHONPATH`에 반드시 포함시킨다.

### 단건 질의

```bash
# Linux/macOS
PYTHONPATH=src python -c "
from agent.graph import app
r = app.invoke({'question': 'VOO의 정식 상품명과 총보수를 알려줘', 'question_id': 'Q-001'})
print(r['answer'])
"
```

```powershell
# Windows PowerShell
$env:PYTHONPATH='src'; $env:PYTHONUTF8='1'
python -c "from agent.graph import app; print(app.invoke({'question':'VOO의 정식 상품명과 총보수를 알려줘','question_id':'Q-001'})['answer'])"
```

**Windows에서는 `PYTHONUTF8=1`을 반드시 설정한다.** 기본 CP949 콘솔에서 일부 오류 경로의 출력이 `UnicodeEncodeError`를 일으킨다.

선택 인자:

| 키 | 기본 | 설명 |
|---|---|---|
| `max_sql_retries` | 3 | SQL 실행 실패 시 재시도 횟수 |

### 파이프라인 구조 시각화

```bash
PYTHONPATH=src python src/agent/graph.py     # mermaid 다이어그램 출력
```

### 연결 확인

```bash
PYTHONPATH=src python -c "
from agent.graph_logic.graph_engine import triple_count
print('graph triples:', triple_count())
"
```

---

## 평가용 API 서버

주최측 규격(`GET /answer`)을 그대로 구현한 HTTP 서버다. 표준 라이브러리만 쓴다 — 평가 기간에 서버에서 추가 설치가 필요 없도록 한 선택이다.

```bash
PYTHONPATH=src python -m serve_answer                    # 0.0.0.0:8080
PYTHONPATH=src python -m serve_answer --port 80          # 80 포트
```

| 환경변수 | 기본 | 설명 |
|---|---|---|
| `ANSWER_HOST` | `0.0.0.0` | 바인드 주소 |
| `ANSWER_PORT` | `8080` | 포트 |
| `ANSWER_TIMEOUT_SECONDS` | `55` | 문항당 제한 시간. 주최측 권장 60초 대비 여유 |
| `ANSWER_MAX_WORKERS` | `4` | 동시 처리 스레드 |

### 요청 / 응답

```bash
curl -s "http://<host>/answer?question_id=Q-001&question=$(python -c "
import urllib.parse,sys; print(urllib.parse.quote('VOO의 총보수를 알려줘'))")"
```

```json
{
  "question_id": "Q-001",
  "question": "VOO의 총보수를 알려줘",
  "retrieved_context": "PREF02N001 해외ETF마스터 · 2026-08-24",
  "think_trace": "조건 파싱 → 라우팅(RDB 단독) → 필터 → 정렬",
  "answer": "총보수 0.03%인 ... (근거: PREF02N001)"
}
```

### 동작 보장

**어떤 경우에도 200 + 5필드 JSON을 돌려준다.** 채점자에게 500이나 연결 오류가 가면 그 문항은 무조건 0점이지만, 스키마를 지킨 "확인할 수 없음"은 답변 불가 문항에서 정답 처리된다.

| 상황 | 동작 |
|---|---|
| 정상 질의 | 파이프라인 결과를 5필드로 반환 |
| 확인 불가 질의 | 200 + 동일 스키마 + 답변 불가 사유 |
| 미정의 파라미터 | 무시하고 정상 처리 |
| `question` 누락 | 200 + 입력 안내 |
| 파이프라인 예외 | 200 + `think_trace`에 오류 기록 |
| 제한 시간 초과 | 200 + 초과 사실 명시 |
| 파이프라인 로드 실패 | 서버는 기동하고 답변 불가 모드로 응답 (`/health`가 `degraded`) |
| 알 수 없는 경로 | 404지만 본문은 5필드 JSON |

운영 점검용 `GET /health`도 제공한다(주최측 규격과 무관한 자체 엔드포인트).

### 규격 회귀 테스트

```bash
python test/answer-api/test_serve_answer.py
```

14개 테스트가 위 표의 각 항목과 URL 인코딩 복원, `Content-Type`, 필드 타입을 검증한다.

---

## 평가 하네스

소스를 수정하지 않고 노드·LLM·SQL/SPARQL 호출을 계측한다.

```bash
# 1) 실행 — 문항 × 회차만큼 E2E 수집
PYTHONPATH=src PYTHONIOENCODING=utf-8 \
  python test/pipline-test/latency/run_latency.py --rounds 2

# 2) 채점 — 루브릭 기반 결정론 채점
python test/pipline-test/latency/analyze.py --output-dir artifacts/eval/<run-id>
```

산출물:

| 파일 | 내용 |
|---|---|
| `traces_*.jsonl` | 문항×회차당 원시 trace |
| `analysis_summary.json` | 채점 결과·원인 라벨·지연 지표 |
| `analysis_tables.md` | 요약표 |
| `per_run_eval.jsonl` | 회차별 판정 |

> `--output-dir`를 생략하면 커밋된 정본 산출물을 덮어쓴다. 감사 목적 실행은 반드시 출력 경로를 지정한다.

채점 기준은 `test/pipline-test/golden_set_data_gap_evaluation_rubric.md`가 단일 출처다. 골든셋 정본은 `goldset/golden_answers_20260824.csv`.

---

## 저장소 구조

```
├─ src/
│  ├─ agent/                  파이프라인 (LangGraph)
│  │  ├─ graph.py             StateGraph 조립 + 웨이브 스케줄러
│  │  ├─ state.py             상태 정의 + 병렬 리듀서
│  │  ├─ nodes.py             각 노드 구현 (NL2SQL 수리 루프 포함)
│  │  ├─ plan_query_db.py     Plan & Routing (규칙 우선, LLM 폴백 1곳)
│  │  ├─ intent_guard.py      LLM 구조화 출력의 결정론적 교정
│  │  ├─ prompts.py           프롬프트
│  │  └─ graph_logic/         Graph 질의 생성·오케스트레이션
│  ├─ tools/
│  │  ├─ rdb_schema.py        도메인 카탈로그 (의미의 정본)
│  │  ├─ schema_snapshot.py   live 스키마 스냅샷 (물리 존재의 정본)
│  │  ├─ graph_schema.py      TBox 카탈로그
│  │  └─ vector_search.py     pgvector 검색
│  ├─ infrastructure/
│  │  ├─ graph_db/client.py   Oxigraph 어댑터 (3단계 폴백)
│  │  └─ vector_db/client.py  pgvector 어댑터
│  └─ kb/                     지식베이스 빌더 (적재·검증)
├─ ontology/                  제출 필수 온톨로지 5종
│  ├─ common.ttl              공통 상위 (fp:Product 루트)
│  ├─ bond_kr.ttl             국내채권
│  ├─ etf_kr.ttl              국내 ETF
│  ├─ etf_gl.ttl              해외 ETF
│  └─ fund_pub.ttl            공모펀드
├─ docs_data_layer/
│  ├─ PROPERTY_STORAGE_MAP.md 속성 136개의 저장소·가용성 매핑
│  ├─ ABSTAIN_RULES.md        답변불가 판정 규칙
│  └─ QUERY_COVERAGE_OFFICIAL.md
├─ metadata/                  온톨로지 개념 ↔ 물리 컬럼 바인딩 (선언적)
├─ goldset/                   골든셋 정본
├─ test/                      평가 하네스 + 계약 회귀
├─ script/                    문서 생성기
└─ requirements.txt
```

---

## 파이프라인

```
사용자 질문
  → receive_question
  → analyze_intent      HCX-007 구조화 출력 (Query Frame)
  → verify_intent       결정론적 guard — enum 교정·모순 해소, LLM 재호출 없음
  → plan_query          규칙 기반 라우팅
  → ┌─ rdb_search ─┐
    ├─ graph_search├   의존성 웨이브 스케줄러 (depends_on 기반)
    └─ vector_search┘
  → merge_results
  → generate_answer     근거 기반 생성 / 근거 없으면 ABSTAIN
```

세 검색 엔진은 단순 fan-out이 아니라 `depends_on`을 반영해 웨이브 단위로 실행된다.

| 질의 유형 | 실행 |
|---|---|
| RDB 단독 | 웨이브 1: RDB |
| 서로 무관한 Graph + RDB | 웨이브 1: 동시 실행 |
| Graph → RDB 의존 | 웨이브 1: Graph / 웨이브 2: RDB |
| Graph 체인 → RDB → Vector | 웨이브 1·2·3 순차 |

---

## 온톨로지

네임스페이스 `fp: <http://mafest.ai/product#>`. 도메인 4파일은 `common.ttl`을 `owl:imports` 한다.

| | Class | ObjectProperty | DatatypeProperty |
|---|---:|---:|---:|
| 합계 | 81 | 43 | 89 |

설계 원칙:

1. **단일 루트** — 모든 상품 클래스는 `fp:Product`의 하위. 상품군 추가가 스키마 변경 없이 가능
2. **n-ary 패턴** — 편입관계·시점 가변 수치는 `fp:Holding` / `fp:MetricSnapshot` 중간 클래스로 표현해 비중·기준일·근거문서를 함께 담는다
3. **domain/range 전면 선언** — 도메인 위반 질의를 추론으로 판정해 ABSTAIN한다
4. **출처 추적** — 모든 datatype property에 `fp:sourceTable`·`fp:sourceColumn`을 박아 답변 evidence가 인용한다. 파생값은 `derived:` 접두
5. **결측 컬럼 배제** — 전량 더미·전량 결측 컬럼은 온톨로지에 올리지 않는다

---

## 데이터

주최측 제공 2026-08-24 배포본을 정본으로 사용한다.

| 테이블 | 도메인 | 행 수 |
|---|---|---:|
| `PRBD01N001` | 국내채권마스터 | 21,882 |
| `PREF01N001` | 국내 ETF 마스터 | 1,780 |
| `PREF02N001` | 해외 ETF 마스터 | 6,037 |
| `PRFD01N001` | 공모펀드마스터 | 23,676 |
| | **합계** | **53,375** |

적재 결과: RDB **53,375행 (100.00%)** · Graph **1,169,374 triples** · Vector **9,055 chunks**

외부 보강: DART 기업 지배구조 관계, ETF 편입종목, 투자설명서. 주최측 데이터와 상충하면 **주최측 값이 우선**한다.

---

## 알려진 제약

| 항목 | 내용 |
|---|---|
| `docs/agent-spec-0825.md` | `agent.agent_core.ask()`를 호출 인터페이스로 안내하지만 **해당 모듈은 현재 저장소에 없다.** 실제 진입점은 `agent.graph.app.invoke()` |
| `golden_set_data_gap_test_sample*.ipynb` | 위와 같은 이유로 `agent_core` import에서 실패한다 |
| Windows CP949 | 일부 오류 경로 출력이 `UnicodeEncodeError`를 낸다. `PYTHONUTF8=1`로 회피 |
| 국내ETF 총보수 | `enriched.product_metric`의 `EXPENSE_RATIO` 기준 1,235건 중 67건(5.4%)만 유효. 결측이 아니라 커버리지 한계 |
| Vector 문서 coverage | 전체 6.39%. 공모펀드가 1.66%로 지배적이며 주원인은 cutoff 이전 투자설명서 부재 |
| `metadata/schema_bindings.json` | 현재 런타임에서 로드되지 않는 선언적 매핑. 일부 물리 참조가 최신 스키마와 어긋나 있다 |
| GraphDB 쓰기 | 배포된 엔드포인트는 read-only (`/update` 403). 적재는 `src/kb/` 빌더로만 수행 |
