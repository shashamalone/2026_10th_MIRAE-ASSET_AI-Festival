#!/usr/bin/env python3
"""ontology/*.ttl (TBox) → docs_data_layer/PROPERTY_STORAGE_MAP.csv

    python3 script/build_storage_map.py

2단계 스키마 검색(`vec.schema_index`)의 `storage` 라우팅 힌트를 채우는 소스다.

왜 필요한가: TBox는 fp: 속성 136개를 선언하지만 그래프(ABox)에 실제로 들어간 것은 37개뿐이다.
나머지 99개는 (a) RDB 담당 파생 (b) 데이터 자체가 없음 (c) 문서 계층으로 성격이 갈리는데,
그 구분이 지금은 build_ontology_instances.py 독스트링의 산문에만 있다. 스키마 검색은
rdfs:comment를 임베딩하므로 136개가 전부 후보로 뜨고, 잘못 라우팅하면 SPARQL이 0행을 반환해
"확인할 수 없음"이 오답으로 나간다.

분류 근거는 전부 TBox와 빌더 소스에서 기계적으로 뽑는다. 사람이 정한 것은 UNFILLABLE·
DOC_LAYER 두 집합뿐이며, 각 항목의 rdfs:comment 원문을 evidence 컬럼에 실어 검증 가능하게 둔다.
"""
import csv
import pathlib
import re

from rdflib import OWL, RDF, RDFS, Graph, Namespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
FP = Namespace("http://mafest.ai/product#")
TBOX = ["common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"]
OUT = ROOT / "docs_data_layer" / "PROPERTY_STORAGE_MAP.csv"

# 주최측 원본 4종. sourceTable 이 이 값이면 raw.* 에 지금 존재한다.
HOST_TABLES = {"PRBD01N001", "PREF01N001", "PREF02N001", "PRFD01N001"}

# 데이터 자체가 없어 인스턴스를 만들 수 없는 속성. rdfs:comment 에 근거가 명시돼 있다.
# 이 집합이 곧 "답변 불가" 판정의 화이트리스트다 — LLM 호출 없이 즉시 판정한다.
UNFILLABLE = {
    "belongsToIndustry", "hasCollateralType", "hasCustodian", "hasDistributionType",
    "hasIssuanceType", "hasIssuerCategory", "hasRedemptionType", "hasUnderlyingScope",
    "subsidiaryOf",
}

# 파생 테이블의 재현 가능성. 외부 수집분만 재현이 안 된다 — 운용사 사이트가 상장폐지
# 종목을 지우므로 지금 다시 수집하면 8/18 수집분과 결과가 달라진다(생존편향).
# 값은 각 테이블을 만드는 스크립트가 무엇을 읽는지로 판정했다.
DERIVATION = {
    "bond_kr_enriched":    ("pure", "build_bond_enrichment.py ← data/csv 원본만"),
    "etf_kr_enriched":     ("pure", "build_etf_enrichment.py ← data/csv 원본만"),
    "fund_pub_dedup":      ("pure", "build_fund_dedup.py ← data/csv 원본만"),
    "etf_theme":           ("pure", "build_etf_enrichment.py:40 ← data/csv 원본만"),
    "company_master":      ("external", "build_company_relations.py ← DART corpcode·KIND"),
    "company_subsidiary":  ("external", "build_company_relations.py ← DART 지배구조"),
    "etf_holding":         ("external", "build_etf_holding.py ← 운용사 사이트 수집분"),
    "document":            ("external", "문서 수집 미착수"),
    "etf_kr_brand":        ("planned", "생산 스크립트 없음"),
    "metric_snapshot":     ("planned", "생산 스크립트 없음"),
    "relations":           ("planned", "generic 관계 유효기간 계층, 미구현"),
}

# 설계는 있으나 아직 만들지 않은 계층. '데이터가 없어 불가능'(UNFILLABLE)과 구분해야 한다.
PLANNED = {"hasMetricSnapshot"}

# 서술형 텍스트·근거문서 계층. 벡터 검색이 담당한다.
DOC_LAYER = {
    "strategyText", "documentTitle", "documentQuote", "documentPublisher",
    "documentPublishedDate", "hasRisk", "supportedBy",
}

# 도메인별 가용성이 갈리는 경우를 잡는다. 이걸 놓치면 "해외ETF 수익률 상위"가
# 조용히 0행이 되어 '없음'으로 오답이 나간다. 반드시 '답변 불가'로 구분해야 한다.
CAVEAT_RE = re.compile(
    r"[^.]*?(해외ETF|국내ETF|공모펀드|채권|ETN)[^.]*?"
    r"(전량 결측|전량 0|전량 무효|전량 1|없다|없어|못한다|축 자체가 없|"
    r"적용할 수 없|기능하지 못)[^.]*\.")

loc = lambda u: str(u).split("#")[-1]


def load_tbox() -> Graph:
    g = Graph()
    for name in TBOX:
        g.parse(ROOT / "ontology" / name, format="turtle")
    return g


def emitted_predicates() -> set[str]:
    """build_ontology_instances.py 가 실제로 쓰는 술어. ABox 존재의 근거다."""
    src = (ROOT / "script" / "build_ontology_instances.py").read_text(encoding="utf-8")
    return set(re.findall(r"FP\.([a-zA-Z_]+)", src)) | set(re.findall(r"fp:([a-zA-Z_]+)", src))


def joined(g: Graph, subj, pred) -> str:
    return "|".join(sorted(loc(o) if str(o).startswith(str(FP)) else str(o)
                           for o in g.objects(subj, pred)))


def classify(name, in_graph, tables):
    """(storage, availability) 결정. 순서가 곧 우선순위다."""
    if in_graph:
        return "graph", "loaded"
    if name in UNFILLABLE:
        return "none", "unavailable"
    if name in DOC_LAYER:
        # 원천 텍스트가 raw.* 에 이미 있으면 남은 일은 임베딩뿐이다.
        if any(t in HOST_TABLES for t in tables):
            return "vector", "pending-embedding"
        return "vector", "pending-collection"
    if name in PLANNED:
        return "rdb", "derived-not-deployed"
    if not tables:
        return "none", "unavailable"
    if any(t in HOST_TABLES for t in tables):
        return "rdb", "raw"                 # VM raw.* 에 지금 있다
    if any(t.startswith("derived:") for t in tables):
        return "rdb", "derived-not-deployed"  # 파생 계층 빌드가 선행돼야 한다
    return "rdb", "unknown"


def main() -> None:
    g = load_tbox()
    emitted = emitted_predicates()

    kinds = {}
    for rdf_type, tag in ((OWL.DatatypeProperty, "DP"), (OWL.ObjectProperty, "OP")):
        for s in g.subjects(RDF.type, rdf_type):
            if str(s).startswith(str(FP)):
                kinds[loc(s)] = tag

    rows = []
    for name in sorted(kinds):
        subj = FP[name]
        comment = " ".join(str(o) for o in g.objects(subj, RDFS.comment)).replace("\n", " ")
        tables = [t for t in joined(g, subj, FP.sourceTable).split("|") if t]
        storage, availability = classify(name, name in emitted, tables)
        derivation, derivation_note = "", ""
        for t in tables:
            if t.startswith("derived:") and t[len("derived:"):] in DERIVATION:
                derivation, derivation_note = DERIVATION[t[len("derived:"):]]
                break
        caveat = CAVEAT_RE.search(comment.replace("**", ""))
        rows.append({
            "property": name,
            "uri": f"http://mafest.ai/product#{name}",
            "kind": kinds[name],
            "storage": storage,
            "availability": availability,
            "domain": joined(g, subj, RDFS.domain),
            "range": joined(g, subj, RDFS.range),
            "label": joined(g, subj, RDFS.label),
            "source_tables": "|".join(tables),
            "source_columns": joined(g, subj, FP.sourceColumn),
            "derivation": derivation,
            "derivation_note": derivation_note,
            "domain_caveat": caveat.group(0).strip() if caveat else "",
            "comment": comment,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {OUT.relative_to(ROOT)}  ({len(rows)} rows)")
    for key in ("storage", "availability", "derivation"):
        counts = {}
        for r in rows:
            counts[r[key]] = counts.get(r[key], 0) + 1
        print(f"\n[{key}]")
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {v:4d}  {k}")
    print(f"\n[domain_caveat 있음] {sum(1 for r in rows if r['domain_caveat'])}건")


if __name__ == "__main__":
    main()
