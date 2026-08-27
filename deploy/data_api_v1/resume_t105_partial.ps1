[CmdletBinding()]
param(
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$IncomingDir = '/home/user1106/financial-agent-v2/incoming',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000',
    [string]$T105ArtifactDir = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
if (-not $T105ArtifactDir) {
    $T105ArtifactDir = Join-Path $repo '..\T-105-data-api-cutover\artifacts\runs\T-105-data-api-cutover\codex-v2-cutover-0826'
}
$sourceRollback = Join-Path $T105ArtifactDir 'data_api_rollback.sh'
$resume = Join-Path $scriptDir 'resume_t105_partial.sh'
$verify = Join-Path $T105ArtifactDir 'data_api_verify.sh'
$watchdog = Join-Path $T105ArtifactDir 'data_api_watchdog.sh'
$ack = Join-Path $T105ArtifactDir 'data_api_ack.sh'
foreach ($file in ($sourceRollback, $resume, $verify, $watchdog, $ack)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing recovery file: $file" }
}

$artifactDir = Join-Path $repo 'artifacts\runs\T-106-agent-data-api\codex-agent-data-api-0827\partial-recovery'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
$patchedRollback = Join-Path $artifactDir 'data_api_rollback.sh'
$rollbackContent = [IO.File]::ReadAllText($sourceRollback)
$oldGraphQuery = 'query=SELECT (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } }'
$allGraphQuery = 'query=SELECT (COUNT(*) AS ?triples) WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }'
if (([regex]::Matches($rollbackContent, [regex]::Escape($oldGraphQuery))).Count -ne 1) {
    throw 'Rollback Graph fingerprint patch anchor mismatch'
}
$rollbackContent = $rollbackContent.Replace($oldGraphQuery, $allGraphQuery)
[IO.File]::WriteAllText($patchedRollback, $rollbackContent, [Text.UTF8Encoding]::new($false))

$uploads = @($patchedRollback, $resume, $verify, $watchdog, $ack)
$remoteNames = @('data_api_rollback.sh', 'resume_t105_partial.sh', 'data_api_verify.sh', 'data_api_watchdog.sh', 'data_api_ack.sh')
$hashLines = for ($index = 0; $index -lt $uploads.Count; $index++) {
    $hash = (Get-FileHash -LiteralPath $uploads[$index] -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $IncomingDir/$($remoteNames[$index])"
}
& scp @uploads "${SshTarget}:$IncomingDir/"
if ($LASTEXITCODE -ne 0) { throw 'Partial recovery upload failed' }
$encodedHashes = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($hashLines -join "`n") + "`n"))
$remoteCommand = "printf '%s' '$encodedHashes' | base64 -d | sha256sum -c - && chmod 755 '$IncomingDir/resume_t105_partial.sh' '$IncomingDir/data_api_rollback.sh' && bash '$IncomingDir/resume_t105_partial.sh' --latest"
$remoteOutput = [Collections.Generic.List[string]]::new()
& ssh $SshTarget $remoteCommand | ForEach-Object {
    $line = $_.ToString()
    [void]$remoteOutput.Add($line)
    Write-Host $line
}
if ($LASTEXITCODE -ne 0) { throw 'T-105 partial recovery failed; API remains fail-closed or rollback output must be inspected' }

$journal = $null
$ackPath = $null
foreach ($line in $remoteOutput) {
    if ($line -match '^DATA_API_CUTOVER_JOURNAL=(/home/user1106/financial-agent-v2/shared/backups/data-platform-v2-[^/]+/data-api-cutover-[0-9TZ]+/journal\.env)$') { $journal = $Matches[1] }
    if ($line -match '^DATA_API_CUTOVER_ACK=(/home/user1106/financial-agent-v2/shared/backups/data-platform-v2-[^/]+/data-api-cutover-[0-9TZ]+/consumer-ack)$') { $ackPath = $Matches[1] }
}
if (-not $journal -or -not $ackPath) { throw 'Recovery completed without exact journal/ack paths' }

try {
    $health = Invoke-RestMethod -Uri "$ConsumerBaseUrl/health" -TimeoutSec 20
    $version = Invoke-RestMethod -Uri "$ConsumerBaseUrl/db/version" -TimeoutSec 20
    $expected = 'financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38'
    if ($health.status -ne 'ok' -or $health.readiness -ne $true -or $health.rdb.release_id -ne $expected -or $health.graph.release_id -ne $expected -or $version.release_id -ne $expected) {
        throw 'Public V2 consumer verification mismatch'
    }
    & ssh $SshTarget "bash '$IncomingDir/data_api_ack.sh' '$journal'"
    if ($LASTEXITCODE -ne 0) { throw 'Recovery consumer acknowledgement failed' }
}
catch {
    & ssh $SshTarget "bash '$IncomingDir/data_api_rollback.sh' '$journal'"
    throw
}
Write-Output "T-105 PARTIAL RECOVERY PASS: $ConsumerBaseUrl release=$expected"
