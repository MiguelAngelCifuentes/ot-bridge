# Bateria completa de pruebas de OT-Bridge (stack IT).
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1 [-Quick] [-Fuxa] [-SkipJava]
#   1. pytest de cada servicio Python (gateway, historian, alarm-engine, digital-twin)
#   2. JUnit de plant-api (contenedor maven; no hace falta Maven local)
#   3. scripts\smoke_test.py  (stack en marcha; -Quick omite la alarma de prueba)
#   4. scripts\check_dashboards.py  (todas las consultas de Grafana)
#   5. -Fuxa: pruebas del SCADA en el sandbox (fuxa\sandbox\test_hmi.py; requiere el sandbox levantado)
# Requisitos: venv con requirements-dev.txt  (.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt)

param(
    [switch]$Quick,
    [switch]$Fuxa,
    [switch]$SkipJava
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root "venv\Scripts\python.exe"
$summary = New-Object System.Collections.ArrayList

function Invoke-Suite([string]$Name, [scriptblock]$Body) {
    Write-Host "`n===== $Name" -ForegroundColor Cyan
    $ErrorActionPreference = "Continue"
    & $Body
    $code = $LASTEXITCODE
    [void]$summary.Add([pscustomobject]@{ Suite = $Name; Resultado = if ($code -eq 0) { "OK" } else { "FALLO ($code)" } })
}

foreach ($svc in "gateway", "historian", "alarm-engine", "digital-twin") {
    Invoke-Suite "pytest $svc" {
        Push-Location (Join-Path $root $svc)
        try { & $py -m pytest -q -p no:cacheprovider tests } finally { Pop-Location }
    }
}

if (-not $SkipJava) {
    Invoke-Suite "JUnit plant-api" {
        # volumen otb-m2: cache de dependencias Maven entre ejecuciones
        & docker run --rm -v "$(Join-Path $root 'api'):/build" -v otb-m2:/root/.m2 -w /build `
            maven:3.9-eclipse-temurin-21 mvn -B -q test
    }
}

$smokeArgs = @("scripts\smoke_test.py")
if ($Quick) { $smokeArgs += "--quick" }
Invoke-Suite "smoke_test" { & $py @smokeArgs }
Invoke-Suite "check_dashboards" { & $py scripts\check_dashboards.py | Select-Object -Last 3 }

if ($Fuxa) {
    Invoke-Suite "FUXA sandbox (test_hmi)" { & $py fuxa\sandbox\test_hmi.py }
}

Write-Host ""
$summary | Format-Table -AutoSize
$failed = @($summary | Where-Object { $_.Resultado -ne "OK" }).Count
if ($failed) { Write-Host "$failed suites con fallos" -ForegroundColor Red; exit 1 }
Write-Host "Todas las pruebas OK" -ForegroundColor Green
exit 0
