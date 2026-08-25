#!/usr/bin/env bash
set -euo pipefail

: "${ADMIN_DATABASE_URL:?ADMIN_DATABASE_URL must be set}"
: "${DATASET_DIR:?DATASET_DIR must point to the approved 2026-07-11 CSV bundle}"
: "${CLOVA_API_KEY:?CLOVA_API_KEY must be set for schema embeddings}"

docker compose --profile ops build builder api
docker compose --profile ops run --rm builder python -m kb.build_data_platform_v2
docker compose --profile ops run --rm builder python -m kb.load_external_v2
docker compose --profile ops run --rm builder python -m kb.build_graph_v2
docker compose --profile ops run --rm builder python -m kb.build_vectors_v2
docker compose --profile ops run --rm builder python -m kb.validate_data_platform_v2 --stage
