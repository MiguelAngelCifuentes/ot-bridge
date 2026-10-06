"""Sistema de diseno y constructores de controles para el proyecto FUXA (SCADA OT).

Cada vista se construye en codigo: los constructores anaden a la vista el item JSON que FUXA
necesita y el fragmento SVG con el mismo id. Los formatos salen de FUXA 1.3.4 (plantillas reales
extraidas del editor y del codigo fuente de FUXA 1.3.4).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

# --------------------------------------------------------------------------- paleta ISA-101
# Fondo gris medio; lo normal es neutro y el color solo aparece para lo que requiere atencion.
BG = "#2B3038"            # fondo de las vistas
PANEL = "#343A44"         # tarjetas
PANEL_EDGE = "#46505C"
HEADER = "#1E232A"        # cabecera y barra de navegacion
TEXT = "#E6E9ED"
TEXT_DIM = "#9AA4AF"
EQUIP = "#7B8794"         # equipo en reposo (gris)
EQUIP_DARK = "#555F6B"
PROCESS = "#8AB8FF"       # valor de proceso (igual que la suite Grafana)
MANUAL = "#5794F2"
RUN = "#4CAF50"           # en marcha / abierto
WARN = "#FF9830"
CRIT = "#F2495C"
EMERG = "#C4162A"
INFO = "#6C8EBF"
OFFLINE = "#3A3F47"       # sin datos (comunicacion perdida)
WATER = "#2F6FB0"
FONT = "Roboto, sans-serif"

# --------------------------------------------------------------------------- permisos
# Grupos FUXA (UserGroups): Viewer 1, Operator 2, Engineer 4, Supervisor 8, Manager 16, Admin 128.
# permission = (grupos_que_ven << 8) | grupos_que_operan ; 0 = sin restriccion
VIEWER, OPERATOR, SUPERVISOR, ADMIN = 1, 2, 8, 128
OPERATE = OPERATOR | SUPERVISOR          # mandos de operacion
SUPERVISE = SUPERVISOR                   # rearmes y diagnostico


def perm(show: int = 0, enable: int = 0) -> int:
    return (show << 8) | enable


def uid(*parts: str) -> str:
    """Id estable a partir de un nombre (los ids no cambian entre builds)."""
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- vista
@dataclass
class View:
    id: str
    name: str
    width: int = 1600
    height: int = 900
    bkcolor: str = BG
    svg: list[str] = field(default_factory=list)
    items: dict = field(default_factory=dict)

    def static(self, fragment: str) -> None:
        self.svg.append(fragment)

    def add(self, item: dict, fragment: str) -> None:
        assert item["id"] not in self.items, f"id duplicado en {self.name}: {item['id']}"
        self.items[item["id"]] = item
        self.svg.append(fragment)

    def nid(self, prefix: str, name: str) -> str:
        return f"{prefix}_{uid(self.id, name)}"

    def to_json(self) -> dict:
        body = "\n".join(self.svg)
        svg = (f'<svg width="{self.width}" height="{self.height}" xmlns="http://www.w3.org/2000/svg" '
               f'xmlns:svg="http://www.w3.org/2000/svg">\n <g>\n  <title>Layer 1</title>\n{body}\n </g>\n</svg>')
        return {"id": self.id, "name": self.name, "type": "svg", "variables": {}, "property": {"events": []},
                "profile": {"width": self.width, "height": self.height, "bkcolor": self.bkcolor, "margin": 0,
                            "align": "topCenter", "gridType": "fixed", "viewRenderDelay": 0},
                "items": self.items, "svgcontent": svg}


# --------------------------------------------------------------------------- SVG estatico
def rect(x, y, w, h, fill=PANEL, stroke="none", rx=6, sw=1, extra="") -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" {extra}/>')


def text(x, y, s, size=14, fill=TEXT, anchor="start", weight="normal", extra="") -> str:
    return (f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-family="{FONT}" '
            f'text-anchor="{anchor}" font-weight="{weight}" {extra}>{escape(str(s))}</text>')


def line(x1, y1, x2, y2, stroke=EQUIP_DARK, sw=1, dash="") -> str:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}/>'


def path(d, stroke=EQUIP, fill="none", sw=2) -> str:
    return f'<path d="{d}" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"/>'


def card(v: View, x, y, w, h, title: str, subtitle: str = "") -> None:
    """Tarjeta con titulo: la unidad de composicion de todas las vistas."""
    v.static(rect(x, y, w, h, PANEL, PANEL_EDGE, 8))
    v.static(text(x + 16, y + 28, title.upper(), 13, TEXT_DIM, weight="bold", extra='letter-spacing="1"'))
    if subtitle:
        v.static(text(x + w - 16, y + 28, subtitle, 12, TEXT_DIM, "end"))


# --------------------------------------------------------------------------- controles
# Calidad del dato: model.py registra aqui el tag de comunicacion, el texto de dato no valido y los tags
# que dependen del PLC. Sus valores se ocultan sin comunicacion y en su lugar aparece "???" en ambar.
QUALITY = {"online": "", "stale_text": "", "tags": set()}


def value(v: View, name: str, tag: str, x, y, *, size=28, color=TEXT, unit="", digits: int | None = None,
          anchor="middle", weight="normal") -> str:
    """Valor numerico o texto de un tag (svg-ext-value)."""
    gid = v.nid("VAL", name)
    actions = []
    if tag in QUALITY["tags"]:
        on = QUALITY["online"]
        actions = [{"variableId": on, "bitmask": 0, "range": {"min": -1, "max": 0}, "type": "hide", "options": {}},
                   {"variableId": on, "bitmask": 0, "range": {"min": 1, "max": 1}, "type": "show", "options": {}}]
        value(v, f"{name}_q", QUALITY["stale_text"], x, y, size=size, color=WARN, anchor=anchor, weight=weight)
    # type 1 = PropertyType.output (numerico; la cadena "output" no muestra la unidad)
    ranges = [{"type": 1, "text": unit, "fractionDigits": digits}] if (unit or digits is not None) else []
    item = {"id": gid, "type": "svg-ext-value", "name": name, "label": "Value", "hide": False, "lock": False,
            "property": {"variableId": tag, "bitmask": 0, "options": {}, "ranges": ranges, "events": [],
                         "actions": actions, "readonly": True}}
    frag = (f'<g id="{gid}" type="svg-ext-value" fill="{color}" font-size="{size}" font-family="{FONT}" '
            f'text-anchor="{anchor}" font-weight="{weight}" stroke-width="0">'
            f'<text x="{x}" y="{y}" id="{gid}_t" fill="{color}" font-size="{size}" font-family="{FONT}" '
            f'text-anchor="{anchor}" font-weight="{weight}">---</text></g>')
    v.add(item, frag)
    return gid


def lamp(v: View, name: str, tag: str, x, y, w, h, *, bit: int = 0, on=RUN, off=EQUIP_DARK, rx=4,
         ranges: list[tuple[float, float, str]] | None = None, shape="rect", blink: tuple | None = None,
         events: list | None = None, stroke="none", d: str = "") -> str:
    """Senalizacion por color (svg-ext-gauge_semaphore). Con bit: se evalua (valor & bit) -> 1/0.

    blink = (bit_o_0, min, max, colorA, colorB): parpadeo cuando el valor (enmascarado) esta en rango.
    """
    gid = v.nid("GSE", name)
    rng = list(ranges or [(1, 1, on), (0, 0, off)])
    if not bit and not any(a <= -1 <= b for a, b, _ in rng):
        rng.insert(0, (-1, -1, OFFLINE))     # sin comunicacion: gris neutro
    actions = []
    if blink:
        b_bit, bmin, bmax, ca, cb = blink
        actions.append({"variableId": tag, "bitmask": b_bit, "range": {"min": bmin, "max": bmax}, "type": "blink",
                        "options": {"fillA": ca, "fillB": cb, "strokeA": stroke, "strokeB": stroke,
                                    "interval": 600}})
    item = {"id": gid, "type": "svg-ext-gauge_semaphore", "name": name, "label": "HtmlSemaphore", "hide": False,
            "lock": False, "property": {"variableId": tag, "bitmask": bit, "options": {},
                                        "ranges": [{"min": a, "max": b, "color": c} for a, b, c in rng],
                                        "events": events or [], "actions": actions, "readonly": True}}
    if shape == "path":
        child = f'<path id="{gid}_s" d="{d}" fill="{off}" stroke="{stroke}" stroke-width="2"/>'
    elif shape == "circle":
        child = (f'<ellipse id="{gid}_s" cx="{x + w / 2}" cy="{y + h / 2}" rx="{w / 2}" ry="{h / 2}" '
                 f'fill="{off}" stroke="{stroke}" stroke-width="2"/>')
    else:
        child = (f'<rect id="{gid}_s" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{off}" '
                 f'stroke="{stroke}" stroke-width="2"/>')
    cursor = ' style="cursor:pointer"' if events else ""
    v.add(item, f'<g id="{gid}" type="svg-ext-gauge_semaphore"{cursor}>{child}</g>')
    return gid


def ev_set(value_) -> dict:
    return {"type": "click", "action": "onSetValue", "actparam": str(value_)}


def ev_dialog(view_id: str) -> dict:
    return {"type": "click", "action": "ondialog", "actparam": view_id, "actoptions": {}}


def ev_page(view_id: str) -> dict:
    return {"type": "click", "action": "onpage", "actparam": view_id, "actoptions": {}}


def ev_close() -> dict:
    return {"type": "click", "action": "onclose", "actparam": ""}


def act(kind: str, tag: str, vmin, vmax, bit: int = 0) -> dict:
    """Accion hide/show sobre un control segun el valor de un tag."""
    return {"variableId": tag, "bitmask": bit, "range": {"min": vmin, "max": vmax}, "type": kind, "options": {}}


def button(v: View, name: str, label: str, x, y, w, h, *, tag: str = "", events: list | None = None,
           bg=EQUIP_DARK, fg=TEXT, size=15, permission: int = 0, actions: list | None = None,
           ranges: list[tuple[float, float, str, str]] | None = None, weight="bold") -> str:
    """Boton HTML (svg-ext-html_button). ranges=(min,max,fondo,texto) colorea segun el valor del tag."""
    gid = v.nid("HXB", name)
    prop = {"variableId": tag, "text": label, "options": {}, "events": events or [], "actions": actions or [],
            "permission": permission, "permissionRoles": {"show": [], "enabled": []}}
    if ranges:
        prop["ranges"] = [{"min": a, "max": b, "color": c, "stroke": s} for a, b, c, s in ranges]
    item = {"id": gid, "type": "svg-ext-html_button", "name": name, "label": "HtmlButton", "hide": False,
            "lock": False, "property": prop}
    style = (f"width:calc(100% - 4px);height:calc(100% - 4px);text-align:center;background-color:{bg};"
             f"color:{fg};font-size:{size}px;font-family:{FONT};font-weight:{weight};border:none;"
             f"border-radius:6px;cursor:pointer;")
    frag = (f'<g id="{gid}" type="svg-ext-html_button" fill="rgba(0,0,0,0)" stroke="rgba(0,0,0,0)">'
            f'<rect id="svg_{gid}" x="{x}" y="{y}" width="{w}" height="{h}" stroke-width="0"/>'
            f'<foreignObject id="H-{gid}" x="{x}" y="{y}" width="{w}" height="{h}">'
            f'<BUTTON id="B-{gid}" class="md-btn md-btn-raised" style="{style}">{escape(label)}</BUTTON>'
            f'</foreignObject></g>')
    v.add(item, frag)
    return gid


def progress(v: View, name: str, tag: str, x, y, w, h, *, vmin=0, vmax=100, color=WATER, bg="#1B2027") -> str:
    """Barra vertical (svg-ext-gauge_progress): se usa como relleno del deposito."""
    gid = v.nid("GXP", name)
    item = {"id": gid, "type": "svg-ext-gauge_progress", "name": name, "label": "HtmlProgress", "hide": False,
            "lock": False, "property": {"variableId": tag, "bitmask": 0, "options": {},
                                        "ranges": [{"min": vmin, "max": vmax, "color": color, "type": 0,
                                                    "style": [False, False]}],
                                        "events": [], "actions": []}}
    frag = (f'<g id="{gid}" type="svg-ext-gauge_progress" x="{x}" y="{y}">'
            f'<rect id="A-{gid}" x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}" stroke="none"/>'
            f'<rect id="B-{gid}" x="{x}" y="{y + h}" width="{w}" height="0" fill="{color}" stroke="none"/>'
            f'<foreignObject id="H-{gid}" x="{x}" y="{y}" width="{w}" height="{h}"/></g>')
    v.add(item, frag)
    return gid


def pipe(v: View, name: str, d: str, flow_tag: str, *, width=10, pipe_color=EQUIP_DARK, content=WATER,
         border="#1B2027", bit: int = 0) -> str:
    """Tuberia animada (svg-ext-pipe): el contenido fluye si flow_tag > 0 (o si el bit esta activo)."""
    gid = v.nid("PIE", name)
    run_min = 1 if bit else 0.1
    actions = [
        {"variableId": flow_tag, "bitmask": bit, "range": {"min": run_min, "max": 100000}, "type": "clockwise",
         "options": {}},
        {"variableId": flow_tag, "bitmask": bit, "range": {"min": -100000, "max": run_min / 2}, "type": "hidecontent",
         "options": {}},
    ]
    options = {"border": border, "borderWidth": width + 4, "pipe": pipe_color, "pipeWidth": width,
               "content": content, "contentWidth": max(width - 4, 2), "contentSpace": 18}
    item = {"id": gid, "type": "svg-ext-pipe", "name": name, "label": "Pipe", "hide": False, "lock": False,
            "property": {"variableId": "", "bitmask": 0, "options": options, "ranges": [], "events": [],
                         "actions": actions}}
    frag = (f'<g id="{gid}" type="svg-ext-pipe" style="pointer-events:none">'
            f'<path id="bPIE_{gid}" d="{d}" stroke="{border}" stroke-width="{width + 4}" fill="none"/>'
            f'<path id="pPIE_{gid}" d="{d}" stroke="{pipe_color}" stroke-width="{width}" fill="none"/>'
            f'<path id="cPIE_{gid}" d="{d}" stroke="{content}" stroke-width="{max(width - 4, 2)}" fill="none" '
            f'stroke-dasharray="18 18" style="display:none"/></g>')
    v.add(item, frag)
    return gid


def number_input(v: View, name: str, tag: str, x, y, w, h, *, vmin=0, vmax=100, permission: int = 0,
                 actions: list | None = None) -> str:
    """Campo numerico con limites (svg-ext-html_input): escribe al pulsar Enter."""
    gid = v.nid("HXI", name)
    item = {"id": gid, "type": "svg-ext-html_input", "name": name, "label": "HtmlInput", "hide": False,
            "lock": False, "property": {"variableId": tag, "bitmask": 0, "events": [], "actions": actions or [],
                                        "permission": permission, "permissionRoles": {"show": [], "enabled": []},
                                        "options": {"updated": True, "numeric": True, "min": vmin, "max": vmax,
                                                    "type": "number", "selectOnClick": True,
                                                    "actionOnEsc": "update"}, "ranges": []}}
    style = (f"width:calc(100% - 7px);height:calc(100% - 7px);text-align:center;border:1px solid {PANEL_EDGE};"
             f"border-radius:6px;font-size:20px;font-family:{FONT};background-color:#1B2027;color:{TEXT};")
    frag = (f'<g id="{gid}" type="svg-ext-html_input" fill="#FFFFFF" stroke="#000000">'
            f'<rect id="svg_{gid}" x="{x}" y="{y}" width="{w}" height="{h}" stroke-width="0" fill="rgba(0,0,0,0)"/>'
            f'<foreignObject id="H-{gid}" x="{x}" y="{y}" width="{w}" height="{h}">'
            f'<INPUT id="I-{gid}" type="text" value="" style="{style}"/></foreignObject></g>')
    v.add(item, frag)
    return gid


def slider(v: View, name: str, tag: str, x, y, w, h, *, vmin=0, vmax=100, step=5, permission: int = 0,
           actions: list | None = None) -> str:
    """Deslizador horizontal (svg-ext-html_slider) para consignas."""
    gid = v.nid("SLI", name)
    options = {"orientation": "horizontal", "direction": "ltr", "fontFamily": FONT,
               "shape": {"baseColor": "#1B2027", "connectColor": MANUAL, "handleColor": TEXT, "barWidth": 12,
                         "handleWidth": 0, "handleHeight": 0},
               "marker": {"color": TEXT_DIM, "subWidth": 5, "subHeight": 1, "fontSize": 12, "divHeight": 2,
                          "divWidth": 10},
               "range": {"min": vmin, "max": vmax}, "step": step,
               "pips": {"mode": "values", "values": [vmin, (vmin + vmax) / 2, vmax], "density": 5},
               "tooltip": {"type": "show", "decimals": 0, "background": HEADER, "color": TEXT, "fontSize": 12}}
    item = {"id": gid, "type": "svg-ext-html_slider", "name": name, "label": "HtmlSlider", "hide": False,
            "lock": False, "property": {"variableId": tag, "bitmask": 0, "options": options, "events": [],
                                        "actions": actions or [], "permission": permission,
                                        "permissionRoles": {"show": [], "enabled": []}, "ranges": []}}
    frag = (f'<g id="{gid}" type="svg-ext-html_slider" fill="#FFFFFF" stroke="#000000">'
            f'<rect id="svg_{gid}" x="{x}" y="{y}" width="{w}" height="{h}" stroke-width="0" fill="rgba(0,0,0,0)"/>'
            f'<foreignObject id="H-{gid}" x="{x}" y="{y}" width="{w}" height="{h}">'
            f'<DIV id="D-{gid}" style="width:100%;height:100%;"></DIV></foreignObject></g>')
    v.add(item, frag)
    return gid


def chart(v: View, name: str, chart_id: str, x, y, w, h, *, history: bool = True, realtime_min: int = 60) -> str:
    """Grafica de tendencias (svg-ext-html_chart) ligada a un objeto de project.charts."""
    gid = v.nid("HXC", name)
    options = {"fontFamily": FONT, "legendFontSize": 13, "colorBackground": "rgba(0,0,0,0)",
               "legendBackground": "rgba(0,0,0,0)", "titleHeight": 22, "axisLabelFontSize": 12, "labelsDivWidth": 0,
               "axisLineColor": "rgba(154,164,175,0.35)", "axisLabelColor": TEXT_DIM, "legendMode": "always",
               "series": [], "width": w, "height": h, "decimalsPrecision": 1, "realtime": realtime_min,
               "mouseWheelScroll": False, "mouseWheelZoom": True, "staticChart": False,
               "dateFormat": "DD_MM_YYYY", "timeFormat": "hh_mm_ss", "lastRange": "last8h",
               "gridLineColor": "rgba(154,164,175,0.15)", "titleColor": TEXT}
    item = {"id": gid, "type": "svg-ext-html_chart", "name": name, "label": "HtmlChart", "hide": False,
            "lock": False, "property": {"id": chart_id, "type": "history" if history else "realtime1",
                                        "options": options, "events": []}}
    frag = (f'<g id="{gid}" type="svg-ext-html_chart" fill="#FFFFFF" stroke="#000000">'
            f'<rect id="svg_{gid}" x="{x}" y="{y}" width="{w}" height="{h}" stroke-width="0" fill="rgba(0,0,0,0)"/>'
            f'<foreignObject id="H-{gid}" x="{x}" y="{y}" width="{w}" height="{h}">'
            f'<DIV id="D-{gid}" style="width:100%;height:100%;"></DIV></foreignObject></g>')
    v.add(item, frag)
    return gid


def alarm_table(v: View, name: str, x, y, w, h, *, history: bool = False, filters: bool = False,
                compact: bool = False) -> str:
    """Tabla de alarmas FUXA (svg-ext-own_ctrl-table, tipo alarms o alarmsHistory)."""
    gid = v.nid("OXC", name)
    cols = ([("ontime", "Activada", 150), ("text", "Alarma", 0), ("type", "Prioridad", 110),
             ("group", "Grupo", 110), ("status", "Estado", 120), ("offtime", "Desactivada", 150),
             ("acktime", "Reconocida", 150), ("userack", "Usuario", 110)] if history else
            [("ontime", "Activada", 150), ("text", "Alarma", 0), ("type", "Prioridad", 110), ("group", "Grupo", 110),
             ("status", "Estado", 120), ("ack", "ACK", 70)])
    if compact:     # tablas estrechas: hora, texto, estado y ACK
        cols = [("ontime", "Activada", 96), ("text", "Alarma", 0), ("status", "Estado", 80), ("ack", "ACK", 46)]
    columns = [{"id": cid, "label": label, "type": "label", "align": "left", "width": width or (250 if compact else 380)}
               for cid, label, width in cols]
    options = {"alarmsColumns": columns, "realtime": not history, "daterange": {"show": history}, "paginator": {"show": history},
               "filter": {"show": filters}, "gridColor": PANEL_EDGE,
               "header": {"show": True, "height": 34, "fontSize": 13, "background": HEADER, "color": TEXT_DIM},
               "row": {"height": 40, "fontSize": 13, "background": PANEL, "color": TEXT},
               "selection": {"background": MANUAL, "color": "#FFFFFF", "fontBold": True}}
    item = {"id": gid, "type": "svg-ext-own_ctrl-table", "name": name, "label": "HtmlTable", "hide": False,
            "lock": False, "property": {"id": None, "type": "alarmsHistory" if history else "alarms",
                                        "options": options, "events": []}}
    frag = (f'<g id="{gid}" type="svg-ext-own_ctrl-table" fill="#FFFFFF" stroke="#000000">'
            f'<rect id="svg_{gid}" x="{x}" y="{y}" width="{w}" height="{h}" stroke-width="0" fill="rgba(0,0,0,0)"/>'
            f'<foreignObject id="H-{gid}" x="{x}" y="{y}" width="{w}" height="{h}">'
            f'<DIV id="D-{gid}" style="width:100%;height:100%;"></DIV></foreignObject></g>')
    v.add(item, frag)
    return gid


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)
