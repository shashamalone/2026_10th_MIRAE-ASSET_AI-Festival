#!/usr/bin/env bash
set -Eeuo pipefail

release_sha=${1:-}
public_expires_at=${2:-}
active_graph=${3:-financial-agent-prep_oxigraph-ontology-20260831-00b5466f}
vector_handoff=${4:-}
base=/home/user1106/financial-agent-v2
incoming=${base}/incoming
release_dir=${base}/releases/${release_sha}
source_release=${base}/releases/57c4edc96bd5cebe7703bb717480b0ebd935b39d
archive=${incoming}/financial-agent-data-api-${release_sha}.tar.gz
expected_release=financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38
expected_graph_triples=1628311
expected_graph=financial-agent-prep_oxigraph-ontology-20260831-00b5466f
graph_receipt=${base}/shared/backups/graph-source-ontology-20260831-00b5466f9463/stage-augment.json

if [[ ! ${release_sha} =~ ^[0-9a-f]{40}$ ]]; then
  echo "REFUSE_SHA: ${release_sha:-unset}" >&2
  exit 2
fi
if [[ "${vector_handoff}" != "INVESTMENT_REPORT_VECTOR_ACTIVE" ]]; then
  echo "REFUSE_VECTOR_HANDOFF: Vector DB deployment handoff is required" >&2
  exit 2
fi
if [[ "${active_graph}" != "${expected_graph}" ]]; then
  echo "REFUSE_GRAPH_VOLUME: expected=${expected_graph} actual=${active_graph}" >&2
  exit 2
fi
python3 - "${public_expires_at}" <<'PY'
from datetime import datetime, timezone
import sys

value = sys.argv[1]
try:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
except ValueError as exc:
    raise SystemExit(f"REFUSE_EXPIRY: {exc}")
now = datetime.now(timezone.utc)
if parsed.tzinfo is None or parsed.astimezone(timezone.utc) <= now:
    raise SystemExit("REFUSE_EXPIRY: a future timezone-aware timestamp is required")
if (parsed.astimezone(timezone.utc) - now).total_seconds() > 30 * 24 * 60 * 60:
    raise SystemExit("REFUSE_EXPIRY: public test exposure cannot exceed 30 days")
PY

test -s "${archive}"
test -f "${source_release}/.env"
test "$(stat -c '%a' "${source_release}/.env")" = 600
test -f "${graph_receipt}"
docker volume inspect "${active_graph}" >/dev/null
python3 - "${graph_receipt}" "${active_graph}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    receipt = json.load(stream)
assert receipt["status"] == "staged", receipt
assert receipt["cutover"] == "not-run", receipt
assert receipt["mode"] == "augment", receipt
assert receipt["volume"] == sys.argv[2], receipt
assert receipt["union_default_triples"] == 1_628_311, receipt
PY

release_marker=${release_dir}/.source-commit
if [[ -d ${release_dir} && -n $(find "${release_dir}" -mindepth 1 -print -quit) ]]; then
  if [[ ! -f ${release_marker} || $(tr -d '\r\n' <"${release_marker}") != "${release_sha}" ]]; then
    echo "REFUSE_NONEMPTY: ${release_dir}" >&2
    exit 2
  fi
  test -x "${release_dir}/deploy/data_api_v1/deploy_public_test.sh"
else
  mkdir -p "${release_dir}"
  tar -xzf "${archive}" -C "${release_dir}" --strip-components=1
  printf '%s\n' "${release_sha}" >"${release_marker}"
fi
cp -p "${source_release}/.env" "${release_dir}/.env"
chmod 600 "${release_dir}/.env"

python3 - "${release_dir}/.env" "${public_expires_at}" "${active_graph}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
values = {
    "PUBLIC_TEST_EXPIRES_AT": sys.argv[2],
    "PUBLIC_RATE_LIMIT_PER_MINUTE": "60",
    "API_MAX_BODY_BYTES": "1048576",
    "EXPECTED_GRAPH_TRIPLES": "1628311",
    "OXIGRAPH_ACTIVE_VOLUME": sys.argv[3],
}
output = []
seen = set()
for line in path.read_text(encoding="utf-8").splitlines():
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
    if match and match.group(1) in values:
        key = match.group(1)
        output.append(f"{key}={values[key]}")
        seen.add(key)
    else:
        output.append(line)
for key, value in values.items():
    if key not in seen:
        output.append(f"{key}={value}")
temporary = path.with_name(path.name + ".install-tmp")
temporary.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")
temporary.chmod(0o600)
temporary.replace(path)
PY

cd "${release_dir}"
mapfile -t settings < <(python3 - .env <<'PY'
from pathlib import Path
import shlex
import sys

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key, value = key.strip(), value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        parsed = shlex.split(value, posix=True)
        value = parsed[0] if parsed else ""
    values[key] = value
for key in (
    "COMPOSE_PROJECT_NAME",
    "POSTGRES_USER",
    "POSTGRES_DB",
    "OXIGRAPH_ACTIVE_VOLUME",
):
    value = values.get(key, "")
    if not value:
        raise SystemExit(f"ENV_FAIL: {key}")
    print(value)
PY
)
project=${settings[0]}
postgres_user=${settings[1]}
postgres_db=${settings[2]}
env_graph=${settings[3]}
test "${project}" = financial-agent-prep
test "${env_graph}" = "${active_graph}"
test "$(stat -c '%a' .env)" = 600

psql_at=(docker compose --project-name "${project}" exec -T db psql -U "${postgres_user}" -d "${postgres_db}" -At -v ON_ERROR_STOP=1 -c)
test "$("${psql_at[@]}" "SELECT (SELECT count(*) FROM raw.bond_kr_master)+(SELECT count(*) FROM raw.etf_kr_master)+(SELECT count(*) FROM raw.etf_gl_master)+(SELECT count(*) FROM raw.fund_pub_master)")" = 53375
test "$("${psql_at[@]}" "SELECT count(*) FROM relations.product_holding")" = 46951
test "$("${psql_at[@]}" "SELECT count(*) FROM relations.company_subsidiary")" = 8866

export COMPOSE_PROJECT_NAME="${project}"
export POSTGRES_USER="${postgres_user}"
export POSTGRES_DB="${postgres_db}"
export OXIGRAPH_ACTIVE_VOLUME="${active_graph}"
export EXPECTED_GRAPH_TRIPLES="${expected_graph_triples}"
export PUBLIC_TEST_EXPIRES_AT="${public_expires_at}"
export V2_CUTOVER_CONFIRMED=V2_RELEASE_IS_ACTIVE
export GRAPH_CUTOVER_CONFIRMED=GRAPH_1628311_IS_ACTIVE

current_graph_id=$(docker compose --project-name "${project}" ps -q graph)
test -n "${current_graph_id}"
old_graph=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${current_graph_id}")
test -n "${old_graph}"
restore_graph() {
  code=$?
  if [[ ${code} -eq 0 ]]; then
    return
  fi
  echo "INSTALL FAIL: restoring previous Graph volume ${old_graph:-unknown}" >&2
  if [[ -n "${old_graph}" ]]; then
    (
      cd "${source_release}"
      OXIGRAPH_ACTIVE_VOLUME="${old_graph}" docker compose \
        --project-name "${project}" \
        -f compose.yaml \
        -f deploy/compose.graph-pointer.yaml \
        up -d --no-deps graph
    ) || true
  fi
  exit "${code}"
}
trap restore_graph ERR

bash deploy/data_api_v1/deploy_public_test.sh
trap - ERR

version_file=$(mktemp)
health_file=$(mktemp)
trap 'rm -f -- "'"${version_file}"'" "'"${health_file}"'"' EXIT
curl --fail --silent --show-error http://127.0.0.1:8000/db/version >"${version_file}"
curl --fail --silent --show-error http://127.0.0.1:8000/health >"${health_file}"
EXPECTED_RELEASE="${expected_release}" python3 - "${version_file}" "${health_file}" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    version = json.load(stream)
with open(sys.argv[2], encoding="utf-8") as stream:
    health = json.load(stream)
assert version["rows"][0]["release_id"] == os.environ["EXPECTED_RELEASE"], version
assert health["status"] == "ok" and health["readiness"] is True, health
assert health["graph"]["triples"] == 1_628_311, health
PY

pointer=${base}/shared/backups/latest-raw-query-api-release.txt
printf '%s\n' "${release_dir}" >"${pointer}"
printf 'VM RAW QUERY API PASS: release=%s source=%s graph=%s triples=%s expires=%s\n' \
  "${expected_release}" "${release_sha}" "${active_graph}" \
  "${expected_graph_triples}" "${public_expires_at}"
