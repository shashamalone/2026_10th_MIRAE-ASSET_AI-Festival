#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${OXIGRAPH_VOLUME:?OXIGRAPH_VOLUME must be the exact production volume name}"

backup_root="${BACKUP_ROOT:-${PWD}/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${backup_root}/data-platform-v2-${timestamp}"
scratch_db="restore_drill_${timestamp//[^0-9A-Za-z]/_}_$$"
scratch_volume="oxigraph-restore-drill-${timestamp,,}-$$"
graph_needs_restart=0
mkdir -p -- "${backup_dir}"

cleanup() {
  if [[ "${graph_needs_restart}" == "1" ]]; then
    docker compose up -d graph >/dev/null 2>&1 || true
  fi
  docker compose exec -T db dropdb -U "${POSTGRES_USER}" --if-exists "${scratch_db}" >/dev/null 2>&1 || true
  docker volume rm "${scratch_volume}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker volume inspect "${OXIGRAPH_VOLUME}" >/dev/null
docker compose exec -T db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc \
  > "${backup_dir}/postgres.dump"
docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -At \
  -c "SELECT table_schema||'.'||table_name||'='||(xpath('/row/c/text()',query_to_xml(format('SELECT count(*) c FROM %I.%I',table_schema,table_name),false,true,'')))[1]::text FROM information_schema.tables WHERE table_schema IN ('meta','raw','enriched','relations','vec','core') ORDER BY 1" \
  > "${backup_dir}/postgres-counts.txt"

docker compose stop graph >&2
graph_needs_restart=1
docker run --rm \
  -v "${OXIGRAPH_VOLUME}:/source:ro" \
  -v "${backup_dir}:/backup" \
  busybox:1.36 tar -C /source -czf /backup/oxigraph-volume.tgz .
docker compose up -d graph >&2
graph_needs_restart=0

printf '%s\n' "${OXIGRAPH_VOLUME}" > "${backup_dir}/oxigraph-volume-name.txt"
docker compose exec -T db pg_restore --list \
  < "${backup_dir}/postgres.dump" > "${backup_dir}/pg-restore-list.txt"
tar -tzf "${backup_dir}/oxigraph-volume.tgz" > "${backup_dir}/graph-tar-list.txt"

# Disposable PostgreSQL and Graph restores prove that both backups are readable.
docker compose exec -T db createdb -U "${POSTGRES_USER}" "${scratch_db}"
docker compose exec -T db pg_restore -U "${POSTGRES_USER}" -d "${scratch_db}" \
  --no-owner --no-privileges < "${backup_dir}/postgres.dump"
docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${scratch_db}" -At \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('meta','raw','enriched','relations','vec','core')" \
  > "${backup_dir}/postgres-restore-drill.txt"
if [ "$(tr -d '\r\n' < "${backup_dir}/postgres-restore-drill.txt")" = "0" ]; then
  echo "PostgreSQL restore drill produced no platform tables" >&2
  exit 1
fi
docker compose exec -T db dropdb -U "${POSTGRES_USER}" "${scratch_db}"

docker volume create "${scratch_volume}" >/dev/null
docker run --rm \
  -v "${scratch_volume}:/restore" \
  -v "${backup_dir}:/backup:ro" \
  busybox:1.36 tar -C /restore -xzf /backup/oxigraph-volume.tgz
docker run --rm -v "${scratch_volume}:/restore:ro" busybox:1.36 \
  sh -c 'test -n "$(find /restore -type f -print -quit)"'
docker volume rm "${scratch_volume}" >/dev/null

(
  cd -- "${backup_dir}"
  sha256sum postgres.dump oxigraph-volume.tgz postgres-counts.txt \
    oxigraph-volume-name.txt pg-restore-list.txt graph-tar-list.txt \
    postgres-restore-drill.txt > SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
)

trap - EXIT
printf '%s\n' "${backup_dir}"
