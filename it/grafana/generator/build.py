"""Genera los dashboards de la suite OT-Bridge en grafana/provisioning/dashboards/.

Uso:  python grafana/generator/build.py
Grafana recarga los JSON provisionados en ~10 s, sin reiniciar.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "provisioning" / "dashboards"
MODULES = ["home", "process", "alarms", "twin", "maintenance", "explorer", "system"]

sys.path.insert(0, str(HERE))


def main(selected: list[str]) -> int:
    for name in selected or MODULES:
        module = importlib.import_module(f"dashboards.{name}")
        dash = module.build()
        path = OUT_DIR / f"{dash['uid']}.json"
        path.write_text(json.dumps(dash, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name}: {sum(p['type'] != 'row' for p in dash['panels'])} paneles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
