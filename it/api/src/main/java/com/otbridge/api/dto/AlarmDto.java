package com.otbridge.api.dto;

import com.otbridge.api.entity.AlarmState;
import com.otbridge.api.entity.Severity;

import java.time.Instant;

public record AlarmDto(
        Long id,
        Long machineId,
        String machineName,
        String variable,
        String code,
        Severity severity,
        AlarmState state,
        String message,
        Instant tsActive,
        Instant tsAck,
        Instant tsResolved,
        String ackBy) {
}
