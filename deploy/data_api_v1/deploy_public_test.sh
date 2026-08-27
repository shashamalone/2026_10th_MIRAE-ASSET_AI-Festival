#!/usr/bin/env bash
set -Eeuo pipefail

project=${COMPOSE_PROJECT_NAME:-}
api_port=${API_PORT:-8000}
verify_url="http://127.0.0.1:${api_port}"
overlay=deploy/data_api_v1/compose.public-test.yaml
graph_pointer=deploy/compose.graph-pointer.yaml

if [[ "${project}" != "financial-agent-prep" ]]; then
  echo "REFUSE_PROJECT: expected financial-agent-prep actual=${project:-unset}" >&2
  exit 2
fi
if [[ "${V2_CUTOVER_CONFIRMED:-}" != "V2_RELEASE_IS_ACTIVE" ]]; then
  echo "REFUSE_CUTOVER_STATE: confirm T-105 success with V2_CUTOVER_CONFIRMED=V2_RELEASE_IS_ACTIVE" >&2
  exit 2
fi
if [[ -z "${PUBLIC_TEST_EXPIRES_AT:-}" ]]; then
  echo "REFUSE_EXPIRY: PUBLIC_TEST_EXPIRES_AT is required" >&2
  exit 2
fi

python deploy/data_api_v1/verify_public_api.py --url "${verify_url}" --health-only
compose=(docker compose --project-name "${project}" -f compose.yaml -f "${graph_pointer}" -f "${overlay}")
"${compose[@]}" config >/dev/null

container="${project}-api-1"
old_image=$(docker inspect --format '{{.Image}}' "${container}" 2>/dev/null || true)
rollback() {
  code=$?
  if [[ ${code} -eq 0 ]]; then
    return
  fi
  echo "DATA API deploy failed; previous image id=${old_image:-unavailable}" >&2
  if [[ -n "${old_image}" ]]; then
    docker image tag "${old_image}" "${project}-api:latest"
    "${compose[@]}" up -d --no-deps --no-build api
  fi
  exit "${code}"
}
trap rollback ERR

"${compose[@]}" build api api-debug
"${compose[@]}" up -d --no-deps api api-debug
python deploy/data_api_v1/verify_public_api.py --url "${verify_url}"
trap - ERR
echo "PUBLIC TEST API PASS: url=${verify_url} debug=http://127.0.0.1:${API_DEBUG_PORT:-8001}"
