# -*- coding: utf-8 -*-
"""Allow-listed SQL/SPARQL builders and evidence helpers for Data API V1."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from data_api.contracts import (
    OntologyValidateRequest,
    ProductQueryRequest,
    ProductSearchRequest,
    RelationTraverseRequest,
)
from kb.v2_manifest import EXTERNAL_CUTOFF


class DataApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


CREDIT_RATING_RANK = {
    "AAA": 1,
    "AA+": 2,
    "AA": 3,
    "AA0": 3,
    "AA-": 4,
    "A+": 5,
    "A": 6,
    "A0": 6,
    "A-": 7,
    "BBB+": 8,
    "BBB": 9,
    "BBB0": 9,
    "BBB-": 10,
    "BB+": 11,
    "BB": 12,
    "BB0": 12,
    "BB-": 13,
    "B+": 14,
    "B": 15,
    "B0": 15,
    "B-": 16,
    "CCC": 17,
    "CC": 18,
    "C": 19,
}

RATING_RANK_SQL = """
CASE upper(b.credit_rating)
  WHEN 'AAA' THEN 1 WHEN 'AA+' THEN 2 WHEN 'AA' THEN 3 WHEN 'AA0' THEN 3
  WHEN 'AA-' THEN 4 WHEN 'A+' THEN 5 WHEN 'A' THEN 6 WHEN 'A0' THEN 6
  WHEN 'A-' THEN 7 WHEN 'BBB+' THEN 8 WHEN 'BBB' THEN 9 WHEN 'BBB0' THEN 9
  WHEN 'BBB-' THEN 10 WHEN 'BB+' THEN 11 WHEN 'BB' THEN 12 WHEN 'BB0' THEN 12
  WHEN 'BB-' THEN 13 WHEN 'B+' THEN 14 WHEN 'B' THEN 15 WHEN 'B0' THEN 15
  WHEN 'B-' THEN 16 WHEN 'CCC' THEN 17 WHEN 'CC' THEN 18 WHEN 'C' THEN 19
END
""".strip()

FILTER_COLUMNS = {
    "AUM": "aum.value",
    "RETURN_1Y": "ret.value",
    "EXPENSE_RATIO": "expense.value",
    "MATURITY_DATE": "b.maturity_date",
    "CREDIT_RATING_RANK": RATING_RANK_SQL,
    "ASSUMED_PURCHASABLE": "b.is_assumed_purchasable",
    "BUY_YIELD": "offer.buy_yield",
}
OPERATORS = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
NUMERIC_FIELDS = {"AUM", "RETURN_1Y", "EXPENSE_RATIO", "CREDIT_RATING_RANK", "BUY_YIELD"}


def _normalized_sql(column: str) -> str:
    return f"regexp_replace(lower(COALESCE({column},'')), '[^0-9a-z가-힣]', '', 'g')"


def product_search_statement(request: ProductSearchRequest) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "name": request.name,
        "normalized_name": "".join(character.lower() for character in request.name if character.isalnum()),
        "product_types": request.product_types or None,
        "limit": request.limit,
    }
    exact = "(p.name=%(name)s OR p.short_name=%(name)s OR p.source_key=%(name)s)"
    normalized = (
        f"({_normalized_sql('p.name')}=%(normalized_name)s OR "
        f"{_normalized_sql('p.short_name')}=%(normalized_name)s OR "
        f"{_normalized_sql('p.source_key')}=%(normalized_name)s)"
    )
    contains = (
        "(p.name ILIKE '%%' || %(name)s || '%%' OR "
        "p.short_name ILIKE '%%' || %(name)s || '%%' OR "
        "p.source_key ILIKE '%%' || %(name)s || '%%')"
    )
    predicate = {"exact": exact, "normalized_exact": normalized, "contains": contains}[request.match]
    statement = f"""
        SELECT p.product_id,p.product_type,p.market_scope,p.name,p.short_name,p.currency,
               p.is_active,p.effective_as_of,p.source_table,p.source_key,
               c.holdings_status,c.holdings_reason,c.document_status,c.document_reason,
               c.performance_status,c.performance_reason,
               CASE WHEN {exact} THEN 'exact'
                    WHEN {normalized} THEN 'normalized_exact'
                    ELSE 'contains' END AS match_type
        FROM enriched.product_master p
        LEFT JOIN meta.product_coverage c USING(product_id)
        WHERE {predicate}
          AND (%(product_types)s::text[] IS NULL OR p.product_type=ANY(%(product_types)s::text[]))
        ORDER BY CASE WHEN {exact} THEN 0 WHEN {normalized} THEN 1 ELSE 2 END,
                 p.product_type,p.name,p.product_id
        LIMIT %(limit)s
    """
    return statement, params


def _coerce_filter_value(field: str, value: str | float | bool) -> Any:
    if field in NUMERIC_FIELDS:
        if isinstance(value, bool):
            raise DataApiError(422, "INVALID_FILTER_VALUE", f"{field}에는 숫자가 필요합니다")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise DataApiError(422, "INVALID_FILTER_VALUE", f"{field}에는 숫자가 필요합니다") from exc
    if field == "MATURITY_DATE":
        try:
            return value if isinstance(value, date) else date.fromisoformat(str(value))
        except ValueError as exc:
            raise DataApiError(422, "INVALID_FILTER_VALUE", "MATURITY_DATE는 YYYY-MM-DD 형식이어야 합니다") from exc
    if field == "ASSUMED_PURCHASABLE":
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"true", "false"}:
            return str(value).lower() == "true"
        raise DataApiError(422, "INVALID_FILTER_VALUE", "ASSUMED_PURCHASABLE에는 boolean이 필요합니다")
    return value


def product_query_statement(request: ProductQueryRequest) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "product_types": request.product_types or None,
        "market_scope": request.market_scope,
        "currency": request.currency,
        "limit": request.limit,
    }
    predicates = [
        "(%(product_types)s::text[] IS NULL OR p.product_type=ANY(%(product_types)s::text[]))",
        "(%(market_scope)s::text IS NULL OR p.market_scope=%(market_scope)s::text)",
        "(%(currency)s::text IS NULL OR upper(p.currency)=upper(%(currency)s::text))",
    ]
    for index, item in enumerate(request.filters):
        if item.field == "ASSUMED_PURCHASABLE" and item.op != "eq":
            raise DataApiError(422, "INVALID_FILTER_OPERATOR", "boolean 필드는 eq만 허용합니다")
        name = f"filter_{index}"
        params[name] = _coerce_filter_value(item.field, item.value)
        predicates.append(f"({FILTER_COLUMNS[item.field]}) {OPERATORS[item.op]} %({name})s")

    sort_expression = "p.name" if request.sort_by == "NAME" else FILTER_COLUMNS[request.sort_by]
    null_order = "" if request.sort_by == "NAME" else " NULLS LAST"
    statement = f"""
        SELECT p.product_id,p.product_type,p.market_scope,p.name,p.short_name,p.currency,
               p.is_active,p.effective_as_of,p.source_table,p.source_key,
               aum.value AS aum,aum.unit AS aum_unit,aum.as_of AS aum_as_of,
               aum.source AS aum_source,aum.source_column AS aum_source_column,
               ret.value AS return_1y,ret.unit AS return_1y_unit,ret.as_of AS return_1y_as_of,
               ret.source AS return_1y_source,ret.source_column AS return_1y_source_column,
               expense.value AS expense_ratio,expense.unit AS expense_ratio_unit,
               expense.as_of AS expense_ratio_as_of,expense.source AS expense_ratio_source,
               expense.source_column AS expense_ratio_source_column,
               b.credit_rating,({RATING_RANK_SQL}) AS credit_rating_rank,
               b.maturity_date,b.is_assumed_purchasable,b.purchasable_rule,
               offer.buy_yield,offer.buy_yield_as_of,offer.buy_yield_source_column,
               c.holdings_status,c.holdings_reason,c.document_status,c.document_reason,
               c.performance_status,c.performance_reason
        FROM enriched.product_master p
        LEFT JOIN meta.product_coverage c USING(product_id)
        LEFT JOIN enriched.bond_kr_product b USING(product_id)
        LEFT JOIN LATERAL (
          SELECT value,unit,as_of,source,source_column FROM enriched.product_metric m
          WHERE m.product_id=p.product_id AND m.metric_code='AUM' AND m.is_available
          ORDER BY m.source_priority,m.as_of DESC NULLS LAST,m.metric_id LIMIT 1
        ) aum ON true
        LEFT JOIN LATERAL (
          SELECT value,unit,as_of,source,source_column FROM enriched.product_metric m
          WHERE m.product_id=p.product_id AND m.metric_code='RETURN_1Y' AND m.is_available
          ORDER BY m.source_priority,m.as_of DESC NULLS LAST,m.metric_id LIMIT 1
        ) ret ON true
        LEFT JOIN LATERAL (
          SELECT value,unit,as_of,source,source_column FROM enriched.product_metric m
          WHERE m.product_id=p.product_id AND m.metric_code='EXPENSE_RATIO' AND m.is_available
          ORDER BY m.source_priority,m.as_of DESC NULLS LAST,m.metric_id LIMIT 1
        ) expense ON true
        LEFT JOIN LATERAL (
          SELECT o.buy_yield,COALESCE(o.sale_yield_base_dt,o.info_base_dt) AS buy_yield_as_of,
                 'buy_yield'::text AS buy_yield_source_column
          FROM enriched.bond_kr_offer o
          WHERE o.product_id=p.product_id AND o.buy_yield IS NOT NULL AND o.buy_yield<>0
          ORDER BY COALESCE(o.sale_yield_base_dt,o.info_base_dt) DESC,o.info_seq DESC LIMIT 1
        ) offer ON true
        WHERE {' AND '.join(predicates)}
        ORDER BY {sort_expression} {request.sort_order.upper()}{null_order},p.product_id
        LIMIT %(limit)s
    """
    return statement, params


def compare_statement(product_ids: list[str], metric_codes: list[str]) -> tuple[str, dict[str, Any]]:
    return (
        """
        SELECT requested.product_id,requested.product_order,p.product_type,p.name,p.currency,
               requested_metric.metric_code,requested_metric.metric_order,
               m.value,m.unit,m.as_of,m.source,m.source_column,m.method,m.is_available,
               m.unavailable_reason
        FROM unnest(%(product_ids)s::text[]) WITH ORDINALITY requested(product_id,product_order)
        CROSS JOIN unnest(%(metric_codes)s::text[]) WITH ORDINALITY
          requested_metric(metric_code,metric_order)
        LEFT JOIN enriched.product_master p ON p.product_id=requested.product_id
        LEFT JOIN LATERAL (
          SELECT value,unit,as_of,source,source_column,method,is_available,unavailable_reason
          FROM enriched.product_metric m
          WHERE m.product_id=requested.product_id
            AND m.metric_code=requested_metric.metric_code
          ORDER BY m.is_available DESC,m.source_priority,m.as_of DESC NULLS LAST,m.metric_id
          LIMIT 1
        ) m ON true
        ORDER BY requested.product_order,requested_metric.metric_order
        """,
        {"product_ids": product_ids, "metric_codes": metric_codes},
    )


DOMAIN_TABLES = {
    "BOND": "enriched.bond_kr_product",
    "ETF_KR": "enriched.etf_kr",
    "ETF_GL": "enriched.etf_gl",
    "ETN_KR": "enriched.etn_kr",
    "ETN_GL": "enriched.etn_gl",
    "FUND_PUB": "enriched.fund",
    "FUND_PRIVATE": "enriched.fund",
}


def domain_detail_statement(product_type: str) -> str:
    table = DOMAIN_TABLES.get(product_type)
    if table is None:
        raise DataApiError(500, "UNSUPPORTED_PRODUCT_TYPE", f"지원하지 않는 product_type: {product_type}")
    return f"SELECT to_jsonb(d)-'product_id' AS attributes FROM {table} d WHERE d.product_id=%(product_id)s"


def holdings_statement(product_id: str, as_of: str | date, limit: int) -> tuple[str, dict[str, Any]]:
    date_predicate = (
        "h.as_of=(SELECT max(h2.as_of) FROM relations.product_holding h2 WHERE h2.product_id=h.product_id)"
        if as_of == "latest"
        else "h.as_of=%(as_of)s::date"
    )
    return (
        f"""
        SELECT h.holding_id,h.product_id,h.security_id,s.display_name,s.security_type,
               s.issuer_name,s.country_code,h.weight,h.unit,h.as_of,h.source,
               h.source_document_id,d.title AS document_title,d.publisher,
               d.published_at,d.url AS source_url,d.source_hash
        FROM relations.product_holding h
        JOIN enriched.security_master s USING(security_id)
        JOIN relations.source_document d ON d.document_id=h.source_document_id
        WHERE h.product_id=%(product_id)s AND {date_predicate}
        ORDER BY h.weight DESC NULLS LAST,s.display_name,h.security_id
        LIMIT %(limit)s
        """,
        {"product_id": product_id, "as_of": None if as_of == "latest" else as_of, "limit": limit},
    )


RELATION_PATTERNS = {
    ("holds_security",),
    ("held_by_product",),
    ("parent_of",),
    ("parent_of", "held_by_product"),
    ("parent_of", "issued_bond"),
    ("issued_bond",),
    ("has_document",),
    ("same_vehicle_as",),
}


def relation_statement(request: RelationTraverseRequest) -> tuple[str, dict[str, Any]] | None:
    path = tuple(request.path)
    if path not in RELATION_PATTERNS:
        raise DataApiError(
            422,
            "UNSUPPORTED_RELATION_PATH",
            "허용되지 않은 관계 경로입니다",
            {"path": list(path), "allowed_paths": [list(item) for item in sorted(RELATION_PATTERNS)]},
        )
    if path == ("same_vehicle_as",):
        return None
    params = {
        "start": request.start_entity_id,
        "as_of": None if request.as_of == "latest" else request.as_of,
        "limit": request.limit,
    }
    as_of_holding = (
        "h.as_of=(SELECT max(h2.as_of) FROM relations.product_holding h2 WHERE h2.product_id=h.product_id)"
        if request.as_of == "latest"
        else "h.as_of=%(as_of)s::date"
    )
    as_of_subsidiary = (
        "r.as_of=(SELECT max(r2.as_of) FROM relations.company_subsidiary r2 WHERE r2.parent_security_id=r.parent_security_id)"
        if request.as_of == "latest"
        else "r.as_of=%(as_of)s::date"
    )
    identity = "(s.security_id=%(start)s OR s.display_name=%(start)s)"
    if path == ("holds_security",):
        return holdings_statement(request.start_entity_id, request.as_of, request.limit)
    if path == ("held_by_product",):
        return (
            f"""
            SELECT 'held_by_product' AS relation_type,h.security_id AS start_entity_id,
                   p.product_id AS end_entity_id,p.name AS end_label,h.weight,h.unit,h.as_of,
                   h.source,h.source_document_id,d.title AS document_title,d.publisher,
                   d.published_at,d.url AS source_url
            FROM enriched.security_master s
            JOIN relations.product_holding h ON h.security_id=s.security_id
            JOIN enriched.product_master p ON p.product_id=h.product_id
            JOIN relations.source_document d ON d.document_id=h.source_document_id
            WHERE {identity} AND {as_of_holding}
            ORDER BY h.weight DESC NULLS LAST,p.name LIMIT %(limit)s
            """,
            params,
        )
    if path == ("parent_of",):
        return (
            f"""
            SELECT 'parent_of' AS relation_type,parent.security_id AS start_entity_id,
                   child.security_id AS end_entity_id,child.display_name AS end_label,
                   r.ownership_pct,r.as_of,r.source,r.source_document_id,
                   d.title AS document_title,d.publisher,d.published_at,d.url AS source_url
            FROM enriched.security_master parent
            JOIN relations.company_subsidiary r ON r.parent_security_id=parent.security_id
            JOIN enriched.security_master child ON child.security_id=r.child_security_id
            JOIN relations.source_document d ON d.document_id=r.source_document_id
            WHERE (parent.security_id=%(start)s OR parent.display_name=%(start)s)
              AND {as_of_subsidiary}
            ORDER BY r.ownership_pct DESC NULLS LAST,child.display_name LIMIT %(limit)s
            """,
            params,
        )
    if path == ("parent_of", "held_by_product"):
        return (
            f"""
            SELECT 'parent_of/held_by_product' AS relation_type,parent.security_id AS start_entity_id,
                   child.security_id AS via_entity_id,child.display_name AS via_label,
                   p.product_id AS end_entity_id,p.name AS end_label,r.ownership_pct,
                   r.as_of AS relation_as_of,h.weight,h.unit,h.as_of AS holding_as_of,
                   r.source AS relation_source,h.source AS holding_source,
                   r.source_document_id AS relation_document_id,
                   h.source_document_id AS holding_document_id
            FROM enriched.security_master parent
            JOIN relations.company_subsidiary r ON r.parent_security_id=parent.security_id
            JOIN enriched.security_master child ON child.security_id=r.child_security_id
            JOIN relations.product_holding h ON h.security_id=child.security_id
            JOIN enriched.product_master p ON p.product_id=h.product_id
            WHERE (parent.security_id=%(start)s OR parent.display_name=%(start)s)
              AND {as_of_subsidiary} AND {as_of_holding}
            ORDER BY h.weight DESC NULLS LAST,p.name LIMIT %(limit)s
            """,
            params,
        )
    if path in {("issued_bond",), ("parent_of", "issued_bond")}:
        if path == ("issued_bond",):
            company_cte = (
                "SELECT s.security_id,s.display_name FROM enriched.security_master s "
                "WHERE s.security_id=%(start)s OR s.display_name=%(start)s"
            )
        else:
            company_cte = f"""
                SELECT child.security_id,child.display_name
                FROM enriched.security_master parent
                JOIN relations.company_subsidiary r ON r.parent_security_id=parent.security_id
                JOIN enriched.security_master child ON child.security_id=r.child_security_id
                WHERE (parent.security_id=%(start)s OR parent.display_name=%(start)s)
                  AND {as_of_subsidiary}
            """
        return (
            f"""
            WITH company AS ({company_cte})
            SELECT '{'/'.join(path)}' AS relation_type,company.security_id AS start_entity_id,
                   b.product_id AS end_entity_id,b.name AS end_label,b.issuer,b.credit_rating,
                   b.maturity_date,b.effective_as_of AS as_of,'PRBD01N001' AS source,
                   'pd_pbcm' AS source_column
            FROM company
            JOIN enriched.bond_kr_product b
              ON regexp_replace(lower(b.issuer),'[^0-9a-z가-힣]','','g') =
                 regexp_replace(lower(company.display_name),'[^0-9a-z가-힣]','','g')
            ORDER BY b.maturity_date,b.product_id LIMIT %(limit)s
            """,
            params,
        )
    if path == ("has_document",):
        return (
            """
            SELECT 'has_document' AS relation_type,p.product_id AS start_entity_id,
                   d.document_id AS end_entity_id,d.title AS end_label,pd.relation_type AS document_relation,
                   d.publisher,d.published_at AS as_of,d.url AS source_url,d.source_hash,
                   d.source_type,d.as_of AS document_as_of
            FROM enriched.product_master p
            JOIN relations.product_document pd ON pd.product_id=p.product_id
            JOIN relations.source_document d ON d.document_id=pd.document_id
            WHERE p.product_id=%(start)s
            ORDER BY d.published_at DESC,d.document_id LIMIT %(limit)s
            """,
            params,
        )
    raise AssertionError(path)


def same_vehicle_sparql(product_id: str, limit: int) -> str:
    if not product_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:_-." for character in product_id):
        raise DataApiError(422, "INVALID_ENTITY_ID", "Graph product_id에 허용되지 않은 문자가 있습니다")
    uri = f"http://mafest.ai/instance/{product_id}"
    return f"""
        PREFIX fp: <http://mafest.ai/product#>
        SELECT ?related WHERE {{
          GRAPH ?g {{
            {{ <{uri}> fp:sameVehicleAs ?related }}
            UNION {{ ?related fp:sameVehicleAs <{uri}> }}
          }}
        }} LIMIT {limit}
    """


RELATION_DOMAINS = {
    "issued_bond": {"BOND"},
    "holds_security": {"ETF_KR", "ETF_GL", "FUND_PUB"},
    "has_document": {"BOND", "ETF_KR", "ETF_GL", "ETN_KR", "ETN_GL", "FUND_PUB", "FUND_PRIVATE"},
    "same_vehicle_as": {"BOND", "ETF_KR", "ETF_GL", "ETN_KR", "ETN_GL", "FUND_PUB", "FUND_PRIVATE"},
}
RELATION_PREDICATES = {
    "issued_bond": "fp:issuedBy",
    "holds_security": "fp:hasHolding",
    "has_document": "fp:hasDocument",
    "same_vehicle_as": "fp:sameVehicleAs",
}


def validate_ontology_request(request: OntologyValidateRequest, product_type: str | None = None) -> dict[str, Any]:
    if request.validation_type == "credit_rating":
        if request.value is None:
            raise DataApiError(422, "MISSING_VALIDATION_VALUE", "credit_rating 검증에는 value가 필요합니다")
        value = request.value.strip().upper()
        rank = CREDIT_RATING_RANK.get(value)
        return {
            "valid": rank is not None,
            "code": "VALID" if rank is not None else "ABSTAIN_INVALID_TAXONOMY",
            "normalized_value": value,
            "rating_rank": rank,
            "evidence": {
                "source": "ontology/common.ttl",
                "predicate": "fp:ratingRank",
                "allowed_values": sorted(CREDIT_RATING_RANK, key=lambda item: CREDIT_RATING_RANK[item]),
            },
        }
    if request.validation_type == "cutoff":
        if request.requested_as_of is None:
            raise DataApiError(422, "MISSING_VALIDATION_VALUE", "cutoff 검증에는 requested_as_of가 필요합니다")
        valid = request.requested_as_of <= EXTERNAL_CUTOFF
        return {
            "valid": valid,
            "code": "VALID" if valid else "ABSTAIN_FUTURE_DATA",
            "requested_as_of": request.requested_as_of,
            "cutoff": EXTERNAL_CUTOFF,
            "evidence": {"source": "meta.dataset_snapshot.cutoff_date"},
        }
    if request.relation is None or request.subject_product_id is None:
        raise DataApiError(
            422,
            "MISSING_VALIDATION_VALUE",
            "relation_domain 검증에는 relation과 subject_product_id가 필요합니다",
        )
    allowed = RELATION_DOMAINS.get(request.relation)
    if allowed is None:
        raise DataApiError(422, "UNSUPPORTED_RELATION", "domain 검증을 지원하지 않는 관계입니다")
    if product_type is None:
        return {
            "valid": False,
            "code": "ABSTAIN_ENTITY_NOT_FOUND",
            "subject_product_id": request.subject_product_id,
        }
    valid = product_type in allowed
    return {
        "valid": valid,
        "code": "VALID" if valid else "ABSTAIN_DOMAIN_MISMATCH",
        "subject_product_id": request.subject_product_id,
        "subject_product_type": product_type,
        "relation": request.relation,
        "allowed_product_types": sorted(allowed),
        "evidence": {
            "source": "ontology/common.ttl",
            "predicate": RELATION_PREDICATES[request.relation],
        },
    }


def metric_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for prefix, code in (("aum", "AUM"), ("return_1y", "RETURN_1Y"), ("expense_ratio", "EXPENSE_RATIO")):
        value = row.get(prefix)
        if value is None:
            continue
        records.append(
            {
                "subject": row.get("product_id"),
                "metric_code": code,
                "value": value,
                "unit": row.get(f"{prefix}_unit"),
                "as_of": row.get(f"{prefix}_as_of"),
                "source": row.get(f"{prefix}_source"),
                "source_column": row.get(f"{prefix}_source_column"),
            }
        )
    if row.get("buy_yield") is not None:
        records.append(
            {
                "subject": row.get("product_id"),
                "metric_code": "BUY_YIELD",
                "value": row.get("buy_yield"),
                "unit": "percent",
                "as_of": row.get("buy_yield_as_of"),
                "source": "PRBD01N001",
                "source_column": row.get("buy_yield_source_column"),
            }
        )
    return records


def json_number(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def _capability(question_id: int, endpoints: list[str], status: str, gap: str | None = None) -> dict[str, Any]:
    return {"question_id": question_id, "endpoints": endpoints, "status": status, "known_gap": gap}


QUESTION_CAPABILITY_MAP = {
    **{question_id: _capability(question_id, ["/v1/products/search", "/v1/products/{product_id}"], "partial" if question_id in {1, 2, 4, 8, 9, 10} else "ready") for question_id in range(1, 11)},
    **{question_id: _capability(question_id, ["/v1/products/query", "/v1/products/compare"], "partial" if question_id in {14, 15, 19, 20} else "ready") for question_id in range(11, 21)},
    21: _capability(21, ["/v1/relations/traverse"], "partial", "sameVehicleAs ABox 실측 필요"),
    22: _capability(22, ["/v1/relations/traverse", "/v1/evidence/semantic-search"], "partial", "문서 인용 coverage"),
    23: _capability(23, ["/v1/relations/traverse", "/v1/evidence/semantic-search"], "gap", "6개월 사건·뉴스 이력 미수집"),
    24: _capability(24, ["/v1/relations/traverse", "/v1/products/query", "/v1/evidence/semantic-search"], "partial", "위험문서는 demo 1건"),
    25: _capability(25, ["/v1/evidence/semantic-search"], "partial", "정책문서는 demo 1건"),
    26: _capability(26, ["/v1/relations/traverse", "/v1/products/query"], "partial", "공모펀드 holdings 미수집"),
    27: _capability(27, ["/v1/relations/traverse", "/v1/evidence/semantic-search"], "partial", "배터리 위험문서 coverage"),
    28: _capability(28, ["/v1/relations/traverse", "/v1/products/query", "/v1/evidence/semantic-search"], "partial", "해외ETF holdings·유형별 위험문서 미수집"),
    29: _capability(29, ["/v1/products/compare", "/v1/evidence/semantic-search"], "gap", "해외ETF holdings 미수집"),
    30: _capability(30, ["/v1/relations/traverse", "/v1/evidence/semantic-search"], "gap", "공모펀드 holdings 미수집"),
    31: _capability(31, ["/v1/ontology/validate"], "ready"),
    32: _capability(32, ["/v1/ontology/validate", "/v1/products/search"], "partial", "모델 출시일 외부 근거 미수집"),
    33: _capability(33, ["/v1/products/search"], "ready"),
    34: _capability(34, ["/v1/ontology/validate"], "ready"),
    35: _capability(35, ["/v1/ontology/validate"], "ready"),
}

assert set(QUESTION_CAPABILITY_MAP) == set(range(1, 36))
