#!/bin/sh
# Inicializacion de un volumen nuevo de InfluxDB 1.8.
# La imagen oficial ya ha creado la BD (INFLUXDB_DB) y los usuarios INFLUXDB_ADMIN/WRITE/READ_USER.
# Aqui se aplican retenciones y continuous queries desde schema.influxql (mismo fichero que usa
# scripts/influx_schema.py sobre una instalacion existente).
set -e

INFLUX="influx -host 127.0.0.1 -port ${INFLUXDB_INIT_PORT:-8086} -username ${INFLUXDB_ADMIN_USER} -password ${INFLUXDB_ADMIN_PASSWORD}"

grep -v '^--' /docker-entrypoint-initdb.d/schema.influxql | while IFS= read -r statement; do
    [ -n "$statement" ] && $INFLUX -execute "$statement"
done

echo "InfluxDB inicializada: BD plant, rp_30d (crudo 1 Hz, por defecto), rp_1y (agregados 1 min) y CQs"
