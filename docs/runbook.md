# Runbook — OT-Bridge

> Operación y diagnóstico. Instalación: [INSTALL.md](../INSTALL.md). Arquitectura: [architecture.md](architecture.md).
> Salvo indicación, los comandos `docker compose` se ejecutan desde `it/`. Los scripts de diagnóstico que usan
> pymodbus o asyncua (`test_read_plc.py`, `test_opcua.py`) necesitan `pip install -r it/requirements-dev.txt`.
> La restauración real (§5) se valida con `restore_test.ps1` en contenedores aislados, sin tocar el stack en marcha.

## 1. Arranque / parada

Con el instalador (desde la raíz del repositorio):

```bash
python otb.py status         # 13 servicios y su salud
python otb.py stop           # para todo; los volúmenes se conservan
python otb.py start          # arranca todo y recarga el programa del PLC
python otb.py deploy-plc     # solo el PLC (el runtime arranca vacío tras reiniciar su contenedor)
```

Servicio a servicio, con Docker Compose:

```powershell
docker compose up -d              # arranca los 10 servicios
docker compose ps                 # todos deben estar (healthy)
docker compose down               # parada total (los volúmenes se conservan)
docker compose logs -f <servicio> # logs de un servicio (rotan: 3 x 10 MB por contenedor)
docker compose up -d --build --no-deps <servicio>   # reconstruir un solo servicio sin tocar el resto
```

El orden lo gestiona compose (`depends_on` con `service_healthy`). Los servicios Python tocan
`/tmp/heartbeat` en su bucle principal; si dejan de hacerlo 90 s, Docker los marca `unhealthy`.

**Instalación nueva** (volúmenes vacíos): `python otb.py install` lo hace todo. A mano: `python scripts\ensure_secrets.py` (genera los secretos que
falten en `.env` y sustituye los marcadores de la plantilla) → `python scripts\mqtt_passwd.py` → `docker compose up -d`. InfluxDB crea usuarios,
retenciones y CQs en su primer arranque (`influxdb/init`); PostgreSQL, el esquema por Flyway.
**Instalación existente** tras cambiar credenciales: `python scripts\influx_users.py`,
`python scripts\postgres_roles.py`, `python scripts\mqtt_passwd.py` (todos idempotentes).

## 2. Verificación rápida

La API exige la cabecera `X-API-Key` (claves en `.env`). `/actuator/health` es libre.

```powershell
curl.exe http://localhost:8080/actuator/health                                    # {"status":"UP"}
curl.exe -H "X-API-Key: <API_KEY_GRAFANA>" http://localhost:8080/api/machines     # plc01 online
curl.exe -H "X-API-Key: <API_KEY_GRAFANA>" "http://localhost:8080/api/alarms?state=ACTIVE"
curl.exe -u reader:<INFLUX_READ_PASSWORD> -G http://localhost:8086/query --data-urlencode "db=plant" --data-urlencode "q=SELECT last(value) FROM sensor_readings GROUP BY variable"
.\venv\Scripts\python.exe scripts\check_dashboards.py      # todas las consultas de Grafana
.\venv\Scripts\python.exe scripts\test_opcua.py            # OPC UA cifrado + usuario
.\venv\Scripts\python.exe scripts\test_read_plc.py         # lectura Modbus directa del PLC (FC03)
```

Grafana: `http://localhost:3000` · FUXA (SCADA OT): `http://localhost:1881` (o el host OT).

## 3. Diagnóstico por servicio (origen → destino)

Flujo: **PLC → gateway → mosquitto → historian / plant-api / alarm-engine / opcua-server /
digital-twin → InfluxDB / PostgreSQL → Grafana**. Se corta donde se detiene la cadena:

| Síntoma | Comprobación | Causa habitual / solución |
|---|---|---|
| Alarma CRITICAL `comunicacion` | `Test-NetConnection <PLC_HOST> -Port 502` | Host OT caído o IP cambiada → `PLC_HOST` en `.env` y `docker compose up -d --no-deps gateway`. Mientras dura, el resto de alarmas quedan **congeladas** (no se resuelven en falso); al volver los datos se reevalúan |
| Sin telemetría | `docker compose logs gateway` | Modbus rechazado (firewall del host OT) o IP cambiada. Con el broker caído el gateway descarta (cola máx. 5000) y lo resume cada 60 s |
| Datos en MQTT pero no en histórico | `docker compose logs historian` | InfluxDB caído → reintenta solo; al parar vacía el búfer |
| API sin datos nuevos | `docker compose logs plant-api` (buscar "MQTT conectado ... suscrito") | La API reconecta sola con sesión persistente. Si no aparece "suscrito" tras una reconexión, `docker compose restart plant-api` |
| 401/403 en la API | cabecera `X-API-Key` | 401 = sin clave o clave errónea; 403 = clave de solo lectura en un POST/PUT (usar `API_KEY_OPERATOR`) |
| Alarma abierta en la API que el motor ya no ve | esperar 30 s | El alarm-engine reconcilia cada 30 s con la API (reabre o cierra lo que falte) |
| SCADA sin alarmas IT | `Test-NetConnection <IT_HOST> -Port 1883` desde el host OT | Regla de firewall 1883 del host IT ([network.md](network.md)) |
| Servicio `unhealthy` | `docker inspect --format "{{json .State.Health}}" <c>` | Bucle principal bloqueado → `docker compose restart <servicio>` y revisar logs |

## 4. Operaciones habituales

- **Reconocer alarma:** `POST /api/alarms/{id}/acknowledge` `{"ackBy":"operador"}` con `API_KEY_OPERATOR`; en FUXA, campana → reconocer.
- **Ajustar reglas de alarma:** `PUT /api/thresholds/{id}` (con `deadband` = histéresis y `delaySeconds` = retardo). El motor las recarga cada 30 s; si una regla se desactiva con su alarma activa, la alarma se resuelve.
- **Rotar una contraseña MQTT:** cambiarla en `.env` → `python scripts\mqtt_passwd.py` (regenera y valida `passwd`, recarga el broker) → `docker compose up -d` para que los clientes la tomen.
- **Histórico:** `rp_30d` (crudo 1 Hz, 30 días) y `rp_1y` (agregados de 1 min, 1 año, por continuous queries). Esquema en `influxdb/init/schema.influxql`; en una instalación existente se aplica con `python scripts\influx_schema.py`.

## 5. Backup y restauración

### Backup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup.ps1 [-BackupDir D:\otb-backups] [-SkipFuxa]
```

Genera `<BackupDir>\<fecha>\` (por defecto `backups\`, o `BACKUP_DIR` de `.env`) con el volcado de PostgreSQL (`--clean --if-exists`), el backup portable de InfluxDB, `grafana.db`, el estado del alarm-engine, el proyecto FUXA (solo lectura), la configuración de mosquitto, el esquema de InfluxDB, recuentos de referencia y `manifest.sha256`. Si algún paso falla, sale con código 1 y el directorio queda como `*_INCOMPLETO`. Rotación: 7 más recientes + el último de cada una de las 4 últimas semanas. **El `.env` no se incluye**: guárdalo aparte.

Programar a diario (PowerShell como administrador):

```powershell
schtasks /Create /TN "OT-Bridge backup" /SC DAILY /ST 02:30 /RL HIGHEST /F /TR "powershell -NoProfile -ExecutionPolicy Bypass -File <ruta-del-repo>\it\scripts\backup.ps1"
```

Recomendado: `BACKUP_DIR` en un disco distinto del sistema.

### Prueba de restauración (sin tocar el stack)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restore_test.ps1 [-Backup backups\<fecha>]
```

Restaura en contenedores temporales sin red, compara hashes y recuentos (PostgreSQL, InfluxDB, CQs, retenciones) y los elimina. Ejecutarla tras cambios en el backup y periódicamente.

### Restauración real

**PostgreSQL** (el dump borra y recrea las tablas; el rol `grafana_ro` debe existir → `python scripts\postgres_roles.py`):

```powershell
docker compose stop plant-api alarm-engine
docker cp backups\<fecha>\postgres_plant.sql otb-postgres:/tmp/restore.sql
docker exec otb-postgres psql -U plant -d plant -v ON_ERROR_STOP=1 -f /tmp/restore.sql
docker compose start plant-api alarm-engine
```

**InfluxDB** (`restore -db` no sobrescribe una BD existente ni recupera las CQs):

```powershell
docker compose stop historian
docker exec otb-influxdb influx -username <INFLUX_ADMIN_USER> -password <INFLUX_ADMIN_PASSWORD> -execute "DROP DATABASE plant"
docker cp backups\<fecha>\influx otb-influxdb:/tmp/restore
docker exec otb-influxdb influxd restore -portable -db plant -host 127.0.0.1:8088 /tmp/restore
python scripts\influx_schema.py        # CQs (las retenciones ya vienen en el backup)
python scripts\influx_users.py         # permisos de historian_w / reader
docker compose start historian
```

**Grafana y alarm-engine:** `docker compose stop <servicio>`, `docker cp` del fichero a su ruta (`/var/lib/grafana/grafana.db`, `/app/data/alarm_state.json`) y `docker compose start <servicio>`. Los dashboards no hace falta restaurarlos: se generan desde `grafana/generator`.
**FUXA:** `python ..\ot\scada\hmi\deploy.py --target plant --rollback backups\<fecha>\plant-<stamp>.json` (modifica el SCADA de planta: confirmar antes).

## 6. Qué hacer si...

- **Se corta la luz / se reinicia el host IT:** `docker compose up -d` — todo vuelve (probado).
- **Cambia la IP del host OT:** `PLC_HOST` en `.env` → `docker compose up -d --no-deps gateway`.
- **Cambia la IP del host IT:** `MQTT_LAN_BIND` en `.env` → `docker compose up -d mosquitto` (y la IP del broker en FUXA).
- **Rotan las IPs (DHCP):** reservar DHCP en el router para ambos hosts y revisar las reglas de firewall.
- **El PLC no arranca tras reiniciar el contenedor:** es lo esperado. El runtime arranca vacío; despliega el programa con **Build** desde OpenPLC Editor.
- **Un servicio no arranca:** `docker compose logs <servicio>` y consultar la sección 3.
- **Se pierde `mosquitto/config/passwd`:** `python scripts\mqtt_passwd.py` lo regenera desde `.env`.
