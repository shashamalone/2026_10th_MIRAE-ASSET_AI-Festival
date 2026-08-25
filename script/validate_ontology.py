#!/usr/bin/env python3
"""ontology/*.ttl 스키마 5종 + 인스턴스 5종 검증. 실패하면 exit 1.

스키마 검사
  1) 파일별 Turtle 파싱 성공 + 트리플 수
  2) 병합 그래프의 클래스/속성 수
  3) rdfs:domain 또는 rdfs:range 없는 property 0건
  4) rdfs:label 없는 엔티티(클래스·속성·코드리스트 개체) 0건
  5) 모든 owl:DatatypeProperty에 fp:sourceTable·fp:sourceColumn 애노테이션 존재
  6) Q35 판정 가능성 — fp:issuedBy의 domain에 ETF 계열이 포함되지 않을 것
  7) 설계 결정 회귀 방지 (등급 서열·상태 개체·테마 176종 등)

인스턴스 검사 (EDA/build_ontology_instances.py 산출)
  A) 개체 수·관계 수가 원천 CSV 행수와 일치
  B) rdfs:domain / rdfs:range 위반 0건 (하위 클래스 추론 포함)
  C) 스팟체크 — 에코프로 → 자회사 에코프로비엠 → 247540 증권 → 편입 ETF ≥ 30종
  D) 스팟체크 — KODEX 200(KR7069500007) 편입종목 수 > 0

실행: python3 EDA/validate_ontology.py
"""
import sys
import time
from pathlib import Path

import pandas as pd
from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal, XSD

FP = "http://mafest.ai/product#"
ROOT = Path(__file__).resolve().parent.parent
FILES = ["common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"]
INSTANCE_FILES = ["instances_bond_kr.ttl", "instances_etf_kr.ttl", "instances_etf_gl.ttl",
                  "instances_fund_pub.ttl", "instances_company.ttl"]

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

################################################################################
# 인스턴스 검증
################################################################################

t0 = time.time()
inst = Graph()
print("\n== 인스턴스 파일별 트리플 수")
for name in INSTANCE_FILES:
    g = Graph()
    try:
        g.parse((ROOT / "ontology" / name).as_posix(), format="turtle")
    except Exception as exc:
        errors.append(f"{name} 파싱 실패: {exc}")
        continue
    print(f"  {name:24s} {len(g):8,d} triples  {(ROOT / 'ontology' / name).stat().st_size / 1e6:6.2f}MB")
    inst += g
if errors:
    print("\n".join("FAIL " + e for e in errors))
    sys.exit(1)
print(f"  {'merged':24s} {len(inst):8,d} triples  ({time.time() - t0:.0f}s)")

# --- A) 개체 수 ↔ 원천 CSV 행수 ---------------------------------------------
read = lambda p: pd.read_csv(  # noqa: E731
    ROOT / p, dtype=str, keep_default_na=False, encoding="utf-8-sig")
etf_kr_csv = read("data/csv/PREF01N001_etf_kr_master_20260824.csv")

def typed(cls):
    return len(set(inst.subjects(RDF.type, fp(cls))))

def subclass_typed(*classes):
    return len({s for c in classes for s in inst.subjects(RDF.type, fp(c))})

expected = [
    ("국내채권", subclass_typed("GovernmentBond", "CorporateBond", "SpecialBond", "Bond"),
     read("data/csv/PRBD01N001_bond_kr_master_20260824.csv").pd_no.nunique()),
    ("국내ETF", len({s for s in inst.subjects(RDF.type, fp("ETF")) if "etfkr-" in str(s)}),
     (etf_kr_csv.pd_grp_no == "ETF").sum()),
    ("해외ETF·ETN", len({s for s in inst.subjects(RDF.type, None) if "etfgl-" in str(s)}),
     len(read("data/csv/PREF02N001_etf_gl_master_20260824.csv"))),
    ("공모펀드", len({s for s in inst.subjects(RDF.type, None) if "fund-" in str(s)}),
     len(read("data/csv/PRFD01N001_fund_pub_master_20260824.csv"))),
    ("편입관계(fp:Holding)", typed("Holding"), len(read("data/relations/etf_holding.csv"))),
    ("테마관계(fp:relatedToTheme)", len(list(inst.triples((None, fp("relatedToTheme"), None)))),
     len(read("data/relations/etf_theme.csv"))),
    ("출자관계(fp:SubsidiaryRelation)", typed("SubsidiaryRelation"),
     len(read("data/relations/company_subsidiary.csv"))),
]
print("\n== A) 개체 수 ↔ 원천 CSV 행수")
for label, got, want in expected:
    print(f"  {label:32s} {got:8,d} / CSV {want:8,d} {'OK' if got == want else 'MISMATCH'}")
    check(got == want, f"{label} 수 불일치: 그래프 {got} vs CSV {want}")

# --- B) domain/range 위반 ---------------------------------------------------
sup = {}  # 클래스 → 자기 자신 + 모든 상위 클래스


def closure(c, seen=None):
    if c in sup:
        return sup[c]
    seen = (seen or set()) | {c}
    out = {c}
    for p in merged.objects(c, RDFS.subClassOf):
        if isinstance(p, URIRef) and p not in seen:
            out |= closure(p, seen)
    sup[c] = out
    return out


types = {}  # 등급·테마 등 스키마 개체의 타입도 함께 봐야 range 판정이 된다
for g in (merged, inst):
    for s, o in g.subject_objects(RDF.type):
        if isinstance(o, URIRef):
            types.setdefault(s, set()).add(o)
type_closure = {s: set().union(*(closure(c) for c in cs)) for s, cs in types.items()}

bad_dom, bad_rng, checked = [], [], 0
for p in sorted(typed_props):
    doms = set().union(*(expand(d) for d in merged.objects(p, RDFS.domain))) or None
    rngs = set().union(*(expand(r) for r in merged.objects(p, RDFS.range))) or None
    is_obj = (p, RDF.type, OWL.ObjectProperty) in merged
    for s, o in inst.subject_objects(p):
        checked += 1
        if doms and not (type_closure.get(s, set()) & doms):
            bad_dom.append((s, p, sorted(types.get(s, []))))
        if not rngs:
            continue
        if is_obj:
            if not (type_closure.get(o, set()) & rngs):
                bad_rng.append((s, p, o))
        elif isinstance(o, Literal):
            want = next(iter(rngs))
            if (o.datatype or XSD.string) != want:
                bad_rng.append((s, p, f"{o.datatype} != {want}"))

print(f"\n== B) domain/range 위반 (검사 {checked:,} 트리플)")
print(f"  domain 위반 {len(bad_dom)}건, range 위반 {len(bad_rng)}건")
for x in bad_dom[:5] + bad_rng[:5]:
    print("   -", x)
check(not bad_dom, f"domain 위반 {len(bad_dom)}건: {bad_dom[:3]}")
check(not bad_rng, f"range 위반 {len(bad_rng)}건: {bad_rng[:3]}")

# --- C) 스팟체크: 에코프로 → 에코프로비엠 → 247540 → 편입 ETF ------------------
q = """
PREFIX fp: <http://mafest.ai/product#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?etf WHERE {
  ?parent a fp:Company ; rdfs:label "에코프로" ; fp:hasSubsidiary ?rel .
  ?rel fp:subsidiaryCompany ?child .
  ?child rdfs:label "에코프로비엠" .
  ?sec fp:issuedByCompany ?child ; fp:securityCode "247540" .
  ?h fp:holdingSecurity ?sec .
  ?etf fp:hasHolding ?h .
}"""
holders = len(set(inst.query(q)))
print(f"\n== C) 에코프로 → 자회사 에코프로비엠 → 247540 증권 → 편입 ETF: {holders}종")
check(holders >= 30, f"에코프로 경로로 도달한 ETF가 {holders}종 (30 미만)")

# --- D) 스팟체크: KODEX 200 편입종목 -----------------------------------------
kodex = URIRef("http://mafest.ai/instance/etfkr-KR7069500007")
n_hold = len(list(inst.objects(kodex, fp("hasHolding"))))
label = next(inst.objects(kodex, RDFS.label), None)
print(f"== D) KODEX 200(KR7069500007) '{label}' 편입종목: {n_hold}건")
check(n_hold > 0, "KODEX 200의 편입종목이 0건")

# --- 결과 ------------------------------------------------------------------
if errors:
    print("\n" + "\n".join("FAIL " + e for e in errors))
    sys.exit(1)
print("\nOK — 스키마 검증 + 인스턴스 스팟체크 4종(A·B·C·D) 전부 통과")
