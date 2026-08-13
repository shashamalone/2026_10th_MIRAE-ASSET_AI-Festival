#!/usr/bin/env python3
"""ontology/*.ttl 5종 검증. 실패하면 exit 1.

검사 항목
  1) 파일별 Turtle 파싱 성공 + 트리플 수
  2) 병합 그래프의 클래스/속성 수
  3) rdfs:domain 또는 rdfs:range 없는 property 0건
  4) rdfs:label 없는 엔티티(클래스·속성·코드리스트 개체) 0건
  5) 모든 owl:DatatypeProperty에 fp:sourceTable·fp:sourceColumn 애노테이션 존재
  6) Q35 판정 가능성 — fp:issuedBy의 domain에 ETF 계열이 포함되지 않을 것

실행: python3 EDA/validate_ontology.py
"""
import sys
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, URIRef

FP = "http://mafest.ai/product#"
ROOT = Path(__file__).resolve().parent.parent
FILES = ["common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"]

fp = lambda name: URIRef(FP + name)  # noqa: E731
PROP_TYPES = [OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty]

errors = []


def check(cond, msg):
    if not cond:
        errors.append(msg)


# --- 1) 파일별 파싱 ---------------------------------------------------------
merged = Graph()
print("== 파일별 트리플 수")
for name in FILES:
    path = ROOT / "ontology" / name
    g = Graph()
    try:
        g.parse(path.as_posix(), format="turtle")
    except Exception as exc:  # 파싱 실패는 즉시 실패로 처리
        errors.append(f"{name} 파싱 실패: {exc}")
        continue
    print(f"  {name:14s} {len(g):6d} triples")
    merged += g
    if name != "common.ttl":
        check(
            (None, OWL.imports, URIRef("http://mafest.ai/ontology/fp-common")) in g,
            f"{name}: owl:imports fp-common 누락",
        )

if errors:
    print("\n".join("FAIL " + e for e in errors))
    sys.exit(1)

print(f"  {'merged':14s} {len(merged):6d} triples")

# --- 2) 클래스/속성 집계 ----------------------------------------------------
classes = {s for s in merged.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}
props = {p: {s for s in merged.subjects(RDF.type, p) if isinstance(s, URIRef)} for p in PROP_TYPES}
all_props = set().union(*props.values())
individuals = {
    s for s in merged.subjects(RDF.type, None)
    if isinstance(s, URIRef) and s not in classes and s not in all_props
    and (s, RDF.type, OWL.Ontology) not in merged
}

print("\n== 병합 그래프 집계")
print(f"  owl:Class            {len(classes)}")
for p in PROP_TYPES:
    print(f"  {p.split('#')[1]:20s} {len(props[p])}")
print(f"  코드리스트 개체       {len(individuals)}")

# --- 3) domain/range 누락 ---------------------------------------------------
typed_props = props[OWL.ObjectProperty] | props[OWL.DatatypeProperty]
missing_dr = sorted(
    str(p).replace(FP, "fp:")
    for p in typed_props
    if (p, RDFS.domain, None) not in merged or (p, RDFS.range, None) not in merged
)
print(f"\n== rdfs:domain/range 누락 property: {len(missing_dr)}")
for p in missing_dr:
    print("   -", p)
check(not missing_dr, f"domain/range 누락 property {len(missing_dr)}건: {missing_dr}")

# --- 4) rdfs:label 누락 -----------------------------------------------------
missing_label = sorted(
    str(e).replace(FP, "fp:")
    for e in classes | all_props | individuals
    if (e, RDFS.label, None) not in merged
)
print(f"== rdfs:label 누락 엔티티: {len(missing_label)}")
for e in missing_label:
    print("   -", e)
check(not missing_label, f"rdfs:label 누락 {len(missing_label)}건: {missing_label}")

# --- 5) DatatypeProperty 출처 애노테이션 -------------------------------------
missing_src = sorted(
    str(p).replace(FP, "fp:")
    for p in props[OWL.DatatypeProperty]
    if (p, fp("sourceTable"), None) not in merged or (p, fp("sourceColumn"), None) not in merged
)
print(f"== 출처 애노테이션 누락 DatatypeProperty: {len(missing_src)}")
for p in missing_src:
    print("   -", p)
check(not missing_src, f"sourceTable/sourceColumn 누락 {len(missing_src)}건: {missing_src}")

# --- 6) Q35: fp:issuedBy 도메인 위반 판정 가능성 -----------------------------
def expand(node):
    """rdfs:domain 값을 클래스 URI 집합으로 편다(owl:unionOf 포함)."""
    if isinstance(node, URIRef):
        return {node}
    out = set()
    for coll in merged.objects(node, OWL.unionOf):
        out |= {c for c in merged.items(coll) if isinstance(c, URIRef)}
    return out


issued_domain = set()
for d in merged.objects(fp("issuedBy"), RDFS.domain):
    issued_domain |= expand(d)

print("\n== Q35 도메인 위반 판정")
print("  fp:issuedBy domain =", sorted(str(c).replace(FP, "fp:") for c in issued_domain))
check(issued_domain == {fp("Bond")}, f"fp:issuedBy의 domain이 fp:Bond 단독이 아님: {issued_domain}")
for cls in ("ETF", "ETN", "PublicFund"):
    check(fp(cls) not in issued_domain, f"fp:issuedBy domain에 fp:{cls} 포함 — Q35 판정 불가")
# ETF가 Bond와 disjoint여야 '주어가 ETF'라는 사실만으로 위반이 확정된다
disjoint = set(merged.objects(fp("ETF"), OWL.disjointWith)) | {
    s for s in merged.subjects(OWL.disjointWith, fp("ETF"))
}
check(fp("Bond") in disjoint, "fp:ETF owl:disjointWith fp:Bond 선언 누락 — Q35 형식 판정 불가")
print("  fp:ETF disjointWith fp:Bond =", fp("Bond") in disjoint)

# --- 7) 설계 결정 회귀 방지 --------------------------------------------------
holding_domain = set()
for d in merged.objects(fp("hasHolding"), RDFS.domain):
    holding_domain |= expand(d)
check(fp("ETN") not in holding_domain, "fp:hasHolding domain에 fp:ETN이 포함됨(ETN은 편입종목 없음)")

ranks = {int(o) for o in merged.objects(None, fp("ratingRank"))}
check(ranks == set(range(1, 20)), f"CreditRating 서열이 1~19가 아님: {sorted(ranks)}")
aa_minus = [s for s in merged.subjects(fp("ratingRank"), None)
            if int(next(merged.objects(s, fp("ratingRank")))) <= 4]
check(len(aa_minus) == 4, f"'AA- 이상'(rank<=4) 개체가 4개가 아님: {len(aa_minus)}")
check((fp("Rating_AAAA"), None, None) not in merged,
      "AAAA 개체가 존재하면 안 됨(ABSTAIN_INVALID_TAXONOMY 판정 근거)")
print(f"  신용등급 개체 {len(ranks)}개 / 'AA- 이상' 해당 {len(aa_minus)}개 / AAAA 부재 확인")

# 무등급의 두 의미: 상태 개체는 존재하되 서열(ratingRank)을 가지면 안 된다
status = {s for s in merged.subjects(RDF.type, fp("RatingStatus"))}
check(status == {fp("Rated"), fp("UnratedByDesign"), fp("RatingUnknown")},
      f"RatingStatus 개체가 Rated/UnratedByDesign/RatingUnknown 3종이 아님: {sorted(status)}")
for s in status:
    check((s, fp("ratingRank"), None) not in merged,
          f"{s}에 ratingRank가 부여됨 — 상태값이 서열 비교에 끼어들면 안 됨")
    check((s, RDF.type, fp("CreditRating")) not in merged,
          f"{s}가 fp:CreditRating 개체로도 선언됨 — 등급 개체와 분리해야 함")
for cls in ("GovernmentBond", "CorporateBond", "SpecialBond"):
    check((fp(cls), RDFS.subClassOf, None) in merged, f"fp:{cls} 하위 클래스 선언 누락")
print(f"  등급 상태 개체 {len(status)}종(서열 미부여 확인) / 채권 하위 클래스 선언 확인")

themes = {s for s in merged.subjects(RDF.type, fp("Theme"))}
check(len(themes) == 176, f"테마 개체가 176종이 아님: {len(themes)}")
print(f"  테마 개체 {len(themes)}종")

# --- 결과 ------------------------------------------------------------------
if errors:
    print("\n" + "\n".join("FAIL " + e for e in errors))
    sys.exit(1)
print("\nOK — 검증 항목 전부 통과")
