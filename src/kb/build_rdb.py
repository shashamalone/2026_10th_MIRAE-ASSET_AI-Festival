# -*- coding: utf-8 -*-
"""11개 CSV를 Action 3용 PostgreSQL RDB로 적재한다.

    python3 src/kb/build_rdb.py          # 재적재 후 검증
    python3 src/kb/build_rdb.py --check  # 원천과 기존 DB를 읽기 전용 검증

원본 CSV는 읽기만 한다. 타입은 schema CSV 또는 아래 고정 manifest에서만 온다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BOND_DSN, ROOT  # noqa: E402


@dataclass(frozen=True)
class Table:
    schema: str
    name: str
    path: Path
    types: dict[str, str]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[tuple[str | tuple[str, ...], str, str | tuple[str, ...]], ...] = ()
    identity: str | None = None
    skip: dict[str, frozenset[str]] = field(default_factory=dict)

    @property
    def fq(self) -> str:
        return f"{self.schema}.{self.name}"


def read_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def raw_types(code: str) -> dict[str, str]:
    path = next((ROOT / "data/csv").glob(f"{code}_*_schema_20260824.csv"))
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["column"].lower(): r["dtype"] for r in csv.DictReader(f)}


def text_with(path: Path, **overrides: str) -> dict[str, str]:
    types = {c.lower(): "text" for c in read_header(path)}
    unknown = set(overrides) - set(types)
    if unknown:
        raise ValueError(f"{path.name}: 타입 override 컬럼 없음 {sorted(unknown)}")
    types.update(overrides)
    return types


CSV = ROOT / "data/csv"
ENRICHED = ROOT / "data/enriched"
RELATIONS = ROOT / "data/relations"

BOND = CSV / "PRBD01N001_bond_kr_master_20260824.csv"
ETF_KR = CSV / "PREF01N001_etf_kr_master_20260824.csv"
ETF_GL = CSV / "PREF02N001_etf_gl_master_20260824.csv"
FUND = CSV / "PRFD01N001_fund_pub_master_20260824.csv"
BOND_E = ENRICHED / "bond_kr_enriched.csv"
ETF_KR_E = ENRICHED / "etf_kr_enriched.csv"
COMPANY = ENRICHED / "company_master.csv"
CODE_MAP = ENRICHED / "holding_code_map.csv"
HOLDING = RELATIONS / "etf_holding.csv"
THEME = RELATIONS / "etf_theme.csv"
SUBSIDIARY = RELATIONS / "company_subsidiary.csv"

TABLES = (
    # pd_no는 08-24 배포본에서 2,463행 중복(장내/장외·정보차수) → 복합키만 유일하다
    Table("raw", "bond_kr_master", BOND, raw_types("PRBD01N001"),
          ("pd_no", "pd_exg_mkt", "info_seq")),
    Table("raw", "etf_kr_master", ETF_KR, raw_types("PREF01N001"), ("pd_itm_no",),
          skip={"pd_itm_no": frozenset({"KR"})}),
    Table("raw", "etf_gl_master", ETF_GL, raw_types("PREF02N001"), ("pd_itm_no",)),
    # 08-24 배포본은 itm_no 단독 유일(속성코드는 prfd_attr_cds로 집약), 깨진 행 0건
    Table("raw", "fund_pub_master", FUND, raw_types("PRFD01N001"), ("itm_no",)),
    Table("enriched", "bond_kr_enriched", BOND_E, text_with(
        BOND_E, info_seq="bigint", crd_grd_rank="integer",
        remaining_days="integer", is_krw="boolean", has_sale_info="boolean",
        is_sellable="boolean"), ("pd_no", "pd_exg_mkt", "info_seq"),
        ((("pd_no", "pd_exg_mkt", "info_seq"), "raw.bond_kr_master",
          ("pd_no", "pd_exg_mkt", "info_seq")),)),
    Table("enriched", "etf_kr_enriched", ETF_KR_E, text_with(
        ETF_KR_E, ter="numeric", charge_rt_final="numeric"), ("pd_itm_no",),
        (("pd_itm_no", "raw.etf_kr_master", "pd_itm_no"),),
        skip={"pd_itm_no": frozenset({"KR"})}),
    Table("enriched", "company_master", COMPANY, text_with(COMPANY), ("corp_code",)),
    Table("enriched", "holding_code_map", CODE_MAP, text_with(CODE_MAP),
          ("holding_code_raw",),
          (("corp_code", "enriched.company_master", "corp_code"),
           ("etf_isin", "raw.etf_kr_master", "pd_itm_no"))),
    Table("relations", "etf_theme", THEME, text_with(THEME, as_of="date"),
          ("pd_itm_no", "theme"),
          (("pd_itm_no", "raw.etf_kr_master", "pd_itm_no"),)),
    Table("relations", "etf_holding", HOLDING, text_with(
        HOLDING, weight="numeric", as_of="date"), ("holding_id",),
        (("pd_itm_no", "raw.etf_kr_master", "pd_itm_no"),), "holding_id"),
    Table("relations", "company_subsidiary", SUBSIDIARY, text_with(
        SUBSIDIARY, ownership_pct="numeric", as_of="date"), ("relation_id",),
        (("parent_corp_code", "enriched.company_master", "corp_code"),
         ("child_corp_code", "enriched.company_master", "corp_code")), "relation_id"),
)
LEGACY_TABLES = ("enriched.fund_pub_dedup",)


def qname(fq: str) -> sql.Composed:
    a, b = fq.split(".")
    return sql.SQL("{}.{}").format(sql.Identifier(a), sql.Identifier(b))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows(table: Table):
    with table.path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        actual = [c.lower() for c in (reader.fieldnames or [])]
        if actual != list(table.types):
            raise ValueError(f"{table.path.name}: header/type manifest 불일치")
        for line, raw in enumerate(reader, 2):
            row = {k.lower(): v for k, v in raw.items()}
            if any(row.get(k) in vals for k, vals in table.skip.items()):
                yield line, None
            else:
                yield line, tuple(None if row[c] == "" else row[c] for c in table.types)


def validate_sources() -> dict[str, tuple[int, int]]:
    result = {}
    for table in TABLES:
        total = skipped = 0
        seen = set()
        key_ix = [list(table.types).index(k) for k in table.primary_key if k != table.identity]
        for line, row in rows(table):
            total += 1
            if row is None:
                skipped += 1
                continue
            if key_ix and table.identity is None:
                key = tuple(row[i] for i in key_ix)
                if None in key or key in seen:
                    raise ValueError(f"{table.fq}:{line} PK 오류 {key!r}")
                seen.add(key)
        result[table.fq] = (total - skipped, skipped)
        print(f"  {table.fq:39s} rows={total-skipped:,} skip={skipped} sha={sha256(table.path)[:12]}")
    return result


def create_table(conn: psycopg.Connection, table: Table) -> None:
    defs = []
    if table.identity:
        defs.append(sql.SQL("{} bigint GENERATED ALWAYS AS IDENTITY").format(
            sql.Identifier(table.identity)))
    defs += [sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(t))
             for c, t in table.types.items()]
    defs.append(sql.SQL("PRIMARY KEY ({})").format(
        sql.SQL(", ").join(map(sql.Identifier, table.primary_key))))
    for cols, ref_table, ref_cols in table.foreign_keys:
        cols = (cols,) if isinstance(cols, str) else cols
        ref_cols = (ref_cols,) if isinstance(ref_cols, str) else ref_cols
        defs.append(sql.SQL("FOREIGN KEY ({}) REFERENCES {} ({})").format(
            sql.SQL(", ").join(map(sql.Identifier, cols)), qname(ref_table),
            sql.SQL(", ").join(map(sql.Identifier, ref_cols))))
    conn.execute(sql.SQL("CREATE TABLE {} ({})").format(
        qname(table.fq), sql.SQL(", ").join(defs)))


def load(conn: psycopg.Connection, table: Table) -> int:
    cols = list(table.types)
    query = sql.SQL("COPY {} ({}) FROM STDIN").format(
        qname(table.fq), sql.SQL(", ").join(map(sql.Identifier, cols)))
    count = 0
    with conn.cursor().copy(query) as copy:
        for _, row in rows(table):
            if row is not None:
                copy.write_row(row)
                count += 1
    return count


def rebuild(expected: dict[str, tuple[int, int]]) -> None:
    with psycopg.connect(BOND_DSN) as conn:
        for schema in ("raw", "enriched", "relations"):
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        for table in reversed(TABLES):
            conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(qname(table.fq)))
        for table in LEGACY_TABLES:
            conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(qname(table)))
        for table in TABLES:
            create_table(conn, table)
            actual = load(conn, table)
            if actual != expected[table.fq][0]:
                raise RuntimeError(f"{table.fq}: 적재 {actual} != 기대 {expected[table.fq][0]}")
            print(f"  loaded {table.fq:32s} {actual:,}")


def validate_db(expected: dict[str, tuple[int, int]]) -> None:
    with psycopg.connect(BOND_DSN) as conn:
        actual_tables = {".".join(row) for row in conn.execute("""
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_schema IN ('raw','enriched','relations')
              AND table_type = 'BASE TABLE'
        """).fetchall()}
        expected_tables = {table.fq for table in TABLES}
        if actual_tables != expected_tables:
            raise RuntimeError(f"DB table 집합 불일치: {sorted(actual_tables ^ expected_tables)}")
        for table in TABLES:
            n = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(qname(table.fq))).fetchone()[0]
            if n != expected[table.fq][0]:
                raise RuntimeError(f"{table.fq}: DB {n} != 원천 {expected[table.fq][0]}")
        cutoff_bad = conn.execute("""
            SELECT count(*) FROM (
              SELECT as_of FROM relations.etf_theme
              UNION ALL SELECT as_of FROM relations.etf_holding
              UNION ALL SELECT as_of FROM relations.company_subsidiary
            ) x WHERE as_of > DATE '2026-08-24'
        """).fetchone()[0]
        if cutoff_bad:
            raise RuntimeError(f"as_of cutoff 초과 {cutoff_bad}행")
        constraints = conn.execute("""
            SELECT count(*) FROM information_schema.table_constraints
            WHERE table_schema IN ('raw','enriched','relations')
              AND constraint_type IN ('PRIMARY KEY','FOREIGN KEY')
        """).fetchone()[0]
        want = len(TABLES) + sum(len(t.foreign_keys) for t in TABLES)
        if constraints < want:
            raise RuntimeError(f"PK/FK 제약 부족: {constraints} < {want}")
    print(f"PASS DB 검증 — {len(TABLES)} tables, PK/FK {constraints}, cutoff 위반 0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    print("원천 검증")
    expected = validate_sources()
    if not args.check:
        print("PostgreSQL 적재")
        rebuild(expected)
    print("PostgreSQL 검증")
    validate_db(expected)


if __name__ == "__main__":
    main()
