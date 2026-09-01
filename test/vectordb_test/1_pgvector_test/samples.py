# -*- coding: utf-8 -*-
"""샘플 문서 10건과 질의 목록.

영문 5건은 지시서의 통과 기준 확인용, 한국어 5건은 실제 코퍼스다.
한국어 문서는 artifacts/bond_terms.json 의 text 필드를 그대로 가져왔다
(ontology/bond_kr.ttl · common.ttl 의 rdfs:label + rdfs:comment 조합).
문장을 지어내면 실제 인덱스 텍스트와 토큰 모양이 달라져 FTS 실측이 무의미해진다.
"""

DOCS = [
    # --- 영문 5건 (지시서 예시 계열) --------------------------------------
    ("en:dog",    "en", "The dog is barking loudly in the yard."),
    ("en:cat",    "en", "A cat is sleeping quietly on the warm windowsill."),
    ("en:pg",     "en", "PostgreSQL is an open source object-relational database system."),
    ("en:vector", "en", "Vector similarity search finds nearest neighbors in embedding space."),
    ("en:market", "en", "The stock market closed higher on strong quarterly earnings reports."),

    # --- 한국어 5건 (artifacts/bond_terms.json 원문 그대로) ----------------
    ("fp:duration", "ko",
     "fp:duration | 듀레이션 | 금리 민감도. **0이 8,268건이며 만기경과와 미계산이 섞여 "
     "있으므로 듀레이션 질의 시 0 제외가 필수**다. 익일 계열(NDY_DUR)과 컨벡시티는 "
     "중복·고급축이라 온톨로지에 싣지 않았다."),
    ("fp:riskGradeLevel", "ko",
     "fp:riskGradeLevel | 위험등급 수준 | 1=최고위험 … 6=최저위험. 채권·국내ETF·공모펀드 "
     "세 도메인의 서열 방향이 모두 같다."),
    ("fp:ratingRank", "ko",
     "fp:ratingRank | 신용등급 서열 | 1=AAA(최상) … 19=C(최하). 'AA- 이상'은 "
     "fp:ratingRank <= 4로 판정한다. data/enriched/bond_kr_enriched.csv의 crd_grd_rank와 "
     "동일 체계이므로 RDB 선필터와 온톨로지 판정 결과가 일치한다."),
    ("fp:couponRate", "ko",
     "fp:couponRate | 표면금리 | 액면 대비 연 이표율(%). **0은 결측이 아니라 "
     "무이표(할인채)**를 뜻한다."),
    ("fp:maturityBucket", "ko",
     "fp:maturityBucket | 잔존만기 구간 | 만기경과 / 1년미만 / 1-3년 / 3-5년 / 5-10년 / "
     "10년이상 / 미상(파생). fp:hasMaturityClass 개체 매핑의 소재다."),
]

# 질의 — (질의문, 기대 doc_key 또는 None, 메모)
# 기대값은 '벡터 검색이 1위로 올려야 하는 문서'다. FTS 기대값은 별도로 두지 않는다
# (한국어에서 FTS 가 무엇을 못 잡는지 자체가 측정 대상이라서).
QUERIES = [
    ("barking dog",       "en:dog",            "영문 정상 동작 확인"),
    ("듀레이션",           "fp:duration",       "정확 어절 — FTS 도 잡아야 정상"),
    ("위험등급",           "fp:riskGradeLevel", "정확 어절 (문서엔 '위험등급 수준')"),
    ("금리 민감도",        "fp:duration",       "복합 어절 2개 — 둘 다 원문에 존재"),
    ("듀레이션이 뭐야?",   "fp:duration",       "조사 결합 — 한국어 FTS 최대 약점"),
    ("등급",              "fp:riskGradeLevel", "부분어 — '위험등급' 안에 있으나 어절이 아님"),
    ("채권 이자율",        "fp:couponRate",     "동의어(표면금리) — 어휘 불일치, 벡터만 가능"),
]


def query_vectors():
    """질의 임베딩을 한 번에 받아 {질의: 벡터} 로 돌려준다.

    seed.py 가 같은 문자열을 이미 임베딩해 뒀으므로 디스크 캐시에서 바로 나온다
    (API 호출 0건). 루프에서 embed() 를 연타하면 429 를 맞는다.
    """
    import clovax
    qs = [q for q, _, _ in QUERIES]
    return dict(zip(qs, clovax.embed_many(qs, progress=False)))
