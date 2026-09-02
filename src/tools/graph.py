# -*- coding: utf-8 -*-
"""읽기 전용 pyoxigraph SPARQL과 최초 관계 vertical slice."""
from __future__ import annotations

import re
from functools import lru_cache

from config import ARTIFACTS

try:
    from pyoxigraph import Store
except ImportError as exc:  # pragma: no cover - 설치 안내 경로
    raise SystemExit("pyoxigraph 미설치 — python3 -m pip install -r requirements.txt") from exc

STORE_PATH = ARTIFACTS / "oxigraph"
MAX_ROWS = 10_000
_FORBIDDEN = re.compile(
    r"\b(?:ADD|CLEAR|COPY|CREATE|DELETE|DROP|INSERT|LOAD|MOVE|SERVICE|WITH)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _store() -> Store:
    if not STORE_PATH.is_dir():
        raise RuntimeError("Graph store 미구축 — python3 src/kb/build_graph.py")
    return Store.read_only(str(STORE_PATH))


def _value(term):
    if term is None:
        return None
    return term.value


def sparql(query: str) -> bool | list[dict]:
    """SELECT/ASK만 허용한다. Agent는 아래 고정 template 함수만 호출한다."""
    text = query.lstrip()
    text = re.sub(r"(?is)^(?:PREFIX\s+\w*:\s*<[^>]+>\s*)+", "", text).lstrip()
    kind = text.split(None, 1)[0].upper() if text else ""
    if kind not in {"SELECT", "ASK"} or _FORBIDDEN.search(query):
        raise ValueError("Graph query는 SERVICE 없는 SELECT/ASK만 허용합니다")
    result = _store().query(query)
    if kind == "ASK":
        return bool(result)
    variables = [v.value for v in result.variables]
    rows = []
    for solution in result:
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"Graph 결과가 상한 {MAX_ROWS:,}행을 초과했습니다")
        rows.append({name: _value(solution[name]) for name in variables})
    return rows


ECOPRO_HOLDING_QUERY = """
PREFIX fp: <http://mafest.ai/product#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?etf ?etf_name ?child ?child_name ?security ?weight ?holding_as_of
                ?holding_source ?relation_as_of ?relation_source
                ?holding_document_title ?holding_document_publisher
                ?holding_document_date ?holding_document_quote
                ?relation_document_title ?relation_document_publisher
                ?relation_document_date ?relation_document_quote WHERE {
  ?parent a fp:Company ; rdfs:label "에코프로" ; fp:hasSubsidiary ?relation .
  ?relation fp:subsidiaryCompany ?child ; fp:asOf ?relation_as_of ;
            fp:sourceId ?relation_source ; fp:supportedBy ?relation_document .
  ?relation_document a fp:Document ; fp:documentTitle ?relation_document_title ;
            fp:documentPublisher ?relation_document_publisher ;
            fp:documentPublishedDate ?relation_document_date ;
            fp:documentQuote ?relation_document_quote .
  FILTER (?relation_as_of <= "2026-08-24"^^xsd:date)
  ?child rdfs:label ?child_name .
  ?security fp:issuedByCompany ?child .
  ?holding fp:holdingSecurity ?security ; fp:asOf ?holding_as_of ;
           fp:sourceId ?holding_source ; fp:supportedBy ?holding_document .
  ?holding_document a fp:Document ; fp:documentTitle ?holding_document_title ;
           fp:documentPublisher ?holding_document_publisher ;
           fp:documentPublishedDate ?holding_document_date ;
           fp:documentQuote ?holding_document_quote .
  FILTER (?holding_as_of <= "2026-08-24"^^xsd:date)
  OPTIONAL { ?holding fp:weight ?weight }
  ?etf a fp:ETF ; fp:hasHolding ?holding ; rdfs:label ?etf_name .
}
ORDER BY ?etf_name ?child_name
"""


def ecopro_subsidiary_etfs() -> list[dict]:
    return sparql(ECOPRO_HOLDING_QUERY)


def evidence_coverage() -> dict:
    """Store 전체의 운영 대상 Graph 관계 evidence 계약을 집계한다."""
    result = {}
    for label, cls in (("holding", "Holding"), ("subsidiary_relation", "SubsidiaryRelation")):
        total = sparql(f"""
PREFIX fp: <http://mafest.ai/product#>
SELECT (COUNT(DISTINCT ?relation) AS ?count) WHERE {{ ?relation a fp:{cls} . }}
""")[0]["count"]
        supported = sparql(f"""
PREFIX fp: <http://mafest.ai/product#>
SELECT (COUNT(DISTINCT ?relation) AS ?count) WHERE {{
  ?relation a fp:{cls} ; fp:supportedBy ?document .
  ?document a fp:Document .
}}
""")[0]["count"]
        total, supported = int(total), int(supported)
        result[label] = {"total": total, "supported": supported,
                         "coverage": supported / total if total else 1.0}
    return result



# === Graph 검색 템플릿 (검증: EXP-20260828-graph-01 G01~G12, EXP-20260828-integrated-01) ===
# 아래 템플릿의 어휘(predicate·URI 패턴)는 로컬 store(1,628,311 triples, cutoff 2026-08-24)
# 실측 프로브로 검증된 것이다:
#   상품: fpi:{etfkr|etfgl|fund|bond}-<코드>, fp:productShortName/productName/productCode
#   기업: fpi:corp-<코드>, fp:organizationName + rdfs:label + skos:altLabel
#   편입: 상품 -fp:hasHolding-> Holding{holdingSecurity, weight, asOf, sourceId, supportedBy}
#   자회사: 기업 -fp:hasSubsidiary-> SubsidiaryRelation{subsidiaryCompany, ownershipPct, asOf, supportedBy}
#   증권↔기업: ?sec fp:issuedByCompany ?corp / 채권 발행: ?bond fp:issuedBy ?issuer
PREFIXES = (
    "PREFIX fp: <http://mafest.ai/product#>\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
    "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n"
    "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
)
DATA_CUTOFF = "2026-08-24"


def _lit(text: str) -> str:
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _q(body: str) -> list:
    return sparql(PREFIXES + body)


def _result(rows, status=None, **extra):
    out = {"status": status or ("ok" if rows else "empty"), "rows": rows}
    out.update(extra)
    return out


# 자연어 해석기는 이 이름만 반환하고, 실제 SPARQL은 여기 등록된 함수가
# 생성한다.  따라서 LLM이 임의의 함수나 Python 코드를 실행할 수 없다.
_TEMPLATE_NAMES = {
    "product_info": "product_info",
    "product_classifications": "product_classifications",
    "company_info": "company_info",
    "subsidiaries": "subsidiaries",
    "product_holdings": "product_holdings",
    "etfs_holding_security": "etfs_holding_security",
    "subsidiary_holding_etfs": "subsidiary_holding_etfs",
    "bond_info": "bond_info",
    "product_info_by_code": "product_info_by_code",
    "etfs_holding_security_like": "etfs_holding_security_like",
    "subsidiary_holding_etf_codes": "subsidiary_holding_etf_codes",
}


def _validate_generated_query(query: str) -> str:
    """Text2SPARQL 산출물을 실행 전에 검증한다.

    자유 생성 경로도 sparql()의 읽기 전용 계약을 공유한다. 알려진 prefix만
    허용하고, PREFIX 뒤의 실제 질의가 SELECT/ASK인지 확인한다.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("생성된 Graph query가 비어 있습니다")

    allowed_prefixes = {"fp", "rdfs", "rdf", "skos", "xsd"}
    prefix_re = re.compile(
        r"(?is)^\s*PREFIX\s+([A-Za-z_]\w*)\s*:\s*<[^>]+>\s*"
    )
    rest = query
    while True:
        match = prefix_re.match(rest)
        if not match:
            break
        if match.group(1) not in allowed_prefixes:
            raise ValueError(f"허용하지 않는 SPARQL prefix: {match.group(1)}")
        rest = rest[match.end():]

    kind = rest.lstrip().split(None, 1)[0].upper() if rest.strip() else ""
    if kind not in {"SELECT", "ASK"}:
        raise ValueError("Text2SPARQL은 SELECT/ASK만 생성해야 합니다")
    return query


def hybrid_search(template: str | None = None, params: dict | None = None,
                  generated_query: str | None = None) -> dict:
    """템플릿 우선, 미지원/무결과 시 제한된 Text2SPARQL fallback.

    ``template``은 ``_TEMPLATE_NAMES``에 등록된 함수명만 받을 수 있다.
    Text2SPARQL은 호출자가 LLM으로 생성해 전달하되, 실행 직전에 동일한
    읽기 전용 검증을 받는다. 두 경로 모두 결과 형식을 ``dict``로 통일한다.
    """
    params = dict(params or {})
    template_error = None

    if template:
        function_name = _TEMPLATE_NAMES.get(template)
        if function_name is None:
            template_error = f"지원하지 않는 Graph 템플릿: {template}"
        else:
            try:
                result = globals()[function_name](**params)
                if result.get("rows"):
                    result["retrieval_mode"] = "template"
                    result["fallback_used"] = False
                    return result
                template_error = "템플릿 조회 결과가 없습니다"
            except Exception as exc:  # fallback 경로에서 생성 질의를 시도한다.
                template_error = f"템플릿 실행 실패: {type(exc).__name__}: {exc}"

    if generated_query is not None:
        try:
            query = _validate_generated_query(generated_query)
            raw = sparql(query)
            rows = ([{"ask": raw}] if isinstance(raw, bool) else raw)
            return _result(rows, retrieval_mode="text2sparql",
                           fallback_used=True, template_error=template_error)
        except Exception as exc:
            return _result([], status="abstain_invalid_graph_query",
                           retrieval_mode="text2sparql", fallback_used=True,
                           template_error=template_error,
                           query_error=f"{type(exc).__name__}: {exc}")

    return _result([], status="abstain_unsupported_graph_query",
                   retrieval_mode="none", fallback_used=False,
                   template_error=template_error)


def product_info(short_name: str) -> dict:
    """G01/G02: 상품 URI·정식명·코드·투자지역."""
    rows = _q(f"""
SELECT ?product ?name ?code ?region_label WHERE {{
  ?product fp:productShortName {_lit(short_name)} .
  OPTIONAL {{ ?product fp:productName ?name }}
  OPTIONAL {{ ?product fp:productCode ?code }}
  OPTIONAL {{ ?product fp:hasInvestmentRegion ?r . ?r rdfs:label ?region_label .
             FILTER(lang(?region_label) = "ko") }}
}}""")
    return _result(rows)


def product_classifications(short_name: str) -> dict:
    """G08: 상품에 연결된 분류 개체(투자지역·자산유형·테마·위험등급 등)."""
    rows = _q(f"""
SELECT ?pred ?node ?node_label ?node_type WHERE {{
  ?product fp:productShortName {_lit(short_name)} ; ?pred ?node .
  ?node rdf:type ?node_type .
  FILTER(?node_type IN (fp:InvestmentRegion, fp:AssetType, fp:Theme, fp:RiskGrade,
                        fp:FundType, fp:Currency, fp:ManagementStrategy, fp:LeverageType))
  OPTIONAL {{ ?node rdfs:label ?node_label . FILTER(lang(?node_label) = "ko") }}
}}""")
    return _result(rows)


def company_info(name: str) -> dict:
    """G03: 기업 URI + 등록된 다른 이름(rdfs:label, skos:altLabel)."""
    rows = _q(f"""
SELECT ?company ?label ?alt WHERE {{
  ?company rdf:type fp:Company ; fp:organizationName {_lit(name)} .
  OPTIONAL {{ ?company rdfs:label ?label }}
  OPTIONAL {{ ?company skos:altLabel ?alt }}
}}""")
    return _result(rows)


def subsidiaries(company_name: str, limit: int = 30) -> dict:
    """G04: 자회사 관계 + 기준일(asOf)·출처(sourceId, supportedBy 문서 제목)."""
    rows = _q(f"""
SELECT ?relation ?child_name ?ownership_pct ?as_of ?source ?doc_title WHERE {{
  ?parent rdf:type fp:Company ; fp:organizationName {_lit(company_name)} ;
          fp:hasSubsidiary ?relation .
  ?relation fp:subsidiaryCompany ?child .
  ?child fp:organizationName ?child_name .
  OPTIONAL {{ ?relation fp:ownershipPct ?ownership_pct }}
  OPTIONAL {{ ?relation fp:asOf ?as_of }}
  OPTIONAL {{ ?relation fp:sourceId ?source }}
  OPTIONAL {{ ?relation fp:supportedBy ?doc . ?doc fp:documentTitle ?doc_title }}
  FILTER(!BOUND(?as_of) || ?as_of <= "{DATA_CUTOFF}"^^xsd:date)
}} ORDER BY ?child_name LIMIT {int(limit)}""")
    return _result(rows)


def product_holdings(short_name: str, limit: int = 10) -> dict:
    """G05: 상품 → 편입 증권 + 비중 + 기준일."""
    rows = _q(f"""
SELECT ?security_label ?weight ?as_of ?source WHERE {{
  ?product fp:productShortName {_lit(short_name)} ; fp:hasHolding ?h .
  ?h fp:holdingSecurity ?sec .
  OPTIONAL {{ ?sec rdfs:label ?security_label }}
  OPTIONAL {{ ?h fp:weight ?weight }}
  OPTIONAL {{ ?h fp:asOf ?as_of }}
  OPTIONAL {{ ?h fp:sourceId ?source }}
  FILTER(!BOUND(?as_of) || ?as_of <= "{DATA_CUTOFF}"^^xsd:date)
}} ORDER BY DESC(?weight) LIMIT {int(limit)}""")
    return _result(rows)


def etfs_holding_security(security_label: str, limit: int = 20) -> dict:
    """G06/G12: 증권 라벨 → 역방향 → 편입 ETF."""
    rows = _q(f"""
SELECT DISTINCT ?etf ?etf_name ?weight ?as_of WHERE {{
  ?sec rdf:type fp:Security ; rdfs:label {_lit(security_label)} .
  ?h fp:holdingSecurity ?sec .
  ?etf rdf:type fp:ETF ; fp:hasHolding ?h ; fp:productShortName ?etf_name .
  OPTIONAL {{ ?h fp:weight ?weight }}
  OPTIONAL {{ ?h fp:asOf ?as_of }}
}} ORDER BY DESC(?weight) LIMIT {int(limit)}""")
    return _result(rows)


def subsidiary_holding_etfs(company_name: str, limit: int = 50) -> dict:
    """G07: 기업 → 자회사 → (자회사 발행 증권) → 편입 ETF. (ecopro 하드코딩 일반화)"""
    rows = _q(f"""
SELECT DISTINCT ?etf_name ?child_name ?security_label ?weight ?holding_as_of WHERE {{
  ?parent rdf:type fp:Company ; fp:organizationName {_lit(company_name)} ;
          fp:hasSubsidiary ?relation .
  ?relation fp:subsidiaryCompany ?child .
  ?child fp:organizationName ?child_name .
  ?sec fp:issuedByCompany ?child .
  OPTIONAL {{ ?sec rdfs:label ?security_label }}
  ?h fp:holdingSecurity ?sec .
  OPTIONAL {{ ?h fp:weight ?weight }}
  OPTIONAL {{ ?h fp:asOf ?holding_as_of }}
  ?etf rdf:type fp:ETF ; fp:hasHolding ?h ; fp:productShortName ?etf_name .
  FILTER(!BOUND(?holding_as_of) || ?holding_as_of <= "{DATA_CUTOFF}"^^xsd:date)
}} ORDER BY ?etf_name LIMIT {int(limit)}""")
    return _result(rows)


def bond_info(product_name: str) -> dict:
    """G09: 채권 종류(rdf:type)·발행사·신용등급."""
    rows = _q(f"""
SELECT ?bond ?cls ?issuer_name ?rating WHERE {{
  ?bond fp:productName {_lit(product_name)} ; rdf:type ?cls .
  FILTER(?cls IN (fp:CorporateBond, fp:GovernmentBond, fp:SpecialBond, fp:Bond))
  OPTIONAL {{ ?bond fp:issuedBy ?issuer . ?issuer fp:organizationName ?issuer_name }}
  OPTIONAL {{ ?bond fp:hasCreditRating ?r . BIND(REPLACE(STR(?r), ".*#Rating_", "") AS ?rating) }}
}}""")
    return _result(rows)


def fund_holdings_check() -> dict:
    """G10: 펀드 편입 데이터 적재 여부 — empty(관계 없음)와 data_gap(미적재)을 구분."""
    funds = int(_q("SELECT (COUNT(DISTINCT ?f) AS ?n) WHERE { ?f rdf:type fp:PublicFund . ?f fp:hasHolding ?h }")[0]["n"])
    products = int(_q("SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?p fp:hasHolding ?h }")[0]["n"])
    total_funds = int(_q("SELECT (COUNT(DISTINCT ?f) AS ?n) WHERE { ?f rdf:type fp:PublicFund }")[0]["n"])
    status = "ok" if funds else ("data_gap" if products else "empty")
    note = (f"편입 관계 보유 상품 {products}개(전부 ETF), 펀드 {total_funds}개 중 0개 → "
            "펀드 편입 데이터 미적재(data_gap). '펀드가 주식을 편입하지 않는다'가 아니다."
            if status == "data_gap" else "")
    return {"status": status, "rows": [], "funds_with_holdings": funds,
            "products_with_holdings": products, "total_funds": total_funds, "note": note}


def domain_violation(short_name: str, prop: str = "issuedBy") -> dict:
    """G11: TBox rdfs:domain 과 주어 클래스 비교 — 잘못된 온톨로지 관계 거부."""
    subj = _q(f"SELECT DISTINCT ?product ?cls WHERE {{ ?product fp:productShortName {_lit(short_name)} ; rdf:type ?cls }}")
    if not subj:
        return {"status": "empty", "rows": [], "note": "주어 상품 부재"}
    domains = [d["d"] for d in _q(f"SELECT ?d WHERE {{ fp:{prop} rdfs:domain ?d }}")]
    ok_rows = []
    for s in subj:
        for dom in domains:
            if sparql(PREFIXES + f"ASK {{ <{s['cls']}> rdfs:subClassOf* <{dom}> }}"):
                ok_rows.append({"cls": s["cls"], "domain": dom})
    if ok_rows:
        return {"status": "ok", "rows": ok_rows}
    comment = _q(f"SELECT ?c WHERE {{ fp:{prop} rdfs:comment ?c }}")
    return {"status": "abstain_domain_error", "rows": [],
            "subject_classes": sorted({s["cls"] for s in subj}),
            "required_domain": domains,
            "tbox_comment": (comment[0]["c"][:300] if comment else "")}


def product_info_by_code(code: str) -> dict:
    """통합실험 Q02: productCode 로 상품 조회 (shortName 이 모호한 펀드용)."""
    rows = _q(f"""
SELECT ?product ?short_name ?name ?region_label ?risk WHERE {{
  ?product fp:productCode {_lit(code)} .
  OPTIONAL {{ ?product fp:productShortName ?short_name }}
  OPTIONAL {{ ?product fp:productName ?name }}
  OPTIONAL {{ ?product fp:hasInvestmentRegion ?r . ?r rdfs:label ?region_label .
             FILTER(lang(?region_label) = "ko") }}
  OPTIONAL {{ ?product fp:hasRiskGrade ?rg . BIND(REPLACE(STR(?rg), ".*#", "") AS ?risk) }}
}}""")
    return _result(rows)


def etfs_holding_security_like(substr: str, limit: int = 30) -> dict:
    """통합실험 Q03: 증권 라벨 부분일치(영문 별칭 대응) → 편입 ETF + 코드."""
    rows = _q(f"""
SELECT DISTINCT ?etf_name ?etf_code ?security_label ?weight ?as_of WHERE {{
  ?sec rdf:type fp:Security ; rdfs:label ?security_label .
  FILTER(CONTAINS(LCASE(STR(?security_label)), LCASE({_lit(substr)})))
  ?h fp:holdingSecurity ?sec .
  ?etf fp:hasHolding ?h ; fp:productShortName ?etf_name .
  OPTIONAL {{ ?etf fp:productCode ?etf_code }}
  OPTIONAL {{ ?h fp:weight ?weight }}
  OPTIONAL {{ ?h fp:asOf ?as_of }}
}} ORDER BY DESC(?weight) LIMIT {int(limit)}""")
    return _result(rows)


def subsidiary_holding_etf_codes(company_name: str, limit: int = 100) -> dict:
    """통합실험 Q05: 자회사 편입 ETF 의 상품코드 목록 (RDB 랭킹 입력)."""
    rows = _q(f"""
SELECT DISTINCT ?etf_name ?etf_code ?child_name WHERE {{
  ?parent rdf:type fp:Company ; fp:organizationName {_lit(company_name)} ;
          fp:hasSubsidiary ?relation .
  ?relation fp:subsidiaryCompany ?child .
  ?child fp:organizationName ?child_name .
  ?sec fp:issuedByCompany ?child .
  ?h fp:holdingSecurity ?sec .
  ?etf rdf:type fp:ETF ; fp:hasHolding ?h ;
       fp:productShortName ?etf_name ; fp:productCode ?etf_code .
}} ORDER BY ?etf_name LIMIT {int(limit)}""")
    return _result(rows)


def class_counts() -> dict:
    """체크리스트 3번: 주식·ETF·펀드·채권·기업이 모두 조회되는가."""
    out = {}
    for cls in ("Security", "ETF", "PublicFund", "CorporateBond",
                "GovernmentBond", "SpecialBond", "Company"):
        out[cls] = int(_q(f"SELECT (COUNT(?s) AS ?n) WHERE {{ ?s rdf:type fp:{cls} }}")[0]["n"])
    return out
