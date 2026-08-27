#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""현재 TTL 10개를 persistent pyoxigraph Store로 구축·검증한다."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import ARTIFACTS, ROOT  # noqa: E402

try:
    from pyoxigraph import RdfFormat, Store
except ImportError as exc:  # pragma: no cover - 설치 안내 경로
    raise SystemExit("pyoxigraph 미설치 — python3 -m pip install -r requirements.txt") from exc

CUTOFF = "2026-07-11"
OUT = ARTIFACTS / "oxigraph"
MANIFEST = OUT / "manifest.json"
TBOX = ("common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl")
ABOX = ("instances_bond_kr.ttl", "instances_etf_kr.ttl", "instances_etf_gl.ttl",
        "instances_fund_pub.ttl", "instances_company.ttl")
FILES = TBOX + ABOX

PREFIX = """
PREFIX fp: <http://mafest.ai/product#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
REQUIRED_PATH = PREFIX + """
ASK {
  ?parent fp:hasSubsidiary ?relation .
  ?relation fp:subsidiaryCompany ?company .
  ?security fp:issuedByCompany ?company .
  ?holding fp:holdingSecurity ?security .
  ?etf fp:hasHolding ?holding .
}
"""
FUTURE_COUNT = PREFIX + f"""
SELECT (COUNT(?node) AS ?count) WHERE {{
  ?node fp:asOf ?as_of .
  FILTER (?as_of > \"{CUTOFF}\"^^xsd:date)
}}
"""
DROP_FUTURE = PREFIX + f"""
DELETE {{ ?node ?predicate ?object . ?subject ?incoming ?node }} WHERE {{
  ?node fp:asOf ?as_of .
  FILTER (?as_of > \"{CUTOFF}\"^^xsd:date)
  {{ ?node ?predicate ?object }} UNION {{ ?subject ?incoming ?node }}
}}
"""


def inputs() -> list[Path]:
    paths = [ROOT / "ontology" / name for name in FILES]
    missing = [str(path.relative_to(ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("TTL 입력 누락: " + ", ".join(missing))
    return paths


def _scalar(store: Store, query: str, name: str) -> int:
    row = next(iter(store.query(query)))
    return int(row[name].value)


def validate_store(store: Store) -> dict:
    triples = len(store)
    if not triples:
        raise ValueError("Oxigraph store가 비어 있습니다")
    if not bool(store.query(REQUIRED_PATH)):
        raise ValueError("필수 Graph 경로 Company→Subsidiary→Security→Holding→ETF가 없습니다")
    future = _scalar(store, FUTURE_COUNT, "count")
    if future:
        raise ValueError(f"fp:asOf가 cutoff {CUTOFF}를 넘는 노드 {future:,}건")
    return {"triple_count": triples, "future_as_of_count": future, "cutoff": CUTOFF,
            "ttl_files": list(FILES)}


def build() -> dict:
    paths = inputs()
    ARTIFACTS.mkdir(exist_ok=True)
    if OUT.exists():
        raise FileExistsError(f"기존 store를 덮어쓰지 않습니다: {OUT}")
    with tempfile.TemporaryDirectory(prefix=".oxigraph-", dir=ARTIFACTS) as tmp:
        candidate = Path(tmp) / "store"
        store = Store(str(candidate))
        for path in paths:
            store.bulk_load(path=str(path), format=RdfFormat.TURTLE)
            print(f"load {path.relative_to(ROOT)}")
        excluded = _scalar(store, FUTURE_COUNT, "count")
        if excluded:
            store.update(DROP_FUTURE)
            print(f"exclude future relation nodes: {excluded:,}")
        store.flush()
        result = validate_store(store)
        result["excluded_future_nodes"] = excluded
        del store
        candidate.replace(OUT)
    MANIFEST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return result


def check() -> dict:
    inputs()
    if not OUT.is_dir():
        raise ValueError(f"Graph store가 없습니다: {OUT}")
    return validate_store(Store.read_only(str(OUT)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = check() if args.check else build()
    print("PASS " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
