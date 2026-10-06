package com.otbridge.api.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.otbridge.api.dto.HistoryPointDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.dto.SensorDto;
import com.otbridge.api.dto.TelemetrySample;
import com.otbridge.api.entity.Sensor;
import com.otbridge.api.exception.NotFoundException;
import com.otbridge.api.mapper.EntityMapper;
import com.otbridge.api.repository.SensorRepository;
import com.otbridge.api.repository.SensorWriteRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Service
public class SensorServiceImpl implements SensorService {

    private final SensorRepository sensorRepository;
    private final SensorWriteRepository sensorWriteRepository;
    private final InfluxQueryClient influx;

    public SensorServiceImpl(SensorRepository sensorRepository,
                             SensorWriteRepository sensorWriteRepository,
                             InfluxQueryClient influx) {
        this.sensorRepository = sensorRepository;
        this.sensorWriteRepository = sensorWriteRepository;
        this.influx = influx;
    }

    @Override
    @Transactional(readOnly = true)
    public PagedResponse<SensorDto> findAll(int page, int size) {
        Page<Sensor> sensors = sensorRepository.findAll(PageRequest.of(page, size, Sort.by("id")));
        return PagedResponse.of(sensors.map(EntityMapper::toSensorDto));
    }

    @Override
    @Transactional(readOnly = true)
    public List<SensorDto> findByMachine(Long machineId) {
        return sensorRepository.findByMachineIdOrderByIdAsc(machineId).stream()
                .map(EntityMapper::toSensorDto)
                .toList();
    }

    @Override
    @Transactional(readOnly = true)
    public SensorDto findById(Long id) {
        return EntityMapper.toSensorDto(requireById(id));
    }

    @Override
    @Transactional(readOnly = true)
    public List<HistoryPointDto> history(Long sensorId, int minutes, String interval) {
        Sensor sensor = requireById(sensorId);
        String variable = sensor.getVariable();
        String plc = sensor.getMachine().getName();

        String query = String.format(
                "SELECT mean(\"value\") FROM \"sensor_readings\" "
                        + "WHERE (\"variable\" = '%s' AND \"plc\" = '%s') "
                        + "AND time > now() - %dm GROUP BY time(%s) fill(null)",
                literal(variable), literal(plc), minutes, interval);

        JsonNode result = influx.query(query);

        List<HistoryPointDto> points = new ArrayList<>();
        JsonNode series = result == null ? null : result.path("series");
        if (series != null && series.isArray() && !series.isEmpty()) {
            for (JsonNode row : series.get(0).path("values")) {
                JsonNode tsNode = row.get(0);
                JsonNode valueNode = row.get(1);
                if (tsNode.isNull() || valueNode.isNull()) {
                    continue;
                }
                points.add(new HistoryPointDto(Instant.parse(tsNode.asText()), valueNode.asDouble()));
            }
        }
        return points;
    }

    @Override
    public void writeTelemetry(List<TelemetrySample> samples) {
        sensorWriteRepository.updateLastValues(samples);
    }

    /** Escapa un valor para un literal InfluxQL entre comillas simples (evita inyeccion si el dato cambia). */
    private static String literal(String value) {
        return value.replace("\\", "\\\\").replace("'", "\\'");
    }

    private Sensor requireById(Long id) {
        return sensorRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Sensor no encontrado: " + id));
    }
}
