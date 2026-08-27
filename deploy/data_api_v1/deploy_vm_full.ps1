[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [switch]$AcceptExistingPublicReadOnlyDbRisk,
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000',
    [DateTimeOffset]$PublicTestExpiresAt = [DateTimeOffset]::Now.AddDays(2),
    [string]$T105ArtifactDir = '',
    [switch]$PrepareCompatibilityPatchOnly
)

$ErrorActionPreference = 'Stop'
if (-not $AcceptExistingPublicReadOnlyDbRisk) {
    throw 'Explicit -AcceptExistingPublicReadOnlyDbRisk is required for this temporary test VM'
}
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
if (-not $T105ArtifactDir) {
    $T105ArtifactDir = Join-Path $repo '..\T-105-data-api-cutover\artifacts\runs\T-105-data-api-cutover\codex-v2-cutover-0826'
}
$sourceT105ArtifactDir = (Resolve-Path $T105ArtifactDir).Path
$patchedT105ArtifactDir = Join-Path $repo 'artifacts\runs\T-106-agent-data-api\codex-agent-data-api-0827\t105-default-graph-fix'
New-Item -ItemType Directory -Path $patchedT105ArtifactDir -Force | Out-Null
Copy-Item -Path (Join-Path $sourceT105ArtifactDir '*') -Destination $patchedT105ArtifactDir -Recurse -Force

$oldGraphQuery = 'query=SELECT (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } }'
$allGraphQuery = 'query=SELECT (COUNT(*) AS ?triples) WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }'
foreach ($name in ('data_api_cutover.sh', 'data_api_rollback.sh')) {
    $path = Join-Path $patchedT105ArtifactDir $name
    $content = [IO.File]::ReadAllText($path)
    $matches = ([regex]::Matches($content, [regex]::Escape($oldGraphQuery))).Count
    if ($matches -ne 1) {
        throw "Expected exactly one legacy named-graph count in ${name}; actual=$matches"
    }
    $content = $content.Replace($oldGraphQuery, $allGraphQuery)
    [IO.File]::WriteAllText($path, $content, [Text.UTF8Encoding]::new($false))
}
$cutoverPath = Join-Path $patchedT105ArtifactDir 'data_api_cutover.sh'
$cutoverContent = [IO.File]::ReadAllText($cutoverPath)
$oldImagePreserve = 'docker tag "${old_api_image}" "${old_api_tag}"'
$safeImagePreserve = @'
rebuilt_old_api=0
if docker image inspect "${old_api_image}" >/dev/null 2>&1; then
    docker tag "${old_api_image}" "${old_api_tag}"
else
    echo "OLD_API_IMAGE_MISSING: committing running container ${api_id} for rollback"
    if ! docker commit --pause=true "${api_id}" "${old_api_tag}" >/dev/null; then
        echo "OLD_API_COMMIT_UNAVAILABLE: rebuilding rollback image from ${current_dir}"
        docker build -t "${old_api_tag}" "${current_dir}"
        rebuilt_old_api=1
    fi
fi
old_api_image=$(docker image inspect -f '{{.Id}}' "${old_api_tag}")
if [[ "${rebuilt_old_api}" == 1 ]]; then
    (
        probe_container="${project}-old-api-probe-${timestamp,,}"
        cleanup_probe() { docker rm -f "${probe_container}" >/dev/null 2>&1 || true; }
        trap cleanup_probe EXIT
        api_network=$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{println}}{{end}}' "${api_id}" | head -n 1)
        test -n "${api_network}"
        docker run -d --name "${probe_container}" --network "${api_network}" \
            --env-file "${current_env}" "${old_api_tag}" >/dev/null
        probe_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${probe_container}")
        test -n "${probe_ip}"
        for _ in $(seq 1 30); do
            if curl --fail --silent --show-error "http://${probe_ip}:8000/health" >"${journal_dir}/rebuilt-old-health.json" 2>/dev/null \
              && curl --fail --silent --show-error "http://${probe_ip}:8000/db/stats" >"${journal_dir}/rebuilt-old-stats.json" 2>/dev/null; then
                break
            fi
            sleep 2
        done
        python3 - "${journal_dir}/old-health.json" "${journal_dir}/rebuilt-old-health.json" "${journal_dir}/old-stats.json" "${journal_dir}/rebuilt-old-stats.json" <<'PY'
import json, sys

def scrub(value):
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items() if key != "elapsed_ms"}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value

values = []
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as stream:
        values.append(scrub(json.load(stream)))
assert values[0] == values[1], (values[0], values[1])
assert values[2] == values[3], (values[2], values[3])
PY
        echo "OLD_API_REBUILD_VERIFY_PASS: image=${old_api_tag}"
    )
fi
'@.TrimEnd()
$imageMatches = ([regex]::Matches($cutoverContent, [regex]::Escape($oldImagePreserve))).Count
if ($imageMatches -ne 1) {
    throw "Expected exactly one legacy old-image tag command; actual=$imageMatches"
}
$cutoverContent = $cutoverContent.Replace($oldImagePreserve, $safeImagePreserve)
[IO.File]::WriteAllText($cutoverPath, $cutoverContent, [Text.UTF8Encoding]::new($false))
Write-Host 'T-105 compatibility patch prepared: full old Graph count and verified rollback API rebuild fallback.'

$t105 = Join-Path $patchedT105ArtifactDir 'data_api_cutover.ps1'
$t106 = Join-Path $scriptDir 'deploy_vm.ps1'
foreach ($file in ($t105, $t106)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing deployment script: $file" }
}
if ($PrepareCompatibilityPatchOnly) {
    Write-Output "T-105 PATCH PREP PASS: $patchedT105ArtifactDir"
    return
}

$expected = 'financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38'
$v2Active = $false
try {
    $health = Invoke-RestMethod -Uri "$ConsumerBaseUrl/health" -TimeoutSec 20
    $v2Active = (
        $health.status -eq 'ok' -and
        $health.readiness -eq $true -and
        $health.rdb.release_id -eq $expected -and
        $health.graph.release_id -eq $expected
    )
}
catch {
    $v2Active = $false
}

if (-not $v2Active) {
    $probe = Invoke-RestMethod -Method Post -Uri "$ConsumerBaseUrl/db" -ContentType 'application/json' -Body '{"sql":"SELECT 1 AS probe"}' -TimeoutSec 20
    if ($probe.rows[0].probe -ne '1' -and $probe.rows[0].probe -ne 1) {
        throw 'Existing public read-only DB probe did not return 1; refusing risk-mode cutover'
    }
    Write-Warning 'The current VM already exposes guarded read-only /db publicly. T-105 will retain that state only until T-106 replaces it and blocks /db*.'
    & $t105 -Preflight -SshTarget $SshTarget -ConsumerBaseUrl $ConsumerBaseUrl
    if ($LASTEXITCODE -ne 0) { throw 'T-105 preflight failed' }
    # T-105 predates the explicit existing-public-risk mode. Its legacy switch is
    # used only after the external probe and caller acknowledgement above.
    & $t105 -ApproveReplaceExistingService -ConfirmTeamRestrictedAccess -SshTarget $SshTarget -ConsumerBaseUrl $ConsumerBaseUrl
    if ($LASTEXITCODE -ne 0) { throw 'T-105 cutover failed or rolled back' }
}
else {
    Write-Host 'T-105 V2 DB/Graph release is already active; skipping cutover.'
}

& $t106 -SshTarget $SshTarget -ConsumerBaseUrl $ConsumerBaseUrl -PublicTestExpiresAt $PublicTestExpiresAt
if ($LASTEXITCODE -ne 0) { throw 'T-106 curated API deployment failed' }
Write-Output "FULL VM DEPLOY PASS: release=$expected public=$ConsumerBaseUrl expires=$($PublicTestExpiresAt.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) raw_db=blocked"
