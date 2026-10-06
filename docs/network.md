# Red, puertos y firewall — OT-Bridge

> Las direcciones de este documento son genéricas. Las reales de cada instalación van en `it/.env`
> (`PLC_HOST`, `MQTT_LAN_BIND`) y en las variables `FUXA_BIND` / `MODBUS_BIND` de la capa OT;
> nunca en el repositorio.

## 1. Topología

```
host OT                                              host IT
simulador + OpenPLC + FUXA                           gateway · mosquitto · influxdb · postgres
esclavo Modbus TCP :502  ───── conducto ─────────▶   gateway lee Modbus (FC03, solo lectura)
FUXA (cliente MQTT)      ◀──── solo lectura ──────   mosquitto :1883 (usuario fuxa, ACL de lectura)
```

- Flujo de proceso **unidireccional OT → IT**: IT nunca escribe en el PLC.
- En **un solo host** no se publica nada en la LAN: OT e IT comparten la red Docker `fuxa_default`.

## 2. Puertos

### Capa OT

| Puerto | Servicio | Publicación por defecto | Notas |
|---|---|---|---|
| 5020/tcp | Simulador · sensores (FC04) | todas las interfaces del host | Lo consume el PLC (`host.docker.internal`) |
| 5021/tcp | Simulador · actuadores (FC03/06/16) | todas las interfaces del host | Lo escribe el PLC |
| 5022/tcp | Simulador · estación de instructor | todas las interfaces del host | Lo usa FUXA (vista Simulador) |
| 502/tcp | Esclavo Modbus del PLC | no publicado (red Docker) | Con OT/IT separados: `modbus-proxy` en `${MODBUS_BIND}` |
| 8443/tcp | API del runtime OpenPLC | `127.0.0.1` | Solo para el Editor local |
| 1881/tcp | FUXA SCADA | `${FUXA_BIND:-127.0.0.1}` | Abrir a la red de planta de forma explícita |

> El simulador representa el cableado de campo. En una instalación compartida conviene restringir
> 5020-5022 al propio host con el firewall.

### Capa IT

| Puerto | Servicio | Publicación |
|---|---|---|
| 1883/tcp | Mosquitto | `127.0.0.1` + `${MQTT_LAN_BIND}` (solo para FUXA con OT/IT separados) |
| 8086/tcp | InfluxDB | `127.0.0.1` |
| 5432/tcp | PostgreSQL | `127.0.0.1` (no publicado en un solo host) |
| 8080/tcp | API REST | `127.0.0.1` |
| 3000/tcp | Grafana | `127.0.0.1` |
| 4840/tcp | OPC UA | `127.0.0.1` |

## 3. Firewall (despliegue OT/IT separado)

Modbus TCP no tiene autenticación y MQTT viaja sin TLS en este laboratorio: el control es el **origen**.

Docker Desktop publica los puertos con su propia regla Allow genérica y reescribe la IP de origen hacia el
contenedor. Por eso el filtrado se hace en el firewall del host y con una regla **Block** explícita para el
resto de orígenes (Block tiene precedencia sobre Allow).

Plantilla para Windows (PowerShell como administrador). Sustituye `<IT_HOST>` y `<OT_HOST>` por las IP de
tu instalación y ajusta los rangos de bloqueo para que excluyan solo esa dirección:

```powershell
# Host OT: Modbus 502 solo desde el host IT
New-NetFirewallRule -DisplayName "OT-Bridge Modbus 502 permitir IT" -Direction Inbound -Protocol TCP `
  -LocalPort 502 -RemoteAddress <IT_HOST> -Action Allow
New-NetFirewallRule -DisplayName "OT-Bridge Modbus 502 bloquear resto" -Direction Inbound -Protocol TCP `
  -LocalPort 502 -RemoteAddress <RANGOS_EXCEPTO_IT_HOST> -Action Block

# Host IT: MQTT 1883 solo desde el host OT
New-NetFirewallRule -DisplayName "OT-Bridge MQTT 1883 permitir OT" -Direction Inbound -Protocol TCP `
  -LocalPort 1883 -RemoteAddress <OT_HOST> -Action Allow
New-NetFirewallRule -DisplayName "OT-Bridge MQTT 1883 bloquear resto" -Direction Inbound -Protocol TCP `
  -LocalPort 1883 -RemoteAddress <RANGOS_EXCEPTO_OT_HOST> -Action Block
```

El bloqueo no afecta a los contenedores (hablan por la red Docker) ni a `127.0.0.1`.

## 4. Verificación

```powershell
Test-NetConnection <OT_HOST> -Port 502          # desde el host IT: True; desde otro equipo: False
python it/scripts/test_read_plc.py <OT_HOST>    # registros %MW100..%MW111 crudos y escalados
Get-NetTCPConnection -State Listen -LocalPort 1883,8086,5432,8080,3000,4840 | Select LocalAddress,LocalPort
```

Recomendado: reserva DHCP en el router para ambos hosts, para que una rotación de direcciones no rompa
el conducto ni deje desfasadas las reglas de firewall.
