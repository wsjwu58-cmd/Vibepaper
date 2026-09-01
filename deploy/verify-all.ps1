param(
    [switch]$CheckOnly,
    [switch]$Json,
    [int]$TimeoutSeconds = 3
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$checks = [System.Collections.Generic.List[object]]::new()

function Add-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message
    )

    $checks.Add([pscustomobject]@{
            name = $Name
            status = $Status
            message = $Message
        }) | Out-Null
}

function Test-EnvironmentFile {
    param(
        [string]$Name,
        [string]$Path,
        [string[]]$RequiredKeys
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Add-Check $Name 'failed' 'environment file is missing'
        return
    }

    $keys = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            $keys[$Matches[1]] = $value
        }
    }

    $missing = @($RequiredKeys | Where-Object { -not $keys.ContainsKey($_) -or [string]::IsNullOrWhiteSpace([string]$keys[$_]) })
    if ($missing.Count -gt 0) {
        Add-Check $Name 'failed' 'required environment entries are missing'
        return
    }
    Add-Check $Name 'passed' 'required environment entries are present'
}

function Get-EnvironmentValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$DefaultValue
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $DefaultValue
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and $Matches[1] -eq $Name) {
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                return $value
            }
        }
    }
    return $DefaultValue
}

function Resolve-TcpEndpoint {
    param(
        [string]$Address,
        [string]$DefaultHost,
        [int]$DefaultPort
    )

    $candidate = if ([string]::IsNullOrWhiteSpace($Address)) { "${DefaultHost}:$DefaultPort" } else { $Address.Trim() }
    if ($candidate -notmatch '^(?<host>[^:]+):(?<port>\d+)$') {
        throw "Invalid TCP endpoint"
    }
    return [pscustomobject]@{ Host = $Matches.host; Port = [int]$Matches.port }
}

function Test-TcpPort {
    param(
        [string]$Name,
        [int]$Port,
        [string]$Server = '127.0.0.1'
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($Server, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutSeconds * 1000)) {
            Add-Check $Name 'failed' 'port is not accepting connections'
            return
        }
        $client.EndConnect($async)
        Add-Check $Name 'passed' 'port is accepting connections'
    } catch {
        Add-Check $Name 'failed' 'port is not accepting connections'
    } finally {
        $client.Dispose()
    }
}

function Test-HttpEndpoint {
    param(
        [string]$Name,
        [string]$Uri
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSeconds
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
            Add-Check $Name 'passed' 'health endpoint responded'
        } else {
            Add-Check $Name 'failed' 'health endpoint returned an unexpected status'
        }
    } catch {
        Add-Check $Name 'failed' 'health endpoint did not respond successfully'
    }
}

$agentEnvPath = Join-Path $projectRoot 'pi-main\packages\vibepaper-agent-service\.env'
Test-EnvironmentFile 'agent-env' $agentEnvPath @(
    'VIBEPAPER_PORT',
    'VIBEPAPER_CANVAS_BASE_URL',
    'VIBEPAPER_GENERATION_BASE_URL',
    'VIBEPAPER_CONFIRM_SIGNING_SECRET'
)
Test-EnvironmentFile 'agnes-key' $agentEnvPath @(
    'VIBEPAPER_AGNES_API_KEY'
)

Test-TcpPort 'frontend-port' 5173
foreach ($port in 8080..8087) {
    Test-TcpPort "java-port-$port" $port
}
Test-TcpPort 'generation-port' 8090
Test-TcpPort 'agent-port' 8091
foreach ($port in @(5432, 6379)) {
    Test-TcpPort "infrastructure-port-$port" $port
}
$nacosEndpoint = Resolve-TcpEndpoint (Get-EnvironmentValue $agentEnvPath 'VIBEPAPER_NACOS_ADDR' '192.168.141.129:8848') '192.168.141.129' 8848
$rocketMqEndpoint = Resolve-TcpEndpoint $env:ROCKETMQ_ADDR '192.168.141.128' 9876
Test-TcpPort 'nacos-port' $nacosEndpoint.Port $nacosEndpoint.Host
Test-TcpPort 'rocketmq-nameserver-port' $rocketMqEndpoint.Port $rocketMqEndpoint.Host

Test-HttpEndpoint 'frontend-health' 'http://127.0.0.1:5173/'
Test-HttpEndpoint 'gateway-health' 'http://127.0.0.1:8080/actuator/health'
Test-HttpEndpoint 'generation-health' 'http://127.0.0.1:8090/api/v1/models'
Test-HttpEndpoint 'agent-health' 'http://127.0.0.1:8091/health'

$failed = @($checks | Where-Object { $_.status -eq 'failed' }).Count
$result = [pscustomobject]@{ checks = @($checks) }
if ($Json) {
    $result | ConvertTo-Json -Depth 4
} else {
    $checks | Format-Table -AutoSize
}

if ($failed -gt 0) {
    exit 1
}
