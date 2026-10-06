"""Crea o actualiza los usuarios de InfluxDB 1.8 a partir de .env (idempotente).

- INFLUX_ADMIN_USER: administrador (todas las privilegios).
- INFLUX_WRITE_USER: escritura en la BD plant (historian).
- INFLUX_READ_USER: lectura en la BD plant (Grafana, plant-api, backup).

Funciona con la autenticacion activada o no: si ya existe el admin se autentica con el. Nunca imprime
contrasenas. En instalaciones nuevas los crea influxdb/init/init.sh con las variables INFLUXDB_*.
Uso:  python scripts/influx_users.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def failed(r: subprocess.CompletedProcess) -> bool:
    text = (r.stdout + r.stderr).lower()
    return r.returncode != 0 or "err:" in text or "error" in text


def influx(statement: str, auth: tuple[str, str] | None) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", "otb-influxdb", "influx"]
    if auth:
        cmd += ["-username", auth[0], "-password", auth[1]]
    return subprocess.run(cmd + ["-execute", statement], capture_output=True, text=True)


def main() -> int:
    e = env()
    db = e.get("INFLUX_DB", "plant")
    admin = (e["INFLUX_ADMIN_USER"], e["INFLUX_ADMIN_PASSWORD"])
    # con la autenticacion desactivada (migracion inicial) se opera sin credenciales; si no, como admin
    auth = None if not failed(influx("SHOW USERS", None)) else admin
    # filas de datos de SHOW USERS (las 2 primeras lineas son la cabecera "user admin" y "---- -----")
    users = {line.split()[0] for line in influx("SHOW USERS", auth).stdout.splitlines()[2:] if line.strip()}

    def upsert(user: str, password: str, create_suffix: str) -> None:
        if user in users:
            stmt = f"SET PASSWORD FOR \"{user}\" = '{password}'"
        else:
            stmt = f"CREATE USER \"{user}\" WITH PASSWORD '{password}'{create_suffix}"
        r = influx(stmt, auth)
        if failed(r):
            raise SystemExit(f"Fallo al crear/actualizar {user}: {(r.stdout + r.stderr).strip()[:200]}")

    upsert(admin[0], admin[1], " WITH ALL PRIVILEGES")
    upsert(e["INFLUX_WRITE_USER"], e["INFLUX_WRITE_PASSWORD"], "")
    upsert(e["INFLUX_READ_USER"], e["INFLUX_READ_PASSWORD"], "")
    for stmt in (f"GRANT WRITE ON \"{db}\" TO \"{e['INFLUX_WRITE_USER']}\"",
                 f"GRANT READ ON \"{db}\" TO \"{e['INFLUX_READ_USER']}\""):
        r = influx(stmt, auth)
        if failed(r):
            raise SystemExit(f"Fallo en GRANT: {(r.stdout + r.stderr).strip()[:200]}")
    print(f"usuarios InfluxDB listos: {admin[0]} (admin), {e['INFLUX_WRITE_USER']} (WRITE {db}), "
          f"{e['INFLUX_READ_USER']} (READ {db})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
