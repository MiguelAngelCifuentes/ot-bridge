package com.otbridge.api.controller;

import com.otbridge.api.dto.ThresholdDto;
import com.otbridge.api.dto.ThresholdRequest;
import com.otbridge.api.service.ThresholdService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/thresholds")
public class ThresholdsController {

    private final ThresholdService thresholdService;

    public ThresholdsController(ThresholdService thresholdService) {
        this.thresholdService = thresholdService;
    }

    @GetMapping
    public List<ThresholdDto> list(@RequestParam(defaultValue = "false") boolean enabledOnly) {
        return thresholdService.findAll(enabledOnly);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ThresholdDto create(@Valid @RequestBody ThresholdRequest request) {
        return thresholdService.create(request);
    }

    @PutMapping("/{id}")
    public ThresholdDto update(@PathVariable Long id, @Valid @RequestBody ThresholdRequest request) {
        return thresholdService.update(id, request);
    }
}
