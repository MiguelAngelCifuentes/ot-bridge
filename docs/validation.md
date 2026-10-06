# Matriz de validación end-to-end — OT-Bridge v1.0

> Validación del sistema completo (comandos desde `it/`). Cada escenario se ejecuta con evidencia: comando + resultado.
> Los escenarios 1-6, 8-10, 15 y 17-18 están automatizados en `scripts/smoke_test.py` y `scripts/check_dashboards.py`.

| # | Escenario | Comando de verificacion | Resultado esperado | Evidencia |
|---|---|---|---|---|
| 1 | Lectura Modbus directa | `.\venv\Scripts\python.exe scripts\test_read_plc.py` | 6 registros (MW100–MW105) con valores coherentes (nivel ~5000, estado bitmask) | Salida del script |
| 2 | Telemetria MQTT | `docker exec otb-mosquitto mosquitto_sub -h 127.0.0.1 -u historian -P <pass> -t 'factory/plc01/telemetry/#' -C 6 -W 5` | 6 mensajes JSON con `ts`, `plc`, `variable`, `value`, `unit`, `q=1` | Salida de mosquitto_sub |
| 3 | Heartbeat MQTT | `docker exec otb-mosquitto mosquitto_sub -h 127.0.0.1 -u historian -P <pass> -t 'factory/plc01/status' -C 1 -W 5` | JSON con `online: true` | Salida de mosquitto_sub |
| 4 | Historizacion InfluxDB | `curl.exe -u reader:<pass> -G "http://localhost:8086/query?db=plant" --data-urlencode "q=SELECT last(value) FROM sensor_readings GROUP BY variable"` | 6+ filas (una por variable) con valores recientes | Respuesta JSON |
| 5 | API: maquinas online | `curl.exe -H "X-API-Key: <key>" http://localhost:8080/api/machines` | Lista con plc01, `online: true`, `lastValue` actualizandose | Respuesta JSON |
| 6 | API: sensores con historial | `curl.exe -H "X-API-Key: <key>" "http://localhost:8080/api/sensors/1/history?minutes=5"` | Array de puntos con `ts` y `value` | Respuesta JSON |
| 7 | Ciclo de alarma completo | Crear umbral → esperar disparo → ACK → esperar resolucion (o publicar telemetria falsa) | Alarma pasa por ACTIVE → ACKNOWLEDGED → RESOLVED | IDs en `/api/alarms` |
| 8 | Auth MQTT: anonimo rechazado | `docker exec otb-mosquitto mosquitto_sub -h 127.0.0.1 -t 'factory/#' -C 1 -W 2` | `Connection Refused: not authorised` | Salida de error |
| 9 | ACL MQTT: escritura no autorizada | `docker exec otb-mosquitto mosquitto_pub -h 127.0.0.1 -u historian -P <pass> -t 'factory/plc01/telemetry/test' -m test` | `Not authorized` en logs de Mosquitto | Logs |
| 10 | OPC UA: lectura de nodos | `.\venv\Scripts\python.exe scripts/test_opcua.py` | 7 nodos bajo PlantaSimulada/plc01 con valores en vivo | Salida del script |
| 11 | Gemelo digital: deteccion | `docker compose logs digital-twin` | Log con `DESVIACION: real=X modelo=Y (Z L)` | Logs del contenedor |
| 12 | Mantenimiento predictivo | `curl.exe -H "X-API-Key: <key>" http://localhost:8080/api/maintenance/recommendations` | JSON con `machineName`, `riskLevel`, `score`, `indicators[]` | Respuesta JSON |
| 13 | Backup PostgreSQL | `powershell -File scripts\backup.ps1` | `postgres_plant.sql` con `CREATE TABLE` y `COPY` para 5 tablas | Fichero + verificacion grep |
| 14 | Backup InfluxDB | (incluido en backup.ps1) | Directorio `influx/` con `.meta`, `.tar.gz` y `.manifest` | Listado de archivos |
| 15 | Puertos solo localhost | `powershell -Command "Get-NetTCPConnection -LocalPort 1883,8086,5432,8080,3000 \| Select LocalAddress,LocalPort"` | Todas las direcciones `127.0.0.1` (no `0.0.0.0`) | Salida del comando |
| 16 | Contenedores no-root | `docker compose exec plant-api whoami` | Usuario no-root (ej. `appuser`) | Salida del comando |
| 17 | Robustez: reinicio completo | `docker compose down; docker compose up -d` | Todos los servicios `healthy`/`running` en <60 s | `docker compose ps` |
| 18 | Grafana en vivo | Abrir `http://localhost:3000` (portada 00 · Visión general) y `python scripts/check_dashboards.py` | 7 dashboards con datos, refresco 5–10 s; script con RESULTADO OK | Captura + salida del script |
| 19 | Swagger API (perfil `dev`) | `SPRING_PROFILES_ACTIVE=dev` y abrir `http://localhost:8080/swagger-ui.html` | Documentación de todos los endpoints; en `prod` devuelve 404 | Captura de pantalla |

