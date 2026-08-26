# Official 35-question offline evaluation

This directory freezes the source contract in
`expected_question/2026_expected_queries.csv` without changing the source files.
It uses only the Python standard library and performs no network or LLM calls.

## Files

- `official_eval_gold.jsonl`: one machine-readable record for each ID 1..35.
- `eval_manifest.json`: source/gold SHA-256 values and release/count contracts.
- `build_eval_set.py`: deterministic artifact builder.
- `validate_eval_set.py`: contract self-check and optional prediction scorer.

Every gold record preserves the original question and required-evidence text. It
also stores their individual UTF-8 SHA-256 values, normalized domains, difficulty,
expected disposition, and cutoff policy. Q31..35 carry explicit abstention reason
codes. Q32 retains its original `2026-07-11` wording and therefore applies that
question-specific cutoff even though the canonical repository release is
`2026-08-24`.

Whole-file hashes normalize CRLF/CR newlines to LF before hashing so Git's Windows
checkout conversion cannot invalidate the contract. Per-question and per-evidence
hashes operate on the exact UTF-8 field text.

## Validate

```powershell
python vectordb_test/6_official_eval/validate_eval_set.py --self-check
```

The command fails if the source CSV, question/evidence text, gold file, IDs,
counts, domains, dispositions, abstention codes, or cutoff policies drift.

## Score offline predictions

Pass a UTF-8 JSONL file containing IDs in order from 1 through 35:

```json
{"id": 1, "disposition": "ANSWER", "evidence_keys": ["상품번호", "갱신일", "발행사", "원신용등급", "금리·만기·수익률·수량 컬럼"]}
{"id": 31, "disposition": "ABSTAIN", "abstain_reason_code": "ABSTAIN_INVALID_TAXONOMY"}
```

```powershell
python vectordb_test/6_official_eval/validate_eval_set.py --predictions predictions.jsonl
```

For `ANSWER`, `evidence_keys` are checked against the exact semicolon-delimited
gold requirements. For `ABSTAIN`, the disposition and reason code must both
match. This scorer verifies the response contract only; it does not claim that
the current data layer can supply every gold requirement. See the gap report.
