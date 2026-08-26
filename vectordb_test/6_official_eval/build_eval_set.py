"""Build the deterministic offline gold set from the frozen 35-question CSV."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
SOURCE_RELATIVE_PATH = Path("expected_question/2026_expected_queries.csv")
SOURCE_PATH = REPO_ROOT / SOURCE_RELATIVE_PATH
GOLD_PATH = EVAL_DIR / "official_eval_gold.jsonl"
MANIFEST_PATH = EVAL_DIR / "eval_manifest.json"

CANONICAL_RELEASE = "2026-08-24"
SOURCE_SUITE_AS_OF = "2026-07-11"
BASE_SHA = "7105519383833db80e6c6f163c240b4394414d19"

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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def normalized_lf_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    return sha256_text(text.replace("\r\n", "\n").replace("\r", "\n"))


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_source_rows() -> list[dict[str, str]]:
    with SOURCE_PATH.open("r", encoding="utf-8-sig", newline="") as source_file:
        return list(csv.DictReader(source_file))


def build_record(row: dict[str, str], row_number: int) -> dict[str, object]:
    question_id = int(row["id"])
    behavior = row["expected_behavior"]
    disposition = "ANSWER" if behavior == "ANSWER" else "ABSTAIN"
    question_as_of = SOURCE_SUITE_AS_OF if question_id == 32 else None
    effective_cutoff = question_as_of or CANONICAL_RELEASE

    if row["product_category"] not in DOMAIN_MAP:
        raise ValueError(f"No domain mapping for {row['product_category']!r}")
    if disposition == "ABSTAIN" and ABSTAIN_REASONS.get(question_id) != behavior:
        raise ValueError(f"Unexpected abstention behavior for Q{question_id}: {behavior}")

    evidence_text = row["required_evidence"]
    return {
        "schema_version": 1,
        "id": question_id,
        "type": row["type"],
        "evaluation_type": row["evaluation_type"],
        "answerability": row["answerability"],
        "product_category": row["product_category"],
        "domain": DOMAIN_MAP[row["product_category"]],
        "difficulty": row["difficulty"],
        "question": row["question"],
        "required_evidence_text": evidence_text,
        "required_evidence": [item.strip() for item in evidence_text.split(";")],
        "expected_disposition": disposition,
        "abstain_reason_code": ABSTAIN_REASONS.get(question_id),
        "cutoff_policy": {
            "source_suite_declared_as_of": SOURCE_SUITE_AS_OF,
            "canonical_release": CANONICAL_RELEASE,
            "external_evidence_not_after": CANONICAL_RELEASE,
            "question_as_of": question_as_of,
            "effective_evidence_not_after": effective_cutoff,
            "mode": (
                "QUESTION_AS_OF_OVERRIDES_RELEASE"
                if question_as_of
                else "CANONICAL_RELEASE_CUTOFF"
            ),
        },
        "source": {
            "path": SOURCE_RELATIVE_PATH.as_posix(),
            "csv_row_number": row_number,
            "question_sha256": sha256_text(row["question"]),
            "required_evidence_sha256": sha256_text(evidence_text),
        },
    }


def main() -> None:
    rows = load_source_rows()
    records = [build_record(row, index + 2) for index, row in enumerate(rows)]

    gold_text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    GOLD_PATH.write_text(gold_text, encoding="utf-8", newline="\n")

    question_evidence_fingerprint = [
        {
            "id": record["id"],
            "question_sha256": record["source"]["question_sha256"],
            "required_evidence_sha256": record["source"]["required_evidence_sha256"],
        }
        for record in records
    ]
    manifest = {
        "schema_version": 1,
        "name": "official-eval-35-offline",
        "base_sha": BASE_SHA,
        "canonical_release": CANONICAL_RELEASE,
        "source_suite_declared_as_of": SOURCE_SUITE_AS_OF,
        "source": {
            "path": SOURCE_RELATIVE_PATH.as_posix(),
            "normalized_lf_sha256": normalized_lf_sha256(SOURCE_PATH),
        },
        "gold": {
            "path": GOLD_PATH.relative_to(REPO_ROOT).as_posix(),
            "normalized_lf_sha256": normalized_lf_sha256(GOLD_PATH),
        },
        "record_count": len(records),
        "id_contract": {"first": 1, "last": 35, "exactly_once": True},
        "disposition_counts": {"ANSWER": 30, "ABSTAIN": 5},
        "hash_contract": {
            "algorithm": "sha256",
            "encoding": "utf-8",
            "file_newlines": "normalized-to-lf",
            "question_evidence_set_sha256": sha256_text(
                canonical_json(question_evidence_fingerprint)
            ),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"wrote {len(records)} records to {GOLD_PATH}")
    print(f"wrote manifest to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
