#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${OXIGRAPH_VOLUME:?OXIGRAPH_VOLUME must be the exact Docker volume name}"

if [[ $# -ne 1 || ! -f "$1/postgres.dump" || ! -f "$1/oxigraph-volume.tgz" || ! -f "$1/oxigraph-volume-name.txt" ]]; then
  echo "usage: $0 <validated-backup-directory>" >&2
  exit 2
fi
backup_dir="$(cd -- "$1" && pwd)"
docker volume inspect "${OXIGRAPH_VOLUME}" >/dev/null
recorded_volume="$(tr -d '\r\n' < "${backup_dir}/oxigraph-volume-name.txt")"
if [[ "${recorded_volume}" != "${OXIGRAPH_VOLUME}" ]]; then
  echo "backup volume ${recorded_volume} != requested ${OXIGRAPH_VOLUME}" >&2
  exit 2
fi

docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  < sql/v2/090_cutover.sql

rollback_on_error() {
  status=$?
  trap - ERR
  echo "cutover failed; restoring from ${backup_dir}" >&2
  ./deploy/rollback_v2.sh "${backup_dir}" || true
  exit "${status}"
}
trap rollback_on_error ERR

docker compose stop graph
docker compose rm -f graph
docker volume rm "${OXIGRAPH_VOLUME}"
docker compose create graph >/dev/null

for name in common bond_kr etf_kr etf_gl fund_pub; do
  docker compose run --rm --no-deps graph load --location /data \
    --file "/tbox/${name}.ttl" --graph "http://mafest.ai/graph/tbox/${name}"
done
for name in bond_kr etf_kr etf_gl fund_pub company; do
  docker compose run --rm --no-deps graph load --location /data \
    --file "/abox/instances_${name}.ttl" --graph "http://mafest.ai/graph/abox/${name}"
done
docker compose run --rm --no-deps graph optimize --location /data
docker compose up -d --build graph api

./deploy/verify_v2.sh
trap - ERR
printf '%s\n' "v2 cutover PASS; preserve ${backup_dir} and *_prev until team approval"
