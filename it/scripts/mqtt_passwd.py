"""Regenera mosquitto/config/passwd completo a partir de .env y recarga el broker.

Cada pareja MQTT_USER_<X> / MQTT_PASSWORD_<X> de .env es un usuario. El fichero se genera desde cero con
mosquitto_passwd en un contenedor desechable (el contenedor del broker, con cap_drop ALL, no puede
escribirlo), se valida (todos los usuarios, formato usuario:hash, finales LF), se sustituye de forma
atomica y se recarga mosquitto con SIGHUP. Nunca imprime contrasenas.

Uso:  python scripts/mqtt_passwd.py            (rotar una contrasena = cambiarla en .env y ejecutar esto)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASSWD = ROOT / "mosquitto" / "config" / "passwd"
IMAGE = "eclipse-mosquitto:2.1.2-alpine"
# En Linux/macOS el contenedor escribe con el UID del usuario: si no, el fichero quedaria de root (0700)
HOST_USER = ["--user", f"{os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []


def env_users() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    users = {}
    for key, user in values.items():
        m = re.fullmatch(r"MQTT_USER_(\w+)", key)
        if m and user:
            password = values.get(f"MQTT_PASSWORD_{m.group(1)}")
            if not password:
                raise SystemExit(f"Falta MQTT_PASSWORD_{m.group(1)} en .env")
            users[user] = password
    return users


def main() -> int:
    users = env_users()
    with tempfile.TemporaryDirectory(dir=ROOT / "mosquitto") as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "passwd").touch()
        for user, password in users.items():
            r = subprocess.run(["docker", "run", "--rm", *HOST_USER, "-v", f"{tmpdir}:/work", IMAGE,
                                "mosquitto_passwd", "-b", "/work/passwd", user, password],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit(f"mosquitto_passwd fallo para {user}: {r.stderr.strip()}")
        content = (tmpdir / "passwd").read_text(encoding="utf-8").replace("\r\n", "\n")
        lines = [l for l in content.split("\n") if l]
        names = [l.split(":", 1)[0] for l in lines]
        if sorted(names) != sorted(users) or not all(re.fullmatch(r"[^:\s]+:\$\d+\$\S+", l) for l in lines):
            raise SystemExit("Fichero generado no valido; passwd actual sin cambios")
        backup = PASSWD.with_suffix(".bak")
        if PASSWD.exists():
            shutil.copyfile(PASSWD, backup)
        tmp_final = PASSWD.with_suffix(".new")
        tmp_final.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        tmp_final.replace(PASSWD)
    r = subprocess.run(["docker", "kill", "-s", "SIGHUP", "otb-mosquitto"], capture_output=True, text=True)
    reload = "OK" if r.returncode == 0 else "broker no arrancado (lo leera al arrancar)"
    print(f"passwd regenerado: {len(users)} usuarios ({', '.join(sorted(users))}); recarga del broker: {reload}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
