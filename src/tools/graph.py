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
  FILTER (?relation_as_of <= "2026-07-11"^^xsd:date)
  ?child rdfs:label ?child_name .
  ?security fp:issuedByCompany ?child .
  ?holding fp:holdingSecurity ?security ; fp:asOf ?holding_as_of ;
           fp:sourceId ?holding_source ; fp:supportedBy ?holding_document .
  ?holding_document a fp:Document ; fp:documentTitle ?holding_document_title ;
           fp:documentPublisher ?holding_document_publisher ;
           fp:documentPublishedDate ?holding_document_date ;
           fp:documentQuote ?holding_document_quote .
  FILTER (?holding_as_of <= "2026-07-11"^^xsd:date)
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
