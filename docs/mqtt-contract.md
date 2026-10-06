# Contrato de datos MQTT y OPC UA — OT-Bridge

> Fuente de verdad del contrato. Cualquier cambio en topics, payloads o unidades exige actualizar este
> documento y **todos** los consumidores a la vez: gateway, historian, alarm-engine, plant-api, opcua-server,
> digital-twin, Grafana (`it/grafana/generator/lib.py`) y FUXA (tags `it_*`).

## 1. Broker

| Parámetro | Valor |
|---|---|
| Host en Docker (red `plant-net`) | `mosquitto` |
| Host en local | `127.0.0.1:1883` · `${MQTT_LAN_BIND}:1883` (solo para el SCADA FUXA; firewall de origen) |
| Autenticación | usuario/contraseña por servicio, `allow_anonymous false` (`it/scripts/mqtt_passwd.py`) |
| ACL | mínimo privilegio por usuario (`it/mosquitto/config/acl`) |

## 2. Topics

| Topic | Emisor | QoS | Retained | Descripción |
|---|---|---|---|---|
| `factory/<plc>/telemetry/<variable>` | gateway | 1 | no | Medidas del PLC, una por variable (1 Hz) |
| `factory/<plc>/status` | gateway | 1 | sí (LWT: `online=false`) | Heartbeat online/offline |
| `factory/alarms/events` | alarm-engine, digital-twin | 1 | no | Eventos de alarma ACTIVE/RESOLVED |
| `factory/<plc>/twin/state` | digital-twin | 0 | no | Estado del gemelo digital (1 Hz); el historian lo guarda en `twin_state` |

- `<plc>` = `plc01`. El PLC se identifica en el topic **y** en el payload.
- Un topic por variable; el consumidor no debe asumir orden entre variables.
- Los consumidores eligen su QoS de suscripción: la API usa 0 para telemetría y estado (dato de refresco) y 1
  para eventos de alarma (no se pueden perder), con sesión persistente.

## 3. Payloads

### 3.1 Telemetría

```json
{"ts": 1790795748, "plc": "plc01", "variable": "caudal_ent", "value": 900, "unit": "lpm_x10", "q": 1}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `ts` | entero | segundos epoch UTC |
| `plc` | string | identificador del PLC (`plc01`) |
| `variable` | string | nombre lógico (tabla §5) |
| `value` | entero | **valor crudo del PLC** (INT con signo, −32768…32767). Escalar con la tabla §5 |
| `unit` | string | unidad del valor crudo (`L_x10`, `mA_x100`, `lpm_x10`, `%`, `bitmask`, vacío) |
| `q` | 0 \| 1 | calidad: `1` lectura válida, `0` PLC inalcanzable (último valor conocido) |

Los valores viajan sin escalar para no perder precisión ni cambiar el tipo entero de InfluxDB; cada
consumidor divide por el divisor de la tabla §5 al presentar.

### 3.2 Estado del PLC (heartbeat)

```json
{"ts": 1790795748, "plc": "plc01", "online": true}
```

El LWT de una caída brusca puede llegar con `ts = 0`: el historian lo descarta como punto, la API usa la
hora actual y el alarm-engine lo trata como pérdida de comunicación.

### 3.3 Evento de alarma

```json
{"ts": 1790795748, "plc": "plc01", "variable": "estado", "severity": "critical", "state": "ACTIVE",
 "message": "Fallo sensor de nivel", "code": "estado:bit4"}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `severity` | string | `warning`, `high` o `critical` |
| `state` | string | `ACTIVE` o `RESOLVED` |
| `message` | string | texto legible para el operador |
| `code` | string | **identidad de la alarma**. ACTIVE/RESOLVED se emparejan por (`plc`, `code`) |

Códigos: `th<id>` (umbral configurado en la API), `estado:bit<N>` (reglas de respaldo sobre bits del PLC),
`comunicacion` (pérdida de comunicación, CRITICAL, la emite el alarm-engine), `gemelo:balance` (gemelo digital).
Sin `code` (emisores antiguos) la API usa `variable:severity`.

### 3.4 Estado del gemelo digital

```json
{"ts": 1790795748, "plc": "plc01", "level_real": 466.3, "level_model": 466.34, "deviation": -0.04, "leak_lpm": 0.11, "threshold": 20.0, "alarmed": false}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `level_real` | número | nivel medido en L (`nivel_x10 / 10`) |
| `level_model` | número | nivel predicho por el observador de balance de masas, en L |
| `deviation` | número | `level_real − level_model` en L (negativo: falta agua respecto a lo esperado) |
| `leak_lpm` | número | caudal no medido estimado en **l/min reales** (positivo = pérdida) |
| `threshold` | número | umbral de alarma en L (`UMBRAL_L`) |
| `alarmed` | bool | `true` mientras la alarma `gemelo:balance` está activa |

Balance: `ΔL = (caudal_ent − caudal_sal) / FLOW_DIVISOR × Δt / 60` con `FLOW_DIVISOR = 10` (caudales en
l/min ×10). Calibrado con datos reales (error < 1 % en ventanas de 10 y 30 min). Si faltan lecturas de nivel
más de 10 s, el modelo se resincroniza con el valor real.

## 4. Reglas del contrato

1. `ts` siempre en segundos epoch **UTC**.
2. `q = 0`: el historian **no** la guarda; el alarm-engine **no** la evalúa y abre la alarma `comunicacion`.
3. Un topic por variable; PLC identificado en topic y payload.
4. El historian y la API toleran reentregas (QoS 1): escritura idempotente (en alarmas, por `code`).
5. Payload malformado: se descarta y se registra en log, sin tumbar al consumidor.

## 5. Registros Modbus de origen y escalado (PLC `plc01`, unit_id 1)

Lectura en bloque (FC03, solo lectura): `read_holding_registers(address=1124, count=12, device_id=1)`
(pymodbus 3.15; **no** usar `slave`). Los registros son `INT` con signo: el gateway convierte de uint16.

> Mapeo del esclavo de OpenPLC: `%QW` ocupa 0–1023 y `%MW` 1024–2047, así que
> `MW100` está en la dirección **1124**. FUXA usa numeración 1-based (+1025).

| Variable | Registro (`.st`) | Dir. | Unidad cruda | Divisor | Unidad de ingeniería | Notas |
|---|---|---|---|---|---|---|
| `nivel_x10` | MW100 `hmi_nivel` | 1124 | `L_x10` | 10 | L | 5000 = 500,0 L; depósito 0–1000 L |
| `nivel_ma` | MW101 | 1125 | `mA_x100` | 100 | mA | 4–20 mA; NAMUR válido 3,5–20,5 |
| `caudal_ent` | MW102 `hmi_caudal_ent` | 1126 | `lpm_x10` | 10 | l/min | llenado (P-101); nominal 150 l/min |
| `caudal_sal` | MW103 `hmi_caudal_sal` | 1127 | `lpm_x10` | 10 | l/min | consumo (V-101) |
| `velocidad` | MW104 `hmi_velocidad` | 1128 | `%` | 1 | % | velocidad real de P-101 |
| `estado` | MW105 `hmi_estado` | 1129 | `bitmask` | — | — | ver bits abajo |
| `modo_manual` | MW106 | 1130 | — | 1 | — | mando: 0 auto, 1 manual (lo escribe FUXA) |
| `mando_marcha` | MW107 | 1131 | — | 1 | — | mando manual de marcha |
| `mando_valvula` | MW108 | 1132 | — | 1 | — | mando manual de válvula |
| `reset_fallos` | MW109 | 1133 | — | 1 | — | reset de fallos (flanco) |
| `consigna_manual` | MW110 | 1134 | `%` | 1 | % | consigna manual de velocidad 0–100 |
| `seta_scada` | MW111 `seta_scada` | 1135 | — | 1 | — | seta de emergencia desde el SCADA (≠0 = pulsada) |

Implementaciones del escalado: `it/grafana/generator/lib.py` (`FLOW`), `it/api/.../PlantUnits.java`,
`it/opcua-server/main.py` (`VARIABLES`), `digital-twin` (`FLOW_DIVISOR`), `it/scripts/test_read_plc.py`.

### Bitmask de `estado` (MW105), nombres del programa del PLC

| Bit | Valor | Nombre | Alarma IT |
|---|---|---|---|
| 0 | 1 | `contactor_cerrado` | — |
| 1 | 2 | `seta_activa` (física o `seta_scada`) | CRITICAL |
| 2 | 4 | `fallo_sensor` | CRITICAL |
| 3 | 8 | `fallo_arranque` | CRITICAL, retardo 1 s |
| 4 | 16 | `alarma_nivel_alto` (≥ 950 L) | HIGH, retardo 2 s |
| 5 | 32 | `alarma_nivel_bajo` (≤ 100 L) | HIGH, retardo 2 s |
| 6 | 64 | `en_reserva` | — |
| 7 | 128 | `modo_manual` | — |
| 8 | 256 | `orden_marcha_bomba` | — |
| 9 | 512 | `orden_apertura_valvula` | — |

Las alarmas IT son umbrales `BIT` de la API (`th<id>`, editables); si la API no responde al arrancar, el
alarm-engine usa las mismas reglas de respaldo (`estado:bit<N>`). Las alarmas de nivel las decide el PLC
(bits 16/32): la capa IT no duplica umbrales numéricos.

## 6. Topics concretos (plc01)

```
factory/plc01/telemetry/{nivel_x10,nivel_ma,caudal_ent,caudal_sal,velocidad,estado,
                         modo_manual,mando_marcha,mando_valvula,reset_fallos,consigna_manual,seta_scada}
factory/plc01/status
factory/plc01/twin/state
factory/alarms/events
```

## 7. OPC UA: mapeo variable → nodo

`opcua-server` (`opc.tcp://127.0.0.1:4840`, política `Basic256Sha256` Sign & Encrypt + usuario/contraseña
`OPC_USER`/`OPC_PASSWORD`; sin acceso anónimo) expone la telemetría bajo `PlantaSimulada/plc01`
(namespace `otbridge`, índice 2). Cada nodo lleva `EngineeringUnits`, `SourceTimestamp` (el `ts` MQTT) y
`StatusCode`: `Good` con el PLC en línea, `UncertainLastUsableValue` sin comunicación.

| Nodo OPC UA | Variable MQTT | Transformación | Tipo | Unidad |
|---|---|---|---|---|
| `NivelDeposito` | `nivel_x10` | / 10 | Double | L |
| `NivelSensorMA` | `nivel_ma` | / 100 | Double | mA |
| `CaudalEntrada` | `caudal_ent` | / 10 | Double | l/min |
| `CaudalSalida` | `caudal_sal` | / 10 | Double | l/min |
| `VelocidadBomba` | `velocidad` | — | Double | % |
| `Estado` | `estado` | — | Int32 | bitmask |
| `PLCOnline` | `factory/plc01/status` → `online` | — | Boolean | — |

### Comparativa de protocolos

| | Modbus TCP | MQTT | OPC UA |
|---|---|---|---|
| **Nivel Purdue** | L1-L2 (OT) | L2.5-L3 (conduit/IT) | L2-L3 (industrial) |
| **Modelo** | Registros planos | Pub/sub con topics | Espacio de objetos jerárquico |
| **Semántica** | Ninguna (solo dirección) | Topic = semántica parcial | Nodos tipados con unidades y calidad |
| **Seguridad** | Ninguna (firewall) | Auth + ACL | Certificados + cifrado + usuario |
| **Cuándo usarlo** | Comunicación directa PLC↔HMI | Desacoplamiento IT, histórico, alarmas | Integración con SCADA/MES comerciales |

## 8. Verificación

```powershell
docker exec mosquitto mosquitto_sub -h 127.0.0.1 -u historian -P <pass> -t "factory/#" -v -C 20
python it/scripts/test_opcua.py      # nodos OPC UA en vivo (cifrado + usuario)
python it/scripts/test_read_plc.py   # registros Modbus crudos y escalados
```
