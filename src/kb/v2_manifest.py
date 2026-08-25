# -*- coding: utf-8 -*-
"""2026-07-11 주최측 CSV 정본의 선언과 읽기 전용 검증.

원본은 수정하지 않는다. ``--check`` 빌더와 실제 적재기가 이 모듈을 함께 사용해
행 수, 헤더, 타입, PK 규칙이 서로 달라지는 것을 막는다.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[2]
DATASET_VERSION = "financial-products-2026-07-11"
RELEASE_DATE = date(2026, 7, 11)
EXTERNAL_CUTOFF = RELEASE_DATE
DEFAULT_DATASET_DIR = ROOT.parent / "data" / "data" / "csv"
CONVERSION_MANIFEST = "_conversion_manifest.json"

SCHEMA_HEADER = ("column", "pk_fk", "dtype", "name_ko", "example")
TYPE_PATTERN = re.compile(
    r"^(?:text|bigint|double precision|numeric(?:\(\d{1,2},\d{1,2}\))?|timestamp without time zone)$",
    re.IGNORECASE,
)


class LookAheadError(ValueError):
    """평가 cutoff 뒤의 스냅샷이나 관측값이 정본에 섞였을 때 발생한다."""


@dataclass(frozen=True)
class SourceSpec:
    code: str
    raw_table: str
    data_file: str
    schema_file: str
    expected_rows: int
    expected_columns: int
    primary_key: tuple[str, ...]
    effective_as_of_columns: tuple[str, ...]
    grain: str


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "PRBD01N001",
        "bond_kr_master",
        "PRBD01N001_bond_kr_master_20260711.csv",
        "PRBD01N001_bond_kr_schema_20260711.csv",
        42_394,
        40,
        ("pd_no",),
        ("pd_std_info_update",),
        "국내 채권 상품",
    ),
    SourceSpec(
        "PREF01N001",
        "etf_kr_master",
        "PREF01N001_etf_kr_master_20260711.csv",
        "PREF01N001_etf_kr_schema_20260711.csv",
        1_734,
        73,
        ("pd_itm_no",),
        ("cu_upt_dt", "du_upt_dt", "wu_upt_dt"),
        "국내 ETF/ETN 상품",
    ),
    SourceSpec(
        "PREF02N001",
        "etf_gl_master",
        "PREF02N001_etf_gl_master_20260711.csv",
        "PREF02N001_etf_gl_schema_20260711.csv",
        5_646,
        49,
        ("pd_itm_no",),
        ("cu_upt_dt", "du_upt_dt", "wu_upt_dt", "du_clpr_base_dt", "du_nav_base_dt"),
        "해외 ETF/ETN 상품",
    ),
    SourceSpec(
        "PRFD01N001",
        "fund_pub_master",
        "PRFD01N001_fund_pub_master_20260711.csv",
        "PRFD01N001_fund_pub_schema_20260711.csv",
        95_619,
        45,
        ("itm_no", "prfd_attr_cd"),
        (),
        "공모펀드 클래스 속성",
    ),
)


@dataclass(frozen=True)
class OfficialColumn:
    ordinal: int
    name: str
    data_type: str
    nullable: bool
    description: str


@dataclass(frozen=True)
class SourceInspection:
    spec: SourceSpec
    data_path: Path
    schema_path: Path
    columns: tuple[OfficialColumn, ...]
    null_counts: tuple[int, ...]
    row_count: int
    excluded_rows: int
    effective_as_of: date | None
    data_sha256: str
    schema_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.spec.code,
            "raw_table": f"raw.{self.spec.raw_table}",
            "data_file": self.data_path.name,
            "schema_file": self.schema_path.name,
            "rows": self.row_count,
            "loaded_rows": self.row_count - self.excluded_rows,
            "excluded_rows": self.excluded_rows,
            "columns": len(self.columns),
            "primary_key": list(self.spec.primary_key),
            "official_nullable_conflicts": {
                column.name: self.null_counts[column.ordinal - 1]
                for column in self.columns
                if not column.nullable and self.null_counts[column.ordinal - 1] > 0
            },
            "effective_as_of": self.effective_as_of.isoformat()
            if self.effective_as_of
            else None,
            "data_sha256": self.data_sha256,
            "schema_sha256": self.schema_sha256,
        }


def dataset_dir(value: str | Path | None = None) -> Path:
    """명시 인자 → 환경변수 → 로컬 공유 폴더 순으로 원천 위치를 정한다."""
    if value:
        return Path(value).expanduser().resolve()
    configured = os.environ.get("DATASET_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DATASET_DIR.resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_key_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_raw_value(value: object, data_type: str) -> object | None:
    """빈 값만 NULL로 바꾸고 0과 코드 원문은 보존한다."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    if isinstance(value, (date, datetime)):
        return value
    # PostgreSQL COPY가 공식 타입에 맞춰 변환하므로 임의 반올림이나
    # 0→NULL 처리를 하지 않는다.
    return value


def read_official_schema(path: Path, primary_key: tuple[str, ...] = ()) -> tuple[OfficialColumn, ...]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle)
        header = tuple(normalized_key_value(value) for value in next(rows))
        if header != SCHEMA_HEADER:
            raise ValueError(f"{path.name}: 공식 스키마 헤더 불일치 {header!r}")
        columns: list[OfficialColumn] = []
        for csv_row, row in enumerate(rows, start=2):
            if not any(normalized_key_value(value) for value in row):
                continue
            if len(row) != len(SCHEMA_HEADER):
                raise ValueError(f"{path.name}:{csv_row}: 스키마 행 폭 불일치")
            name = normalized_key_value(row[0])
            data_type = normalized_key_value(row[2])
            description = normalized_key_value(row[3]) or ""
            if not name or not data_type:
                raise ValueError(f"{path.name}:{csv_row}: 불완전한 스키마 행")
            if not TYPE_PATTERN.fullmatch(data_type):
                raise ValueError(f"{path.name}:{csv_row}: 허용하지 않은 타입 {data_type!r}")
            normalized_name = name.lower()
            columns.append(
                OfficialColumn(
                    ordinal=len(columns) + 1,
                    name=normalized_name,
                    data_type=data_type.lower(),
                    nullable=normalized_name not in primary_key,
                    description=description,
                )
            )
    names = [column.name for column in columns]
    if len(names) != len(set(names)):
        raise ValueError(f"{path.name}: 중복 컬럼명")
    return tuple(columns)


def iter_data_rows(
    path: Path, columns: tuple[OfficialColumn, ...]
) -> Iterator[tuple[object | None, ...]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle)
        header = tuple(normalized_key_value(value) for value in next(rows))
        expected = tuple(column.name for column in columns)
        if tuple(value.lower() if value else value for value in header) != expected:
            raise ValueError(f"{path.name}: data/schema 컬럼 1:1 불일치")
        for row in rows:
            if len(row) != len(columns):
                raise ValueError(f"{path.name}: 행 폭 {len(row)} != {len(columns)}")
            yield tuple(
                normalize_raw_value(value, column.data_type)
                for value, column in zip(row, columns)
            )


def parse_source_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = normalized_key_value(value)
    if not text:
        return None
    text = re.sub(r"\.0+$", "", text)
    for candidate, format_string in ((text[:10], "%Y-%m-%d"), (text, "%Y%m%d")):
        try:
            return datetime.strptime(candidate, format_string).date()
        except ValueError:
            continue
    return None


def exclusion_reason(spec: SourceSpec, row: tuple[object | None, ...], names: list[str]) -> str | None:
    if spec.code == "PRFD01N001" and normalized_key_value(row[names.index("itm_no")]) == '"':
        return "KNOWN_BROKEN_FUND_ROW"
    return None


def inspect_source(root: Path, spec: SourceSpec) -> SourceInspection:
    data_path = root / spec.data_file
    schema_path = root / spec.schema_file
    columns = read_official_schema(schema_path, spec.primary_key)
    if len(columns) != spec.expected_columns:
        raise ValueError(
            f"{spec.code}: 스키마 {len(columns)}열 != 기대 {spec.expected_columns}열"
        )
    names = [column.name for column in columns]
    missing_pk = set(spec.primary_key) - set(names)
    if missing_pk:
        raise ValueError(f"{spec.code}: PK 컬럼 누락 {sorted(missing_pk)}")

    key_indexes = [names.index(name) for name in spec.primary_key]
    date_indexes = [names.index(name) for name in spec.effective_as_of_columns]
    seen: set[tuple[str, ...]] = set()
    maximum_as_of: date | None = None
    row_count = 0
    excluded_rows = 0
    null_counts = [0] * len(columns)
    for excel_row, row in enumerate(iter_data_rows(data_path, columns), start=2):
        row_count += 1
        reason = exclusion_reason(spec, row, names)
        if reason:
            excluded_rows += 1
            continue
        for index, value in enumerate(row):
            if value is None:
                null_counts[index] += 1
        key = tuple(normalized_key_value(row[index]) for index in key_indexes)
        if any(value is None for value in key):
            raise ValueError(f"{spec.code}:{excel_row}: PK NULL {key!r}")
        typed_key = tuple(value for value in key if value is not None)
        if typed_key in seen:
            raise ValueError(f"{spec.code}:{excel_row}: PK 중복 {typed_key!r}")
        seen.add(typed_key)
        for index in date_indexes:
            candidate = parse_source_date(row[index])
            if candidate and candidate > EXTERNAL_CUTOFF:
                raise LookAheadError(
                    f"{spec.code}:{excel_row}: {names[index]}={candidate}가 cutoff {EXTERNAL_CUTOFF} 초과"
                )
            if candidate:
                maximum_as_of = max(maximum_as_of or candidate, candidate)

    if row_count != spec.expected_rows:
        raise ValueError(
            f"{spec.code}: {row_count:,}행 != 기대 {spec.expected_rows:,}행"
        )
    return SourceInspection(
        spec=spec,
        data_path=data_path,
        schema_path=schema_path,
        columns=columns,
        null_counts=tuple(null_counts),
        row_count=row_count,
        excluded_rows=excluded_rows,
        effective_as_of=maximum_as_of or RELEASE_DATE,
        data_sha256=sha256_file(data_path),
        schema_sha256=sha256_file(schema_path),
    )


def validate_source_dir(value: str | Path | None = None) -> tuple[SourceInspection, ...]:
    root = dataset_dir(value)
    if not root.is_dir():
        raise FileNotFoundError(f"정본 데이터 디렉터리를 찾을 수 없습니다: {root}")
    manifest_path = root / CONVERSION_MANIFEST
    if not manifest_path.is_file():
        if any(root.rglob("*260824*")) or any(root.rglob("prbd01n001_data.xlsx")):
            raise LookAheadError("2026-08-24 스냅샷은 평가 cutoff 2026-07-11 이후 정본입니다")
        raise FileNotFoundError(f"승인 변환 manifest 누락: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    approved = {
        str(entry["file"]): entry
        for entry in manifest
        if isinstance(entry, dict) and str(entry.get("file", "")).endswith(".csv")
    }
    expected = {name for spec in SOURCES for name in (spec.data_file, spec.schema_file)}
    if not expected <= set(approved):
        raise ValueError(f"변환 manifest 정본 파일 누락: {sorted(expected - set(approved))}")
    for name in sorted(expected):
        entry = approved[name]
        if entry.get("snapshot") != RELEASE_DATE.isoformat():
            raise LookAheadError(f"{name}: snapshot={entry.get('snapshot')}가 2026-07-11 계약과 불일치")
        path = root / name
        if not path.is_file() or sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"{name}: 승인 SHA-256 불일치")
    return tuple(inspect_source(root, spec) for spec in SOURCES)


def snapshot_hash(inspections: Iterable[SourceInspection]) -> str:
    payload = [
        {
            "file": item.data_path.name,
            "sha256": item.data_sha256,
            "schema_file": item.schema_path.name,
            "schema_sha256": item.schema_sha256,
        }
        for item in inspections
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
