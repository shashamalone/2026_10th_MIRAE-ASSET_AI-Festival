# -*- coding: utf-8 -*-
"""채권 스키마 벡터 검색 (PostgreSQL + pgvector).

접속은 프로세스당 한 번만 연다. 매 검색마다 다시 연결하면 질의 하나에 수십 ms가 붙어
응답 예산(60초 권장, 15초 목표)을 갉아먹는다.

FAISS 에서 이전했다(2026-08-22). cosine 점수가 FAISS(정규화 후 IndexFlatIP)와
최대 오차 5.03e-07 로 일치하므로 BOND_SCORE_FLOOR 를 그대로 쓴다.
근거: vectordb_test/results/1_pgvector_test_report.md, script/test_pgvector_migration.py
"""
import sys
from functools import lru_cache
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (BOND_DSN, BOND_SCORE_FLOOR, BOND_TABLE,  # noqa: E402
                    BOND_TOP_K)
import clova  # noqa: E402


@lru_cache(maxsize=1)
def _conn():
    # ponytail: 단일 커넥션. api.py 가 동시 요청을 받게 되면 psycopg_pool 로 바꾼다.
    try:
        c = psycopg.connect(BOND_DSN, autocommit=True)
    except psycopg.OperationalError as e:
        raise SystemExit(f"pgvector 접속 실패 — {e}\n"
                         f"  PostgreSQL 이 떠 있는지, 먼저 python3 kb/build_bond_index.py 를"
                         f" 실행했는지 확인하라") from e
    n = c.execute(f"SELECT count(*) FROM {BOND_TABLE}").fetchone()[0]
    if not n:
        raise SystemExit(f"{BOND_TABLE} 이 비어 있다 — python3 kb/build_bond_index.py 를 실행하라")
    return c


def bond_schema_search(text: str, k: int = BOND_TOP_K,
                       floor: float = BOND_SCORE_FLOOR) -> list[dict]:
    """질문 → 관련 채권 스키마 용어 Top-K. score는 cosine 유사도(1에 가까울수록 유사).

    자르는 순서가 FAISS 때와 같아야 한다 — 먼저 k개를 뽑고, 그 다음 floor 로 거른다.
    floor 를 SQL WHERE 로 내리면 하한을 넘는 것 중 상위 k개가 나와 결과가 더 많아진다.
    (이 순서 자체는 알려진 결함이다. 근거 없는 용어가 k 슬롯을 먼저 차지할 수 있다 —
     vectordb_test/3_baseline_130_v2/baseline_130_v2_report.md §7 정책 2 참조.
     이번 이전은 엔진만 바꾸는 범위라 동작을 그대로 옮긴다.)
    """
    if not text or not text.strip():
        return []
    q = str(list(map(float, clova.embed(text))))
    rows = _conn().execute(
        f"""SELECT term_uri, label, comment, 1 - (embedding <=> %(q)s::vector) AS score
              FROM {BOND_TABLE}
             ORDER BY embedding <=> %(q)s::vector
             LIMIT %(k)s""",
        {"q": q, "k": k},
    ).fetchall()
    out = []
    for term_uri, label, comment, score in rows:
        if float(score) < floor:
            continue          # 하한 미달은 버린다. 억지로 K개를 채우지 않는다
        out.append({"term_uri": term_uri, "label": label,
                    "comment": comment, "score": round(float(score), 4)})
    return out
