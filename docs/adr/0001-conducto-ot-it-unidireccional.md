# ADR 0001 · Conducto OT→IT unidireccional y de solo lectura

**Estado:** aceptada

## Contexto

La capa IT necesita los datos del proceso (histórico, alarmas, KPIs, gemelo digital), pero Modbus TCP no
tiene autenticación: cualquier cliente que alcance el `:502` del PLC puede escribir en sus registros.

## Decisión

- La frontera OT/IT se cruza por **un único conducto**: el gateway lee los registros `%MW100..%MW111` del
  PLC con **FC03 (solo lectura)** y publica en MQTT.
- Ningún servicio IT escribe en el PLC. El mando es exclusivo del SCADA (zona OT) y lo valida el PLC.
- En despliegue separado, el `:502` solo admite como origen el host IT (firewall con Block explícito).

## Consecuencias

- Un compromiso de la zona IT no da control sobre el proceso.
- Las órdenes de operación desde IT (por ejemplo, desde la API) no existen por diseño; si se necesitaran,
  irían por un conducto distinto, autenticado y auditado.
- Evolución natural: sustituir el firewall por un proxy unidireccional (data diode).
