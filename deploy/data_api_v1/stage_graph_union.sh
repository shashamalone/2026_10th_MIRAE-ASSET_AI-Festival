#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/home/user1106/financial-agent-v2}"
INCOMING="${BASE}/incoming"
BUNDLE_ID="ontology-20260831-00b5466f9463"
ARCHIVE="ontology-bundle-${BUNDLE_ID}.tar.gz"
ARCHIVE_SHA256="d89543a8c65598e3439926c43df08b127b2c260e658ba7835d54564525938e98"
IMAGE="ghcr.io/oxigraph/oxigraph@sha256:e68b3625743db4a4b18129a907ae36766f89bb6deeb8ab50d35685dbabe00b0e"
PROJECT="financial-agent-prep"
MODE="${GRAPH_LOAD_MODE:-augment}"
EXPECTED_AUGMENT_UNION_TRIPLES=1628311
V2_RELEASE="${V2_RELEASE:-${BASE}/releases/57c4edc96bd5cebe7703bb717480b0ebd935b39d}"
BUNDLE_ROOT="${BASE}/shared/data/ontology"
BUNDLE_DIR="${BUNDLE_ROOT}/${BUNDLE_ID}"
NEW_VOLUME="${NEW_VOLUME:-${PROJECT}_oxigraph-ontology-20260831-00b5466f}"
RECEIPT_ROOT="${BASE}/shared/backups/graph-source-${BUNDLE_ID}"
LOCK_ROOT="${BASE}/shared/locks"
LOCK_FILE="${LOCK_ROOT}/graph-deployment.lock"

if [[ "${MODE}" != "augment" && "${MODE}" != "replace" ]]; then
  echo "REFUSE_MODE: GRAPH_LOAD_MODE must be augment or replace" >&2
  exit 2
fi

mkdir -p "${BUNDLE_ROOT}" "${RECEIPT_ROOT}" "${LOCK_ROOT}"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "REFUSE_LOCKED: another Graph deployment is active" >&2
  exit 3
fi

archive_path="${INCOMING}/${ARCHIVE}"
test -f "${archive_path}"
actual_archive_sha="$(sha256sum "${archive_path}" | awk '{print $1}')"
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

tmp_root="$(mktemp -d "${INCOMING}/.graph-bundle.XXXXXX")"
cleanup() {
  rm -rf -- "${tmp_root}"
}
trap cleanup EXIT

tar -xzf "${archive_path}" -C "${tmp_root}"
extracted="${tmp_root}/ontology-bundle"
test -d "${extracted}/tbox"
test -d "${extracted}/abox"
test -f "${extracted}/manifest.json"
test -f "${extracted}/SOURCE_SHA256SUMS"

python3 - "${extracted}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
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
actual = {
    path.relative_to(root).as_posix()
    for path in root.rglob("*")
    if path.is_file()
}
if actual != expected:
    raise SystemExit(f"REFUSE_FILE_SET: expected={sorted(expected)} actual={sorted(actual)}")
if any(path.is_symlink() for path in root.rglob("*")):
    raise SystemExit("REFUSE_SYMLINK")
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("bundle_id") != "ontology-20260831-00b5466f9463":
    raise SystemExit("REFUSE_BUNDLE_ID")
if manifest.get("aggregates") != {
    "abox_triples": 1166833,
    "tbox_triples": 2541,
    "named_graph_quads": 1169374,
    "union_unique_triples": 1169374,
    "default_graph_triples": 0,
    "named_graphs": 10,
}:
    raise SystemExit("REFUSE_MANIFEST_AGGREGATES")
if {item["path"] for item in manifest["files"]} != expected - {"SOURCE_SHA256SUMS", "manifest.json"}:
    raise SystemExit("REFUSE_MANIFEST_PATHS")
PY
(
  cd "${extracted}"
  sha256sum -c SOURCE_SHA256SUMS
)
mv "${extracted}" "${BUNDLE_DIR}"

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

if [[ "${MODE}" == "augment" ]]; then
  test -d "${V2_RELEASE}/ontology"
  test -d "${V2_RELEASE}/artifacts/graph_v2"
  for name in common bond_kr etf_kr etf_gl fund_pub; do
    test -f "${V2_RELEASE}/ontology/${name}.ttl"
    load_one "${V2_RELEASE}/ontology/${name}.ttl" "http://mafest.ai/graph/tbox/${name}"
  done
  for name in bond_kr etf_kr etf_gl fund_pub company; do
    test -f "${V2_RELEASE}/artifacts/graph_v2/instances_${name}.ttl"
    load_one "${V2_RELEASE}/artifacts/graph_v2/instances_${name}.ttl" "http://mafest.ai/graph/abox/${name}"
  done
  base_abox="$(query_csv "SELECT (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } FILTER(STRSTARTS(STR(?g), 'http://mafest.ai/graph/abox/')) }" | tail -n 1 | tr -d '\r"')"
  if [[ "${base_abox}" != "655388" ]]; then
    echo "REFUSE_BASE_ABOX: expected=655388 actual=${base_abox}" >&2
    exit 7
  fi
fi

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

graphs_csv="${RECEIPT_ROOT}/named-graphs-${MODE}.csv"
query_csv "SELECT ?g (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g ORDER BY ?g" >"${graphs_csv}"
default_csv="${RECEIPT_ROOT}/default-graph-${MODE}.csv"
query_csv "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }" >"${default_csv}"
union_csv="${RECEIPT_ROOT}/union-default-${MODE}.csv"
query_union_csv "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }" >"${union_csv}"

NEW_VOLUME="${NEW_VOLUME}" MODE="${MODE}" BUNDLE_ID="${BUNDLE_ID}" \
  ARCHIVE_SHA256="${ARCHIVE_SHA256}" IMAGE="${IMAGE}" \
  EXPECTED_AUGMENT_UNION_TRIPLES="${EXPECTED_AUGMENT_UNION_TRIPLES}" \
  python3 - "${graphs_csv}" "${default_csv}" "${union_csv}" "${BUNDLE_DIR}/manifest.json" \
  "${RECEIPT_ROOT}/stage-${MODE}.json" <<'PY'
import csv
import json
import os
import pathlib
import sys

graphs_path, default_path, union_path, manifest_path, receipt_path = map(pathlib.Path, sys.argv[1:])
with graphs_path.open(encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))
graphs = {row["g"]: int(row["triples"]) for row in rows}
expected_graphs = {
    "http://mafest.ai/graph/abox/bond_kr",
    "http://mafest.ai/graph/abox/company",
    "http://mafest.ai/graph/abox/etf_gl",
    "http://mafest.ai/graph/abox/etf_kr",
    "http://mafest.ai/graph/abox/fund_pub",
    "http://mafest.ai/graph/tbox/bond_kr",
    "http://mafest.ai/graph/tbox/common",
    "http://mafest.ai/graph/tbox/etf_gl",
    "http://mafest.ai/graph/tbox/etf_kr",
    "http://mafest.ai/graph/tbox/fund_pub",
}
if set(graphs) != expected_graphs:
    raise SystemExit(f"REFUSE_GRAPH_SET: {sorted(graphs)}")
with default_path.open(encoding="utf-8-sig", newline="") as handle:
    default_rows = list(csv.DictReader(handle))
default_count = int(default_rows[0]["triples"])
if default_count != 0:
    raise SystemExit(f"REFUSE_DEFAULT_GRAPH: {default_count}")
with union_path.open(encoding="utf-8-sig", newline="") as handle:
    union_rows = list(csv.DictReader(handle))
union_count = int(union_rows[0]["triples"])
mode = os.environ["MODE"]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if mode == "replace":
    expected = {item["named_graph"]: int(item["triples"]) for item in manifest["files"]}
    if graphs != expected:
        raise SystemExit(f"REFUSE_REPLACE_COUNTS: expected={expected} actual={graphs}")
    expected_union = int(manifest["aggregates"]["union_unique_triples"])
else:
    expected_union = int(os.environ["EXPECTED_AUGMENT_UNION_TRIPLES"])
if union_count != expected_union:
    raise SystemExit(f"REFUSE_UNION_COUNT: expected={expected_union} actual={union_count}")
abox = sum(value for graph, value in graphs.items() if "/abox/" in graph)
tbox = sum(value for graph, value in graphs.items() if "/tbox/" in graph)
receipt = {
    "status": "staged",
    "cutover": "not-run",
    "mode": mode,
    "bundle_id": os.environ["BUNDLE_ID"],
    "bundle_archive_sha256": os.environ["ARCHIVE_SHA256"],
    "oxigraph_image": os.environ["IMAGE"],
    "volume": os.environ["NEW_VOLUME"],
    "graphs": graphs,
    "abox_triples": abox,
    "tbox_triples": tbox,
    "named_graph_quads": abox + tbox,
    "default_graph_triples": default_count,
    "union_default_triples": union_count,
}
receipt_path.write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(
    f"GRAPH STAGE PASS: mode={mode} volume={receipt['volume']} "
    f"abox={abox} tbox={tbox} total={abox + tbox} default={default_count} "
    f"union_default={union_count} "
    "cutover=not-run"
)
PY
