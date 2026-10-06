package com.otbridge.api.controller;

import com.otbridge.api.dto.HistoryPointDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.dto.SensorDto;
import com.otbridge.api.service.SensorService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/sensors")
@Validated
public class SensorsController {

    private final SensorService sensorService;

    public SensorsController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @GetMapping
    public PagedResponse<SensorDto> list(
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(200) int size) {
        return sensorService.findAll(page, size);
    }

    @GetMapping("/{id}")
    public SensorDto get(@PathVariable Long id) {
        return sensorService.findById(id);
    }

    @GetMapping("/{id}/history")
    public List<HistoryPointDto> history(
            @PathVariable Long id,
            @RequestParam(defaultValue = "60") @Min(1) @Max(43200) int minutes,
            @RequestParam(defaultValue = "1m") @Pattern(regexp = "^\\d+[smh]$") String interval) {
        return sensorService.history(id, minutes, interval);
    }
}
