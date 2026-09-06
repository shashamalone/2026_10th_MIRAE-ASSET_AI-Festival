from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, URIRef


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "refresh_holding_graph", ROOT / "src" / "kb" / "refresh_holding_graph.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
FP = Namespace("http://mafest.ai/product#")


def test_security_normalization_and_uri_escaping():
    assert MODULE.normalize_security_code("KR7005930003", "isin") == "005930"
    assert MODULE.normalize_security_code("688256 C1 Equity", "bloomberg") == "688256 C1 Equity"
    assert MODULE.escaped("688256 C1 Equity") == "688256%20C1%20Equity"


def test_builder_replaces_only_holdings_and_adds_document_provenance(tmp_path: Path):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    product = URIRef("http://mafest.ai/instance/etfkr-KR7000000001")
    old_holding = URIRef("http://mafest.ai/instance/hold-old")
    etf_graph = Graph()
    etf_graph.add((product, RDF.type, FP.ETF))
    etf_graph.add((product, FP.productCode, Literal("KR7000000001")))
    etf_graph.add((product, FP.hasHolding, old_holding))
    etf_graph.add((old_holding, RDF.type, FP.Holding))
    etf_graph.add((old_holding, FP.asOf, Literal("2026-07-10")))
    etf_graph.serialize(baseline / "instances_etf_kr.ttl", format="turtle")
    company_graph = Graph()
    company_graph.add((URIRef("http://mafest.ai/instance/company-kept"), RDF.type, FP.Company))
    company_graph.serialize(baseline / "instances_company.ttl", format="turtle")

    empty_graph = Graph()
    for filename in (
        "bond_kr.ttl",
        "etf_kr.ttl",
        "etf_gl.ttl",
        "fund_pub.ttl",
        "instances_bond_kr.ttl",
        "instances_etf_gl.ttl",
        "instances_fund_pub.ttl",
    ):
        empty_graph.serialize(baseline / filename, format="turtle")
    common = tmp_path / "common.ttl"
    Graph().serialize(common, format="turtle")

    relation = tmp_path / "etf_holding.csv"
    pd.DataFrame(
        [
            {
                "pd_itm_no": "KR7000000001",
                "holding_code_raw": "688256 C1 Equity",
                "holding_code_type": "bloomberg",
                "holding_name": "Cambricon Technologies",
                "weight": "9.25",
                "source": "TIGER",
                "as_of": "2026-08-21",
            }
        ]
    ).to_csv(relation, index=False, lineterminator="\n")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "snapshot_as_of": "2026-08-21",
                "relation_sha256": hashlib.sha256(relation.read_bytes()).hexdigest(),
                "entries": {
                    "000001": {
                        "isin": "KR7000000001",
                        "name": "TIGER fixture",
                        "document": "Mirae Asset TIGER ETF",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    master = tmp_path / "master.csv"
    pd.DataFrame(
        [
            {
                "pd_grp_no": "ETF",
                "pd_itm_no": "KR7000000001",
                "pd_itm_no_ma": "A000001",
            }
        ]
    ).to_csv(master, index=False)
    output = tmp_path / "output"
    manifest = MODULE.build(
        SimpleNamespace(
            baseline_dir=baseline,
            relation=relation,
            provenance=provenance,
            master=master,
            common_tbox=common,
            output_dir=output,
        )
    )

    refreshed = Graph().parse(output / "ontology-bundle" / "abox" / "instances_etf_kr.ttl")
    assert (product, FP.hasHolding, old_holding) not in refreshed
    assert not list(refreshed.triples((old_holding, None, None)))
    new_holdings = list(refreshed.objects(product, FP.hasHolding))
    assert len(new_holdings) == 1
    assert (new_holdings[0], FP.asOf, Literal("2026-08-21", datatype=MODULE.XSD.date)) in refreshed
    documents = list(refreshed.objects(new_holdings[0], FP.supportedBy))
    assert len(documents) == 1
    assert (
        documents[0],
        FP.documentPublisher,
        Literal("Mirae Asset TIGER ETF"),
    ) in refreshed
    assert manifest["holdings"]["removed_baseline_holding_nodes"] == 1
    assert manifest["holdings"]["rows"] == 1

    company = Graph().parse(output / "ontology-bundle" / "abox" / "instances_company.ttl")
    security = URIRef("http://mafest.ai/instance/sec-688256%20C1%20Equity")
    assert (security, FP.securityCode, Literal("688256 C1 Equity")) in company
    assert (URIRef("http://mafest.ai/instance/company-kept"), RDF.type, FP.Company) in company
