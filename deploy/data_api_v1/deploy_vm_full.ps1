[CmdletBinding()]
param(
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$IncomingDir = '/home/user1106/financial-agent-v2/incoming',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000',
    [DateTimeOffset]$PublicTestExpiresAt = [DateTimeOffset]::Now.AddDays(2),
    [switch]$ConfirmInvestmentReportVectorActive
)

$ErrorActionPreference = 'Stop'
$deploy = Join-Path $PSScriptRoot 'deploy_vm.ps1'
& $deploy `
    -SshTarget $SshTarget `
    -IncomingDir $IncomingDir `
    -ConsumerBaseUrl $ConsumerBaseUrl `
    -PublicTestExpiresAt $PublicTestExpiresAt `
    -ConfirmInvestmentReportVectorActive:$ConfirmInvestmentReportVectorActive
if ($LASTEXITCODE -ne 0) {
    throw 'T-107 full deployment failed'
}
