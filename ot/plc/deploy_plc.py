"""Despliega el programa del PLC en OpenPLC Runtime v4 por su API REST, sin OpenPLC Editor.

Sube el programa compilado (ot/plc/dist/runtime-v4, el mismo paquete que envia el Editor al pulsar Build),
espera a que el runtime lo compile y pone el PLC en RUN. En un runtime recien creado registra primero la
cuenta de administrador con las credenciales de it/.env (la primera cuenta solo se puede crear una vez).

Uso:  python ot/plc/deploy_plc.py [--url https://127.0.0.1:8443] [--no-start]
Credenciales: OPENPLC_USER / OPENPLC_PASSWORD en it/.env (las genera it/scripts/ensure_secrets.py).
"""
from __future__ import annotations

import argparse
import io
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist" / "runtime-v4"
ENV = HERE.parents[1] / "it" / ".env"
COMPILE_TIMEOUT_S = 600
READY_TIMEOUT_S = 180


def env(name: str) -> str:
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    raise SystemExit(f"Falta {name} en it/.env (ejecuta: python it/scripts/ensure_secrets.py)")


class Runtime:
    """Cliente minimo de la API del runtime. Solo para el runtime local: su certificado es autofirmado."""

    def __init__(self, url: str):
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise SystemExit("Por seguridad este script solo habla con un runtime local (certificado autofirmado)")
        self._base = url.rstrip("/") + "/api"
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE
        self._token = ""

    def request(self, method: str, path: str, body: bytes | None = None, content_type: str = "application/json"):
        req = urllib.request.Request(self._base + path, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", content_type)
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, context=self._ctx, timeout=60) as res:
                raw = res.read()
                return res.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, raw.decode(errors="replace")

    def post_json(self, path: str, data: dict):
        return self.request("POST", path, json.dumps(data).encode())

    def wait_ready(self) -> None:
        deadline = time.time() + READY_TIMEOUT_S
        while time.time() < deadline:
            try:
                code, _ = self.request("GET", "/version")
                if code == 200:
                    return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(3)
        raise SystemExit("El runtime de OpenPLC no responde en 127.0.0.1:8443")

    def authenticate(self, user: str, password: str) -> None:
        credentials = {"username": user, "password": password}
        code, body = self.post_json("/login", credentials)
        if code != 200:
            created, detail = self.post_json("/create-user", credentials)
            if created == 201:
                print(f"  cuenta de administrador '{user}' creada en el runtime")
            elif created == 401:
                raise SystemExit("El runtime ya tiene usuarios y OPENPLC_USER/OPENPLC_PASSWORD no coinciden.\n"
                                 "Pon en it/.env las credenciales de ese runtime, o reinicia sus datos con\n"
                                 "  python otb.py uninstall --volumes  (borra tambien el historico)")
            else:
                raise SystemExit(f"No se pudo crear la cuenta del runtime: HTTP {created} {detail}")
            code, body = self.post_json("/login", credentials)
        if code != 200 or not isinstance(body, dict) or "access_token" not in body:
            raise SystemExit("Inicio de sesion en el runtime rechazado")
        self._token = body["access_token"]


def build_zip() -> bytes:
    required = [DIST / "generated.hpp", DIST / "conf" / "modbus_master.json"]
    if not all(p.exists() for p in required):
        raise SystemExit(f"Programa compilado incompleto en {DIST}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(DIST.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(DIST).as_posix())
    return buffer.getvalue()


def multipart(field: str, filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/zip\r\n\r\n").encode()
    return head + payload + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def deploy(rt: Runtime, start: bool) -> None:
    rt.request("GET", "/stop-plc")
    body, ctype = multipart("file", "program.zip", build_zip())
    code, result = rt.request("POST", "/upload-file?clean=1", body, ctype)
    if code != 200 or (isinstance(result, dict) and result.get("UploadFileFail")):
        raise SystemExit(f"Subida del programa rechazada: HTTP {code} {result}")
    print("  programa subido; compilando en el runtime (puede tardar 1-3 min la primera vez)...")

    deadline = time.time() + COMPILE_TIMEOUT_S
    status = ""
    while time.time() < deadline:
        time.sleep(3)
        _, result = rt.request("GET", "/compilation-status")
        status = (result or {}).get("status", "") if isinstance(result, dict) else ""
        if status in ("SUCCESS", "FAILED"):
            break
    if status != "SUCCESS":
        logs = (result or {}).get("logs", []) if isinstance(result, dict) else []
        lines = logs if isinstance(logs, list) else str(logs).splitlines()
        tail = "".join(line if str(line).endswith("\n") else f"{line}\n" for line in lines[-15:])
        raise SystemExit(f"La compilacion no termino bien (estado: {status or 'sin respuesta'})\n{tail}")
    print("  compilacion correcta")

    if start:
        rt.request("GET", "/start-plc")
        deadline = time.time() + 60
        while time.time() < deadline:
            time.sleep(2)
            _, result = rt.request("GET", "/status")
            state = json.dumps(result).upper()
            if "RUNNING" in state:
                print("  PLC en RUN")
                return
        raise SystemExit("El PLC no paso a RUN; revisa: docker logs otb-openplc")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="https://127.0.0.1:8443")
    parser.add_argument("--no-start", action="store_true", help="compila pero deja el PLC parado")
    args = parser.parse_args()
    rt = Runtime(args.url)
    rt.wait_ready()
    rt.authenticate(env("OPENPLC_USER"), env("OPENPLC_PASSWORD"))
    deploy(rt, start=not args.no_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
