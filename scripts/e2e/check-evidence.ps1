param(
    [Parameter(Mandatory = $true)]
    [string]$Root
)

$ErrorActionPreference = "Stop"
$issues = [System.Collections.Generic.List[string]]::new()
$secretPattern = 'sk-[A-Za-z0-9]{20,}|(api[_-]?key|authorization|secret|password)\s*[:=]\s*[^\s,}]+'

if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    Write-Error "Evidence root does not exist: $Root"
    exit 1
}

$caseDirectories = @(Get-ChildItem -LiteralPath $Root -Directory)
if ($caseDirectories.Count -eq 0) { $issues.Add("No case evidence directories found") }

foreach ($caseDirectory in $caseDirectories) {
    $resultPath = Join-Path $caseDirectory.FullName "result.json"
    $eventsPath = Join-Path $caseDirectory.FullName "events.ndjson"
    $probePath = Join-Path $caseDirectory.FullName "media-probe.json"
    foreach ($required in @($resultPath, $eventsPath, $probePath)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { $issues.Add("Missing evidence: $required") }
    }
    if (Test-Path -LiteralPath $resultPath -PathType Leaf) {
        try {
            $result = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
            if ($result.status -notin @("passed", "failed", "blocked_external")) { $issues.Add("Invalid status in $resultPath") }
        } catch { $issues.Add("Invalid JSON: $resultPath") }
    }
    foreach ($textPath in @($resultPath, $eventsPath, $probePath)) {
        if (Test-Path -LiteralPath $textPath -PathType Leaf) {
            $text = Get-Content -Raw -LiteralPath $textPath
            if ($text -match $secretPattern) { $issues.Add("Possible secret in $textPath") }
        }
    }
    $screenshots = Join-Path $caseDirectory.FullName "screenshots"
    if (Test-Path -LiteralPath $screenshots -PathType Container) {
        $pngs = @(Get-ChildItem -LiteralPath $screenshots -File -Filter "*.png")
        if ($pngs.Count -eq 0) { $issues.Add("Screenshot directory is empty: $screenshots") }
        foreach ($png in $pngs) {
            if ($png.Length -lt 100) { $issues.Add("Blank screenshot: $($png.FullName)") }
        }
    }
}

if ($issues.Count -gt 0) {
    $issues | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Output (ConvertTo-Json @{ root = (Resolve-Path -LiteralPath $Root).Path; cases = $caseDirectories.Count; status = "ok" } -Compress)
exit 0
