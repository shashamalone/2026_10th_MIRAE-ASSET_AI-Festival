# Agent runtime architecture

## 1. 책임 분리

```text
agent/                         Agent 오케스트레이션
  graph.py                     LangGraph StateGraph
  nodes.py                     receive/analyze/plan/search/answer 노드
  get_clova.py                 HyperCLOVA X chat + bge-m3 query embedding

tools/                         Agent-facing capability
  vector_search.py             Vector 검색 입력·출력 정규화
  graph_search.py              Graph 검색 진입점

infrastructure/                외부 저장소 통신 어댑터
  vector_db/client.py          PostgreSQL + pgvector read-only 검색
  graph_db/client.py           Oxigraph 3단계 read-only failover

kb/                            적재·검증·빌드 코드
```

`nodes.py`는 DB driver, SQL table name, Oxigraph transport를 직접 다루지
않는다. 검색 노드는 `tools`만 호출하고, 연결 방식은 `infrastructure`에서
환경변수로 결정한다.

## 2. 호출 흐름

```text
vector_search_node
  -> tools.vector_search.search_documents
  -> infrastructure.vector_db.client.VectorDBClient.search
  -> vec.document_chunk + vec.chunk_embedding (cosine distance)
  -> vec.document_product (선택적 상품 제한)
```

```text
graph_search_node
  -> graph_orchestrator
  -> agent.graph_logic.graph_engine.sparql
  -> infrastructure.graph_db.client.OxigraphClient.query
  -> 외부 mount snapshot -> 로컬 snapshot -> 원격 SPARQL endpoint
```

## 3. 통신 설정

### PostgreSQL / pgvector

직접 연결을 사용할 때:

```dotenv
DATABASE_URL=postgresql://agent_reader:***@host:5432/database
VECTOR_SCHEMA=vec
VECTOR_DB_TIMEOUT=3
```

또는 `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`를 사용한다.
DSN이 없으면 기존 `agent.utils`의 read-only `/db/sql` API를 사용한다.

Vector 검색은 정규화된 세 테이블을 사용한다.

```text
vec.document_chunk
  content_hash + embedding_model + model_revision
    -> vec.chunk_embedding

vec.document_chunk.document_id
    -> vec.document_product.document_id
    -> product_id
```

- `vec.document_chunk`: 청크 원문·인용문·페이지·기준일
- `vec.chunk_embedding`: 고유 content hash별 1024차원 벡터
- `vec.document_product`: 문서와 정규 상품 ID 연결

검색 계약은 다음과 같다.

- `embedding_model = bge-m3`
- `embedding_dim = 1024`
- cosine distance: `chunk_embedding.embedding <=> query_vector`
- top-k는 청크에 먼저 적용하고 상품 목록은 이후 결합해 중복을 방지
- 최대 반환 건수: 20

### Oxigraph

Oxigraph는 다음 순서로 조회한다.

```text
1. Agent 서버에 마운트된 외부 read-only snapshot
2. Agent 서버 로컬 read-only snapshot
3. 원격 SPARQL endpoint
```

환경변수:

```dotenv
OXIGRAPH_REMOTE_STORE_PATH=\\server\share\oxigraph-snapshot
OXIGRAPH_LOCAL_STORE_PATH=artifacts/oxigraph
OXIGRAPH_FALLBACK_ENDPOINT=http://40.82.145.44:55001/query
OXIGRAPH_TIMEOUT=60
```

이전 설정과의 호환을 위해 `OXIGRAPH_STORE_PATH`와 `OXIGRAPH_ENDPOINT`도
각각 로컬 경로와 fallback endpoint 별칭으로 지원한다. HTTP timeout의
기본값은 60초다. `pyoxigraph` 파일 조회에는 Python HTTP timeout이
적용되지 않으므로 외부 mount timeout은 운영체제·mount 설정에서 관리한다.

외부 경로는 URL이 아니라 Agent 서버에서 보이는 파일시스템 경로여야 한다.
실행 중인 writer의 활성 RocksDB volume을 공유하지 않고, 검증이 완료된
불변 snapshot을 read-only로 마운트한다. 세 경로는 동일한 release와
데이터 기준일(2026-08-24)을 사용해야 한다.

다음 상황에만 다음 transport로 fallback한다.

- snapshot 경로 없음
- pyoxigraph 미설치
- 파일 권한·mount·RocksDB open/read I/O 오류

정상적인 0건 결과, SPARQL 문법 오류, 허용하지 않은 update query에는
fallback하지 않는다. Agent는 `SELECT`와 `ASK`만 실행하며 SPARQL update와
`SERVICE`는 차단한다.

## 4. 실행 전 점검

VectorDB의 실제 테이블 메타데이터·행 수·연결률·출력 샘플은 Jupyter 셀
스크립트 `test/vector_db/vector_metadata_samples.py`로 확인한다. 1024차원
원벡터는 출력하지 않으며, 실제 의미 검색 셀은 기본적으로 비활성화한다.

```bash
python -m py_compile src/infrastructure/vector_db/client.py src/infrastructure/graph_db/client.py src/tools/vector_search.py src/tools/graph_search.py src/agent/nodes.py
python -m py_compile test/vector_db/vector_metadata_samples.py
python -m unittest discover -s test/graph_db -p "test_*.py"
python -m unittest discover -s test/vector_db -p "test_*.py"
python src/kb/build_vectors.py --check
```

Vector 테이블이 0행이면 연결 성공과 검색 결과 존재는 별개다. 이 경우
검색 결과는 빈 목록이며, 근거가 없다는 사실을 데이터 부재로 오인하지
않도록 embedding release 후 운영 검증을 수행한다.
