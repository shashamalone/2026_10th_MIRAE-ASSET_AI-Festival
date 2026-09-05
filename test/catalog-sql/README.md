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

For the frozen-code 35x3 run use `--ids "" --rounds 3`. This is 35 cold + 70 warm
executions, not 105 warm executions. Preserve superseded 429 attempts and report
both the attempted denominator and the scoreable denominator. Do not execute
the legacy analyzer's `main` without redirecting its module-level `HERE`, since
it overwrites tracked historical output files.

## Review / outstanding limitations

- `entity_lookup` is a separate free-form purpose-to-SQL path, still using the
  existing LLM writer/repair. Do not describe all SQL generation as deterministic.
- Intent/verification can omit or misclassify user requests before compilation.
  The compiler does not invent missing filters or translate unknown categories.
- Numeric units without an established conversion (especially foreign-currency
  AUM) are rejected. No exchange rate is fabricated.
- UNION retains the pre-existing fixed four-column result contract; per-metric
  provenance and supplementary fields require a separate consumer-contract change.
- Existing domain subtype/risk-order catalog semantics still require independent
  financial review. A valid SQL query alone is not proof of a correct answer.
- Description aliases and `as_of_column` are metadata, not evidence that a value
  is current or complete. Source values, nulls and coverage caveats must survive
  answer generation. Domestic fee coverage is not repaired by this code.
- Golden answer-token matching is diagnostic, not the competition's final score.
  Review retrieval evidence, unsupported inference, omissions, latency and cost
  separately, with a fixed code/data release recorded in each run manifest.
