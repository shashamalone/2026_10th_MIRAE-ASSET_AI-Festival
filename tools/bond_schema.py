# -*- coding: utf-8 -*-
"""채권 스키마 벡터 검색.

FAISS 인덱스와 term JSON은 프로세스당 한 번만 읽는다. 매 검색마다 다시 읽으면
질의 하나에 수백 ms가 붙어 응답 예산(60초 권장, 15초 목표)을 갉아먹는다.
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (BOND_INDEX_PATH, BOND_SCORE_FLOOR,  # noqa: E402
                    BOND_TERMS_PATH, BOND_TOP_K)
import clova  # noqa: E402


@lru_cache(maxsize=1)
def _load():
    if not BOND_INDEX_PATH.exists():
        raise SystemExit(f"인덱스 없음: {BOND_INDEX_PATH}\n  먼저 python3 kb/build_bond_index.py 를 실행하라")
    index = faiss.read_index(str(BOND_INDEX_PATH))
    terms = json.loads(BOND_TERMS_PATH.read_text(encoding="utf-8"))
    if index.ntotal != len(terms):
        raise SystemExit(f"인덱스와 term JSON 불일치: {index.ntotal} vs {len(terms)} — 재빌드 필요")
    return index, terms


def bond_schema_search(text: str, k: int = BOND_TOP_K,
                       floor: float = BOND_SCORE_FLOOR) -> list[dict]:
    """질문 → 관련 채권 스키마 용어 Top-K. score는 cosine 유사도(1에 가까울수록 유사)."""
    if not text or not text.strip():
        return []
    index, terms = _load()
    q = np.asarray([clova.embed(text)], dtype=np.float32)
    faiss.normalize_L2(q)
    scores, ids = index.search(q, min(k, index.ntotal))
    out = []
    for score, i in zip(scores[0], ids[0]):
        if i < 0:
            continue
        if float(score) < floor:
            continue          # 하한 미달은 버린다. 억지로 K개를 채우지 않는다
        t = terms[int(i)]
        out.append({"term_uri": t["term_uri"], "label": t["label"],
                    "comment": t["comment"], "score": round(float(score), 4)})
    return out
