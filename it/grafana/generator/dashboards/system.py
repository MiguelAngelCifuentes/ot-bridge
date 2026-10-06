"""06 · Sistema y comunicaciones: conectividad OT, ingesta de datos, servicios IT y OPC UA."""
from lib import *  # noqa: F403

UID = "otb-system"

STATUS = f'"plc_status" WHERE ({PLC_FILTER}) AND $timeFilter'

OPCUA_NODES = [
    ("NivelDeposito", "nivel_x10", " / 10.0", U_LITRE, 1),
    ("NivelSensorMA", "nivel_ma", " / 100.0", U_MA, 2),
    ("CaudalEntrada", "caudal_ent", FLOW, U_FLOW, 1),
    ("CaudalSalida", "caudal_sal", FLOW, U_FLOW, 1),
    ("VelocidadBomba", "velocidad", "", U_PERCENT, 0),
    ("Estado", "estado", "", U_NONE, 0),
]


def build() -> dict:
    reset_ids()
    refs = "ABCDEFG"
    p = [
        stat("PLC", grid(0, 0, 4, 4), [influx("A", f'SELECT last("online") FROM {STATUS}')],
             mappings=[value_map({1: ("EN LÍNEA", OK), 0: ("SIN CONEXIÓN", CRIT)})], value_size=22,
             noValue="SIN DATOS", desc="Último heartbeat publicado por el gateway (LWT si cae)."),
        stat("Disponibilidad", grid(4, 0, 4, 4), [influx("A", f'SELECT mean("online") * 100.0 FROM {STATUS}')],
             unit=U_PERCENT, decimals=2, color_mode="value",
             thresholds=steps((None, CRIT), (95, WARN), (99, PROCESS)),
             desc="Porcentaje de heartbeats online en el rango."),
        stat("Desconexiones", grid(8, 0, 4, 4),
             [influx("A", 'SELECT sum("x") FROM (SELECT (abs("d") - "d") / 2 AS "x" FROM '
                          f'(SELECT difference("online") AS "d" FROM {STATUS}))')],
             decimals=0, color_mode="value", noValue="0", thresholds=steps((None, PROCESS), (1, WARN), (5, CRIT)),
             desc="Transiciones online → offline del PLC en el rango."),
        stat("Último dato", grid(12, 0, 4, 4), [latest("A", "nivel_x10", "nivel")], unit=U_FROM_NOW,
             fields="/^Time$/", color_mode="none", value_size=20,
             desc="Antigüedad de la última lectura almacenada: > unos segundos indica ingesta detenida."),
        stat("Ingesta", grid(16, 0, 4, 4),
             [influx("A", 'SELECT count("value") / 5.0 FROM "sensor_readings" WHERE time > now() - 5m')],
             unit="puntos/min", decimals=0, color_mode="value", graph="none",
             thresholds=steps((None, CRIT), (300, WARN), (600, PROCESS)),
             desc="Puntos de telemetría escritos por minuto (últimos 5 min). 11 variables a 1 Hz ≈ 660/min."),
        stat("API REST", grid(20, 0, 4, 4),
             [api("A", "/actuator/health", "", [("status", "Estado", "string")])],
             fields="/^Estado$/", value_size=22,
             mappings=[value_map({"UP": ("OPERATIVA", OK), "DOWN": ("CAÍDA", CRIT)})], noValue="SIN RESPUESTA",
             desc="Health check de plant-api (Spring Boot actuator) consultado por Grafana."),

        state_timeline("Conectividad del PLC", grid(0, 4, 24, 4),
                       [influx("A", f'SELECT last("online") FROM {STATUS} GROUP BY time($__interval) fill(previous)',
                               "PLC")],
                       mappings=[value_map({1: ("En línea", OK), 0: ("Sin conexión", CRIT)})],
                       desc="Historial de conexión PLC → gateway."),
        timeseries("Ingesta por flujo de datos", grid(0, 8, 14, 8),
                   [influx("A", 'SELECT count("value") FROM "sensor_readings" WHERE $timeFilter GROUP BY time(1m) fill(0)',
                           "Telemetría"),
                    influx("B", 'SELECT count("level_real") FROM "twin_state" WHERE $timeFilter GROUP BY time(1m) fill(0)',
                           "Gemelo digital"),
                    influx("C", 'SELECT count("online") FROM "plc_status" WHERE $timeFilter GROUP BY time(1m) fill(0)',
                           "Heartbeat")],
                   unit="puntos/min", decimals=0, legend_calcs=["mean", "min"],
                   overrides=[override("Telemetría", color=fixed(PROCESS)),
                              override("Gemelo digital", color=fixed(MODEL)),
                              override("Heartbeat", color=fixed(NEUTRAL))],
                   desc="Puntos por minuto escritos en InfluxDB por cada flujo. Una caída a 0 localiza el eslabón roto."),
        stat("Base de datos relacional", grid(14, 8, 10, 8),
             [sql("""SELECT
  (SELECT count(*) FROM alarms) AS "Alarmas registradas",
  (SELECT count(*) FROM thresholds WHERE enabled) AS "Umbrales activos",
  (SELECT count(*) FROM sensors) AS "Sensores",
  pg_database_size(current_database()) AS "Tamaño BD\"""")],
             text_mode="value_and_name", color_mode="none", orientation="horizontal", decimals=0,
             overrides=[override("Tamaño BD", unit="bytes", decimals=1)],
             desc="Contenido de PostgreSQL (plant-api): alarmas, umbrales y sensores, y tamaño de la base."),

        row("Servidor OPC UA · opc.tcp://127.0.0.1:4840", 16),
        stat("Estado OPC UA", grid(0, 17, 4, 6), [influx("A", f'SELECT last("online") FROM {STATUS}')],
             mappings=[value_map({1: ("PUBLICANDO", OK), 0: ("DATOS INTERRUMPIDOS", CRIT)})], value_size=20,
             noValue="SIN DATOS",
             desc="Nodo PLCOnline del servidor OPC UA. Grafana no habla OPC UA: se muestra el mismo flujo MQTT "
                  "que alimenta los nodos (verificación directa con scripts/test_opcua.py)."),
        stat("Nodos publicados · PlantaSimulada/plc01", grid(4, 17, 20, 6),
             [latest(refs[i], var, name, scale) for i, (name, var, scale, _, _) in enumerate(OPCUA_NODES)]
             + [influx("G", f'SELECT last("online") FROM {STATUS}', "PLCOnline")],
             text_mode="value_and_name", color_mode="value", thresholds=steps((None, PROCESS)),
             overrides=[override(name, unit=unit, decimals=dec) for name, _, _, unit, dec in OPCUA_NODES]
             + [override("PLCOnline", mappings=[value_map({1: ("True", OK), 0: ("False", CRIT)})])],
             desc="Valores actuales de los 7 nodos del namespace otbridge."),
    ]
    return dashboard(UID, "06 · Sistema y comunicaciones", p, refresh="10s", time_from="now-6h",
                     description="Salud de la cadena de datos: PLC, ingesta, API, PostgreSQL y servidor OPC UA.")
