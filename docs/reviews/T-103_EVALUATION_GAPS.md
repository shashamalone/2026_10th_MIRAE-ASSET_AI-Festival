# T-103 Evaluation Gaps

## Contract boundary

The source suite labels questions 1..30 `ANSWER` and questions 31..35
`ABSTAIN`. The offline gold preserves that benchmark contract exactly. It is not
a claim that the current data layer can already produce complete, correct answers
for all 30 answer cases.

The validator is intentionally deterministic and offline. It checks identity,
disposition, required-evidence keys, reason codes, and cutoff/hash invariants. It
does not use an LLM to judge prose and does not invent missing evidence.

## 2026-07-11 and 2026-08-24 gap

| Concern | Frozen source suite | Current repository contract | Evaluation handling |
|---|---|---|---|
| Declared data date | `2026-07-11` in the expected-question Markdown | Canonical release and external cutoff are `2026-08-24` | Both values are explicit in every gold record; neither is rewritten |
| Official inputs | Legacy 2026-07-11 CSV-based analysis | Eight official 2026-08-24 XLSX files take precedence | Gold uses 2026-08-24 as the general evidence cutoff |
| Question-specific date | Q32 literally asks for `2026-07-11` | The repository release is later | Q32 keeps the literal text and uses 2026-07-11 as its stricter effective cutoff |
| Old coverage report | `docs/QUERY_COVERAGE_35.md` measures legacy inputs and explicitly marks itself legacy | V2 schema/catalog target the 2026-08-24 release | Old availability counts are gap evidence, not the current operational truth |

Changing Q32 to 2026-08-24 would alter the test premise and its expected reason
code. This task therefore records the discrepancy rather than silently editing the
question. A future benchmark-version decision should create a new source suite and
new hashes.

## Known evidence gaps

The most concrete local audit is the legacy coverage report; its values must be
revalidated against a built 2026-08-24 data platform before they are used as
current metrics. It nevertheless identifies these contract risks:

- Q1, Q2: named bond rows lacked some requested sale/yield/date values.
- Q4: the requested disparity-rate field is a dummy/uncomputed zero axis and the
  named ETF's base-index evidence was previously absent. The raw zero must not be
  presented as a measured disparity rate.
- Q8, Q9, Q10, Q19: the legacy public-fund layer lacked a per-row numerical
  as-of column; Q19 also had partial hedge-flag coverage.
- Q14: the collateral/guarantee classification axis was absent.
- Q15: the domestic-ETF base-index evidence was incomplete.
- Q20, Q22..Q30: holdings, document quotations, relationship coverage, or history
  were partial or absent. In particular Q23 needs a six-month event history, Q25
  needs official policy documents, Q29 needs overseas holdings, and Q30 needs
  public-fund holdings.
- Q32: local data established no Kimi product relation but did not establish the
  model release-date fact needed to distinguish
  `ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF` from entity-not-found. Its gold reason code is
  preserved as a benchmark expectation, not upgraded into a proven fact.

These gaps should surface as evidence-coverage failures in offline scoring. They
must not be hidden by changing an `ANSWER` record to `ABSTAIN` inside this frozen
set or by supplying unsupported prose.

## Explicit abstention contract

| ID | Reason code | Required decision evidence |
|---:|---|---|
| 31 | `ABSTAIN_INVALID_TAXONOMY` | `AAAA` is outside the allowed credit-rating taxonomy |
| 32 | `ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF` | Release date and product relation evaluated at the literal 2026-07-11 cutoff |
| 33 | `ABSTAIN_ENTITY_NOT_FOUND` | Exact product identity lookup; no substitution with similar names |
| 34 | `ABSTAIN_FUTURE_DATA` | Requested realized 2027 return is later than available evidence |
| 35 | `ABSTAIN_DOMAIN_MISMATCH` | VOO is an ETF and cannot occupy the bond subject domain of `issuedBy` |

Q31..35 must be scored by both `ABSTAIN` disposition and exact reason code. An
empty answer or a different abstention reason is not equivalent.

## Follow-up integration checks

1. Run the self-check after every source-suite or gold change.
2. Build the 2026-08-24 data platform and measure required-evidence coverage per
   question; publish that result separately from the frozen expectation.
3. Version, rather than overwrite, the source suite if the team decides to update
   Q32 or any `ANSWER`/`ABSTAIN` label.
