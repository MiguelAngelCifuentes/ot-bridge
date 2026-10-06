<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/banner-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/images/banner-light.png">
  <img alt="OT-Bridge — plataforma de referencia de integración IT/OT" src="docs/images/banner-dark.png" width="100%">
</picture>

<br>

[![CI](https://github.com/MiguelAngelCifuentes/ot-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/MiguelAngelCifuentes/ot-bridge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/licencia-MIT-informational)](LICENSE)
![IEC 62443](https://img.shields.io/badge/IEC_62443-zonas_y_conductos-0b5394)
![Purdue](https://img.shields.io/badge/Purdue%2FPERA-L0%E2%86%92L3.5-0b5394)
![IEC 61131-3](https://img.shields.io/badge/IEC_61131--3-Structured_Text-c2410c)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Java](https://img.shields.io/badge/Java_21-Spring_Boot_3.4-6DB33F?logo=springboot&logoColor=white)
![Docker](https://img.shields.io/badge/Docker_Compose-OT_%2B_IT-2496ED?logo=docker&logoColor=white)
![Modbus](https://img.shields.io/badge/Modbus_TCP-555)
![MQTT](https://img.shields.io/badge/MQTT-660066?logo=mqtt&logoColor=white)
![OPC UA](https://img.shields.io/badge/OPC_UA-Basic256Sha256-555)
![Grafana](https://img.shields.io/badge/Grafana-11-F46800?logo=grafana&logoColor=white)

**[Arquitectura](docs/architecture.md)** ·
**[Seguridad](docs/security.md)** ·
**[Despliegue](docs/deployment.md)** ·
**[Contratos de datos](docs/mqtt-contract.md)** ·
**[ADR](docs/adr/)**

</div>

---

Una planta de bombeo simulada **de extremo a extremo**: el transmisor de nivel emite 4-20 mA, un PLC real
(OpenPLC, IEC 61131-3) decide y protege, un SCADA ISA-101 la opera, y una pasarela **unidireccional** lleva los
datos a una capa IT completa con histórico, alarmas ISA-18.2, gemelo digital, OPC UA, API REST y dashboards.

No es un programa: son **trece servicios especializados unidos por contratos de datos explícitos**,
organizados según el modelo **Purdue** y segmentados en **zonas y conductos IEC 62443**.

<div align="center">

<img src="docs/images/demo-fault-injection.gif" alt="Inyección de un fallo de cable en el transmisor LT-101 y reacción del sistema" width="100%">

<sub><b>Demostración real.</b> Desde la estación de instructor se corta el cable del transmisor LT-101 → el PLC lee
0 mA, lo diagnostica como fallo de sensor (NAMUR), detiene la bomba y cierra el consumo → la alarma aparece en el
SCADA y viaja por MQTT a la capa IT → al restablecer el cable, el sistema se recupera solo.</sub>

</div>

## En cifras

<div align="center">

| 3 capas OT | 10 servicios IT | 6 vistas SCADA | 7 dashboards | 5 fallos inyectables | 62 tests + E2E 27/27 |
|:---:|:---:|:---:|:---:|:---:|:---:|
| simulador · PLC · SCADA | broker · historian · API · alarmas · gemelo · OPC UA… | generadas desde código | generados desde código | estación de instructor | pytest · JUnit · smoke test |

</div>

## Arquitectura

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/architecture-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/images/architecture-light.png">
  <img alt="Arquitectura por niveles Purdue" src="docs/images/architecture-dark.png" width="100%">
</picture>

**El recorrido de un dato**

1. **L0 · Campo.** El simulador convierte la física de la balsa en señales: el nivel viaja como corriente (`11,42 mA → registro 1142`).
2. **L1 · Control.** El PLC valida la señal (NAMUR NE43: < 3,5 mA cable cortado, > 20,5 mA cortocircuito), escala, regula con histéresis y vigila el contactor. Es la **única autoridad de mando**.
3. **L2 · Supervisión.** FUXA lee el estado procesado (`%MW100..%MW111`) y permite operar por rol, con confirmación en los mandos críticos.
4. **L2.5 · Conducto.** El gateway cruza la frontera en **un solo sentido**: lee el PLC con FC03 y publica en MQTT. Nunca escribe.
5. **L3 / L3.5 · IT.** Cada servicio consume el contrato MQTT con su propio usuario y ACL: histórico, alarmas, gemelo, OPC UA, API y Grafana.

Detalle completo en [docs/architecture.md](docs/architecture.md).

## SCADA · capa OT

Seis vistas ISA-101 (gris lo normal, color solo lo anómalo), faceplates por equipo, alarmas ISA-18.2 y roles.
El proyecto entero **se genera desde Python** y se valida antes de desplegarse ([ADR 0003](docs/adr/0003-hmi-y-dashboards-como-codigo.md)).

<table>
  <tr>
    <td width="50%"><img src="docs/images/scada-overview.png" alt="Visión general"><br><sub><b>Visión general</b> · estado de planta, depósito con setpoints, equipos y alarmas</sub></td>
    <td width="50%"><img src="docs/images/scada-process.png" alt="P&ID"><br><sub><b>Proceso · P&amp;ID vivo</b> · tuberías animadas, instrumentación y estados</sub></td>
  </tr>
  <tr>
    <td><img src="docs/images/scada-control.png" alt="Mando y seguridades"><br><sub><b>Mando y seguridades</b> · manual/automático, consigna, matriz de seguridades y paro SCADA</sub></td>
    <td><img src="docs/images/scada-alarms.png" alt="Alarmas"><br><sub><b>Alarmas ISA-18.2</b> · prioridades, ACK e histórico; alarmas IT por MQTT</sub></td>
  </tr>
  <tr>
    <td><img src="docs/images/scada-simulator.png" alt="Estación de instructor"><br><sub><b>Estación de instructor</b> · inyección de fallos y verdad física frente a lo que mide el PLC</sub></td>
    <td><img src="docs/images/scada-trends.png" alt="Tendencias"><br><sub><b>Tendencias</b> · histórico de nivel, caudales, bomba y equipos</sub></td>
  </tr>
</table>

<details>
<summary><b>Diagnóstico y programa del PLC</b></summary>
<br>

<img src="docs/images/scada-diagnostics.png" alt="Diagnóstico">
<sub><b>Diagnóstico</b> (solo supervisor) · comunicaciones, registros %MW100–%MW111, bits de estado y constantes del PLC</sub>

<br><br>

<img src="docs/images/plc-structured-text.png" alt="Programa del PLC en Structured Text">
<sub><b>Programa del PLC</b> (<a href="ot/plc/pous/programs/main.st"><code>main.st</code></a>) · acondicionamiento 4-20 mA, diagnóstico NAMUR, histéresis de llenado, reserva de consumo, jerarquía manual/automático y vigilancia del contactor con TON de 3 s</sub>

</details>

## Dashboards · capa IT

Siete dashboards de Grafana **generados desde código**, con el mismo sistema de diseño que el SCADA.

<table>
  <tr>
    <td colspan="2"><img src="docs/images/grafana-home.png" alt="Visión general IT"><br><sub><b>00 · Visión general</b> · estado derivado, disponibilidad, OEE, producción, riesgo predictivo, gemelo y sinóptico vivo</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/grafana-process.png" alt="Proceso"><br><sub><b>01 · Proceso</b> · tendencias con bandas de alarma y cronología de estado</sub></td>
    <td width="50%"><img src="docs/images/grafana-alarms.png" alt="Alarmas"><br><sub><b>02 · Alarmas</b> · MTTA/MTTR, tasa ISA-18.2, chattering y bad actors</sub></td>
  </tr>
  <tr>
    <td><img src="docs/images/grafana-twin.png" alt="Gemelo digital"><br><sub><b>03 · Gemelo digital</b> · nivel real frente a modelo de balance de masas</sub></td>
    <td><img src="docs/images/grafana-maintenance.png" alt="Mantenimiento predictivo"><br><sub><b>04 · Mantenimiento predictivo</b> · score de la API e indicadores de salud</sub></td>
  </tr>
  <tr>
    <td><img src="docs/images/grafana-explorer.png" alt="Explorador"><br><sub><b>05 · Explorador de datos</b> · cualquier variable, agregación y comparación temporal</sub></td>
    <td><img src="docs/images/grafana-system.png" alt="Sistema"><br><sub><b>06 · Sistema y comunicaciones</b> · PLC, ingesta, API, PostgreSQL y OPC UA</sub></td>
  </tr>
</table>

## Seguridad por diseño

| Capa | Control |
|---|---|
| **Conducto OT→IT** | Unidireccional y de solo lectura (FC03). IT nunca escribe en el PLC ([ADR 0001](docs/adr/0001-conducto-ot-it-unidireccional.md)) |
| **PLC** | Arranque seguro: el runtime arranca sin programa; solo un despliegue explícito lo pone en RUN ([ADR 0004](docs/adr/0004-arranque-seguro-del-plc.md)) |
| **SCADA** | Autenticación JWT, roles, confirmación en mandos críticos; credenciales fuera del proyecto exportable |
| **MQTT** | Sin anónimos, un usuario por servicio, ACL de mínimo privilegio |
| **Datos y API** | Roles por base de datos, Grafana de solo lectura, API key por cliente, OPC UA cifrado |
| **Plataforma** | Puertos en loopback, contenedores no-root con `cap_drop: ALL`, imágenes fijadas, secretos generados y fuera de git |
| **Repositorio** | gitleaks en pre-commit y CI, Trivy, Dependabot |

<table>
  <tr>
    <td width="50%"><img src="docs/images/term-mqtt-security.png" alt="MQTT: autenticación y ACL"></td>
    <td width="50%"><img src="docs/images/term-opcua.png" alt="OPC UA cifrado"></td>
  </tr>
</table>

<details>
<summary><b>Más evidencias: telemetría MQTT, conducto Modbus, API y prueba de extremo a extremo</b></summary>
<br>

<img src="docs/images/term-mqtt-telemetry.png" alt="Telemetría MQTT en vivo">
<img src="docs/images/term-modbus.png" alt="Lectura Modbus FC03">
<img src="docs/images/term-api.png" alt="API con API key">
<img src="docs/images/term-smoke-test.png" alt="Smoke test de extremo a extremo">
<img src="docs/images/term-docker-ps.png" alt="Servicios en marcha">

</details>

Modelo de amenazas, riesgos aceptados y lecciones aprendidas: **[docs/security.md](docs/security.md)**.

## Puesta en marcha

```powershell
git clone https://github.com/MiguelAngelCifuentes/ot-bridge.git && cd ot-bridge
copy it\.env.example it\.env
python it\scripts\ensure_secrets.py      # genera todos los secretos (aleatorios, nunca se imprimen)
python it\scripts\mqtt_passwd.py         # usuarios del broker desde .env
powershell -ExecutionPolicy Bypass -File it\scripts\up-single-host.ps1
```

Después, en **OpenPLC Editor**, abre `ot/plc` y pulsa **Build**: el PLC arranca vacío por diseño.
Guía completa, despliegue en dos hosts y firewall: **[docs/deployment.md](docs/deployment.md)**.

## Estructura

```
ot-bridge/
├── ot/                        Zona OT
│   ├── field/                 L0 · simulador de planta (Modbus :5020 / :5021 / :5022)
│   ├── plc/                   L1 · proyecto OpenPLC v4 (Structured Text)
│   └── scada/                 L2 · FUXA: compose OT, HMI como código, estación de instructor
├── it/                        Zona IT
│   ├── gateway/               L2.5 · Modbus FC03 → MQTT
│   ├── historian/ alarm-engine/ digital-twin/ opcua-server/      servicios Python
│   ├── api/                   API REST Spring Boot + PostgreSQL (Flyway)
│   ├── mosquitto/ influxdb/ postgres/ grafana/                    infraestructura y dashboards como código
│   ├── scripts/               secretos, arranque, smoke test, backup y restauración
│   └── docker-compose*.yml    despliegue OT/IT separado o en un solo host
└── docs/                      arquitectura, seguridad, red, contratos, runbook, ADR
```

## Normas y referencias aplicadas

| Norma | Dónde se aplica |
|---|---|
| **Purdue · PERA** | Niveles L0–L3.5 y separación de funciones |
| **IEC 62443** | Zonas, conductos y defensa en profundidad |
| **IEC 61131-3** | Programa del PLC en Structured Text |
| **ISA-101** | Diseño de HMI de alto rendimiento (SCADA y dashboards) |
| **ISA-18.2** | Gestión de alarmas: prioridades, ACK, histéresis, retardos, chattering |
| **NAMUR NE43** | Diagnóstico de lazos 4-20 mA (cable cortado / cortocircuito) |

## Pruebas

| Suite | Qué cubre |
|---|---|
| **pytest** (45) | Contrato y escalado del gateway, parseo del historian, reglas, histéresis y reconciliación del motor de alarmas, gemelo digital |
| **JUnit + MockMvc** (17) | Idempotencia de alarmas, scoring de mantenimiento, filtro de API key, errores 4xx |
| **Build del SCADA** | Validación de 13 vistas, 237 controles, 50 tags: referencias, históricos y mandos sin permiso |
| **Smoke test E2E** (27) | Servicios healthy, flujo PLC → InfluxDB / API, controles de seguridad y ciclo completo de una alarma |
| **SCADA en sandbox** | 24 comprobaciones funcionales pulsando el HMI real y 4 roles |
| **Restauración** | Backup restaurado en contenedores aislados y verificado por hash y recuentos |

<img src="docs/images/term-tests.png" alt="Tests unitarios en verde" width="70%">

## Documentación

| Documento | Contenido |
|---|---|
| [architecture.md](docs/architecture.md) | Proceso, niveles Purdue, recorrido de un dato, zonas y conductos |
| [security.md](docs/security.md) | Modelo de amenazas, controles, riesgos aceptados, lecciones aprendidas |
| [network.md](docs/network.md) | Puertos, publicación y firewall |
| [deployment.md](docs/deployment.md) | Un solo host o OT/IT separados |
| [register-map.md](docs/register-map.md) | Contrato Modbus de campo (4-20 mA, órdenes, instructor) |
| [mqtt-contract.md](docs/mqtt-contract.md) | Topics, payloads, escalado, registros del PLC y nodos OPC UA |
| [scada-hmi.md](docs/scada-hmi.md) | SCADA generado desde código, roles y trampas de FUXA |
| [runbook.md](docs/runbook.md) | Operación, diagnóstico, backup y restauración |
| [validation.md](docs/validation.md) | Matriz de validación de extremo a extremo |
| [adr/](docs/adr/) | Decisiones de arquitectura |

## Roadmap

- TLS en MQTT (`8883`), API y Grafana; lista de confianza de certificados OPC UA.
- Conducto con proxy unidireccional (data diode).
- Docker secrets y rotación periódica de claves.
- Mantenimiento predictivo con Isolation Forest sobre variables de salud (vibración, temperatura, consumo).

---

<div align="center">
<sub>Proyecto de demostración y aprendizaje: no está pensado para controlar procesos reales sin una evaluación de riesgos.
Licencia <a href="LICENSE">MIT</a>.</sub>
</div>
