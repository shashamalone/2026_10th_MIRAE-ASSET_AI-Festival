#!/usr/bin/env python3
"""실제 pyoxigraph Store의 최초 관계 경로와 안전 계약을 검사한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kb.build_graph import MANIFEST  # noqa: E402
from tools.graph import ecopro_subsidiary_etfs, sparql  # noqa: E402

CUTOFF = "2026-07-11"


def metrics() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = ecopro_subsidiary_etfs()
    assert rows, "에코프로→자회사→편입증권→ETF 결과가 0건"
    assert all(x["holding_as_of"] <= CUTOFF and x["relation_as_of"] <= CUTOFF
               for x in rows)
    assert all(x["holding_source"] and x["relation_source"] for x in rows)
    distinct_etfs = len({x["etf"] for x in rows})
    assert distinct_etfs >= 30
    try:
        sparql("DELETE WHERE { ?s ?p ?o }")
    except ValueError:
        readonly_rejection = True
    else:
        readonly_rejection = False
    assert readonly_rejection
    try:
        sparql("SELECT ?s WHERE { SERVICE <https://example.com/sparql> { ?s ?p ?o } }")
    except ValueError:
        service_rejection = True
    else:
        service_rejection = False
    assert service_rejection
    # 현재 ABox는 supportedBy 문서 노드를 만들지 않아 최종 답변 승격은 보류한다.
    result = {
        "cutoff": CUTOFF,
        "triple_count": manifest["triple_count"],
        "excluded_future_nodes": manifest["excluded_future_nodes"],
        "future_as_of_count": manifest["future_as_of_count"],
        "ecopro_path_rows": len(rows),
        "distinct_etfs": distinct_etfs,
        "etn_rows": 0,
        "relation_evidence_coverage": 1.0,
        "supported_by_coverage": 0.0,
        "readonly_rejection": readonly_rejection,
        "service_rejection": service_rejection,
        "graph_execution_pass": True,
        "graph_only_promotion_ready": False,
        "blocker": "fp:supportedBy 문서 evidence 인스턴스 없음",
    }
    print("PASS graph execution — " + json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    metrics()
