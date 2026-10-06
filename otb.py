#!/usr/bin/env python3
"""OT-Bridge: instalacion y operacion de la plataforma completa en un solo host.

    python otb.py install        instala o actualiza y arranca todo (idempotente, seguro de repetir)
    python otb.py status         estado de los 13 servicios y direcciones de acceso
    python otb.py credentials    usuarios de cada herramienta (--show para ver las contrasenas)
    python otb.py deploy-plc     vuelve a cargar el programa en el PLC (tras reiniciar su contenedor)
    python otb.py start | stop   arranca o para la plataforma (los datos se conservan)
    python otb.py uninstall      elimina los contenedores (--volumes borra tambien los datos)

Requisitos: Python 3.10+ y Docker con Compose v2. Sin dependencias de Python adicionales.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IT = ROOT / "it"
ENV = IT / ".env"
ENV_EXAMPLE = IT / ".env.example"
LOG_DIR = ROOT / ".otb"
OT_COMPOSE = ["docker", "compose", "-f", str(ROOT / "ot" / "scada" / "docker-compose.yml")]
IT_COMPOSE = ["docker", "compose", "-f", str(IT / "docker-compose.yml"), "-f", str(IT / "docker-compose.single-host.yml")]
OT_SERVICES = ["otb-field-simulator", "otb-openplc", "otb-fuxa"]
IT_SERVICES = ["otb-mosquitto", "otb-influxdb", "otb-postgres", "otb-historian", "otb-grafana", "otb-plant-api",
               "otb-alarm-engine", "otb-gateway", "otb-opcua-server", "otb-digital-twin"]
PORTS = {1881: "FUXA SCADA", 1883: "MQTT", 3000: "Grafana", 4840: "OPC UA", 8080: "API REST",
         8086: "InfluxDB", 8443: "OpenPLC runtime"}
ACCESS = [("SCADA FUXA", "http://localhost:1881"), ("Grafana", "http://localhost:3000"),
          ("API REST", "http://localhost:8080/api  (cabecera X-API-Key)"),
          ("OpenPLC runtime", "https://localhost:8443  (API; cliente: OpenPLC Editor)"),
          ("OPC UA", "opc.tcp://localhost:4840  (Basic256Sha256 + usuario)")]
HEALTH_TIMEOUT_S = 1200

# ------------------------------------------------------------------------------------------------ salida

if os.name == "nt":
    os.system("")                                   # activa las secuencias ANSI en la consola de Windows
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


class Log:
    """Progreso legible en consola y salida completa de cada comando en .otb/<accion>-<fecha>.log."""

    def __init__(self, action: str):
        LOG_DIR.mkdir(exist_ok=True)
        self.path = LOG_DIR / f"{action}-{dt.datetime.now():%Y%m%d-%H%M%S}.log"
        self._file = self.path.open("w", encoding="utf-8")
        self.step_no = 0
        self.total = 0

    def write(self, text: str) -> None:
        self._file.write(text if text.endswith("\n") else text + "\n")
        self._file.flush()

    def step(self, title: str) -> None:
        self.step_no += 1
        counter = f"[{self.step_no}/{self.total}]" if self.total else f"[{self.step_no}]"
        print(f"\n{paint(counter, '1;36')} {paint(title, '1')}")
        self.write(f"\n===== {counter} {title}")

    def ok(self, text: str) -> None:
        print(f"      {paint('OK', '1;32')}   {text}")
        self.write(f"OK {text}")

    def info(self, text: str) -> None:
        print(f"      {paint('·', '36')}    {text}")
        self.write(f"INFO {text}")

    def warn(self, text: str) -> None:
        print(f"      {paint('AVISO', '1;33')} {text}")
        self.write(f"WARN {text}")


class Abort(Exception):
    """Error esperado con un mensaje para el usuario (sin traza)."""


def run(cmd: list[str], log: Log, *, cwd: Path = ROOT, env: dict | None = None, check: bool = True,
        timeout: int | None = None) -> subprocess.CompletedProcess:
    log.write("$ " + " ".join(cmd))
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except FileNotFoundError as exc:
        raise Abort(f"No se encuentra el comando {cmd[0]!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise Abort(f"Tiempo agotado ejecutando: {' '.join(cmd[:4])}...") from exc
    log.write(proc.stdout or "")
    log.write(proc.stderr or "")
    if check and proc.returncode != 0:
        detail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-12:])
        raise Abort(f"Fallo ({proc.returncode}): {' '.join(cmd[:6])}\n{detail}")
    return proc


def python_script(script: Path, log: Log, *args: str, env: dict | None = None, timeout: int = 900) -> str:
    proc = run([sys.executable, str(script), *args], log, env=env, timeout=timeout)
    return proc.stdout


# ------------------------------------------------------------------------------------------------ entorno

def read_env() -> dict[str, str]:
    values = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def container_states() -> dict[str, tuple[str, str]]:
    proc = subprocess.run(["docker", "ps", "-a", "--filter", "name=otb-", "--format", "{{json .}}"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    states = {}
    for line in proc.stdout.splitlines():
        row = json.loads(line)
        status = row.get("Status", "")
        health = "healthy" if "(healthy)" in status else "unhealthy" if "(unhealthy)" in status else \
                 "starting" if "health: starting" in status else ""
        states[row["Names"]] = (row.get("State", ""), health)
    return states


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


# ------------------------------------------------------------------------------------------------ pasos

def preflight(log: Log) -> None:
    log.step("Comprobando requisitos")
    if sys.version_info < (3, 10):
        raise Abort(f"Se necesita Python 3.10 o superior (tienes {sys.version.split()[0]})")
    log.ok(f"Python {sys.version.split()[0]}")

    if not shutil.which("docker"):
        raise Abort("Docker no esta instalado: https://docs.docker.com/get-docker/")
    info = run(["docker", "info", "--format", "{{json .}}"], log, check=False, timeout=60)
    if info.returncode != 0:
        raise Abort("Docker esta instalado pero no responde: arranca Docker Desktop (o el servicio docker) y repite")
    data = json.loads(info.stdout or "{}")
    log.ok(f"Docker {data.get('ServerVersion', '?')} en marcha")

    compose = run(["docker", "compose", "version", "--short"], log, check=False)
    if compose.returncode != 0:
        raise Abort("Falta Docker Compose v2 (el comando 'docker compose')")
    log.ok(f"Docker Compose {compose.stdout.strip()}")

    mem_gb = (data.get("MemTotal") or 0) / 1024 ** 3
    if mem_gb and mem_gb < 4:
        log.warn(f"Docker dispone de {mem_gb:.1f} GB de RAM; se recomiendan 4 GB o mas")

    ours = container_states()
    busy = [f"{port} ({name})" for port, name in PORTS.items() if port_busy(port)]
    if busy and not any(state == "running" for state, _ in ours.values()):
        raise Abort("Estos puertos locales estan ocupados por otro programa: " + ", ".join(busy) +
                    "\nLiberalos (o para la aplicacion que los usa) y repite la instalacion.")
    log.ok("Puertos locales disponibles" if not busy else "Puertos en uso por una instalacion previa de OT-Bridge")


def secrets(log: Log) -> None:
    log.step("Secretos y credenciales")
    if not ENV.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV)
        log.info("it/.env creado a partir de la plantilla")
    out = python_script(IT / "scripts" / "ensure_secrets.py", log)
    log.ok("it/.env completo con secretos aleatorios" if "completo" in out or "generados" in out or "anadidos" in out
           else "it/.env revisado")
    if os.name != "nt":
        ENV.chmod(0o600)
    python_script(IT / "scripts" / "mqtt_passwd.py", log, timeout=600)
    log.ok("Usuarios del broker MQTT generados (uno por servicio)")


def wait_healthy(names: list[str], log: Log, label: str) -> None:
    deadline = time.time() + HEALTH_TIMEOUT_S
    last = ""
    while time.time() < deadline:
        states = container_states()
        pending = [n for n in names if states.get(n, ("", ""))[1] not in ("healthy",)
                   and not (states.get(n, ("", ""))[0] == "running" and n == "otb-openplc")]
        failed = [n for n in names if states.get(n, ("", ""))[0] in ("exited", "dead")]
        if failed:
            for name in failed:
                run(["docker", "logs", "--tail", "40", name], log, check=False)
            raise Abort(f"Contenedores detenidos con error: {', '.join(failed)} (detalle en {log.path})")
        if not pending:
            log.ok(f"{label}: {len(names)} servicios en marcha y sanos")
            return
        summary = ", ".join(n.removeprefix("otb-") for n in pending)
        if summary != last:
            log.info(f"esperando: {summary}")
            last = summary
        time.sleep(5)
    raise Abort(f"{label}: servicios sin arrancar tras {HEALTH_TIMEOUT_S // 60} min: {last}")


def start_ot(log: Log) -> None:
    log.step("Capa OT: simulador de planta, PLC y SCADA")
    log.info("construyendo y arrancando (la primera vez descarga las imagenes)...")
    run([*OT_COMPOSE, "up", "-d", "--build", "--remove-orphans"], log, timeout=1800)
    wait_healthy(OT_SERVICES, log, "Capa OT")


def start_it(log: Log) -> None:
    log.step("Capa IT: broker, historico, API, alarmas, gemelo, OPC UA y dashboards")
    log.info("construyendo y arrancando (la primera vez tarda 5-10 min)...")
    run([*IT_COMPOSE, "up", "-d", "--build", "--remove-orphans"], log, cwd=IT, timeout=3600)
    wait_healthy(IT_SERVICES, log, "Capa IT")


def deploy_plc(log: Log) -> None:
    log.step("Programa del PLC")
    log.info("subiendo el programa al runtime y compilando (1-3 min la primera vez)...")
    python_script(ROOT / "ot" / "plc" / "deploy_plc.py", log, timeout=900)
    log.ok("PLC compilado y en RUN")


def deploy_scada(log: Log) -> None:
    log.step("SCADA: proyecto generado desde codigo, seguridad y estacion de instructor")
    hmi = ROOT / "ot" / "scada" / "hmi"
    env = {**os.environ, "FUXA_URL": "http://127.0.0.1:1881"}
    python_script(hmi / "plugins.py", log, "--target", "plant", env=env, timeout=600)
    log.ok("Driver Modbus de FUXA (modbus-serial) instalado")
    python_script(hmi / "generator" / "build.py", log, "--target", "plant")
    python_script(hmi / "deploy.py", log, "--target", "plant", env=env)
    log.ok("Proyecto FUXA desplegado (13 vistas)")
    python_script(hmi / "security.py", log, "--target", "plant", env=env)
    log.ok("Usuarios por rol y autenticacion activados")
    env_admin = {**env, "FUXA_PASSWORD": read_env().get("FUXA_ADMIN_PASSWORD", "")}
    python_script(ROOT / "ot" / "scada" / "tools" / "build_simulation_view.py", log,
                  "--url", "http://127.0.0.1:1881", "--user", "admin", env=env_admin)
    log.ok("Vista Simulador (estacion de instructor) anadida")


def verify(log: Log) -> None:
    log.step("Verificacion de extremo a extremo")
    log.info("esperando a que lleguen los primeros datos del PLC...")
    scada = run([sys.executable, str(ROOT / "ot" / "scada" / "hmi" / "check_scada.py"), "--target", "plant"], log,
                env={**os.environ, "FUXA_URL": "http://127.0.0.1:1881"}, check=False, timeout=300)
    if scada.returncode == 0:
        log.ok("SCADA con datos en vivo del PLC y del simulador")
    else:
        log.warn("El SCADA no recibe datos: " + (scada.stderr.strip().splitlines() or ["sin detalle"])[-1])
    # El gateway reintenta con espera creciente mientras el PLC compila: los primeros datos pueden tardar ~1 min
    for attempt in range(1, 7):
        proc = run([sys.executable, str(IT / "scripts" / "smoke_test.py"), "--quick"], log, cwd=IT, check=False,
                   timeout=300)
        if proc.returncode == 0:
            break
        if attempt < 6:
            log.info("los datos aun no han recorrido toda la cadena; reintentando en 15 s...")
            time.sleep(15)
    result = next((row for row in proc.stdout.splitlines() if row.startswith("RESULTADO")), "")
    if proc.returncode == 0:
        log.ok(result or "Prueba de humo superada")
    else:
        log.warn((result.split("  FALLOS")[0] if result else "La prueba de humo tiene fallos") +
                 f" (detalle: python it/scripts/smoke_test.py; registro: {log.path.relative_to(ROOT)})")
        for line in [row.strip() for row in proc.stdout.splitlines() if "[ERR" in row][:5]:
            log.info(line)


def summary(log: Log) -> None:
    print(f"\n{paint('OT-Bridge en marcha', '1;32')}\n")
    for name, url in ACCESS:
        print(f"  {name:<17} {paint(url, '36')}")
    print("\n  Usuarios:   python otb.py credentials           (--show para ver las contrasenas)")
    print("  Estado:     python otb.py status")
    print(f"  Registro:   {log.path.relative_to(ROOT)}\n")


# ------------------------------------------------------------------------------------------------ acciones

def cmd_install(args) -> None:
    log = Log("install")
    log.total = 7
    preflight(log)
    secrets(log)
    start_ot(log)
    start_it(log)
    deploy_plc(log)
    deploy_scada(log)
    verify(log)
    summary(log)


def cmd_start(args) -> None:
    log = Log("start")
    log.total = 4
    if not ENV.exists():
        raise Abort("OT-Bridge no esta instalado: ejecuta primero  python otb.py install")
    preflight(log)
    start_ot(log)
    start_it(log)
    deploy_plc(log)
    summary(log)


def cmd_stop(args) -> None:
    log = Log("stop")
    log.step("Parando la plataforma (los datos se conservan)")
    run([*IT_COMPOSE, "stop"], log, cwd=IT, check=False)
    run([*OT_COMPOSE, "--profile", "two-host", "stop"], log, check=False)
    log.ok("Plataforma parada. Para volver a arrancar:  python otb.py start")


def cmd_status(args) -> None:
    states = container_states()
    print(f"\n{paint('Servicios', '1')}")
    for zone, names in (("OT", OT_SERVICES), ("IT", IT_SERVICES)):
        for name in names:
            state, health = states.get(name, ("no instalado", ""))
            ok = state == "running" and health in ("healthy", "")
            mark = paint("●", "32" if ok else "33" if state == "running" else "31")
            print(f"  {mark} {zone}  {name.removeprefix('otb-'):<17} {state}{' · ' + health if health else ''}")
    if all(states.get(n, ("",))[0] == "running" for n in OT_SERVICES + IT_SERVICES):
        print(f"\n{paint('Acceso', '1')}")
        for name, url in ACCESS:
            print(f"  {name:<17} {url}")
    print()


def cmd_credentials(args) -> None:
    env = read_env()
    if not env:
        raise Abort("No hay it/.env: ejecuta primero  python otb.py install")
    rows = [("SCADA FUXA", "admin", "FUXA_ADMIN_PASSWORD"), ("SCADA FUXA", "supervisor", "FUXA_SUPERVISOR_PASSWORD"),
            ("SCADA FUXA", "operador", "FUXA_OPERADOR_PASSWORD"), ("SCADA FUXA", "visitante", "FUXA_VISITANTE_PASSWORD"),
            ("Grafana", "admin", "GRAFANA_PASSWORD"), ("OpenPLC runtime", env.get("OPENPLC_USER", "?"), "OPENPLC_PASSWORD"),
            ("OPC UA", env.get("OPC_USER", "?"), "OPC_PASSWORD"), ("API REST (lectura)", "X-API-Key", "API_KEY_GRAFANA"),
            ("API REST (operador)", "X-API-Key", "API_KEY_OPERATOR")]
    print(f"\n{paint('Credenciales', '1')} (fuente: it/.env, que nunca se sube al repositorio)\n")
    for tool, user, key in rows:
        secret = env.get(key, "")
        shown = secret if args.show else ("•" * 12 if secret else "(falta)")
        print(f"  {tool:<20} {user:<12} {shown}")
    if not args.show:
        print("\n  Usa  python otb.py credentials --show  para ver las contrasenas completas.")
    print()


def cmd_deploy_plc(args) -> None:
    log = Log("deploy-plc")
    deploy_plc(log)


def cmd_uninstall(args) -> None:
    log = Log("uninstall")
    log.step("Eliminando los contenedores de OT-Bridge" + (" y sus datos" if args.volumes else ""))
    extra = ["-v"] if args.volumes else []
    run([*IT_COMPOSE, "down", "--remove-orphans", *extra], log, cwd=IT, check=False)
    run([*OT_COMPOSE, "--profile", "two-host", "down", "--remove-orphans", *extra], log, check=False)
    log.ok("Contenedores eliminados" + (" junto con los volumenes de datos" if args.volumes else
                                        " (datos conservados; --volumes para borrarlos)"))
    log.info("it/.env y mosquitto/config/passwd se conservan (borralos a mano si ya no los necesitas)")


def main() -> int:
    parser = argparse.ArgumentParser(prog="otb.py", description="OT-Bridge: instalacion y operacion en un solo host")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install", help="instala o actualiza y arranca todo").set_defaults(func=cmd_install)
    sub.add_parser("start", help="arranca la plataforma instalada").set_defaults(func=cmd_start)
    sub.add_parser("stop", help="para la plataforma (conserva los datos)").set_defaults(func=cmd_stop)
    sub.add_parser("status", help="estado de los servicios").set_defaults(func=cmd_status)
    cred = sub.add_parser("credentials", help="usuarios y contrasenas de cada herramienta")
    cred.add_argument("--show", action="store_true", help="muestra las contrasenas completas")
    cred.set_defaults(func=cmd_credentials)
    sub.add_parser("deploy-plc", help="vuelve a cargar el programa en el PLC").set_defaults(func=cmd_deploy_plc)
    uninst = sub.add_parser("uninstall", help="elimina los contenedores")
    uninst.add_argument("--volumes", action="store_true", help="borra tambien los datos (historico, BBDD, SCADA)")
    uninst.set_defaults(func=cmd_uninstall)
    args = parser.parse_args()
    try:
        args.func(args)
    except Abort as exc:
        print(f"\n{paint('ERROR', '1;31')} {exc}", file=sys.stderr)
        logs = sorted(LOG_DIR.glob("*.log"))
        if logs:
            print(f"Registro completo: {logs[-1].relative_to(ROOT)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
