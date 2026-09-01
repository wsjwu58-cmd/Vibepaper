$ErrorActionPreference = "Stop"
$checker = Join-Path $PSScriptRoot "..\check-evidence.ps1"
$fixture = Join-Path ([System.IO.Path]::GetTempPath()) ("vibepaper-evidence-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path (Join-Path $fixture "case-1") -Force | Out-Null
try {
    $resultPath = Join-Path $fixture "case-1\result.json"
    $eventsPath = Join-Path $fixture "case-1\events.ndjson"
    $probePath = Join-Path $fixture "case-1\media-probe.json"
    '{"caseId":"case-1","status":"passed"}' | Set-Content -LiteralPath $resultPath -Encoding utf8
    '' | Set-Content -LiteralPath $eventsPath -Encoding utf8
    '{"status":"not_run"}' | Set-Content -LiteralPath $probePath -Encoding utf8
    & $checker -Root $fixture | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "valid evidence should pass" }

    Remove-Item -LiteralPath $probePath
    & pwsh -NoProfile -File $checker -Root $fixture 2>$null
    $checkerExitCode = $LASTEXITCODE
    if ($checkerExitCode -eq 0) { throw "missing media probe should fail" }
    Write-Output "check-evidence tests passed"
} finally {
    if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
