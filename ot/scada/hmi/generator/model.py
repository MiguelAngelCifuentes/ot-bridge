"""Modelo del proyecto FUXA: dispositivos, diccionario de tags, script de decodificacion, alarmas y graficas.

Fuente de verdad del PLC: ot/plc/pous/programs/main.st (registros %MW100..%MW111, bits de hmi_estado y setpoints).
"""
from __future__ import annotations

from dataclasses import dataclass

import lib
from lib import EMERG, INFO, MANUAL, PROCESS, RUN, WARN, uid

# --------------------------------------------------------------------------- constantes del PLC (.st)
SP = {"SP_ALARMA_ALTA": 950, "SP_LLENO": 900, "SP_ARRANQUE_BOMBA": 300, "SP_REARME_CONSUMO": 250,
      "SP_RESERVA": 200, "SP_ALARMA_BAJA": 100}
CONSTANTS = [("SP_ALARMA_ALTA", "950 L", "Alarma de nivel muy alto (bit 16)"),
             ("SP_LLENO", "900 L", "Parada normal de la bomba en automático"),
             ("SP_ARRANQUE_BOMBA", "300 L", "Arranque de la bomba en automático"),
             ("SP_REARME_CONSUMO", "250 L", "Fin de reserva: se rehabilita el consumo"),
             ("SP_RESERVA", "200 L", "Inicio de reserva: se cierra el consumo (bit 64)"),
             ("SP_ALARMA_BAJA", "100 L", "Alarma de nivel muy bajo (bit 32)"),
             ("MA_MIN_VALIDO / MAX", "3,50 / 20,50 mA", "Rango válido del transmisor LT-101"),
             ("VELOCIDAD_AUTO", "75 %", "Velocidad fija en automático y consigna al pasar a manual"),
             ("TON_ARRANQUE / PARO", "3 s", "Discrepancia orden/confirmación que provoca fallo de arranque")]

# Bits de hmi_estado (MW105) con los nombres reales del programa PLC
BITS = [(1, "contactor_cerrado", "Contactor P-101 confirmado"),
        (2, "seta_activa", "Seta de emergencia (física o SCADA)"),
        (4, "fallo_sensor", "Fallo transmisor LT-101"),
        (8, "fallo_arranque", "Fallo de arranque/paro P-101"),
        (16, "alarma_nivel_alto", "Nivel muy alto (>= 950 L)"),
        (32, "alarma_nivel_bajo", "Nivel muy bajo (<= 100 L)"),
        (64, "en_reserva", "Consumo en reserva (<= 200 L)"),
        (128, "modo_manual", "Modo manual"),
        (256, "bomba_marcha", "Orden de marcha P-101"),
        (512, "valvula_abrir", "Orden de apertura V-101")]

PLC_DEVICE_ID = "d_plc_tanque"
MQTT_DEVICE_ID = "d_mqtt_it"
SERVER_DEVICE_ID = "0"


def tid(name: str) -> str:
    return "t_" + uid("tag", name)


@dataclass(frozen=True)
class PlcTag:
    name: str
    address: int          # base 1 (FUXA): MW100 = 1125
    divisor: int
    description: str
    unit: str = ""
    writable: bool = False

    @property
    def id(self) -> str:
        return tid(self.name)


PLC_TAGS = [
    PlcTag("LT101_nivel", 1125, 10, "Nivel del depósito TK-101 (MW100)", "L"),
    PlcTag("LT101_ma", 1126, 100, "Señal del transmisor LT-101 (MW101)", "mA"),
    PlcTag("FT101_caudal", 1127, 10, "Caudal de entrada / llenado (MW102)", "l/min"),
    PlcTag("FT102_caudal", 1128, 10, "Caudal de salida / consumo (MW103)", "l/min"),
    PlcTag("P101_velocidad", 1129, 1, "Velocidad real de la bomba P-101 (MW104)", "%"),
    PlcTag("PLC_estado", 1130, 1, "Registro de estado hmi_estado (MW105)"),
    PlcTag("CMD_modo", 1131, 1, "Modo: 0 automático, 1 manual (MW106)", writable=True),
    PlcTag("CMD_marcha", 1132, 1, "Mando manual de marcha P-101 (MW107)", writable=True),
    PlcTag("CMD_valvula", 1133, 1, "Mando manual de apertura V-101 (MW108)", writable=True),
    PlcTag("CMD_reset", 1134, 1, "Reset de fallos por pulso (MW109)", writable=True),
    PlcTag("CMD_consigna", 1135, 1, "Consigna manual de velocidad 0-100 % (MW110)", "%", writable=True),
    PlcTag("CMD_seta_scada", 1136, 1, "Paro de emergencia SCADA (MW111)", writable=True),
]
T = {t.name: t.id for t in PLC_TAGS}

# Tags internos del servidor FUXA calculados por el script de decodificacion
INTERNAL_NUM = ["plc_online", "it_online", "b_contactor", "b_seta", "b_fsensor", "b_farranque", "b_alta", "b_baja",
                "b_reserva", "b_manual", "b_orden_bomba", "b_orden_valvula", "seguridades_ok", "disc_s",
                "discrepancia", "estado_planta", "estado_bomba", "estado_valvula", "mando_habilitado",
                "reset_visible", "balance_lpm", "nivel_pct"]
INTERNAL_TXT = ["txt_stale", "txt_planta", "txt_modo", "txt_bomba", "txt_valvula", "txt_consumo", "txt_sensor", "txt_plc",
                "txt_it", "txt_seguridades"]
for _n in INTERNAL_NUM + INTERNAL_TXT:
    T[_n] = tid(_n)
T["conn_plc"] = tid("conn_plc")
lib.QUALITY.update({"online": T["plc_online"], "stale_text": T["txt_stale"],
                    "tags": {t.id for t in PLC_TAGS} | {T["balance_lpm"], T["nivel_pct"]}})
T["conn_it"] = tid("conn_it")
for _n in ("it_severidad", "it_estado", "it_variable", "it_mensaje"):
    T[_n] = tid(_n)

DAQ_ON = {"enabled": True, "interval": 5, "changed": True, "restored": False}
DAQ_OFF = {"enabled": False, "interval": 60, "changed": False, "restored": False}
DAQ_TAGS = {"LT101_nivel", "LT101_ma", "FT101_caudal", "FT102_caudal", "P101_velocidad", "PLC_estado",
            "CMD_modo", "CMD_consigna", "b_contactor", "b_orden_valvula", "b_manual", "balance_lpm"}


def devices(plc_address: str, mqtt_url: str) -> dict:
    """Dispositivos del proyecto. Sin credenciales: FUXA guarda las del broker en su almacen de seguridad
    (devicesSecurity), que no se expone en /api/project; deploy.py las fija desde .env."""
    server_tags = {
        T["conn_plc"]: {"id": T["conn_plc"], "name": "PLC_Tanque Connection Status", "label": "Estado conexion PLC",
                        "value": "", "type": "number", "memaddress": PLC_DEVICE_ID, "daq": DAQ_OFF, "init": "",
                        "sysType": 1},
        T["conn_it"]: {"id": T["conn_it"], "name": "IT-Broker Connection Status", "label": "Estado conexion IT",
                       "value": "", "type": "number", "memaddress": MQTT_DEVICE_ID, "daq": DAQ_OFF, "init": "",
                       "sysType": 1},
    }
    for n in INTERNAL_NUM:
        server_tags[T[n]] = {"id": T[n], "name": n, "label": n, "value": "0", "type": "number", "init": "0",
                             "daq": DAQ_ON if n in DAQ_TAGS else DAQ_OFF, "description": "Calculado por script"}
    for n in INTERNAL_TXT:
        server_tags[T[n]] = {"id": T[n], "name": n, "label": n, "value": "", "type": "string", "init": "---",
                             "daq": DAQ_OFF, "description": "Calculado por script"}

    plc_tags = {t.id: {"id": t.id, "name": t.name, "type": "Int16", "memaddress": "400000", "address": t.address,
                       "divisor": t.divisor, "description": t.description,
                       "daq": DAQ_ON if t.name in DAQ_TAGS else DAQ_OFF} for t in PLC_TAGS}

    it_tags = {}
    for n, key in (("it_severidad", "severity"), ("it_estado", "state"), ("it_variable", "variable"),
                   ("it_mensaje", "message")):
        it_tags[T[n]] = {"id": T[n], "name": n, "label": "", "value": "", "type": "json",
                         "address": "factory/alarms/events", "memaddress": key, "divisor": 1, "access": "ro",
                         "options": {"subs": ["factory/alarms/events"]}, "format": 0, "init": "", "daq": DAQ_OFF,
                         "sysType": None, "description": "Ultima alarma del motor IT (MQTT, solo lectura)"}

    return {
        SERVER_DEVICE_ID: {"id": SERVER_DEVICE_ID, "name": "FUXA Server", "type": "FuxaServer", "enabled": True,
                           "polling": 1000, "property": {}, "tags": server_tags},
        PLC_DEVICE_ID: {"id": PLC_DEVICE_ID, "name": "PLC_Tanque", "type": "ModbusTCP", "enabled": True,
                        "polling": 1000, "tags": plc_tags,
                        "property": {"address": plc_address, "port": None, "slot": None, "rack": None,
                                     "slaveid": "1", "baudrate": 9600, "databits": 8, "stopbits": 1,
                                     "parity": "None", "connectionOption": "TcpPort", "delay": 10,
                                     "forceFC16": False}},
        MQTT_DEVICE_ID: {"id": MQTT_DEVICE_ID, "name": "IT-Broker", "type": "MQTTclient", "enabled": True,
                         "polling": 1000, "tags": it_tags,
                         "certificatesDir": "/usr/src/app/FUXA/server/_certificates",
                         "property": {"address": mqtt_url, "timeout": 10000}},
    }


# --------------------------------------------------------------------------- script de decodificacion
def decode_script() -> dict:
    """Script de servidor (cada 1 s): decodifica hmi_estado y calcula estados y textos para el HMI.

    Una unica fuente de verdad (el PLC); las vistas y las alarmas leen estos tags internos.
    """
    code = f"""
var raw = Number($getTag('{T['PLC_estado']}')) || 0;
var st = $getTag('{T['conn_plc']}');
// estado de conexion de FUXA: 0 = sin respuesta (> 5 sondeos), 3 = aviso (> 2 sondeos), 5 = en linea
var online = Number(st) >= 3 ? 1 : 0;
var its = $getTag('{T['conn_it']}');
var itOnline = Number(its) >= 3 ? 1 : 0;
var e = online ? raw : 0;
// sin comunicacion los estados valen -1 (las vistas los pintan en gris; las alarmas no los ven activos)
function b(n) {{ return online ? ((e & n) ? 1 : 0) : -1; }}
var contactor = b(1), seta = b(2), fs = b(4), fa = b(8), alta = b(16), baja = b(32);
var reserva = b(64), manual = b(128), ob = b(256), ov = b(512);
var seg = !online ? -1 : ((!seta && !fs && !fa) ? 1 : 0);
// discrepancia orden/confirmacion sostenida >= 2 s (el PLC declara fallo a los 3 s)
var discS = (online && ob !== contactor) ? (Number($getTag('{T['disc_s']}')) || 0) + 1 : 0;
var disc = discS >= 2 ? 1 : 0;
var planta = !online ? -1 : (seta ? 3 : ((fs || fa) ? 2 : (contactor ? 1 : 0)));
var bomba = !online ? -1 : (fa ? 2 : (disc ? 3 : (contactor ? 1 : 0)));
var ent = Number($getTag('{T['FT101_caudal']}')) || 0;
var sal = Number($getTag('{T['FT102_caudal']}')) || 0;
var nivel = Number($getTag('{T['LT101_nivel']}')) || 0;
var set = function (n, v) {{ $setTag(n, v); }};
set('{T['txt_stale']}', online ? '' : '???');
set('{T['plc_online']}', online); set('{T['it_online']}', itOnline);
set('{T['b_contactor']}', contactor); set('{T['b_seta']}', seta); set('{T['b_fsensor']}', fs);
set('{T['b_farranque']}', fa); set('{T['b_alta']}', alta); set('{T['b_baja']}', baja);
set('{T['b_reserva']}', reserva); set('{T['b_manual']}', manual);
set('{T['b_orden_bomba']}', ob); set('{T['b_orden_valvula']}', ov);
set('{T['seguridades_ok']}', seg); set('{T['disc_s']}', discS); set('{T['discrepancia']}', disc);
set('{T['estado_planta']}', planta); set('{T['estado_bomba']}', bomba);
set('{T['estado_valvula']}', !online ? -1 : ov);
set('{T['mando_habilitado']}', (online && manual === 1) ? 1 : 0);
set('{T['reset_visible']}', (online && fa === 1 && seta === 0) ? 1 : 0);
set('{T['balance_lpm']}', Math.round((ent - sal) * 10) / 10);
set('{T['nivel_pct']}', Math.round(nivel / 10));
set('{T['txt_planta']}', ['SIN COMUNICACIÓN', 'PARADA', 'EN MARCHA', 'FALLO', 'EMERGENCIA'][planta + 1]);
set('{T['txt_modo']}', !online ? '---' : (manual ? 'MANUAL' : 'AUTOMÁTICO'));
set('{T['txt_bomba']}', ['SIN DATOS', 'PARADA', 'EN MARCHA', 'FALLO ARRANQUE', 'SIN CONFIRMACIÓN'][bomba + 1]);
set('{T['txt_valvula']}', !online ? 'SIN DATOS' : (ov ? 'ABIERTA' : 'CERRADA'));
set('{T['txt_consumo']}', !online ? 'SIN DATOS' : (reserva ? 'EN RESERVA' : 'PERMITIDO'));
set('{T['txt_sensor']}', !online ? 'SIN DATOS' : (fs ? 'FUERA DE RANGO' : 'SEÑAL VÁLIDA'));
set('{T['txt_plc']}', online ? 'EN LÍNEA' : 'SIN COMUNICACIÓN');
set('{T['txt_it']}', itOnline ? 'EN LÍNEA' : 'SIN CONEXIÓN');
set('{T['txt_seguridades']}', !online ? 'SIN DATOS' : (seg ? 'SEGURIDADES OK' : 'BLOQUEO ACTIVO'));
""".strip()
    return {"id": "s_" + uid("script", "decode"), "name": "decodificar_estado", "code": code, "sync": False,
            "parameters": [], "mode": "SERVER", "permission": 0, "permissionRoles": {"enabled": []},
            "scheduling": {"mode": "interval", "interval": 1, "schedules": []}}


# --------------------------------------------------------------------------- alarmas (ISA-18.2)
def _alarm(name: str, tag: str, level: str, text: str, group: str, vmin=1, vmax=1, delay=2) -> dict:
    colors = {"highhigh": (EMERG, "#FFFFFF"), "high": (WARN, "#1B1B1B"), "low": ("#FADE2A", "#1B1B1B"),
              "info": (INFO, "#FFFFFF")}
    bk, fg = colors[level]
    sub = {"enabled": True, "min": vmin, "max": vmax, "text": text, "group": group,
           "ackmode": "float" if level == "info" else "ackactive", "bkcolor": bk, "color": fg,
           "checkdelay": 1, "timedelay": delay}
    return {"name": name, "property": {"variableId": tag, "permission": 0,
                                       "permissionRoles": {"show": [], "enabled": []}},
            "value": "", "actions": {}, level: sub}


def alarms() -> list[dict]:
    return [
        _alarm("SETA ACTIVA", T["b_seta"], "highhigh", "SETA DE EMERGENCIA ACTIVA", "Seguridad", delay=0),
        _alarm("FALLO ARRANQUE P-101", T["b_farranque"], "highhigh", "FALLO ARRANQUE P-101", "Bomba"),
        _alarm("FALLO LT-101", T["b_fsensor"], "highhigh", "FALLO TRANSMISOR LT-101",
               "Depósito"),
        _alarm("COMUNICACION PLC", T["plc_online"], "highhigh", "COMUNICACIÓN PLC PERDIDA", "Sistema",
               vmin=-1, vmax=0, delay=5),
        _alarm("NIVEL MUY ALTO", T["b_alta"], "high", "NIVEL MUY ALTO TK-101 (≥ 950 L)", "Depósito"),
        _alarm("NIVEL MUY BAJO", T["b_baja"], "high", "NIVEL MUY BAJO TK-101 (≤ 100 L)", "Depósito"),
        _alarm("CONSUMO EN RESERVA", T["b_reserva"], "info", "CONSUMO EN RESERVA (≤ 200 L)", "Depósito"),
        _alarm("MODO MANUAL", T["b_manual"], "info", "PLANTA EN MODO MANUAL", "Operación"),
    ]


# --------------------------------------------------------------------------- graficas
def _line(tag_name: str, label: str, color: str, yaxis: int = 1, zones: list | None = None) -> dict:
    device = "FUXA Server" if tag_name in INTERNAL_NUM else "PLC_Tanque"
    return {"device": device, "id": T[tag_name], "name": tag_name, "label": label, "color": color,
            "fill": None, "yaxis": yaxis, "lineInterpolation": 0, "lineWidth": 2, "spanGaps": True,
            "zones": zones or []}


CHART_IDS = {k: "c_" + uid("chart", k) for k in ("nivel", "caudales", "bomba", "equipos")}


def charts() -> list[dict]:
    return [
        {"id": CHART_IDS["nivel"], "name": "Nivel TK-101 (L)",
         "lines": [_line("LT101_nivel", "Nivel", PROCESS)]},
        {"id": CHART_IDS["caudales"], "name": "Caudales (l/min)",
         "lines": [_line("FT101_caudal", "Entrada FT-101", PROCESS), _line("FT102_caudal", "Salida FT-102", "#4FC3C3"),
                   _line("balance_lpm", "Balance", "#B877D9")]},
        {"id": CHART_IDS["bomba"], "name": "Bomba P-101 (%)",
         "lines": [_line("P101_velocidad", "Velocidad real", PROCESS), _line("CMD_consigna", "Consigna manual", WARN)]},
        {"id": CHART_IDS["equipos"], "name": "Estado de equipos (0/1)",
         "lines": [_line("b_contactor", "Bomba en marcha", RUN), _line("b_orden_valvula", "Valvula abierta", MANUAL),
                   _line("b_manual", "Modo manual", WARN)]},
    ]
