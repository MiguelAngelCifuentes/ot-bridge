"""Adds the "Simulador" tab to the FUXA project through the FUXA REST API.

Creates (or replaces, it is idempotent) the SIM_Campo Modbus device pointing at the
field simulator :5022, its tags, the server-side helper tags and script, the
"SIMULACION ACTIVA" alarm, the v_otb_simulation view and its navigation entry.
A backup of the current project is saved before anything is changed.

Usage:
    python build_simulation_view.py --url http://localhost:1881 --user admin
    (password from --password or the FUXA_PASSWORD environment variable)
"""

import argparse
import getpass
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path(__file__).resolve().parent / "backups"

# Estacion de instructor del simulador de planta (servicio field-simulator de la red OT)
SIMULATOR_ADDRESS = os.environ.get("OTB_SIMULATOR_ADDRESS", "field-simulator:5022")
DEVICE_ID = "d_sim_campo"
DEVICE_NAME = "SIM_Campo"
SERVER_DEVICE_ID = "0"
VIEW_ID = "v_otb_simulation"
VIEW_NAME = "Simulador"
SCRIPT_ID = "s_sim_estado"
ALARM_NAME = "SIMULACIÓN ACTIVA"
NAV_PERMISSION = 0
BUTTON_PERMISSION = 10

HOLDING = "400000"
INPUT = "300000"

FONT = "Roboto, sans-serif"
BACKGROUND = "#2B3038"
HEADER = "#1E232A"
PANEL = "#343A44"
BORDER = "#46505C"
TEXT = "#E6E9ED"
MUTED = "#9AA4AF"
OFFLINE = "#3A3F47"
IDLE = "#555F6B"
OK = "#4CAF50"
WARNING = "#FF9830"
FAULT = "#F2495C"
BLUE = "#5794F2"

PLC_ONLINE_TAG = "t_6d4cbdff5c4a7855"
PLC_TAGS = {
    "level": "t_0ef5fd4f49215eb7",
    "level_ma": "t_69e23c9635d6d0e7",
    "inlet": "t_9f687861464ff8c7",
    "outlet": "t_182e2e154e75680c",
    "speed": "t_5676d1b7127b7d31",
    "contactor": "t_4198db1d60669822",
    "seta": "t_9ce6e880881dee20",
    "pump_order": "t_2d7d4c29fc420a0d",
    "valve_order": "t_b4a9814f2e14e994",
}

FAULTS = [
    ("bomba", 0, "BOMBA P-101 AVERIADA", "Recibe orden de marcha pero no gira ni da caudal"),
    ("cable", 1, "CABLE LT-101 CORTADO", "La señal de nivel cae a 0 mA (fallo de sensor)"),
    ("corto", 2, "CORTOCIRCUITO LT-101", "La señal de nivel sube a 22 mA (fallo de sensor)"),
    ("contactor", 3, "CONTACTOR SIN CONFIRMACIÓN", "La confirmación de marcha no llega: fallo de arranque a los 3 s"),
    ("seta", 4, "SETA DE EMERGENCIA DE CAMPO", "Seta física pulsada: la bomba se detiene"),
]


def tag_id(name: str) -> str:
    return "t_" + hashlib.sha1(f"sim:{name}".encode()).hexdigest()[:16]


def item_id(prefix: str, name: str) -> str:
    return f"{prefix}_" + hashlib.sha1(f"simview:{name}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------- device and tags

def modbus_tag(name, memaddress, offset, divisor, description):
    return {
        "id": tag_id(name),
        "name": name,
        "type": "Int16",
        "memaddress": memaddress,
        "address": offset + 1,
        "divisor": divisor,
        "description": description,
        "daq": {"enabled": False, "interval": 60, "changed": False, "restored": False},
    }


DEVICE_TAGS = [
    *[modbus_tag(f"SIM_f_{key}", HOLDING, offset, 1, f"Inyección: {title} (HR{offset})")
      for key, offset, title, _ in FAULTS],
    modbus_tag("SIM_clear", HOLDING, 5, 1, "Pulso: quitar todos los fallos (HR5)"),
    modbus_tag("SIM_nivel_forzado", HOLDING, 6, 1, "Nivel a forzar en litros (HR6)"),
    modbus_tag("SIM_forzar", HOLDING, 7, 1, "Pulso: aplicar nivel forzado (HR7)"),
    modbus_tag("SIM_nivel_real", INPUT, 0, 10, "Nivel real del depósito (IR0)"),
    modbus_tag("SIM_caudal_ent", INPUT, 1, 10, "Caudal de entrada real (IR1)"),
    modbus_tag("SIM_caudal_sal", INPUT, 2, 10, "Caudal de salida real (IR2)"),
    modbus_tag("SIM_desborde", INPUT, 3, 10, "Caudal de desbordamiento (IR3)"),
    modbus_tag("SIM_velocidad", INPUT, 4, 1, "Velocidad real de la bomba (IR4)"),
    modbus_tag("SIM_contactor", INPUT, 5, 1, "Contactor confirmado en campo (IR5)"),
    modbus_tag("SIM_cmd_marcha", INPUT, 6, 1, "Orden de marcha recibida en campo (IR6)"),
    modbus_tag("SIM_cmd_consigna", INPUT, 7, 1, "Consigna de velocidad recibida (IR7)"),
    modbus_tag("SIM_cmd_valvula", INPUT, 8, 1, "Orden de válvula recibida (IR8)"),
    modbus_tag("SIM_fallos", INPUT, 9, 1, "Bitmask de fallos activos (IR9)"),
    modbus_tag("SIM_senal_nivel", INPUT, 10, 100, "Señal de nivel enviada al PLC (IR10)"),
]


def build_device() -> dict:
    return {
        "id": DEVICE_ID,
        "name": DEVICE_NAME,
        "type": "ModbusTCP",
        "enabled": True,
        "polling": 1000,
        "property": {
            "address": SIMULATOR_ADDRESS, "port": None, "slot": None, "rack": None,
            "slaveid": "1", "baudrate": 9600, "databits": 8, "stopbits": 1, "parity": "None",
            "connectionOption": "TcpPort", "delay": 10, "forceFC16": False,
        },
        "tags": {tag["id"]: tag for tag in DEVICE_TAGS},
    }


def server_tag(name, kind="number", init="0"):
    return {
        "id": tag_id(name), "name": name, "label": name, "value": "", "type": kind, "init": init,
        "daq": {"enabled": False, "interval": 60, "changed": False, "restored": False},
        "description": "Calculado por script (simulación)",
    }


CONNECTION_TAG = {
    "id": tag_id("connection"), "name": f"{DEVICE_NAME} Connection Status",
    "label": "Estado conexion simulador", "value": "", "type": "number", "memaddress": DEVICE_ID,
    "daq": {"enabled": False, "interval": 60, "changed": False, "restored": False},
    "init": "", "sysType": 1,
}

STATE_TAGS = ["sim_online", "sim_activa", *[f"sim_f_{key}" for key, *_ in FAULTS],
              "sim_contactor", "sim_marcha", "sim_valvula"]
TEXT_TAGS = ["txt_sim_conexion", "txt_sim_fallos"]


def server_tags() -> list[dict]:
    return [CONNECTION_TAG, *[server_tag(n) for n in STATE_TAGS],
            *[server_tag(n, "string", "---") for n in TEXT_TAGS]]


def T(name: str) -> str:
    return tag_id(name)


# ---------------------------------------------------------------- script and alarm

def build_script() -> dict:
    faults = "\n".join(
        f"set('{T('sim_f_' + key)}', b(f & {1 << offset}));" for key, offset, *_ in FAULTS
    )
    code = f"""var st = $getTag('{T('connection')}');
// estado de conexion de FUXA: 0 = sin respuesta, 3 = aviso, 5 = en linea
var online = Number(st) >= 3 ? 1 : 0;
var f = online ? (Number($getTag('{T('SIM_fallos')}')) || 0) : 0;
// sin comunicacion los estados valen -1 (gris en la vista, la alarma no los ve activos)
function b(v) {{ return online ? (v ? 1 : 0) : -1; }}
function n(id) {{ return Number($getTag(id)) || 0; }}
var set = function (id, v) {{ $setTag(id, v); }};
var count = 0;
for (var i = 0; i < 5; i++) {{ if (f & (1 << i)) {{ count++; }} }}
set('{T('sim_online')}', online);
set('{T('sim_activa')}', online ? (f ? 1 : 0) : -1);
{faults}
set('{T('sim_contactor')}', b(n('{T('SIM_contactor')}')));
set('{T('sim_marcha')}', b(n('{T('SIM_cmd_marcha')}')));
set('{T('sim_valvula')}', b(n('{T('SIM_cmd_valvula')}')));
set('{T('txt_sim_conexion')}', online ? 'EN LÍNEA' : 'SIN COMUNICACIÓN');
set('{T('txt_sim_fallos')}', !online ? '---' : (count ? count + ' INYECTADO' + (count > 1 ? 'S' : '') : 'NINGUNO'));"""
    return {
        "id": SCRIPT_ID, "name": "simulacion_estado", "code": code, "sync": False,
        "parameters": [], "mode": "SERVER", "permission": 0,
        "permissionRoles": {"enabled": []},
        "scheduling": {"mode": "interval", "interval": 1, "schedules": []},
    }


def build_alarm() -> dict:
    return {
        "name": ALARM_NAME,
        "property": {"variableId": T("sim_activa"), "permission": 0,
                     "permissionRoles": {"show": [], "enabled": []}},
        "value": "", "actions": {},
        "high": {"enabled": True, "min": 1, "max": 1,
                 "text": "FALLOS DE SIMULACIÓN INYECTADOS EN CAMPO", "group": "Simulación",
                 "ackmode": "float", "bkcolor": WARNING, "color": "#000000",
                 "checkdelay": 1, "timedelay": 1},
    }


# ---------------------------------------------------------------- view

class ViewBuilder:

    def __init__(self):
        self.svg: list[str] = []
        self.items: dict[str, dict] = {}

    def rect(self, x, y, w, h, fill, stroke="none", rx=8):
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
                        f'stroke="{stroke}" stroke-width="1" />')

    def text(self, x, y, value, size=14, color=TEXT, bold=False, anchor="start", extra=""):
        weight = "bold" if bold else "normal"
        self.svg.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-family="{FONT}" '
                        f'text-anchor="{anchor}" font-weight="{weight}" {extra}>{_escape(value)}</text>')

    def panel(self, x, y, w, h, title):
        self.rect(x, y, w, h, PANEL, BORDER)
        self.text(x + 20, y + 32, title, 15, MUTED, True, extra='letter-spacing="1"')

    def value(self, name, x, y, variable, unit=None, decimals=0, size=18, anchor="middle",
              online_tag=None):
        wid = item_id("VAL", name)
        ranges = [{"type": 1, "text": unit, "fractionDigits": decimals}] if unit is not None else []
        self.items[wid] = {
            "id": wid, "type": "svg-ext-value", "name": name, "label": "Value", "hide": False,
            "lock": False,
            "property": {"variableId": variable, "bitmask": 0, "options": {}, "ranges": ranges,
                         "events": [], "actions": _online_actions(online_tag), "readonly": True},
        }
        attrs = (f'fill="{TEXT}" font-size="{size}" font-family="{FONT}" text-anchor="{anchor}" '
                 f'font-weight="bold"')
        self.svg.append(f'<g id="{wid}" type="svg-ext-value" {attrs} stroke-width="0">'
                        f'<text x="{x}" y="{y}" id="{wid}_t" {attrs}>---</text></g>')

    def semaphore(self, name, x, y, w, h, variable, active_color, rx=6):
        wid = item_id("GSE", name)
        self.items[wid] = {
            "id": wid, "type": "svg-ext-gauge_semaphore", "name": name, "label": "HtmlSemaphore",
            "hide": False, "lock": False,
            "property": {"variableId": variable, "bitmask": 0, "options": {},
                         "ranges": [{"min": -1, "max": -1, "color": OFFLINE},
                                    {"min": 0, "max": 0, "color": IDLE},
                                    {"min": 1, "max": 1, "color": active_color}],
                         "events": [], "actions": [], "readonly": True},
        }
        self.svg.append(f'<g id="{wid}" type="svg-ext-gauge_semaphore"><rect id="{wid}_s" x="{x}" '
                        f'y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{IDLE}" stroke="none" '
                        f'stroke-width="2"/></g>')

    def button(self, name, x, y, w, h, label, variable, value, color, size=15):
        wid = item_id("HXB", name)
        self.items[wid] = {
            "id": wid, "type": "svg-ext-html_button", "name": name, "label": "HtmlButton",
            "hide": False, "lock": False,
            "property": {"variableId": variable, "text": label, "options": {},
                         "events": [{"type": "click", "action": "onSetValue", "actparam": str(value)}],
                         "actions": _online_actions(T("sim_online")),
                         "permission": BUTTON_PERMISSION,
                         "permissionRoles": {"show": [], "enabled": []}},
        }
        style = (f"width:calc(100% - 4px);height:calc(100% - 4px);text-align:center;"
                 f"background-color:{color};color:#FFFFFF;font-size:{size}px;font-family:{FONT};"
                 f"font-weight:bold;border:none;border-radius:6px;cursor:pointer;")
        self.svg.append(f'<g id="{wid}" type="svg-ext-html_button" fill="rgba(0,0,0,0)" '
                        f'stroke="rgba(0,0,0,0)"><rect id="svg_{wid}" x="{x}" y="{y}" width="{w}" '
                        f'height="{h}" stroke-width="0"/><foreignObject id="H-{wid}" x="{x}" y="{y}" '
                        f'width="{w}" height="{h}"><BUTTON id="B-{wid}" class="md-btn md-btn-raised" '
                        f'style="{style}">{_escape(label)}</BUTTON></foreignObject></g>')

    def number_input(self, name, x, y, w, h, variable, minimum, maximum):
        wid = item_id("HXI", name)
        self.items[wid] = {
            "id": wid, "type": "svg-ext-html_input", "name": name, "label": "HtmlInput",
            "hide": False, "lock": False,
            "property": {"variableId": variable, "bitmask": 0, "events": [],
                         "actions": _online_actions(T("sim_online")),
                         "permission": BUTTON_PERMISSION,
                         "permissionRoles": {"show": [], "enabled": []},
                         "options": {"updated": True, "numeric": True, "min": minimum,
                                     "max": maximum, "type": "number", "selectOnClick": True,
                                     "actionOnEsc": "update"},
                         "ranges": []},
        }
        style = (f"width:calc(100% - 7px);height:calc(100% - 7px);text-align:center;"
                 f"border:1px solid {BORDER};border-radius:6px;font-size:20px;font-family:{FONT};"
                 f"background-color:#1B2027;color:{TEXT};")
        self.svg.append(f'<g id="{wid}" type="svg-ext-html_input" fill="#FFFFFF" stroke="#000000">'
                        f'<rect id="svg_{wid}" x="{x}" y="{y}" width="{w}" height="{h}" '
                        f'stroke-width="0" fill="rgba(0,0,0,0)"/><foreignObject id="H-{wid}" x="{x}" '
                        f'y="{y}" width="{w}" height="{h}"><INPUT id="I-{wid}" type="text" value="" '
                        f'style="{style}"/></foreignObject></g>')

    def build(self) -> dict:
        svg = ('<svg width="1600" height="900" xmlns="http://www.w3.org/2000/svg" '
               'xmlns:svg="http://www.w3.org/2000/svg">\n <g>\n  <title>Layer 1</title>\n'
               + "\n".join(self.svg) + "\n </g>\n</svg>")
        return {
            "id": VIEW_ID, "name": VIEW_NAME, "type": "svg", "variables": {},
            "property": {"events": []},
            "profile": {"width": 1600, "height": 900, "bkcolor": BACKGROUND, "margin": 0,
                        "align": "topCenter", "gridType": "fixed", "viewRenderDelay": 0},
            "items": self.items, "svgcontent": svg,
        }


def _online_actions(online_tag):
    if online_tag is None:
        return []
    return [
        {"variableId": online_tag, "bitmask": 0, "range": {"min": -1, "max": 0}, "type": "hide",
         "options": {}},
        {"variableId": online_tag, "bitmask": 0, "range": {"min": 1, "max": 1}, "type": "show",
         "options": {}},
    ]


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_view() -> dict:
    view = ViewBuilder()
    _header(view)
    _faults_panel(view)
    _force_level_panel(view)
    _truth_panel(view)
    return view.build()


def _header(view: ViewBuilder) -> None:
    view.rect(0, 0, 1600, 64, HEADER, rx=0)
    view.text(24, 40, "SIMULADOR", 22, TEXT, True)
    view.semaphore("sh_conexion", 560, 12, 260, 40, T("sim_online"), OK)
    view.text(572, 26, "SIMULADOR :5022", 10, "#FFFFFF", extra='letter-spacing="1" opacity="0.75"')
    view.value("sh_conexion_txt", 690, 45, T("txt_sim_conexion"), size=16)
    view.semaphore("sh_fallos", 832, 12, 300, 40, T("sim_activa"), WARNING)
    view.text(844, 26, "FALLOS INYECTADOS", 10, "#FFFFFF", extra='letter-spacing="1" opacity="0.75"')
    view.value("sh_fallos_txt", 982, 45, T("txt_sim_fallos"), size=16)
    view.text(1576, 38, "Estación de instructor — actúa sobre la planta, no sobre el PLC",
              12, MUTED, anchor="end")


def _faults_panel(view: ViewBuilder) -> None:
    view.panel(24, 84, 760, 476, "INYECCIÓN DE FALLOS")
    for row, (key, _, title, effect) in enumerate(FAULTS):
        y = 136 + row * 66
        view.semaphore(f"sf_{key}", 44, y, 16, 48, T(f"sim_f_{key}"), FAULT, rx=4)
        view.text(76, y + 20, title, 15, TEXT, True)
        view.text(76, y + 40, effect, 12, MUTED)
        view.button(f"bf_{key}_on", 500, y, 130, 48, "INYECTAR", T(f"SIM_f_{key}"), 1, FAULT)
        view.button(f"bf_{key}_off", 640, y, 130, 48, "RESTABLECER", T(f"SIM_f_{key}"), 0, IDLE)
    view.button("bf_clear", 44, 482, 726, 58, "QUITAR TODOS LOS FALLOS", T("SIM_clear"), 1, OK, 18)


def _force_level_panel(view: ViewBuilder) -> None:
    view.panel(24, 580, 760, 296, "FORZAR NIVEL DEL DEPÓSITO TK-101")
    view.text(44, 650, "Nivel real", 13, MUTED)
    view.value("fl_real", 44, 690, T("SIM_nivel_real"), " L", 1, 30, "start", T("sim_online"))
    view.text(300, 650, "Nuevo nivel (0–1000 L)", 13, MUTED)
    view.number_input("fl_input", 300, 660, 200, 48, T("SIM_nivel_forzado"), 0, 1000)
    view.button("fl_apply", 520, 660, 250, 48, "APLICAR NIVEL", T("SIM_forzar"), 1, BLUE)
    hints = [
        "Escribe el nivel y pulsa APLICAR: el depósito salta a ese valor y la física continúa.",
        "Umbrales del PLC: alarma alta ≥ 950 L · lleno 900 L · arranque bomba ≤ 300 L",
        "rearme consumo ≥ 250 L · reserva ≤ 200 L · alarma baja ≤ 100 L",
    ]
    for index, hint in enumerate(hints):
        view.text(44, 760 + index * 24, hint, 13, MUTED)


TRUTH_ROWS = [
    ("tr_nivel", "Nivel del depósito", "SIM_nivel_real", "level", " L", 1),
    ("tr_senal", "Señal LT-101", "SIM_senal_nivel", "level_ma", " mA", 2),
    ("tr_ent", "Caudal de entrada", "SIM_caudal_ent", "inlet", " lpm", 1),
    ("tr_sal", "Caudal de salida", "SIM_caudal_sal", "outlet", " lpm", 1),
    ("tr_desb", "Desbordamiento", "SIM_desborde", None, " lpm", 1),
    ("tr_vel", "Velocidad bomba P-101", "SIM_velocidad", "speed", " %", 0),
]

TRUTH_STATES = [
    ("ts_contactor", "Contactor confirmado", "sim_contactor", "contactor", OK),
    ("ts_marcha", "Orden de marcha bomba", "sim_marcha", "pump_order", OK),
    ("ts_valvula", "Orden de válvula de salida", "sim_valvula", "valve_order", OK),
    ("ts_seta", "Seta de emergencia", "sim_f_seta", "seta", FAULT),
]


def _truth_panel(view: ViewBuilder) -> None:
    view.panel(804, 84, 772, 792, "VERDAD FÍSICA vs. LO QUE VE EL PLC")
    _truth_columns(view, 140)
    for row, (name, label, field_tag, plc_key, unit, decimals) in enumerate(TRUTH_ROWS):
        y = 186 + row * 46
        view.rect(820, y - 28, 740, 40, "#2E343D", rx=4)
        view.text(836, y, label, 15)
        view.value(f"{name}_campo", 1250, y, T(field_tag), unit, decimals, 17,
                   online_tag=T("sim_online"))
        if plc_key:
            view.value(f"{name}_plc", 1450, y, PLC_TAGS[plc_key], unit, decimals, 17,
                       online_tag=PLC_ONLINE_TAG)
        else:
            view.text(1450, y, "no instrumentado", 13, MUTED, anchor="middle")
    view.text(824, 488, "ÓRDENES Y ESTADOS DIGITALES", 13, MUTED, True, extra='letter-spacing="1"')
    _truth_columns(view, 520)
    for row, (name, label, field_tag, plc_key, color) in enumerate(TRUTH_STATES):
        y = 566 + row * 46
        view.rect(820, y - 28, 740, 40, "#2E343D", rx=4)
        view.text(836, y, label, 15)
        view.semaphore(f"{name}_campo", 1200, y - 22, 100, 28, T(field_tag), color)
        view.semaphore(f"{name}_plc", 1400, y - 22, 100, 28, PLC_TAGS[plc_key], color)
    view.text(1250, 780, "Consigna de velocidad recibida en campo", 13, MUTED, anchor="end")
    view.value("tr_consigna", 1300, 780, T("SIM_cmd_consigna"), " %", 0, 17, "start",
               T("sim_online"))
    notes = [
        "Campo = valor físico real del simulador (:5022). PLC = lo que mide y decide el PLC (:502).",
        "Una diferencia entre columnas es exactamente lo que provoca un fallo inyectado.",
    ]
    for index, note in enumerate(notes):
        view.text(824, 824 + index * 22, note, 12, MUTED)


def _truth_columns(view: ViewBuilder, y: int) -> None:
    view.text(1250, y, "CAMPO (REAL)", 12, MUTED, True, "middle", 'letter-spacing="1"')
    view.text(1450, y, "PLC (MEDIDO)", 12, MUTED, True, "middle", 'letter-spacing="1"')


# ---------------------------------------------------------------- layout

def updated_layout(layout: dict) -> dict:
    items = [i for i in layout["navigation"]["items"] if i.get("view") != VIEW_ID]
    items.append({
        "text": VIEW_NAME, "view": VIEW_ID, "link": "", "icon": "science", "image": "",
        "permission": NAV_PERMISSION, "permissionRoles": {"show": [], "enabled": []},
    })
    layout["navigation"]["items"] = items
    return layout


# ---------------------------------------------------------------- FUXA API

class FuxaClient:

    def __init__(self, url: str):
        self._url = url.rstrip("/")
        self._token = ""

    def sign_in(self, user: str, password: str) -> None:
        response = self._request("POST", "/api/signin", {"username": user, "password": password})
        self._token = response["data"]["token"]

    def get_project(self) -> dict:
        return self._request("GET", "/api/project")

    def set_project_data(self, cmd: str, data) -> None:
        self._request("POST", "/api/projectData", {"cmd": cmd, "data": data})

    def _request(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self._url + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self._token:
            request.add_header("x-access-token", self._token)
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        return json.loads(payload) if payload else None


def save_backup(project: dict) -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / f"project-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(project, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def apply(client: FuxaClient) -> None:
    project = client.get_project()
    print(f"backup: {save_backup(project)}")

    server = project["devices"][SERVER_DEVICE_ID]
    server["tags"].update({tag["id"]: tag for tag in server_tags()})
    client.set_project_data("set-device", build_device())
    client.set_project_data("set-device", server)
    print(f"device {DEVICE_NAME} -> {SIMULATOR_ADDRESS} ({len(DEVICE_TAGS)} tags)")

    client.set_project_data("set-script", build_script())
    client.set_project_data("set-alarm", build_alarm())
    client.set_project_data("set-view", build_view())
    client.set_project_data("layout", updated_layout(project["hmi"]["layout"]))
    print(f"view {VIEW_ID}, script, alarm and navigation entry saved")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:1881")
    parser.add_argument("--user", default=os.environ.get("FUXA_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("FUXA_PASSWORD"))
    parser.add_argument("--dry-run", action="store_true", help="write the generated view to stdout")
    args = parser.parse_args()

    if args.dry_run:
        print(json.dumps(build_view(), indent=1))
        return 0

    client = FuxaClient(args.url)
    try:
        client.sign_in(args.user, args.password or getpass.getpass("FUXA password: "))
        apply(client)
    except urllib.error.HTTPError as error:
        print(f"FUXA API error {error.code}: {error.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
