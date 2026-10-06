# Arranque de OT-Bridge en un solo host (OT + IT en la misma maquina).
#   powershell -ExecutionPolicy Bypass -File it\scripts\up-single-host.ps1
#   1 Docker Desktop   2 OT: openplc-runtime + fuxa (ot/scada/docker-compose.yml)   3 simulador de planta (--headless)
#   4 prerequisitos    5 stack IT (docker-compose.yml + docker-compose.single-host.yml)   6 espera a healthy
#   7 FUXA -> broker mosquitto:1883   8 prueba rapida   9 navegador
# Idempotente: se puede lanzar con todo ya arrancado. Solo ASCII (PowerShell 5.1 lee los .ps1 sin BOM como ANSI).
param(
    [switch]$NoBrowser,
    [switch]$SkipBuild,
    [int]$HealthTimeoutS = 600
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root 'venv\Scripts\python.exe'
$RepoRoot = Split-Path -Parent $Root
$FieldDir = Join-Path $RepoRoot 'ot\field'
$OtCompose = Join-Path $RepoRoot 'ot\scada\docker-compose.yml'
$LogDir = Join-Path $Root 'logs'
$ComposeArgs = @('compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.single-host.yml')
$Services = @('mosquitto', 'influxdb', 'historian', 'grafana', 'postgres', 'plant-api', 'alarm-engine',
              'gateway', 'opcua-server', 'digital-twin')
$OtContainers = @('openplc-runtime', 'fuxa')
$DockerDesktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
$warnings = New-Object System.Collections.Generic.List[string]

function Step($n, $msg) { Write-Host ""; Write-Host "[$n/9] $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "      OK   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "      AVISO $msg" -ForegroundColor Yellow; $warnings.Add($msg) }
function Fail($msg) {
    Write-Host "      ERROR $msg" -ForegroundColor Red
    Write-Host ""
    Write-Host "Arranque detenido. Corrige el error y vuelve a lanzar el script (es seguro repetirlo)." -ForegroundColor Red
    exit 1
}
function Test-Port([int]$port) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}
function Test-Docker {
    & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}
function Get-ContainerState([string]$name) {
    $state = & docker inspect -f '{{.State.Status}}' $name 2>$null
    if ($LASTEXITCODE -ne 0) { return 'missing' }
    return "$state".Trim()
}

Write-Host 'OT-Bridge - arranque en un solo host' -ForegroundColor White

# 1 ------------------------------------------------------------------------------------------------
Step 1 'Docker Desktop'
if (-not (Test-Docker)) {
    if (-not (Test-Path $DockerDesktop)) { Fail "Docker no responde y no encuentro $DockerDesktop" }
    Write-Host '      arrancando Docker Desktop (hasta 3 min)...'
    Start-Process -FilePath $DockerDesktop | Out-Null
    $deadline = (Get-Date).AddSeconds(180)
    while (-not (Test-Docker)) {
        if ((Get-Date) -gt $deadline) { Fail 'Docker Desktop no ha arrancado en 3 minutos' }
        Start-Sleep -Seconds 5
    }
}
Ok ("Docker " + (& docker info --format '{{.ServerVersion}}' 2>$null))

# 2 ------------------------------------------------------------------------------------------------
Step 2 'Capa OT: PLC y SCADA FUXA'
foreach ($name in $OtContainers) {
    $state = Get-ContainerState $name
    if ($state -eq 'missing') {
        & docker compose -f $OtCompose up -d $name 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "no se pudo crear $name (docker compose -f ot\scada\docker-compose.yml up -d)" }
    }
    elseif ($state -ne 'running') {
        & docker start $name 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "no se pudo arrancar $name (docker start $name)" }
    }
    Ok "$name en marcha"
}
& docker network inspect fuxa_default 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'no existe la red Docker fuxa_default (la crea ot/scada/docker-compose.yml)' }
foreach ($name in @('openplc-runtime', 'fuxa')) {
    $nets = & docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' $name 2>$null
    if ("$nets" -notmatch 'fuxa_default') { Fail "$name no esta en la red fuxa_default (red actual: $nets)" }
}
Ok 'red fuxa_default con openplc-runtime y fuxa'

# 3 ------------------------------------------------------------------------------------------------
Step 3 'Simulador de planta (:5020 sensores, :5021 actuadores, :5022 instructor)'
if (-not (Test-Path $Py)) { Fail "falta el entorno Python: py -3 -m venv venv; .\venv\Scripts\pip install -r requirements-dev.txt" }
New-Item -ItemType Directory -Force $LogDir | Out-Null
if (Test-Port 5020) {
    Ok 'ya estaba en marcha (puerto 5020 escuchando)'
} else {
    if (-not (Test-Path (Join-Path $FieldDir 'main.py'))) { Fail "no encuentro el simulador en $FieldDir" }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $proc = Start-Process -FilePath $Py -ArgumentList '-u', 'main.py', '--headless' -WorkingDirectory $FieldDir `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $LogDir "field-$stamp.log") `
        -RedirectStandardError (Join-Path $LogDir "field-$stamp.err.log")
    Set-Content -Path (Join-Path $LogDir 'field.pid') -Value $proc.Id -Encoding ascii
    $deadline = (Get-Date).AddSeconds(20)
    while (-not ((Test-Port 5020) -and (Test-Port 5021) -and (Test-Port 5022))) {
        if ($proc.HasExited) { Fail "el simulador se ha cerrado: revisa logs\field-$stamp.err.log" }
        if ((Get-Date) -gt $deadline) { Fail "el simulador no abre los puertos 5020-5022: revisa logs\field-$stamp.err.log" }
        Start-Sleep -Milliseconds 500
    }
    Ok "arrancado en segundo plano (PID $($proc.Id), log logs\field-$stamp.log)"
}

# 4 ------------------------------------------------------------------------------------------------
Step 4 'Prerequisitos del stack IT'
if (-not (Test-Path '.env')) { Fail 'falta .env en la raiz' }
if (-not (Test-Path 'mosquitto\config\passwd')) { Fail 'falta mosquitto\config\passwd (python scripts\mqtt_passwd.py)' }
$envText = Get-Content '.env' -Raw
foreach ($key in @('MQTT_LAN_BIND', 'MQTT_PASSWORD_FUXA', 'FUXA_ADMIN_PASSWORD', 'API_KEY_GRAFANA')) {
    if ($envText -notmatch "(?m)^$key=\S") { Fail "falta $key en .env" }
}
Ok '.env y passwd presentes'

# 5 ------------------------------------------------------------------------------------------------
Step 5 'Stack IT (10 servicios)'
$upArgs = $ComposeArgs + @('up', '-d')
if (-not $SkipBuild) { $upArgs += '--build' }
Write-Host '      la primera vez construye las imagenes (5-10 min, necesita internet)...'
& docker @upArgs
if ($LASTEXITCODE -ne 0) { Fail 'docker compose up ha fallado (mira el mensaje de arriba)' }
Ok 'contenedores creados'

# 6 ------------------------------------------------------------------------------------------------
Step 6 "Esperando a que los 10 servicios esten healthy (max $HealthTimeoutS s)"
$deadline = (Get-Date).AddSeconds($HealthTimeoutS)
while ($true) {
    $rows = & docker @ComposeArgs ps --all --format '{{.Service}}|{{.State}}|{{.Health}}' 2>$null
    $status = @{}
    foreach ($row in $rows) { $p = "$row".Split('|'); if ($p.Count -ge 3) { $status[$p[0]] = $p } }
    $pending = @($Services | Where-Object { -not $status.ContainsKey($_) -or $status[$_][2] -ne 'healthy' })
    if ($pending.Count -eq 0) { break }
    if ((Get-Date) -gt $deadline) {
        foreach ($svc in $pending) {
            $st = if ($status.ContainsKey($svc)) { "$($status[$svc][1]) $($status[$svc][2])" } else { 'no creado' }
            Write-Host "      $svc : $st" -ForegroundColor Red
            & docker @ComposeArgs logs --tail 15 $svc
        }
        Fail ("servicios sin healthy: " + ($pending -join ', '))
    }
    Write-Host ("      pendientes: " + ($pending -join ', '))
    Start-Sleep -Seconds 10
}
Ok 'los 10 servicios healthy'

# 7 ------------------------------------------------------------------------------------------------
Step 7 'SCADA FUXA -> broker IT (mqtt://mosquitto:1883)'
& $Py scripts\fuxa_set_broker.py --fuxa http://localhost:1881 --broker mqtt://mosquitto:1883
if ($LASTEXITCODE -eq 0) { Ok 'IT-Broker de FUXA apuntando a mosquitto' }
else { Warn 'no se pudo cambiar el broker de FUXA (la tarjeta de alarmas IT de FUXA no tendra datos)' }

# 8 ------------------------------------------------------------------------------------------------
Step 8 'Prueba rapida de extremo a extremo (PLC -> gateway -> MQTT -> InfluxDB y API)'
& $Py scripts\smoke_test.py --quick
if ($LASTEXITCODE -eq 0) { Ok 'prueba rapida superada' }
else { Warn 'la prueba rapida tiene fallos (mira [ERR] arriba); el stack sigue arrancado' }

# 9 ------------------------------------------------------------------------------------------------
Step 9 'Listo'
$links = [ordered]@{
    'SCADA FUXA (OT)'      = 'http://localhost:1881'
    'Grafana (IT)'         = 'http://localhost:3000'
    'OpenPLC runtime'      = 'https://localhost:8443'
    'API REST (X-API-Key)' = 'http://localhost:8080/api/machines'
}
foreach ($k in $links.Keys) { Write-Host ("      {0,-22} {1}" -f $k, $links[$k]) }
Write-Host '      OPC UA                 opc.tcp://localhost:4840'
if (-not $NoBrowser) {
    Start-Process 'http://localhost:1881'
    Start-Process 'http://localhost:3000'
}
Write-Host ""
if ($warnings.Count -eq 0) {
    Write-Host 'OT-Bridge en marcha: todo OK.' -ForegroundColor Green
} else {
    Write-Host "OT-Bridge en marcha con $($warnings.Count) aviso(s):" -ForegroundColor Yellow
    $warnings | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}
exit 0
