# -*- coding: utf-8 -*-
"""주최측 axis_sample 정답지로 코드리스트 적재를 채점한다.

    python3 script/score_codelist_axes.py

data/csv/*_axis_sample_*.csv 는 주최측이 도메인별 100건에 대해 분류축 정답을 붙여 준 것이다.
지금까지 우리는 "몇 건 붙었나"만 셌다. 이 스크립트는 "맞게 붙었나"를 센다.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from rdflib import RDFS, Graph, Namespace, URIRef

ROOT = Path(__file__).resolve().parent.parent
FP = "http://mafest.ai/product#"
FPI = "http://mafest.ai/instance/"

# (axis 컬럼, 우리 ObjectProperty, 인스턴스 URI 접두, 정답지 PK 컬럼)
SPEC = [
    ("PRBD01N001_bond_kr", "pd_no", "bond-", [
        ("axis_issuerType",      "hasBondIssuerType"),
        ("axis_maturityClass",   "hasMaturityClass"),
        ("axis_creditRating",    "hasRatingBand"),
        ("axis_currency",        "hasCurrency"),
        ("axis_issuanceMarket",  "hasIssuanceMarket"),
        ("axis_couponType",      "hasCouponType"),        # 미배선 — 갭 확인용
        ("axis_collateralType",  "hasCollateralType"),    # 미배선
        ("axis_issuerCategory",  "hasIssuerCategory"),    # 미배선
    ]),
    ("PREF01N001_etf_kr", "pd_itm_no", "etfkr-", [
        ("axis_assetType",         "hasAssetType"),
        ("axis_region",            "hasInvestmentRegion"),
        ("axis_strategy",          "hasManagementStrategy"),
        ("axis_replicationMethod", "hasReplicationMethod"),
        ("axis_leverageType",      "hasLeverageType"),
        ("axis_underlyingScope",   "hasUnderlyingScope"),   # 미배선
        ("axis_distributionType",  "hasDistributionType"),  # 미배선
    ]),
    ("PRFD01N001_fund_pub", "itm_no", "fund-", [
        ("axis_fundType",            "hasFundType"),
        ("axis_investorEligibility", "hasInvestorEligibility"),
        ("axis_listingType",         "hasListingType"),          # 미배선
        ("axis_classDifferentiation", "hasClassDifferentiation"),  # 미배선
        ("axis_redemptionType",      "hasRedemptionType"),       # 미배선
        ("axis_issuanceType",        "hasIssuanceType"),         # 미배선
    ]),
]

INST = {"PRBD01N001_bond_kr": "instances_bond_kr.ttl",
        "PREF01N001_etf_kr": "instances_etf_kr.ttl",
        "PRFD01N001_fund_pub": "instances_fund_pub.ttl"}


def load_abox(fname, prefix):
    """인스턴스 TTL에서 {상품코드: {프로퍼티: 개체지역명}} 을 뽑는다. rdflib 없이 정규식으로 — 47MB라 빠르다."""
    txt = (ROOT / "ontology" / fname).read_text(encoding="utf-8")
    out = defaultdict(dict)
    cur = None
    for line in txt.splitlines():
        m = re.match(rf"fpi:{prefix}(\S+)", line)
        if m:
            cur = m.group(1)
            continue
        if cur:
            m2 = re.search(r"fp:(has\w+|ratingStatus)\s+fp:(\w+)", line)
            if m2:
                out[cur][m2.group(1)] = m2.group(2)
        if line.strip().endswith("."):
            cur = None if not line.strip().startswith("fp:") else cur
    return out


# 정답지의 축 값(GovernmentBond, DomesticMarket…)은 개체의 **영문 rdfs:label**이다.
# 개체 지역명(IssuerType_Government)과는 다르므로 라벨로 비교해야 한다.
_g = Graph()
for _f in ("common", "bond_kr", "etf_kr", "etf_gl", "fund_pub"):
    _g.parse(ROOT / "ontology" / f"{_f}.ttl", format="turtle")
_FPNS = Namespace(FP)
SURF = {}   # 개체 지역명 → 그 개체의 모든 표층형(소문자)
for _s in set(_g.subjects()):
    if isinstance(_s, URIRef) and str(_s).startswith(FP):
        name = str(_s).split("#")[-1]
        forms = {str(o).strip().casefold() for o in _g.objects(_s, RDFS.label)}
        forms.add(name.casefold())
        if "_" in name:
            forms.add(name.split("_", 1)[1].casefold())
        SURF[name] = forms


print(f"{'도메인':<10}{'축':<26}{'우리 값 있음':>12}{'정답 일치':>10}{'정확도':>9}   비고")
print("-" * 104)
grand_hit = grand_have = 0
for table, pk, prefix, axes in SPEC:
    gold = pd.read_csv(ROOT / f"data/csv/{table}_axis_sample_20260711.csv",
                       dtype=str, keep_default_na=False)
    abox = load_abox(INST[table], prefix)
    for axis, prop in axes:
        if axis not in gold.columns:
            continue
        have = hit = 0
        wrong = defaultdict(int)
        for r in gold.itertuples(index=False):
            key = getattr(r, pk)
            want = getattr(r, axis).strip()
            got = abox.get(key, {}).get(prop, "")
            # 개체 지역명은 'IssuerType_Government' 형태. 접두를 떼고 비교한다.
            if not got:
                continue
            have += 1
            if want.casefold() in SURF.get(got, {got.casefold()}):
                hit += 1
            else:
                wrong[f"{want}→{got}"] += 1
        acc = f"{hit/have*100:5.1f}%" if have else "    —"
        note = "미배선" if have == 0 else (
            "" if hit == have else "  " + ", ".join(f"{k}({v})" for k, v in
                                                    sorted(wrong.items(), key=lambda x: -x[1])[:2]))
        print(f"{table.split('_',1)[1]:<10}{axis:<26}{have:>12}{hit:>10}{acc:>9}   {note}")
        grand_hit += hit
        grand_have += have
print("-" * 104)
print(f"{'합계':<36}{grand_have:>12}{grand_hit:>10}"
      f"{grand_hit/grand_have*100:>8.1f}%" if grand_have else "")
