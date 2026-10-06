package com.otbridge.api.controller;

import com.otbridge.api.dto.MaintenanceRecommendationDto;
import com.otbridge.api.service.MaintenanceService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maintenance")
public class MaintenanceController {

    private final MaintenanceService maintenanceService;

    public MaintenanceController(MaintenanceService maintenanceService) {
        this.maintenanceService = maintenanceService;
    }

    @GetMapping("/recommendations")
    public MaintenanceRecommendationDto recommendations(@RequestParam(defaultValue = "plc01") String plc) {
        return maintenanceService.recommendations(plc);
    }
}
