#!/usr/bin/env python3
"""data/csv·enriched·relations → ontology/instances_*.ttl (인스턴스 5파일).

    python3 EDA/build_ontology_instances.py

스키마 5파일(common·bond_kr·etf_kr·etf_gl·fund_pub)은 건드리지 않고 인스턴스만 생성한다.
출력은 **결정적**이다 — 정렬된 순서, 타임스탬프 없음. 두 번 실행하면 바이트 동일하다.

URI 규칙 (인스턴스 전용 프리픽스 fpi: = http://mafest.ai/instance/)
    fpi:bond-{pd_no}          국내채권      fpi:etfkr-{pd_itm_no}  국내ETF
    fpi:etfgl-{pd_itm_no}     해외ETF/ETN   fpi:fund-{itm_no}      공모펀드
    fpi:corp-{corp_code}      DART 고유번호로 특정된 기업/발행사
    fpi:corp-n-{정규화명}      고유번호 미매칭 기업 (동명이인 5,532종은 특정 불가)
    fpi:sec-{종목코드}         편입증권 (KR7 ISIN은 ticker6로 정규화해 노드를 합친다)
    fpi:hold-{ETF}-{종목}-{n} 편입관계 n-ary 노드   fpi:sub-{모}-{자}-{n} 자회사 n-ary 노드
    URI에 못 쓰는 문자는 UTF-8 퍼센트 인코딩(%XX)으로 규칙적으로 이스케이프한다.
    한글·CJK는 Turtle PN_CHARS에 포함되므로 그대로 둔다(가독성).

넣지 않는 것: 파생 플래그(is_sellable·crd_grd_rank 등 RDB 담당), 룩어헤드/더미 컬럼,
              추정 기준일(etf_theme의 as_of는 공란이라 fp:asOf 트리플 자체를 생략).
"""
import re
import time
from collections import Counter
from pathlib import Path

import pandas as pd
from rdflib import RDF, RDFS, Graph, Namespace, URIRef

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ontology"
FP = "http://mafest.ai/product#"
FPI = "http://mafest.ai/instance/"

# 정규화 규칙은 build_company_relations.py의 corp_name_norm과 동일해야 조인이 성립한다
ALIAS = {"에스케이": "SK", "엘지": "LG", "케이티": "KT", "지에스": "GS", "씨제이": "CJ",
         "에이치디": "HD", "에스디": "SD", "디비": "DB", "케이비": "KB", "엔에이치": "NH"}
DROP = re.compile(r"\(주\)|㈜|\(유\)|주식회사|[\s·,]")


def norm(name):
    s = DROP.sub("", str(name))
    for k in sorted(ALIAS, key=len, reverse=True):
        s = s.replace(k, ALIAS[k])
    return s.upper()


assert norm("에스케이하이닉스(주)") == "SK하이닉스"
assert norm("(주)엘지에너지솔루션") == "LG에너지솔루션"


def esc(s):
    """URI 지역부 이스케이프. ASCII 영숫자·'_'·'-'와 한글/CJK만 남기고 나머지는 %XX."""
    out = []
    for c in str(s):
        o = ord(c)
        if c.isascii() and (c.isalnum() or c in "_-"):
            out.append(c)
        elif 0x3130 <= o <= 0x318F or 0xAC00 <= o <= 0xD7A3 or 0x4E00 <= o <= 0x9FFF:
            out.append(c)
        else:
            out += ["%%%02X" % b for b in c.encode()]
    return "".join(out)


def lit(s):
    """Turtle 문자열 리터럴. 상품명에 따옴표·백슬래시·개행이 실제로 들어 있다."""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"'


def dec(v):
    return f'"{v}"^^xsd:decimal'


def date(v):
    return f'"{v}"^^xsd:date'


HEADER = """@prefix fp:   <{fp}> .
@prefix fpi:  <{fpi}> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

################################################################################
# {title}
# 자동 생성 — EDA/build_ontology_instances.py. 직접 편집 금지.
# {note}
################################################################################

"""


class Doc:
    """엔티티 블록을 모아 결정적 순서로 직렬화한다."""

    def __init__(self, title, note):
        self.head = HEADER.format(fp=FP, fpi=FPI, title=title, note=note)
        self.blocks = []
        self.triples = 0

    def add(self, subject, pairs):
        pairs = [(p, o) for p, o in pairs if o]
        self.triples += sum(1 if isinstance(o, str) else len(o) for _, o in pairs)
        # 다중값은 한 줄 하나 — 편입종목 1건 증감이 10KB 한 줄이 아니라 한 줄 diff가 된다
        body = " ;\n    ".join(f"{p} {o if isinstance(o, str) else ',\n        '.join(o)}"
                               for p, o in pairs)
        self.blocks.append(f"{subject}\n    {body} .\n")

    def write(self, path):
        path.write_text(self.head + "\n".join(self.blocks), encoding="utf-8")
        return path.stat().st_size


t0 = time.time()
read = lambda p, **kw: pd.read_csv(  # noqa: E731
    ROOT / p, dtype=str, keep_default_na=False, encoding="utf-8-sig", **kw)

# ── 코드리스트 매핑 ─────────────────────────────────────────────────────────
# 원본 CSV 값("남미/북미") → 온톨로지 개체(fp:Region_Americas) 사전을 **스키마 TTL에서 읽는다**.
# 코드에 하드코딩하지 않는 이유: 같은 표기가 TTL과 코드 두 곳에 생기면, 원본 표기가 바뀔 때
# 한쪽만 고쳐도 에러가 안 나고 조용히 해당 상품들이 검색에서 빠진다.
_SCHEMA = Graph()
for _f in ("common", "bond_kr", "etf_kr", "etf_gl", "fund_pub"):
    _SCHEMA.parse(OUT / f"{_f}.ttl", format="turtle")
_FPNS = Namespace(FP)
_SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
_MISS = Counter()   # 사전에 없어 링크를 못 만든 (축, 원본값) 집계 — 마지막에 보고한다
_HIT = Counter()    # 축별로 실제 생성된 링크 수. 0이면 배선이 끊긴 것이다


def codelist(cls):
    """fp:{cls} 개체의 label·altLabel → 'fp:개체명' 사전.

    - 언어태그는 무시한다("1"@en 과 "주식형"@ko 를 같은 자격으로 본다).
    - 정렬해 순회한다. rdflib의 subjects() 순서는 비결정적이라, 그냥 쓰면 실행할 때마다
      출력 TTL이 달라져 "두 번 돌리면 바이트 동일"이라는 이 스크립트의 계약이 깨진다.
    - 같은 표층형이 한 클래스 안에서 두 개체를 가리키면 조용히 하나를 고르지 않고 멈춘다.
      어느 쪽을 골랐는지 모른 채 넘어가면 답변 근거가 틀어진다.
    """
    m = {}
    for s in sorted(_SCHEMA.subjects(RDF.type, _FPNS[cls]), key=str):
        name = str(s).split("#")[-1]
        for prop in (RDFS.label, _SKOS.altLabel):
            for o in sorted(_SCHEMA.objects(s, prop), key=str):
                k = str(o).strip().casefold()
                if not k:
                    continue
                if k in m and m[k] != f"fp:{name}":
                    raise SystemExit(f"코드리스트 표층형 충돌: {cls} '{k}' → {m[k]} vs fp:{name}")
                m[k] = f"fp:{name}"
    if not m:
        raise SystemExit(f"코드리스트 비어 있음: fp:{cls} 개체가 스키마에 없다")
    return m


def link(prop, table, value):
    """원본값 → 코드리스트 개체 트리플. 사전에 없으면 만들지 않는다(추측 금지)."""
    v = str(value).strip()
    if not v:
        return None
    hit = table.get(v.casefold())
    if hit is None:
        _MISS[(prop, v)] += 1
        return None
    _HIT[prop] += 1
    return (prop, hit)


CL_RISK = codelist("RiskGrade")
CL_REGION = codelist("InvestmentRegion")
CL_ASSET = codelist("AssetType")
CL_CURR = codelist("Currency")
CL_FUNDTYPE = codelist("FundType")
CL_BISSUER = codelist("BondIssuerType")
CL_MARKET = codelist("IssuanceMarket")
CL_TRADING = codelist("TradingMarket")
CL_ELIG = codelist("InvestorEligibility")
CL_MATURITY = codelist("MaturityClass")
CL_STRATEGY = codelist("ManagementStrategy")
CL_REPL = codelist("ReplicationMethod")

# ── 규칙 기반 축 ────────────────────────────────────────────────────────────
# 사전으로 못 푸는 둘. 이유가 서로 다르다.

# (1) 신용등급 대역: CRD_GRD 20종 → 6대역의 **다대일**이다. 'AA-'를 RatingBand_AA의
#     altLabel로 달면 같은 문자열이 이미 fp:CreditRating 개체의 표층형이라 충돌한다.
#     최장 접두 우선으로 결정적으로 떨어진다(AAA→AA→A, BBB→BB→B).
_BAND = [("AAA", "AAA"), ("AA", "AA"), ("A", "A"), ("BBB", "BBB"),
         ("BB", "Specul"), ("B", "Specul"), ("CCC", "Specul"), ("CC", "Specul"), ("C", "Specul")]


def rating_band(grade):
    g = str(grade).strip().upper()
    if not g:
        _HIT["fp:hasRatingBand"] += 1
        return ("fp:hasRatingBand", "fp:RatingBand_NotRated")
    for pre, band in _BAND:
        if g.startswith(pre):
            _HIT["fp:hasRatingBand"] += 1
            return ("fp:hasRatingBand", f"fp:RatingBand_{band}")
    _MISS[("fp:hasRatingBand", g)] += 1
    return None


# (2) 레버리지: cu_lev_fector는 배수 숫자다. "-3" 같은 수치를 어휘 라벨(altLabel)로 다는 건
#     의미상 오용이고 "1" vs "1.0" 파싱 차이에 깨진다. 실측 9종 중 개체가 있는 6종만 잇고
#     ±0.5·±1.5(6종목)는 대응 개체가 없어 트리플을 만들지 않는다 — 근사 매핑은 오답이 된다.
_LEV = {1.0: "Standard", 2.0: "2X", 3.0: "3X",
        -1.0: "Inverse1X", -2.0: "Inverse2X", -3.0: "Inverse3X"}


def leverage(factor):
    v = str(factor).strip()
    if not v:
        return None
    try:
        f = float(v)
    except ValueError:
        _MISS[("fp:hasLeverageType", v)] += 1
        return None
    if f not in _LEV:
        _MISS[("fp:hasLeverageType", v)] += 1
        return None
    _HIT["fp:hasLeverageType"] += 1
    return ("fp:hasLeverageType", f"fp:Leverage_{_LEV[f]}")


def links(*items):
    """None을 걸러 pairs에 바로 이어 붙일 수 있게 한다."""
    return [x for x in items if x]


# ── 마스터 로드 ────────────────────────────────────────────────────────────
master = read("data/enriched/company_master.csv")
uniq_norm = master.groupby("corp_name_norm").corp_code.nunique()
NORM2CODE = master[master.corp_name_norm.isin(uniq_norm[uniq_norm == 1].index)] \
    .set_index("corp_name_norm").corp_code.to_dict()
CODE2NAME = master.set_index("corp_code").corp_name.to_dict()
listed = master[master.stock_code.str.len() == 6]
STOCK2CODE = listed.set_index("stock_code").corp_code.to_dict()

# 편입종목 식별자 해소표(우선주→보통주 기업, 모ETF 판별 포함). build_holding_code_map.py 산출
cmap = read("data/enriched/holding_code_map.csv")
MAP2CORP = {r.holding_code_raw: r.corp_code for r in cmap.itertuples(index=False) if r.corp_code}
MAP2ETF = {r.holding_code_raw: r.etf_isin for r in cmap.itertuples(index=False) if r.etf_isin}

companies = {}  # uri -> {code, labels, types}


def company(raw_name, code="", kind="Company"):
    """기업 노드 등록(참조되는 것만). 고유번호 우선, 없으면 정규화명 URI."""
    n = norm(raw_name)
    code = code or NORM2CODE.get(n, "")
    uri = f"fpi:corp-{code}" if code else f"fpi:corp-n-{esc(n)}"
    e = companies.setdefault(uri, {"code": code, "labels": set(), "types": set()})
    e["labels"].add(str(raw_name).strip())
    e["types"].add(kind)
    return uri


securities = {}  # uri -> {code, names}


def security(code_raw, code_type, name):
    """편입증권 노드. KR7 ISIN(KR7247540008)은 ticker6(247540)로 접어 노드를 합친다.
    편입종목이 ETF면(해소표 etf_ticker_exact 72종) 별도 증권 노드 대신 그 ETF 상품 노드를 쓴다
    — fp:ETF는 fp:Security의 하위이므로 fp:holdingSecurity의 range를 만족한다."""
    code = code_raw[3:9] if code_type == "isin" and code_raw.startswith("KR7") and len(code_raw) == 12 else code_raw
    if MAP2ETF.get(code) in ETF_URI:
        return ETF_URI[MAP2ETF[code]]
    uri = f"fpi:sec-{esc(code)}"
    e = securities.setdefault(uri, {"code": code, "names": set()})
    if name:
        e["names"].add(name)
    return uri


# ── 1. 국내채권 ────────────────────────────────────────────────────────────
BOND_CLASS = {"국공채": "fp:GovernmentBond", "개인투자용국채": "fp:GovernmentBond",
              "회사채": "fp:CorporateBond", "외화채권-회사채": "fp:CorporateBond",
              "외화채권-금융채": "fp:CorporateBond", "특수채": "fp:SpecialBond"}
RATING = {"AAA": "AAA", "AA+": "AAp", "AA": "AA", "AA-": "AAm", "A+": "Ap", "A": "A", "A-": "Am",
          "BBB+": "BBBp", "BBB": "BBB", "BBB-": "BBBm", "BB+": "BBp", "BB": "BB", "BB-": "BBm",
          "B+": "Bp", "B": "B", "B-": "Bm", "CCC": "CCC", "CC": "CC", "C": "C"}

bond = read("data/csv/PRBD01N001_bond_kr_master_20260824.csv")
_bond_key = ["pd_no", "pd_exg_mkt", "info_seq"]
_ben = read("data/enriched/bond_kr_enriched.csv").set_index(_bond_key)
grade = _ben.crd_grd_norm.to_dict()
MATBUCKET = _ben.maturity_bucket.to_dict()

d_bond = Doc(f"fp-instances-bond-kr — 국내채권 {bond.pd_no.nunique():,}종({len(bond):,}행)",
             "출처: PRBD01N001_bond_kr_master_20260824.csv + data/enriched/bond_kr_enriched.csv")
for r in bond.sort_values(_bond_key).itertuples(index=False):
    key = (r.pd_no, r.pd_exg_mkt, r.info_seq)
    g = grade.get(key, "")
    pairs = [("a", BOND_CLASS.get(r.std_pd_mcls_nm, "fp:Bond")),
             ("rdfs:label", lit(r.pd_nm)),
             ("fp:productCode", lit(r.pd_no)),
             ("fp:productName", lit(r.pd_nm))]
    if r.pd_pbcm.strip():
        pairs.append(("fp:issuedBy", company(r.pd_pbcm, kind="Issuer")))
    if g in RATING:
        pairs += [("fp:hasCreditRating", f"fp:Rating_{RATING[g]}"), ("fp:ratingStatus", "fp:Rated")]
    else:  # 국공채·개인투자용국채의 등급 결측은 '미평가가 정상'(UnratedByDesign)
        pairs.append(("fp:ratingStatus", "fp:UnratedByDesign"
                      if BOND_CLASS.get(r.std_pd_mcls_nm) == "fp:GovernmentBond" else "fp:RatingUnknown"))
    pairs += links(
        rating_band(g),
        link("fp:hasRiskGrade", CL_RISK, r.pd_risk_gcd),
        link("fp:hasCurrency", CL_CURR, r.curr_cd),
        link("fp:hasBondIssuerType", CL_BISSUER, r.std_pd_mcls_nm),
        link("fp:hasIssuanceMarket", CL_MARKET, r.pd_ctry_cd),
        link("fp:hasTradingMarket", CL_TRADING, r.pd_exg_mkt),
        link("fp:hasMaturityClass", CL_MATURITY, MATBUCKET.get(key, "")))
    d_bond.add(f"fpi:bond-{esc(r.pd_no)}", pairs)

# ── 2. 국내ETF (ETN 제외) + 편입관계 + 테마 ─────────────────────────────────
etf_kr = read("data/csv/PREF01N001_etf_kr_master_20260824.csv")
etf_kr = etf_kr[etf_kr.pd_grp_no == "ETF"].sort_values("pd_itm_no")
ETF_URI = {c: f"fpi:etfkr-{esc(c)}" for c in etf_kr.pd_itm_no}

# LSEG 파생 replication은 '실물(액티브)'처럼 복제방식·운용전략 조합값이다. 복제방식만 떼어 쓴다.
_etfen = read("data/enriched/etf_kr_enriched.csv")
REPL_LSEG = {r.pd_itm_no: {"실물": "실물복제", "합성": "합성복제"}.get(
    (m.group(1) if (m := re.match(r"(실물|합성)\(", r.replication)) else ""), "")
    for r in _etfen.itertuples(index=False)}

hold = read("data/relations/etf_holding.csv").sort_values(
    ["pd_itm_no", "holding_code_raw", "holding_name", "weight"], kind="stable")
hold["seq"] = hold.groupby(["pd_itm_no", "holding_code_raw"]).cumcount()  # 동일 (ETF,종목) 1,370건
theme = read("data/relations/etf_theme.csv").sort_values(["pd_itm_no", "theme"])
fund = read("data/csv/PRFD01N001_fund_pub_master_20260824.csv").sort_values("itm_no")
SAME = {k: v for k, v in zip(fund.ksd_itm_no, fund.itm_no) if k in ETF_URI}

holdings_by_etf, hold_rows = {}, []
for r in hold.itertuples(index=False):
    uri = f"fpi:hold-{esc(r.pd_itm_no)}-{esc(r.holding_code_raw)}-{r.seq}"
    holdings_by_etf.setdefault(r.pd_itm_no, []).append(uri)
    hold_rows.append((uri, security(r.holding_code_raw, r.holding_code_type, r.holding_name),
                      r.weight, r.as_of, r.source))
themes_by_etf = theme.groupby("pd_itm_no").theme.apply(list).to_dict()

d_kr = Doc("fp-instances-etf-kr — 국내ETF 1,202종 + 편입관계 47,016건 + 테마 5,646건",
           "출처: PREF01N001(pd_grp_no='ETF'), data/relations/etf_holding.csv·etf_theme.csv"
           "\n# etf_theme의 as_of는 원천 공란이라 fp:asOf 트리플을 생략한다(거짓 기준일 방지).")
theme_iris = set()
for r in etf_kr.itertuples(index=False):
    pairs = [("a", "fp:ETF"), ("rdfs:label", lit(r.pd_nm)),
             ("fp:productCode", lit(r.pd_itm_no)), ("fp:productName", lit(r.pd_nm)),
             ("fp:productShortName", lit(r.pd_abrv_nm) if r.pd_abrv_nm else "")]
    hs = holdings_by_etf.get(r.pd_itm_no)
    if hs:
        pairs.append(("fp:hasHolding", sorted(hs)))
    ts = themes_by_etf.get(r.pd_itm_no)
    if ts:
        iris = [f"<{FP}Theme_{t.replace(' ', '_')}>" for t in sorted(ts)]
        theme_iris.update(iris)
        pairs.append(("fp:relatedToTheme", iris))
    pairs += links(
        link("fp:hasRiskGrade", CL_RISK, r.pd_risk_cd),
        link("fp:hasInvestmentRegion", CL_REGION, r.wu_inv_rgn),
        link("fp:hasAssetType", CL_ASSET, r.wu_inv_ast_type),
        link("fp:hasCurrency", CL_CURR, r.pd_curr_cd),
        link("fp:hasManagementStrategy", CL_STRATEGY, r.cu_strtegy),
        # cu_strtegy에는 복제방식(실물복제·합성복제)과 운용전략(액티브)이 섞여 있다.
        # '액티브'는 복제방식 정보가 아닌데 fp:Replication_Active 라벨과 문자열이 맞아 잘못 붙는다
        # (주최측 정답지 대조에서 Physical 21건이 Active로 오적재됨). 복제방식 값만 받는다.
        link("fp:hasReplicationMethod", CL_REPL,
             r.cu_strtegy if r.cu_strtegy in ("실물복제", "합성복제") else "")
        or link("fp:hasReplicationMethod", CL_REPL, REPL_LSEG.get(r.pd_itm_no, "")),
        leverage(r.cu_lev_fector))
    if r.pd_itm_no in SAME.values():
        pairs.append(("fp:sameVehicleAs", sorted(f"fpi:fund-{esc(f)}" for k, f in SAME.items()
                                                 if k == r.pd_itm_no)))
    d_kr.add(ETF_URI[r.pd_itm_no], pairs)

for uri, sec, weight, as_of, source in hold_rows:
    d_kr.add(uri, [("a", "fp:Holding"), ("fp:holdingSecurity", sec),
                   ("fp:weight", dec(weight) if weight else ""),  # 결측 798건은 트리플 생략
                   ("fp:asOf", date(as_of)), ("fp:sourceId", lit(source))])

# 테마 개체는 etf_kr.ttl에 이미 선언되어 있다. URI가 어긋나면 그래프가 끊기므로 즉시 실패시킨다.
declared = set(re.findall(r"<(http://mafest\.ai/product#Theme_[^>]+)>", (OUT / "etf_kr.ttl").read_text("utf-8")))
missing = {i.strip("<>") for i in theme_iris} - declared
assert not missing, f"etf_kr.ttl에 없는 테마 URI {len(missing)}건: {sorted(missing)[:5]}"

# ── 3. 해외ETF/ETN ─────────────────────────────────────────────────────────
etf_gl = read("data/csv/PREF02N001_etf_gl_master_20260824.csv").sort_values("pd_itm_no")
d_gl = Doc(f"fp-instances-etf-gl — 해외ETF·ETN {len(etf_gl):,}종",
           "출처: PREF02N001_etf_gl_master_20260824.csv (pd_grp_no로 ETF/ETN 분리)")
for r in etf_gl.itertuples(index=False):
    d_gl.add(f"fpi:etfgl-{esc(r.pd_itm_no)}",
             [("a", "fp:ETN" if r.pd_grp_no == "ETN" else "fp:ETF"),
              ("rdfs:label", lit(r.pd_nm)),
              ("fp:productCode", lit(r.pd_itm_no)), ("fp:productName", lit(r.pd_nm)),
              ("fp:productShortName", lit(r.pd_abrv_nm) if r.pd_abrv_nm else ""),
              ("fp:ticker", lit(r.pd_abrv_nm) if r.pd_abrv_nm else ""),
              ("fp:isinCode", lit(r.pd_isin_cd) if r.pd_isin_cd else "")]
             + links(link("fp:hasCurrency", CL_CURR, r.pd_trd_ccy),
                     # domain이 union(ETF, PublicFund)라 ETN에는 붙일 수 없다
                     link("fp:hasReplicationMethod", CL_REPL, r.cu_index_repl_mthd)
                     if r.pd_grp_no != "ETN" else None,
                     link("fp:hasInvestmentRegion", CL_REGION, r.wu_inv_rgn)))

# ── 4. 공모펀드 ────────────────────────────────────────────────────────────
d_fund = Doc(f"fp-instances-fund-pub — 펀드 {len(fund):,}종(itm_no 유일)",
             "출처: PRFD01N001_fund_pub_master_20260824.csv. 사모·구분 결측 상품은 fp:PublicFund가"
             "\n# 공모 한정 클래스이므로 fp:Product로만 선언한다(스키마 fp:PublicFund 주석 준수).")
for r in fund.itertuples(index=False):
    pub = r.prvo_pbff_desc == "공모"
    pairs = [("a", "fp:PublicFund" if pub else "fp:Product"),
             ("rdfs:label", lit(r.itm_nm)),
             ("fp:productCode", lit(r.itm_no)), ("fp:productName", lit(r.itm_nm)),
             ("fp:productShortName", lit(r.itm_abrv_nm) if r.itm_abrv_nm else ""),
             ("fp:ksdCode", lit(r.ksd_itm_no) if pub and r.ksd_itm_no else "")]
    pairs += links(
        link("fp:hasRiskGrade", CL_RISK, r.zrin_fd_ivst_risk_gcd),
        link("fp:hasInvestmentRegion", CL_REGION, r.fd_ivst_rgn_desc),
        link("fp:hasAssetType", CL_ASSET, r.or_attr_desc),
        link("fp:hasCurrency", CL_CURR, r.curr_cd),
        # 아래 둘은 domain이 fp:PublicFund다. 사모·구분결측은 fp:Product로만 선언되므로 생략한다.
        link("fp:hasFundType", CL_FUNDTYPE, r.or_attr_desc) if pub else None,
        link("fp:hasInvestorEligibility", CL_ELIG, r.prvo_pbff_desc) if pub else None)
    if r.ksd_itm_no in ETF_URI:
        pairs.append(("fp:sameVehicleAs", ETF_URI[r.ksd_itm_no]))
    d_fund.add(f"fpi:fund-{esc(r.itm_no)}", pairs)

# ── 5. 기업·증권·자회사 관계 ────────────────────────────────────────────────
sub = read("data/relations/company_subsidiary.csv").sort_values(
    ["parent_corp_code", "child_name_norm", "child_corp_code", "ownership_pct"], kind="stable")
sub["seq"] = sub.groupby(["parent_corp_code", "child_name_norm"]).cumcount()  # 중복 공시 105건

sub_rows = []
for r in sub.itertuples(index=False):
    parent = company(r.parent_name, code=r.parent_corp_code)
    child = company(r.child_name, code=r.child_corp_code)
    uri = f"fpi:sub-{esc(r.parent_corp_code)}-{esc(r.child_name_norm)}-{r.seq}"
    sub_rows.append((uri, parent, child, r.ownership_pct, r.as_of, r.source))

# 증권 → 발행기업 (해소표 우선, 없으면 상장 종목코드 직매칭)
sec_company = {}
for uri, e in securities.items():
    code = MAP2CORP.get(e["code"]) or STOCK2CODE.get(e["code"])
    if code:
        sec_company[uri] = company(CODE2NAME[code], code=code)

d_co = Doc("fp-instances-company — 참조된 기업/발행사 + 편입증권 + 자회사 관계",
           "출처: data/enriched/company_master.csv(DART), data/relations/company_subsidiary.csv,"
           "\n# data/relations/etf_holding.csv. 전 118,709사가 아니라 **참조되는 기업만** 만든다.")
for uri in sorted(companies):
    e = companies[uri]
    label = CODE2NAME[e["code"]] if e["code"] else min(e["labels"])
    alt = sorted(x for x in e["labels"] if x and x != label)
    d_co.add(uri, [("a", sorted(f"fp:{t}" for t in e["types"])),
                   ("rdfs:label", lit(label)),
                   ("fp:organizationName", lit(norm(label))),
                   ("fp:corpCode", lit(e["code"]) if e["code"] else ""),
                   ("skos:altLabel", [lit(x) for x in alt] if alt else "")])

for uri in sorted(securities):
    e = securities[uri]
    names = sorted(e["names"])
    d_co.add(uri, [("a", "fp:Security"),
                   ("rdfs:label", lit(names[0]) if names else lit(e["code"])),
                   ("fp:securityCode", lit(e["code"])),
                   ("skos:altLabel", [lit(x) for x in names[1:]] if len(names) > 1 else ""),
                   ("fp:issuedByCompany", sec_company.get(uri, ""))])

for uri, parent, child, pct, as_of, source in sorted(sub_rows):
    d_co.add(uri, [("a", "fp:SubsidiaryRelation"), ("fp:subsidiaryCompany", child),
                   ("fp:ownershipPct", dec(pct) if pct else ""),  # 결측 2,378건은 트리플 생략
                   ("fp:asOf", date(as_of)), ("fp:sourceId", lit(source))])
# 모회사 → 관계 노드. 기업 블록과 분리해 두어야 정렬이 결정적이다.
by_parent = {}
for uri, parent, *_ in sub_rows:
    by_parent.setdefault(parent, []).append(uri)
for parent in sorted(by_parent):
    d_co.add(parent, [("fp:hasSubsidiary", sorted(by_parent[parent]))])

# ── 출력 ───────────────────────────────────────────────────────────────────
print(f"{'파일':32s} {'엔티티':>8s} {'트리플':>9s} {'크기':>10s}")
total = 0
for name, doc in [("instances_bond_kr.ttl", d_bond), ("instances_etf_kr.ttl", d_kr),
                  ("instances_etf_gl.ttl", d_gl), ("instances_fund_pub.ttl", d_fund),
                  ("instances_company.ttl", d_co)]:
    size = doc.write(OUT / name)
    total += doc.triples
    print(f"  {name:30s} {len(doc.blocks):8,d} {doc.triples:9,d} {size/1e6:9.2f}MB")
print(f"  {'합계':30s} {'':8s} {total:9,d}")
print(f"기업 {len(companies):,}종(고유번호 매칭 {sum(1 for e in companies.values() if e['code']):,}) / "
      f"증권 {len(securities):,}종(발행기업 링크 {len(sec_company):,}) / "
      f"편입관계 {len(hold_rows):,} / 자회사관계 {len(sub_rows):,} / 동일상품 {len(SAME)}")

# ── 코드리스트 배선 보고 ────────────────────────────────────────────────────
# 0건인 축은 배선이 끊긴 것이다. 미매핑은 조용히 넘기지 않고 전부 센다.
print("\n코드리스트 링크")
for prop, n in sorted(_HIT.items(), key=lambda x: -x[1]):
    print(f"  {prop:<28} {n:>7,d}")
if _MISS:
    print(f"미매핑 (사전에 없어 트리플 생략) — {sum(_MISS.values()):,}건 / {len(_MISS)}종")
    for (prop, val), n in sorted(_MISS.items(), key=lambda x: -x[1])[:12]:
        print(f"  {prop:<28} {val[:24]:<26} {n:>7,d}")
print(f"소요 {time.time() - t0:.1f}s")
