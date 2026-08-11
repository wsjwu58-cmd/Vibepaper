$names = @(
    "identity-service", "canvas-service", "asset-service", "billing-service",
    "enterprise-service", "gallery-service", "admin-service", "vibepaper-gateway"
)
Get-CimInstance Win32_Process -Filter "name='java.exe'" | Where-Object {
    $_.CommandLine -match "vibepaper-services" -and ($names | Where-Object { $_.CommandLine -match $_ })
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "STOPPED $($_.ProcessId)"
}
Get-CimInstance Win32_Process -Filter "name='uvicorn.exe'" | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "STOPPED uvicorn $($_.ProcessId)"
}
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and ($_.CommandLine -match 'celery_app|agent\.workers\.celery')
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "STOPPED celery $($_.ProcessId)"
}
