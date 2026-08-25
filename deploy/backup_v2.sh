#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${OXIGRAPH_VOLUME:?OXIGRAPH_VOLUME must be the exact Docker volume name}"

backup_root="${BACKUP_ROOT:-${PWD}/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${backup_root}/data-platform-v2-${timestamp}"
mkdir -p -- "${backup_dir}"

docker volume inspect "${OXIGRAPH_VOLUME}" >/dev/null
docker compose exec -T db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc \
  > "${backup_dir}/postgres.dump"
docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -At \
  -c "SELECT table_schema||'.'||table_name||'='||(xpath('/row/c/text()',query_to_xml(format('SELECT count(*) c FROM %I.%I',table_schema,table_name),false,true,'')))[1]::text FROM information_schema.tables WHERE table_schema IN ('meta','raw','enriched','relations','vec','core') ORDER BY 1" \
  > "${backup_dir}/postgres-counts.txt"

docker compose stop graph
docker run --rm \
  -v "${OXIGRAPH_VOLUME}:/source:ro" \
  -v "${backup_dir}:/backup" \
  busybox:1.36 tar -C /source -czf /backup/oxigraph-volume.tgz .
docker compose up -d graph

printf '%s\n' "${OXIGRAPH_VOLUME}" > "${backup_dir}/oxigraph-volume-name.txt"
if [[ -f .env ]]; then
  cp -- .env "${backup_dir}/runtime.env"
  chmod 600 "${backup_dir}/runtime.env"
fi
printf '%s\n' "${backup_dir}"
