# Política de seguridad

OT-Bridge es un proyecto de laboratorio y demostración: **no está pensado para controlar procesos reales**
sin una evaluación de riesgos y un endurecimiento adicional (TLS, gestión de identidades, segmentación física).

## Notificar una vulnerabilidad

Si encuentras una vulnerabilidad, no abras un issue público. Usa
**[Report a vulnerability](../../security/advisories/new)** (GitHub Private Vulnerability Reporting) e incluye:

- componente afectado (simulador, PLC, SCADA, gateway, broker, API…);
- pasos para reproducirla y el impacto esperado;
- versión o commit.

Recibirás respuesta en un plazo razonable y se publicará un aviso una vez corregida.

## Alcance

Controles implementados, modelo de amenazas y riesgos aceptados: [docs/security.md](docs/security.md).

Los riesgos aceptados documentados (por ejemplo, Modbus sin autenticación o MQTT sin TLS en laboratorio)
no se consideran vulnerabilidades, salvo que se demuestre un impacto mayor del descrito.
