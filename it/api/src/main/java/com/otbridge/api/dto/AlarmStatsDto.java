package com.otbridge.api.dto;

import java.util.Map;

public record AlarmStatsDto(
        long active,
        long acknowledged,
        long resolved,
        Map<String, Long> bySeverityActive) {
}
