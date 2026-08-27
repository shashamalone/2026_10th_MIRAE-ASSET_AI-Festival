[CmdletBinding()]
param(
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$IncomingDir = '/home/user1106/financial-agent-v2/incoming',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000'
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $scriptDir 'prepare_t105_retry.sh'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Missing retry preparation script: $script"
}

$hash = (Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()
$remoteScript = "$IncomingDir/prepare_t105_retry.sh"
& scp $script "${SshTarget}:$remoteScript"
if ($LASTEXITCODE -ne 0) {
    throw 'T-105 retry preparation upload failed'
}

$remoteCommand = "printf '%s  %s\n' '$hash' '$remoteScript' | sha256sum -c - && chmod 755 '$remoteScript' && bash '$remoteScript'"
$remoteOutput = [Collections.Generic.List[string]]::new()
& ssh $SshTarget $remoteCommand | ForEach-Object {
    $line = $_.ToString()
    [void]$remoteOutput.Add($line)
    Write-Host $line
}
if ($LASTEXITCODE -ne 0) {
    throw 'T-105 retry preparation failed; live cutover was not started'
}
if (-not ($remoteOutput | Where-Object { $_ -match '^T105 RETRY READY PASS:' })) {
    throw 'T-105 retry preparation returned without the exact success marker'
}

$health = Invoke-RestMethod -Uri "$ConsumerBaseUrl/health" -TimeoutSec 20
$probe = Invoke-RestMethod -Method Post -Uri "$ConsumerBaseUrl/db" -ContentType 'application/json' -Body '{"sql":"SELECT 1 AS probe"}' -TimeoutSec 20
if ($health.status -ne 'ok' -or ($probe.rows[0].probe -ne '1' -and $probe.rows[0].probe -ne 1)) {
    throw "External old API baseline failed after retry preparation: health=$($health.status) probe=$($probe.rows[0].probe)"
}
Write-Output "REMOTE T105 RETRY READY PASS: old API remains active at $ConsumerBaseUrl"
