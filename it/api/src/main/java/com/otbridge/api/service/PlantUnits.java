package com.otbridge.api.service;

/**
 * Escalado del contrato MQTT: los valores son enteros crudos del PLC (docs/mqtt-contract.md, tabla de escalado).
 * Unica fuente de estas constantes en la API.
 */
public final class PlantUnits {

    /** nivel_x10 -> litros */
    public static final double LEVEL_DIVISOR = 10.0;
    /** nivel_ma -> mA */
    public static final double MA_DIVISOR = 100.0;
    /** caudal_ent / caudal_sal (l/min x10, hmi_caudal_* del PLC) -> l/min */
    public static final double FLOW_DIVISOR = 10.0;

    private PlantUnits() {
    }
}
