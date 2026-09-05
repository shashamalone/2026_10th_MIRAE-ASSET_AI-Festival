# T-139: catalog SQL reliability

Base: `2ed94ba` (T-138's final prompt/name-normalization handoff).
Task's original base: `4a7cb37`. No DB writes or new dependencies.

## Contract

- `schema_snapshot` remains the only physical-schema authority.
- `catalog_sql` reads domain-filtered `/db/catalog` metadata, validates the
  code-name view/master column contract, rejects incomplete responses, and
  caches semantic rows for five minutes bound to the physical snapshot/release.
- Unambiguous descriptions supplement reviewed aliases; curated AUM, index,
  fees, type, ranking and availability rules take precedence.
- LLM fallback can select only live base columns for requested concepts.
- Target/UNION queries use a deterministic SELECT compiler. SQL-writing and
  SQL-repair LLMs cannot change those queries. Transport 429 retries preserve SQL.
- Values are escaped independently of PostgreSQL string settings; text
  containment uses literal substring matching, not user-supplied LIKE patterns.
- Empty/unsupported conditions stop the query instead of disappearing.
- Product identity and metadata-declared source dates accompany target results.
- A failed/empty Graph dependency cannot become an unrestricted RDB lookup.

## Reproduce

Use the existing Python 3.13 environment; no Python 3.11 requirement.

```powershell
python -m unittest discover -s test/catalog-sql -v
python test/catalog-sql/run_checks.py live --env-file <existing-env-path> --out artifacts/runs/<run-id>/codex-t139-sql-0905
python test/catalog-sql/run_checks.py pipeline --env-file <existing-env-path> --ids Q2,Q4 --rounds 1 --out artifacts/runs/<run-id>/codex-t139-sql-0905
```

`--snapshot-seed <existing-snapshot>` can seed the run's own cache. Its TTL and
server release are still verified. The source cache is never changed. Outputs
must remain in the current worktree's agent-scoped artifact directory.

The user currently requires **one round only** (`--rounds 1`); do not repeat
paid pipeline runs to smooth out model variability. Preserve superseded 429 attempts and report
both the attempted denominator and the scoreable denominator. Do not execute
the legacy analyzer's `main` without redirecting its module-level `HERE`, since
it overwrites tracked historical output files.

For a single diagnostic question without a full-question retry or paid quota
probes, use `--ids Q3 --rounds 1 --single-attempt`. This calls the same instrumented
pipeline once, even on failure; the legacy harness also disables SDK retries.
Run manifests record Python/ontology SHA-256 hashes, including when HEAD is dirty.

Domestic ETF `AUM`, `현재 AUM`, `최종 AUM`, `순자산(AUM)` use `du_last_aum`
(user-confirmed on 2026-09-05). Unqualified net assets remain `pd_net_tamt`.
Projections, filters and sorting share this distinction; no fallback substitutes
one column for the other. Historical goldens/traces are preserved, not rewritten
to match this change. `inspect_etf_outputs.py` compares source columns and fee
availability with read-only SELECTs and no model calls, using supplied product codes.

## Requested-field answer contract

- The compiler exports serializable projection bindings (request label, result
  key, source column, unit, source dates, zero/null policy). The answer node uses
  those execution-time bindings, not a second LLM-based column guess.
- Direct RDB `lookup` without Graph/Vector or narrative topics renders fields in
  code and makes **no answer-model call**. Exact names, numbers, decimals and dates
  remain unchanged; the submission API still has its original five fields.
- Every requested field in scope is displayed with its value or a distinct
  reason: NULL, blank, unselected column, unresolved mapping, zero result rows,
  blocked query, failed query, or a metadata-defined unavailable/restricted value.
  Default numeric zero and false remain values. A catalog zero-as-unavailable
  rule preserves the raw zero but does not present it as a valid measurement.
- Mixed/narrative queries retain synthesis and append the deterministic RDB
  block. A blank answer or narrative-model outage cannot erase that block.
  This does not prove that all free-form narrative claims are correct.
- Source-date fields are bound using catalog metadata, not the dataset's release
  date. Rows are not cross-filled between products/markets. Display truncation
  is explicit (returned rows versus displayed rows).
- This layer cannot recover requirements already lost by intent analysis,
  manufacture missing source values, or create missing Graph/ontology plans.
  Legacy SQL without projection bindings is reported as unmapped, not guessed.

`test_answer_contract.py` covers NULLs, zeros/false, blanks, missing projections,
failures, field completeness, exact values, provenance, multirow separation,
truncation, narrative omissions/outages, joins, and UNION ordinal-rank safety.

## Bond raw values and local ontology output views

- Analysis and verification retain raw-rating, normalized-rating and maturity
  requests separately. A conservative code guard restores known catalog/view
  terms in positive noun-list display clauses, masking named entities first.
  It does not infer filters or recover arbitrary natural-language paraphrases.
- Output-only views live next to the bond catalog but are not physical columns.
  The compiler selects actual `crd_grd`, `mat_dt`, `info_base_dt` inputs; unknown
  view names are never emitted as SQL column names. Raw rating remains unchanged.
- CreditRating labels/aliases come from the existing `ontology/common.ttl` TBox;
  maturity buckets come from `ontology/bond_kr.ttl`. No product/question lookup
  table and no new ontology definitions are introduced.
- Maturity uses `mat_dt - info_base_dt` calendar days, 365 days/year, with an
  inclusive lower and exclusive upper bound. It never substitutes duration,
  stale `remaining_days`, the current clock, or a guess from the product name.
  This is a source repayment-date classification, not a claim about legal/call
  terms. Sentinel/invalid/missing dates, unknown grades, unavailable TBox rules
  and ambiguous classification axes yield an explicit per-field reason.
- Derived evidence travels with each row into the requested-field renderer.
  The answer distinguishes **local TBox rule application** from a remote
  GraphDB/ABox lookup. Output-view filters/sorts are explicitly unsupported;
  UNION supplementary-field limitations remain unchanged.

`test_bond_output_views.py` covers request restoration, model omissions, source
date boundaries, all existing rating aliases, unavailable/ambiguous rules,
nonmutation and plan-to-SQL-to-answer execution without an answer-model call.

## Review / outstanding limitations

- `entity_lookup` is a separate free-form purpose-to-SQL path, still using the
  existing LLM writer/repair. Do not describe all SQL generation as deterministic.
- Intent/verification can omit or misclassify user requests before compilation.
  The compiler does not invent missing filters or translate unknown categories.
- Numeric units without an established conversion (especially foreign-currency
  AUM) are rejected. No exchange rate is fabricated.
- UNION ranks canonical identifiers, then hydrates selected identities with
  catalog-bound supplementary fields and provenance. Failed hydration remains
  explicit; foreign currencies are never combined into an unconverted AUM rank.
- Existing domain subtype/risk-order catalog semantics still require independent
  financial review. A valid SQL query alone is not proof of a correct answer.
- Description aliases and `as_of_column` are metadata, not evidence that a value
  is current or complete. Source values, nulls and coverage caveats must survive
  answer generation. Domestic fee coverage is not repaired by this code.
- Golden answer-token matching is diagnostic, not the competition's final score.
  Review retrieval evidence, unsupported inference, omissions, latency and cost
  separately, with a fixed code/data release recorded in each run manifest.
- Some legacy manual overrides match exact SQL strings. `E'...'` literals and
  qualified columns can evade those heuristics without changing SQL semantics.
  Any apparent pass-rate gain therefore also requires semantic review.

## Q5 / Q7–Q35 remediation diagnostics (2026-09-05)

- `run_sequence.py` paces unique question attempts and refuses an existing output
  directory. Paid attempts must not be repeated to replace a failure. Stop on
  repeated provider outages; no schema safety or release checks are bypassed.
- `replay_rdb.py` reuses a saved intent from the single trace or previous audit.
  Model calls are forbidden, optional Graph queries are read-only, and Vector
  search is explicitly not replayed. This is not end-to-end answer accuracy.
- `report_questions.py` records all 30 scoped questions (Q5, Q7–Q35), their old
  and single-attempt answers, SQL/SPARQL, source metadata, follow-up replays, and
  remaining blockers. It updates the agent-scoped TODO from review decisions.
- `summarize_trace_results.py` reports runtime statuses, tokens and latency,
  never a correctness score. The diagnosis spans several code commits.
- Relation facts require source ID and as-of date. Missing Graph document
  metadata is disclosed. A classification link is not a holding, a risk grade
  is not an industry-risk explanation, and a source update date is not proof of
  the numeric observation date.
- Explicit parent-and-subsidiary enumerations use a scoped OR group; other
  independent requirements retain AND. Company names reach bond issuer filters,
  never the product-ISIN filter. Legal designators are normalized in exact
  organization comparisons without fuzzy company matching.
- Provider errors left Q33–Q35 without paid attempts. Q30 overlapped a logging
  patch but failed at initial intent API access; exclude it from clean-build
  comparisons. No final frozen-build/official score is claimed.
