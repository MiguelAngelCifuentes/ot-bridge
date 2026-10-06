"""Completa .env con secretos aleatorios: anade los que falten y sustituye los marcadores CAMBIAR de la
plantilla. Nunca imprime valores.

Uso:  python scripts/ensure_secrets.py            (idempotente: no toca los secretos ya definidos)
La lista de secretos requeridos esta en REQUIRED; .env.example documenta cada uno con CAMBIAR.
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
PLACEHOLDERS = {"", "CAMBIAR"}

# (variable, valor por defecto si no es secreto; None = secreto aleatorio)
REQUIRED = [
    # Credenciales base: broker MQTT por servicio, PostgreSQL, Grafana y usuarios del SCADA FUXA
    ("MQTT_PASSWORD_GATEWAY", None), ("MQTT_PASSWORD_HISTORIAN", None), ("MQTT_PASSWORD_ALARM", None),
    ("MQTT_PASSWORD_API", None), ("MQTT_PASSWORD_FUXA", None),
    ("POSTGRES_PASSWORD", None), ("GRAFANA_PASSWORD", None),
    ("FUXA_ADMIN_PASSWORD", None), ("FUXA_OPERADOR_PASSWORD", None),
    ("FUXA_SUPERVISOR_PASSWORD", None), ("FUXA_VISITANTE_PASSWORD", None),
    # InfluxDB con autenticacion: admin, escritura (historian) y lectura (Grafana, API, backup)
    ("INFLUX_ADMIN_USER", "admin"), ("INFLUX_ADMIN_PASSWORD", None),
    ("INFLUX_WRITE_USER", "historian_w"), ("INFLUX_WRITE_PASSWORD", None),
    ("INFLUX_READ_USER", "reader"), ("INFLUX_READ_PASSWORD", None),
    # Usuario de solo lectura de PostgreSQL para Grafana
    ("GRAFANA_DB_USER", "grafana_ro"), ("GRAFANA_DB_PASSWORD", None),
    # API keys de la plant-api (X-API-Key)
    ("API_KEY_GRAFANA", None), ("API_KEY_ALARM_ENGINE", None), ("API_KEY_OPERATOR", None),
    # MQTT: usuarios separados para OPC UA (lectura) y gemelo (publica alarmas y estado)
    ("MQTT_USER_OPCUA", "opcua"), ("MQTT_PASSWORD_OPCUA", None),
    ("MQTT_USER_TWIN", "twin"), ("MQTT_PASSWORD_TWIN", None),
    # OPC UA con usuario (sin acceso anonimo)
    ("OPC_USER", "otbridge"), ("OPC_PASSWORD", None),
    # Cuenta de administrador del runtime de OpenPLC (la crea ot/plc/deploy_plc.py en el primer despliegue)
    ("OPENPLC_USER", "otb-admin"), ("OPENPLC_PASSWORD", None),
    # Interfaz en la que se publica MQTT para el SCADA (dos hosts: IP LAN del host IT)
    ("MQTT_LAN_BIND", "127.0.0.1"),
]


def main() -> int:
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    secret_keys = {k for k, v in REQUIRED if v is None}
    replaced = []
    for i, line in enumerate(lines):
        key, sep, value = line.partition("=")
        if sep and key in secret_keys and value.strip() in PLACEHOLDERS:
            lines[i] = f"{key}={secrets.token_urlsafe(24)}"
            replaced.append(key)
    if replaced:
        ENV.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print("generados en .env (sustituyen la plantilla):", ", ".join(replaced))
    present = {l.split("=", 1)[0] for l in lines if "=" in l and not l.lstrip().startswith("#")}
    missing = [(k, v) for k, v in REQUIRED if k not in present]
    if not missing:
        print("secretos: .env completo")
        return 0
    with ENV.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n# --- Anadidos por scripts/ensure_secrets.py (auditoria) ---\n")
        for key, default in missing:
            f.write(f"{key}={default if default is not None else secrets.token_urlsafe(24)}\n")
    print("anadidos a .env:", ", ".join(k for k, _ in missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
