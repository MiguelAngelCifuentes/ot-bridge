package com.otbridge.api.mqtt;

import com.otbridge.api.entity.AlarmState;
import com.otbridge.api.entity.Severity;

public record AlarmEventPayload(
        long ts,
        String plc,
        String variable,
        Severity severity,
        AlarmState state,
        String message,
        String code) {
}
