param(
    [switch]$SkipPython
)

$ErrorActionPreference = "Stop"
$root = "E:\VibePaperProject"
$logDir = "$root\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$javaServices = @(
    @{ Name = "identity-service";  Port = 8081 },
    @{ Name = "canvas-service";    Port = 8082 },
    @{ Name = "asset-service";     Port = 8083 },
    @{ Name = "billing-service";   Port = 8084 },
    @{ Name = "enterprise-service";Port = 8085 },
    @{ Name = "gallery-service";   Port = 8086 },
    @{ Name = "admin-service";     Port = 8087 },
    @{ Name = "vibepaper-gateway"; Port = 8080 }
)

foreach ($svc in $javaServices) {
    $jar = Get-ChildItem "$root\vibepaper-services\$($svc.Name)\target\*.jar" |
        Where-Object { $_.Name -notlike "*sources*" -and $_.Name -notlike "*original*" } |
        Select-Object -First 1
    if (-not $jar) {
        Write-Host "SKIP $($svc.Name): jar not found"
        continue
    }
    Start-Process -FilePath "java" -ArgumentList "-jar", "`"$($jar.FullName)`"" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput "$logDir\$($svc.Name).log" `
        -RedirectStandardError "$logDir\$($svc.Name).err.log"
    Write-Host "STARTED $($svc.Name) ($($svc.Port))"
}

if (-not $SkipPython) {
    Start-Process -FilePath "$root\generation-service\.venv\Scripts\uvicorn.exe" `
        -ArgumentList "src.generation.main:app", "--host", "0.0.0.0", "--port", "8090" `
        -WorkingDirectory "$root\generation-service" -WindowStyle Hidden `
        -RedirectStandardOutput "$logDir\generation-service.log" `
        -RedirectStandardError "$logDir\generation-service.err.log"
    Write-Host "STARTED generation-service (8090)"

    Start-Process -FilePath "$root\agent-service\.venv\Scripts\uvicorn.exe" `
        -ArgumentList "src.agent.main:app", "--host", "0.0.0.0", "--port", "8091" `
        -WorkingDirectory "$root\agent-service" -WindowStyle Hidden `
        -RedirectStandardOutput "$logDir\agent-service.log" `
        -RedirectStandardError "$logDir\agent-service.err.log"
    Write-Host "STARTED agent-service (8091)"

    # Celery：clock 唤醒 / 记忆队列（agent 进程内也有 inline scanner 兜底）
    # Windows 不支持 worker --beat 合并；worker / beat 必须分进程
    # 注意：勿用 $celery 作变量名——部分环境下会被污染成 $null，导致 Test-Path 失败
    $celeryExe = Join-Path $root "agent-service\.venv\Scripts\celery.exe"
    if (Test-Path -LiteralPath $celeryExe) {
        Start-Process -FilePath $celeryExe `
            -ArgumentList "-A", "src.agent.workers.celery_app.celery_app", "worker", "-l", "info", "-P", "solo" `
            -WorkingDirectory "$root\agent-service" -WindowStyle Hidden `
            -RedirectStandardOutput "$logDir\agent-celery.log" `
            -RedirectStandardError "$logDir\agent-celery.err.log"
        Start-Process -FilePath $celeryExe `
            -ArgumentList "-A", "src.agent.workers.celery_app.celery_app", "beat", "-l", "info" `
            -WorkingDirectory "$root\agent-service" -WindowStyle Hidden `
            -RedirectStandardOutput "$logDir\agent-celery-beat.log" `
            -RedirectStandardError "$logDir\agent-celery-beat.err.log"
        Write-Host "STARTED agent-celery (worker + beat)"
    }
}

Write-Host "All services launched. Logs: $logDir"
