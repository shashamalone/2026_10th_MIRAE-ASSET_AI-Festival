#!/usr/bin/env bash
set -Eeuo pipefail

project=${COMPOSE_PROJECT_NAME:-}
api_port=${API_PORT:-8000}
verify_url="http://127.0.0.1:${api_port}"
graph_pointer=deploy/compose.graph-pointer.yaml
graph_union=deploy/data_api_v1/compose.graph-union-default.yaml
public_overlay=deploy/data_api_v1/compose.public-test.yaml
expected_graph_triples=${EXPECTED_GRAPH_TRIPLES:-1628311}

if [[ "${project}" != "financial-agent-prep" ]]; then
  echo "REFUSE_PROJECT: expected financial-agent-prep actual=${project:-unset}" >&2
  exit 2
fi
if [[ "${V2_CUTOVER_CONFIRMED:-}" != "V2_RELEASE_IS_ACTIVE" ]]; then
  echo "REFUSE_CUTOVER_STATE: V2_CUTOVER_CONFIRMED=V2_RELEASE_IS_ACTIVE is required" >&2
  exit 2
fi
if [[ "${GRAPH_CUTOVER_CONFIRMED:-}" != "GRAPH_1628311_IS_ACTIVE" ]]; then
  echo "REFUSE_GRAPH_STATE: GRAPH_CUTOVER_CONFIRMED=GRAPH_1628311_IS_ACTIVE is required" >&2
  exit 2
fi
if [[ -z "${PUBLIC_TEST_EXPIRES_AT:-}" ]]; then
  echo "REFUSE_EXPIRY: PUBLIC_TEST_EXPIRES_AT is required" >&2
  exit 2
fi
if [[ "${expected_graph_triples}" != 1628311 ]]; then
  echo "REFUSE_GRAPH_COUNT: expected 1628311 actual=${expected_graph_triples}" >&2
  exit 2
fi

compose=(
  docker compose --project-name "${project}"
  -f compose.yaml
  -f "${graph_pointer}"
  -f "${graph_union}"
  -f "${public_overlay}"
)
"${compose[@]}" config >/dev/null

container="${project}-api-1"
old_image=$(docker inspect --format '{{.Image}}' "${container}" 2>/dev/null || true)
if [[ -z "${old_image}" ]] || ! docker image inspect "${old_image}" >/dev/null 2>&1; then
  echo "REFUSE_ROLLBACK_IMAGE: running API image is not locally recoverable" >&2
  exit 2
fi
rollback() {
  code=$?
  if [[ ${code} -eq 0 ]]; then
    return
  fi
  echo "RAW QUERY API deploy failed; previous image id=${old_image:-unavailable}" >&2
  if [[ -n "${old_image}" ]] && docker image inspect "${old_image}" >/dev/null 2>&1; then
    docker image tag "${old_image}" "${project}-api:latest"
    "${compose[@]}" up -d --no-deps --no-build api
  fi
  exit "${code}"
}
trap rollback ERR

"${compose[@]}" build api
"${compose[@]}" up -d --no-deps graph
"${compose[@]}" up -d --no-deps api
python3 deploy/data_api_v1/verify_public_api.py \
  --url "${verify_url}" \
  --expected-graph-triples "${expected_graph_triples}"

trap - ERR
echo "RAW QUERY PUBLIC TEST API PASS: url=${verify_url} expires=${PUBLIC_TEST_EXPIRES_AT} graph=${expected_graph_triples} union_default=on"
