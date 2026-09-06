[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot,
    [string]$SshTarget = 'user1106@40.82.145.44',
    [switch]$StageOnly
)

$ErrorActionPreference = 'Stop'
$bundle = (Resolve-Path -LiteralPath $BundleRoot).Path
$manifestPath = Join-Path $bundle 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "manifest.json is missing: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$bundleId = [string]$manifest.bundle_id
if ($bundleId -notmatch '^ontology-holdings-20260821-[0-9a-f]{12}$') {
    throw "Unexpected bundle id: $bundleId"
}
$parent = Split-Path -Parent $bundle
$archive = Join-Path $parent "ontology-bundle-$bundleId.tar.gz"
if (-not (Test-Path -LiteralPath $archive)) {
    tar.exe -czf $archive -C $parent 'ontology-bundle'
    if ($LASTEXITCODE -ne 0) { throw 'tar failed' }
}
$archiveSha = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$newVolume = "financial-agent-prep_oxigraph-holdings-20260821-$($bundleId.Substring($bundleId.Length - 12))"
$remoteArchive = "/home/user1106/financial-agent-v2/incoming/$(Split-Path -Leaf $archive)"
$remoteScript = '/home/user1106/financial-agent-v2/incoming/stage_and_cutover.sh'
$stageScript = Join-Path $PSScriptRoot 'stage_and_cutover.sh'

Write-Host "Uploading bundle=$bundleId sha256=$archiveSha volume=$newVolume"
& scp -- $archive $stageScript "${SshTarget}:/home/user1106/financial-agent-v2/incoming/"
if ($LASTEXITCODE -ne 0) { throw 'bundle/script upload failed' }

$cutover = if ($StageOnly) { '0' } else { '1' }
$remoteCommand = "chmod 700 '$remoteScript' && BUNDLE_ID='$bundleId' ARCHIVE_SHA256='$archiveSha' NEW_VOLUME='$newVolume' CUTOVER='$cutover' '$remoteScript'"
& ssh -- $SshTarget $remoteCommand
if ($LASTEXITCODE -ne 0) { throw "remote graph deployment failed with exit code $LASTEXITCODE" }

[pscustomobject]@{
    bundle_id = $bundleId
    archive = $archive
    archive_sha256 = $archiveSha
    new_volume = $newVolume
    cutover_requested = -not $StageOnly
} | ConvertTo-Json -Depth 4
