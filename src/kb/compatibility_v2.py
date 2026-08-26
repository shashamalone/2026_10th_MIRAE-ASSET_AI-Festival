# -*- coding: utf-8 -*-
"""평가 종료까지 유지하는 명시적 V1→V2 PostgreSQL 호환 뷰."""
from __future__ import annotations

from collections.abc import Iterable

try:
    from psycopg import sql
except ImportError:  # 정적 source/catalog check는 psycopg 없이도 동작한다.
    sql = None  # type: ignore[assignment]

from kb.catalog_v2 import STATIC_TABLES, ColumnDef
from kb.v2_manifest import SourceInspection


RAW_VIEW_NAMES = {
    "bond_kr_master": "prbd01n001",
    "etf_kr_master": "pref01n001",
    "etf_gl_master": "pref02n001",
    "fund_pub_master": "prfd01n001",
}


def _columns(schema_name: str, table_name: str) -> tuple[ColumnDef, ...]:
    for table in STATIC_TABLES:
        if table.schema == schema_name and table.name == table_name:
            return table.columns
    raise KeyError(f"catalog table missing: {schema_name}.{table_name}")


def _projection(columns: Iterable[ColumnDef | object]):
    if sql is None:
        raise RuntimeError("호환 뷰 생성에는 requirements.txt의 psycopg가 필요합니다")
    expressions = []
    for column in columns:
        name = str(getattr(column, "name"))
        data_type = str(getattr(column, "data_type"))
        expressions.append(
            sql.SQL("{}::{} AS {}").format(
                sql.Identifier(name), sql.SQL(data_type), sql.Identifier(name)
            )
        )
    return sql.SQL(", ").join(expressions)


def _replace_simple_view(
    conn,
    target_schema: str,
    target_name: str,
    source_schema: str,
    source_name: str,
    columns: Iterable[ColumnDef | object],
    where: str | None = None,
) -> None:
    statement = sql.SQL("CREATE OR REPLACE VIEW {}.{} AS SELECT {} FROM {}.{}").format(
        sql.Identifier(target_schema),
        sql.Identifier(target_name),
        _projection(columns),
        sql.Identifier(source_schema),
        sql.Identifier(source_name),
    )
    if where:
        statement += sql.SQL(" WHERE ") + sql.SQL(where)
    conn.execute(statement)


def create_compatibility_views(conn, inspections: tuple[SourceInspection, ...], schemas: dict[str, str]) -> None:
    """star projection 없이 컬럼 순서·타입을 고정한 호환 뷰를 생성한다."""
    for item in inspections:
        _replace_simple_view(
            conn,
            schemas["RAW"],
            RAW_VIEW_NAMES[item.spec.raw_table],
            schemas["RAW"],
            item.spec.raw_table,
            item.columns,
        )

    _replace_simple_view(
        conn,
        schemas["ENRICHED"],
        "fund_pub",
        schemas["ENRICHED"],
        "fund",
        _columns("enriched", "fund"),
        "offering_type = '공모'",
    )
    for view_name, source_name in (
        ("bond_kr", "bond_kr_product"),
        ("etf_kr", "etf_kr"),
        ("etf_gl", "etf_gl"),
    ):
        _replace_simple_view(
            conn,
            schemas["CORE"],
            view_name,
            schemas["ENRICHED"],
            source_name,
            _columns("enriched", source_name),
        )
    _replace_simple_view(
        conn,
        schemas["CORE"],
        "fund_pub",
        schemas["ENRICHED"],
        "fund_pub",
        _columns("enriched", "fund"),
    )

    conn.execute(
        sql.SQL(
            """
            CREATE OR REPLACE VIEW {}.etn AS
            SELECT product_id::text AS product_id, pd_itm_no::text AS pd_itm_no,
                   name::text AS name, ticker::text AS ticker, isin::text AS isin,
                   issuer::text AS issuer, currency::text AS currency,
                   listing_date::date AS listing_date, NULL::date AS inception_date,
                   delisting_date::date AS delisting_date,
                   effective_as_of::date AS effective_as_of, 'KR'::text AS market_scope
            FROM {}.etn_kr
            UNION ALL
            SELECT product_id::text, pd_itm_no::text, name::text, ticker::text,
                   isin::text, issuer::text, currency::text, NULL::date,
                   inception_date::date, NULL::date, effective_as_of::date, 'GL'::text
            FROM {}.etn_gl
            """
        ).format(
            sql.Identifier(schemas["CORE"]),
            sql.Identifier(schemas["ENRICHED"]),
            sql.Identifier(schemas["ENRICHED"]),
        )
    )

    _replace_simple_view(
        conn,
        schemas["RELATIONS"],
        "etf_holding",
        schemas["RELATIONS"],
        "product_holding",
        _columns("relations", "product_holding"),
    )
    _replace_simple_view(
        conn,
        schemas["RELATIONS"],
        "etf_theme",
        schemas["RELATIONS"],
        "product_classification",
        _columns("relations", "product_classification"),
        "classification_type = 'theme'",
    )
    _replace_simple_view(
        conn,
        schemas["VEC"],
        "doc_chunk",
        schemas["VEC"],
        "document_chunk",
        _columns("vec", "document_chunk"),
    )
    _replace_simple_view(
        conn,
        schemas["VEC"],
        "schema_index",
        schemas["VEC"],
        "schema_terms_all",
        _columns("vec", "schema_terms_all"),
    )
