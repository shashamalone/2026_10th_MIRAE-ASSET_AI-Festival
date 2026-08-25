# VECTORDB DEFINITION V2.0

자동 생성 파일입니다. 직접 편집하지 말고 `python src/kb/build_catalog_v2.py`를 실행합니다.
물리 정의의 정본은 [단일 카탈로그](../../src/kb/catalog_v2.py), [Vector DDL](../../sql/v2/001_platform_schema.sql), [임베딩 빌더](../../src/kb/build_vectors_v2.py)입니다.

- 데이터 버전: `financial-products-2026-07-11`
- 배포일: `2026-07-11`
- 외부 근거 cutoff: `2026-07-11`

## 범위와 엔진

- 엔진: PostgreSQL 17의 pgvector 확장
- 임베딩: CLOVA Studio `bge-m3`, 1024차원
- 거리: cosine distance (`<=>`), 점수 표시는 `1 - distance`
- ANN 인덱스: HNSW + `vector_cosine_ops`
- 저장 위치: PostgreSQL `vec` 스키마; 별도 FAISS 운영 경로 없음
- 임베딩 원문과 벡터 산출물은 Git에 커밋하지 않습니다.

## 인덱스 분리

| 논리 인덱스 | 물리 테이블 | 현재 정의 행 수 | 용도 | 갱신 조건 |
|---|---|---:|---|---|
| 채권 schema grounding | `vec.bond_schema_terms` | 130 | 채권 질의의 TBox 의미 검색 | `common.ttl` 또는 `bond_kr.ttl` 변경 |
| 전체 schema grounding | `vec.schema_terms_all` | 189 | 전 상품군 ontology grounding | TBox 5개 중 하나 변경 |
| content grounding | `vec.document_chunk` | 배포 시 산출 | 문서 근거·인용 검색 | 공식 문서 수집 또는 청크 변경 |

Ontology Index와 Content Index는 목적·필터·갱신주기가 다르므로 같은 테이블에 섞지 않습니다.

## 임베딩 텍스트와 식별 규칙

- TBox term은 `term_uri | rdfs:label | skos:altLabel | rdfs:comment` 순서로 결합합니다.
- 문서 청크는 `document_id`, `product_id`, `page_number`, `citation_text`, `published_at`, `source_url`을 보존합니다.
- `content_hash=SHA-256(원문)`와 `embedding_model`이 같으면 기존 벡터를 재사용합니다.
- 같은 테이블에서 원문 해시 중복을 허용하지 않으며 임베딩 NULL과 1024차원 불일치를 빌드 실패로 처리합니다.
- 문서에는 페이지와 인용문을 저장하지만 별도 문자 offset 컬럼은 아직 구현되지 않았습니다.
- `published_at`이 cutoff를 초과하는 청크가 하나라도 있으면 전체 적재를 중단합니다.

## 테이블 목록

| 스키마 | 테이블 | 종류 | grain | PK | 인덱스 | 상태 |
|---|---|---|---|---|---|---|
| `vec` | `bond_schema_terms` | table | 채권 TBox grounding term 1개 | `term_uri` | embedding vector_cosine_ops (HNSW), content_hash,embedding_model | 구현=구현, 배포=미배포 |
| `vec` | `schema_terms_all` | table | 전체 TBox grounding term 1개 | `term_uri` | embedding vector_cosine_ops (HNSW), content_hash,embedding_model | 구현=구현, 배포=미배포 |
| `vec` | `document_chunk` | table | 문서 청크 1개 | `chunk_id` | embedding vector_cosine_ops (HNSW), document_id, product_id | 구현=구현, 배포=미배포 |

## 물리 테이블 상세

### `vec.bond_schema_terms`

- 종류: table
- 설명: common+bond TBox 주석 130행 CLOVA bge-m3 임베딩
- grain: 채권 TBox grounding term 1개
- PK: `term_uri`
- 인덱스: embedding vector_cosine_ops (HNSW), content_hash,embedding_model
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `term_uri` | `text` | N | 1 |  |  |  | TBox URI | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `label` | `text` | N |  |  |  |  | 라벨 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `comment` | `text` | N |  |  |  |  | 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `alt_labels` | `text[]` | N |  |  |  |  | 대체 표기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `content` | `text` | N |  |  |  |  | 임베딩 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `content_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `embedding_model` | `text` | N |  |  |  |  | bge-m3 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `embedding_dim` | `smallint` | N |  |  |  |  | 1024 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `embedding` | `vector(1024)` | N |  |  |  |  | CLOVA 임베딩 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `vec.schema_terms_all`

- 종류: table
- 설명: 5개 TBox 주석 189행 CLOVA bge-m3 임베딩
- grain: 전체 TBox grounding term 1개
- PK: `term_uri`
- 인덱스: embedding vector_cosine_ops (HNSW), content_hash,embedding_model
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `term_uri` | `text` | N | 1 |  |  |  | TBox URI | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `label` | `text` | N |  |  |  |  | 라벨 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `comment` | `text` | N |  |  |  |  | 설명 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `alt_labels` | `text[]` | N |  |  |  |  | 대체 표기 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `content` | `text` | N |  |  |  |  | 임베딩 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `content_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `embedding_model` | `text` | N |  |  |  |  | bge-m3 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `embedding_dim` | `smallint` | N |  |  |  |  | 1024 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `embedding` | `vector(1024)` | N |  |  |  |  | CLOVA 임베딩 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `vec.document_chunk`

- 종류: table
- 설명: 문서·상품·페이지·발행일·인용 위치가 있는 콘텐츠 임베딩
- grain: 문서 청크 1개
- PK: `chunk_id`
- 인덱스: embedding vector_cosine_ops (HNSW), document_id, product_id
- 상태: 구현=구현, 배포=미배포

| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |
|---:|---|---|:---:|---:|---|---|---|---|---|---|---|
| 1 | `chunk_id` | `text` | N | 1 |  |  |  | 결정적 청크 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 2 | `document_id` | `text` | N |  | relations.source_document.document_id |  |  | 근거 문서 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 3 | `product_id` | `text` | Y |  | enriched.product_master.product_id |  |  | 연결 상품 ID | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 4 | `page_number` | `integer` | Y |  |  |  |  | 원문 페이지 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 5 | `citation_text` | `text` | N |  |  |  |  | 인용 위치/문장 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `chunk_text` | `text` | N |  |  |  |  | 임베딩 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `published_at` | `date` | N |  |  |  | published_at | 문서 발행일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 8 | `source_url` | `text` | N |  |  |  |  | 원문 URL | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측 축 미존재 시 검증된 외부 원천(2순위) | 파생 |
| 9 | `content_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `embedding_model` | `text` | N |  |  |  |  | bge-m3 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `embedding_dim` | `smallint` | N |  |  |  |  | 1024 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 12 | `embedding` | `vector(1024)` | N |  |  |  |  | CLOVA 임베딩 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

## 검색 계약

```sql
SELECT term_uri, label, comment,
       1 - (embedding <=> %(query_embedding)s::vector) AS cosine_similarity
FROM vec.schema_terms_all
ORDER BY embedding <=> %(query_embedding)s::vector
LIMIT %(top_k)s;
```

상품 후보가 이미 정해진 content 검색은 `product_id = ANY(...)` 조건으로 범위를 먼저 제한합니다.
전용 `tsvector`/GIN 컬럼은 현재 v2 DDL에 없으므로 FTS 하이브리드는 구현 상태로 표기하지 않습니다.

## 빌드와 검증

1. TBox 5개와 cutoff 이하 문서 청크를 읽고 원문 해시 중복을 검사합니다.
2. 기존 `vec_next`와 정식 `vec`에서 같은 모델·원문 해시의 임베딩 캐시를 조회합니다.
3. 누락된 원문만 CLOVA에 보내고 결과가 정확히 1024차원인지 확인합니다.
4. 세 테이블을 upsert한 뒤 cosine HNSW 인덱스를 생성합니다.
5. 행 수, embedding NULL, 차원, 중복 해시, HNSW 인덱스 3개를 검증합니다.

필수 비밀값은 `CLOVA_API_KEY`이며 host는 `CLOVA_HOST`로 주입합니다. 비밀값은 문서·로그·DB에 저장하지 않습니다.
