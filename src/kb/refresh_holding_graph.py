"""Build a deterministic Graph bundle with refreshed ETF holdings.

The official/product and non-holding relationship triples are preserved from
the last verified bundle.  Only ``fp:Holding`` nodes and ``fp:hasHolding``
edges are replaced.  The source bundle is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD


FP = Namespace("http://mafest.ai/product#")
FPI = Namespace("http://mafest.ai/instance/")

GRAPH_NAMES = {
    "tbox/common.ttl": "http://mafest.ai/graph/tbox/common",
    "tbox/bond_kr.ttl": "http://mafest.ai/graph/tbox/bond_kr",
    "tbox/etf_kr.ttl": "http://mafest.ai/graph/tbox/etf_kr",
    "tbox/etf_gl.ttl": "http://mafest.ai/graph/tbox/etf_gl",
    "tbox/fund_pub.ttl": "http://mafest.ai/graph/tbox/fund_pub",
    "abox/instances_bond_kr.ttl": "http://mafest.ai/graph/abox/bond_kr",
    "abox/instances_company.ttl": "http://mafest.ai/graph/abox/company",
    "abox/instances_etf_gl.ttl": "http://mafest.ai/graph/abox/etf_gl",
    "abox/instances_etf_kr.ttl": "http://mafest.ai/graph/abox/etf_kr",
    "abox/instances_fund_pub.ttl": "http://mafest.ai/graph/abox/fund_pub",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def escaped(value: object) -> str:
    """Match the legacy instance URI escaping rule."""
    output: list[str] = []
    for character in str(value):
        codepoint = ord(character)
        if character.isascii() and (character.isalnum() or character in "_-"):
            output.append(character)
        elif 0xAC00 <= codepoint <= 0xD7A3 or 0x3400 <= codepoint <= 0x9FFF:
            output.append(character)
        else:
            output.append(quote(character, safe=""))
    return "".join(output)


def normalize_security_code(raw: str, code_type: str) -> str:
    raw = raw.strip()
    if code_type == "isin" and raw.startswith("KR7") and len(raw) == 12:
        return raw[3:9]
    return raw


def decimal_literal(value: object) -> Literal | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    try:
        return Literal(Decimal(text), datatype=XSD.decimal, normalize=True)
    except InvalidOperation:
        return None


def parse_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(path, format="turtle")
    return graph


def serialize_sorted(graph: Graph, path: Path, heading: str) -> None:
    """Write deterministic N-Triples-compatible Turtle."""
    lines = [
        "# " + heading,
        "# Deterministic one-triple-per-line Turtle; generated file, do not edit.",
        "",
    ]
    lines.extend(
        sorted(f"{subject.n3()} {predicate.n3()} {obj.n3()} ." for subject, predicate, obj in graph)
    )
    value = ("\n".join(lines) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def remove_old_holdings(graph: Graph) -> int:
    nodes = set(graph.subjects(RDF.type, FP.Holding))
    nodes.update(graph.objects(None, FP.hasHolding))
    for subject, obj in list(graph.subject_objects(FP.hasHolding)):
        graph.remove((subject, FP.hasHolding, obj))
    for node in nodes:
        graph.remove((node, None, None))
        graph.remove((None, None, node))
    return len(nodes)


def product_map(graph: Graph) -> dict[str, URIRef]:
    output: dict[str, URIRef] = {}
    for subject, code in graph.subject_objects(FP.productCode):
        output[str(code)] = subject
    return output


def security_map(graph: Graph) -> dict[str, URIRef]:
    output: dict[str, URIRef] = {}
    for subject, code in graph.subject_objects(FP.securityCode):
        output.setdefault(str(code), subject)
    return output


def load_inputs(relation_path: Path, provenance_path: Path, master_path: Path):
    relation = pd.read_csv(relation_path, dtype=str, keep_default_na=False)
    required = {
        "pd_itm_no",
        "holding_code_raw",
        "holding_code_type",
        "holding_name",
        "weight",
        "source",
        "as_of",
    }
    missing = sorted(required - set(relation.columns))
    if missing:
        raise ValueError(f"relation missing columns: {missing}")
    dates = sorted(set(relation["as_of"]))
    if dates != ["2026-08-21"]:
        raise ValueError(f"relation must contain only 2026-08-21, got {dates}")
    relation = relation.sort_values(
        ["pd_itm_no", "holding_code_raw", "holding_name", "weight"],
        kind="stable",
    ).copy()
    relation["sequence"] = relation.groupby(["pd_itm_no", "holding_code_raw"]).cumcount()
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("snapshot_as_of") != "2026-08-21":
        raise ValueError("provenance snapshot date mismatch")
    if provenance.get("relation_sha256") != sha256_file(relation_path):
        raise ValueError("relation hash does not match provenance")
    master = pd.read_csv(master_path, dtype=str, keep_default_na=False)
    master = master.loc[master["pd_grp_no"].eq("ETF")]
    return relation, provenance, master


def build(args: argparse.Namespace) -> dict:
    baseline = args.baseline_dir.resolve()
    output_root = args.output_dir.resolve()
    if output_root == baseline or baseline in output_root.parents:
        raise ValueError("output bundle must not be inside the immutable baseline")

    relation, provenance, master = load_inputs(
        args.relation.resolve(), args.provenance.resolve(), args.master.resolve()
    )
    source_etf = baseline / "instances_etf_kr.ttl"
    source_company = baseline / "instances_company.ttl"
    etf_graph = parse_graph(source_etf)
    company_graph = parse_graph(source_company)
    removed_holdings = remove_old_holdings(etf_graph)
    products = product_map(etf_graph)
    missing_products = sorted(set(relation["pd_itm_no"]) - set(products))
    if missing_products:
        raise ValueError(f"{len(missing_products)} relation products absent from baseline: {missing_products[:10]}")

    ticker_to_product = {
        row.pd_itm_no_ma[1:]: products[row.pd_itm_no]
        for row in master.itertuples(index=False)
        if row.pd_itm_no in products and row.pd_itm_no_ma
    }
    securities = security_map(company_graph)
    entries_by_isin = {
        value["isin"]: value for value in provenance.get("entries", {}).values()
    }
    missing_provenance = sorted(set(relation["pd_itm_no"]) - set(entries_by_isin))
    if missing_provenance:
        raise ValueError(f"relation products missing provenance: {missing_provenance[:10]}")

    document_nodes: dict[str, URIRef] = {}
    new_security_nodes: set[URIRef] = set()
    for row in relation.itertuples(index=False):
        product = products[row.pd_itm_no]
        holding = URIRef(
            FPI
            + f"hold-{escaped(row.pd_itm_no)}-{escaped(row.holding_code_raw)}-{row.sequence}"
        )
        normalized = normalize_security_code(row.holding_code_raw, row.holding_code_type)
        security = ticker_to_product.get(normalized) or securities.get(normalized)
        if security is None:
            security = URIRef(FPI + f"sec-{escaped(normalized)}")
            securities[normalized] = security
            new_security_nodes.add(security)
        company_graph.add((security, RDF.type, FP.Security))
        company_graph.add((security, FP.securityCode, Literal(normalized)))
        if row.holding_name:
            company_graph.add((security, RDFS.label, Literal(row.holding_name)))

        if row.pd_itm_no not in document_nodes:
            entry = entries_by_isin[row.pd_itm_no]
            document = URIRef(FPI + f"doc-holding-{escaped(row.pd_itm_no)}-20260821")
            document_nodes[row.pd_itm_no] = document
            title = f"{entry['name']} 편입종목 공시 (2026-08-21)"
            etf_graph.add((document, RDF.type, FP.Document))
            etf_graph.add((document, RDFS.label, Literal(title)))
            etf_graph.add((document, FP.documentTitle, Literal(title)))
            etf_graph.add((document, FP.documentPublisher, Literal(entry["source"])))
            etf_graph.add(
                (document, FP.documentPublishedDate, Literal("2026-08-21", datatype=XSD.date))
            )

        etf_graph.add((product, FP.hasHolding, holding))
        etf_graph.add((holding, RDF.type, FP.Holding))
        etf_graph.add((holding, FP.holdingSecurity, security))
        weight = decimal_literal(row.weight)
        if weight is not None:
            etf_graph.add((holding, FP.weight, weight))
        etf_graph.add((holding, FP.asOf, Literal("2026-08-21", datatype=XSD.date)))
        etf_graph.add((holding, FP.sourceId, Literal(row.source)))
        etf_graph.add((holding, FP.supportedBy, document_nodes[row.pd_itm_no]))

    bundle = output_root / "ontology-bundle"
    if bundle.exists():
        raise FileExistsError(f"refusing to overwrite existing bundle: {bundle}")
    (bundle / "tbox").mkdir(parents=True)
    (bundle / "abox").mkdir(parents=True)

    for filename in ("bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"):
        shutil.copy2(baseline / filename, bundle / "tbox" / filename)
    shutil.copy2(args.common_tbox.resolve(), bundle / "tbox" / "common.ttl")
    for filename in ("instances_bond_kr.ttl", "instances_etf_gl.ttl", "instances_fund_pub.ttl"):
        shutil.copy2(baseline / filename, bundle / "abox" / filename)
    serialize_sorted(
        etf_graph,
        bundle / "abox" / "instances_etf_kr.ttl",
        f"ETF_KR holdings refreshed: {len(relation):,} rows, {relation['pd_itm_no'].nunique():,} products, as_of=2026-08-21",
    )
    serialize_sorted(
        company_graph,
        bundle / "abox" / "instances_company.ttl",
        f"Company/security graph preserved; {len(new_security_nodes):,} new security nodes from 2026-08-21 holdings",
    )

    files: list[dict] = []
    aggregates = {"abox_triples": 0, "tbox_triples": 0, "named_graph_quads": 0, "default_graph_triples": 0, "named_graphs": 10}
    union: set[tuple] = set()
    for relative, named_graph in GRAPH_NAMES.items():
        path = bundle / relative
        graph = parse_graph(path)
        count = len(graph)
        union.update(graph)
        kind = "abox" if relative.startswith("abox/") else "tbox"
        aggregates[f"{kind}_triples"] += count
        files.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "triples": count,
                "named_graph": named_graph,
            }
        )
    aggregates["named_graph_quads"] = aggregates["abox_triples"] + aggregates["tbox_triples"]
    aggregates["union_unique_triples"] = len(union)
    content_id = hashlib.sha256(
        "\n".join(f"{item['sha256']}  {item['path']}" for item in files).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema_version": 2,
        "bundle_id": f"ontology-holdings-20260821-{content_id[:12]}",
        "created_at": utc_now(),
        "mode": "replace",
        "baseline_dir": str(baseline),
        "source": {
            "relation_path": str(args.relation.resolve()),
            "relation_sha256": sha256_file(args.relation.resolve()),
            "provenance_path": str(args.provenance.resolve()),
            "provenance_sha256": sha256_file(args.provenance.resolve()),
            "master_path": str(args.master.resolve()),
            "master_sha256": sha256_file(args.master.resolve()),
        },
        "holdings": {
            "as_of": "2026-08-21",
            "rows": len(relation),
            "products": int(relation["pd_itm_no"].nunique()),
            "documents": len(document_nodes),
            "removed_baseline_holding_nodes": removed_holdings,
            "new_security_nodes": len(new_security_nodes),
        },
        "files": files,
        "aggregates": aggregates,
    }
    atomic_json(bundle / "manifest.json", manifest)
    sums = "\n".join(f"{item['sha256']}  {item['path']}" for item in files) + "\n"
    (bundle / "SOURCE_SHA256SUMS").write_text(sums, encoding="utf-8", newline="\n")
    atomic_json(output_root / "graph_build_receipt.json", manifest)
    return manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--relation", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--common-tbox", type=Path, default=Path("ontology/common.ttl"))
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    manifest = build(parse_args(sys.argv[1:] if argv is None else argv))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
