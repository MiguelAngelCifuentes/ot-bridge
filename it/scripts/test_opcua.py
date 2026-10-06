"""Verificacion OPC UA: lee los nodos de opcua-server con Basic256Sha256 (Sign & Encrypt) + usuario.

Genera (una vez) un certificado de cliente autofirmado en scripts/.opcua-client/ (gitignored) y usa
OPC_USER / OPC_PASSWORD de .env. Comprueba ademas que el acceso anonimo sin cifrar es rechazado.
Uso:  .\\venv\\Scripts\\python.exe scripts\\test_opcua.py
"""
from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

from asyncua import Client, ua
from asyncua.crypto.cert_gen import setup_self_signed_certificate
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256
from cryptography.x509.oid import ExtendedKeyUsageOID

ROOT = Path(__file__).resolve().parent.parent
PKI = ROOT / "scripts" / ".opcua-client"
URL = "opc.tcp://127.0.0.1:4840"
CLIENT_URI = "urn:otbridge:test-client"


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


async def anonymous_rejected() -> bool:
    try:
        async with Client(url=URL, timeout=5) as client:
            await client.nodes.objects.get_children()
        return False
    except Exception:
        return True


async def main() -> int:
    e = env()
    PKI.mkdir(exist_ok=True)
    key, cert = PKI / "client_key.pem", PKI / "client_cert.der"
    await setup_self_signed_certificate(key, cert, CLIENT_URI, socket.gethostname(),
                                        [ExtendedKeyUsageOID.CLIENT_AUTH], {"commonName": "otbridge-test"})

    client = Client(url=URL, timeout=10)
    client.application_uri = CLIENT_URI
    client.set_user(e["OPC_USER"])
    client.set_password(e["OPC_PASSWORD"])
    await client.set_security(SecurityPolicyBasic256Sha256, str(cert), str(key),
                              mode=ua.MessageSecurityMode.SignAndEncrypt)
    print(f"Conectando a {URL} (Basic256Sha256 SignAndEncrypt, usuario {e['OPC_USER']}) ...")
    async with client:
        planta = await client.nodes.objects.get_child(["2:PlantaSimulada", "2:plc01"])
        children = await planta.get_children()
        print(f"\nNodos bajo PlantaSimulada/plc01 ({len(children)}):\n")
        print(f"  {'Nodo':<22} {'Valor':>10} {'Unidad':<8} {'Calidad':<26} Origen")
        for node in children:
            name = (await node.read_browse_name()).Name
            dv = await node.read_data_value()
            unit = ""
            try:
                eu = await node.get_child(["0:EngineeringUnits"])
                unit = (await eu.read_value()).DisplayName.Text
            except ua.UaError:
                pass
            src = dv.SourceTimestamp.strftime("%H:%M:%S") if dv.SourceTimestamp else "-"
            print(f"  {name:<22} {dv.Value.Value!s:>10} {unit:<8} {dv.StatusCode.name:<26} {src}")

    rejected = await anonymous_rejected()
    print(f"\nAcceso anonimo sin cifrar rechazado: {'SI' if rejected else 'NO (revisar seguridad)'}")
    print("Verificacion OPC UA OK" if rejected else "Verificacion OPC UA con avisos")
    return 0 if rejected else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
