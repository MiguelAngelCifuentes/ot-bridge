# Prueba de restauracion de OT-Bridge: restaura un backup en contenedores TEMPORALES y aislados
# (sin red, sin volumenes) y compara con los recuentos de referencia del backup. No toca el stack.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\restore_test.ps1 [-Backup <dir>] [-BackupDir <raiz>]
# Sin -Backup usa el mas reciente. Termina con codigo 0 si todo coincide, 1 si no.

param(
    [string]$Backup = "",
    [string]$BackupDir = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$pgImage = "postgres:16.13"
$influxImage = "influxdb:1.8.10"
$pg = "otb-restore-pg"
$influx = "otb-restore-influx"

function Invoke-Native {
    param([string]$Step, [string[]]$Arguments)
    $ErrorActionPreference = "Continue"
    $out = & docker @Arguments 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "$Step fallo (codigo $LASTEXITCODE): $(($out | Select-Object -Last 5) -join ' | ')" }
    return $out
}

function Wait-Until([string]$Step, [scriptblock]$Probe) {
    for ($i = 0; $i -lt 60; $i++) {
        $ErrorActionPreference = "Continue"
        & $Probe 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    throw "$Step no responde"
}

function Remove-TempContainers {
    $ErrorActionPreference = "Continue"
    & docker rm -f $pg $influx 2>&1 | Out-Null
}

if (-not $Backup) {
    if (-not $BackupDir) { $BackupDir = Join-Path $root "backups" }
    $Backup = (Get-ChildItem $BackupDir -Directory | Where-Object { $_.Name -match '^\d{8}_\d{6}$' } |
        Sort-Object Name -Descending | Select-Object -First 1).FullName
}
if (-not $Backup -or -not (Test-Path "$Backup\reference.json")) { throw "No hay backup valido (falta reference.json)" }
Write-Host "Backup: $Backup"
$ref = Get-Content "$Backup\reference.json" -Raw | ConvertFrom-Json
$results = New-Object System.Collections.ArrayList

function Check([string]$Name, $Expected, $Actual) {
    $okc = "$Expected" -eq "$Actual"
    [void]$results.Add([pscustomobject]@{ Comprobacion = $Name; Esperado = $Expected; Restaurado = $Actual; OK = $okc })
}

try {
    Write-Host "==> Integridad (manifest.sha256)"
    $bad = 0
    foreach ($line in Get-Content "$Backup\manifest.sha256") {
        $hash, $rel = $line -split '  ', 2
        $actual = (Get-FileHash (Join-Path $Backup $rel) -Algorithm SHA256).Hash.ToLower()
        if ($actual -ne $hash) { $bad++; Write-Host "  hash distinto: $rel" -ForegroundColor Red }
    }
    Check "ficheros con hash correcto" 0 $bad

    Remove-TempContainers
    Write-Host "==> PostgreSQL temporal ($pgImage, sin red)"
    $pgPass = [guid]::NewGuid().ToString("N")
    Invoke-Native "Arranque postgres" @("run", "-d", "--name", $pg, "--network", "none", "-e", "POSTGRES_USER=plant",
                                      "-e", "POSTGRES_DB=plant", "-e", "POSTGRES_PASSWORD=$pgPass", $pgImage) | Out-Null
    Wait-Until "postgres temporal" { docker exec $pg psql -U plant -d plant -tAc "select 1" }
    Invoke-Native "Rol grafana_ro" @("exec", $pg, "psql", "-U", "plant", "-d", "plant", "-c", "CREATE ROLE grafana_ro") | Out-Null
    Invoke-Native "Copia del dump" @("cp", "$Backup\postgres_plant.sql", "$($pg):/tmp/dump.sql") | Out-Null
    Invoke-Native "Restauracion SQL" @("exec", $pg, "psql", "-U", "plant", "-d", "plant", "-q", "-v", "ON_ERROR_STOP=1",
                                     "-f", "/tmp/dump.sql") | Out-Null
    # segunda pasada: el dump (--clean --if-exists) debe poder aplicarse sobre una BD ya poblada
    Invoke-Native "Reaplicacion del dump" @("exec", $pg, "psql", "-U", "plant", "-d", "plant", "-q", "-v", "ON_ERROR_STOP=1",
                                          "-f", "/tmp/dump.sql") | Out-Null
    $q = {
        param($sql)
        [int64]((Invoke-Native "Consulta" @("exec", $pg, "psql", "-U", "plant", "-d", "plant", "-tAc", $sql)) | Select-Object -First 1)
    }
    Check "pg alarms (id <= max)" $ref.pg.alarms_upto_max_id (& $q "select count(*) from alarms where id <= $($ref.pg.max_alarm_id)")
    Check "pg thresholds" $ref.pg.thresholds (& $q "select count(*) from thresholds")
    Check "pg sensors" $ref.pg.sensors (& $q "select count(*) from sensors")
    Check "pg machines" $ref.pg.machines (& $q "select count(*) from machines")
    Check "pg flyway" $ref.pg.flyway (& $q "select count(*) from flyway_schema_history where success")

    Write-Host "==> InfluxDB temporal ($influxImage, sin red)"
    Invoke-Native "Arranque influx" @("run", "-d", "--name", $influx, "--network", "none", $influxImage) | Out-Null
    Wait-Until "influx temporal" { docker exec $influx influx -execute "SHOW DATABASES" }
    Invoke-Native "Copia del backup" @("cp", "$Backup\influx", "$($influx):/tmp/restore") | Out-Null
    Invoke-Native "influxd restore" @("exec", $influx, "influxd", "restore", "-portable", "-db", "plant",
                                    "-host", "127.0.0.1:8088", "/tmp/restore") | Out-Null
    $iq = {
        param($query)
        $lines = Invoke-Native "Consulta Influx" @("exec", $influx, "influx", "-database", "plant", "-format", "csv",
                                                   "-execute", $query)
        $row = $lines | Where-Object { $_ -match '^[^,]+,\d' } | Select-Object -First 1
        if ($row) { [int64]($row -split ',')[-1] } else { 0 }
    }
    $window = "time <= $($ref.t0)s AND time > $($ref.t0)s - 29d"
    Check "influx sensor_readings (T0)" $ref.influx.sensor_readings (& $iq "SELECT count(value) FROM rp_30d.sensor_readings WHERE $window")
    Check "influx sensor_readings_1m (T0)" $ref.influx.sensor_1m (& $iq "SELECT count(mean) FROM rp_1y.sensor_readings_1m WHERE $window")
    # restore -db no recupera las CQs: se reaplican desde el esquema guardado (procedimiento del runbook)
    $schema = if (Test-Path "$Backup\influx_schema.influxql") { "$Backup\influx_schema.influxql" } else { "influxdb\init\schema.influxql" }
    Get-Content $schema | Where-Object { $_ -match '^CREATE CONTINUOUS QUERY' } | ForEach-Object {
        Invoke-Native "CQ" @("exec", $influx, "influx", "-execute", $_) | Out-Null
    }
    $cqs = (Invoke-Native "CQs" @("exec", $influx, "influx", "-execute", "SHOW CONTINUOUS QUERIES")) -match '^cq_'
    Check "influx continuous queries" 3 @($cqs).Count
    $rps = (Invoke-Native "RPs" @("exec", $influx, "influx", "-execute", "SHOW RETENTION POLICIES ON plant")) -match '^rp_'
    Check "influx retenciones" 2 @($rps).Count

    Write-Host "==> Resto de ficheros"
    Check "grafana.db presente" $true ((Get-Item "$Backup\grafana.db").Length -gt 0)
    Check "alarm_state.json valido" $true ([bool](Get-Content "$Backup\alarm_state.json" -Raw | ConvertFrom-Json))
}
catch {
    [void]$results.Add([pscustomobject]@{ Comprobacion = "ERROR"; Esperado = ""; Restaurado = $_.Exception.Message; OK = $false })
}
finally {
    Remove-TempContainers
}

$results | Format-Table -AutoSize
$failed = @($results | Where-Object { -not $_.OK }).Count
if ($failed -gt 0) { Write-Host "RESTAURACION: $failed comprobaciones fallidas" -ForegroundColor Red; exit 1 }
Write-Host "RESTAURACION OK: $($results.Count) comprobaciones" -ForegroundColor Green
exit 0
