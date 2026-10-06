# ADR 0004 · Arranque seguro del PLC: solo un despliegue explícito lo pone en RUN

**Estado:** aceptada

## Contexto

OpenPLC Runtime v4 pasa automáticamente a RUN al arrancar si encuentra un programa compilado
(`build/libplc_*.so`). Como el contenedor conserva el último programa, un simple reinicio de Docker ponía la
planta en marcha con la lógica del último despliegue, sin intervención del ingeniero y sin que el Editor
estuviera conectado.

## Decisión

El servicio `openplc-runtime` de `ot/scada/docker-compose.yml` borra el programa compilado en cada arranque:

```yaml
command: ["bash", "-c", "rm -f /workdir/build/libplc_*.so && exec bash ./start_openplc.sh"]
```

El runtime arranca vacío y solo un **Build/Upload desde OpenPLC Editor** carga el programa y lo pone en RUN.

## Consecuencias

- Tras un corte de energía o un reinicio, la planta queda parada hasta un arranque deliberado
  (comportamiento esperado en una puesta en marcha controlada).
- Hay que volver a desplegar el programa tras cada reinicio del contenedor.
- Usuarios y configuración del runtime se conservan en el volumen `openplc-runtime-data`.
