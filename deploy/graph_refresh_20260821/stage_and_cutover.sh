#!/usr/bin/env bash
set -Eeuo pipefail

# Required environment:
#   BUNDLE_ID, ARCHIVE_SHA256, NEW_VOLUME
# Optional: BASE, PROJECT, IMAGE, CUTOVER (1/0)
BASE="${BASE:-/home/user1106/financial-agent-v2}"
PROJECT="${PROJECT:-financial-agent-prep}"
IMAGE="${IMAGE:-ghcr.io/oxigraph/oxigraph@sha256:e68b3625743db4a4b18129a907ae36766f89bb6deeb8ab50d35685dbabe00b0e}"
CUTOVER="${CUTOVER:-1}"
: "${BUNDLE_ID:?BUNDLE_ID is required}"
: "${ARCHIVE_SHA256:?ARCHIVE_SHA256 is required}"
: "${NEW_VOLUME:?NEW_VOLUME is required}"

INCOMING="${BASE}/incoming"
ARCHIVE="ontology-bundle-${BUNDLE_ID}.tar.gz"
ARCHIVE_PATH="${INCOMING}/${ARCHIVE}"
BUNDLE_ROOT="${BASE}/shared/data/ontology"
BUNDLE_DIR="${BUNDLE_ROOT}/${BUNDLE_ID}"
BACKUP_ROOT="${BASE}/shared/backups/graph-refresh-${BUNDLE_ID}"
LOCK_ROOT="${BASE}/shared/locks"
LOCK_FILE="${LOCK_ROOT}/graph-deployment.lock"
RUNTIME_ROOT="${BASE}/shared/runtime"
mkdir -p "${BUNDLE_ROOT}" "${BACKUP_ROOT}" "${LOCK_ROOT}" "${RUNTIME_ROOT}"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "REFUSE_LOCKED: another Graph deployment is active" >&2
  exit 3
fi

if [[ "${CUTOVER}" != "0" && "${CUTOVER}" != "1" ]]; then
  echo "REFUSE_CUTOVER: CUTOVER must be 0 or 1" >&2
  exit 2
fi
if [[ ! "${NEW_VOLUME}" =~ ^${PROJECT}_oxigraph-holdings-20260821-[0-9a-f]{8,16}$ ]]; then
  echo "REFUSE_VOLUME_NAME: ${NEW_VOLUME}" >&2
  exit 2
fi

temporary_root=""
cleanup() {
  if [[ -n "${temporary_root}" && -d "${temporary_root}" ]]; then
    rm -rf -- "${temporary_root}"
  fi
}
trap cleanup EXIT

validate_bundle() {
  local root="$1"
  python3 - "${root}" "${BUNDLE_ID}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
bundle_id = sys.argv[2]
expected = {
    "SOURCE_SHA256SUMS",
    "manifest.json",
    "abox/instances_bond_kr.ttl",
    "abox/instances_company.ttl",
    "abox/instances_etf_gl.ttl",
    "abox/instances_etf_kr.ttl",
    "abox/instances_fund_pub.ttl",
    "tbox/bond_kr.ttl",
    "tbox/common.ttl",
    "tbox/etf_gl.ttl",
    "tbox/etf_kr.ttl",
    "tbox/fund_pub.ttl",
}
actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
if actual != expected:
    raise SystemExit(f"REFUSE_FILE_SET: expected={sorted(expected)} actual={sorted(actual)}")
if any(path.is_symlink() for path in root.rglob("*")):
    raise SystemExit("REFUSE_SYMLINK")
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("bundle_id") != bundle_id:
    raise SystemExit(f"REFUSE_BUNDLE_ID: {manifest.get('bundle_id')} != {bundle_id}")
if manifest.get("mode") != "replace":
    raise SystemExit("REFUSE_MODE")
holdings = manifest.get("holdings", {})
if holdings.get("as_of") != "2026-08-21" or int(holdings.get("rows", 0)) <= 0:
    raise SystemExit(f"REFUSE_HOLDINGS: {holdings}")
if int(manifest.get("aggregates", {}).get("named_graphs", 0)) != 10:
    raise SystemExit("REFUSE_GRAPH_COUNT")
PY
  (
    cd "${root}"
    sha256sum -c SOURCE_SHA256SUMS
  )
}

test -f "${ARCHIVE_PATH}" || {
  echo "REFUSE_ARCHIVE_MISSING: ${ARCHIVE_PATH}" >&2
  exit 4
}
actual_archive_sha="$(sha256sum "${ARCHIVE_PATH}" | awk '{print $1}')"
if [[ "${actual_archive_sha}" != "${ARCHIVE_SHA256}" ]]; then
  echo "REFUSE_ARCHIVE_SHA: expected=${ARCHIVE_SHA256} actual=${actual_archive_sha}" >&2
  exit 4
fi
if [[ -e "${BUNDLE_DIR}" ]]; then
  echo "REFUSE_BUNDLE_EXISTS: ${BUNDLE_DIR}" >&2
  exit 5
fi
if docker volume inspect "${NEW_VOLUME}" >/dev/null 2>&1; then
  echo "REFUSE_VOLUME_EXISTS: ${NEW_VOLUME}" >&2
  exit 6
fi

temporary_root="$(mktemp -d "${INCOMING}/.holdings-graph.XXXXXX")"
tar -xzf "${ARCHIVE_PATH}" -C "${temporary_root}"
validate_bundle "${temporary_root}/ontology-bundle"
mv "${temporary_root}/ontology-bundle" "${BUNDLE_DIR}"
expected_graph_triples="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["aggregates"]["union_unique_triples"])' "${BUNDLE_DIR}/manifest.json")"
docker volume create "${NEW_VOLUME}" >/dev/null

load_one() {
  local file="$1"
  local graph="$2"
  docker run --rm \
    -v "${NEW_VOLUME}:/data" \
    -v "${file}:/source.ttl:ro" \
    "${IMAGE}" load --location /data --file /source.ttl --graph "${graph}"
}
query_csv() {
  local query="$1"
  docker run --rm -v "${NEW_VOLUME}:/data:ro" "${IMAGE}" query \
    --location /data --query "${query}" --results-format text/csv
}
query_union_csv() {
  local query="$1"
  docker run --rm -v "${NEW_VOLUME}:/data:ro" "${IMAGE}" query \
    --location /data --union-default-graph --query "${query}" --results-format text/csv
}

load_one "${BUNDLE_DIR}/tbox/common.ttl" "http://mafest.ai/graph/tbox/common"
load_one "${BUNDLE_DIR}/tbox/bond_kr.ttl" "http://mafest.ai/graph/tbox/bond_kr"
load_one "${BUNDLE_DIR}/tbox/etf_kr.ttl" "http://mafest.ai/graph/tbox/etf_kr"
load_one "${BUNDLE_DIR}/tbox/etf_gl.ttl" "http://mafest.ai/graph/tbox/etf_gl"
load_one "${BUNDLE_DIR}/tbox/fund_pub.ttl" "http://mafest.ai/graph/tbox/fund_pub"
load_one "${BUNDLE_DIR}/abox/instances_bond_kr.ttl" "http://mafest.ai/graph/abox/bond_kr"
load_one "${BUNDLE_DIR}/abox/instances_etf_kr.ttl" "http://mafest.ai/graph/abox/etf_kr"
load_one "${BUNDLE_DIR}/abox/instances_etf_gl.ttl" "http://mafest.ai/graph/abox/etf_gl"
load_one "${BUNDLE_DIR}/abox/instances_fund_pub.ttl" "http://mafest.ai/graph/abox/fund_pub"
load_one "${BUNDLE_DIR}/abox/instances_company.ttl" "http://mafest.ai/graph/abox/company"
docker run --rm -v "${NEW_VOLUME}:/data" "${IMAGE}" optimize --location /data

graphs_csv="${BACKUP_ROOT}/named-graphs-stage.csv"
default_csv="${BACKUP_ROOT}/default-graph-stage.csv"
union_csv="${BACKUP_ROOT}/union-default-stage.csv"
dates_csv="${BACKUP_ROOT}/holding-dates-stage.csv"
cambricon_csv="${BACKUP_ROOT}/cambricon-stage.csv"
query_csv "SELECT ?g (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g ORDER BY ?g" >"${graphs_csv}"
query_csv "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }" >"${default_csv}"
query_union_csv "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }" >"${union_csv}"
query_union_csv 'SELECT ?as_of (COUNT(*) AS ?holdings) WHERE { ?h a <http://mafest.ai/product#Holding> ; <http://mafest.ai/product#asOf> ?as_of . } GROUP BY ?as_of ORDER BY ?as_of' >"${dates_csv}"
query_union_csv 'SELECT ?product_code ?product_name ?security_name ?weight ?as_of WHERE { ?p <http://mafest.ai/product#hasHolding> ?h ; <http://mafest.ai/product#productCode> ?product_code ; <http://www.w3.org/2000/01/rdf-schema#label> ?product_name . ?h <http://mafest.ai/product#holdingSecurity> ?s ; <http://mafest.ai/product#asOf> ?as_of . OPTIONAL { ?h <http://mafest.ai/product#weight> ?weight } ?s <http://www.w3.org/2000/01/rdf-schema#label> ?security_name . FILTER(CONTAINS(LCASE(STR(?security_name)), "cambricon")) } ORDER BY ?product_code' >"${cambricon_csv}"

python3 - "${graphs_csv}" "${default_csv}" "${union_csv}" "${dates_csv}" "${BUNDLE_DIR}/manifest.json" <<'PY'
import csv
import json
import pathlib
import sys

graphs_path, default_path, union_path, dates_path, manifest_path = map(pathlib.Path, sys.argv[1:])
def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
graphs = {row["g"]: int(row["triples"]) for row in rows(graphs_path)}
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
expected = {item["named_graph"]: int(item["triples"]) for item in manifest["files"]}
if graphs != expected:
    raise SystemExit(f"REFUSE_REPLACE_COUNTS: expected={expected} actual={graphs}")
default_count = int(rows(default_path)[0]["triples"])
if default_count != 0:
    raise SystemExit(f"REFUSE_DEFAULT_GRAPH: {default_count}")
union_count = int(rows(union_path)[0]["triples"])
if union_count != int(manifest["aggregates"]["union_unique_triples"]):
    raise SystemExit(f"REFUSE_UNION: {union_count}")
dates = rows(dates_path)
expected_dates = [{"as_of": "2026-08-21", "holdings": str(manifest["holdings"]["rows"])}]
if dates != expected_dates:
    raise SystemExit(f"REFUSE_HOLDING_DATES: expected={expected_dates} actual={dates}")
PY

active_container="$(docker ps -q \
  --filter "label=com.docker.compose.project=${PROJECT}" \
  --filter 'label=com.docker.compose.service=graph' | head -n 1)"
test -n "${active_container}" || {
  echo "REFUSE_ACTIVE_GRAPH_NOT_FOUND" >&2
  exit 7
}
active_volume="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${active_container}")"
test -n "${active_volume}" || {
  echo "REFUSE_ACTIVE_VOLUME_NOT_FOUND" >&2
  exit 7
}
if [[ "${active_volume}" == "${NEW_VOLUME}" ]]; then
  echo "REFUSE_ALREADY_ACTIVE: ${NEW_VOLUME}" >&2
  exit 7
fi

# The old versioned volume is the immediate rollback copy and is never deleted.
docker volume inspect "${active_volume}" >"${BACKUP_ROOT}/active-volume-before.json"
printf '%s\n' "${active_volume}" >"${BACKUP_ROOT}/active-volume-before.txt"

active_api_container="$(docker ps -q \
  --filter "label=com.docker.compose.project=${PROJECT}" \
  --filter 'label=com.docker.compose.service=api' | head -n 1)"
test -n "${active_api_container}" || {
  echo "REFUSE_ACTIVE_API_NOT_FOUND" >&2
  exit 7
}
old_expected_graph_triples="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${active_api_container}" | sed -n 's/^EXPECTED_GRAPH_TRIPLES=//p' | tail -n 1)"
test -n "${old_expected_graph_triples}" || {
  echo "REFUSE_OLD_GRAPH_EXPECTATION_NOT_FOUND" >&2
  exit 7
}

if [[ "${CUTOVER}" == "0" ]]; then
  echo "GRAPH STAGE PASS: volume=${NEW_VOLUME} active_unchanged=${active_volume}"
  exit 0
fi

working_dir="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "${active_container}")"
config_files="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "${active_container}")"
test -n "${working_dir}" && test -n "${config_files}" || {
  echo "REFUSE_COMPOSE_LABELS_MISSING" >&2
  exit 8
}
env_path="${working_dir}/.env"
test -f "${env_path}" || {
  echo "REFUSE_ENV_MISSING: ${env_path}" >&2
  exit 8
}
env_backup="${BACKUP_ROOT}/runtime.env.before"
cp -p "${env_path}" "${env_backup}"
chmod 600 "${env_backup}"

write_pointer() {
  local path="$1"
  local volume="$2"
  local graph_triples="$3"
  python3 - "${path}" "${volume}" "${graph_triples}" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
volume = sys.argv[2]
graph_triples = sys.argv[3]
temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
temporary.write_text(
    "services:\n"
    "  graph:\n"
    "    volumes:\n"
    "      - graph-data:/data\n"
    "  api:\n"
    "    environment:\n"
    f"      EXPECTED_GRAPH_TRIPLES: \"{graph_triples}\"\n"
    "volumes:\n"
    "  graph-data:\n"
    "    external: true\n"
    f"    name: {volume}\n",
    encoding="utf-8",
)
temporary.replace(path)
PY
}

new_pointer="${RUNTIME_ROOT}/compose.graph-pointer-${BUNDLE_ID}.yaml"
rollback_pointer="${RUNTIME_ROOT}/compose.graph-pointer-rollback-${BUNDLE_ID}.yaml"
write_pointer "${new_pointer}" "${NEW_VOLUME}" "${expected_graph_triples}"
write_pointer "${rollback_pointer}" "${active_volume}" "${old_expected_graph_triples}"

compose_up() {
  local pointer="$1"
  local arguments=(--project-name "${PROJECT}")
  local file
  IFS=',' read -r -a files <<<"${config_files}"
  for file in "${files[@]}"; do
    arguments+=(-f "${file}")
  done
  arguments+=(-f "${pointer}")
  (cd "${working_dir}" && docker compose "${arguments[@]}" up -d --no-deps --force-recreate graph)
  (cd "${working_dir}" && docker compose "${arguments[@]}" up -d --no-deps --force-recreate api)
}

rollback() {
  echo "CUTOVER_FAILED: restoring ${active_volume}" >&2
  compose_up "${rollback_pointer}" || true
  if [[ -f "${env_backup}" ]]; then
    cp -p "${env_backup}" "${env_path}" || true
    chmod 600 "${env_path}" || true
  fi
}
trap rollback ERR
compose_up "${new_pointer}"

for _ in $(seq 1 30); do
  active_container="$(docker ps -q \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --filter 'label=com.docker.compose.service=graph' | head -n 1)"
  current_volume="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${active_container}" 2>/dev/null || true)"
  if [[ "${current_volume}" == "${NEW_VOLUME}" ]]; then
    break
  fi
  sleep 1
done
if [[ "${current_volume:-}" != "${NEW_VOLUME}" ]]; then
  echo "REFUSE_CUTOVER_POINTER: ${current_volume:-missing}" >&2
  false
fi

public_dates="${BACKUP_ROOT}/holding-dates-public.csv"
public_health="${BACKUP_ROOT}/health-public.json"
for _ in $(seq 1 30); do
  if curl -fsS --max-time 10 http://127.0.0.1:8000/health >"${public_health}" && \
    curl -fsS --max-time 10 -X POST -H 'Content-Type: text/plain; charset=utf-8' \
      --data 'SELECT ?as_of (COUNT(*) AS ?holdings) WHERE { ?h a <http://mafest.ai/product#Holding> ; <http://mafest.ai/product#asOf> ?as_of . } GROUP BY ?as_of ORDER BY ?as_of' \
      http://127.0.0.1:8000/db/sparql >"${public_dates}"; then
    break
  fi
  sleep 1
done
test -s "${public_dates}" || {
  echo "REFUSE_PUBLIC_QUERY" >&2
  false
}
python3 - "${public_dates}" "${public_health}" "${BUNDLE_DIR}/manifest.json" <<'PY'
import json
import pathlib
import sys

response_path, health_path, manifest_path = map(pathlib.Path, sys.argv[1:])
payload = json.loads(response_path.read_text(encoding="utf-8"))
health = json.loads(health_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
expected = [{"as_of": "2026-08-21", "holdings": str(manifest["holdings"]["rows"])}]
if payload.get("rows") != expected:
    raise SystemExit(f"REFUSE_PUBLIC_HOLDING_DATES: expected={expected} actual={payload}")
expected_triples = int(manifest["aggregates"]["union_unique_triples"])
if health.get("readiness") is not True or int(health.get("graph_triples", -1)) != expected_triples:
    raise SystemExit(f"REFUSE_PUBLIC_HEALTH: expected_triples={expected_triples} actual={health}")
PY

python3 - "${env_path}" "${NEW_VOLUME}" "${expected_graph_triples}" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
updates = {
    "OXIGRAPH_ACTIVE_VOLUME": sys.argv[2],
    "EXPECTED_GRAPH_TRIPLES": sys.argv[3],
}
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
output = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else ""
    if key in updates:
        output.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        output.append(line)
for key, value in updates.items():
    if key not in seen:
        output.append(f"{key}={value}")
temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
temporary.replace(path)
PY

trap - ERR
BUNDLE_ID="${BUNDLE_ID}" NEW_VOLUME="${NEW_VOLUME}" ACTIVE_VOLUME="${active_volume}" \
OLD_EXPECTED_GRAPH_TRIPLES="${old_expected_graph_triples}" \
ARCHIVE_SHA256="${ARCHIVE_SHA256}" python3 - "${BUNDLE_DIR}/manifest.json" "${BACKUP_ROOT}/cutover-receipt.json" <<'PY'
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

manifest_path, receipt_path = map(pathlib.Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
receipt = {
    "status": "cutover_passed",
    "cutover_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "bundle_id": os.environ["BUNDLE_ID"],
    "bundle_archive_sha256": os.environ["ARCHIVE_SHA256"],
    "active_volume_before_retained": os.environ["ACTIVE_VOLUME"],
    "active_volume_after": os.environ["NEW_VOLUME"],
    "rollback_volume": os.environ["ACTIVE_VOLUME"],
    "rollback_expected_graph_triples": int(os.environ["OLD_EXPECTED_GRAPH_TRIPLES"]),
    "holdings": manifest["holdings"],
    "aggregates": manifest["aggregates"],
}
temporary = receipt_path.with_name(receipt_path.name + ".tmp")
temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(receipt_path)
print(json.dumps(receipt, ensure_ascii=False))
PY
echo "GRAPH CUTOVER PASS: previous=${active_volume} active=${NEW_VOLUME} rollback=retained"
