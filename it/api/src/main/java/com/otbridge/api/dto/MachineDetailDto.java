package com.otbridge.api.dto;

import java.time.Instant;
import java.util.List;

public record MachineDetailDto(
        Long id,
        String name,
        String description,
        boolean online,
        Instant lastSeenTs,
        List<SensorDto> sensors,
        List<AlarmDto> activeAlarms) {
}
