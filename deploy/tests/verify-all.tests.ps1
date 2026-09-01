$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot '..\verify-all.ps1'
$json = & pwsh -NoProfile -File $scriptPath -CheckOnly -Json
$result = $json | ConvertFrom-Json

if (-not ($result.checks.name -contains 'agent-env')) { throw 'agent-env check missing' }
if (-not ($result.checks.name -contains 'agnes-key')) { throw 'agnes-key check missing' }
if (-not ($result.checks.name -contains 'nacos-port')) { throw 'nacos remote check missing' }
if (-not ($result.checks.name -contains 'rocketmq-nameserver-port')) { throw 'rocketmq remote check missing' }
if (($result.checks | Where-Object { $_.name -eq 'nacos-port' }).status -ne 'passed') { throw 'configured Nacos endpoint should be reachable' }
if (($result.checks | Where-Object { $_.name -eq 'rocketmq-nameserver-port' }).status -ne 'passed') { throw 'configured RocketMQ endpoint should be reachable' }
if ($json -match 'sk-[A-Za-z0-9]') { throw 'secret leaked' }

Write-Output 'verify-all tests passed'
