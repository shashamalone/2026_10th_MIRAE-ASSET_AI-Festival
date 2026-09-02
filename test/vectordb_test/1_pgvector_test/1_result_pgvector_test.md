# pgvector 1차 검증 결과

실행일 2026-08-22 · 전체 재현: `README.md` 참조

---

## 1. 환경


| 항목       | 값                                                        |
| -------- | -------------------------------------------------------- |
| OS       | Linux 6.6.87.2-microsoft-standard-WSL2 (Ubuntu resolute) |
| Python   | 3.14.4                                                   |
| DB 접속    | `127.0.0.1:5432` TCP (유닉스 소켓은 peer 인증 실패 — host 명시 필수)   |
| DB       | `vectordb_test`                                          |
| 파이썬 드라이버 | `psycopg 3.3.4` (binary), `pgvector 0.5.0`               |
| `docker` | **없음** — `docker-compose.yml` 은 작성만 해 뒀고 이 머신에서는 실행 불가   |
| 문서 수     | 10건 (영문 5 + 한국어 5)                                       |


한국어 문서 5건은 지어낸 문장이 아니라 `artifacts/bond_terms.json` 의 `text` 필드 원문이다
(`ontology/bond_kr.ttl` · `common.ttl` 의 `rdfs:label` + `rdfs:comment` 조합).
실제 인덱스 텍스트와 토큰 모양이 같아야 FTS 실측이 의미가 있다.

## 2. PostgreSQL 버전

```
PostgreSQL 18.6 (Ubuntu 18.6-0ubuntu0.26.04.1) on x86_64-pc-linux-gnu
```

## 3. pgvector 버전

```
vector   0.8.1
:  1.6      (한국어 부분어 폴백 검증용, contrib)
```

## 4. 임베딩 모델과 차원


| 항목  | 값                                                                                                                        |
| --- | ------------------------------------------------------------------------------------------------------------------------ |
| 모델  | `bge-m3` (CLOVA Studio / HyperCLOVA X)                                                                                   |
| 차원  | **1024** (`vector(1024)`, 실측 확인)                                                                                         |
| 거리  | **cosine** — `<=>` / `vector_cosine_ops`                                                                                 |
| 정규화 | **하지 않고 원본을 저장한다.** 저장 벡터의 L2 norm 은 25.016 ~ 26.576 으로 1이 아니다. `<=>` 가 내부에서 정규화하므로 결과에 영향이 없다 (§9 에서 FAISS 와 수치 동등성 확인) |
| 호출  | 저장소 루트 `clova.py` 의 `embed_many()` 재사용. 문서 10 + 질의 7 = **17회**, 1.2초 간격, 429 없음                                          |


## 5. 테스트 목록과 6. PASS/FAIL

프레임워크 없이 `python3 test_x.py` 로 실행하고 exit code 로 판정했다.
파이프를 거치지 않고 직접 실행해 `$?` 를 읽었다.


| #   | 테스트                      | 내용                                              | exit | 판정       |
| --- | ------------------------ | ----------------------------------------------- | ---- | -------- |
| 1   | `test_connection.py`     | 접속 · 서버 버전 · `vector`/`` 확장 · text search 설정 목록 | 0    | **PASS** |
| 2   | `test_schema.py`         | 테이블·컬럼·차원(1024)·FTS/trigram/HNSW 인덱스·적재량(10건)   | 0    | **PASS** |
| 3   | `test_vector_search.py`  | 질의 7건 1위 정답 · 정렬 · 값 범위 · **FAISS 동등성**         | 0    | **PASS** |
| 4   | `test_keyword_search.py` | `simple` vs `english` vs `pg_trgm` 한국어 실측 매트릭스  | 0    | **PASS** |
| 5   | `test_hybrid_search.py`  | RRF 산식 · 합집합 · FTS 0건일 때 폴백                     | 0    | **PASS** |
| 6   | `test_integration.py`    | 전 질의 3방식 실행 + `sample_queries.json` 생성          | 0    | **PASS** |


**6/6 PASS. BLOCKED·FAIL 없음.**

## 7. 실패 원인

테스트 실패는 없다. 다만 **작성 도중 실제로 잡은 결함 2건**을 기록해 둔다.

1. **유닉스 소켓 누수** — `config.py` 가 `os.environ` 을 수정하는 방식이었는데,
 `config` 를 import 하지 않은 `test_connection.py` 가 조용히 유닉스 소켓으로 붙어
 `FATAL: role "rladl" does not exist` 로 실패했다.
 → 부작용 대신 명시적 `config.DSN` 으로 바꿔 잊어버릴 여지를 제거했다.
2. `**vector <=> double precision[]` 연산자 없음** — `register_vector` 는 numpy 배열만
 `vector` 로 보낸다. `clova.embed_many()` 는 순수 파이썬 `list` 를 주므로 `float8[]` 로 나갔다.
 (`INSERT` 는 대상 컬럼 타입으로 assignment cast 가 되어 조용히 통과했고, `SELECT` 에서만 터졌다.)
 → 모든 벡터 질의가 지나가는 `search.vector_search()` 한 곳에서 `::vector` 로 캐스팅한다.

## 8. 한국어 FTS 실측 — 이번 검증의 핵심

### 8.1 전제 확인

`pg_ts_config` 에 설정 **30종**이 있지만 `**korean` 은 없다.**
`simple` 은 공백·구두점으로만 자르고, `english` 는 거기에 **라틴 문자용** 스테머와 불용어를 얹을 뿐이다.
즉 한국어에서 토큰 단위는 형태소가 아니라 **어절**이다.

```
to_tsvector('simple', 'fp:duration | 듀레이션 | 금리 민감도. **0이 8,268건이며 만기경과와 …')
→ '0이':6  '268건이며':8  '금리':4  '듀레이션':3,13  '만기경과와':9  '미계산이':10  '민감도':5  '제외가':17 …
```

`'0이'`, `'만기경과와'`, `'미계산이'`, `'제외가'` 처럼 **조사가 붙은 채로 한 토큰**이 된다.

### 8.2 실측 매트릭스


| 질의             | 유형                      | `simple` | `english` | `pg_trgm` | 벡터  |
| -------------- | ----------------------- | -------- | --------- | --------- | --- |
| `barking dog`  | 영문 정확                   | HIT      | HIT       | HIT       | HIT |
| `barking dogs` | 영문 굴절                   | **MISS** | HIT       | HIT       | —   |
| `듀레이션`         | 정확 어절                   | HIT      | HIT       | HIT       | HIT |
| `위험등급`         | 정확 어절                   | HIT      | HIT       | HIT       | HIT |
| `금리 민감도`       | 어절 2개                   | HIT      | HIT       | HIT       | HIT |
| `듀레이션이`        | **조사 결합**               | **MISS** | **MISS**  | HIT       | HIT |
| `듀레이션이 뭐야?`    | **조사 + 자연어**            | **MISS** | **MISS**  | HIT       | HIT |
| `등급`           | **부분어** (`등급` ⊂ `위험등급`) | **MISS** | **MISS**  | HIT       | HIT |
| `채권 이자율`       | **동의어** (원문 `표면금리`)     | **MISS** | **MISS**  | 오답 1위     | HIT |


**한국어 질의 6건 중  FTS(**`simple`**) 적중 3건 / FTS(**`english`**) 적중 3건 / 벡터 1위 정답 6건.**

### 8.3 결론 네 가지

1. **한국어 FTS 는 "어절이 정확히 일치할 때만" 동작한다.**
 사전에 있는 용어를 그대로 친 경우(`듀레이션`, `위험등급`)는 잡지만,
 사용자가 실제로 던지는 자연어 질문(`듀레이션이 뭐야?`)은 **하나도 못 잡는다.**
 조사 하나만 붙어도 토큰이 달라지기 때문이다. 한국어 질의에서 이건 예외가 아니라 기본값이다.
2. `**english` 설정은 한국어에 아무 이득이 없다.**
 한국어 질의 6건 전부에서 `simple` 과 결과가 **완전히 동일**했다.
 스테머·불용어가 라틴 문자에만 적용되기 때문이다. 실제로 `english` 는
 `fp:duration` 의 `duration` 을 `durat` 로 스테밍해 URI 토큰만 훼손한다.
 차이는 영문에서만 났다 — `barking dogs` 는 `english` 만 잡았다(`dogs`→`dog`).
 → **한국어 코퍼스에 `english` 설정을 쓸 이유가 없다. `simple` 을 쓰라.**
3. **부분 단어 매칭은 안 된다. 폴백이 필요하다.**
 한국어 복합명사는 띄어쓰기 없이 붙는데(`위험등급`, `표면금리`, `잔존만기`),
 FTS 는 어절 통째로만 토큰이라 `등급` 으로는 `위험등급` 을 못 찾는다.
 `pg_trgm`(`word_similarity` + `ILIKE`)은 조사 결합과 부분어를 **회수는 한다**
 (`등급`→`fp:riskGradeLevel` 0.333, `듀레이션이`→`fp:duration` 0.667).
 **다만 정밀도를 못 준다** — `채권 이자율` 질의에서 정답 `fp:couponRate`(0.143)를 제치고
 무관한 `fp:riskGradeLevel`(0.429)을 1위로 올렸다. 글자 겹침이지 의미가 아니기 때문이다.
 → `pg_trgm` 은 **랭커가 아니라 회수 보조**로만 써야 한다.
4. **어휘 불일치는 벡터만 해결한다.**
 `채권 이자율` → `표면금리` 는 글자가 하나도 안 겹쳐 FTS·trigram 모두 실패했지만
 벡터는 `fp:couponRate` 를 0.554 로 1위에 올렸다.

### 8.4 그래서 어떻게 할 것인가

- **벡터를 주 검색기로 두고, FTS 는 정확 용어 질의의 가산점으로만 쓴다.** RRF 가 이 구조를 그대로 만든다.
실측상 FTS 가 0건이어도 하이브리드 1위는 항상 정답이었다(§9).
- `pg_trgm` 은 **넣어 두되 랭킹에 태우지 않는다.** 벡터가 0건일 때의 마지막 회수 그물로만 쓴다.
지금 규모(용어 130건)에서는 벡터가 항상 무언가를 돌려주므로 사실상 불필요하다.
- 한국어 형태소 분석기(`textsearch_ko`/`mecab-ko`, `pg_bigm`)를 **깔지 않아도 된다.**
FTS 에 기대하는 역할이 "정확 용어 일치"뿐이라면 `simple` 로 충분하고,
그 이상은 어차피 벡터가 담당한다. 서버에 컴파일 의존성을 늘릴 이유가 없다.

## 9. 실제 hybrid 결과

RRF, `k=60`, `score(d) = Σ 1/(k + rank)`. 벡터 랭킹 + FTS(`simple`) 랭킹. reranker 없음.

**(a) FTS 와 벡터가 모두 잡는 경우 — `듀레이션`**


| 순위  | doc_key             | RRF      | 기여                          |
| --- | ------------------- | -------- | --------------------------- |
| 1   | `fp:duration`       | 0.032787 | vector#1 + keyword#1 = 2/61 |
| 2   | `en:vector`         | 0.016129 | vector#2                    |
| 3   | `fp:maturityBucket` | 0.015873 | vector#3                    |


**(b) FTS 가 0건인 경우 — `듀레이션이 뭐야?`** (조사 결합)


| 순위  | doc_key         | RRF      | 기여         |
| --- | --------------- | -------- | ---------- |
| 1   | `fp:duration`   | 0.016393 | vector#1 만 |
| 2   | `fp:couponRate` | 0.016129 | vector#2   |
| 3   | `en:pg`         | 0.015873 | vector#3   |


→ FTS 가 통째로 실패해도 **하이브리드 1위는 정답을 유지한다.**

**(c) 어휘 불일치 — `채권 이자율`** (FTS·trigram 모두 실패)


| 순위  | doc_key         | RRF      | 기여                      |
| --- | --------------- | -------- | ----------------------- |
| 1   | `fp:couponRate` | 0.016393 | vector#1 (cosine 0.554) |
| 2   | `fp:duration`   | 0.016129 | vector#2                |


**질의 7건 전부에서 하이브리드 1위 = 기대 문서.** 원시 결과는 `sample_queries.json`.

## 10. 서버 이전 시 변경사항

### 10.1 인프라

- `docker-compose.yml` 그대로 사용 (`pgvector/pgvector:pg18`). 이 개발 머신엔 docker 가 없어 실행하지 못했다.
- `POSTGRES_INITDB_ARGS: --encoding=UTF8 --locale=C.UTF-8` 유지. 한국어 형태소 분석기가 없으므로
collation 은 검색 품질에 관여하지 않는다.
- 확장은 `vector` 만 필수. `pg_trgm` 은 회수 폴백을 쓸 때만.
- 현재 스키마는 `psql -f schema.sql` 한 번이면 끝이라 마이그레이션 도구가 필요 없다.

### 10.2 FAISS → pgvector 코드 변경 (파일·함수 단위)

**핵심: cosine 점수가 수치까지 같으므로 임계값을 다시 잡을 필요가 없다.**
현행 `src/kb/build_bond_index.py` 는 `faiss.normalize_L2` + `IndexFlatIP` 로 cosine 을 구하는데,
pgvector 의 `1 - (a <=> b)` 와 **최대 오차 5.03e-07**, Top-5 순서 동일임을 실측했다
(`test_vector_search.py` 의 "FAISS 동등성" 항목). → `config.BOND_SCORE_FLOOR = 0.45` **그대로 유효.**


| 파일                           | 함수                       | 지금                                                    | 바꿀 것                                                                                                              |
| ---------------------------- | ------------------------ | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `src/kb/build_bond_index.py` | `collect()`              | TTL → terms 리스트                                       | **그대로 둔다.** 산출물이 곧 적재 행이 된다                                                                                       |
|                              | `main()`                 | `faiss.normalize_L2` → `IndexFlatIP` → `write_index`  | `INSERT INTO bond_terms(term_uri, label, comment, alt_labels, content, embedding)`. **정규화 호출 삭제** (`<=>` 가 내부 처리) |
|                              |                          | `BOND_TERMS_PATH` JSON 기록                             | 삭제 가능. 행 자체가 label·comment 를 들고 있어 JSON 이 이중 관리가 된다                                                               |
|                              |                          | `vector_id` (정렬 순서 = 인덱스 위치)                          | 삭제. `term_uri` 가 자연 PK다. 재빌드 때 순서가 흔들릴 걱정도 사라진다                                                                   |
| `src/tools/bond_schema.py`   | `_load()` (`@lru_cache`) | 인덱스+JSON 을 프로세스당 1회 로드, `ntotal != len(terms)` 정합성 검사 | **함수 통째로 삭제.** 대신 `psycopg_pool.ConnectionPool` 하나. 정합성 검사는 DB 가 단일 소스라 불필요                                       |
|                              | `bond_schema_search()`   | `clova.embed(text)`                                   | 그대로                                                                                                               |
|                              |                          | `faiss.normalize_L2(q)` + `index.search(q, k)`        | `ORDER BY embedding <=> %s::vector LIMIT k`. `**%s::vector` 캐스팅 필수** (§7-2)                                       |
|                              |                          | `if float(score) < floor: continue`                   | SQL 로 내림: `WHERE (embedding <=> %s::vector) <= 1 - 0.45`. 값은 그대로                                                  |
|                              |                          | 반환 `score` = IP 내적                                    | `1 - distance`. 의미·수치 동일                                                                                          |
| `config.py`                  | —                        | `BOND_INDEX_PATH`, `BOND_TERMS_PATH`                  | 삭제하고 DSN 상수 추가                                                                                                    |
|                              | —                        | `BOND_SCORE_FLOOR = 0.45`, `BOND_TOP_K = 5`           | **변경 없음**                                                                                                         |
| `requirements.txt`           | —                        | `faiss-cpu`                                           | `psycopg[binary]`, `pgvector` 로 교체                                                                                |
| `src/agent/nodes.py`         | —                        | `bond_schema_search()` 호출                             | **변경 없음** — 시그니처·반환 형태를 유지하면 호출부는 안 건드려도 된다                                                                       |


### 10.3 이전으로 새로 얻는 것

- **하이브리드가 공짜로 된다.** FAISS 에는 FTS 가 없어 지금은 벡터 단독이다.
같은 테이블에 GIN 인덱스만 추가하면 §9 구조가 그대로 붙는다.
- **정확 용어 질의의 사각지대가 메워진다.** 벡터는 `듀레이션` 을 0.550 으로 1위에 놓지만
2위 `en:vector`(0.357)와의 간격이 크지 않다. FTS 가 정확 일치에 가산점을 주면 이 경계가 또렷해진다.
- 인덱스 파일과 terms JSON 의 **이중 관리가 사라진다** (`ntotal != len(terms)` 검사 자체가 없어진다).

### 10.4 주의

- 현재 용어 **130건** 규모에서는 HNSW 가 의미 없다. 실측에서도 플래너가 **Seq Scan** 을 골랐고
그게 정상이다. 인덱스는 만들어 두되 성능 근거로 삼지 말 것.
- 인스턴스 데이터(`ontology/instances_*.ttl`, 수백만 트리플)까지 같은 테이블에 넣을 거라면
그때 HNSW 파라미터(`m`, `ef_construction`)와 `maintenance_work_mem` 을 다시 봐야 한다.
이번 검증 범위(스키마 용어)는 아니다.

---

# PASS

6개 테스트 전부 exit 0. **PostgreSQL 18.6 + pgvector 0.8.1 에서 벡터 검색 · Full Text Search ·
하이브리드(RRF) 결합이 모두 동작하며, FAISS 와 cosine 점수가 5.03e-07 오차로 일치하므로
`BOND_SCORE_FLOOR` 를 포함한 기존 임계값을 그대로 들고 이전할 수 있다.**

단, PASS 는 **"pgvector 로 이전 가능"** 이라는 뜻이지 **"한국어 FTS가 쓸 만하다"** 는 뜻이 아니다.  
한국어 FTS 는 어절 완전 일치에서만 동작하며 조사·부분어·동의어 질의를 전혀 못 잡는다  
(한국어 질의 6건 중 3건 적중). **검색 품질의 주축은 벡터여야 하고 FTS 는 보조다.**
이 전제가 깨지면(예: FTS 단독 경로를 만들면) 한국어 질의에서 곧바로 무응답이 난다.