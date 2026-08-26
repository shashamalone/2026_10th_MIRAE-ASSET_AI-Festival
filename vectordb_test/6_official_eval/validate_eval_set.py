"""Validate the frozen official evaluation set and optionally score predictions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
GOLD_PATH = EVAL_DIR / "official_eval_gold.jsonl"
MANIFEST_PATH = EVAL_DIR / "eval_manifest.json"
EXPECTED_IDS = list(range(1, 36))
CANONICAL_RELEASE = "2026-08-24"
SOURCE_SUITE_AS_OF = "2026-07-11"

DOMAIN_MAP = {
    "채권": ["bond_kr"],
    "국내ETF": ["etf_kr"],
    "해외ETF": ["etf_gl"],
    "공모펀드": ["fund_pub"],
    "ETF": ["etf_kr", "etf_gl"],
    "전체": ["bond_kr", "etf_kr", "etf_gl", "fund_pub"],
    "국내ETF·공모펀드": ["etf_kr", "fund_pub"],
    "국내ETF·해외ETF": ["etf_kr", "etf_gl"],
    "채권·국내ETF·공모펀드": ["bond_kr", "etf_kr", "fund_pub"],
    "채권·ETF": ["bond_kr", "etf_kr", "etf_gl"],
    "해외ETF·채권": ["etf_gl", "bond_kr"],
}

ABSTAIN_REASONS = {
    31: "ABSTAIN_INVALID_TAXONOMY",
    32: "ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF",
    33: "ABSTAIN_ENTITY_NOT_FOUND",
    34: "ABSTAIN_FUTURE_DATA",
    35: "ABSTAIN_DOMAIN_MISMATCH",
}

REQUIRED_KEYS = {
    "schema_version",
    "id",
    "type",
    "evaluation_type",
    "answerability",
    "product_category",
    "domain",
    "difficulty",
    "question",
    "required_evidence_text",
    "required_evidence",
    "expected_disposition",
    "abstain_reason_code",
    "cutoff_policy",
    "source",
}


class ValidationFailure(Exception):
    """Raised when one or more deterministic contract checks fail."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def normalized_lf_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    return sha256_text(text.replace("\r\n", "\n").replace("\r", "\n"))


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValidationFailure(f"{path}: blank line at {line_number}")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationFailure(f"{path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValidationFailure(f"{path}:{line_number}: object required")
        records.append(value)
    return records


def check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_gold() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    errors: list[str] = []
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source_path = REPO_ROOT / manifest["source"]["path"]
    records = load_jsonl(GOLD_PATH)

    check(manifest.get("schema_version") == 1, "manifest schema_version must be 1", errors)
    check(manifest.get("record_count") == 35, "manifest record_count must be 35", errors)
    check(
        manifest.get("disposition_counts") == {"ANSWER": 30, "ABSTAIN": 5},
        "manifest disposition counts must be ANSWER=30, ABSTAIN=5",
        errors,
    )
    check(
        manifest.get("canonical_release") == CANONICAL_RELEASE,
        f"canonical release must be {CANONICAL_RELEASE}",
        errors,
    )
    check(
        manifest.get("source_suite_declared_as_of") == SOURCE_SUITE_AS_OF,
        f"source suite as-of must remain {SOURCE_SUITE_AS_OF}",
        errors,
    )
    check(
        normalized_lf_sha256(source_path) == manifest["source"]["normalized_lf_sha256"],
        "source CSV SHA-256 does not match manifest",
        errors,
    )
    check(
        normalized_lf_sha256(GOLD_PATH) == manifest["gold"]["normalized_lf_sha256"],
        "gold JSONL SHA-256 does not match manifest",
        errors,
    )

    with source_path.open("r", encoding="utf-8-sig", newline="") as source_file:
        source_rows = list(csv.DictReader(source_file))
    source_by_id = {int(row["id"]): row for row in source_rows}
    ids = [record.get("id") for record in records]

    check(len(records) == 35, f"gold must contain 35 records, found {len(records)}", errors)
    check(ids == EXPECTED_IDS, f"gold IDs must be ordered exactly 1..35, found {ids}", errors)
    check(len(set(ids)) == len(ids), "gold IDs must be unique", errors)
    check(sorted(source_by_id) == EXPECTED_IDS, "source CSV IDs must be exactly 1..35", errors)

    dispositions: Counter[str] = Counter()
    difficulties: Counter[str] = Counter()
    fingerprint: list[dict[str, object]] = []

    for record in records:
        question_id = record.get("id")
        if question_id not in source_by_id:
            continue
        row = source_by_id[question_id]
        label = f"Q{question_id}"
        missing_keys = REQUIRED_KEYS - set(record)
        check(not missing_keys, f"{label}: missing keys {sorted(missing_keys)}", errors)
        if missing_keys:
            continue

        expected_disposition = "ANSWER" if row["expected_behavior"] == "ANSWER" else "ABSTAIN"
        expected_reason = ABSTAIN_REASONS.get(question_id)
        expected_evidence = [item.strip() for item in row["required_evidence"].split(";")]
        question_as_of = SOURCE_SUITE_AS_OF if question_id == 32 else None
        expected_cutoff = {
            "source_suite_declared_as_of": SOURCE_SUITE_AS_OF,
            "canonical_release": CANONICAL_RELEASE,
            "external_evidence_not_after": CANONICAL_RELEASE,
            "question_as_of": question_as_of,
            "effective_evidence_not_after": question_as_of or CANONICAL_RELEASE,
            "mode": (
                "QUESTION_AS_OF_OVERRIDES_RELEASE"
                if question_as_of
                else "CANONICAL_RELEASE_CUTOFF"
            ),
        }

        check(record["schema_version"] == 1, f"{label}: schema_version must be 1", errors)
        check(record["type"] == row["type"], f"{label}: type differs from source", errors)
        check(
            record["evaluation_type"] == row["evaluation_type"],
            f"{label}: evaluation_type differs from source",
            errors,
        )
        check(
            record["answerability"] == row["answerability"],
            f"{label}: answerability differs from source",
            errors,
        )
        check(
            record["product_category"] == row["product_category"],
            f"{label}: product_category differs from source",
            errors,
        )
        check(
            record["domain"] == DOMAIN_MAP.get(row["product_category"]),
            f"{label}: domain mapping is invalid",
            errors,
        )
        check(record["difficulty"] == row["difficulty"], f"{label}: difficulty differs", errors)
        check(record["question"] == row["question"], f"{label}: question text was rewritten", errors)
        check(
            record["required_evidence_text"] == row["required_evidence"],
            f"{label}: evidence text was rewritten",
            errors,
        )
        check(
            record["required_evidence"] == expected_evidence,
            f"{label}: evidence list differs from source",
            errors,
        )
        check(
            record["expected_disposition"] == expected_disposition,
            f"{label}: expected disposition is invalid",
            errors,
        )
        check(
            record["abstain_reason_code"] == expected_reason,
            f"{label}: abstain reason must be {expected_reason!r}",
            errors,
        )
        check(record["cutoff_policy"] == expected_cutoff, f"{label}: cutoff policy is invalid", errors)
        check(
            record["source"]["path"] == manifest["source"]["path"],
            f"{label}: source path differs from manifest",
            errors,
        )
        check(
            record["source"]["csv_row_number"] == question_id + 1,
            f"{label}: source CSV row number is invalid",
            errors,
        )
        question_hash = sha256_text(row["question"])
        evidence_hash = sha256_text(row["required_evidence"])
        check(
            record["source"]["question_sha256"] == question_hash,
            f"{label}: question SHA-256 mismatch",
            errors,
        )
        check(
            record["source"]["required_evidence_sha256"] == evidence_hash,
            f"{label}: evidence SHA-256 mismatch",
            errors,
        )

        dispositions[record["expected_disposition"]] += 1
        difficulties[record["difficulty"]] += 1
        fingerprint.append(
            {
                "id": question_id,
                "question_sha256": question_hash,
                "required_evidence_sha256": evidence_hash,
            }
        )

    check(dispositions == {"ANSWER": 30, "ABSTAIN": 5}, f"bad dispositions: {dict(dispositions)}", errors)
    check(difficulties == {"하": 10, "중": 10, "상": 10, "-": 5}, f"bad difficulties: {dict(difficulties)}", errors)
    check(
        sha256_text(canonical_json(fingerprint))
        == manifest["hash_contract"]["question_evidence_set_sha256"],
        "question/evidence set fingerprint does not match manifest",
        errors,
    )

    if errors:
        raise ValidationFailure("\n".join(f"- {error}" for error in errors))
    return records, manifest


def score_predictions(gold: list[dict[str, Any]], prediction_path: Path) -> dict[str, Any]:
    predictions = load_jsonl(prediction_path)
    ids = [prediction.get("id") for prediction in predictions]
    if ids != EXPECTED_IDS or len(set(ids)) != 35:
        raise ValidationFailure("prediction IDs must be ordered exactly 1..35")

    passed = 0
    disposition_correct = 0
    abstain_reason_correct = 0
    evidence_coverage_total = 0.0
    details: list[dict[str, Any]] = []

    for expected, actual in zip(gold, predictions, strict=True):
        disposition_ok = actual.get("disposition") == expected["expected_disposition"]
        disposition_correct += int(disposition_ok)
        if expected["expected_disposition"] == "ANSWER":
            submitted_evidence = actual.get("evidence_keys", [])
            if not isinstance(submitted_evidence, list):
                submitted_evidence = []
            required = set(expected["required_evidence"])
            supplied = set(submitted_evidence)
            evidence_coverage = len(required & supplied) / len(required)
            reason_ok = True
        else:
            evidence_coverage = 1.0
            reason_ok = actual.get("abstain_reason_code") == expected["abstain_reason_code"]
            abstain_reason_correct += int(reason_ok)
        evidence_coverage_total += evidence_coverage
        record_pass = disposition_ok and reason_ok and evidence_coverage == 1.0
        passed += int(record_pass)
        details.append(
            {
                "id": expected["id"],
                "pass": record_pass,
                "disposition_ok": disposition_ok,
                "abstain_reason_ok": reason_ok,
                "evidence_coverage": round(evidence_coverage, 6),
            }
        )

    return {
        "record_count": 35,
        "passed": passed,
        "pass_rate": round(passed / 35, 6),
        "disposition_accuracy": round(disposition_correct / 35, 6),
        "abstain_reason_accuracy": round(abstain_reason_correct / 5, 6),
        "mean_evidence_coverage": round(evidence_coverage_total / 35, 6),
        "details": details,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="validate only the committed gold contract")
    parser.add_argument("--predictions", type=Path, help="score an offline JSONL prediction file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.self_check and args.predictions is None:
        print("error: pass --self-check or --predictions PATH", file=sys.stderr)
        return 2
    try:
        gold, manifest = validate_gold()
        if args.predictions is not None:
            print(json.dumps(score_predictions(gold, args.predictions), ensure_ascii=False, indent=2))
        else:
            print(
                "SELF-CHECK PASS: "
                f"{manifest['record_count']} records, "
                "IDs 1..35, ANSWER=30, ABSTAIN=5, source/hash/cutoff contracts valid"
            )
    except (KeyError, OSError, ValueError, ValidationFailure, json.JSONDecodeError) as exc:
        print(f"SELF-CHECK FAIL:\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
