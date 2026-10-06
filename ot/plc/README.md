# PLC · OpenPLC v4 (IEC 61131-3)

| Ruta | Contenido |
|---|---|
| `pous/programs/main.st` | **Programa fuente** en Structured Text: acondicionamiento 4-20 mA, diagnóstico NAMUR, histéresis, reserva, manual/automático, seguridades y vigilancia del contactor |
| `devices/remote/*.json` | Modbus maestro hacia el simulador de campo (`field-simulator:5020` sensores, `:5021` actuadores) |
| `devices/servers/HMI_Server.json` | Modbus esclavo `:502` con `%MW100..%MW111` para el SCADA y el gateway OT→IT |
| `project.json` | Proyecto de OpenPLC Editor (tarea cíclica de 20 ms) |
| `dist/runtime-v4/` | Programa **compilado por OpenPLC Editor** a partir de `main.st`, listo para el runtime |
| `deploy_plc.py` | Despliega `dist/runtime-v4` por la API del runtime, sin el Editor (`python otb.py deploy-plc`) |

## Flujo de trabajo

- **Usar la planta:** `python otb.py install` despliega este programa automáticamente.
- **Cambiar la lógica:** abre esta carpeta en OpenPLC Editor v4, edita `main.st` y pulsa **Build** contra
  `https://localhost:8443`. Para que `otb.py` despliegue tu versión, copia la salida del Build
  (`build/OpenPLC Runtime v4/src/`) sobre `dist/runtime-v4/` y haz commit.

El contrato de registros está en [docs/register-map.md](../../docs/register-map.md) y
[docs/mqtt-contract.md](../../docs/mqtt-contract.md) (§5).

## Componentes de terceros

`dist/runtime-v4/` contiene código generado por OpenPLC Editor y las cabeceras de la biblioteca de runtime
STruC++ (`strucpp_runtime/include/`), © Autonomy / OpenPLC Project, distribuidas bajo
**GPL-3.0-or-later WITH STruCpp-runtime-exception**, tal como indica la cabecera de cada fichero. Esa excepción
permite usarlas en programas de PLC sin imponer la GPL al programa. El resto del repositorio se distribuye bajo
la licencia [MIT](../../LICENSE).
