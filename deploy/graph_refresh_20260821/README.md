# ETF holdings Graph refresh

This release replaces only the domestic ETF `fp:Holding` relationship layer.
The 2026-08-24 organizer master remains the product truth, while the publisher
holding documents have the actual snapshot date 2026-08-21.

## Safety contract

- Never write into `data/data`, `data/snapshots`, or `data/ontology`.
- Build from the verified baseline into `artifacts/runs/...`.
- Load into a new versioned Docker volume.
- Verify the exact ten named graphs, union count, and the single holdings date.
- Keep the previously active volume as the rollback copy.
- Change the Compose pointer only after stage validation passes.

## Collection

```powershell
py -3.13 script\refresh_etf_holdings.py `
  --master ..\..\data\snapshots\legacy-build-2026-08-24\data\csv\PREF01N001_etf_kr_master_20260824.csv `
  --output-dir artifacts\runs\20260906T146-full\codex-t146-holdings-0906 `
  --as-of 2026-08-21
```

Each publisher response has a `.meta.json` sidecar with URL, actual/requested
date evidence, retrieval time, row count, and SHA-256. Products whose official
`pd_lste_dt` is on or before the snapshot are recorded as inactive exclusions,
not false collection failures.

## Bundle and deploy

```powershell
py -3.13 src\kb\refresh_holding_graph.py `
  --baseline-dir ..\..\data\ontology `
  --relation artifacts\runs\20260906T146-full\codex-t146-holdings-0906\etf_holding.csv `
  --provenance artifacts\runs\20260906T146-full\codex-t146-holdings-0906\etf_holdings_provenance.json `
  --master ..\..\data\snapshots\legacy-build-2026-08-24\data\csv\PREF01N001_etf_kr_master_20260824.csv `
  --common-tbox ontology\common.ttl `
  --output-dir artifacts\runs\20260906T146-graph\codex-t146-holdings-0906

.\deploy\graph_refresh_20260821\deploy_vm.ps1 `
  -BundleRoot artifacts\runs\20260906T146-graph\codex-t146-holdings-0906\ontology-bundle
```

`-StageOnly` loads and validates a new volume without changing the runtime
pointer. A normal deployment keeps the old volume, writes versioned stage and
cutover receipts on the VM, recreates only the Graph service, and validates the
public `/db/sparql` route. If cutover verification fails, the script switches
the Compose pointer back to the retained old volume.
