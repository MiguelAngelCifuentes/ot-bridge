package com.otbridge.api.service;

import com.otbridge.api.dto.MaintenanceRecommendationDto;

public interface MaintenanceService {

    MaintenanceRecommendationDto recommendations(String plc);
}
