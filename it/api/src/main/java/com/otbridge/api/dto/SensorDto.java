package com.otbridge.api.dto;

import java.time.Instant;

public record SensorDto(
        Long id,
        Long machineId,
        String machineName,
        String variable,
        String unit,
        String description,
        Double lastValue,
        Instant lastTs) {
}
