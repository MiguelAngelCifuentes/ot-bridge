package com.otbridge.api.controller;

import com.otbridge.api.dto.MachineDetailDto;
import com.otbridge.api.dto.MachineDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.dto.SensorDto;
import com.otbridge.api.service.MachineService;
import com.otbridge.api.service.SensorService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/machines")
@Validated
public class MachinesController {

    private final MachineService machineService;
    private final SensorService sensorService;

    public MachinesController(MachineService machineService, SensorService sensorService) {
        this.machineService = machineService;
        this.sensorService = sensorService;
    }

    @GetMapping
    public PagedResponse<MachineDto> list(
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(200) int size) {
        return machineService.findAll(page, size);
    }

    @GetMapping("/{id}")
    public MachineDetailDto get(@PathVariable Long id) {
        return machineService.findById(id);
    }

    @GetMapping("/{id}/sensors")
    public List<SensorDto> sensors(@PathVariable Long id) {
        return sensorService.findByMachine(id);
    }
}
