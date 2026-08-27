[CmdletBinding()]
param(
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000'
)

$ErrorActionPreference = 'Stop'
$remoteScript = @'
set -Eeuo pipefail
container=financial-agent-prep-api-1
test "$(docker inspect -f '{{.Config.Image}}' "${container}")" = financial-agent-prep-api-rollback:20260827t032046z
docker start "${container}" >/dev/null
health=$(mktemp)
stats=$(mktemp)
trap 'rm -f -- "${health}" "${stats}"' EXIT
for _ in $(seq 1 30); do
  if curl --fail --silent --show-error http://127.0.0.1:8000/health >"${health}" 2>/dev/null \
    && curl --fail --silent --show-error http://127.0.0.1:8000/db/stats >"${stats}" 2>/dev/null; then
    break
  fi
  sleep 2
done
python3 - "${health}" "${stats}" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    health = json.load(stream)
with open(sys.argv[2], encoding="utf-8") as stream:
    stats = json.load(stream)
assert health.get("status") == "ok", health
assert isinstance(stats, dict) and stats, stats
print("REMOTE OLD API HEALTH PASS: status=ok stats_keys=" + ",".join(sorted(stats)))
PY
docker inspect "${container}" | python3 -c 'import json,sys; x=json.load(sys.stdin)[0]; print("api_image="+x["Config"]["Image"]+" running="+str(x["State"]["Running"]).lower())'
'@
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
& ssh $SshTarget "printf '%s' '$encoded' | base64 -d | bash"
if ($LASTEXITCODE -ne 0) { throw 'Old API emergency restore failed' }

$health = Invoke-RestMethod -Uri "$ConsumerBaseUrl/health" -TimeoutSec 20
$probe = Invoke-RestMethod -Method Post -Uri "$ConsumerBaseUrl/db" -ContentType 'application/json' -Body '{"sql":"SELECT 1 AS probe"}' -TimeoutSec 20
if ($health.status -ne 'ok' -or ($probe.rows[0].probe -ne '1' -and $probe.rows[0].probe -ne 1)) {
    throw "External old API verification failed: health=$($health.status) probe=$($probe.rows[0].probe)"
}
Write-Output "OLD API EMERGENCY RESTORE PASS: $ConsumerBaseUrl"
