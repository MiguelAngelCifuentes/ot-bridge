package com.otbridge.api.dto;

import java.time.Instant;

public record MachineDto(
        Long id,
        String name,
        String description,
        boolean online,
        Instant lastSeenTs,
        int sensorCount,
        long activeAlarmCount) {
}
