# -*- coding: utf-8 -*-
"""경로·모델 상수. 채권 MVP 범위."""
from pathlib import Path

# config.py 는 src/ 안에 있다. .parent = src/, 한 번 더 올려야 저장소 루트다.
# 한 번만 올리면 ARTIFACTS 가 src/artifacts 를 새로 만들며 조용히 캐시를 잃는다.
ROOT = Path(__file__).resolve().parent.parent

# 지시서는 ontology/bond.ttl 하나를 가정하지만 이 저장소의 스키마는 common + 도메인 4로 갈려 있다.
# 테스트 질문의 '위험등급'(fp:RiskGrade·fp:riskGradeLevel)은 common.ttl에만 있어서
# bond_kr.ttl만 인덱싱하면 4문항 중 1문항을 못 답한다. 둘 다 넣는다.
BOND_TTL_PATHS = [ROOT / "ontology" / "bond_kr.ttl", ROOT / "ontology" / "common.ttl"]

ARTIFACTS = ROOT / "artifacts"

# 스키마 벡터 인덱스는 PostgreSQL + pgvector 에 둔다(FAISS 에서 이전, 2026-08-22).
# 이전 근거는 vectordb_test/results/1_pgvector_test_report.md — cosine 점수가
# FAISS(정규화 후 IndexFlatIP)와 최대 오차 5.03e-07 로 일치해 임계값을 그대로 쓴다.
# 비밀번호를 포함하므로 DSN 을 로그에 찍지 않는다. 접속 정보는 환경변수로 덮을 수 있다.
import os
# Azure Data API
# 현재 공개 테스트 API는 임시 주소다. 운영에서는 환경변수로 반드시 덮어쓴다.
FINANCIAL_DATA_API_URL = os.environ.get(
    "FINANCIAL_DATA_API_URL",
    "http://40.82.145.44:8000",
)
FINANCIAL_DATA_RELEASE_ID = os.environ.get(
    "FINANCIAL_DATA_RELEASE_ID",
    "financial-products-2026-08-24@"
    "ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38",
)
DATA_API_TIMEOUT_SECONDS = float(
    os.environ.get("DATA_API_TIMEOUT_SECONDS", "10")
)

# Direct PostgreSQL connection.
# Existing rdb/bond_schema tools still use this configuration.
BOND_DB = {
    "host": os.environ.get("PGHOST", "127.0.0.1"),
    "port": os.environ.get("PGPORT", "5432"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", "postgres"),
    "dbname": os.environ.get("PGDATABASE", "mafest"),
}
# 유닉스 소켓은 peer 인증에 걸린다. host 를 명시해 TCP 로 붙는다.
BOND_DSN = " ".join(f"{k}={v}" for k, v in BOND_DB.items())
BOND_TABLE = "bond_schema_terms"
EMBED_DIM = 1024

BOND_TOP_K = 5
# cosine 점수 하한. 실측상 0.36~0.38대는 무관한 용어(자회사 관계 등)가 섞인다.
# 빈약한 근거를 주면 모델이 일반 지식으로 메워 근거 없는 단정이 나온다.
BOND_SCORE_FLOOR = 0.45

EMBEDDING_MODEL = "bge-m3"        # 1024차원, cosine (CLOVA Studio)
# 1단계 Query Frame 추출. HCX-005·HCX-DASH-002 와 대표 4문항으로 비교해 정했다 —
# 스키마 준수 4/4 vs 2/4 vs 1/4. DASH-002 의 속도 이점은 프롬프트가 길어지면서
# 사라졌다(출력 토큰이 지연을 지배한다). 근거: vectordb_test/4_query_frame_v1/4_result_query_frame_v1.md
FRAME_MODEL = "HCX-007"
ANSWER_MODEL = "HCX-005"          # 답변 생성
CHAT_TIMEOUT_SECONDS = 13           # API tail stall은 재시도 없이 ABSTAIN해 15초 E2E를 지킨다

CLOVA_HOST = "https://clovastudio.stream.ntruss.com"

# --- 콘텐츠 벡터 인덱스 (검증: EXP-20260828-vector-01) ---
CONTENT_TABLE = "vec.document_chunk"
CONTENT_TOP_K = 3                   # V01~V08 검증 시 top_k=3, 정답 문서 전부 top-1
CONTENT_SCORE_FLOOR = 0.45          # bge-m3 cosine — 무관 질의(V08)가 0.43으로 정상 차단됨
PDF_DEMO_DIR = ROOT / "data" / "pdf_demo"
