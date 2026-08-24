# -*- coding: utf-8 -*-
"""실제 평가 질문 35문항에 한국어 FTS 가 몇 건이나 걸리는지 실측.

앞서 "35문항은 전부 자연어라 FTS 가 사실상 전멸한다"고 단정했는데
그건 재보지 않은 추정이었다. 여기서 실제로 센다.
"""
import csv
import sys
from pathlib import Path

import psycopg

# config.py 는 형제 폴더에 있다(폴더 재편). 저장소 루트보다 먼저 넣어야
# 루트 config.py 가 아니라 이 테스트용 config.py 가 잡힌다.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent
                       / "1_pgvector_test"))
from config import DSN

CSV = Path(__file__).resolve().parent.parent / "expected_question" / "2026_expected_queries.csv"

rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
assert len(rows) == 35, f"35문항이 아님: {len(rows)}"

conn = psycopg.connect(DSN, autocommit=True)
hit = miss = 0
detail = []
for r in rows:
    q = r["question"]
    res = conn.execute(
        "SELECT term_uri FROM terms130"
        " WHERE to_tsvector('simple',content) @@ plainto_tsquery('simple',%(q)s)"
        " ORDER BY ts_rank(to_tsvector('simple',content),"
        "                  plainto_tsquery('simple',%(q)s)) DESC LIMIT 3",
        {"q": q}).fetchall()
    (hit := hit + 1) if res else (miss := miss + 1)
    detail.append((r["id"], len(res), q))
conn.close()

print(f"평가 질문 35문항 중 FTS(simple) 적중: {hit}건 / 무적중: {miss}건")
print(f"  → 무적중 비율 {miss/35:.0%}")
print("\n[FTS 가 무언가 잡은 문항]")
for i, n, q in detail:
    if n:
        print(f"  #{i:<3} {q[:58]}…")
