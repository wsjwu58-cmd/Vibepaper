[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CaseId,

    [Parameter(Mandatory = $true)]
    [string]$CanvasUrl,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [Parameter(Mandatory = $true)]
    [string[]]$Checkpoints,

    [string[]]$WaitText = @(),

    [string]$Session = "vibepaper-full-chain-evidence"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$screenshotDir = Join-Path $OutputDir "screenshots"
New-Item -ItemType Directory -Force -Path $screenshotDir | Out-Null

function Invoke-AgentBrowser {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = (& agent-browser --session $Session @Arguments 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "agent-browser failed ($LASTEXITCODE): $output"
    }
    return $output.Trim()
}

function Save-Redacted {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $redacted = $Text
    $redacted = $redacted -replace '(?i)(authorization|api[_-]?key|secret|password|token|cookie)(\s*[:=]\s*)("[^"]*"|''[^'']*''|[^,\s}]+)', '$1$2<redacted>'
    $redacted = $redacted -replace '(?<!\d)\d{7,}(?!\d)', '<redacted>'
    [System.IO.File]::WriteAllText($Path, $redacted, [System.Text.UTF8Encoding]::new($false))
}

Invoke-AgentBrowser @("--headed", "open", $CanvasUrl) | Out-Null
Invoke-AgentBrowser @("wait", "--load", "domcontentloaded") | Out-Null

for ($index = 0; $index -lt $Checkpoints.Count; $index++) {
    $checkpoint = $Checkpoints[$index]
    if ($index -lt $WaitText.Count -and -not [string]::IsNullOrWhiteSpace($WaitText[$index])) {
        Invoke-AgentBrowser @("wait", "--text", $WaitText[$index]) | Out-Null
    }

    $safeName = ($checkpoint -replace '[^A-Za-z0-9._-]+', '-')
    $snapshot = Invoke-AgentBrowser @("snapshot", "-i", "--json")
    Save-Redacted (Join-Path $OutputDir "$safeName-snapshot.json") $snapshot

    try {
        $network = Invoke-AgentBrowser @("network", "requests", "--json")
        Save-Redacted (Join-Path $OutputDir "$safeName-network.json") $network
    } catch {
        Save-Redacted (Join-Path $OutputDir "$safeName-network-error.log") $_.Exception.Message
    }

    try {
        $console = Invoke-AgentBrowser @("console", "--json")
        Save-Redacted (Join-Path $OutputDir "$safeName-console.json") $console
    } catch {
        Save-Redacted (Join-Path $OutputDir "$safeName-console-error.log") $_.Exception.Message
    }

    Invoke-AgentBrowser @("screenshot", (Join-Path $screenshotDir "$safeName.png")) | Out-Null
}

Write-Output (ConvertTo-Json @{ caseId = $CaseId; session = $Session; checkpoints = $Checkpoints; outputDir = (Resolve-Path -LiteralPath $OutputDir).Path } -Compress)
