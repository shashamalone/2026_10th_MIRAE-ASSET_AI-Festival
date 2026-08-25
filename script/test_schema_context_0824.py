#!/usr/bin/env python3
"""08-24 채권 매수가능 의미와 복합 join key 회귀 검사."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tools.rdb import compile_plan  # noqa: E402
from tools.schema_context import ground, metadata  # noqa: E402


def main():
    metadata.cache_clear()
    plan = ground("매수 가능한 회사채", {
        "domain_candidates": ["bond_kr"], "task": "filter_rank", "entities": [],
        "requested_fields": [{"text": "잔존일수"}],
        "constraints": [{"raw": "매수 가능한 회사채", "field_text": "매수 가능"}],
        "ordering": [],
    })
    assert not plan["unresolved"], plan
    assert any(f["binding"] == "bond.remaining_days" and f["operator"] == ">"
               and f["value"] == 0 for f in plan["filters"]), plan["filters"]
    assert all(f["binding"] != "bond.buyable_quantity" for f in plan["filters"])

    query = compile_plan(plan).query.as_string()
    assert "buyable_quantity" not in query
    for key in ("pd_no", "pd_exg_mkt", "info_seq"):
        assert query.count(f'"{key}"') >= 2, query

    explicit = ground("매수가능수량이 0보다 큰 채권", {
        "domain_candidates": ["bond_kr"], "task": "filter_rank", "entities": [],
        "requested_fields": [{"text": "매수수익률"}, {"text": "매수가능수량"}],
        "constraints": [{"raw": "매수가능수량이 0보다 큰",
                         "field_text": "매수가능수량", "operator": ">", "value_num": 0}],
        "ordering": [],
    })
    assert not explicit["unresolved"], explicit
    assert any(f["binding"] == "bond.remaining_days" and f["operator"] == ">"
               and f["value"] == 0 for f in explicit["filters"]), explicit
    assert all(f["binding"] != "bond.buyable_quantity" for f in explicit["filters"])
    assert "bond.applied_yield" in explicit["select"]
    assert "bond.buyable_quantity" not in explicit["select"]
    print("PASS 08-24 매수가능 라우팅 + 채권 복합 join key")


if __name__ == "__main__":
    main()
