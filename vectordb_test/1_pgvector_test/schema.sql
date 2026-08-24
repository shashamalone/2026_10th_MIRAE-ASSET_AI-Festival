-- vectordb_test — 벡터 + FTS 하이브리드 검증용 최소 스키마
-- 적용: psql -h 127.0.0.1 -U postgres -d vectordb_test -f schema.sql

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- 한국어 부분어 매칭 폴백 검증용

DROP TABLE IF EXISTS documents;

CREATE TABLE documents (
    id        bigserial PRIMARY KEY,
    doc_key   text UNIQUE NOT NULL,          -- 결과 대조용 안정 키 (fp:duration 등)
    lang      text NOT NULL CHECK (lang IN ('ko', 'en')),
    content   text NOT NULL,
    -- bge-m3 (CLOVA Studio) 1024차원. 정규화하지 않은 원본 벡터를 저장한다.
    -- <=> (vector_cosine_ops) 는 내부에서 정규화하므로 결과는 정규화 여부와 무관하다.
    embedding vector(1024) NOT NULL
);

-- Full Text Search — 두 설정을 나란히 두고 한국어 동작을 실측한다.
-- PostgreSQL 기본 배포에는 한국어 형태소 분석기(korean 설정)가 없다.
CREATE INDEX documents_fts_simple_idx
    ON documents USING gin (to_tsvector('simple', content));
CREATE INDEX documents_fts_english_idx
    ON documents USING gin (to_tsvector('english', content));

-- 부분어/조사 결합 질의 폴백 후보
CREATE INDEX documents_content_trgm_idx
    ON documents USING gin (content gin_trgm_ops);

-- 벡터 — cosine. 10건짜리 테스트에선 플래너가 seq scan 을 고르지만
-- 인덱스 생성 자체가 되는지, 결과가 일치하는지를 본다.
CREATE INDEX documents_embedding_hnsw_idx
    ON documents USING hnsw (embedding vector_cosine_ops);
