#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${OXIGRAPH_VOLUME:?OXIGRAPH_VOLUME must be the exact pre-cutover volume}"
: "${OXIGRAPH_NEXT_VOLUME:?OXIGRAPH_NEXT_VOLUME must be the attempted next volume}"
: "${AGENT_QUERY_URL:?AGENT_QUERY_URL is mandatory for rollback verification}"

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <validated-backup-directory>" >&2
  exit 2
fi
backup_dir="$(cd -- "$1" && pwd)"
for required in oxigraph-volume.tgz oxigraph-volume-name.txt SHA256SUMS; do
  if [[ ! -f "${backup_dir}/${required}" ]]; then
    echo "validated backup file missing: ${required}" >&2
    exit 2
  fi
done
(
  cd -- "${backup_dir}"
  sha256sum -c SHA256SUMS >/dev/null
)
recorded_volume="$(tr -d '\r\n' < "${backup_dir}/oxigraph-volume-name.txt")"
if [[ "${recorded_volume}" != "${OXIGRAPH_VOLUME}" ]]; then
  echo "backup volume ${recorded_volume} != requested ${OXIGRAPH_VOLUME}" >&2
  exit 2
fi

pointer_override="deploy/compose.graph-pointer.yaml"
pointer_file="${GRAPH_POINTER_FILE:-${PWD}/artifacts/runtime/graph-active.env}"
next_container="${OXIGRAPH_NEXT_CONTAINER:-financial-product-graph-next}"

OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_NEXT_VOLUME}" \
  docker compose -f compose.yaml -f "${pointer_override}" stop -t "${API_DRAIN_SECONDS:-30}" api

prev_count="$(docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -At \
  -c "SELECT count(*) FROM pg_namespace WHERE nspname IN ('meta_prev','raw_prev','enriched_prev','relations_prev','vec_prev','core_prev')")"
prev_count="$(tr -d '\r\n' <<<"${prev_count}")"
if [[ "${prev_count}" == "6" ]]; then
  docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    < sql/v2/095_rollback.sql
elif [[ "${prev_count}" != "0" ]]; then
  echo "partial *_prev set detected (${prev_count}/6); refusing unsafe rollback" >&2
  exit 1
fi

OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_NEXT_VOLUME}" \
  docker compose -f compose.yaml -f "${pointer_override}" stop graph
OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_NEXT_VOLUME}" \
  docker compose -f compose.yaml -f "${pointer_override}" rm -f graph
if docker container inspect "${next_container}" >/dev/null 2>&1; then
  docker stop "${next_container}" >/dev/null
  docker rm "${next_container}" >/dev/null
fi

if ! docker volume inspect "${OXIGRAPH_VOLUME}" >/dev/null 2>&1; then
  docker volume create "${OXIGRAPH_VOLUME}" >/dev/null
  docker run --rm \
    -v "${OXIGRAPH_VOLUME}:/restore" \
    -v "${backup_dir}:/backup:ro" \
    busybox:1.36 tar -C /restore -xzf /backup/oxigraph-volume.tgz
fi
OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_VOLUME}" \
  docker compose -f compose.yaml -f "${pointer_override}" up -d graph

docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  < sql/v2/100_readonly_grants.sql
docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  < deploy/readonly_lockdown_v2.sql
OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_VOLUME}" \
  docker compose -f compose.yaml -f "${pointer_override}" up -d --build api

if ! ./deploy/verify_v2.sh --rollback; then
  OXIGRAPH_ACTIVE_VOLUME="${OXIGRAPH_VOLUME}" \
    docker compose -f compose.yaml -f "${pointer_override}" stop api
  echo "rollback verification failed; API remains closed" >&2
  exit 1
fi
mkdir -p -- "$(dirname -- "${pointer_file}")"
printf 'OXIGRAPH_ACTIVE_VOLUME=%s\n' "${OXIGRAPH_VOLUME}" > "${pointer_file}"
printf '%s\n' "rollback PASS; failed schemas, next Graph volume, and backup are preserved"
