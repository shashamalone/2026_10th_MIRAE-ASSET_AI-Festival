# -*- coding: utf-8 -*-
"""PostgreSQL 17의 ``*_next``에 금융상품 데이터 플랫폼 v2를 적재한다.

기본 실행은 stage 스키마만 재생성하며 정식 스키마는 건드리지 않는다. ``--check``는
원천과 생성 문서를 읽기만 하고 파일/DB를 변경하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
except ImportError:  # --check는 PostgreSQL 드라이버 없이도 순수 읽기 검증 가능
    psycopg = None  # type: ignore[assignment]
    sql = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.build_catalog_v2 import build_outputs, write_or_check  # noqa: E402
from kb.catalog_v2 import build_catalog  # noqa: E402
from kb.v2_manifest import (  # noqa: E402
    DATASET_VERSION,
    EXTERNAL_CUTOFF,
    RELEASE_DATE,
    ROOT,
    SourceInspection,
    exclusion_reason,
    iter_data_rows,
    snapshot_hash,
    validate_source_dir,
)

SCHEMAS = {
    "META": "meta_next",
    "RAW": "raw_next",
    "ENRICHED": "enriched_next",
    "RELATIONS": "relations_next",
    "VEC": "vec_next",
    "CORE": "core_next",
}
SQL_DIR = ROOT / "sql" / "v2"


def execute_many(conn: psycopg.Connection, statement: str, rows) -> None:
    """psycopg 3의 Cursor.executemany를 한곳에서 사용한다."""
    with conn.cursor() as cursor:
        cursor.executemany(statement, rows)


def dsn() -> str:
    if value := os.environ.get("DATABASE_URL"):
        return value
    if not os.environ.get("PGDATABASE"):
        raise RuntimeError(
            "DATABASE_URL 또는 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE를 환경변수로 제공하세요"
        )
    keys = ("host", "port", "user", "password", "dbname")
    env = {
        "host": os.environ.get("PGHOST", "127.0.0.1"),
        "port": os.environ.get("PGPORT", "5432"),
        "user": os.environ.get("PGUSER", "agent_admin"),
        "password": os.environ.get("PGPASSWORD", ""),
        "dbname": os.environ["PGDATABASE"],
    }
    return " ".join(f"{key}={env[key]}" for key in keys)


def render_sql(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    for token, schema in SCHEMAS.items():
        content = content.replace(f"__{token}__", schema)
    content = content.replace("__CUTOFF_DATE__", EXTERNAL_CUTOFF.isoformat())
    content = content.replace("__RELEASE_DATE__", RELEASE_DATE.isoformat())
    content = content.replace("__DATASET_VERSION__", DATASET_VERSION)
    leftovers = [token for token in ("META", "RAW", "ENRICHED", "RELATIONS", "VEC", "CORE") if f"__{token}__" in content]
    if leftovers:
        raise ValueError(f"{path}: 치환되지 않은 토큰 {leftovers}")
    return content


def recreate_stage_schemas(conn: psycopg.Connection) -> None:
    # 정확히 고정된 *_next만 대상으로 한다. 정식·*_prev 스키마는 절대 삭제하지 않는다.
    for schema_name in SCHEMAS.values():
        conn.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
        )
    conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(SCHEMAS["RAW"])))


def create_raw_table(conn: psycopg.Connection, item: SourceInspection) -> None:
    primary_key = set(item.spec.primary_key)
    definitions = [
        sql.SQL("{} {}{}").format(
            sql.Identifier(column.name),
            sql.SQL(column.data_type),
            sql.SQL(" NOT NULL")
            if column.name in primary_key
            or (not column.nullable and item.null_counts[column.ordinal - 1] == 0)
            else sql.SQL(""),
        )
        for column in item.columns
    ]
    definitions.append(
        sql.SQL("PRIMARY KEY ({})").format(
            sql.SQL(", ").join(sql.Identifier(name) for name in item.spec.primary_key)
        )
    )
    conn.execute(
        sql.SQL("CREATE TABLE {}.{} ({})").format(
            sql.Identifier(SCHEMAS["RAW"]),
            sql.Identifier(item.spec.raw_table),
            sql.SQL(", ").join(definitions),
        )
    )


def load_raw_table(conn: psycopg.Connection, item: SourceInspection) -> int:
    names = [column.name for column in item.columns]
    statement = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(SCHEMAS["RAW"]),
        sql.Identifier(item.spec.raw_table),
        sql.SQL(", ").join(sql.Identifier(name) for name in names),
    )
    count = 0
    with conn.cursor().copy(statement) as copy:
        for row in iter_data_rows(item.data_path, item.columns):
            if exclusion_reason(item.spec, row, names):
                continue
            copy.write_row(row)
            count += 1
    expected = item.row_count - item.excluded_rows
    if count != expected:
        raise RuntimeError(f"{item.spec.code}: COPY {count:,} != 적재 대상 {expected:,}")
    return count


def insert_catalog(conn: psycopg.Connection, inspections) -> int:
    rows = []
    for table in build_catalog(inspections):
        for ordinal, column in enumerate(table.columns, 1):
            rows.append(
                (
                    table.schema,
                    table.name,
                    ordinal,
                    column.name,
                    column.data_type,
                    column.nullable,
                    column.description,
                    column.unit,
                    column.as_of_column,
                    column.zero_null_rule,
                    column.source_priority,
                    column.transform_expression,
                    table.implementation_status,
                    table.deployment_status,
                    column.pk_ordinal,
                    column.fk_target,
                    table.grain,
                )
            )
    execute_many(
        conn,
        f"""
        INSERT INTO {SCHEMAS['META']}.column_catalog (
          table_schema,table_name,ordinal_position,column_name,data_type,is_nullable,
          description,unit,as_of_column,zero_null_rule,source_priority,transform_expression,
          implementation_status,deployment_status,pk_ordinal,fk_target,grain
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        rows,
    )
    return len(rows)


def validate_stage(conn: psycopg.Connection, inspections) -> dict[str, object]:
    expected_raw = {
        item.spec.raw_table: item.row_count - item.excluded_rows for item in inspections
    }
    actual_raw = {}
    for table, expected in expected_raw.items():
        actual = conn.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(SCHEMAS["RAW"]), sql.Identifier(table)
            )
        ).fetchone()[0]
        if actual != expected:
            raise RuntimeError(f"raw.{table}: DB {actual:,} != 원천 {expected:,}")
        actual_raw[table] = actual

    product_counts = dict(
        conn.execute(
            f"SELECT product_type, count(*) FROM {SCHEMAS['ENRICHED']}.product_master GROUP BY 1"
        ).fetchall()
    )
    expected_product_counts = {
        "BOND": conn.execute(
            f"SELECT count(DISTINCT pd_no) FROM {SCHEMAS['RAW']}.bond_kr_master"
        ).fetchone()[0],
        "ETF_KR": conn.execute(
            f"SELECT count(*) FROM {SCHEMAS['RAW']}.etf_kr_master WHERE btrim(pd_grp_no)='ETF'"
        ).fetchone()[0],
        "ETN_KR": conn.execute(
            f"SELECT count(*) FROM {SCHEMAS['RAW']}.etf_kr_master WHERE btrim(pd_grp_no)='ETN'"
        ).fetchone()[0],
        "ETF_GL": conn.execute(
            f"SELECT count(*) FROM {SCHEMAS['RAW']}.etf_gl_master WHERE btrim(pd_grp_no)='ETF'"
        ).fetchone()[0],
        "ETN_GL": conn.execute(
            f"SELECT count(*) FROM {SCHEMAS['RAW']}.etf_gl_master WHERE btrim(pd_grp_no)='ETN'"
        ).fetchone()[0],
        "FUND_PUB": conn.execute(
            f"SELECT count(DISTINCT itm_no) FROM {SCHEMAS['RAW']}.fund_pub_master WHERE btrim(prvo_pbff_desc)='공모'"
        ).fetchone()[0],
        "FUND_PRIVATE": conn.execute(
            f"SELECT count(DISTINCT itm_no) FROM {SCHEMAS['RAW']}.fund_pub_master WHERE btrim(prvo_pbff_desc)='사모'"
        ).fetchone()[0],
    }
    expected_product_counts = {
        product_type: count for product_type, count in expected_product_counts.items() if count
    }
    if product_counts != expected_product_counts:
        raise RuntimeError(
            f"상품유형 행 수 불일치 actual={product_counts} expected={expected_product_counts}"
        )

    metric_zero_bad = conn.execute(
        f"SELECT count(*) FROM {SCHEMAS['ENRICHED']}.product_metric "
        "WHERE is_available AND (value IS NULL OR value = 0)"
    ).fetchone()[0]
    coverage_count = conn.execute(
        f"SELECT count(*) FROM {SCHEMAS['META']}.product_coverage"
    ).fetchone()[0]
    product_count = sum(product_counts.values())
    if metric_zero_bad:
        raise RuntimeError(f"0/NULL인데 사용 가능인 지표 {metric_zero_bad}행")
    if coverage_count != product_count:
        raise RuntimeError(f"coverage {coverage_count:,} != product {product_count:,}")

    purchasability_bad = conn.execute(
        f"""
        SELECT count(*) FROM {SCHEMAS['ENRICHED']}.bond_kr_product
        WHERE is_assumed_purchasable IS DISTINCT FROM
              (maturity_date IS NULL OR maturity_date > %s)
        """
        , (EXTERNAL_CUTOFF,)
    ).fetchone()[0]
    if purchasability_bad:
        raise RuntimeError(f"채권 구매가능 가정 규칙 위반 {purchasability_bad}행")

    cutoff_bad = conn.execute(
        f"""
        SELECT count(*) FROM (
          SELECT published_at d FROM {SCHEMAS['RELATIONS']}.source_document
          UNION ALL SELECT as_of FROM {SCHEMAS['RELATIONS']}.source_document
          UNION ALL SELECT as_of FROM {SCHEMAS['RELATIONS']}.product_holding
          UNION ALL SELECT as_of FROM {SCHEMAS['RELATIONS']}.product_classification
          UNION ALL SELECT as_of FROM {SCHEMAS['RELATIONS']}.company_subsidiary
          UNION ALL SELECT as_of FROM {SCHEMAS['ENRICHED']}.product_metric
          UNION ALL SELECT published_at FROM {SCHEMAS['VEC']}.document_chunk
        ) dates WHERE d > %s
        """
        , (EXTERNAL_CUTOFF,)
    ).fetchone()[0]

    metric_date_bad = conn.execute(
        f"""
        SELECT count(*) FROM {SCHEMAS['ENRICHED']}.product_metric
        WHERE is_available AND (as_of IS NULL OR as_of > %s)
        """,
        (EXTERNAL_CUTOFF,),
    ).fetchone()[0]
    metric_axis_bad = conn.execute(
        f"""
        SELECT count(*) FROM (
          SELECT m.metric_id
          FROM {SCHEMAS['ENRICHED']}.product_metric m
          JOIN {SCHEMAS['RAW']}.etf_kr_master r
            ON m.product_id = 'etf_kr:' || btrim(r.pd_itm_no)
          WHERE m.source='PREF01N001' AND (
            (m.metric_code='AUM' AND
              (m.source_column <> 'du_last_aum' OR
               m.as_of IS DISTINCT FROM {SCHEMAS['META']}.yyyymmdd(r.du_upt_dt)))
            OR (m.metric_code='RETURN_1Y' AND
              (m.source_column <> 'du_er_1y' OR
               m.as_of IS DISTINCT FROM {SCHEMAS['META']}.yyyymmdd(r.du_upt_dt)))
            OR (m.metric_code='EXPENSE_RATIO' AND
              (m.source_column <> 'cu_charge_rt' OR
               m.as_of IS DISTINCT FROM {SCHEMAS['META']}.yyyymmdd(r.cu_upt_dt)))
          )
          UNION ALL
          SELECT m.metric_id
          FROM {SCHEMAS['ENRICHED']}.product_metric m
          JOIN {SCHEMAS['RAW']}.etf_gl_master r
            ON m.product_id = 'etf_gl:' || btrim(r.pd_itm_no)
          WHERE m.source='PREF02N001' AND (
            (m.metric_code='AUM' AND
              (m.source_column <> 'du_last_aum' OR
               m.as_of IS DISTINCT FROM {SCHEMAS['META']}.yyyymmdd(r.du_upt_dt)))
            OR (m.metric_code='EXPENSE_RATIO' AND
              (m.source_column <> 'cu_charge_rt' OR
               m.as_of IS DISTINCT FROM {SCHEMAS['META']}.yyyymmdd(r.cu_upt_dt)))
          )
          UNION ALL
          SELECT m.metric_id
          FROM {SCHEMAS['ENRICHED']}.product_metric m
          JOIN {SCHEMAS['RAW']}.fund_pub_master r
            ON m.product_id = 'fund:' || btrim(r.itm_no)
          WHERE m.source='PRFD01N001' AND (
            (m.metric_code='AUM' AND
              (m.source_column <> 'fd_nast_suma' OR
               m.as_of IS DISTINCT FROM {SCHEMAS['META']}.yyyymmdd(r.fd_daily_bas_dt)))
            OR (m.metric_code='RETURN_1Y' AND
              (m.source_column <> 'fd_yr1_ern_r' OR
               m.as_of IS DISTINCT FROM {SCHEMAS['META']}.yyyymmdd(r.fd_price_bas_dt)))
            OR (m.metric_code='EXPENSE_RATIO' AND
              (m.source_column <> 'ofwk_trus_rwrd_r+or_co_rwrd_r+sale_co_rwrd_r+trusc_rwrd_r'
               OR m.as_of IS DISTINCT FROM {SCHEMAS['META']}.yyyymmdd(r.fd_price_bas_dt)))
          )
        ) invalid_metric_axis
        """
    ).fetchone()[0]
    if metric_date_bad or metric_axis_bad:
        raise RuntimeError(
            f"지표 기준일/출처축 위반 date={metric_date_bad}, axis={metric_axis_bad}"
        )
    if cutoff_bad:
        raise RuntimeError(f"외부 cutoff 초과 {cutoff_bad}행")

    return {
        "raw_rows": actual_raw,
        "product_counts": product_counts,
        "product_count": product_count,
        "coverage_count": coverage_count,
        "available_metric_zero_or_null": metric_zero_bad,
        "purchasability_rule_mismatch": purchasability_bad,
        "external_cutoff_violations": cutoff_bad,
        "metric_date_violations": metric_date_bad,
        "metric_axis_violations": metric_axis_bad,
    }


def build(data_dir: str | Path | None = None) -> dict[str, object]:
    if psycopg is None:
        raise RuntimeError("실제 적재에는 requirements.txt의 psycopg가 필요합니다")
    inspections = validate_source_dir(data_dir)
    manifest_sha = snapshot_hash(inspections)
    snapshot_id = uuid.uuid5(uuid.NAMESPACE_URL, f"mafest:{manifest_sha}")
    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    loaded_rows: dict[str, int] = {}

    with psycopg.connect(dsn()) as conn:
        recreate_stage_schemas(conn)
        for item in inspections:
            create_raw_table(conn, item)
            loaded_rows[f"raw.{item.spec.raw_table}"] = load_raw_table(conn, item)

        conn.execute(render_sql(SQL_DIR / "001_platform_schema.sql"))
        source_files = [item.as_dict() for item in inspections]
        domain_as_of = {
            item.spec.code: item.effective_as_of.isoformat() if item.effective_as_of else None
            for item in inspections
        }
        conn.execute(
            f"""
            INSERT INTO {SCHEMAS['META']}.dataset_snapshot
              (snapshot_id,dataset_version,release_date,cutoff_date,domain_as_of,source_files,source_hash)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
            """,
            (
                snapshot_id,
                DATASET_VERSION,
                RELEASE_DATE,
                EXTERNAL_CUTOFF,
                json.dumps(domain_as_of),
                json.dumps(source_files, ensure_ascii=False),
                manifest_sha,
            ),
        )
        conn.execute(
            f"""
            INSERT INTO {SCHEMAS['META']}.load_run
              (run_id,snapshot_id,started_at,status,phase,source_rows,loaded_rows,validation_result)
            VALUES (%s,%s,%s,'running','raw_loaded',%s::jsonb,%s::jsonb,'{{}}'::jsonb)
            """,
            (
                run_id,
                snapshot_id,
                started_at,
                json.dumps(
                    {
                        item.spec.code: {
                            "source": item.row_count,
                            "loaded": item.row_count - item.excluded_rows,
                            "excluded": item.excluded_rows,
                        }
                        for item in inspections
                    }
                ),
                json.dumps(loaded_rows),
            ),
        )
        loaded_rows["meta.column_catalog"] = insert_catalog(conn, inspections)
        conn.execute(render_sql(SQL_DIR / "010_enrich.sql"))
        validation = validate_stage(conn, inspections)
        conn.execute(
            f"""
            UPDATE {SCHEMAS['META']}.load_run
            SET finished_at=clock_timestamp(), status='passed', phase='rdb_validated',
                loaded_rows=%s::jsonb, validation_result=%s::jsonb
            WHERE run_id=%s
            """,
            (json.dumps(loaded_rows), json.dumps(validation), run_id),
        )

    return {
        "snapshot_id": str(snapshot_id),
        "run_id": str(run_id),
        "snapshot_hash": manifest_sha,
        "schemas": SCHEMAS,
        "loaded_rows": loaded_rows,
        "validation": validation,
    }


def read_only_check(data_dir: str | Path | None = None) -> dict[str, object]:
    inspections = validate_source_dir(data_dir)
    # 생성 결과를 메모리에서 만들고 현재 커밋 산출물과 비교만 한다.
    write_or_check(build_outputs(data_dir), check=True)
    return {
        "mode": "check",
        "mutated_files": False,
        "mutated_database": False,
        "snapshot_hash": snapshot_hash(inspections),
        "sources": [item.as_dict() for item in inspections],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="금융상품 데이터 플랫폼 v2 stage 빌더")
    parser.add_argument("--data-dir", help="2026-08-24 주최측 정본 XLSX 8개 디렉터리")
    parser.add_argument(
        "--check", action="store_true", help="파일·DB를 변경하지 않고 원천/카탈로그만 검증"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = read_only_check(args.data_dir) if args.check else build(args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
