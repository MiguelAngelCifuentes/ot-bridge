package com.otbridge.api.dto;

import com.otbridge.api.entity.Operator;
import com.otbridge.api.entity.Severity;

public record ThresholdDto(
        Long id,
        String variable,
        Operator operator,
        Double value,
        Severity severity,
        String message,
        boolean enabled,
        double deadband,
        int delaySeconds) {
}
