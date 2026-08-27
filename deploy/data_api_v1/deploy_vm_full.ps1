[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [switch]$AcceptExistingPublicReadOnlyDbRisk,
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000',
    [DateTimeOffset]$PublicTestExpiresAt = [DateTimeOffset]::Now.AddDays(2),
    [string]$T105ArtifactDir = ''
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
$t105 = Join-Path $T105ArtifactDir 'data_api_cutover.ps1'
$t106 = Join-Path $scriptDir 'deploy_vm.ps1'
foreach ($file in ($t105, $t106)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing deployment script: $file" }
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
