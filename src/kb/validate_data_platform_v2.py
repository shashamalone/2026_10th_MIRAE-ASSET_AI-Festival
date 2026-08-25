# -*- coding: utf-8 -*-
"""금융상품 데이터 플랫폼 v2의 정적·stage DB·Graph·Vector 통합 검증."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from rdflib import OWL, RDF, RDFS, Graph, Namespace, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.build_catalog_v2 import build_outputs, write_or_check  # noqa: E402
from kb.v2_manifest import ROOT, validate_source_dir  # noqa: E402
from tools.sql_guard import strip_literals_and_comments  # noqa: E402

FP = Namespace("http://mafest.ai/product#")
FPI = "http://mafest.ai/instance/"
SQL_PATH = ROOT / "sql" / "v2" / "010_enrich.sql"
OUTPUT_DIR = ROOT / "artifacts" / "graph_v2"
SCHEMAS = {"META": "meta_next", "RAW": "raw_next", "ENRICHED": "enriched_next", "RELATIONS": "relations_next", "VEC": "vec_next", "CORE": "core_next"}


def validate_no_buyable_quantity_rule() -> dict[str, object]:
    sql_text = SQL_PATH.read_text(encoding="utf-8")
    normalized = strip_literals_and_comments(sql_text).lower()
    violations = []
    for index, statement in enumerate(normalized.split(";"), 1):
        if "buyable_quantity" not in statement:
            continue
        if "is_assumed_purchasable" in statement or re.search(
            r"\b(?:where|having|order\s+by|filter)\b[^;]*\bbuyable_quantity\b", statement
        ):
            violations.append(index)
    if violations:
        raise ValueError(f"BUYABLE_QUANTITY가 판매 판정/필터에 사용됨: SQL 문 {violations}")
    return {"sql_occurrences": normalized.count("buyable_quantity"), "decision_violations": 0}


def validate_runtime_dependencies() -> dict[str, object]:
    python_files = list((ROOT / "src").rglob("*.py"))
    runtime_files = python_files + [ROOT / "requirements.txt", ROOT / "compose.yaml"]
    forbidden_import = re.compile(
        r"^\s*(?:from|import)\s+(?:duckdb|faiss|pyoxigraph|google\.generativeai)\b",
        re.IGNORECASE,
    )
    hits = []
    for path in python_files:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden_import.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{line_number}")
    requirement_text = "\n".join(
        line.split("#", 1)[0] for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    )
    if re.search(r"\b(?:duckdb|faiss|pyoxigraph|google-generativeai)\b", requirement_text, re.IGNORECASE):
        hits.append("requirements.txt")
    if hits:
        raise ValueError("운영 경로 금지 의존성: " + ", ".join(hits))
    return {"checked_files": len(runtime_files), "forbidden_hits": 0}


def validate_tbox() -> dict[str, object]:
    graph = Graph()
    files = sorted((ROOT / "ontology").glob("*.ttl"))
    for path in files:
        graph.parse(path, format="turtle")
    bond_graph = Graph()
    for name in ("common.ttl", "bond_kr.ttl"):
        bond_graph.parse(ROOT / "ontology" / name, format="turtle")
    term_filter = lambda value: isinstance(value, URIRef) and str(value).startswith(str(FP))
    bond_terms = {subject for subject in bond_graph.subjects(RDFS.comment, None) if term_filter(subject)}
    all_terms = {subject for subject in graph.subjects(RDFS.comment, None) if term_filter(subject)}
    if len(bond_terms) != 130 or len(all_terms) != 188:
        raise ValueError(f"TBox grounding 행 수 불일치: bond={len(bond_terms)}, all={len(all_terms)}")
    required_classes = {FP.KoreanETF, FP.GlobalETF, FP.KoreanETN, FP.GlobalETN, FP.Holding, FP.SubsidiaryRelation, FP.Sector}
    missing = [str(value) for value in required_classes if (value, RDF.type, OWL.Class) not in graph]
    if missing:
        raise ValueError(f"TBox 필수 클래스 누락: {missing}")
    for prop, domain, range_ in (
        (FP.hasSector, FP.Product, FP.Sector),
        (FP.hasDocument, FP.Product, FP.Document),
    ):
        if (prop, RDF.type, OWL.ObjectProperty) not in graph or (prop, RDFS.domain, domain) not in graph or (prop, RDFS.range, range_) not in graph:
            raise ValueError(f"TBox 분류/문서 속성 계약 불일치: {prop}")
    return {"files": len(files), "triples": len(graph), "bond_terms": len(bond_terms), "all_terms": len(all_terms)}


def validate_static(data_dir: str | Path | None = None) -> dict[str, object]:
    inspections = validate_source_dir(data_dir)
    write_or_check(build_outputs(data_dir), check=True)
    return {
        "sources": [item.as_dict() for item in inspections],
        "catalog_outputs": "match",
        "buyable_quantity": validate_no_buyable_quantity_rule(),
        "runtime_dependencies": validate_runtime_dependencies(),
        "tbox": validate_tbox(),
    }


def validate_abox_files() -> dict[str, object]:
    expected = {
        "instances_bond_kr.ttl",
        "instances_etf_kr.ttl",
        "instances_etf_gl.ttl",
        "instances_fund_pub.ttl",
        "instances_company.ttl",
    }
    actual = {path.name for path in OUTPUT_DIR.glob("instances_*.ttl")}
    if actual != expected:
        raise ValueError(f"ABox 5개 집합 불일치: actual={sorted(actual)}")
    graph = Graph()
    counts = {}
    for path in sorted(OUTPUT_DIR.glob("instances_*.ttl")):
        one = Graph()
        one.parse(path, format="turtle")
        counts[path.name] = len(one)
        graph += one

    subclass_graph = Graph()
    for path in sorted((ROOT / "ontology").glob("*.ttl")):
        subclass_graph.parse(path, format="turtle")

    def is_subclass(child: URIRef, parent: URIRef) -> bool:
        frontier = [child]
        seen = set()
        while frontier:
            current = frontier.pop()
            if current == parent:
                return True
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(
                value for value in subclass_graph.objects(current, RDFS.subClassOf) if isinstance(value, URIRef)
            )
        return False

    errors = []
    for product, holding in graph.subject_objects(FP.hasHolding):
        product_types = set(graph.objects(product, RDF.type))
        if not any(is_subclass(value, FP.ETF) or is_subclass(value, FP.PublicFund) for value in product_types if isinstance(value, URIRef)):
            errors.append(f"hasHolding domain:{product}")
        if (holding, RDF.type, FP.Holding) not in graph:
            errors.append(f"hasHolding range:{holding}")
        for predicate in (FP.holdingSecurity, FP.asOf, FP.supportedBy, FP.sourceId):
            if not any(graph.objects(holding, predicate)):
                errors.append(f"holding missing {predicate}:{holding}")
    for parent, relation in graph.subject_objects(FP.hasSubsidiary):
        if (parent, RDF.type, FP.Company) not in graph:
            errors.append(f"hasSubsidiary domain:{parent}")
        if (relation, RDF.type, FP.SubsidiaryRelation) not in graph:
            errors.append(f"hasSubsidiary range:{relation}")
        for predicate in (FP.subsidiaryCompany, FP.asOf, FP.supportedBy, FP.sourceId):
            if not any(graph.objects(relation, predicate)):
                errors.append(f"subsidiary missing {predicate}:{relation}")
    for predicate, range_class in (
        (FP.relatedToTheme, FP.Theme),
        (FP.hasSector, FP.Sector),
        (FP.hasInvestmentRegion, FP.InvestmentRegion),
    ):
        for product, classification in graph.subject_objects(predicate):
            product_types = set(graph.objects(product, RDF.type))
            if not any(is_subclass(value, FP.Product) for value in product_types if isinstance(value, URIRef)):
                errors.append(f"classification domain:{product}")
            if (classification, RDF.type, range_class) not in graph:
                errors.append(f"classification range:{classification}")
    for product, document in graph.subject_objects(FP.hasDocument):
        product_types = set(graph.objects(product, RDF.type))
        if not any(is_subclass(value, FP.Product) for value in product_types if isinstance(value, URIRef)):
            errors.append(f"hasDocument domain:{product}")
        if (document, RDF.type, FP.Document) not in graph:
            errors.append(f"hasDocument range:{document}")
    if errors:
        raise ValueError("Graph domain/range/n-ary 오류: " + ", ".join(errors[:20]))
    if any(not str(subject).startswith(FPI) for subject in graph.subjects() if isinstance(subject, URIRef)):
        raise ValueError("ABox subject URI namespace 불안정")
    return {"files": counts, "triples": len(graph), "domain_range_errors": 0}


def validate_stage(data_dir: str | Path | None = None) -> dict[str, object]:
    import psycopg

    from kb.build_data_platform_v2 import dsn, validate_stage as validate_rdb_stage
    from kb.build_graph_v2 import build as build_graph
    from kb.build_vectors_v2 import validate_vectors

    inspections = validate_source_dir(data_dir)
    with psycopg.connect(dsn()) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rdb = validate_rdb_stage(conn, inspections)
        document_count = conn.execute(f"SELECT count(*) FROM {SCHEMAS['VEC']}.document_chunk").fetchone()[0]
        vectors = validate_vectors(conn, document_count)
        plans = conn.execute(
            f"EXPLAIN (FORMAT JSON) SELECT product_id,name,purchasable_rule FROM {SCHEMAS['ENRICHED']}.bond_kr_product WHERE is_assumed_purchasable"
        ).fetchone()[0]
        if "buyable_quantity" in json.dumps(plans).lower():
            raise ValueError("판매가능 채권 실행계획에 BUYABLE_QUANTITY가 포함됨")

        started = time.perf_counter()
        cross_rows = conn.execute(
            f"""
            SELECT p.product_id,p.product_type,p.name,m.value return_1y,m.as_of,m.source,
                   c.holdings_status,c.holdings_reason,d.url
            FROM {SCHEMAS['RELATIONS']}.product_holding h
            JOIN {SCHEMAS['ENRICHED']}.security_master s USING(security_id)
            JOIN {SCHEMAS['ENRICHED']}.product_master p USING(product_id)
            JOIN {SCHEMAS['META']}.product_coverage c USING(product_id)
            LEFT JOIN {SCHEMAS['ENRICHED']}.product_metric m ON m.product_id=p.product_id
                 AND m.metric_code='RETURN_1Y' AND m.is_available
            JOIN {SCHEMAS['RELATIONS']}.source_document d ON d.document_id=h.source_document_id
            WHERE p.product_type IN ('ETF_KR','ETF_GL','FUND_PUB')
              AND (s.display_name='삼성전자' OR EXISTS (
                    SELECT 1 FROM {SCHEMAS['ENRICHED']}.security_identifier i
                    WHERE i.security_id=s.security_id AND i.id_type='KR_TICKER' AND i.id_value='005930'))
              AND m.value IS NOT NULL AND m.value <> 0
            ORDER BY m.value DESC LIMIT 10
            """
        ).fetchall()
        elapsed = time.perf_counter() - started
        if elapsed > 3.0:
            raise ValueError(f"대표 RDB 교차질의 {elapsed:.3f}s > 3s")
        if not cross_rows:
            unavailable = conn.execute(
                f"""SELECT count(*) FROM {SCHEMAS['META']}.product_coverage c
                JOIN {SCHEMAS['ENRICHED']}.product_master p USING(product_id)
                WHERE p.product_type IN ('ETF_KR','ETF_GL','FUND_PUB')
                  AND c.holdings_status='unavailable'
                  AND c.holdings_reason LIKE '편입내역 미확보%%'"""
            ).fetchone()[0]
            if not unavailable:
                raise ValueError("삼성전자 교차질의가 0행인데 미확보 coverage도 없음")
        hnsw = conn.execute(
            "SELECT count(*) FROM pg_indexes WHERE schemaname=%s AND indexdef ILIKE '%%USING hnsw%%'",
            (SCHEMAS["VEC"],),
        ).fetchone()[0]
        if hnsw < 3:
            raise ValueError(f"cosine HNSW 인덱스 부족: {hnsw}")
    graph_preview = build_graph(check_only=True)
    graph_files = validate_abox_files()
    return {
        "rdb": rdb,
        "vectors": vectors,
        "hnsw_indexes": hnsw,
        "bond_plan_buyable_quantity": False,
        "cross_query_rows": len(cross_rows),
        "cross_query_seconds": round(elapsed, 4),
        "graph_preview": graph_preview,
        "graph_files": graph_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="금융상품 데이터 플랫폼 v2 검증")
    parser.add_argument("--data-dir")
    parser.add_argument("--stage", action="store_true", help="*_next DB/Graph/Vector까지 검증")
    args = parser.parse_args()
    result = {"static": validate_static(args.data_dir)}
    if args.stage:
        result["stage"] = validate_stage(args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
