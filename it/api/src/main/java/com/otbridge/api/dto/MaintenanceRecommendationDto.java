package com.otbridge.api.dto;

import java.util.List;

public record MaintenanceRecommendationDto(
        String machineName,
        String riskLevel,
        int score,
        List<MaintenanceIndicatorDto> indicators) {
}
