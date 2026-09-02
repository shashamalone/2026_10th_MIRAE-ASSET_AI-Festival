# -*- coding: utf-8 -*-
"""PostgreSQL 11테이블에서 A 조건 Physical Schema Catalog를 추출한다."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))           # 런타임 모듈은 src/ 아래에 있다
from config import BOND_DSN  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "contexts/schema_only.json"
SCHEMAS = ("raw", "enriched", "relations")


def digest(data) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def collect(conn) -> list[dict]:
    columns = conn.execute("""
        SELECT table_schema,table_name,column_name,data_type,is_nullable,
               ordinal_position,column_default,is_identity
        FROM information_schema.columns
        WHERE table_schema = ANY(%s)
        ORDER BY table_schema,table_name,ordinal_position
    """, (list(SCHEMAS),)).fetchall()
    keys = conn.execute("""
        SELECT tc.table_schema,tc.table_name,tc.constraint_type,kcu.column_name,
               ccu.table_schema,ccu.table_name,ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON (tc.constraint_catalog,tc.constraint_schema,tc.constraint_name)=
             (kcu.constraint_catalog,kcu.constraint_schema,kcu.constraint_name)
        LEFT JOIN information_schema.constraint_column_usage ccu
          ON (tc.constraint_catalog,tc.constraint_schema,tc.constraint_name)=
             (ccu.constraint_catalog,ccu.constraint_schema,ccu.constraint_name)
        WHERE tc.table_schema = ANY(%s)
          AND tc.constraint_type IN ('PRIMARY KEY','FOREIGN KEY')
        ORDER BY tc.table_schema,tc.table_name,tc.constraint_name,kcu.ordinal_position
    """, (list(SCHEMAS),)).fetchall()
    by_col = {}
    for s, t, kind, col, rs, rt, rc in keys:
        item = by_col.setdefault((s, t, col), {"primary_key": False, "references": []})
        if kind == "PRIMARY KEY":
            item["primary_key"] = True
        else:
            item["references"].append(f"{rs}.{rt}.{rc}")
    tables = {}
    for s, t, col, typ, nullable, pos, default, identity in columns:
        key = by_col.get((s, t, col), {"primary_key": False, "references": []})
        tables.setdefault(f"{s}.{t}", []).append({
            "name": col, "datatype": typ, "nullable": nullable == "YES",
            "primary_key": key["primary_key"], "references": key["references"],
            "identity": identity == "YES", "ordinal": pos,
        })
    if len(tables) != 11:
        raise RuntimeError(f"11테이블이 아님: {len(tables)} {sorted(tables)}")
    return [{"table": name, "columns": cols} for name, cols in sorted(tables.items())]


def main() -> None:
    with psycopg.connect(BOND_DSN) as conn:
        tables = collect(conn)
        version = conn.execute("show server_version").fetchone()[0]
        counts = {}
        for t in tables:
            schema, table = t["table"].split(".")
            counts[t["table"]] = conn.execute(
                psycopg.sql.SQL("SELECT count(*) FROM {}.{}").format(
                    psycopg.sql.Identifier(schema), psycopg.sql.Identifier(table))).fetchone()[0]
    payload = {"condition": "A", "engine": "postgresql", "server_version": version,
               "data_cutoff": "2026-08-24", "tables": tables, "row_counts": counts}
    payload["catalog_sha256"] = digest(payload)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS {OUT.relative_to(ROOT)} — {len(tables)} tables sha={payload['catalog_sha256'][:12]}")


if __name__ == "__main__":
    main()
