# -*- coding: utf-8 -*-
"""공식 XLSX+단일 카탈로그에서 v2 정의서 4종을 결정적으로 생성한다."""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.catalog_v2 import VIEW_DEFINITIONS, TableDef, build_catalog  # noqa: E402
from kb.v2_manifest import (  # noqa: E402
    DATASET_VERSION,
    EXTERNAL_CUTOFF,
    RELEASE_DATE,
    ROOT,
    snapshot_hash,
    validate_source_dir,
)

DOC_DIR = ROOT / "docs" / "docs_data_layer"
OUTPUTS = {
    "structure": DOC_DIR / "CURRENT_DATA_BUILD_STRUCTURE.md",
    "definition_md": DOC_DIR / "TABLE_DEFINITION_V2_0.md",
    "definition_csv": DOC_DIR / "table_definition_v2_0.csv",
    "agent_catalog": ROOT / "metadata" / "schema_catalog.json",
}


def md(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def structure_markdown(inspections, catalog: tuple[TableDef, ...]) -> str:
    source_rows = "\n".join(
        f"| {item.spec.code} | `{item.data_path.name}` | {item.row_count:,} | "
        f"{len(item.columns)} | {item.effective_as_of or '미표기'} | "
        f"{', '.join(f'{name}={count:,}' for name, count in item.as_dict()['official_nullable_conflicts'].items()) or '-'} | "
        f"`{item.data_sha256}` |"
        for item in inspections
    )
    table_counts: dict[str, int] = {}
    for table in catalog:
        table_counts[table.schema] = table_counts.get(table.schema, 0) + 1
    schema_rows = "\n".join(
        f"| `{schema}` | {count} |" for schema, count in sorted(table_counts.items())
    )
    return f"""# CURRENT DATA BUILD STRUCTURE

자동 생성 파일입니다. 직접 편집하지 말고 `python src/kb/build_catalog_v2.py`를 실행합니다.

## 데이터 계약

- 버전: `{DATASET_VERSION}`
- 배포일/외부 근거 상한: `{RELEASE_DATE.isoformat()}`
- 전체 manifest SHA-256: `{snapshot_hash(inspections)}`
- 원천: 정상 XLSX 8개만 허용하며 `__MACOSX/._*`는 탐색 단계에서 제외합니다.
- 런타임: PostgreSQL 17 + pgvector + Oxigraph + 읽기전용 FastAPI
- 제출 경로에서 제외: DuckDB, FAISS, pyoxigraph, Gemini

## 원천 정본

| 코드 | 데이터 파일 | 행 | 열 | 실질 기준일 | 공식 Nullable 충돌(NULL 건수) | SHA-256 |
|---|---|---:|---:|---|---|---|
{source_rows}

## 빌드 순서

1. 원천 8개 집합·SHA-256·행/열·공식 헤더·PK 유일성 검사
2. `raw_next`에 공식 타입·컬럼 그대로 적재(공백만 NULL, 0 보존)
3. `enriched_next`·`relations_next`·`meta_next` 생성
4. 결정적 ABox TTL 5개 생성 및 TBox/ABox RDF 검증
5. CLOVA Studio `bge-m3` 1024차원 schema/content embedding 적재
6. PK/FK·cutoff·Graph·Vector·교차질의·금지 SQL 검증
7. 검증 완료 후에만 `*_next → 정식`, 기존 정식 → `*_prev` 전환

모든 빌더의 `--check`는 파일과 DB를 변경하지 않습니다. 데이터·외부 원문·임베딩은
Git에 넣지 않고 이 카탈로그, 코드, SQL, 문서와 체크섬만 공유합니다.

## 물리 스키마

| 스키마 | 물리 테이블 수 |
|---|---:|
{schema_rows}

호환 뷰와 materialized view는 `TABLE_DEFINITION_V2_0.md`의 뷰 절을 따릅니다.

## 핵심 의미 규칙

- `buyable_quantity`는 raw/offer 저장 전용이며 구매가능 판정·필터·정렬에 사용하지 않습니다.
- 채권은 최신 정본에 있고 명시적으로 만기 또는 리스팅 종료가 아닌 경우에만
  `is_assumed_purchasable=true`이며 `purchasable_rule`을 함께 반환합니다.
- 측정값의 0/NULL은 `product_metric.is_available=false`로 비교·랭킹에서 제외합니다.
- 코드/플래그 0은 공식 설명을 따르며 이름 컬럼이 없으면 의미를 추측하지 않습니다.
- 동일 지표는 주최측 값이 우선이고 주최측에 축이 없을 때만 cutoff 검증 외부값을 씁니다.
- 미확보 관계는 `meta.product_coverage`에 이유를 저장하며 비보유로 해석하지 않습니다.
- 공식 `Nullable=NO`와 정본 공백이 충돌하면 해당 컬럼만 NULL을 허용하고 충돌 건수를
  manifest·카탈로그에 기록합니다. PK는 예외 없이 NOT NULL입니다.
"""


def definition_markdown(catalog: tuple[TableDef, ...]) -> str:
    sections = [
        "# TABLE DEFINITION V2.0",
        "",
        "자동 생성 파일입니다. 모든 물리 컬럼은 공식 XLSX 또는 `src/kb/catalog_v2.py`의 단일 카탈로그에서 생성됩니다.",
        "",
    ]
    for table in catalog:
        pk = ", ".join(
            column.name
            for column in sorted(
                (column for column in table.columns if column.pk_ordinal),
                key=lambda value: value.pk_ordinal or 0,
            )
        ) or "없음"
        sections.extend(
            [
                f"## `{table.fq_name}`",
                "",
                f"- 종류: {table.kind}",
                f"- 설명: {table.description}",
                f"- grain: {table.grain}",
                f"- PK: `{pk}`",
                f"- 인덱스: {', '.join(table.indexes) or 'PK만'}",
                f"- 상태: 구현={table.implementation_status}, 배포={table.deployment_status}",
                "",
                "| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |",
                "|---:|---|---|:---:|---:|---|---|---|---|---|---|---|",
            ]
        )
        for ordinal, column in enumerate(table.columns, 1):
            sections.append(
                "| "
                + " | ".join(
                    md(value)
                    for value in (
                        ordinal,
                        f"`{column.name}`",
                        f"`{column.data_type}`",
                        "Y" if column.nullable else "N",
                        column.pk_ordinal or "",
                        column.fk_target,
                        column.unit,
                        column.as_of_column,
                        column.description,
                        column.zero_null_rule,
                        column.source_priority,
                        column.transform_expression,
                    )
                )
                + " |"
            )
        sections.append("")

    sections.extend(
        [
            "## 호환 뷰와 검색 뷰",
            "",
            "| 이름 | 종류 | 원천/정의 | 목적/필터 |",
            "|---|---|---|---|",
        ]
    )
    for view in VIEW_DEFINITIONS:
        sections.append(
            f"| `{md(view['name'])}` | {md(view.get('kind', 'view'))} | "
            f"`{md(view['source'])}` | {md(view.get('purpose') or view.get('filter', ''))} |"
        )
    sections.append("")
    return "\n".join(sections)


CSV_COLUMNS = (
    "table_schema",
    "table_name",
    "table_kind",
    "grain",
    "ordinal_position",
    "column_name",
    "data_type",
    "is_nullable",
    "pk_ordinal",
    "fk_target",
    "unit",
    "as_of_column",
    "description",
    "zero_null_rule",
    "source_priority",
    "transform_expression",
    "implementation_status",
    "deployment_status",
)


def definition_csv(catalog: tuple[TableDef, ...]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for table in catalog:
        for ordinal, column in enumerate(table.columns, 1):
            writer.writerow(
                {
                    "table_schema": table.schema,
                    "table_name": table.name,
                    "table_kind": table.kind,
                    "grain": table.grain,
                    "ordinal_position": ordinal,
                    "column_name": column.name,
                    "data_type": column.data_type,
                    "is_nullable": column.nullable,
                    "pk_ordinal": column.pk_ordinal or "",
                    "fk_target": column.fk_target,
                    "unit": column.unit,
                    "as_of_column": column.as_of_column,
                    "description": column.description,
                    "zero_null_rule": column.zero_null_rule,
                    "source_priority": column.source_priority,
                    "transform_expression": column.transform_expression,
                    "implementation_status": table.implementation_status,
                    "deployment_status": table.deployment_status,
                }
            )
    return stream.getvalue()


def agent_catalog(inspections, catalog: tuple[TableDef, ...]) -> str:
    payload = {
        "catalog_version": "2.0",
        "dataset_version": DATASET_VERSION,
        "release_date": RELEASE_DATE.isoformat(),
        "external_cutoff": EXTERNAL_CUTOFF.isoformat(),
        "snapshot_hash": snapshot_hash(inspections),
        "source_files": [item.as_dict() for item in inspections],
        "business_rules": {
            "buyable_quantity": "storage_only_never_use_for_purchasability",
            "bond_purchasability": "present_in_latest_and_not_explicitly_matured_or_delisted",
            "metric_zero_null": "unavailable_exclude_from_ranking",
            "code_zero": "preserve_and_use_official_name_only",
            "source_priority": "organizer_axis_first_external_only_when_axis_absent",
            "missing_holding": "coverage_unavailable_not_not_held",
            "external_cutoff": EXTERNAL_CUTOFF.isoformat(),
            "global_etf_return_1y": "adjusted_price_or_total_return_only_never_plain_close",
        },
        "tables": [table.as_dict() for table in catalog],
        "views": list(VIEW_DEFINITIONS),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_outputs(data_dir: str | Path | None = None) -> dict[Path, str]:
    inspections = validate_source_dir(data_dir)
    catalog = build_catalog(inspections)
    return {
        OUTPUTS["structure"]: structure_markdown(inspections, catalog),
        OUTPUTS["definition_md"]: definition_markdown(catalog),
        OUTPUTS["definition_csv"]: definition_csv(catalog),
        OUTPUTS["agent_catalog"]: agent_catalog(inspections, catalog),
    }


def write_or_check(outputs: dict[Path, str], check: bool) -> None:
    differences: list[str] = []
    for path, content in outputs.items():
        if check:
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != content:
                differences.append(str(path.relative_to(ROOT)))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    if differences:
        raise SystemExit("생성 산출물 불일치: " + ", ".join(differences))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="v2 데이터 카탈로그 4종 생성")
    parser.add_argument("--data-dir", help="정본 XLSX 8개가 있는 디렉터리")
    parser.add_argument(
        "--check", action="store_true", help="어떤 파일도 쓰지 않고 재생성 결과만 비교"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    write_or_check(build_outputs(args.data_dir), args.check)


if __name__ == "__main__":
    main()
