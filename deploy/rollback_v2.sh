#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${OXIGRAPH_VOLUME:?OXIGRAPH_VOLUME must be the exact Docker volume name}"

if [[ $# -ne 1 || ! -f "$1/oxigraph-volume.tgz" || ! -f "$1/oxigraph-volume-name.txt" ]]; then
  echo "usage: $0 <validated-backup-directory>" >&2
  exit 2
fi
backup_dir="$(cd -- "$1" && pwd)"
recorded_volume="$(tr -d '\r\n' < "${backup_dir}/oxigraph-volume-name.txt")"
if [[ "${recorded_volume}" != "${OXIGRAPH_VOLUME}" ]]; then
  echo "backup volume ${recorded_volume} != requested ${OXIGRAPH_VOLUME}" >&2
  exit 2
fi

docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  < sql/v2/095_rollback.sql
docker compose stop graph
docker compose rm -f graph
docker volume inspect "${OXIGRAPH_VOLUME}" >/dev/null 2>&1 && docker volume rm "${OXIGRAPH_VOLUME}"
docker compose create graph >/dev/null
docker run --rm \
  -v "${OXIGRAPH_VOLUME}:/restore" \
  -v "${backup_dir}:/backup:ro" \
  busybox:1.36 tar -C /restore -xzf /backup/oxigraph-volume.tgz
docker compose up -d graph api
