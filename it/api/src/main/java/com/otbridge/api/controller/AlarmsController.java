package com.otbridge.api.controller;

import com.otbridge.api.dto.AcknowledgeRequest;
import com.otbridge.api.dto.AlarmDto;
import com.otbridge.api.dto.AlarmStatsDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.entity.AlarmState;
import com.otbridge.api.entity.Severity;
import com.otbridge.api.service.AlarmService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/alarms")
@Validated
public class AlarmsController {

    private final AlarmService alarmService;

    public AlarmsController(AlarmService alarmService) {
        this.alarmService = alarmService;
    }

    @GetMapping
    public PagedResponse<AlarmDto> list(
            @RequestParam(required = false) AlarmState state,
            @RequestParam(required = false) Severity severity,
            @RequestParam(required = false) Long machineId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(200) int size) {
        return alarmService.search(state, severity, machineId, page, size);
    }

    @GetMapping("/stats")
    public AlarmStatsDto stats() {
        return alarmService.stats();
    }

    @GetMapping("/{id}")
    public AlarmDto get(@PathVariable Long id) {
        return alarmService.findById(id);
    }

    @PostMapping("/{id}/acknowledge")
    public AlarmDto acknowledge(@PathVariable Long id, @Valid @RequestBody AcknowledgeRequest request) {
        return alarmService.acknowledge(id, request.ackBy());
    }
}
