package com.otbridge.api.dto;

import com.otbridge.api.entity.Operator;
import com.otbridge.api.entity.Severity;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record ThresholdRequest(
        @NotBlank @Size(max = 64) String variable,
        @NotNull Operator operator,
        @NotNull Double value,
        @NotNull Severity severity,
        @Size(max = 255) String message,
        Boolean enabled,
        @PositiveOrZero Double deadband,
        @Min(0) @Max(3600) Integer delaySeconds) {
}
