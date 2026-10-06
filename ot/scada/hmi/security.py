"""Activa la seguridad de FUXA: usuarios por rol, contrasena de admin propia, autenticacion JWT e idioma.

Uso:  python ot/scada/hmi/security.py --target sandbox|plant
- Genera (si faltan) contrasenas aleatorias en .env: FUXA_ADMIN_PASSWORD, FUXA_OPERADOR_PASSWORD,
  FUXA_SUPERVISOR_PASSWORD, FUXA_VISITANTE_PASSWORD. Nunca se imprimen.
- Grupos FUXA: visitante = Viewer (1), operador = Operator (2), supervisor = Supervisor (8),
  admin = todos (-1). Los permisos de cada mando estan en el proyecto (lib.perm).
- Idempotente: si la seguridad ya esta activa se autentica como admin con la contrasena de .env.
"""
from __future__ import annotations

import argparse
import secrets
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import ROOT, URLS, call  # noqa: E402

USERS = [("operador", "Operador de planta", 2, "FUXA_OPERADOR_PASSWORD"),
         ("supervisor", "Supervisor de planta", 8, "FUXA_SUPERVISOR_PASSWORD"),
         ("visitante", "Visitante (solo lectura)", 1, "FUXA_VISITANTE_PASSWORD")]


def ensure_secrets(names: list[str]) -> dict[str, str]:
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    values = {l.split("=", 1)[0]: l.split("=", 1)[1].strip() for l in lines if "=" in l and not l.startswith("#")}
    new = [n for n in names if not values.get(n)]
    if new:
        with env_path.open("a", encoding="utf-8") as f:
            f.write("\n# FUXA (SCADA OT): usuarios del HMI - generados por ot/scada/hmi/security.py\n")
            for n in new:
                values[n] = secrets.token_urlsafe(15)
                f.write(f"{n}={values[n]}\n")
        print(f"contrasenas generadas en .env: {', '.join(new)}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=URLS, required=True)
    args = parser.parse_args()
    base = URLS[args.target]
    pw = ensure_secrets(["FUXA_ADMIN_PASSWORD"] + [u[3] for u in USERS])

    settings = call(f"{base}/api/settings")
    token = None
    if settings.get("secureEnabled"):
        token = call(f"{base}/api/signin", "POST", {"username": "admin", "password": pw["FUXA_ADMIN_PASSWORD"]})[
            "data"]["token"]

    # 1. usuarios por rol y contrasena propia para admin (sustituye la de fabrica 123456)
    call(f"{base}/api/users", "POST", {"params": {"username": "admin", "fullname": "Administrador",
                                                  "password": pw["FUXA_ADMIN_PASSWORD"], "groups": -1,
                                                  "info": "{}"}}, token)
    for user, full, groups, key in USERS:
        call(f"{base}/api/users", "POST", {"params": {"username": user, "fullname": full, "password": pw[key],
                                                      "groups": groups, "info": "{}"}}, token)
    print("usuarios: admin, " + ", ".join(u[0] for u in USERS))

    # 2. autenticacion JWT e interfaz en espanol (se aplica en caliente)
    if not settings.get("secureEnabled") or settings.get("language") != "es":
        settings.update({"secureEnabled": True, "tokenExpiresIn": "8h", "language": "es"})
        call(f"{base}/api/settings", "POST", settings, token)
        print("seguridad activada (token 8 h) e idioma es")

    # 3. comprobaciones
    for user, _, _, key in [("admin", "", 0, "FUXA_ADMIN_PASSWORD")] + USERS:
        res = call(f"{base}/api/signin", "POST", {"username": user, "password": pw[key]})
        print(f"  login {user}: {'OK' if res and res.get('data', {}).get('token') else 'FALLO'}")
    try:
        call(f"{base}/api/signin", "POST", {"username": "admin", "password": "123456"})
        print("  AVISO: la contrasena de fabrica de admin sigue funcionando")
        return 1
    except urllib.error.HTTPError:
        print("  contrasena de fabrica de admin rechazada: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
