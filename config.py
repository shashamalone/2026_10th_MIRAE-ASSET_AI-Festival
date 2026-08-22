# -*- coding: utf-8 -*-
"""경로·모델 상수. 채권 MVP 범위."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 지시서는 ontology/bond.ttl 하나를 가정하지만 이 저장소의 스키마는 common + 도메인 4로 갈려 있다.
# 테스트 질문의 '위험등급'(fp:RiskGrade·fp:riskGradeLevel)은 common.ttl에만 있어서
# bond_kr.ttl만 인덱싱하면 4문항 중 1문항을 못 답한다. 둘 다 넣는다.
BOND_TTL_PATHS = [ROOT / "ontology" / "bond_kr.ttl", ROOT / "ontology" / "common.ttl"]

ARTIFACTS = ROOT / "artifacts"
BOND_INDEX_PATH = ARTIFACTS / "bond.faiss"
BOND_TERMS_PATH = ARTIFACTS / "bond_terms.json"

BOND_TOP_K = 5
# cosine 점수 하한. 실측상 0.36~0.38대는 무관한 용어(자회사 관계 등)가 섞인다.
# 빈약한 근거를 주면 모델이 일반 지식으로 메워 근거 없는 단정이 나온다.
BOND_SCORE_FLOOR = 0.45

EMBEDDING_MODEL = "bge-m3"        # 1024차원, cosine (CLOVA Studio)
INTENT_MODEL = "HCX-DASH-002"     # 분류 전용 — 가장 빠름 (실측 0.29s)
ANSWER_MODEL = "HCX-005"          # 답변 생성

CLOVA_HOST = "https://clovastudio.stream.ntruss.com"
