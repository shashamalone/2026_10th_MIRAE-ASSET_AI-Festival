#!/usr/bin/env bash
set -Eeuo pipefail

release_sha=${1:?release sha required}
expected_graph_triples=${2:?expected graph triples required}
expected_release=financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38
base=/home/user1106/financial-agent-v2
incoming=${base}/incoming
release_dir=${base}/releases/${release_sha}
archive=${incoming}/financial-agent-api-only-${release_sha}.tar.gz
checksums=${incoming}/financial-agent-api-only-${release_sha}-SHA256SUMS
pointer=${base}/shared/backups/latest-raw-query-api-release.txt
pre_health=
rollback_health=
pointer_tmp=

cleanup() {
  test -z "${pre_health}" || rm -f -- "${pre_health}"
  test -z "${rollback_health}" || rm -f -- "${rollback_health}"
  test -z "${pointer_tmp}" || rm -f -- "${pointer_tmp}"
}
trap cleanup EXIT

[[ ${release_sha} =~ ^[0-9a-f]{40}$ ]] || {
  echo "API_ONLY_REFUSE_SHA: ${release_sha}" >&2
  exit 2
}
test "${expected_graph_triples}" = 1226698 || {
  echo "API_ONLY_REFUSE_GRAPH: ${expected_graph_triples}" >&2
  exit 2
}
test -s "${archive}"
test -s "${checksums}"
cd "${incoming}"
sha256sum -c "${checksums}"

test -s "${pointer}"
pointer_value=$(tr -d '\r\n' <"${pointer}")
current_release=$(realpath -e -- "${pointer_value}")
case "${current_release}" in
  "${base}/releases/"*) ;;
  *) echo "API_ONLY_REFUSE_POINTER: ${current_release}" >&2; exit 2 ;;
esac
test -f "${current_release}/.env"
test "$(stat -c '%a' "${current_release}/.env")" = 600

release_marker=${release_dir}/.api-only-source-commit
if [[ -d ${release_dir} && -n $(find "${release_dir}" -mindepth 1 -print -quit) ]]; then
  test -f "${release_marker}"
  test "$(tr -d '\r\n' <"${release_marker}")" = "${release_sha}"
else
  mkdir -p "${release_dir}"
  tar -xzf "${archive}" -C "${release_dir}" --strip-components=1
  printf '%s\n' "${release_sha}" >"${release_marker}"
fi
cp -p "${current_release}/.env" "${release_dir}/.env"
chmod 600 "${release_dir}/.env"

pre_health=$(mktemp)
curl --fail --silent --show-error http://127.0.0.1:8000/health >"${pre_health}"
python3 - "${pre_health}" "${expected_release}" "${expected_graph_triples}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    health = json.load(stream)
if health.get("release_id") != sys.argv[2]:
    raise SystemExit("API_ONLY_REFUSE_PRE_HEALTH: release")
if int((health.get("graph") or {}).get("triples") or 0) != int(sys.argv[3]):
    raise SystemExit("API_ONLY_REFUSE_PRE_HEALTH: graph")
PY

set -a
source "${release_dir}/.env"
set +a
: "${COMPOSE_PROJECT_NAME:?COMPOSE_PROJECT_NAME required}"
: "${OXIGRAPH_ACTIVE_VOLUME:?OXIGRAPH_ACTIVE_VOLUME required}"
: "${PUBLIC_TEST_EXPIRES_AT:?PUBLIC_TEST_EXPIRES_AT required}"
: "${CLOVA_API_KEY:?CLOVA_API_KEY required for answer pipeline}"
test "${COMPOSE_PROJECT_NAME}" = financial-agent-prep
test "${EXPECTED_GRAPH_TRIPLES:-}" = "${expected_graph_triples}"
docker volume inspect "${OXIGRAPH_ACTIVE_VOLUME}" >/dev/null

compose_release() {
  local owned_release=$1
  shift
  docker compose \
    --env-file "${owned_release}/.env" \
    --project-name "${COMPOSE_PROJECT_NAME}" \
    -f "${owned_release}/compose.yaml" \
    -f "${owned_release}/deploy/compose.graph-pointer.yaml" \
    -f "${owned_release}/deploy/data_api_v1/compose.graph-union-default.yaml" \
    -f "${owned_release}/deploy/data_api_v1/compose.public-test.yaml" \
    "$@"
}

compose_release "${current_release}" config >/dev/null
compose_release "${release_dir}" config >/dev/null
old_api_container=$(compose_release "${current_release}" ps -q api)
old_db_container=$(compose_release "${current_release}" ps -q db)
old_graph_container=$(compose_release "${current_release}" ps -q graph)
test -n "${old_api_container}"
test -n "${old_db_container}"
test -n "${old_graph_container}"
old_api_image=$(docker inspect --format '{{.Image}}' "${old_api_container}")
test -n "${old_api_image}"
docker image inspect "${old_api_image}" >/dev/null
api_image=${COMPOSE_PROJECT_NAME}-api:latest

rollback() {
  code=$?
  trap - ERR
  set +e
  echo "API_ONLY_FAIL: restoring previous release ${current_release} image ${old_api_image}" >&2
  docker image tag "${old_api_image}" "${api_image}"
  compose_release "${current_release}" up -d --no-deps --no-build api
  rollback_compose_code=$?
  rollback_health=$(mktemp)
  rollback_ready=1
  if [[ ${rollback_compose_code} -eq 0 ]]; then
    for _attempt in $(seq 1 30); do
      if curl --fail --silent http://127.0.0.1:8000/health >"${rollback_health}" && \
        python3 - "${rollback_health}" "${expected_release}" "${expected_graph_triples}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    health = json.load(stream)
ok = (
    health.get("release_id") == sys.argv[2]
    and int((health.get("graph") or {}).get("triples") or 0) == int(sys.argv[3])
)
raise SystemExit(0 if ok else 1)
PY
      then
        rollback_ready=0
        break
      fi
      sleep 2
    done
  fi
  if [[ ${rollback_compose_code} -ne 0 || ${rollback_ready} -ne 0 ]]; then
    echo "API_ONLY_ROLLBACK_HEALTH_FAIL: manual recovery required" >&2
  else
    echo "API_ONLY_ROLLBACK_PASS: previous API restored" >&2
  fi
  exit "${code}"
}
trap rollback ERR

compose_release "${release_dir}" build api
compose_release "${release_dir}" up -d --no-deps api
test "$(compose_release "${release_dir}" ps -q db)" = "${old_db_container}"
test "$(compose_release "${release_dir}" ps -q graph)" = "${old_graph_container}"
python3 "${release_dir}/deploy/data_api_v1/verify_public_api.py" \
  --url http://127.0.0.1:8000 \
  --expected-graph-triples "${expected_graph_triples}"

pointer_tmp=$(mktemp "${pointer}.tmp.XXXXXX")
printf '%s\n' "${release_dir}" >"${pointer_tmp}"
mv -f -- "${pointer_tmp}" "${pointer}"
pointer_tmp=
trap - ERR
echo "API_ONLY_PASS: release=${release_sha} graph=${expected_graph_triples} db=unchanged graph_service=unchanged"
