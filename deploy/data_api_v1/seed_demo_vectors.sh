#!/usr/bin/env bash
set -Eeuo pipefail

project=${COMPOSE_PROJECT_NAME:-}
manifest_host=${DEMO_VECTOR_MANIFEST:-artifacts/demo_vectors/manifest.json}
manifest_container=/app/artifacts/demo_vectors/manifest.json

if [[ "${project}" != "financial-agent-prep" ]]; then
  echo "REFUSE_PROJECT: expected financial-agent-prep actual=${project:-unset}" >&2
  exit 2
fi
if [[ ! -f "${manifest_host}" ]]; then
  echo "MISSING_MANIFEST: ${manifest_host}" >&2
  exit 2
fi

compose=(docker compose --project-name "${project}" -f compose.yaml)
"${compose[@]}" --profile ops run --rm builder \
  python -m kb.build_demo_vectors_v2 --manifest "${manifest_container}" --check

if [[ "${DEMO_VECTOR_APPLY_ACK:-}" != "APPLY_TWO_OFFICIAL_DOCUMENTS" ]]; then
  echo "CHECK PASS; set DEMO_VECTOR_APPLY_ACK=APPLY_TWO_OFFICIAL_DOCUMENTS to perform two CLOVA embedding calls" >&2
  exit 3
fi

"${compose[@]}" --profile ops run --rm builder \
  python -m kb.build_demo_vectors_v2 --manifest "${manifest_container}"
"${compose[@]}" --profile ops run --rm builder \
  python -m kb.build_demo_vectors_v2 --verify
echo "DEMO VECTOR PASS: schema=vec_demo documents=2 chunks=2 production_ready=false"
