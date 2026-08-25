# -*- coding: utf-8 -*-
"""legacy 20260711 근거 중 260824 상품과 재검증되는 관계만 bundle로 변환한다.

``../data/data``의 raw/enriched 수치는 운영 정본으로 사용하지 않는다. 이 모듈은
공식 원문과 HTTPS sidecar, cutoff, 새 상품 식별자가 모두 확인되는 국내 ETF
편입내역과 DART 자회사 관계만 ``artifacts/external_v2`` JSONL로 재생성한다.
미해결 식별자는 관계로 추정하지 않고 audit report에 집계한다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.load_external_v2 import FILES, validate_bundle  # noqa: E402
from kb.v2_manifest import (  # noqa: E402
    EXTERNAL_CUTOFF,
    ROOT,
    SOURCES,
    dataset_dir,
    inspect_source,
    iter_data_rows,
)

DEFAULT_LEGACY_ROOT = Path(
    os.environ.get("LEGACY_DATA_DIR", ROOT.parent / "data" / "data")
).resolve()
DEFAULT_OUTPUT = ROOT / "artifacts" / "external_v2"
AUDIT_FILE = "legacy_audit_report.json"


def digest_text(*parts: object, length: int = 32) -> str:
    value = "|".join(str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_date(value: object, context: str) -> date:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{context}: ISO 기준일 오류 {value!r}") from exc
    if parsed > EXTERNAL_CUTOFF:
        raise ValueError(f"{context}: {parsed} > cutoff {EXTERNAL_CUTOFF}")
    return parsed


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_sidecars(directory: Path, key: str) -> dict[str, tuple[dict[str, object], Path]]:
    result: dict[str, tuple[dict[str, object], Path]] = {}
    for meta_path in sorted(directory.glob("*.meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_identity = meta.get(key)
        identity = "" if raw_identity is None else str(raw_identity).strip()
        source_path = meta_path.with_name(meta_path.name.removesuffix(".meta.json"))
        if not identity or not source_path.is_file():
            continue
        if identity in result:
            previous_meta, previous_source = result[identity]
            same_evidence = (
                file_hash(previous_source) == file_hash(source_path)
                and previous_meta.get("url") == meta.get("url")
                and previous_meta.get("as_of") == meta.get("as_of")
            )
            if same_evidence:
                continue
            raise ValueError(f"{directory}: 충돌하는 sidecar {key} 중복 {identity}")
        if not str(meta.get("url", "")).startswith("https://"):
            raise ValueError(f"{meta_path.name}: 공식 HTTPS URL 필요")
        parse_date(meta.get("as_of"), meta_path.name)
        result[identity] = (meta, source_path)
    return result


def current_domestic_etfs(data_dir: str | Path | None) -> set[str]:
    spec = next(item for item in SOURCES if item.code == "PREF01N001")
    inspection = inspect_source(dataset_dir(data_dir), spec)
    names = [column.name for column in inspection.columns]
    id_index = names.index("pd_itm_no")
    group_index = names.index("pd_grp_no")
    return {
        str(row[id_index]).strip()
        for row in iter_data_rows(inspection.data_path, inspection.columns)
        if str(row[group_index]).strip() == "ETF"
    }


def document_record(
    meta: dict[str, object], source_path: Path, title: str, source_type: str
) -> dict[str, object]:
    source_hash = file_hash(source_path)
    as_of = parse_date(meta["as_of"], source_path.name).isoformat()
    return {
        "document_id": f"doc:{source_type}:{source_hash[:24]}",
        "title": title,
        "publisher": str(meta["source"]),
        "published_at": as_of,
        "url": str(meta["url"]),
        "source_hash": source_hash,
        "source_type": source_type,
        "as_of": as_of,
    }


def security_id(code_type: str, raw_code: str, display_name: str) -> str:
    normalized = re.sub(r"\s+", "", raw_code).upper()
    safe_type = {
        "isin": "isin",
        "ticker6": "kr_ticker",
        "bloomberg": "bloomberg",
    }.get(code_type, "legacy_other")
    if safe_type == "legacy_other":
        normalized = digest_text(normalized, display_name, length=24)
    return f"{safe_type}:{normalized}"


def build_holdings(
    legacy_root: Path, product_ids: set[str]
) -> tuple[dict[str, list[dict[str, object]]], dict[str, int]]:
    relations = read_csv(legacy_root / "relations" / "etf_holding.csv")
    sidecars = read_sidecars(legacy_root / "external" / "etf_kr_holdings", "isin")
    documents: dict[str, dict[str, object]] = {}
    securities: dict[str, dict[str, object]] = {}
    identifiers: dict[tuple[str, str, str], dict[str, object]] = {}
    holdings: dict[tuple[str, str, str, str], dict[str, object]] = {}
    product_documents: dict[tuple[str, str], dict[str, object]] = {}
    rejected = defaultdict(int)

    for row_number, row in enumerate(relations, 2):
        source_key = row["pd_itm_no"].strip()
        product_id = f"etf_kr:{source_key}"
        if source_key not in product_ids:
            rejected["product_not_in_260824_etf"] += 1
            continue
        sidecar = sidecars.get(source_key)
        if sidecar is None:
            rejected["official_sidecar_missing"] += 1
            continue
        meta, source_path = sidecar
        relation_as_of = parse_date(row["as_of"], f"etf_holding.csv:{row_number}")
        sidecar_as_of = parse_date(meta["as_of"], source_path.name)
        if relation_as_of != sidecar_as_of:
            rejected["sidecar_as_of_mismatch"] += 1
            continue
        document = document_record(
            meta,
            source_path,
            f"{meta.get('name') or source_key} 구성내역 {relation_as_of}",
            "holding_disclosure",
        )
        documents[document["document_id"]] = document
        product_documents[(product_id, document["document_id"])] = {
            "product_id": product_id,
            "document_id": document["document_id"],
            "relation_type": "holdings",
        }

        raw_code = row["holding_code_raw"].strip()
        code_type = row["holding_code_type"].strip().lower()
        display_name = row["holding_name"].strip() or raw_code
        sec_id = security_id(code_type, raw_code, display_name)
        securities.setdefault(
            sec_id,
            {
                "security_id": sec_id,
                "display_name": display_name,
                "security_type": "holding_security",
                "issuer_name": None,
                "country_code": None,
            },
        )
        id_type = {
            "isin": "ISIN",
            "ticker6": "KR_TICKER",
            "bloomberg": "BLOOMBERG",
        }.get(code_type, "LEGACY_OTHER")
        identifiers[(sec_id, id_type, raw_code)] = {
            "security_id": sec_id,
            "id_type": id_type,
            "id_value": raw_code,
            "is_primary": True,
        }
        holding_key = (
            product_id,
            sec_id,
            relation_as_of.isoformat(),
            str(document["document_id"]),
        )
        weight = float(row["weight"]) if row["weight"].strip() else None
        if holding_key not in holdings:
            holdings[holding_key] = {
                "holding_id": f"holding:{digest_text(product_id, sec_id, relation_as_of, document['document_id'])}",
                "product_id": product_id,
                "security_id": sec_id,
                "weight": weight,
                "unit": "percent",
                "as_of": relation_as_of.isoformat(),
                "source_document_id": document["document_id"],
                "source": row["source"].strip(),
            }
        elif weight is not None:
            previous = holdings[holding_key]["weight"]
            holdings[holding_key]["weight"] = weight if previous is None else float(previous) + weight
            holdings[holding_key]["source"] = f"{row['source'].strip()}; aggregated_same_identifier"

    return (
        {
            "source_documents": list(documents.values()),
            "securities": list(securities.values()),
            "security_identifiers": list(identifiers.values()),
            "product_holdings": list(holdings.values()),
            "product_documents": list(product_documents.values()),
        },
        {
            **rejected,
            "source_rows": len(relations),
            "accepted_relations": len(holdings),
            "matched_source_rows": sum(
                1 for row in relations if row["pd_itm_no"].strip() in product_ids
            ),
        },
    )


def build_subsidiaries(
    legacy_root: Path,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, int]]:
    relations = read_csv(legacy_root / "relations" / "company_subsidiary.csv")
    sidecars = read_sidecars(
        legacy_root / "external" / "company_governance", "corp_code"
    )
    documents: dict[str, dict[str, object]] = {}
    securities: dict[str, dict[str, object]] = {}
    identifiers: dict[tuple[str, str, str], dict[str, object]] = {}
    subsidiaries: list[dict[str, object]] = []
    rejected = defaultdict(int)

    grouped: dict[tuple[str, str, str], list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for row_number, row in enumerate(relations, 2):
        child_code = row["child_corp_code"].strip()
        if not child_code:
            rejected["unresolved_child_corp_code"] += 1
            continue
        grouped[
            (row["parent_corp_code"].strip(), child_code, row["as_of"].strip())
        ].append((row_number, row))

    for (parent_code, child_code, _), grouped_rows in sorted(grouped.items()):
        signatures = {
            (
                row["child_name"].strip(),
                row["ownership_pct"].strip(),
                row["invest_purpose"].strip(),
            )
            for _, row in grouped_rows
        }
        if len(signatures) > 1:
            # DART 원문에 보통주/RCPS 등 여러 증권종류가 한 child corp로 묶인 경우다.
            # 현재 관계 모델에서 안전하게 합산할 공식 계산축이 없으므로 추정하지 않는다.
            rejected["ambiguous_multiple_share_classes"] += len(grouped_rows)
            continue
        row_number, row = grouped_rows[0]
        rejected["exact_duplicate_rows_removed"] += len(grouped_rows) - 1
        sidecar = sidecars.get(parent_code)
        if sidecar is None:
            rejected["official_sidecar_missing"] += 1
            continue
        meta, source_path = sidecar
        relation_as_of = parse_date(row["as_of"], f"company_subsidiary.csv:{row_number}")
        document = document_record(
            meta,
            source_path,
            f"{row['parent_name'].strip()} 타법인출자 현황",
            "dart_governance",
        )
        documents[document["document_id"]] = document
        parent_id = f"dart:{parent_code}"
        child_id = f"dart:{child_code}"
        for sec_id, code, name in (
            (parent_id, parent_code, row["parent_name"].strip()),
            (child_id, child_code, row["child_name"].strip()),
        ):
            securities.setdefault(
                sec_id,
                {
                    "security_id": sec_id,
                    "display_name": name or code,
                    "security_type": "company",
                    "issuer_name": None,
                    "country_code": "KR",
                },
            )
            identifiers[(sec_id, "DART_CORP_CODE", code)] = {
                "security_id": sec_id,
                "id_type": "DART_CORP_CODE",
                "id_value": code,
                "is_primary": True,
            }
        subsidiaries.append(
            {
                "relation_id": f"subsidiary:{digest_text(parent_id, child_id, relation_as_of, document['document_id'])}",
                "parent_security_id": parent_id,
                "child_security_id": child_id,
                "ownership_pct": float(row["ownership_pct"])
                if row["ownership_pct"].strip()
                else None,
                "as_of": relation_as_of.isoformat(),
                "source_document_id": document["document_id"],
                "source": row["source"].strip(),
            }
        )

    return (
        {
            "source_documents": list(documents.values()),
            "securities": list(securities.values()),
            "security_identifiers": list(identifiers.values()),
            "company_subsidiaries": subsidiaries,
        },
        {**rejected, "source_rows": len(relations), "accepted_rows": len(subsidiaries)},
    )


def merge_records(*parts: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
    merged = {name: [] for name in FILES}
    identity_fields = {
        "source_documents": ("document_id",),
        "securities": ("security_id",),
        "security_identifiers": ("security_id", "id_type", "id_value"),
        "product_holdings": ("holding_id",),
        "product_classifications": ("classification_id",),
        "company_subsidiaries": ("relation_id",),
        "product_documents": ("product_id", "document_id", "relation_type"),
    }
    for name in FILES:
        by_key: dict[tuple[object, ...], dict[str, object]] = {}
        for part in parts:
            for record in part.get(name, []):
                key = tuple(record[field] for field in identity_fields[name])
                if key in by_key and by_key[key] != record:
                    raise ValueError(f"{name}: 충돌하는 중복 {key}")
                by_key[key] = record
        merged[name] = [by_key[key] for key in sorted(by_key, key=lambda value: tuple(map(str, value)))]
    return merged


def write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    content = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    path.write_text(content, encoding="utf-8")


def build_bundle(
    legacy_root: Path = DEFAULT_LEGACY_ROOT,
    output_dir: Path = DEFAULT_OUTPUT,
    data_dir: str | Path | None = None,
    check: bool = False,
) -> dict[str, object]:
    product_ids = current_domestic_etfs(data_dir)
    holding_records, holding_audit = build_holdings(legacy_root, product_ids)
    subsidiary_records, subsidiary_audit = build_subsidiaries(legacy_root)
    records = merge_records(holding_records, subsidiary_records)
    counts = validate_bundle({**records, "lseg_returns": []})
    audit = {
        "canonical_dataset": "financial-products-2026-08-24",
        "legacy_root": str(legacy_root),
        "cutoff": EXTERNAL_CUTOFF.isoformat(),
        "accepted": counts,
        "holdings": holding_audit,
        "subsidiaries": subsidiary_audit,
        "rejected_sources": {
            "raw_and_enriched_20260711": "schema/grain mismatch; organizer 260824 values take priority",
            "etf_theme.csv": "as_of and source document missing",
        },
        "unresolved_means_absent": False,
    }
    if not check:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, filename in FILES.items():
            write_jsonl(output_dir / filename, records[name])
        (output_dir / AUDIT_FILE).write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="legacy 근거를 260824 외부 bundle로 재해소")
    parser.add_argument("--legacy-root", type=Path, default=DEFAULT_LEGACY_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--data-dir")
    parser.add_argument("--check", action="store_true", help="bundle을 쓰지 않고 감사만 수행")
    args = parser.parse_args()
    result = build_bundle(
        args.legacy_root.resolve(), args.output_dir.resolve(), args.data_dir, args.check
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
