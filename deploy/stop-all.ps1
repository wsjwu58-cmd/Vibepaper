$names = @(
    "identity-service", "canvas-service", "asset-service", "billing-service",
    "enterprise-service", "gallery-service", "admin-service", "vibepaper-gateway"
)
Get-CimInstance Win32_Process -Filter "name='java.exe'" | Where-Object {
    $cmd = $_.CommandLine
    $cmd -and ($cmd -match "vibepaper-services") -and ($names | Where-Object { $cmd -match [regex]::Escape($_) })
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "STOPPED java $($_.ProcessId)"
}
# CommandLine 有时为空，按端口再清一次，避免旧进程占坑导致新实例起不来、网关 503
$ports = 8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087
foreach ($port in $ports) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            $procId = $_.OwningProcess
            if ($procId -and $procId -gt 0) {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "STOPPED port $port pid $procId"
            }
        }
}
Get-NetTCPConnection -LocalPort 8090,8091 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $procId = $_.OwningProcess
    if ($procId -and $procId -gt 0) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "STOPPED agent/generation port $($_.LocalPort) pid $procId"
    }
}
