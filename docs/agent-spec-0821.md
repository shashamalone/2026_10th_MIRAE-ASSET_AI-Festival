# 에이전트 파일 구조 (LangGraph)  확정 v1 · 2026-08-21

## 1. 트리

1. 최종 트리구조

```
repo/
├── agent/                  # LangGraph — 상태·노드·그래프
│   ├── agent_core.py       # StateGraph 조립·compile, run(question) 진입, to_response() 5필드 직렬화
│   ├── nodes.py            # 노드 함수 전부 (8개). 도구는 tools/에서 import만
│   └── state.py            # State TypedDict + ABSTAIN 코드 상수
├── tools/                  # spec 5절이 확정한 도구 4 + 판정 1. 각 파일이 엔진 핸들 1개를 소유
│   ├── rdb.py              # sql(query) -> list[dict]                DuckDB
│   ├── graph.py            # sparql(query) -> list[dict]             pyoxigraph (ABox)
│   ├── schema.py           # schema_search(text, domain, k) -> list  FAISS 스키마 인덱스
│   ├── content.py          # content_search(text, filter, k) -> list FAISS 콘텐츠 인덱스
│   └── validate.py         # TBox 판정 5종 → ABSTAIN 코드 (유형6). sparql ASK만 쓴다
├── kb/                     # 빌드 타임 전용. 런타임에서 import 하지 않는다 (ids.py 제외)
│   ├── build_rdb.py        # data/csv+enriched+relations 12테이블 → artifacts/kb.duckdb
│   ├── build_graph.py      # ontology/*.ttl 10개 → artifacts/oxigraph/ (TBox·ABox named graph 분리)
│   ├── build_schema_index.py   # TBox rdfs:comment 193청크 → artifacts/schema.faiss
│   ├── build_content_index.py  # cu_strtegy 등 서술 텍스트 → artifacts/content.faiss
│   └── ids.py              # norm()·식별자 해소 단일 구현 (spec R7). 빌드와 런타임이 같은 규칙을 쓴다
├── artifacts/              # 빌드 산출물. 전부 gitignore (spec 4.4)
├── api.py                  # FastAPI 진입점 1파일. 기동 시 그래프 compile 1회 + 엔진 로드 1회
├── config.py               # 경로·모델명·k·시간예산 상수
├── clova.py                # HyperCLOVA X 클라이언트 — chat()·embed()·parse_json_loose()·load_key()
├── requirements.txt        # 제출 필수 (spec 4.4 목록)
├── data/ ontology/ script/ docs*/   # 기존 유지
```

`__init__.py`는 만들지 않는다 (namespace package로 충분)



2. mvp(채권 트리구조 -&gt; 이후 다른 종목으로 확대)

```
repo/
├── agent/
│   ├── agent_core.py
│   ├── nodes.py
│   └── state.py
│
├── tools/
│   └── bond_schema.py
│
├── kb/
│   └── build_bond_index.py
│
├── artifacts/
│   ├── bond.faiss
│   └── bond_terms.json
│
├── ontology/
│   └── bond.ttl
│
├── script/
│   └── test_bond_agent.py
│
├── clova.py
├── config.py
└── api.py
```



## 2. 원칙

- **루트에 `langgraph/` 디렉터리를 만들지 않는다.**
  - pip 패키지 `langgraph`를 가려 `from langgraph.graph import StateGraph`가 로컬 폴더로 해석된다. 같은 이유로 루트 `graph.py`·`langgraph.py`도 금지 (`tools/graph.py`는 `tools.graph`라 안전).
- `script/test_langgraph.py`를 `agent/`로 이식할 때 `sys.path.insert(0, ...)`를 **제거**한다. 이 줄이 남아 있으면 위 충돌이 되살아난다.



## 3. 기술스택

### 기술스택


| 계층         | 엔진(local test용 스택)                          | 선정 근거                                                                                                                                           |
| ---------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **RDB**    | **DuckDB**                                  | 집계·조인·정렬에서 SQLite 대비 10~100배, CSV 직접 질의로 적재 단계가 짧다. 서버 프로세스 불필요                                                                                 |
| **Graph**  | **pyoxigraph** (SPARQL)                     | 기존 `ontology/*.ttl`을 **변환 없이** 벌크 로드. rdflib 대비 SPARQL 수십 배(터미널 노드 탐색 19.99ms vs 752.35ms). rdflib은 100만 트리플 구간에서 수십 초라 유형4의 다단계 순차 경로에서 예산을 소진 |
| **Vector** | **FAISS**                                   | `bge-m3` 1024차원 cosine. 코퍼스가 1만 청크 미만이라 인덱스 구조 선택이 자유로움                                                                                         |
| **LLM**    | HyperCLOVA X — `langchain_naver.ChatClovaX` | 과제 필수 제약. `.env`의 `clova=` 키 사용                                                                                                                 |


**신규 의존성 3개**: `duckdb`, `pyoxigraph`, `faiss-cpu`  
이미 설치됨: `fastapi`, `uvicorn`, `rdflib`, `langchain`, `langchain-naver`, `pandas`, `numpy`



### LLM 모델 


| 용도                        | 모델               | 근거                                                        |
| ------------------------- | ---------------- | --------------------------------------------------------- |
| 1단계 Intent Classification | **HCX-DASH-002** | 분류만 하므로 경량·고속. 32k 컨텍스트로 충분                               |
| 3단계 Query Planning        | **HCX-007**      | 실행 계획을 JSON으로 받아야 하므로 **structured outputs 단독 지원** 모델이 필요 |
| 답변 생성                     | **HCX-007**      | 근거 보존이 중요                                                 |


⚠️ **제약:** function calling · structured outputs · thinking은 **동시 사용 불가**. 

- 3단계는 structured outputs를 쓰므로 function calling을 함께 쓰지 않는다. 라우팅은 LLM tool call이 아니라 반환된 JSON 계획을 **파이썬 코드가 해석·실행**한다.



## 4. State (agent/state.py)

```python
class State(TypedDict):
    question_id: str
    question: str
    intent: dict            # 1단계  {domain, query_type, keywords, entities, numeric_filters}
    schema_hits: list[dict] # 2단계  [{term_uri, comment, domain_file, score}]
    plan: dict              # 3단계  {"steps": [{id, engine, query, depends_on, purpose}]}
    results: dict           # step_id → rows
    evidence: dict          # 내부 표현 {graph, rdb, vector} — 정정 C9
    trace: list[str]        # think_trace 원재료. 노드마다 1줄씩 append
    abstain: dict | None    # {code, reason} — None이 아니면 답변은 "확인할 수 없음"
    answer: str
```

ABSTAIN 코드 5종(= AGENTS.md의 답변불가 사유 구분): `INVALID_TAXONOMY` / `AFTER_AS_OF` / `NOT_FOUND` / `FUTURE_VALUE` / `DOMAIN_VIOLATION`

## 5. 노드 (agent/nodes.py)


| 노드                | spec 단계    | LLM                                      | 쓰는 도구                           |
| ----------------- | ---------- | ---------------------------------------- | ------------------------------- |
| `classify_intent` | 1단계        | HCX-DASH-002 **1회** (structured outputs) | —                               |
| `guard_intent`    | 1단계 결정적 보정 | 0                                        | —                               |
| `check_tbox`      | 유형6 판정     | 0                                        | `validate.*` (TBox 그래프만)        |
| `ground_schema`   | 2단계        | 0 (임베딩 1회)                               | `schema_search`                 |
| `plan`            | 3단계        | HCX-007 **1회** (structured outputs)      | —                               |
| `execute`         | 계획 실행      | 0                                        | `sql`·`sparql`·`content_search` |
| `verify`          | 단계 D       | 0                                        | `sparql` ASK (SHACL 대신 — R4)    |
| `answer`          | 단계 E       | HCX-007 **1회**, abstain이면 **0회**(템플릿)    | —                               |


LLM 합계 3회 = spec 2절. 유형6은 `check_tbox`→`answer` 경로라 0~1회.

```
START → classify_intent → guard_intent ─┬─ query_type=unanswerable_check → check_tbox ─┬─ abstain 확정 → answer
                                        │                                              └─ 통과 ↓
                                        └────────────────────────────→ ground_schema → plan → execute → verify → answer → END
```

`verify`가 0건·`unresolved` 플래그를 만나면 abstain을 채우고 그대로 `answer`로 간다 — 조용히 "없음"으로 답하지 않기 위한 지점이다.



&nbsp;