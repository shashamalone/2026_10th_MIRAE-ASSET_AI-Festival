#!/usr/bin/env bash
set -Eeuo pipefail

project=${COMPOSE_PROJECT_NAME:-}
api_port=${API_PORT:-8000}
verify_url="http://127.0.0.1:${api_port}"
overlay=deploy/data_api_v1/compose.public-test.yaml
graph_pointer=deploy/compose.graph-pointer.yaml
team_overlay=deploy/data_api_v1/compose.team-db-test.yaml
team_db_public=${TEAM_DB_PUBLIC_MODE:-0}
team_db_ack=${TEAM_DB_PUBLIC_ACK:-}

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
if [[ "${team_db_public}" != 0 && "${team_db_public}" != 1 ]]; then
  echo "REFUSE_TEAM_DB_MODE: expected 0 or 1 actual=${team_db_public}" >&2
  exit 2
fi
if [[ "${team_db_public}" == 1 && "${team_db_ack}" != I_ACCEPT_TEMPORARY_GUARDED_READ_ONLY_DB ]]; then
  echo "REFUSE_TEAM_DB_ACK: explicit temporary public /db acknowledgement is required" >&2
  exit 2
fi

python3 deploy/data_api_v1/verify_public_api.py --url "${verify_url}" --health-only
compose=(docker compose --project-name "${project}" -f compose.yaml -f "${graph_pointer}" -f "${overlay}")
services=(api api-debug)
verify_args=(--url "${verify_url}")
if [[ "${team_db_public}" == 1 ]]; then
  test -f "${team_overlay}"
  compose+=(-f "${team_overlay}")
  services=(api)
  verify_args+=(--team-db-public)
fi
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

"${compose[@]}" build "${services[@]}"
if [[ "${team_db_public}" == 1 ]]; then
  "${compose[@]}" stop api-debug >/dev/null 2>&1 || true
  "${compose[@]}" rm -f api-debug >/dev/null 2>&1 || true
fi
"${compose[@]}" up -d --no-deps "${services[@]}"
python3 deploy/data_api_v1/verify_public_api.py "${verify_args[@]}"
trap - ERR
if [[ "${team_db_public}" == 1 ]]; then
  echo "TEAM DB TEST API PASS: url=${verify_url} raw_db=guarded-readonly expires=${PUBLIC_TEST_EXPIRES_AT}"
else
  echo "PUBLIC TEST API PASS: url=${verify_url} debug=http://127.0.0.1:${API_DEBUG_PORT:-8001} raw_db=blocked"
fi
