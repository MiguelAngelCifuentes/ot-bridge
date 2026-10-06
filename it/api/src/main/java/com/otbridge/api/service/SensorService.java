package com.otbridge.api.service;

import com.otbridge.api.dto.HistoryPointDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.dto.SensorDto;
import com.otbridge.api.dto.TelemetrySample;

import java.util.List;

public interface SensorService {

    PagedResponse<SensorDto> findAll(int page, int size);

    List<SensorDto> findByMachine(Long machineId);

    SensorDto findById(Long id);

    List<HistoryPointDto> history(Long sensorId, int minutes, String interval);

    void writeTelemetry(List<TelemetrySample> samples);
}
