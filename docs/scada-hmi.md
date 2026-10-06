# SCADA OT — FUXA generado desde código

SCADA de operación de la balsa TK-101, en FUXA **1.3.4**. El proyecto **se genera desde código** (`ot/scada/hmi/`): se prueba en un sandbox local con un simulador del PLC y se despliega por API con copia previa. No se edita a mano en planta.

## 1. Estructura

| Ruta | Contenido |
|---|---|
| `generator/lib.py` | Sistema de diseño ISA-101 (paleta común con Grafana), permisos y constructores de controles (valor, señalización con bitmask, botón, tubería animada, barra, deslizador, campo numérico, gráfica, tabla de alarmas) |
| `generator/model.py` | Dispositivos, diccionario de tags, bits, constantes del PLC, script de decodificación, alarmas y gráficas |
| `generator/views/` | Una vista por módulo + `dialogs.py` (faceplates y confirmaciones) + `common.py` (barra de estado, depósito) |
| `generator/build.py` | Ensambla y **valida** el proyecto: tags referenciados, ids SVG, vistas enlazadas, DAQ de las gráficas, mandos sin permiso |
| `deploy.py` | Backup del proyecto remoto → `POST /api/project` → credenciales MQTT al almacén de seguridad; `--rollback <backup>` |
| `security.py` | Usuarios por rol, contraseña de admin propia, autenticación JWT e idioma (idempotente) |
| `snapshot.py` | Capturas con Chromium headless de cada vista (`/view?name=<vista>`) |
| `sandbox/` | `docker-compose.yml` (FUXA 1.3.4 + simulador), `plc_sim.py`, `test_hmi.py`, `test_roles.py` |
| `build/`, `backups/` | Salidas y copias (fuera de git: los backups contienen secretos) |

Flujo:

```powershell
docker compose -f ot/scada/hmi/sandbox/docker-compose.yml up -d    # sandbox en 127.0.0.1:1882 + simulador 127.0.0.1:5502
python ot/scada/hmi/generator/build.py --target sandbox            # o --target plant
python ot/scada/hmi/deploy.py --target sandbox                     # backup + despliegue
python ot/scada/hmi/sandbox/test_hmi.py                            # 24 comprobaciones funcionales
python ot/scada/hmi/sandbox/test_roles.py                          # 4 roles
python ot/scada/hmi/snapshot.py --target sandbox                   # capturas en ot/scada/hmi/build/snapshots
```

## 2. Vistas (niveles ISA-101)

| Vista | Nivel | Contenido |
|---|---|---|
| Visión general | 1 | Estado de planta, modo, consumo, comunicaciones; depósito con setpoints; caudales, balance, velocidad, consigna; equipos clicables; alarmas activas; última alarma IT |
| Proceso | 2 | P&ID vivo: acometida → **P-101** (llenado) → FT-101 → **TK-101** → FT-102 → **V-101** (consumo). Tuberías animadas con caudal, equipos coloreados por estado, marcas de setpoints |
| Mando | 2 | Modo (MANUAL con confirmación), bomba (MARCHA con confirmación, PARO inmediato, consigna por deslizador y campo), válvula, matriz de seguridades con RESET, **paro de emergencia SCADA** |
| Alarmas | 2 | Activas con ACK, histórico filtrable, alarmas IT (MQTT, informativas) |
| Tendencias | 2 | Histórico (DAQ SQLite de FUXA): nivel, caudales y balance, velocidad y consigna, estado de equipos |
| Diagnóstico | 4 | (solo supervisor) comunicaciones, registros MW100–MW111, bits de `hmi_estado`, constantes del PLC |
| Faceplates P-101, V-101, LT-101 | 3 | Detalle por equipo (clic en el P&ID o en Equipos) |

Estilo: fondo gris medio, equipos en gris en reposo. El color solo tiene significado: verde = marcha/abierto, azul = manual/proceso, ámbar = aviso u orden sin confirmar, rojo = fallo o alarma. Si se pierde la comunicación con el PLC, los valores se sustituyen por `???` en ámbar y los equipos pasan a gris «SIN DATOS».

## 3. Tags (PLC_Tanque, Modbus TCP, unit 1, direcciones en base 1)

| Tag | Dir. | Registro | Escala | Uso |
|---|---|---|---|---|
| `LT101_nivel` | 1125 | MW100 | /10 → L | Nivel TK-101 |
| `LT101_ma` | 1126 | MW101 | /100 → mA | Señal del transmisor |
| `FT101_caudal` | 1127 | MW102 | /10 → l/min | Entrada (llenado) |
| `FT102_caudal` | 1128 | MW103 | /10 → l/min | Salida (consumo) |
| `P101_velocidad` | 1129 | MW104 | % | Velocidad real |
| `PLC_estado` | 1130 | MW105 | bits | `hmi_estado` |
| `CMD_modo` | 1131 | MW106 | 0/1 | Automático / manual |
| `CMD_marcha` | 1132 | MW107 | 0/1 | Marcha manual P-101 |
| `CMD_valvula` | 1133 | MW108 | 0/1 | Apertura manual V-101 |
| `CMD_reset` | 1134 | MW109 | pulso | Reset de fallos (el PLC lo devuelve a 0) |
| `CMD_consigna` | 1135 | MW110 | 0–100 % | Consigna manual |
| `CMD_seta_scada` | 1136 | MW111 | 0/1 | Paro de emergencia SCADA |

Bits de `hmi_estado`: 1 contactor, 2 seta (física o SCADA), 4 fallo sensor, 8 fallo arranque, 16 nivel muy alto, 32 nivel muy bajo, **64 reserva, 128 manual, 256 orden de bomba, 512 orden de válvula** (nombres del programa `ot/plc/pous/programs/main.st`).

El **script de servidor `decodificar_estado`** se ejecuta cada segundo y calcula tags internos. Es la única fuente de verdad para vistas y alarmas:
- bits `b_*`;
- `plc_online` / `it_online`, a partir del estado de conexión de FUXA (0 sin respuesta, 3 aviso, 5 en línea);
- `seguridades_ok`;
- discrepancia orden/confirmación sostenida ≥ 2 s;
- estados de planta, bomba y válvula;
- balance;
- textos de estado.

Sin comunicación, los estados valen −1.

## 4. Alarmas (ISA-18.2)

| Prioridad | Alarma | Condición | ACK |
|---|---|---|---|
| Crítica | Seta de emergencia activa | bit 2 | obligatorio |
| Crítica | Fallo arranque P-101 | bit 8 | obligatorio |
| Crítica | Fallo transmisor LT-101 | bit 4 | obligatorio |
| Crítica | Comunicación PLC perdida | `plc_online` = 0 durante 5 s | obligatorio |
| Alta | Nivel muy alto (≥ 950 L) | bit 16 | obligatorio |
| Alta | Nivel muy bajo (≤ 100 L) | bit 32 | obligatorio |
| Info | Consumo en reserva (≤ 200 L) | bit 64 | no |
| Info | Modo manual | bit 128 | no |

Las alarmas salen de los bits del PLC, así que FUXA no duplica umbrales. Se evitaron dos alarmas molestas habituales: «NIVEL ALTO ≥ 900», que saltaba en cada llenado normal porque 900 L es la parada normal de la bomba, y «VELOCIDAD ALTA ≥ 95», que saltaba con la consigna manual legítima del 100 %.

## 5. Seguridad y roles

| Usuario | Grupo FUXA | Puede |
|---|---|---|
| (invitado) | — | Ver; los mandos aparecen deshabilitados y el servidor rechaza sus escrituras |
| `visitante` | Viewer (1) | Ver |
| `operador` | Operator (2) | Modo, marcha/paro, válvula, consigna, reset, paro SCADA, ACK |
| `supervisor` | Supervisor (8) | Lo anterior + rearme de la seta SCADA + vista Diagnóstico |
| `admin` | todos | Editor y despliegues |

- Las contraseñas están en `.env` (`FUXA_*_PASSWORD`, generadas por `security.py`). La de fábrica de admin (`123456`) queda anulada.
- Permiso por control: `permission = (grupos_que_ven << 8) | grupos_que_operan`. El build **rechaza** cualquier mando sin permiso.
- **Credenciales MQTT:** en el almacén de seguridad de FUXA (`devicesSecurity`), **no** en el proyecto. Si se guardan en `property.pwd`, `/api/project` las sirve sin autenticar.
- **Riesgo residual (FUXA 1.3.4):** el servidor exige usuario autenticado para escribir, pero no comprueba el grupo; el filtrado por rol lo hace la interfaz. Mitigación: cuentas nominales, SCADA en la red de planta y el PLC mantiene todas las seguridades.

## 6. Mandos y reglas del PLC que el HMI respeta

- **Mandos de bomba y válvula:** solo en MANUAL (se muestran con `mando_habilitado`).
- **Paso a MANUAL:** sin salto; el PLC conserva el estado de la bomba y fija la consigna al 75 %.
- **Seguridades:** seta, fallo de sensor y fallo de arranque anulan la orden de marcha en el PLC, se pulse lo que se pulse.
- **Confirmaciones:**
  - piden confirmación: pasar a MANUAL, MARCHA, RESET y rearme de la seta SCADA;
  - actúan al instante: PARO y paro de emergencia SCADA.
  - En los faceplates el mando es directo: abrir el equipo ya es el primer paso de la acción.
- **Paro SCADA (MW111):** es un paro software y **no sustituye a la seta física**.

## 7. Sandbox y simulador

- **FUXA del sandbox:** `frangoteam/fuxa:1.3.4`. Es exactamente la versión de planta, comprobada por el hash del bundle (`main.b64ff8912033d095.js`).
- **Plugin Modbus:** `modbus-serial`, instalado por API con `plugins.py` y persistido en el volumen `fuxa-pkg`. Sin él, FUXA no puede crear los dispositivos Modbus (`plugin is missing`).
- **`plc_sim.py`:** porta el programa `.st` (mismos registros, TON de 3 s, reset por pulso, arranque sin salto) con una dinámica simple del depósito (1,2 l/min por % de velocidad; salida por gravedad).
- **Inyección de fallos** (registros del simulador):
  - 2000 = el contactor no confirma;
  - 2001 = transmisor fuera de rango;
  - 2002 = seta física;
  - 2003 = aceleración.
- **Pruebas:**
  - `test_hmi.py` pulsa los botones reales del HMI y comprueba los registros (24/24);
  - `test_roles.py` comprueba los permisos por usuario (4/4).
- **Regla de oro:** el sandbox nunca apunta al PLC real, y la capa IT no escribe en el PLC.

## 8. Despliegue en planta

`python otb.py install` hace los pasos 1–5 automáticamente. A mano:

1. `python ot/scada/hmi/plugins.py --target plant` (driver Modbus; idempotente).
2. `python ot/scada/hmi/generator/build.py --target plant`.
3. `python ot/scada/hmi/deploy.py --target plant` (URL en `FUXA_URL`). Deja una copia en `ot/scada/hmi/backups/` y fija las credenciales MQTT.
4. `python ot/scada/hmi/security.py --target plant`. Crea los usuarios, activa la autenticación y pone la interfaz en español.
5. Vista de instructor: `python ot/scada/tools/build_simulation_view.py --url <FUXA> --user admin` (dispositivo `SIM_Campo` → `field-simulator:5022`, vista «Simulador», idempotente).
6. Verificación:
   - `python ot/scada/hmi/check_scada.py --target plant`: PLC y simulador entregan datos en vivo;
   - los valores coinciden con `test_read_plc.py` y Grafana;
   - **prueba de mando controlada por el operador** (AUTO → MANUAL → consigna → AUTO).
7. Rollback: `deploy.py --target plant --rollback ot/scada/hmi/backups/<fichero>.json`.
8. Copia de seguridad sin desplegar (solo lectura): `deploy.py --target plant --backup-only --out <dir>`
   (la usa `it/scripts/backup.ps1`).

**Coherencia con la capa IT:** FUXA, Grafana, la API, OPC UA y el gemelo aplican el mismo escalado (caudales /10),
así que todos muestran los mismos l/min. Los tags `it_*` extraen `severity`, `state`, `variable` y `message` de
`factory/alarms/events`; la alarma IT `comunicacion` (CRITICAL) indica que la capa IT ha perdido el PLC.

## 9. Trampas de FUXA 1.3.4 descubiertas

- El valor con unidad necesita `ranges[0].type = 1` (numérico); con `"output"` la unidad no se muestra.
- Estado de conexión de un dispositivo: numérico (0 / 3 / 5), no `connect-ok`.
- MQTT: la dirección va en `property.address`, y usuario y contraseña en el almacén de seguridad. El valor se envía como objeto, porque el servidor ya lo serializa.
- Las alarmas no admiten bitmask; las señalizaciones sí (`property.bitmask` y `action.bitmask`).
- Las tablas de alarmas necesitan `options.alarmsColumns`.
- Las zonas de color en las líneas de gráfica rompen el dibujo en 1.3.4.
- Formato de fecha de la cabecera: sintaxis de Angular (`dd/MM/yyyy HH:mm:ss`).
- `POST /api/project` sustituye el proyecto completo; el almacén de seguridad de dispositivos se conserva.
