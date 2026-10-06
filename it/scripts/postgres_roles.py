"""Crea o actualiza el rol de solo lectura de Grafana en PostgreSQL (idempotente).

GRAFANA_DB_USER / GRAFANA_DB_PASSWORD de .env: LOGIN con SELECT en las tablas de la API y nada mas
(un panel de Grafana no puede modificar ni borrar datos). Rotar la contrasena = cambiarla en .env y
volver a ejecutar. Nunca imprime la contrasena.
Uso:  python scripts/postgres_roles.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLES = ("alarms", "sensors", "machines", "thresholds")


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    e = env()
    role, password = e["GRAFANA_DB_USER"], e["GRAFANA_DB_PASSWORD"]
    db, owner = e["POSTGRES_DB"], e["POSTGRES_USER"]
    sql = f"""
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
    ALTER ROLE "{role}" WITH LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
  ELSE
    CREATE ROLE "{role}" WITH LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}";
GRANT CONNECT ON DATABASE "{db}" TO "{role}";
GRANT USAGE ON SCHEMA public TO "{role}";
GRANT SELECT ON {", ".join(TABLES)} TO "{role}";
"""
    r = subprocess.run(["docker", "exec", "-i", "otb-postgres", "psql", "-v", "ON_ERROR_STOP=1", "-q",
                        "-U", owner, "-d", db], input=sql, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"Fallo al configurar el rol: {r.stderr.strip()[:300]}")
    print(f"rol {role}: LOGIN, SELECT en {', '.join(TABLES)} (sin escritura)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
