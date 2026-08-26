#!/usr/bin/env bash
set -euo pipefail

mode="${1:---cutover}"
if [[ "${mode}" != "--cutover" && "${mode}" != "--rollback" ]]; then
  echo "usage: $0 [--cutover|--rollback]" >&2
  exit 2
fi
: "${AGENT_QUERY_URL:?AGENT_QUERY_URL is mandatory for 35-case live regression}"

api_url="${API_URL:-http://127.0.0.1:${API_PORT:-8000}}"
expected_release="${EXPECTED_RELEASE_ID:-financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38}"
health="$(curl --fail --silent --show-error "${api_url}/health")"
VERIFY_MODE="${mode}" EXPECTED_RELEASE_ID="${expected_release}" python3 -c '
import json,os,sys
h=json.load(sys.stdin)
assert h["rdb"]["snapshot_hash"] == h["graph"]["snapshot_hash"], h
assert h["rdb"]["release_id"] == h["graph"]["release_id"], h
assert h["vector_status"] in {"pending", "ready"}, h
if os.environ["VERIFY_MODE"] == "--cutover":
    assert h["status"] == "ok" and h["readiness"] is True, h
    assert h["rdb"]["release_id"] == os.environ["EXPECTED_RELEASE_ID"], h
else:
    assert "database_error" not in h and "graph_error" not in h, h
    assert h["rdb"]["snapshot_hash"] is not None, h
' <<<"${health}"

for path in /db/version /db/stats /db/tables /db/catalog /db/coverage; do
  curl --fail --silent --show-error "${api_url}${path}" >/dev/null
done
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT 1 AS ok"}' "${api_url}/db" \
  | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r["columns"]==["ok"] and r["row_count"]==1 and "elapsed_ms" in r, r'

sql_write_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"query":"DELETE FROM enriched.product_master"}' "${api_url}/db/sql")"
sql_multi_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT 1; DROP TABLE raw.bond_kr_master"}' "${api_url}/db/sql")"
sparql_write_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"sparql":"INSERT DATA { <a> <b> <c> }"}' "${api_url}/db/sparql")"
if [[ "${sql_write_status}" != "400" || "${sql_multi_status}" != "400" || "${sparql_write_status}" != "400" ]]; then
  echo "read-only API guard failed: sql=${sql_write_status}, multi=${sql_multi_status}, sparql=${sparql_write_status}" >&2
  exit 1
fi

if [[ -n "${POSTGRES_USER:-}" && -n "${POSTGRES_DB:-}" ]]; then
  if docker compose exec -T db psql -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "BEGIN; SET ROLE agent_reader; INSERT INTO meta.load_run SELECT * FROM meta.load_run LIMIT 1; ROLLBACK" \
    >/dev/null 2>&1; then
    echo "agent_reader unexpectedly obtained INSERT permission" >&2
    exit 1
  fi
  if docker compose exec -T db psql -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "BEGIN; SET ROLE agent_reader; CREATE TABLE public.reader_must_not_create(id integer); ROLLBACK" \
    >/dev/null 2>&1; then
    echo "agent_reader unexpectedly obtained DDL permission" >&2
    exit 1
  fi
  role_settings="$(docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -At \
    -c "SELECT array_to_string(rolconfig, ',') FROM pg_roles WHERE rolname='agent_reader'")"
  if [[ "${role_settings}" != *"default_transaction_read_only=on"* || "${role_settings}" != *"statement_timeout=2s"* ]]; then
    echo "agent_reader role timeout/read-only settings missing: ${role_settings}" >&2
    exit 1
  fi
fi

python3 script/regression_v2.py --check >/dev/null
python3 script/regression_v2.py --endpoint "${AGENT_QUERY_URL}"
printf '%s\n' "v2 ${mode#--} health/API/security/35-case regression PASS"
