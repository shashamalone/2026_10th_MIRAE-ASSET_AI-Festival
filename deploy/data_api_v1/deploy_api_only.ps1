[CmdletBinding()]
param(
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$IncomingDir = '/home/user1106/financial-agent-v2/incoming',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000',
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$expectedGraphTriples = 1226698
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
$installer = Join-Path $scriptDir 'install_api_only_release.sh'
$verifier = Join-Path $scriptDir 'verify_public_api.py'
foreach ($required in @($installer, $verifier)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing API-only deployment file: $required"
    }
}

& git -C $repo diff --quiet --exit-code
if ($LASTEXITCODE -ne 0) { throw 'Refuse dirty tracked worktree' }
& git -C $repo diff --cached --quiet --exit-code
if ($LASTEXITCODE -ne 0) { throw 'Refuse staged changes' }
$releaseSha = (& git -C $repo rev-parse HEAD).Trim()
if ($releaseSha -notmatch '^[0-9a-f]{40}$') { throw "Invalid release SHA: $releaseSha" }

$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$artifactDir = Join-Path $repo "artifacts\runs\$runId\codex-t154-answer-deploy-0906"
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null

# This is the default mode. It performs only public read-only requests and writes
# an allowlisted local receipt; it never opens SSH or changes the VM.
& py -3.13 -X utf8 $verifier `
    --url $ConsumerBaseUrl `
    --expected-graph-triples $expectedGraphTriples `
    --preflight `
    --artifact-dir $artifactDir
if ($LASTEXITCODE -ne 0) { throw 'Read-only deployment preflight failed' }

if (-not $Execute) {
    Write-Output "API-ONLY PREFLIGHT PASS: no deployment executed; artifact=$artifactDir"
    Write-Output 'Re-run with -Execute only after reviewing the receipt and commit SHA.'
    return
}

$archiveName = "financial-agent-api-only-$releaseSha.tar.gz"
$archive = Join-Path $artifactDir $archiveName
& git -C $repo archive --format=tar.gz --prefix="financial-agent-api-only-$releaseSha/" --output=$archive HEAD
if ($LASTEXITCODE -ne 0) { throw 'API-only git archive failed' }

# The working tree can use CRLF on Windows. Bash interprets the trailing CR in
# `set -Eeuo pipefail` as part of the option name, so create a deterministic
# LF-only, UTF-8-no-BOM upload artifact instead of uploading the checkout file.
$installerUpload = Join-Path $artifactDir 'install_api_only_release.sh'
$installerText = [IO.File]::ReadAllText($installer).Replace("`r`n", "`n").Replace("`r", "`n")
[IO.File]::WriteAllText($installerUpload, $installerText, [Text.UTF8Encoding]::new($false))

$checksumName = "financial-agent-api-only-$releaseSha-SHA256SUMS"
$checksumPath = Join-Path $artifactDir $checksumName
$checksumLines = @(
    "$((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant())  $archiveName",
    "$((Get-FileHash -Algorithm SHA256 -LiteralPath $installerUpload).Hash.ToLowerInvariant())  install_api_only_release.sh"
)
[IO.File]::WriteAllText(
    $checksumPath,
    ($checksumLines -join [Environment]::NewLine) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)

& scp $archive $installerUpload $checksumPath "${SshTarget}:$IncomingDir/"
if ($LASTEXITCODE -ne 0) { throw 'API-only upload failed' }

$remote = "cd '$IncomingDir' && chmod 755 install_api_only_release.sh && bash install_api_only_release.sh '$releaseSha' '$expectedGraphTriples'"
& ssh $SshTarget $remote
if ($LASTEXITCODE -ne 0) {
    throw 'API-only VM install failed; the remote installer attempted previous-release rollback'
}

& py -3.13 -X utf8 $verifier `
    --url $ConsumerBaseUrl `
    --expected-graph-triples $expectedGraphTriples
if ($LASTEXITCODE -ne 0) { throw 'External API-only post-deploy verification failed' }
Write-Output "REMOTE API-ONLY PASS: release=$releaseSha graph=$expectedGraphTriples db=unchanged graph_service=unchanged"
