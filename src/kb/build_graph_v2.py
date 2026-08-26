# -*- coding: utf-8 -*-
"""PostgreSQL v2 stage에서 결정적 ABox Turtle 5개를 생성한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.build_data_platform_v2 import SCHEMAS, dsn  # noqa: E402
from kb.v2_manifest import (  # noqa: E402
    DATASET_VERSION,
    EXPECTED_ABOX_TRIPLES,
    EXPECTED_RELATION_COUNTS,
    EXPECTED_SNAPSHOT_HASH,
    RELEASE_ID,
    ROOT,
    sha256_file,
)

FP = "http://mafest.ai/product#"
FPI = "http://mafest.ai/instance/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
XSD = "http://www.w3.org/2001/XMLSchema#"
OUTPUT_DIR = ROOT / "artifacts" / "graph_v2"
MANIFEST_PATH = OUTPUT_DIR / "graph_manifest.json"
PREFIX = """# 자동 생성. 직접 편집 금지.
@prefix fp: <http://mafest.ai/product#> .
@prefix fpi: <http://mafest.ai/instance/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

"""


def uri(namespace: str, value: object) -> str:
    if not namespace:
        return f"<{value}>"
    return f"<{namespace}{quote(str(value), safe='')}>"


def literal(value: object, datatype: str | None = None) -> str:
    if value is None:
        raise ValueError("NULL literal은 생성하지 않습니다")
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    suffix = f"^^<{datatype}>" if datatype else ""
    return f'"{text}"{suffix}'


def add(triples: set[str], subject: str, predicate: str, obj: str) -> None:
    triples.add(f"{subject} {predicate} {obj} .")


def rows(conn: psycopg.Connection, statement: str) -> list[dict[str, object]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
        cursor.execute(statement)
        return list(cursor.fetchall())


def product_triples(records: list[dict[str, object]], class_name: str) -> set[str]:
    triples: set[str] = set()
    for record in records:
        product = uri(FPI, record["product_id"])
        add(triples, product, uri("", RDF_TYPE), uri(FP, class_name))
        add(triples, product, uri(FP, "productCode"), literal(record["source_key"]))
        add(triples, product, uri(FP, "productName"), literal(record["name"]))
        if record.get("short_name"):
            add(triples, product, uri(FP, "productShortName"), literal(record["short_name"]))
    return triples


def build_from_db(conn: psycopg.Connection) -> dict[str, set[str]]:
    product_base = f"{SCHEMAS['ENRICHED']}.product_master"
    graphs: dict[str, set[str]] = {}
    graphs["instances_bond_kr.ttl"] = product_triples(
        rows(conn, f"SELECT product_id,source_key,name,short_name FROM {product_base} WHERE product_type='BOND' ORDER BY product_id"),
        "Bond",
    )
    kr_records = rows(
        conn,
        f"SELECT product_id,source_key,name,short_name,product_type FROM {product_base} "
        "WHERE product_type IN ('ETF_KR','ETN_KR') ORDER BY product_id",
    )
    kr: set[str] = set()
    for record in kr_records:
        kr |= product_triples([record], "KoreanETF" if record["product_type"] == "ETF_KR" else "KoreanETN")
    graphs["instances_etf_kr.ttl"] = kr

    gl_records = rows(
        conn,
        f"SELECT product_id,source_key,name,short_name,product_type FROM {product_base} "
        "WHERE product_type IN ('ETF_GL','ETN_GL') ORDER BY product_id",
    )
    gl: set[str] = set()
    for record in gl_records:
        gl |= product_triples([record], "GlobalETF" if record["product_type"] == "ETF_GL" else "GlobalETN")
    graphs["instances_etf_gl.ttl"] = gl
    graphs["instances_fund_pub.ttl"] = product_triples(
        rows(conn, f"SELECT product_id,source_key,name,short_name FROM {product_base} WHERE product_type='FUND_PUB' ORDER BY product_id"),
        "PublicFund",
    )
    graph_for_type = {
        "BOND": "instances_bond_kr.ttl",
        "ETF_KR": "instances_etf_kr.ttl",
        "ETN_KR": "instances_etf_kr.ttl",
        "ETF_GL": "instances_etf_gl.ttl",
        "ETN_GL": "instances_etf_gl.ttl",
        "FUND_PUB": "instances_fund_pub.ttl",
    }
    classification_map = {
        "theme": ("relatedToTheme", "Theme"),
        "sector": ("hasSector", "Sector"),
        "region": ("hasInvestmentRegion", "InvestmentRegion"),
        "asset_type": ("hasAssetType", "AssetType"),
    }
    for record in rows(
        conn,
        f"""
        SELECT c.*,p.product_type
        FROM {SCHEMAS['RELATIONS']}.product_classification c
        JOIN {product_base} p USING(product_id)
        WHERE p.product_type <> 'FUND_PRIVATE'
        ORDER BY c.classification_id
        """,
    ):
        classification_type = str(record["classification_type"]).lower()
        if classification_type not in classification_map:
            raise ValueError(f"지원하지 않는 classification_type={classification_type}")
        predicate, class_name = classification_map[classification_type]
        target = graphs[graph_for_type[str(record["product_type"])]]
        product = uri(FPI, record["product_id"])
        node = uri(FPI, f"classification:{classification_type}:{record['classification_value']}")
        add(target, product, uri(FP, predicate), node)
        add(target, node, uri("", RDF_TYPE), uri(FP, class_name))
        add(target, node, uri("", RDFS_LABEL), literal(record["classification_value"]))
        if record.get("source_document_id"):
            add(target, product, uri(FP, "hasDocument"), uri(FPI, f"document:{record['source_document_id']}"))

    company: set[str] = set()
    for record in rows(
        conn,
        f"""
        SELECT DISTINCT s.security_id,s.display_name,s.security_type
        FROM {SCHEMAS['ENRICHED']}.security_master s
        WHERE EXISTS (SELECT 1 FROM {SCHEMAS['RELATIONS']}.product_holding h WHERE h.security_id=s.security_id)
           OR EXISTS (SELECT 1 FROM {SCHEMAS['RELATIONS']}.company_subsidiary r
                      WHERE r.parent_security_id=s.security_id OR r.child_security_id=s.security_id)
        ORDER BY s.security_id
        """,
    ):
        security = uri(FPI, f"security:{record['security_id']}")
        class_name = "Company" if record["security_type"] == "company" else "Security"
        add(company, security, uri("", RDF_TYPE), uri(FP, class_name))
        add(company, security, uri("", RDFS_LABEL), literal(record["display_name"]))

    for record in rows(
        conn,
        f"SELECT document_id,title,publisher,published_at,url FROM {SCHEMAS['RELATIONS']}.source_document ORDER BY document_id",
    ):
        document = uri(FPI, f"document:{record['document_id']}")
        add(company, document, uri("", RDF_TYPE), uri(FP, "Document"))
        add(company, document, uri(FP, "documentTitle"), literal(record["title"]))
        add(company, document, uri(FP, "documentPublisher"), literal(record["publisher"]))
        add(company, document, uri(FP, "documentPublishedDate"), literal(record["published_at"], XSD + "date"))

    for record in rows(
        conn,
        f"SELECT * FROM {SCHEMAS['RELATIONS']}.product_holding ORDER BY holding_id",
    ):
        product = uri(FPI, record["product_id"])
        holding = uri(FPI, f"holding:{record['holding_id']}")
        security = uri(FPI, f"security:{record['security_id']}")
        document = uri(FPI, f"document:{record['source_document_id']}")
        add(company, product, uri(FP, "hasHolding"), holding)
        add(company, holding, uri("", RDF_TYPE), uri(FP, "Holding"))
        add(company, holding, uri(FP, "holdingSecurity"), security)
        if record["weight"] is not None:
            add(company, holding, uri(FP, "weight"), literal(record["weight"], XSD + "decimal"))
        add(company, holding, uri(FP, "asOf"), literal(record["as_of"], XSD + "date"))
        add(company, holding, uri(FP, "supportedBy"), document)
        add(company, holding, uri(FP, "sourceId"), literal(record["source"]))

    for record in rows(
        conn,
        f"SELECT * FROM {SCHEMAS['RELATIONS']}.company_subsidiary ORDER BY relation_id",
    ):
        parent = uri(FPI, f"security:{record['parent_security_id']}")
        child = uri(FPI, f"security:{record['child_security_id']}")
        relation = uri(FPI, f"subsidiary:{record['relation_id']}")
        document = uri(FPI, f"document:{record['source_document_id']}")
        add(company, parent, uri(FP, "hasSubsidiary"), relation)
        add(company, relation, uri("", RDF_TYPE), uri(FP, "SubsidiaryRelation"))
        add(company, relation, uri(FP, "subsidiaryCompany"), child)
        if record["ownership_pct"] is not None:
            add(company, relation, uri(FP, "ownershipPct"), literal(record["ownership_pct"], XSD + "decimal"))
        add(company, relation, uri(FP, "asOf"), literal(record["as_of"], XSD + "date"))
        add(company, relation, uri(FP, "supportedBy"), document)
        add(company, relation, uri(FP, "sourceId"), literal(record["source"]))

    for record in rows(
        conn,
        f"SELECT * FROM {SCHEMAS['RELATIONS']}.product_document ORDER BY product_id,document_id,relation_type",
    ):
        add(
            company,
            uri(FPI, record["product_id"]),
            uri(FP, "hasDocument"),
            uri(FPI, f"document:{record['document_id']}"),
        )
    graphs["instances_company.ttl"] = company
    return graphs


def serialize(triples: set[str]) -> str:
    return PREFIX + "\n".join(sorted(triples)) + "\n"


def validate_turtle(contents: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, content in contents.items():
        graph = Graph()
        graph.parse(data=content, format="turtle")
        counts[name] = len(graph)
    return counts


def manifest(contents: dict[str, str], counts: dict[str, int]) -> dict[str, object]:
    tbox = {}
    for name in ("common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"):
        path = ROOT / "ontology" / name
        graph = Graph()
        graph.parse(path, format="turtle")
        tbox[name] = {
            "named_graph": f"http://mafest.ai/graph/tbox/{path.stem}",
            "path": f"ontology/{name}",
            "triples": len(graph),
            "sha256": sha256_file(path),
        }
    abox = {
        name: {
            "named_graph": f"http://mafest.ai/graph/abox/{Path(name).stem.removeprefix('instances_')}",
            "path": f"artifacts/graph_v2/{name}",
            "triples": counts[name],
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
        for name, content in sorted(contents.items())
    }
    total = sum(counts.values())
    if total != EXPECTED_ABOX_TRIPLES:
        raise ValueError(
            f"ABox triple 수 불일치: {total:,} != {EXPECTED_ABOX_TRIPLES:,}"
        )
    return {
        "dataset_version": DATASET_VERSION,
        "release_id": RELEASE_ID,
        "snapshot_hash": EXPECTED_SNAPSHOT_HASH,
        "tbox": tbox,
        "abox": abox,
        "total_abox_triples": total,
    }


def validate_manifest_files(path: Path = MANIFEST_PATH) -> dict[str, object]:
    """커밋 TBox와 생성 ABox의 파일 집합·SHA·트리플 수를 다시 검증한다."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("release_id") != RELEASE_ID or payload.get("snapshot_hash") != EXPECTED_SNAPSHOT_HASH:
        raise ValueError("Graph manifest release/snapshot 계약 불일치")
    for section in ("tbox", "abox"):
        for name, item in payload[section].items():
            file_path = ROOT / str(item["path"])
            if not file_path.is_file():
                raise FileNotFoundError(f"Graph manifest 파일 누락: {file_path}")
            if sha256_file(file_path) != item["sha256"]:
                raise ValueError(f"Graph manifest SHA 불일치: {name}")
            graph = Graph()
            graph.parse(file_path, format="turtle")
            if len(graph) != item["triples"]:
                raise ValueError(f"Graph manifest triple 불일치: {name}")
    abox_total = sum(int(item["triples"]) for item in payload["abox"].values())
    if abox_total != EXPECTED_ABOX_TRIPLES or payload.get("total_abox_triples") != abox_total:
        raise ValueError(
            f"Graph manifest ABox 합계 불일치: {abox_total:,} != {EXPECTED_ABOX_TRIPLES:,}"
        )
    return payload


def build(check_only: bool = False) -> dict[str, object]:
    with psycopg.connect(dsn()) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        source_hash = conn.execute(
            f"SELECT source_hash FROM {SCHEMAS['META']}.dataset_snapshot ORDER BY built_at DESC LIMIT 1"
        ).fetchone()[0]
        if source_hash != EXPECTED_SNAPSHOT_HASH:
            raise ValueError(
                f"RDB stage snapshot {source_hash} != {EXPECTED_SNAPSHOT_HASH}"
            )
        relation_counts = {
            "product_holdings": conn.execute(
                f"SELECT count(*) FROM {SCHEMAS['RELATIONS']}.product_holding"
            ).fetchone()[0],
            "company_subsidiaries": conn.execute(
                f"SELECT count(*) FROM {SCHEMAS['RELATIONS']}.company_subsidiary"
            ).fetchone()[0],
        }
        if relation_counts != EXPECTED_RELATION_COUNTS:
            raise ValueError(
                f"Graph 입력 관계 수 불일치 actual={relation_counts} "
                f"expected={EXPECTED_RELATION_COUNTS}"
            )
        contents = {name: serialize(triples) for name, triples in build_from_db(conn).items()}
    counts = validate_turtle(contents)
    result = manifest(contents, counts)
    if check_only:
        result.update({"mode": "check", "mutated_files": False, "mutated_database": False})
        return result
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        (OUTPUT_DIR / name).write_text(content, encoding="utf-8", newline="\n")
    MANIFEST_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 결정적 ABox 5개 빌더")
    parser.add_argument("--check", action="store_true", help="파일을 쓰지 않고 DB→TTL 결과만 검증")
    parser.add_argument(
        "--validate-files",
        action="store_true",
        help="DB에 접속하지 않고 기존 TBox/ABox manifest·SHA·트리플을 검증",
    )
    args = parser.parse_args()
    if args.check and args.validate_files:
        parser.error("--check와 --validate-files는 함께 사용할 수 없습니다")
    result = validate_manifest_files() if args.validate_files else build(args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
