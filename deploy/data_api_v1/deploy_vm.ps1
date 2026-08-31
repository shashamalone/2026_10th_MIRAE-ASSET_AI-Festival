[CmdletBinding()]
param(
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$IncomingDir = '/home/user1106/financial-agent-v2/incoming',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000',
    [DateTimeOffset]$PublicTestExpiresAt = [DateTimeOffset]::Now.AddDays(2),
    [switch]$ConfirmInvestmentReportVectorActive
)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmInvestmentReportVectorActive) {
    throw 'Vector DB investment-report deployment handoff must be confirmed before Graph/API deployment'
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
$installer = Join-Path $scriptDir 'install_vm_release.sh'
$graphStage = Join-Path $scriptDir 'stage_graph_union.sh'
$graphArtifactDir = Join-Path $repo 'artifacts\runs\T-107-db-api-graph-union\codex-db-api-graph-0831\graph-source'
$graphArchiveName = 'ontology-bundle-ontology-20260831-00b5466f9463.tar.gz'
$graphArchive = Join-Path $graphArtifactDir $graphArchiveName
foreach ($required in @($installer, $graphStage, $graphArchive)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing deployment input: $required"
    }
}

& git -C $repo diff --quiet --exit-code
if ($LASTEXITCODE -ne 0) { throw 'Refuse dirty tracked worktree' }
& git -C $repo diff --cached --quiet --exit-code
if ($LASTEXITCODE -ne 0) { throw 'Refuse staged changes' }
$releaseSha = (& git -C $repo rev-parse HEAD).Trim()
if ($releaseSha -notmatch '^[0-9a-f]{40}$') {
    throw "Invalid release SHA: $releaseSha"
}

$expiry = $PublicTestExpiresAt.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
if ($PublicTestExpiresAt -le [DateTimeOffset]::Now.AddMinutes(10)) {
    throw 'PublicTestExpiresAt must be more than 10 minutes in the future'
}
if ($PublicTestExpiresAt -gt [DateTimeOffset]::Now.AddDays(30)) {
    throw 'PublicTestExpiresAt cannot exceed 30 days'
}

$artifactDir = Join-Path $repo 'artifacts\runs\T-107-db-api-graph-union\codex-db-api-graph-0831\vm-deploy'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
$archiveName = "financial-agent-data-api-$releaseSha.tar.gz"
$archive = Join-Path $artifactDir $archiveName
& git -C $repo archive --format=tar.gz --prefix="financial-agent-data-api-$releaseSha/" --output=$archive HEAD
if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }

$manifestName = "financial-agent-data-api-$releaseSha-SHA256SUMS"
$manifest = Join-Path $artifactDir $manifestName
$uploads = @(
    @{ Path = $archive; Name = $archiveName },
    @{ Path = $installer; Name = 'install_vm_release.sh' },
    @{ Path = $graphStage; Name = 'stage_graph_union.sh' },
    @{ Path = $graphArchive; Name = $graphArchiveName }
)
$manifestLines = foreach ($item in $uploads) {
    $hash = (Get-FileHash -LiteralPath $item.Path -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($item.Name)"
}
[IO.File]::WriteAllText(
    $manifest,
    ($manifestLines -join [Environment]::NewLine) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)

Write-Host "Uploading T-107 release $releaseSha; enter the SSH password only in this terminal."
$uploadPaths = @($uploads.Path) + $manifest
& scp $uploadPaths "${SshTarget}:$IncomingDir/"
if ($LASTEXITCODE -ne 0) { throw 'T-107 upload failed' }

$receipt = '/home/user1106/financial-agent-v2/shared/backups/graph-source-ontology-20260831-00b5466f9463/stage-augment.json'
$graphVolume = 'financial-agent-prep_oxigraph-ontology-20260831-00b5466f'
$remote = @"
cd '$IncomingDir' &&
sha256sum -c '$manifestName' &&
chmod 755 install_vm_release.sh stage_graph_union.sh &&
if [ ! -f '$receipt' ]; then GRAPH_LOAD_MODE=augment bash stage_graph_union.sh; fi &&
bash install_vm_release.sh '$releaseSha' '$expiry' '$graphVolume' 'INVESTMENT_REPORT_VECTOR_ACTIVE'
"@ -replace "`r?`n", ' '
& ssh $SshTarget $remote
if ($LASTEXITCODE -ne 0) {
    throw 'T-107 VM install failed; inspect Graph Stage or API rollback output'
}

$version = Invoke-RestMethod -Uri "$ConsumerBaseUrl/db/version" -TimeoutSec 20
$health = Invoke-RestMethod -Uri "$ConsumerBaseUrl/health" -TimeoutSec 20
$sql = Invoke-RestMethod -Method Post -Uri "$ConsumerBaseUrl/db/sql" `
    -ContentType 'text/plain; charset=utf-8' -Body 'SELECT 1 AS probe' -TimeoutSec 20
$sparql = Invoke-RestMethod -Method Post -Uri "$ConsumerBaseUrl/db/sparql" `
    -ContentType 'text/plain; charset=utf-8' `
    -Body 'SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }' -TimeoutSec 20
$expected = 'financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38'
if (
    $version.rows[0].release_id -ne $expected -or
    $health.status -ne 'ok' -or
    [int64]$health.graph.triples -ne 1628311 -or
    [int]$sql.rows[0].probe -ne 1 -or
    [int64]$sparql.rows[0].triples -ne 1628311
) {
    throw "Consumer verification failed: health=$($health.status) graph=$($health.graph.triples)"
}
Write-Output "REMOTE VM RAW QUERY API PASS: $ConsumerBaseUrl release=$expected graph=1628311 union_default=on expires=$expiry"
