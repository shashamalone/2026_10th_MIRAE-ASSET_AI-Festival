# VECTORDB DEFINITION V2.0

이 문서는 팀원과 Agent/LLM이 별도 구두 설명 없이 물리 구조와 의미 계약을 재구성할 수 있도록 만든 자급형 정의서입니다.
자동 생성 파일이므로 직접 편집하지 말고 `python src/kb/build_catalog_v2.py`를 실행합니다.
물리 정의의 정본은 [단일 카탈로그](../../src/kb/catalog_v2.py), [Vector DDL](../../sql/v2/001_platform_schema.sql), [임베딩 빌더](../../src/kb/build_vectors_v2.py)입니다.

- 데이터 버전: `financial-products-2026-08-24`
- release ID: `financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38`
- 배포일: `2026-08-24`
- 외부 근거 cutoff: `2026-08-24`

## 이 문서를 읽는 순서

1. 질의가 스키마 의미 검색인지 문서 근거 검색인지 `라우팅 계약`으로 결정합니다.
2. 해당 테이블의 메타데이터 필드로 RDB/Graph 후보 범위를 제한합니다.
3. cosine 결과는 관련도 후보일 뿐 사실 판정이 아니므로 출처·날짜·인용문을 검증합니다.
4. 답변에는 검색 점수만 제시하지 말고 `근거 반환 계약`의 식별자와 provenance를 보존합니다.

## 범위와 엔진

- 엔진: PostgreSQL 17의 pgvector 확장
- 임베딩 계약: CLOVA Studio `bge-m3`, 1024차원(이번 릴리스 신규 호출 없음)
- 거리: cosine distance (`<=>`), 점수 표시는 `1 - distance`
- ANN 인덱스: 유효 벡터가 재사용된 테이블에만 HNSW + `vector_cosine_ops`
- 저장 위치: PostgreSQL `vec` 스키마; 별도 FAISS 운영 경로 없음
- 임베딩 원문과 벡터 산출물은 Git에 커밋하지 않습니다.
- 담당 연산: 자연어↔TBox 용어 grounding, 후보 상품에 한정한 공식 문서 근거 검색
- 비담당 연산: 숫자 정렬·집계는 RDB, 관계 존재와 domain/range 판정은 GraphDB가 담당

## 읽기 인터페이스

Vector 검색은 PostgreSQL 읽기 경로를 공유합니다. 이번 릴리스는 테이블과 `vector(1024)` 계약만 배포하며 신규 CLOVA 호출을 하지 않습니다. 동일 `content_hash`·`bge-m3`·1024차원·cutoff/FK 계약의 운영 벡터를 전부 재사용할 수 있을 때만 `ready`, 아니면 세 테이블을 비우고 `pending`으로 둡니다. API나 팀 계정은 vector INSERT/UPDATE와 인덱스 재생성을 할 수 없습니다.

## 라우팅 계약

| 사용자 의도 | 검색 테이블 | 필수 사전 필터 | 후속 처리 |
|---|---|---|---|
| ‘안전한’, ‘패시브’, ‘발행사’처럼 물리 컬럼이 불명확 | `vec.schema_terms_all` | 선택적 도메인/TBox 파일 | 반환 `term_uri`를 Graph/RDB 메타데이터에 연결 |
| 채권 용어만 grounding | `vec.bond_schema_terms` | 없음 | 채권 TBox 허용값·속성 검사 |
| 상품 투자전략·위험요인·근거문장 | `vec.document_chunk` | `product_id = ANY(...)`, cutoff | `document_id`로 문서 provenance 결합 |
| 숫자 TOP-N·정확 필터 | 검색하지 않음 | 해당 없음 | RDB로 라우팅 |
| 자회사·편입 다중 홉 | 검색하지 않음 | 해당 없음 | Graph로 후보를 정한 뒤 필요할 때 문서 검색 |

RDB/Graph의 정규 상품 식별자와 Vector의 `product_id`는 동일 문자열입니다. `document_id`는 `relations.source_document.document_id`와 동일하며, 페이지·인용문은 `vec.document_chunk`가 소유합니다.

## 인덱스 분리

| 논리 인덱스 | 물리 테이블 | 현재 정의 행 수 | 용도 | 갱신 조건 |
|---|---|---:|---|---|
| 채권 schema grounding | `vec.bond_schema_terms` | 130 | 채권 질의의 TBox 의미 검색 | `common.ttl` 또는 `bond_kr.ttl` 변경 |
| 전체 schema grounding | `vec.schema_terms_all` | 189 | 전 상품군 ontology grounding | TBox 5개 중 하나 변경 |
| content grounding | `vec.document_chunk` | 배포 시 산출 | 문서 근거·인용 검색 | 공식 문서 수집 또는 청크 변경 |

Ontology Index와 Content Index는 목적·필터·갱신주기가 다르므로 같은 테이블에 섞지 않습니다.

## 임베딩 텍스트와 식별 규칙

- TBox term은 `term_uri | rdfs:label | skos:altLabel | rdfs:comment` 순서로 결합합니다.
- 각 TBox term은 `domain_file`과 `property_type`(class/object_property/datatype_property/individual/other)을 별도 메타데이터로 보존합니다.
- 문서 청크는 `document_id`, `product_id`, `page_number`, `citation_text`, `published_at`, `source_url`을 보존합니다.
- `content_hash=SHA-256(원문)`와 `embedding_model`이 같으면 기존 벡터를 재사용합니다.
- 같은 테이블에서 원문 해시 중복을 허용하지 않으며 임베딩 NULL과 1024차원 불일치를 빌드 실패로 처리합니다.
- 문서에는 페이지와 인용문을 저장하지만 별도 문자 offset 컬럼은 아직 구현되지 않았습니다.
- `published_at`이 cutoff를 초과하는 청크가 하나라도 있으면 전체 적재를 중단합니다.
- 자연어 유사도는 관계의 존재, 수치의 참값, 시점 유효성을 증명하지 않습니다. 이 세 가지는 각각 Graph/RDB/날짜 검증으로 확정합니다.

## 테이블 목록

| 스키마 | 테이블 | 종류 | grain | PK | 인덱스 | 상태 |
|---|---|---|---|---|---|---|
| `vec` | `bond_schema_terms` | table | 채권 TBox grounding term 1개 | `term_uri` | embedding vector_cosine_ops (HNSW), content_hash,embedding_model | 구현=구현, 배포=미배포 |
| `vec` | `schema_terms_all` | table | 전체 TBox grounding term 1개 | `term_uri` | embedding vector_cosine_ops (HNSW), content_hash,embedding_model | 구현=구현, 배포=미배포 |
| `vec` | `document_chunk` | table | 문서 청크 1개 | `chunk_id` | embedding vector_cosine_ops (HNSW), document_id, product_id | 구현=구현, 배포=미배포 |

## 물리 테이블 상세

### `vec.bond_schema_terms`

- 종류: table
- 설명: common+bond TBox 주석용 vector(1024) 계약; 동일 해시 운영 벡터만 재사용
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
| 5 | `domain_file` | `text` | N |  |  |  |  | 정의가 위치한 TBox 파일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `property_type` | `text` | N |  |  |  |  | class/object/datatype/individual 구분 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `content` | `text` | N |  |  |  |  | 임베딩 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `content_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `embedding_model` | `text` | N |  |  |  |  | bge-m3 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `embedding_dim` | `smallint` | N |  |  |  |  | 1024 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `embedding` | `vector(1024)` | N |  |  |  |  | CLOVA 임베딩 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `vec.schema_terms_all`

- 종류: table
- 설명: 5개 TBox 주석용 vector(1024) 계약; 신규 임베딩 생성은 후속 릴리스
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
| 5 | `domain_file` | `text` | N |  |  |  |  | 정의가 위치한 TBox 파일 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 6 | `property_type` | `text` | N |  |  |  |  | class/object/datatype/individual 구분 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 7 | `content` | `text` | N |  |  |  |  | 임베딩 원문 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 8 | `content_hash` | `text` | N |  |  |  |  | 원문 SHA-256 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 9 | `embedding_model` | `text` | N |  |  |  |  | bge-m3 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 10 | `embedding_dim` | `smallint` | N |  |  |  |  | 1024 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |
| 11 | `embedding` | `vector(1024)` | N |  |  |  |  | CLOVA 임베딩 | 빈 값=NULL; 0은 원본 값으로 보존 | 주최측(1순위) | 파생 |

### `vec.document_chunk`

- 종류: table
- 설명: 문서·상품·페이지·발행일·인용 위치가 있는 vector(1024) 계약
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
SELECT term_uri, label, comment, domain_file, property_type,
       1 - (embedding <=> %(query_embedding)s::vector) AS cosine_similarity
FROM vec.schema_terms_all
ORDER BY embedding <=> %(query_embedding)s::vector
LIMIT %(top_k)s;
```

상품 후보가 이미 정해진 content 검색은 `product_id = ANY(...)` 조건으로 범위를 먼저 제한합니다.
전용 `tsvector`/GIN 컬럼은 현재 v2 DDL에 없으므로 FTS 하이브리드는 구현 상태로 표기하지 않습니다.

문서 근거 검색의 안전한 형태입니다.

```sql
SELECT chunk_id, document_id, product_id, page_number, citation_text,
       published_at, source_url, 1 - (embedding <=> %(query_embedding)s::vector) AS score
FROM vec.document_chunk
WHERE product_id = ANY(%(candidate_product_ids)s)
  AND published_at <= DATE '2026-08-24'
ORDER BY embedding <=> %(query_embedding)s::vector
LIMIT %(top_k)s;
```

## 근거 반환 계약

- schema grounding: `term_uri`, `label`, `comment`, `domain_file`, cosine score를 반환합니다.
- content grounding: `chunk_id`, `document_id`, `product_id`, `citation_text`, `page_number`, `published_at`, `source_url`, cosine score를 반환합니다.
- 인용문은 저장된 `citation_text` 범위만 사용하며 검색 점수나 모델 추론을 원문 주장처럼 표현하지 않습니다.
- 문서가 없거나 상품 coverage가 `unavailable`이면 ‘위험이 없음’이 아니라 ‘근거 문서 미확보’로 답합니다.
- schema hit만 있는 국내 ETF는 분류 의미까지만 설명하고 투자설명서에 있을 법한 전략 문장을 생성하지 않습니다.

## Graph → RDB → Vector 결합 예

1. Graph가 분류·관계 조건으로 `product_id` 후보를 반환합니다.
2. RDB가 동일 ID의 가용 지표만 정렬해 TOP-N을 정합니다.
3. Vector는 TOP-N ID로 `document_chunk`를 제한해 인용 근거를 찾습니다.
4. 통합기는 상품 ID, 수치별 기준일, 문서 발행일을 서로 덮어쓰지 않고 별도 evidence로 유지합니다.

## 빌드와 검증

1. TBox 5개와 cutoff 이하 문서 청크를 읽고 원문 해시 중복을 검사합니다.
2. 정식 `vec`에서 같은 모델·원문 해시·1024차원의 임베딩만 조회합니다.
3. 모든 입력을 재사용할 수 있으면 적재하고, 하나라도 없으면 세 테이블을 빈 상태로 둡니다.
4. 유효 벡터가 있는 테이블에만 cosine HNSW 인덱스를 생성합니다.
5. 행 수, embedding NULL, 차원, 중복 해시, HNSW, `vector_status`와 읽기 전용 권한을 검증합니다.

신규 임베딩 생성은 별도 후속 릴리스입니다. 이번 단계는 `CLOVA_API_KEY`를 요구하거나 호출하지 않으며 빈 검색 결과를 근거 부재로 해석하지 않습니다.
