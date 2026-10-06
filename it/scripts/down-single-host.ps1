# Parada de OT-Bridge en un solo host:  powershell -ExecutionPolicy Bypass -File it\scripts\down-single-host.ps1 [-IncludeOT]
# Para el stack IT (sin borrar datos: nunca usa -v) y el simulador de planta.
# La capa OT (openplc-runtime, fuxa) se deja en marcha salvo con -IncludeOT.
# Solo ASCII (PowerShell 5.1 lee los .ps1 sin BOM como ANSI).
param([switch]$IncludeOT)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$PidFile = Join-Path $Root 'logs\field.pid'

Write-Host '[1/3] Stack IT' -ForegroundColor Cyan
& docker compose -f docker-compose.yml -f docker-compose.single-host.yml down
if ($LASTEXITCODE -eq 0) { Write-Host '      OK   parado (volumenes conservados)' -ForegroundColor Green }
else { Write-Host '      AVISO docker compose down ha fallado' -ForegroundColor Yellow }

Write-Host '[2/3] Simulador de planta' -ForegroundColor Cyan
$stopped = $false
if (Test-Path $PidFile) {
    $simPid = [int](Get-Content $PidFile -Raw).Trim()
    $proc = Get-Process -Id $simPid -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -like 'python*') {
        Stop-Process -Id $simPid -Force
        $stopped = $true
        Write-Host "      OK   parado (PID $simPid)" -ForegroundColor Green
    }
    Remove-Item $PidFile -Force
}
if (-not $stopped) {
    $owner = Get-NetTCPConnection -State Listen -LocalPort 5020 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($owner) {
        Write-Host "      AVISO el puerto 5020 sigue ocupado (PID $($owner.OwningProcess)), no lo lanzo este script: cierralo a mano" -ForegroundColor Yellow
    } else {
        Write-Host '      OK   no estaba en marcha' -ForegroundColor Green
    }
}

Write-Host '[3/3] Capa OT' -ForegroundColor Cyan
if ($IncludeOT) {
    & docker stop fuxa openplc-runtime 2>&1 | Out-Null
    Write-Host '      OK   fuxa y openplc-runtime parados' -ForegroundColor Green
} else {
    Write-Host '      sin cambios: openplc-runtime y fuxa siguen en marcha (usa -IncludeOT para pararlos)'
}
