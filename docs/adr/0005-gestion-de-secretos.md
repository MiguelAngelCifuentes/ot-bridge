# ADR 0005 · Secretos fuera del repositorio, generados y nunca impresos

**Estado:** aceptada

## Contexto

El sistema maneja más de 20 credenciales: usuarios MQTT por servicio, InfluxDB por rol, PostgreSQL, claves
de API por cliente, OPC UA, Grafana y los usuarios del SCADA. Escribirlas a mano invita a reutilizarlas y a
que acaben en commits, logs o backups.

## Decisión

- Todas viven en `it/.env`, excluido de git. La plantilla `it/.env.example` solo lleva marcadores `CAMBIAR`.
- `it/scripts/ensure_secrets.py` genera valores aleatorios (`secrets.token_urlsafe`) para los que falten o
  sigan con el marcador, sin imprimirlos nunca.
- Los ficheros derivados (`passwd` de Mosquitto, roles de InfluxDB y PostgreSQL) se regeneran desde `.env`
  con scripts idempotentes.
- Los backups excluyen `.env` y `passwd`; los backups de FUXA (que incluyen credenciales) quedan fuera de git.
- Defensa en profundidad del repositorio: `.gitignore` estricto, gitleaks en pre-commit y en CI.

## Consecuencias

- Una instalación nueva no comparte credenciales con ninguna otra.
- Rotar una clave = cambiarla en `.env` y ejecutar el script correspondiente.
- `.env` queda sin cifrar en disco (riesgo aceptado en laboratorio; roadmap: Docker secrets).
