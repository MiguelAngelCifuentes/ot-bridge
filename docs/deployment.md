# Despliegue — OT-Bridge

## Requisitos

| Herramienta | Versión probada |
|---|---|
| Docker Desktop / Engine + Compose | Compose v2 o superior |
| Python | 3.11 o superior (simulador y scripts) |
| OpenPLC Editor | v4 (para compilar y desplegar `ot/plc`) |
| Windows PowerShell 5.1 | Scripts `*.ps1` de operación (opcionales) |

## 1. Un solo host (recomendado para empezar)

```powershell
git clone https://github.com/<usuario>/ot-bridge.git
cd ot-bridge

# 1. Secretos: plantilla + valores aleatorios (nunca se imprimen)
copy it\.env.example it\.env
python it\scripts\ensure_secrets.py
python it\scripts\mqtt_passwd.py

# 2. Entorno Python (simulador y herramientas)
py -3 -m venv it\venv
it\venv\Scripts\pip install -r it\requirements-dev.txt -r ot\field\requirements.txt

# 3. Todo en marcha: capa OT, simulador y los 10 servicios IT
powershell -ExecutionPolicy Bypass -File it\scripts\up-single-host.ps1
```

Después, en **OpenPLC Editor**: abre `ot/plc`, conecta con el runtime (`https://localhost:8443`) y pulsa
**Build**. El PLC arranca vacío por diseño: solo ese despliegue lo pone en RUN.

Y despliega el SCADA generado desde código:

```powershell
it\venv\Scripts\python ot\scada\hmi\generator\build.py --target plant
it\venv\Scripts\python ot\scada\hmi\deploy.py --target plant
it\venv\Scripts\python ot\scada\hmi\security.py --target plant
it\venv\Scripts\python ot\scada\tools\build_simulation_view.py --url http://localhost:1881 --user admin
```

| Servicio | URL local |
|---|---|
| SCADA FUXA | http://localhost:1881 |
| Grafana | http://localhost:3000 |
| API REST | http://localhost:8080/api (cabecera `X-API-Key`) |
| OpenPLC runtime | https://localhost:8443 |
| OPC UA | opc.tcp://localhost:4840 |

Parada: `it\scripts\down-single-host.ps1` (añade `-IncludeOT` para parar también PLC y SCADA).

## 2. OT e IT en hosts separados

**Host OT**

```powershell
$env:FUXA_BIND = "<IP del host OT>"     # operación del SCADA desde la red de planta
$env:MODBUS_BIND = "<IP del host OT>"   # conducto hacia el host IT
docker compose -f ot/scada/docker-compose.yml --profile two-host up -d
python ot/field/main.py                 # simulador de planta con consola de fallos
```

**Host IT**

```powershell
# it/.env: PLC_HOST=<IP del host OT>  ·  MQTT_LAN_BIND=<IP del host IT>
docker compose -f it/docker-compose.yml up -d
python it/scripts/fuxa_set_broker.py --fuxa http://<IP del host OT>:1881 --broker mqtt://<IP del host IT>:1883
```

Aplica las reglas de firewall de [network.md](network.md) en ambos hosts.

## 3. Verificación

```powershell
docker compose -f it/docker-compose.yml ps         # 10 servicios healthy
python it/scripts/smoke_test.py                    # flujo PLC → MQTT → InfluxDB / API y controles de seguridad
python it/scripts/check_dashboards.py              # todas las consultas de los 7 dashboards
powershell -File it/scripts/run_tests.ps1          # batería completa
```

Operación diaria, diagnóstico y backups: [runbook.md](runbook.md).
