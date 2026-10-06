package com.otbridge.api.service;

import com.otbridge.api.dto.AlarmDto;
import com.otbridge.api.dto.MachineDetailDto;
import com.otbridge.api.dto.MachineDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.dto.SensorDto;
import com.otbridge.api.entity.AlarmState;
import com.otbridge.api.entity.Machine;
import com.otbridge.api.exception.NotFoundException;
import com.otbridge.api.mapper.EntityMapper;
import com.otbridge.api.repository.AlarmRepository;
import com.otbridge.api.repository.MachineRepository;
import com.otbridge.api.repository.SensorRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;

@Service
public class MachineServiceImpl implements MachineService {

    private final MachineRepository machineRepository;
    private final SensorRepository sensorRepository;
    private final AlarmRepository alarmRepository;

    public MachineServiceImpl(MachineRepository machineRepository,
                              SensorRepository sensorRepository,
                              AlarmRepository alarmRepository) {
        this.machineRepository = machineRepository;
        this.sensorRepository = sensorRepository;
        this.alarmRepository = alarmRepository;
    }

    @Override
    @Transactional(readOnly = true)
    public PagedResponse<MachineDto> findAll(int page, int size) {
        Page<Machine> machines = machineRepository.findAll(PageRequest.of(page, size, Sort.by("name")));
        Page<MachineDto> dtos = machines.map(machine ->
                EntityMapper.toMachineDto(machine,
                        alarmRepository.countByMachineIdAndState(machine.getId(), AlarmState.ACTIVE)));
        return PagedResponse.of(dtos);
    }

    @Override
    @Transactional(readOnly = true)
    public MachineDetailDto findById(Long id) {
        Machine machine = requireById(id);
        List<SensorDto> sensors = sensorRepository.findByMachineIdOrderByIdAsc(id).stream()
                .map(EntityMapper::toSensorDto)
                .toList();
        List<AlarmDto> activeAlarms = alarmRepository.findByMachineIdAndStateOrderByTsActiveDesc(id, AlarmState.ACTIVE)
                .stream()
                .map(EntityMapper::toAlarmDto)
                .toList();
        return new MachineDetailDto(
                machine.getId(),
                machine.getName(),
                machine.getDescription(),
                machine.isOnline(),
                machine.getLastSeenTs(),
                sensors,
                activeAlarms);
    }

    @Override
    @Transactional
    public void updateStatus(String name, boolean online, Instant ts) {
        machineRepository.findByName(name).ifPresent(machine -> {
            machine.setOnline(online);
            machine.setLastSeenTs(ts);
        });
    }

    @Override
    @Transactional(readOnly = true)
    public Machine requireByName(String name) {
        return machineRepository.findByName(name)
                .orElseThrow(() -> new NotFoundException("Máquina no encontrada: " + name));
    }

    private Machine requireById(Long id) {
        return machineRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Máquina no encontrada: " + id));
    }
}
