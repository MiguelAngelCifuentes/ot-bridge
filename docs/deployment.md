# Despliegue — OT-Bridge

| Modo | Para qué | Cómo |
|---|---|---|
| **Un solo host** | Desarrollo, demostración y portfolio | `python otb.py install` — guía completa en [INSTALL.md](../INSTALL.md) |
| **OT e IT en hosts separados** | Topología realista de planta: zona OT y zona IT en equipos distintos, unidas por un conducto de solo lectura con firewall | Este documento |

## Topología con dos hosts

```
host OT (planta)                                       host IT (oficina / CPD)
├─ otb-field-simulator  (red otb-ot, sin publicar)
├─ otb-openplc          :8443 → 127.0.0.1             ├─ otb-gateway ── lee <OT_HOST>:502 (FC03)
├─ otb-modbus-proxy     :502  → <OT_HOST>  ──────────▶│
└─ otb-fuxa             :1881 → <OT_HOST>  ◀──────────├─ otb-mosquitto :1883 → <IT_HOST> (usuario fuxa, solo lectura)
                                                       └─ … resto del stack IT en 127.0.0.1
```

Los dos únicos flujos que cruzan entre hosts son el **Modbus de solo lectura** (IT → OT:502) y el **MQTT de solo
lectura** de FUXA (OT → IT:1883). Los dos están restringidos por origen en el firewall ([network.md](network.md)).

## 1. Preparar ambos hosts

En los dos: Docker con Compose v2, Python 3.10+ y el repositorio clonado.

```bash
git clone https://github.com/MiguelAngelCifuentes/ot-bridge.git && cd ot-bridge
```

Los secretos se generan **una sola vez, en el host IT**, y se copian al host OT por un canal seguro (USB cifrado,
`scp`), nunca por correo ni por chat. El host OT necesita las variables `OPENPLC_*`, `FUXA_*` y
`MQTT_PASSWORD_FUXA`.

## 2. Host IT

```bash
copy it\.env.example it\.env          # cp en Linux/macOS
```

En `it/.env`:

```ini
PLC_HOST=<IP del host OT>
MQTT_LAN_BIND=<IP del host IT>        # interfaz donde FUXA alcanza el broker
```

```bash
python it/scripts/ensure_secrets.py
python it/scripts/mqtt_passwd.py
docker compose -f it/docker-compose.yml up -d --build
```

## 3. Host OT

Copia `it/.env` desde el host IT y arranca la capa OT publicando el SCADA y el conducto Modbus en la interfaz LAN:

```bash
# PowerShell: $env:FUXA_BIND="<IP del host OT>"; $env:MODBUS_BIND="<IP del host OT>"
export FUXA_BIND=<IP del host OT> MODBUS_BIND=<IP del host OT>
docker compose -f ot/scada/docker-compose.yml --profile two-host up -d --build

python ot/plc/deploy_plc.py                                  # programa del PLC y RUN

export FUXA_URL=http://127.0.0.1:1881
python ot/scada/hmi/plugins.py --target plant                # driver Modbus de FUXA
python ot/scada/hmi/generator/build.py --target plant
python ot/scada/hmi/deploy.py --target plant
python ot/scada/hmi/security.py --target plant
FUXA_PASSWORD=<FUXA_ADMIN_PASSWORD> python ot/scada/tools/build_simulation_view.py --url $FUXA_URL --user admin

# El SCADA lee las alarmas IT del broker del host IT
python it/scripts/fuxa_set_broker.py --fuxa $FUXA_URL --broker mqtt://<IP del host IT>:1883
```

## 4. Firewall

Aplica las reglas de origen de [network.md §3](network.md#3-firewall-despliegue-otit-separado) en los dos hosts:
`502` en el host OT solo desde el host IT, y `1883` en el host IT solo desde el host OT.

## 5. Verificación

```bash
# Host IT
python it/scripts/test_read_plc.py <IP del host OT>   # conducto Modbus (requiere it/requirements-dev.txt)
python it/scripts/smoke_test.py                       # flujo completo PLC → MQTT → InfluxDB / API

# Host OT
python ot/scada/hmi/check_scada.py --target plant     # el SCADA recibe datos del PLC y del simulador
```

Operación diaria, diagnóstico y backups: [runbook.md](runbook.md).
