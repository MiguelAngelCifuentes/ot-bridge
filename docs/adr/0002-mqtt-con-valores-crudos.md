# ADR 0002 · MQTT como bus de integración IT con valores crudos del PLC

**Estado:** aceptada

## Contexto

Seis consumidores IT (historian, motor de alarmas, API, OPC UA, gemelo digital y FUXA) necesitan los mismos
datos con semánticas distintas. Acoplar cada uno al PLC por Modbus multiplicaría las conexiones a la zona OT.

## Decisión

- El gateway publica **una vez** en Mosquitto y cada servicio se suscribe con su propio usuario y ACL.
- Un topic por variable: `factory/<plc>/telemetry/<variable>`, con `ts` UTC, `plc`, `unit` y calidad `q`.
- Los valores viajan **sin escalar** (enteros crudos del PLC). Cada consumidor aplica el divisor documentado
  en [mqtt-contract.md](../mqtt-contract.md).

## Consecuencias

- Sin pérdida de precisión ni cambio de tipo en InfluxDB (los campos enteros siguen siendo enteros).
- El escalado está implementado en varios consumidores: el contrato es la única fuente de verdad y cualquier
  cambio exige actualizar todos a la vez.
- Añadir un consumidor nuevo no toca la zona OT.
