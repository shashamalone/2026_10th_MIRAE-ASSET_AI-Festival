# -*- coding: utf-8 -*-
"""검증된 외부 JSONL bundle을 ``*_next``에 적재한다.

외부 원문과 산출 JSONL은 artifacts(비커밋)에 두며, 모든 published_at/as_of가
2026-08-24 이하여야 한 행이라도 적재된다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.build_data_platform_v2 import SCHEMAS, dsn  # noqa: E402
from kb.collect_lseg_returns_v2 import (  # noqa: E402
    END_DATE as LSEG_END_DATE,
    OBSERVATION_EDGE_TOLERANCE_DAYS,
    OUTPUT as LSEG_OUTPUT,
    START_DATE as LSEG_START_DATE,
)
from kb.v2_manifest import EXTERNAL_CUTOFF, EXPECTED_RELATION_COUNTS, ROOT  # noqa: E402

DEFAULT_BUNDLE = ROOT / "artifacts" / "external_v2"
FILES = {
    "source_documents": "source_documents.jsonl",
    "securities": "securities.jsonl",
    "security_identifiers": "security_identifiers.jsonl",
    "product_holdings": "product_holdings.jsonl",
    "product_classifications": "product_classifications.jsonl",
    "company_subsidiaries": "company_subsidiaries.jsonl",
    "product_documents": "product_documents.jsonl",
}
DATE_FIELDS = {"published_at", "as_of", "observation_start", "observation_end"}


def execute_many(conn: psycopg.Connection, statement: str, rows) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(statement, rows)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    result = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            for field in DATE_FIELDS & set(row):
                if row[field] in (None, ""):
                    continue
                parsed = date.fromisoformat(str(row[field]))
                if parsed > EXTERNAL_CUTOFF:
                    raise ValueError(
                        f"{path.name}:{line_number}: {field}={parsed} > {EXTERNAL_CUTOFF}"
                    )
                row[field] = parsed
            if "url" in row and not str(row["url"]).startswith("https://"):
                raise ValueError(f"{path.name}:{line_number}: 공식 HTTPS URL 필요")
            if "source_hash" in row and not re.fullmatch(r"[0-9a-fA-F]{64}", str(row["source_hash"])):
                raise ValueError(f"{path.name}:{line_number}: SHA-256 형식 오류")
            result.append(row)
    return result


def read_bundle(directory: Path) -> dict[str, list[dict[str, object]]]:
    records = {name: read_jsonl(directory / filename) for name, filename in FILES.items()}
    records["lseg_returns"] = read_jsonl(LSEG_OUTPUT)
    return records


def required(record: dict[str, object], fields: tuple[str, ...], context: str) -> tuple[object, ...]:
    missing = [field for field in fields if record.get(field) in (None, "")]
    if missing:
        raise ValueError(f"{context}: 필수 필드 누락 {missing}")
    return tuple(record[field] for field in fields)


def validate_bundle(records: dict[str, list[dict[str, object]]]) -> dict[str, int]:
    contracts = {
        "source_documents": ("document_id", "title", "publisher", "published_at", "url", "source_hash", "source_type"),
        "securities": ("security_id", "display_name", "security_type"),
        "security_identifiers": ("security_id", "id_type", "id_value", "is_primary"),
        "product_holdings": ("holding_id", "product_id", "security_id", "as_of", "source_document_id", "source"),
        "product_classifications": ("classification_id", "product_id", "classification_type", "classification_value", "as_of", "source_document_id", "source"),
        "company_subsidiaries": ("relation_id", "parent_security_id", "child_security_id", "as_of", "source_document_id", "source"),
        "product_documents": ("product_id", "document_id", "relation_type"),
        "lseg_returns": ("product_id", "metric_code", "unit", "as_of", "source", "source_column", "method", "is_available"),
    }
    for name, fields in contracts.items():
        ids: set[tuple[object, ...]] = set()
        for index, record in enumerate(records[name], 1):
            values = required(record, fields, f"{name}:{index}")
            identity = values[:1] if name not in {"security_identifiers", "product_documents"} else values[:3]
            if identity in ids:
                raise ValueError(f"{name}:{index}: 중복 식별자 {identity}")
            ids.add(identity)
    for index, record in enumerate(records["lseg_returns"], 1):
        if not record.get("is_available"):
            continue
        start, end = required(
            record,
            ("observation_start", "observation_end"),
            f"lseg_returns:{index}",
        )
        if not (
            LSEG_START_DATE <= start <= LSEG_START_DATE + timedelta(days=OBSERVATION_EDGE_TOLERANCE_DAYS)
            and LSEG_END_DATE - timedelta(days=OBSERVATION_EDGE_TOLERANCE_DAYS) <= end <= LSEG_END_DATE
        ):
            raise ValueError(f"lseg_returns:{index}: 1년 관측창 불충족 {start}..{end}")
    return {name: len(values) for name, values in records.items()}


def load(directory: Path) -> dict[str, int]:
    records = read_bundle(directory)
    counts = validate_bundle(records)
    for relation_name, expected in EXPECTED_RELATION_COUNTS.items():
        if counts[relation_name] != expected:
            raise ValueError(
                f"{relation_name}: 검증된 bundle {counts[relation_name]:,} != 기대 {expected:,}"
            )
    with psycopg.connect(dsn()) as conn:
        r = records
        execute_many(
            conn,
            f"""INSERT INTO {SCHEMAS['RELATIONS']}.source_document
              (document_id,title,publisher,published_at,url,source_hash,source_type,as_of)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
              ON CONFLICT (document_id) DO UPDATE SET title=EXCLUDED.title,publisher=EXCLUDED.publisher,
              published_at=EXCLUDED.published_at,url=EXCLUDED.url,source_hash=EXCLUDED.source_hash,
              source_type=EXCLUDED.source_type,as_of=EXCLUDED.as_of""",
            [required(x, ("document_id","title","publisher","published_at","url","source_hash","source_type"), "source_documents") + (x.get("as_of"),) for x in r["source_documents"]],
        )
        execute_many(
            conn,
            f"""INSERT INTO {SCHEMAS['ENRICHED']}.security_master
              (security_id,display_name,security_type,issuer_name,country_code) VALUES (%s,%s,%s,%s,%s)
              ON CONFLICT (security_id) DO UPDATE SET display_name=EXCLUDED.display_name,
              security_type=EXCLUDED.security_type,issuer_name=EXCLUDED.issuer_name,country_code=EXCLUDED.country_code""",
            [required(x, ("security_id","display_name","security_type"), "securities") + (x.get("issuer_name"),x.get("country_code")) for x in r["securities"]],
        )
        execute_many(
            conn,
            f"""INSERT INTO {SCHEMAS['ENRICHED']}.security_identifier
              (security_id,id_type,id_value,is_primary) VALUES (%s,%s,%s,%s)
              ON CONFLICT DO NOTHING""",
            [required(x, ("security_id","id_type","id_value","is_primary"), "security_identifiers") for x in r["security_identifiers"]],
        )
        execute_many(
            conn,
            f"""INSERT INTO {SCHEMAS['RELATIONS']}.product_holding
              (holding_id,product_id,security_id,weight,unit,as_of,source_document_id,source)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (holding_id) DO UPDATE SET
              weight=EXCLUDED.weight,unit=EXCLUDED.unit,as_of=EXCLUDED.as_of,
              source_document_id=EXCLUDED.source_document_id,source=EXCLUDED.source""",
            [required(x, ("holding_id","product_id","security_id"), "product_holdings") + (x.get("weight"),x.get("unit","percent")) + required(x, ("as_of","source_document_id","source"), "product_holdings") for x in r["product_holdings"]],
        )
        execute_many(
            conn,
            f"""INSERT INTO {SCHEMAS['RELATIONS']}.product_classification
              (classification_id,product_id,classification_type,classification_value,as_of,source_document_id,source)
              VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (classification_id) DO UPDATE SET
              classification_value=EXCLUDED.classification_value,as_of=EXCLUDED.as_of,
              source_document_id=EXCLUDED.source_document_id,source=EXCLUDED.source""",
            [required(x, ("classification_id","product_id","classification_type","classification_value","as_of"), "product_classifications") + (x.get("source_document_id"),) + required(x, ("source",), "product_classifications") for x in r["product_classifications"]],
        )
        execute_many(
            conn,
            f"""INSERT INTO {SCHEMAS['RELATIONS']}.company_subsidiary
              (relation_id,parent_security_id,child_security_id,ownership_pct,as_of,source_document_id,source)
              VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (relation_id) DO UPDATE SET
              ownership_pct=EXCLUDED.ownership_pct,as_of=EXCLUDED.as_of,
              source_document_id=EXCLUDED.source_document_id,source=EXCLUDED.source""",
            [required(x, ("relation_id","parent_security_id","child_security_id"), "company_subsidiaries") + (x.get("ownership_pct"),) + required(x, ("as_of","source_document_id","source"), "company_subsidiaries") for x in r["company_subsidiaries"]],
        )
        execute_many(
            conn,
            f"""INSERT INTO {SCHEMAS['RELATIONS']}.product_document
              (product_id,document_id,relation_type) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
            [required(x, ("product_id","document_id","relation_type"), "product_documents") for x in r["product_documents"]],
        )
        for x in r["lseg_returns"]:
            value = x.get("value")
            is_available = bool(x["is_available"]) and value not in (None, 0)
            conn.execute(
                f"""INSERT INTO {SCHEMAS['ENRICHED']}.product_metric
                  (metric_id,product_id,metric_code,value,unit,as_of,source,source_column,method,
                   is_available,unavailable_reason,source_priority)
                  VALUES (md5(%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,2)
                  ON CONFLICT (product_id,metric_code,as_of,source,method) DO UPDATE SET
                  value=EXCLUDED.value,is_available=EXCLUDED.is_available,
                  unavailable_reason=EXCLUDED.unavailable_reason,source_column=EXCLUDED.source_column""",
                (
                    f"{x['product_id']}|{x['metric_code']}|{x['as_of']}|{x['source']}|{x['method']}",
                    x["product_id"],x["metric_code"],value,x["unit"],x["as_of"],x["source"],
                    x["source_column"],x["method"],is_available,
                    None if is_available else x.get("unavailable_reason","VALUE_UNAVAILABLE"),
                ),
            )
        conn.execute(
            f"""UPDATE {SCHEMAS['META']}.product_coverage c SET
              holdings_status=CASE WHEN EXISTS (SELECT 1 FROM {SCHEMAS['RELATIONS']}.product_holding h WHERE h.product_id=c.product_id) THEN 'available' ELSE holdings_status END,
              holdings_reason=CASE WHEN EXISTS (SELECT 1 FROM {SCHEMAS['RELATIONS']}.product_holding h WHERE h.product_id=c.product_id) THEN '근거 문서 기반 편입내역 확보' ELSE holdings_reason END,
              document_status=CASE WHEN EXISTS (SELECT 1 FROM {SCHEMAS['RELATIONS']}.product_document d WHERE d.product_id=c.product_id) THEN 'available' ELSE document_status END,
              document_reason=CASE WHEN EXISTS (SELECT 1 FROM {SCHEMAS['RELATIONS']}.product_document d WHERE d.product_id=c.product_id) THEN '공식 문서 연결' ELSE document_reason END,
              performance_status=CASE WHEN EXISTS (SELECT 1 FROM {SCHEMAS['ENRICHED']}.product_metric m WHERE m.product_id=c.product_id AND m.metric_code='RETURN_1Y' AND m.is_available) THEN 'available' ELSE performance_status END,
              performance_reason=CASE WHEN EXISTS (SELECT 1 FROM {SCHEMAS['ENRICHED']}.product_metric m WHERE m.product_id=c.product_id AND m.metric_code='RETURN_1Y' AND m.is_available) THEN '주최측 또는 허용된 외부 1년 수익률 확보' ELSE performance_reason END"""
        )
        conn.execute(f"REFRESH MATERIALIZED VIEW {SCHEMAS['ENRICHED']}.product_search")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 외부 관계/문서/LSEG bundle 적재")
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--check", action="store_true", help="파일만 검증하고 DB를 변경하지 않음")
    args = parser.parse_args()
    records = read_bundle(args.bundle_dir)
    result = validate_bundle(records) if args.check else load(args.bundle_dir)
    print(json.dumps({"mode": "check" if args.check else "load", "counts": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
