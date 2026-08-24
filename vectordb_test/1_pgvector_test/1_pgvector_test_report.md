# vectordb_test — pgvector 1차 검증

FAISS 로 돼 있는 채권 스키마 인덱스를 PostgreSQL + pgvector 로 옮길 수 있는지 판단하기 위한
사전 테스트다. **벡터 검색 · Full Text Search · 하이브리드(RRF) 결합**이 한 DB 안에서 되는지,
특히 **한국어에서 FTS 가 실제로 쓸 만한지**를 실측한다.

결과 요약은 [`results/test_result.md`](results/test_result.md), 질의별 원시 결과는
[`results/sample_queries.json`](results/sample_queries.json) 에 있다.

## 한 줄 결론

벡터 검색과 하이브리드는 문제없이 동작한다. **한국어 FTS 는 형태소 분석기가 없어
조사가 붙거나 복합명사 일부만 친 질의를 전혀 못 잡는다.** 한국어 질의 6건 중 FTS 는 3건만
적중했고 벡터는 6건 모두 1위로 맞혔다. 자세한 내용은 결과 문서를 보라.

## 실행

```bash
cd vectordb_test

# 1. 의존성 (한 번만)
pip3 install --user --break-system-packages "psycopg[binary]" pgvector

# 2. 스키마
PGPASSWORD=postgres psql -h 127.0.0.1 -p 5432 -U postgres -d vectordb_test -f schema.sql

# 3. 적재 (CLOVA 임베딩 17건 — 문서 10 + 질의 7)
python3 seed.py

# 4. 테스트 — 파이프를 거치지 말고 직접 실행해서 exit code 를 읽을 것
for t in test_connection test_schema test_vector_search \
         test_keyword_search test_hybrid_search test_integration; do
  python3 $t.py; echo "$t -> $?"
done
```

접속 정보는 `config.py` 가 libpq 환경변수(`PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`/`PGDATABASE`)에서
읽고, 없으면 `127.0.0.1:5432 / postgres / vectordb_test` 를 쓴다.
**유닉스 소켓으로 붙으면 peer 인증에 걸리므로 host 를 반드시 명시한다.**

## 파일

| 파일 | 역할 |
|---|---|
| `schema.sql` | `documents(id, doc_key, lang, content, embedding vector(1024))` + FTS/trigram/HNSW 인덱스 |
| `samples.py` | 샘플 문서 10건(영문 5 + 한국어 5)과 질의 7건 |
| `seed.py` | CLOVA 임베딩 후 적재 |
| `search.py` | `vector_search` / `keyword_search` / `trigram_search` / `hybrid_search`(RRF) |
| `config.py` | 경로·모델 상수 + DSN. 저장소 `clova.py` 의 `from config import ...` 계약도 만족시킨다 |
| `clovax.py` | 저장소 루트 `clova.py` 를 그대로 로드 (새 클라이언트가 아니다). **08-22 `src/` 이전 후 루트에는 없다** — `clovax.py` 는 아직 `src/clova.py` 를 보지 않고 git 블롭(`46ac51a:clova.py`) 폴백으로 로드한다 |
| `checks.py` | PASS/FAIL 출력 + exit code |
| `test_*.py` | 프레임워크 없이 `python3 test_x.py` 로 실행, exit code 로 성패 |
| `docker-compose.yml` | **다른 머신용.** 이 머신에는 docker 가 없어 실행 불가 |
| `setup_local_pg.sh` | sudo·docker 없이 PostgreSQL+pgvector 를 사용자 디렉터리에 띄우는 대안 |

## 규칙 (지켜진 것)

- LLM·임베딩은 **HyperCLOVA X 전용**. 임베딩은 `bge-m3` / **1024차원** / **cosine**.
- 임베딩은 저장소 루트의 검증된 `clova.py` 를 재사용한다. `clovax.py` 는 그것을 로드만 한다.
- 분당 쿼터 때문에 `embed_many()` 만 쓴다(1.2초 간격 + 429 백오프 + 디스크 캐시).
  루프에서 `embed()` 를 연타하지 않는다. 캐시는 `vectordb_test/artifacts/embed_cache.json` 에
  따로 두어 저장소의 `artifacts/` 를 건드리지 않는다.
- 저장소의 기존 파일은 읽기만 했다. FAISS 코드는 손대지 않았다(이번은 비교 검증이지 교체가 아니다).

## 이 머신의 환경 제약

| 항목 | 상태 |
|---|---|
| `docker` | 없음 → `docker-compose.yml` 은 작성만 해 두고 다른 머신에서 써야 한다 |
| PostgreSQL 서버 | **있음** — 18.6 이 직접 설치돼 5432 에서 동작 |
| pgvector | **있음** — 0.8.1 |
| `pg_trgm` | **있음** — 1.6 (contrib) |
| 한국어 FTS 설정 | **없음** — `pg_ts_config` 30종 중 `korean` 부재 |

`setup_local_pg.sh` 는 서버가 없는 머신을 위한 대안이다. `apt-get download` 는 root 가 필요 없으므로
deb 를 사용자 디렉터리에 풀어 `initdb`/`postgres` 를 직접 돌린다. 시스템에는 아무것도 설치하지 않는다.
검증 과정에서 실제로 이 방식으로 PostgreSQL 18.3 + pgvector 0.8.1 을 55432 포트에 띄워 봤고 동작했다.
