"""01 · Proceso: operacion en tiempo real, estado de maquina, mando y produccion."""
from lib import *  # noqa: F403

UID = "otb-process"

LEVEL_THR = steps((None, CRIT), (100, PROCESS), (900, WARN))   # umbrales de la API: < 100 L aviso, > 900 L alto
ON_OFF = [value_map({0: ("OFF", INACTIVE), 1: ("ON", OK)})]

# Bits del registro de estado hmi_estado con los nombres del programa PLC (ot/plc/pous/programs/main.st)
STATUS_BITS = [
    (1, "Contactor bomba", OK),
    (2, "Seta emergencia", EMERG),
    (4, "Fallo sensor", CRIT),
    (8, "Fallo arranque", CRIT),
    (16, "Nivel alto", WARN),
    (32, "Nivel bajo", WARN),
    (64, "Consumo en reserva", "#6C8EBF"),
    (128, "Modo manual", WARN),
    (256, "Orden marcha P-101", OK),
    (512, "Orden apertura V-101", "#1F4E79"),
]


def _bit_query(ref: str, weight: int, alias: str) -> dict:
    expr = 'last("value") % 2' if weight == 1 else f'FLOOR(last("value") / {weight}) % 2'
    return influx(ref, f'SELECT {expr} FROM "sensor_readings" WHERE ({where("estado")}) AND $timeFilter', alias)


def _bit_series(ref: str, weight: int, alias: str, variable: str = "estado") -> dict:
    expr = 'last("value") % 2' if weight == 1 else f'FLOOR(last("value") / {weight}) % 2'
    return influx(ref, f'SELECT {expr} FROM "sensor_readings" WHERE ({where(variable)}) AND $timeFilter '
                       "GROUP BY time($__interval) fill(previous)", alias)


def build() -> dict:
    reset_ids()
    refs = iter("ABCDEFGHIJKLMNOP")
    p = [
        row("Variables de proceso", 0),
        gauge("Nivel del depósito", grid(0, 1, 6, 8), [latest("A", "nivel_x10", "Nivel", " / 10.0")],
              unit=U_LITRE, min_=0, max_=1000, decimals=0, thresholds=LEVEL_THR,
              desc="Nivel actual. Bandas: < 100 L nivel bajo, > 900 L nivel alto (umbrales del motor de alarmas)."),
        gauge("Velocidad de bomba", grid(6, 1, 6, 8), [latest("A", "velocidad", "Velocidad")],
              unit=U_PERCENT, min_=0, max_=100, decimals=0,
              thresholds=steps((None, PROCESS), (95, WARN)),
              desc="Velocidad del variador. > 95 % genera aviso de velocidad alta."),
        gauge("Transmisor de nivel", grid(12, 1, 6, 8), [latest("A", "nivel_ma", "Señal", " / 100.0")],
              unit=U_MA, min_=0, max_=24, decimals=2,
              thresholds=steps((None, CRIT), (3.8, PROCESS), (20.5, CRIT)),
              desc="Lazo 4–20 mA del sensor de nivel. Fuera de 3,8–20,5 mA indica fallo del lazo (NAMUR NE43)."),
        stat("Caudal de entrada", grid(18, 1, 6, 4), [series("A", "caudal_ent", "Entrada", FLOW)],
             unit=U_FLOW, decimals=1, color_mode="value", graph="area", thresholds=steps((None, PROCESS)),
             desc="Caudal de entrada con su tendencia en el rango."),
        stat("Caudal de salida", grid(18, 5, 6, 4), [series("A", "caudal_sal", "Salida", FLOW)],
             unit=U_FLOW, decimals=1, color_mode="value", graph="area", thresholds=steps((None, "#4FC3C3")),
             desc="Caudal de salida (producción) con su tendencia en el rango."),

        row("Tendencias", 9),
        timeseries("Nivel del depósito", grid(0, 10, 12, 8), [series("A", "nivel_x10", "Nivel", " / 10.0")],
                   unit=U_LITRE, decimals=1, thresholds=steps((None, WARN), (100, TRANSPARENT), (900, WARN)),
                   threshold_style="dashed", legend_calcs=["min", "max", "mean", "lastNotNull"],
                   overrides=[override("Nivel", color=fixed(PROCESS))],
                   desc="Nivel con las líneas de alarma de nivel bajo (100 L) y alto (900 L)."),
        timeseries("Caudales y balance", grid(12, 10, 12, 8),
                   [series("A", "caudal_ent", "caudal_ent", FLOW), series("B", "caudal_sal", "caudal_sal", FLOW)],
                   unit=U_FLOW, decimals=1, legend_calcs=["mean", "lastNotNull"],
                   transformations=[t_join(), t_binary("Balance", "caudal_ent", "-", "caudal_sal"),
                                    t_organize(rename={"caudal_ent": "Entrada", "caudal_sal": "Salida"})],
                   overrides=[override("Entrada", color=fixed(PROCESS)),
                              override("Salida", color=fixed("#4FC3C3")),
                              override("Balance", color=fixed(MODEL), custom__drawStyle="bars",
                                       custom__fillOpacity=35, custom__lineWidth=0, custom__axisPlacement="right",
                                       custom__axisCenteredZero=True)],
                   desc="Entrada y salida (líneas) y balance neto entrada − salida (barras, eje derecho)."),
        timeseries("Velocidad y consigna", grid(0, 18, 12, 7),
                   [series("A", "velocidad", "Velocidad real"), series("B", "consigna_manual", "Consigna manual", agg="last")],
                   unit=U_PERCENT, min_=0, max_=100, decimals=0, legend_calcs=["mean", "lastNotNull"],
                   overrides=[override("Velocidad real", color=fixed(PROCESS)),
                              override("Consigna manual", color=fixed(WARN), custom__fillOpacity=0,
                                       custom__lineInterpolation="stepAfter",
                                       custom__lineStyle={"fill": "dash", "dash": [6, 4]})],
                   desc="Velocidad del variador frente a la consigna manual (solo aplica en modo manual)."),
        timeseries("Señal del transmisor", grid(12, 18, 12, 7), [series("A", "nivel_ma", "Señal", " / 100.0")],
                   unit=U_MA, min_=0, max_=24, decimals=2,
                   thresholds=steps((None, CRIT), (3.8, TRANSPARENT), (20.5, CRIT)), threshold_style="line+area",
                   overrides=[override("Señal", color=fixed(PROCESS))], legend_calcs=["min", "max", "lastNotNull"],
                   desc="Lazo 4–20 mA con las zonas de fallo NAMUR (< 3,8 mA y > 20,5 mA) sombreadas."),

        row("Estado de máquina y mando", 25),
        stat("Registro de estado (bit a bit)", grid(0, 26, 24, 4),
             [_bit_query(next(refs), w, name) for w, name, _ in STATUS_BITS],
             text_mode="name", color_mode="background", orientation="vertical", value_size=14,
             overrides=[override(name, mappings=[value_map({0: (name, INACTIVE), 1: (name, color)})])
                        for _, name, color in STATUS_BITS],
             desc="Decodificación del registro de estado. Encendido = color; apagado = gris. "
                  "Los bits 6–9 no están documentados en el contrato y se muestran para no ocultar información."),
        stat("Mando observado", grid(0, 30, 24, 4),
             [latest("A", "modo_manual", "Modo"), latest("B", "mando_marcha", "Marcha"),
              latest("C", "mando_valvula", "Válvula"), latest("D", "consigna_manual", "Consigna")],
             text_mode="value_and_name", color_mode="background", orientation="vertical",
             overrides=[override("Modo", mappings=[value_map({0: ("AUTOMÁTICO", INACTIVE), 1: ("MANUAL", WARN)})]),
                        override("Marcha", mappings=[value_map({0: ("PARO", INACTIVE), 1: ("MARCHA", OK)})]),
                        override("Válvula", mappings=[value_map({0: ("CERRADA", INACTIVE), 1: ("ABIERTA", "#1F4E79")})]),
                        override("Consigna", unit=U_PERCENT, color=fixed("#2A3A4F"))],
             desc="Registros de mando escritos desde FUXA (OT). IT solo los observa: nunca escribe en el PLC."),
        state_timeline("Cronología de estado", grid(0, 34, 24, 7),
                       [_bit_series("A", 1, "Bomba (contactor)"),
                        _bit_series("B", 4, "Fallo sensor"),
                        _bit_series("C", 8, "Fallo arranque"),
                        _bit_series("D", 2, "Seta emergencia"),
                        _bit_series("E", 1, "Modo manual", "modo_manual"),
                        _bit_series("F", 512, "Válvula abierta")],
                       mappings=[value_map({0: ("OFF", INACTIVE), 1: ("ON", OK)})],
                       overrides=[override(n, mappings=[value_map({0: ("OFF", INACTIVE), 1: ("ON", c)})])
                                  for n, c in (("Fallo sensor", CRIT), ("Fallo arranque", CRIT),
                                               ("Seta emergencia", EMERG), ("Modo manual", WARN),
                                               ("Válvula abierta", "#1F4E79"))],
                       desc="Qué estuvo activo y cuándo: bomba, fallos, seta, modo y válvula."),

        row("Producción", 41),
        stat("Producción en el rango", grid(0, 42, 6, 4),
             [influx("A", f'SELECT integral("value"){FLOW} / 60.0 FROM "sensor_readings" WHERE ({where("caudal_sal")}) '
                          "AND $timeFilter")],
             unit=U_LITRE, decimals=0, color_mode="value", thresholds=steps((None, PROCESS)),
             desc="Volumen bombeado: integral del caudal de salida."),
        stat("Variación de nivel", grid(6, 42, 6, 4),
             [influx("A", f'SELECT last("value") / 10.0 - first("value") / 10.0 FROM "sensor_readings" '
                          f'WHERE ({where("nivel_x10")}) AND $timeFilter')],
             unit=U_LITRE, decimals=1, color_mode="value", thresholds=steps((None, PROCESS)),
             desc="Nivel final − nivel inicial del rango."),
        stat("Rendimiento", grid(12, 42, 6, 4),
             [influx("A", f'SELECT mean("value"){FLOW} / {NOMINAL_FLOW_LPM} * 100.0 FROM "sensor_readings" '
                          f'WHERE ({where("caudal_sal")}) AND $timeFilter')],
             unit=U_PERCENT, decimals=1, color_mode="value",
             thresholds=steps((None, CRIT), (40, WARN), (60, PROCESS)),
             desc=f"Caudal medio de salida frente al fondo de escala ({NOMINAL_FLOW_LPM:g} l/min)."),
        stat("Tiempo en marcha", grid(18, 42, 6, 4),
             [influx("A", 'SELECT mean(b) * 100.0 FROM (SELECT "value" % 2 AS b FROM "sensor_readings" '
                          f'WHERE ({where("estado")}) AND $timeFilter)')],
             unit=U_PERCENT, decimals=1, color_mode="value", thresholds=steps((None, PROCESS)),
             desc="Porcentaje del rango con el contactor de bomba cerrado."),
        timeseries("Producción acumulada", grid(0, 46, 12, 8),
                   [influx("A", f'SELECT CUMULATIVE_SUM(mean("value")){FLOW} FROM "sensor_readings" '
                                f'WHERE ({where("caudal_sal")}) AND $timeFilter GROUP BY time(1m) fill(0)', "Producción")],
                   unit=U_LITRE, decimals=0, overrides=[override("Producción", color=fixed(PROCESS))],
                   custom={"fillOpacity": 20},
                   desc="Volumen acumulado a lo largo del rango (suma de caudales medios por minuto)."),
        timeseries("Nivel: contexto de 24 h", grid(12, 46, 12, 8),
                   [series("A", "nivel_x10", "Nivel", " / 10.0", interval="5m")],
                   unit=U_LITRE, decimals=0, timeFrom="24h", color=fixed(PROCESS),
                   thresholds=steps((None, WARN), (100, TRANSPARENT), (900, WARN)), threshold_style="dashed",
                   legend_calcs=["min", "max", "mean"],
                   desc="Ciclos de llenado y vaciado de las últimas 24 h (media cada 5 min), independiente del rango."),
    ]
    return dashboard(UID, "01 · Proceso", p, refresh="5s", time_from="now-30m",
                     description="Operación en tiempo real: variables, tendencias, estado, mando y producción.")
