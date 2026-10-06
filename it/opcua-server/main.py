from __future__ import annotations

import asyncio
import hmac
import logging
import socket
from datetime import datetime, timezone
from pathlib import Path

from asyncua import Server, ua
from asyncua.crypto.cert_gen import setup_self_signed_certificate
from asyncua.crypto.permission_rules import User, UserRole
from cryptography.x509.oid import ExtendedKeyUsageOID

from adapters.mqtt_bridge import MqttBridge
from config import load_config

logger = logging.getLogger("opcua-server")

HEARTBEAT_FILE = Path("/tmp/heartbeat")
APP_URI = "urn:otbridge:opcua-server"

# (nodo OPC UA, variable del contrato MQTT, divisor a unidades de ingenieria, unidad, descripcion)
# divisor None = valor crudo entero (Int32), p. ej. la mascara de bits de estado.
# Los valores del contrato son enteros crudos del PLC (docs/mqtt-contract.md, tabla de escalado).
VARIABLES = (
    ("NivelDeposito", "nivel_x10", 10, "L", "Nivel del deposito TK-101"),
    ("NivelSensorMA", "nivel_ma", 100, "mA", "Senal del transmisor LT-101"),
    ("CaudalEntrada", "caudal_ent", 10, "l/min", "Caudal de entrada (llenado, FT-101)"),
    ("CaudalSalida", "caudal_sal", 10, "l/min", "Caudal de salida (consumo, FT-102)"),
    ("VelocidadBomba", "velocidad", 1, "%", "Velocidad real de la bomba P-101"),
    ("Estado", "estado", None, "", "Registro de estado hmi_estado (bitmask)"),
)


class EnvUserManager:
    """Un unico usuario definido por entorno; sin usuario anonimo."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def get_user(self, iserver, username=None, password=None, certificate=None):
        if username == self._username and password and hmac.compare_digest(password, self._password):
            return User(role=UserRole.User, name=username)
        return None


async def configure_security(server: Server, pki_dir: Path) -> None:
    """Basic256Sha256 (Sign & Encrypt) con certificado autofirmado persistente y login por usuario."""
    pki_dir.mkdir(parents=True, exist_ok=True)
    key_file, cert_file = pki_dir / "server_key.pem", pki_dir / "server_cert.der"
    await setup_self_signed_certificate(key_file, cert_file, APP_URI, socket.gethostname(),
                                        [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH],
                                        {"countryName": "ES", "organizationName": "OT-Bridge",
                                         "commonName": "opcua-server"})
    await server.load_certificate(str(cert_file))
    await server.load_private_key(str(key_file))
    server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
    server.set_security_IDs(["Username"])


def data_value(variant: ua.Variant, status: int, source_ts: datetime | None) -> ua.DataValue:
    return ua.DataValue(Value=variant, StatusCode=ua.StatusCode(status),
                        SourceTimestamp=source_ts, ServerTimestamp=datetime.now(timezone.utc))


def as_variant(raw, divisor: int | None) -> ua.Variant:
    if divisor is None:
        return ua.Variant(int(raw), ua.VariantType.Int32)
    return ua.Variant(float(raw) / divisor, ua.VariantType.Double)


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    logger.info("Servidor OPC UA arrancando en opc.tcp://%s:%d", config.opc_endpoint, config.opc_port)

    bridge = MqttBridge(config)
    bridge.start()

    server = Server(user_manager=EnvUserManager(config.opc_user, config.opc_password)
                    if config.opc_password else None)
    await server.init()
    server.set_endpoint(f"opc.tcp://{config.opc_endpoint}:{config.opc_port}")
    server.set_server_name("OT-Bridge OPC UA Server")
    await server.set_application_uri(APP_URI)
    if config.opc_password:
        await configure_security(server, Path(config.pki_dir))
    else:
        logger.warning("OPC_PASSWORD vacio: servidor SIN seguridad (solo para pruebas)")

    idx = await server.register_namespace("otbridge")
    plant = await server.nodes.objects.add_object(idx, "PlantaSimulada")
    plc = await plant.add_object(idx, "plc01")

    nodes = {}
    for node_name, _var, divisor, unit, description in VARIABLES:
        node = await plc.add_variable(idx, node_name, as_variant(0, divisor))
        await node.write_attribute(ua.AttributeIds.Description,
                                   ua.DataValue(ua.Variant(ua.LocalizedText(description), ua.VariantType.LocalizedText)))
        if unit:
            eu = ua.EUInformation(NamespaceUri="http://www.opcfoundation.org/UA/units/un/cefact",
                                  DisplayName=ua.LocalizedText(unit), Description=ua.LocalizedText(unit))
            await node.add_property(0, "EngineeringUnits", eu)
        nodes[node_name] = node
    online_node = await plc.add_variable(idx, "PLCOnline", False)
    logger.info("Nodos OPC UA creados: %s + PLCOnline", ", ".join(nodes))

    async with server:
        while True:
            await asyncio.sleep(1)
            HEARTBEAT_FILE.touch()
            snapshot = bridge.snapshot()
            online = snapshot["online"].get("plc01", False)
            await online_node.write_value(bool(online))
            for node_name, var, divisor, _unit, _desc in VARIABLES:
                sample = snapshot["values"].get(f"plc01|{var}")
                if sample is None:
                    continue
                value, ts = sample
                source_ts = datetime.fromtimestamp(ts, timezone.utc) if ts > 0 else None
                # sin comunicacion el ultimo valor se conserva pero deja de ser "Good"
                status = ua.StatusCodes.Good if online else ua.StatusCodes.UncertainLastUsableValue
                await nodes[node_name].write_value(data_value(as_variant(value, divisor), status, source_ts))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
