package com.otbridge.api.service;

import com.otbridge.api.dto.ThresholdDto;
import com.otbridge.api.dto.ThresholdRequest;

import java.util.List;

public interface ThresholdService {

    List<ThresholdDto> findAll(Boolean enabledOnly);

    ThresholdDto create(ThresholdRequest request);

    ThresholdDto update(Long id, ThresholdRequest request);
}
