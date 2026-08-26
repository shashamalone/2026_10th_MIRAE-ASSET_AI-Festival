#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${OXIGRAPH_VOLUME:?OXIGRAPH_VOLUME must be the exact current volume name}"
: "${OXIGRAPH_NEXT_VOLUME:?OXIGRAPH_NEXT_VOLUME must be the validated versioned volume}"
: "${AGENT_QUERY_URL:?AGENT_QUERY_URL is mandatory before production cutover}"

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <validated-backup-directory>" >&2
  exit 2
fi
backup_dir="$(cd -- "$1" && pwd)"
for required in postgres.dump oxigraph-volume.tgz oxigraph-volume-name.txt SHA256SUMS pg-restore-list.txt graph-tar-list.txt; do
  if [[ ! -f "${backup_dir}/${required}" ]]; then
    echo "validated backup file missing: ${required}" >&2
    exit 2
  fi
done
(
  cd -- "${backup_dir}"
  sha256sum -c SHA256SUMS >/dev/null
)
tar -tzf "${backup_dir}/oxigraph-volume.tgz" >/dev/null
recorded_volume="$(tr -d '\r\n' < "${backup_dir}/oxigraph-volume-name.txt")"
if [[ "${recorded_volume}" != "${OXIGRAPH_VOLUME}" ]]; then
  echo "backup volume ${recorded_volume} != current ${OXIGRAPH_VOLUME}" >&2
  exit 2
fi
if [[ "${OXIGRAPH_NEXT_VOLUME}" == "${OXIGRAPH_VOLUME}" ]]; then
  echo "next and production Graph volume names must differ" >&2
  exit 2
fi
docker volume inspect "${OXIGRAPH_VOLUME}" >/dev/null
docker volume inspect "${OXIGRAPH_NEXT_VOLUME}" >/dev/null

ready="$(docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -At \
  -c "SELECT count(*) FROM meta_next.load_run WHERE status='passed' AND phase='cutover_ready' AND validation_result->>'cutover_ready'='true'")"
if [[ "$(tr -d '\r\n' <<<"${ready}")" != "1" ]]; then
  echo "exactly one cutover_ready stage run is required" >&2
  exit 1
fi

next_container="${OXIGRAPH_NEXT_CONTAINER:-financial-product-graph-next}"
pointer_override="deploy/compose.graph-pointer.yaml"
pointer_file="${GRAPH_POINTER_FILE:-${PWD}/artifacts/runtime/graph-active.env}"

rollback_on_error() {
  status=$?
  trap - ERR
  echo "cutover failed; API remains drained while both stores are restored" >&2
  if ! ./deploy/rollback_v2.sh "${backup_dir}"; then
    if ! OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_VOLUME}" \
      docker compose -f compose.yaml -f "${pointer_override}" stop api; then
      echo "failed to confirm API stop after rollback error" >&2
    fi
    echo "ROLLBACK FAILED; traffic must remain closed for operator recovery" >&2
    exit 97
  fi
  exit "${status}"
}

docker compose stop -t "${API_DRAIN_SECONDS:-30}" api
trap rollback_on_error ERR

docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  < sql/v2/090_cutover.sql

docker compose stop graph
docker compose rm -f graph
if docker container inspect "${next_container}" >/dev/null 2>&1; then
  docker stop "${next_container}" >/dev/null
  docker rm "${next_container}" >/dev/null
fi
OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_NEXT_VOLUME}" \
  docker compose -f compose.yaml -f "${pointer_override}" up -d graph

docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  < sql/v2/100_readonly_grants.sql
docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  < deploy/readonly_lockdown_v2.sql
OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_NEXT_VOLUME}" \
  docker compose -f compose.yaml -f "${pointer_override}" up -d --build api

./deploy/verify_v2.sh --cutover
mkdir -p -- "$(dirname -- "${pointer_file}")"
printf 'OXIGRAPH_ACTIVE_VOLUME=%s\n' "${OXIGRAPH_NEXT_VOLUME}" > "${pointer_file}"

trap - ERR
printf '%s\n' \
  "v2 cutover PASS; preserve ${backup_dir}, ${OXIGRAPH_VOLUME}, ${OXIGRAPH_NEXT_VOLUME}, and *_prev"
