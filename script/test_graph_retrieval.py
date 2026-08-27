#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로컬 Graph 검색 템플릿 회귀 (EXP-20260828-graph-01 승격분).

전제: artifacts/oxigraph 가 cutoff 2026-08-24 로 빌드돼 있어야 한다
(python3 src/kb/build_graph.py). LLM·네트워크 미사용.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from config import ARTIFACTS  # noqa: E402
from tools import graph as G  # noqa: E402

man = json.loads((ARTIFACTS / "oxigraph" / "manifest.json").read_text(encoding="utf-8"))
assert man["cutoff"] == "2026-08-24", f"store cutoff={man['cutoff']} — 재빌드 필요"

# 상품 조회 (G01) + 부재 → empty
r = G.product_info("KODEX 200")
assert r["status"] == "ok" and r["rows"][0]["code"] == "KR7069500007", r
assert G.product_info("존재하지않는상품명XYZ")["status"] == "empty"

# 기업→자회사 (G04): as_of·supportedBy 근거 포함
r = G.subsidiaries("에코프로")
assert r["status"] == "ok", r
assert any(x.get("as_of") for x in r["rows"]) and any(x.get("doc_title") for x in r["rows"])

# 상품→편입 증권 (G05) / 증권→ETF 역방향 (G06)
r = G.product_holdings("KODEX 200", 10)
assert r["status"] == "ok" and len(r["rows"]) == 10, r
assert G.etfs_holding_security("삼성전자")["status"] == "ok"

# 자회사 편입 ETF 경로 (G07) — 코드 포함 버전
r = G.subsidiary_holding_etf_codes("에코프로")
assert r["status"] == "ok" and all(x.get("etf_code") for x in r["rows"]), r

# 펀드 편입 미적재는 empty 가 아니라 data_gap (G10)
r = G.fund_holdings_check()
assert r["status"] == "data_gap", r

# 도메인 위반 거부 (G11): ETF 가 주어인 fp:issuedBy
r = G.domain_violation("VOO", "issuedBy")
assert r["status"] == "abstain_domain_error", r

# 갱신 쿼리 차단
try:
    G.sparql("INSERT DATA { <urn:a> <urn:b> <urn:c> }")
    raise AssertionError("INSERT 차단 실패")
except ValueError:
    pass

print("PASS test_graph_retrieval")
