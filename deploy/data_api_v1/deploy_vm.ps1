[CmdletBinding()]
param(
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$IncomingDir = '/home/user1106/financial-agent-v2/incoming',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000',
    [DateTimeOffset]$PublicTestExpiresAt = [DateTimeOffset]::Now.AddDays(2),
    [switch]$KeepPublicReadOnlyDbForTeamTest
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
$installer = Join-Path $scriptDir 'install_vm_release.sh'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "Missing installer: $installer"
}

& git -C $repo diff --quiet --exit-code
if ($LASTEXITCODE -ne 0) { throw 'Refuse dirty tracked worktree' }
& git -C $repo diff --cached --quiet --exit-code
if ($LASTEXITCODE -ne 0) { throw 'Refuse staged changes' }
$releaseSha = (& git -C $repo rev-parse HEAD).Trim()
if ($releaseSha -notmatch '^[0-9a-f]{40}$') { throw "Invalid release SHA: $releaseSha" }

$expiry = $PublicTestExpiresAt.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
if ($PublicTestExpiresAt -le [DateTimeOffset]::Now.AddMinutes(10)) {
    throw 'PublicTestExpiresAt must be more than 10 minutes in the future'
}
$artifactDir = Join-Path $repo 'artifacts\runs\T-106-agent-data-api\codex-agent-data-api-0827\vm-deploy'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
$archiveName = "financial-agent-data-api-$releaseSha.tar.gz"
$archive = Join-Path $artifactDir $archiveName
& git -C $repo archive --format=tar.gz --prefix="financial-agent-data-api-$releaseSha/" --output=$archive HEAD
if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }

$installerHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
$archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$manifestName = "financial-agent-data-api-$releaseSha-SHA256SUMS"
$manifest = Join-Path $artifactDir $manifestName
$manifestText = "$archiveHash  $archiveName`n$installerHash  install_vm_release.sh`n"
[IO.File]::WriteAllText($manifest, $manifestText, [Text.UTF8Encoding]::new($false))

Write-Host "Uploading T-106 release $releaseSha; enter the SSH password only in this terminal."
& scp $archive $manifest $installer "${SshTarget}:$IncomingDir/"
if ($LASTEXITCODE -ne 0) { throw 'T-106 upload failed' }
$accessMode = if ($KeepPublicReadOnlyDbForTeamTest) { 'team-db' } else { 'curated' }
$teamDbAck = if ($KeepPublicReadOnlyDbForTeamTest) { 'I_ACCEPT_TEMPORARY_GUARDED_READ_ONLY_DB' } else { '-' }
$remote = "cd '$IncomingDir' && sha256sum -c '$manifestName' && chmod 755 install_vm_release.sh && bash install_vm_release.sh '$releaseSha' '$expiry' '$accessMode' '$teamDbAck'"
& ssh $SshTarget $remote
if ($LASTEXITCODE -ne 0) {
    throw 'T-106 VM install failed; the preceding V2 API remains available or was restored by the deploy guard'
}

$release = Invoke-RestMethod -Uri "$ConsumerBaseUrl/v1/release" -TimeoutSec 20
$health = Invoke-RestMethod -Uri "$ConsumerBaseUrl/health" -TimeoutSec 20
$rawStatus = 0
try {
    Invoke-WebRequest -UseBasicParsing -Uri "$ConsumerBaseUrl/db/version" -TimeoutSec 20 -ErrorAction Stop | Out-Null
    $rawStatus = 200
}
catch {
    if ($_.Exception.Response) { $rawStatus = [int]$_.Exception.Response.StatusCode }
}
$expected = 'financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38'
$expectedRawStatus = if ($KeepPublicReadOnlyDbForTeamTest) { 200 } else { 404 }
if ($release.release_id -ne $expected -or $health.status -ne 'ok' -or $rawStatus -ne $expectedRawStatus) {
    throw "Consumer verification failed: release=$($release.release_id) health=$($health.status) raw_status=$rawStatus"
}
$rawMode = if ($KeepPublicReadOnlyDbForTeamTest) { 'guarded-readonly' } else { 'blocked' }
Write-Output "REMOTE VM DATA API PASS: $ConsumerBaseUrl release=$expected expires=$expiry raw_db=$rawMode"
