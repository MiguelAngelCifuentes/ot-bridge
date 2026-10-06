# ADR 0003 · SCADA y dashboards generados desde código

**Estado:** aceptada

## Contexto

FUXA y Grafana se editan normalmente a mano en su interfaz web. Eso deja la configuración en bases de datos
binarias, sin revisión, difícil de reproducir y con riesgo de incoherencias entre el SCADA y los dashboards
(escalados, nombres de bits, colores).

## Decisión

- El proyecto FUXA completo (13 vistas, 237 controles, 50 tags, alarmas y gráficas) se **genera en Python**
  (`ot/scada/hmi/generator/`) y se despliega por API con backup previo y rollback.
- Los 7 dashboards de Grafana se generan desde `it/grafana/generator/` y se provisionan como ficheros.
- Un sistema de diseño común **ISA-101** (gris lo normal, color solo lo anómalo) se aplica en ambos.
- El build **valida** el proyecto: tags referenciados, vistas enlazadas, históricos de las gráficas y que
  ningún mando quede sin permiso.

## Consecuencias

- La configuración se revisa en pull requests y se reproduce en cualquier instalación.
- Las bases de datos de FUXA (`fuxa_data/`) no se versionan: contienen usuarios, el secreto JWT y credenciales.
- Requiere conocer el formato interno de FUXA 1.3.4 (documentado en [scada-hmi.md](../scada-hmi.md) §9).
