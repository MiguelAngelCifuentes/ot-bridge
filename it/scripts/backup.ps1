# Backup de OT-Bridge (stack IT).
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\backup.ps1 [-BackupDir D:\otb-backups] [-SkipFuxa]
#
# Genera <BackupDir>\<yyyyMMdd_HHmmss>\ con:
#   postgres_plant.sql   pg_dump --clean --if-exists (restaurable sobre una BD existente), UTF-8 sin BOM
#   influx\              influxd backup -portable -db plant (retenciones, CQs y datos)
#   grafana.db           BD de Grafana (usuarios, preferencias; los dashboards salen del generador)
#   alarm_state.json     estado persistido del alarm-engine
#   fuxa-plant-*.json    proyecto FUXA de la planta (solo lectura via API; se omite si no responde)
#   influx_schema.influxql  retenciones y CQs (restore -db no recupera las CQs; se reaplican)
#   mosquitto.conf, mosquitto_acl.txt   (el passwd NO: se regenera desde .env con scripts\mqtt_passwd.py)
#   reference.json       recuentos de referencia en T0 para scripts\restore_test.ps1
#   manifest.sha256      suma SHA-256 de cada fichero
# Rotacion: se conservan los 7 backups mas recientes y el ultimo de cada una de las 4 ultimas semanas.
# Si algun paso critico falla, el directorio se renombra a *_INCOMPLETO, se ignora en la rotacion y el
# script termina con codigo 1 (visible en la tarea programada).
# Nota: el .env (secretos) no se incluye; guardalo aparte en un lugar seguro.

param(
    [string]$BackupDir = "",
    [switch]$SkipFuxa
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$e = @{}
Get-Content .env | Where-Object { $_ -match '^[A-Za-z_0-9]+=' } | ForEach-Object {
    $q = $_ -split '=', 2; $e[$q[0]] = $q[1].Trim()
}
if (-not $BackupDir) { $BackupDir = if ($e['BACKUP_DIR']) { $e['BACKUP_DIR'] } else { Join-Path $root "backups" } }

# Ejecuta un comando nativo; falla si su codigo de salida no es 0 (en PS 5.1 $ErrorActionPreference no lo detecta)
function Invoke-Native {
    param([string]$Step, [string]$Exe, [string[]]$Arguments)
    $ErrorActionPreference = "Continue"
    $out = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) {
        throw "$Step fallo (codigo $LASTEXITCODE): $(($out | Select-Object -Last 5) -join ' | ')"
    }
    return $out
}

function Get-InfluxScalar([string]$Query) {
    $args_ = @("exec", "otb-influxdb", "influx", "-username", $e['INFLUX_READ_USER'], "-password", $e['INFLUX_READ_PASSWORD'],
               "-database", "plant", "-format", "csv", "-execute", $Query)
    $lines = Invoke-Native "Consulta InfluxDB" "docker" $args_
    $row = $lines | Where-Object { $_ -match '^[^,]+,\d' } | Select-Object -First 1
    if (-not $row) { return 0 }
    return [int64]($row -split ',')[-1]
}

function Get-PgScalar([string]$Query) {
    $v = Invoke-Native "Consulta PostgreSQL" "docker" @("exec", "otb-postgres", "psql", "-U", $e['POSTGRES_USER'],
                                                         "-d", $e['POSTGRES_DB'], "-tAc", $Query)
    return [int64](($v | Select-Object -First 1).Trim())
}

$stamp = Get-Date -Format yyyyMMdd_HHmmss
$dir = Join-Path $BackupDir $stamp
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$ok = $true

try {
    Write-Host "==> Recuentos de referencia (T0)"
    $t0 = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $maxAlarm = Get-PgScalar "select coalesce(max(id),0) from alarms"
    $window = "time <= $($t0)s AND time > $($t0)s - 29d"
    $reference = [ordered]@{
        t0          = $t0
        pg          = [ordered]@{
            alarms_upto_max_id = Get-PgScalar "select count(*) from alarms where id <= $maxAlarm"
            max_alarm_id       = $maxAlarm
            thresholds         = Get-PgScalar "select count(*) from thresholds"
            sensors            = Get-PgScalar "select count(*) from sensors"
            machines           = Get-PgScalar "select count(*) from machines"
            flyway             = Get-PgScalar "select count(*) from flyway_schema_history where success"
        }
        influx      = [ordered]@{
            sensor_readings = Get-InfluxScalar "SELECT count(value) FROM rp_30d.sensor_readings WHERE $window"
            sensor_1m       = Get-InfluxScalar "SELECT count(mean) FROM rp_1y.sensor_readings_1m WHERE $window"
        }
    }
    [IO.File]::WriteAllText((Join-Path $dir "reference.json"), ($reference | ConvertTo-Json -Depth 4), $utf8)

    Write-Host "==> PostgreSQL (pg_dump --clean --if-exists)"
    Invoke-Native "pg_dump" "docker" @("exec", "otb-postgres", "pg_dump", "-U", $e['POSTGRES_USER'], "-d", $e['POSTGRES_DB'],
                                     "--clean", "--if-exists", "-f", "/tmp/otb_dump.sql") | Out-Null
    Invoke-Native "Copia del dump" "docker" @("cp", "otb-postgres:/tmp/otb_dump.sql", "$dir\postgres_plant.sql") | Out-Null
    Invoke-Native "Limpieza" "docker" @("exec", "otb-postgres", "rm", "-f", "/tmp/otb_dump.sql") | Out-Null
    if ((Get-Item "$dir\postgres_plant.sql").Length -lt 1024) { throw "Dump de PostgreSQL sospechosamente pequeno" }

    Write-Host "==> InfluxDB (backup portable de la BD plant)"
    Invoke-Native "Limpieza" "docker" @("exec", "otb-influxdb", "rm", "-rf", "/tmp/otb_influx") | Out-Null
    Invoke-Native "influxd backup" "docker" @("exec", "otb-influxdb", "influxd", "backup", "-portable", "-db", "plant",
                                            "-host", "127.0.0.1:8088", "/tmp/otb_influx") | Out-Null
    Invoke-Native "Copia del backup Influx" "docker" @("cp", "otb-influxdb:/tmp/otb_influx", "$dir\influx") | Out-Null
    Invoke-Native "Limpieza" "docker" @("exec", "otb-influxdb", "rm", "-rf", "/tmp/otb_influx") | Out-Null
    if (-not (Get-ChildItem "$dir\influx" -Filter *.manifest)) { throw "Backup de InfluxDB sin manifiesto" }

    Write-Host "==> Grafana y alarm-engine"
    Invoke-Native "Copia de grafana.db" "docker" @("cp", "otb-grafana:/var/lib/grafana/grafana.db", "$dir\grafana.db") | Out-Null
    Invoke-Native "Copia del estado del alarm-engine" "docker" @("cp", "otb-alarm-engine:/app/data/alarm_state.json",
                                                               "$dir\alarm_state.json") | Out-Null

    Write-Host "==> Mosquitto (sin passwd)"
    Copy-Item mosquitto\config\mosquitto.conf "$dir\mosquitto.conf"
    Copy-Item mosquitto\config\acl "$dir\mosquitto_acl.txt"
    # influxd restore -db no recupera las continuous queries: se reaplican desde este fichero
    Copy-Item influxdb\init\schema.influxql "$dir\influx_schema.influxql"
}
catch {
    $ok = $false
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

if ($ok -and -not $SkipFuxa) {
    Write-Host "==> Proyecto FUXA de la planta (solo lectura)"
    try {
        $py = if (Test-Path "venv\Scripts\python.exe") { "venv\Scripts\python.exe" } else { "python" }
        Invoke-Native "Backup FUXA" $py @("..\ot\scada\hmi\deploy.py", "--target", "plant", "--backup-only", "--out", $dir) | Out-Null
    }
    catch { Write-Host "AVISO: proyecto FUXA no copiado (FUXA no disponible?): $($_.Exception.Message)" -ForegroundColor Yellow }
}

if (-not $ok) {
    Rename-Item $dir "$($stamp)_INCOMPLETO"
    Write-Host "Backup INCOMPLETO: $($dir)_INCOMPLETO" -ForegroundColor Red
    exit 1
}

Write-Host "==> Manifiesto SHA-256"
$lines = Get-ChildItem $dir -Recurse -File | Where-Object { $_.Name -ne "manifest.sha256" } | Sort-Object FullName |
    ForEach-Object {
        $rel = $_.FullName.Substring($dir.Length + 1).Replace('\', '/')
        "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $rel"
    }
[IO.File]::WriteAllLines((Join-Path $dir "manifest.sha256"), [string[]]$lines, $utf8)

Write-Host "==> Rotacion (7 recientes + ultimo de 4 semanas)"
$all = Get-ChildItem $BackupDir -Directory | Where-Object { $_.Name -match '^\d{8}_\d{6}$' } |
    Sort-Object Name -Descending
$keep = @{}
$all | Select-Object -First 7 | ForEach-Object { $keep[$_.Name] = $true }
$cal = [Globalization.CultureInfo]::InvariantCulture.Calendar
$all | Group-Object {
    $d = [datetime]::ParseExact($_.Name.Substring(0, 8), "yyyyMMdd", $null)
    "$($d.Year)-$($cal.GetWeekOfYear($d, 'FirstFourDayWeek', 'Monday'))"
} | Select-Object -First 4 | ForEach-Object { $keep[$_.Group[0].Name] = $true }
$all | Where-Object { -not $keep[$_.Name] } | ForEach-Object {
    Remove-Item $_.FullName -Recurse -Force
    Write-Host "  eliminado $($_.Name)"
}

$size = (Get-ChildItem $dir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Backup completado en {0} ({1:N1} MB, {2} ficheros); conservados: {3}" -f $dir, $size, $lines.Count, $keep.Count)
exit 0
