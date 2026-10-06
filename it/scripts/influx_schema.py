"""Aplica influxdb/init/schema.influxql sobre una instalacion existente (idempotente).

Las sentencias ya aplicadas (retencion o continuous query existente) se dan por buenas. Con --backfill
rellena rp_1y con los agregados de 1 minuto de los datos crudos disponibles (30 dias).
Uso:  python scripts/influx_schema.py [--backfill]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "influxdb" / "init" / "schema.influxql"
BACKFILL = [
    'SELECT mean("value") AS "mean", min("value") AS "min", max("value") AS "max" INTO "plant"."rp_1y"."sensor_readings_1m" '
    'FROM "plant"."rp_30d"."sensor_readings" WHERE time > now() - 30d GROUP BY time(1m), *',
    'SELECT mean("online") AS "online" INTO "plant"."rp_1y"."plc_status_1m" FROM "plant"."rp_30d"."plc_status" '
    'WHERE time > now() - 30d GROUP BY time(1m), *',
    'SELECT mean("level_real") AS "level_real", mean("level_model") AS "level_model", mean("deviation") AS "deviation", '
    'mean("leak_lpm") AS "leak_lpm" INTO "plant"."rp_1y"."twin_state_1m" FROM "plant"."rp_30d"."twin_state" '
    'WHERE time > now() - 30d GROUP BY time(1m), *',
]


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def run(statement: str, e: dict[str, str]) -> tuple[bool, str]:
    r = subprocess.run(["docker", "exec", "otb-influxdb", "influx", "-username", e["INFLUX_ADMIN_USER"],
                        "-password", e["INFLUX_ADMIN_PASSWORD"], "-database", "plant", "-execute", statement],
                       capture_output=True, text=True)
    text = (r.stdout + r.stderr).strip()
    ok = r.returncode == 0 and "err" not in text.lower()
    return ok or "already exists" in text.lower(), text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true")
    args = parser.parse_args()
    e = env()
    statements = [l.strip() for l in SCHEMA.read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("--")]
    for statement in statements + (BACKFILL if args.backfill else []):
        ok, text = run(statement, e)
        label = statement.split(" ON ")[0][:60] if statement.startswith("CREATE") else statement[:60]
        print(f"  [{'OK ' if ok else 'ERR'}] {label}{'' if ok else ' -> ' + text[:150]}")
        if not ok:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
