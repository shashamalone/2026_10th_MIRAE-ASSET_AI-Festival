#!/usr/bin/env bash
set -euo pipefail

api_url="${API_URL:-http://127.0.0.1:${API_PORT:-8000}}"
health="$(curl --fail --silent --show-error "${api_url}/health")"
python3 -c 'import json,sys; h=json.load(sys.stdin); assert h["status"]=="ok", h; assert h["data"]["dataset_version"]=="financial-products-2026-07-11", h' <<<"${health}"
curl --fail --silent --show-error "${api_url}/db/version" >/dev/null
curl --fail --silent --show-error "${api_url}/db/catalog" >/dev/null
curl --fail --silent --show-error "${api_url}/db/coverage" >/dev/null
python3 script/regression_v2.py --check >/dev/null

if [[ -z "${AGENT_QUERY_URL:-}" ]]; then
  printf '%s\n' "AGENT_QUERY_URL is required for the mandatory 35-case live regression" >&2
  exit 1
fi
python3 script/regression_v2.py --endpoint "${AGENT_QUERY_URL}"
printf '%s\n' "v2 health/catalog/coverage and 35-case regression PASS"
