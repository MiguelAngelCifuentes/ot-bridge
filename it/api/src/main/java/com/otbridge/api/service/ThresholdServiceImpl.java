package com.otbridge.api.service;

import com.otbridge.api.dto.ThresholdDto;
import com.otbridge.api.dto.ThresholdRequest;
import com.otbridge.api.entity.Threshold;
import com.otbridge.api.exception.BadRequestException;
import com.otbridge.api.exception.NotFoundException;
import com.otbridge.api.repository.SensorRepository;
import com.otbridge.api.mapper.EntityMapper;
import com.otbridge.api.repository.ThresholdRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class ThresholdServiceImpl implements ThresholdService {

    private final ThresholdRepository thresholdRepository;
    private final SensorRepository sensorRepository;

    public ThresholdServiceImpl(ThresholdRepository thresholdRepository, SensorRepository sensorRepository) {
        this.thresholdRepository = thresholdRepository;
        this.sensorRepository = sensorRepository;
    }

    @Override
    @Transactional(readOnly = true)
    public List<ThresholdDto> findAll(Boolean enabledOnly) {
        List<Threshold> thresholds = Boolean.TRUE.equals(enabledOnly)
                ? thresholdRepository.findByEnabledTrueOrderByIdAsc()
                : thresholdRepository.findAllByOrderByIdAsc();
        return thresholds.stream().map(EntityMapper::toThresholdDto).toList();
    }

    @Override
    @Transactional
    public ThresholdDto create(ThresholdRequest request) {
        Threshold threshold = new Threshold();
        apply(request, threshold);
        threshold.setEnabled(request.enabled() == null || request.enabled());
        return EntityMapper.toThresholdDto(thresholdRepository.save(threshold));
    }

    @Override
    @Transactional
    public ThresholdDto update(Long id, ThresholdRequest request) {
        Threshold threshold = thresholdRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Umbral no encontrado: " + id));
        apply(request, threshold);
        if (request.enabled() != null) {
            threshold.setEnabled(request.enabled());
        }
        return EntityMapper.toThresholdDto(threshold);
    }

    private void apply(ThresholdRequest request, Threshold threshold) {
        // una regla sobre una variable inexistente nunca dispararia (p. ej. una errata en el nombre)
        if (!sensorRepository.existsByVariable(request.variable())) {
            throw new BadRequestException("Variable desconocida: " + request.variable());
        }
        threshold.setVariable(request.variable());
        threshold.setOperator(request.operator());
        threshold.setValue(request.value());
        threshold.setSeverity(request.severity());
        threshold.setMessage(request.message());
        if (request.deadband() != null) {
            threshold.setDeadband(request.deadband());
        }
        if (request.delaySeconds() != null) {
            threshold.setDelaySeconds(request.delaySeconds());
        }
    }
}
