# -*- coding: utf-8 -*-
"""2단계 스키마 인덱스가 지금 무엇을 못 하는지 센다.

grounding은 "안전한" 같은 말을 fp: 용어로 번역한다. 그러려면 용어마다
(a) 사람·원본데이터가 쓰는 표층형과 (b) 그 값이 뜻하는 바가 텍스트로 있어야 한다.
없는 것을 찾는 게 전부다.

실행:  python3 script/audit_tbox_index.py
"""
import collections
import glob
import pathlib
import re

import pandas as pd
from rdflib import OWL, RDF, RDFS, Graph, Namespace, URIRef

ROOT = pathlib.Path(__file__).resolve().parent.parent
FP = Namespace("http://mafest.ai/product#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
FILES = ["common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"]
HANGUL = re.compile(r"[가-힣]")

loc = lambda u: str(u).split("#")[-1]

g = Graph()
for f in FILES:
    g.parse(ROOT / "ontology" / f, format="turtle")

classes = {s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}
dprops = set(g.subjects(RDF.type, OWL.DatatypeProperty))
oprops = set(g.subjects(RDF.type, OWL.ObjectProperty))
inds = {s for s in g.subjects(RDF.type, None)
        if isinstance(s, URIRef) and str(s).startswith(str(FP))
        and any(o in classes for o in g.objects(s, RDF.type))}

has = lambda s, p: any(True for _ in g.objects(s, p))
surface = lambda s: [str(o) for p in (RDFS.label, SKOS.altLabel) for o in g.objects(s, p)]

print("=" * 96)
print("1. 인덱스 청크 후보와 주석 보유")
print("=" * 96)
print(f"{'종류':<26}{'전체':>6}{'label':>7}{'comment':>9}{'altLabel':>10}{'한글표층형':>11}")
tot = com = 0
for name, ss in [("Class", classes), ("DatatypeProperty", dprops),
                 ("ObjectProperty", oprops), ("Individual(코드리스트)", inds)]:
    c = sum(has(s, RDFS.comment) for s in ss)
    ko = sum(any(HANGUL.search(t) for t in surface(s)) for s in ss)
    print(f"{name:<26}{len(ss):>6}{sum(has(s, RDFS.label) for s in ss):>7}"
          f"{c:>9}{sum(has(s, SKOS.altLabel) for s in ss):>10}{ko:>11}")
    tot += len(ss); com += c
print(f"{'합계':<26}{tot:>6}{'':>7}{com:>9}")
print(f"\n→ 인덱스 청크 후보 {tot}개 / 주석 보유 {com}개 ({com/tot*100:.1f}%)")

print("\n" + "=" * 96)
print("2. 서열이 필요한 코드리스트에 수치 서열값이 있는가")
print("=" * 96)
ORDERED = ["RiskGrade", "CreditRating", "RatingBand", "MaturityClass", "LeverageType"]
for c in ORDERED:
    ms = list(g.subjects(RDF.type, FP[c]))
    num = sum(1 for m in ms if any(
        True for p, o in g.predicate_objects(m)
        if str(p).startswith(str(FP)) and str(o).replace(".", "").replace("-", "").isdigit()))
    mark = "OK  " if num == len(ms) and ms else "없음"
    print(f"  {mark} {c:<18} 개체 {len(ms):>3}개 중 수치 서열값 보유 {num:>3}개")

print("\n" + "=" * 96)
print("3. 원본 CSV 값이 코드리스트 개체로 흡수되는가")
print("=" * 96)
col_index = {}
for p in (glob.glob(str(ROOT / "data/csv/*.csv")) + glob.glob(str(ROOT / "data/enriched/*.csv"))
          + glob.glob(str(ROOT / "data/relations/*.csv"))):
    try:
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
    except Exception:
        continue
    for c in df.columns:
        col_index.setdefault(c, df)

# 원본값→개체가 1:1 표층형 매핑이 아니라 계산·파싱으로 정해지는 축.
# 미흡수가 정상이므로 갭으로 세지 않는다. 대신 규칙이 어디 적혀 있는지가 문제다.
DERIVED = {
    "hasCouponType": "표면금리 0 여부 / 채권종류명 파싱",
    "hasCollateralType": "채권종류명 파싱",
    "hasLeverageType": "배수 숫자 → 구간 매핑",
    "hasListingType": "식별자 존재 여부",
    "hasClassDifferentiation": "대표종목번호 존재 여부",
    "ratingStatus": "등급값 존재 여부",
    "hasRatingBand": "등급 문자열 접두 매핑",
}

rows = []
for p in oprops:
    rng = next(g.objects(p, RDFS.range), None)
    if rng not in classes:
        continue
    ms = list(g.subjects(RDF.type, rng))
    if not ms:
        continue
    forms = {t.strip().lower() for m in ms for t in surface(m)}
    for sc in [str(o) for o in g.objects(p, FP.sourceColumn)]:
        col = sc.split(".")[-1]
        df = col_index.get(col)
        if df is None:
            continue
        vals = sorted({v.strip() for v in df[col] if v.strip()})
        miss = [v for v in vals if v.lower() not in forms]
        rows.append((loc(p), sc, len(vals), len(vals) - len(miss), miss))

gaps = []
print(f"{'ObjectProperty':<24}{'sourceColumn':<40}{'원본':>5}{'흡수':>5}  미흡수")
print("-" * 96)
for prop, sc, n, hit, miss in sorted(rows, key=lambda r: (r[3] == r[2], r[0])):
    if prop in DERIVED:
        continue
    if hit != n:
        gaps.append((prop, sc, miss))
    m = ", ".join(miss[:6]) + (f" … 외 {len(miss)-6}" if len(miss) > 6 else "")
    print(f"{prop:<24}{sc:<40}{n:>5}{hit:>5}  {m}")

print(f"\n[파생 규칙 축 — 미흡수가 정상이므로 위에서 제외함]")
for k, v in DERIVED.items():
    print(f"  {k:<26} {v}")

print("\n" + "=" * 96)
print("4. 판정")
print("=" * 96)
print(f"  인덱스 청크 후보          : {tot}개 (주석 {com}개, {com/tot*100:.1f}%)")
print(f"  주석 없는 코드리스트 개체  : {sum(1 for s in inds if not has(s, RDFS.comment))}개")
print(f"  표층형 보강 필요 축        : {len(gaps)}개")
for prop, sc, miss in gaps:
    print(f"     - {prop:<24}{sc:<34} {', '.join(miss[:4])}")
print(f"  파생 규칙 명시 필요 축     : {len(DERIVED)}개 (온톨로지가 아니라 빌드 스크립트 소관)")
