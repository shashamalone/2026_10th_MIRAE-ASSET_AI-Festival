#!/usr/bin/env bash
set -Eeuo pipefail

release_sha=${1:-}
public_expires_at=${2:-}
access_mode=${3:-curated}
team_db_ack=${4:-}
base=/home/user1106/financial-agent-v2
incoming=${base}/incoming
release_dir=${base}/releases/${release_sha}
source_release=${base}/releases/57c4edc96bd5cebe7703bb717480b0ebd935b39d
archive=${incoming}/financial-agent-data-api-${release_sha}.tar.gz
expected_release=financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38
expected_graph=financial-agent-prep_oxigraph-next-2026-08-24-57c4edc

if [[ ! ${release_sha} =~ ^[0-9a-f]{40}$ ]]; then
  echo "REFUSE_SHA: ${release_sha:-unset}" >&2
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
if parsed.tzinfo is None or parsed.astimezone(timezone.utc) <= datetime.now(timezone.utc):
    raise SystemExit("REFUSE_EXPIRY: a future timezone-aware timestamp is required")
if (parsed.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds() > 30 * 24 * 60 * 60:
    raise SystemExit("REFUSE_EXPIRY: public test exposure cannot exceed 30 days")
PY
case "${access_mode}" in
  curated) ;;
  team-db)
    test "${team_db_ack}" = I_ACCEPT_TEMPORARY_GUARDED_READ_ONLY_DB || {
      echo "REFUSE_TEAM_DB_ACK: exact acknowledgement is required" >&2
      exit 2
    }
    ;;
  *) echo "REFUSE_ACCESS_MODE: ${access_mode}" >&2; exit 2 ;;
esac
test -s "${archive}"
test -f "${source_release}/.env"
test "$(stat -c '%a' "${source_release}/.env")" = 600

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

python3 - "${release_dir}/.env" "${public_expires_at}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
values = {
    "PUBLIC_TEST_EXPIRES_AT": sys.argv[2],
    "PUBLIC_RATE_LIMIT_PER_MINUTE": "60",
    "API_MAX_BODY_BYTES": "1048576",
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
for key in ("COMPOSE_PROJECT_NAME", "POSTGRES_USER", "POSTGRES_DB", "OXIGRAPH_ACTIVE_VOLUME"):
    value = values.get(key, "")
    if not value:
        raise SystemExit(f"ENV_FAIL: {key}")
    print(value)
PY
)
project=${settings[0]}
postgres_user=${settings[1]}
postgres_db=${settings[2]}
active_graph=${settings[3]}
test "${project}" = financial-agent-prep
test "${active_graph}" = "${expected_graph}"
test "$(stat -c '%a' .env)" = 600

health_file=$(mktemp)
trap 'rm -f -- "${health_file}"' EXIT
curl --fail --silent --show-error http://127.0.0.1:8000/health >"${health_file}"
EXPECTED_RELEASE="${expected_release}" python3 - "${health_file}" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream)
expected = os.environ["EXPECTED_RELEASE"]
assert value["status"] == "ok" and value["readiness"] is True, value
assert value["rdb"]["release_id"] == value["graph"]["release_id"] == expected, value
PY

psql_at=(docker compose --project-name "${project}" exec -T db psql -U "${postgres_user}" -d "${postgres_db}" -At -v ON_ERROR_STOP=1 -c)
test "$("${psql_at[@]}" "SELECT (SELECT count(*) FROM raw.bond_kr_master)+(SELECT count(*) FROM raw.etf_kr_master)+(SELECT count(*) FROM raw.etf_gl_master)+(SELECT count(*) FROM raw.fund_pub_master)")" = 53375
test "$("${psql_at[@]}" "SELECT count(*) FROM relations.product_holding")" = 46951
test "$("${psql_at[@]}" "SELECT count(*) FROM relations.company_subsidiary")" = 8866
graph_id=$(docker compose --project-name "${project}" ps -q graph)
test -n "${graph_id}"
test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${graph_id}")" = "${active_graph}"

export COMPOSE_PROJECT_NAME="${project}"
export POSTGRES_USER="${postgres_user}"
export POSTGRES_DB="${postgres_db}"
export OXIGRAPH_ACTIVE_VOLUME="${active_graph}"
export PUBLIC_TEST_EXPIRES_AT="${public_expires_at}"
export V2_CUTOVER_CONFIRMED=V2_RELEASE_IS_ACTIVE
if [[ "${access_mode}" == team-db ]]; then
  export TEAM_DB_PUBLIC_MODE=1
  export TEAM_DB_PUBLIC_ACK=I_ACCEPT_TEMPORARY_GUARDED_READ_ONLY_DB
else
  export TEAM_DB_PUBLIC_MODE=0
  unset TEAM_DB_PUBLIC_ACK || true
fi
bash deploy/data_api_v1/deploy_public_test.sh

version_file=$(mktemp)
curl --fail --silent --show-error http://127.0.0.1:8000/v1/release >"${version_file}"
EXPECTED_RELEASE="${expected_release}" python3 - "${version_file}" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream)
assert value["release_id"] == os.environ["EXPECTED_RELEASE"], value
PY
rm -f -- "${version_file}"
raw_status=$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8000/db/version)
if [[ "${access_mode}" == team-db ]]; then
  test "${raw_status}" = 200
else
  test "${raw_status}" = 404
fi
printf '%s\n' "${release_dir}" >"${base}/shared/backups/latest-curated-data-api-release.txt"
printf 'VM DATA API PASS: release=%s source=%s graph=%s public_expires_at=%s raw_db=%s\n' \
  "${expected_release}" "${release_sha}" "${active_graph}" "${public_expires_at}" "${access_mode}"
