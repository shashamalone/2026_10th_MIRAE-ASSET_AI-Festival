## 기술스택

> 관계 데이터 CSV→ Python으로 TTL 생성→ pyoxigraph에 GraphDB 구축→ SPARQL로 관계 검색



**최종 서버**

```
  FastAPI Agent 서버
    ├─ PostgreSQL 서버
    ├─ pyoxigraph Graph 파일
    └─ HCX API
```

- TTL: 회사·자회사·ETF 관계를 저장하는 그래프 파일
- pyoxigraph: TTL 데이터를 저장하고 검색하는 GraphDB
- SPARQL: GraphDB에 질문하는 검색 언어. (RDB의 SQL과 비슷)
- Python: 데이터를 TTL로 변환하고 SPARQL을 실행



[참고] 

- PostgreSQL: 표 형태 데이터를 저장하고 SQL로 검색
  - PostgreSQL → 테이블·행·열 → SQL
- pyoxigraph: 관계 그래프 데이터를 저장하고 SPARQL로 검색
  - pyoxigraph → 노드·관계·속성 → SPARQL



&nbsp;

### 현재 DB

- 로컬에는 이미 `artifacts/oxigraph`가 존재하고, `src/tools/[graph.py](http://graph.py)`도 다음 방식으로 구현

```
Store.read_only(str(STORE_PATH))
```

- 따라서 지금은 **별도 Oxigraph Server를 띄우지 않고, 로컬 embedded pyoxigraph Store로 먼저 진행**

```
로컬: Agent → pyoxigraph → artifacts/oxigraph
Azure: Agent/Jupyter → Data API → Oxigraph Server
```

```
Jupyter / Agent
    ↓ HTTP
Azure Data API :8000
    ↓ 내부 연결
Oxigraph Server :7878
    ↓
활성 Graph volume
```

- Azure `/health`에서 `graph_triples: 655388`
- Azure `/db/sparql` 요청이 `HTTP 200`
- 문서에 활성 Oxigraph volume이 기록되어 있음
- PostgreSQL `5432`, Oxigraph `7878`은 외부에 공개하지 않는다고 명시됨

---

# GraphDB 서빙 구조

## 현재 개발·테스트 환경

```
TTL 파일
  ↓
pyoxigraph Store 생성
  ↓
artifacts/oxigraph/
  ↓
Agent가 Store.read_only()로 열기
  ↓
Python에서 SPARQL 실행
```

현재 로컬에는 다음 Graph Store가 준비되어 있습니다.

```
artifacts/oxigraph/
```

Agent는 이 Store를 읽기 전용으로 열어 Graph 데이터를 검색

```
from pyoxigraph import Store

store = Store.read_only("artifacts/oxigraph")
result = store.query(sparql_query)
```

데이터를 직접 수정하지 않고, Graph 데이터를 갱신할 때는 새 Store를 만든 뒤 검증이 끝나면 교체

```
새 TTL
  ↓
임시 Graph Store 생성
  ↓
SPARQL·행 수·evidence 검증
  ↓
기존 artifacts/oxigraph 교체
  ↓
Agent 재시작
```

## 현재 실행 구조

```
Jupyter 또는 FastAPI Agent
├─ PostgreSQL
│   └─ RDB 데이터 조회
└─ artifacts/oxigraph
    └─ pyoxigraph Graph Store 읽기 전용 조회
```

현재 구조에서는 PostgreSQL처럼 별도의 Oxigraph Server를 실행할 필요가 없습니다.

```
Agent Python 코드
  ├─ PostgreSQL 연결
  └─ pyoxigraph Store.read_only()
```

Graph Store는 로컬 디스크에 저장되며, Agent는 SELECT·ASK 형태의 읽기 전용 SPARQL만 실행합니다.



&nbsp;

&nbsp;

## Graph Store 생성

TTL 파일로 Graph Store를 새로 만들 때는 다음 명령을 사용합니다.

```
python src/kb/build_graph.py
```

생성 결과:

```
artifacts/oxigraph/
```

생성 후에는 Graph Store가 비어 있지 않은지와 대표 SPARQL 질의를 확인합니다.

## 테스트

Jupyter에서 다음과 같이 로컬 Graph를 테스트할 수 있습니다.

```
from tools.graph import sparql

result = sparql(
    """
    PREFIX fp: <http://mafest.ai/product#>

    SELECT ?product ?name
    WHERE {
        GRAPH <http://mafest.ai/graph/abox/etf_kr> {
            ?product a fp:KoreanETF ;
                     fp:productShortName ?name .
        }
    }
    LIMIT 10
    """
)

result
```



&nbsp;

## 운영 확장 단계

 TEST 환경에서는 내장 pyoxigraph store로 진행

```
TEST 환경 운영
FastAPI + PostgreSQL + 내장 pyoxigraph
```

대회 제출 시 별도 Oxigraph Server를 도입

```
FastAPI Agent 서버
    ├─ PostgreSQL 서버
    ├─ pyoxigraph Graph 파일
    └─ HCX API
```

```
대규모 운영
Agent 서버
  ↓ HTTP SPARQL
별도 Oxigraph Server
  ↓
공유 Graph Store
```

