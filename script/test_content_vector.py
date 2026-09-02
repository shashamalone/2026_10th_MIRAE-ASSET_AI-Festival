#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로컬 콘텐츠 벡터 검색 회귀 (EXP-20260828-vector-01 승격분).

전제: vec.document_chunk 적재 (python3 src/kb/build_content_index.py).
CLOVA 임베딩 1~3회 호출 (artifacts/embed_cache.json 캐시).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tools import content  # noqa: E402

r = content.search("국민성장펀드의 구조와 투자전략")
if r["retrieval_status"] == "pending":
    sys.exit("SKIP  인덱스 미구축 — python3 src/kb/build_content_index.py 후 재실행: "
             + " / ".join(r["trace"]))
assert r["retrieval_status"] == "ok", r["trace"]
assert all({"source", "text", "score", "document_id", "as_of"} <= set(e) for e in r["evidence"])
assert any("국민성장" in e["document_id"] for e in r["evidence"]), \
    [e["document_id"] for e in r["evidence"]]
assert all(e["as_of"] <= "2026-08-24" for e in r["evidence"])  # look-ahead 금지

r = content.search("TIGER MSCI Korea TR이 추종하는 지수와 기초자산")
assert r["retrieval_status"] == "ok", r["trace"]
assert "TIGERMSCIKOREA" in r["evidence"][0]["document_id"].replace(" ", "").upper(), \
    r["evidence"][0]["document_id"]

# floor 미달 → empty, evidence 생성 금지 (규칙 4)
r = content.search("전혀 무관한 임의의 텍스트 qwerty asdf", floor=0.99)
assert r["retrieval_status"] == "empty" and r["evidence"] == [], r

print("PASS test_content")
