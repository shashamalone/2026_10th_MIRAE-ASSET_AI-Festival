#!/usr/bin/env bash
set -euo pipefail

: "${ADMIN_DATABASE_URL:?ADMIN_DATABASE_URL must be set}"
: "${DATASET_DIR:?DATASET_DIR must point to the canonical 2026-08-24 XLSX directory}"
: "${OXIGRAPH_VOLUME:?OXIGRAPH_VOLUME must be the exact current production volume}"
: "${OXIGRAPH_NEXT_VOLUME:?OXIGRAPH_NEXT_VOLUME must be a new versioned volume}"

next_container="${OXIGRAPH_NEXT_CONTAINER:-financial-product-graph-next}"
stage_run_started=0

mark_stage_failed() {
  exit_code=$?
  trap - ERR
  if [[ "${stage_run_started}" == "1" ]]; then
    if ! docker compose --profile ops run --rm builder \
      python -m kb.build_data_platform_v2 --mark-failed stage_command_failed; then
      printf '%s\n' "WARNING: stage failed and load_run failure recording also failed" >&2
    fi
  fi
  exit "${exit_code}"
}

trap mark_stage_failed ERR

docker compose --profile ops build builder api
docker compose up -d db

# Source/catalog/contract checks run inside the immutable builder image.
docker compose --profile ops run --rm builder python -m kb.build_data_platform_v2 --check
docker compose --profile ops run --rm \
  -v "${PWD}/tests:/app/tests:ro" \
  builder python -m unittest discover -s /app/tests -p 'test_v2_contracts.py'

# Only *_next schemas and a new versioned Graph volume are mutated.
stage_run_started=1
docker compose --profile ops run --rm builder python -m kb.build_data_platform_v2
docker compose --profile ops run --rm builder python -m kb.audit_legacy_evidence_v2
docker compose --profile ops run --rm builder python -m kb.load_external_v2
docker compose --profile ops run --rm builder python -m kb.build_graph_v2
docker compose --profile ops run --rm builder python -m kb.build_graph_v2 --validate-files
docker compose --profile ops run --rm builder python -m kb.build_vectors_v2

./deploy/load_graph_next_v2.sh
docker compose --profile ops run --rm --no-deps \
  -e "OXIGRAPH_NEXT_QUERY_URL=http://${next_container}:7878/query" \
  builder python -m kb.validate_data_platform_v2 --stage
stage_run_started=0

printf '%s\n' \
  "stage PASS: *_next is cutover_ready; Graph volume ${OXIGRAPH_NEXT_VOLUME} remains isolated"
