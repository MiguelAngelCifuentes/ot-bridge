package com.otbridge.api.service;

import com.otbridge.api.dto.AlarmDto;
import com.otbridge.api.dto.AlarmStatsDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.entity.Alarm;
import com.otbridge.api.entity.AlarmState;
import com.otbridge.api.entity.Machine;
import com.otbridge.api.entity.Severity;
import com.otbridge.api.exception.ConflictException;
import com.otbridge.api.exception.NotFoundException;
import com.otbridge.api.mapper.EntityMapper;
import com.otbridge.api.repository.AlarmRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class AlarmServiceImpl implements AlarmService {

    private static final Logger log = LoggerFactory.getLogger(AlarmServiceImpl.class);

    private static final List<AlarmState> OPEN_STATES = List.of(AlarmState.ACTIVE, AlarmState.ACKNOWLEDGED);

    private final AlarmRepository alarmRepository;
    private final MachineService machineService;

    public AlarmServiceImpl(AlarmRepository alarmRepository, MachineService machineService) {
        this.alarmRepository = alarmRepository;
        this.machineService = machineService;
    }

    @Override
    @Transactional(readOnly = true)
    public PagedResponse<AlarmDto> search(AlarmState state, Severity severity, Long machineId, int page, int size) {
        Specification<Alarm> spec = Specification.where(null);
        if (state != null) {
            spec = spec.and((root, query, cb) -> cb.equal(root.get("state"), state));
        }
        if (severity != null) {
            spec = spec.and((root, query, cb) -> cb.equal(root.get("severity"), severity));
        }
        if (machineId != null) {
            spec = spec.and((root, query, cb) -> cb.equal(root.get("machine").get("id"), machineId));
        }
        Page<Alarm> alarms = alarmRepository.findAll(spec,
                PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "tsActive")));
        return PagedResponse.of(alarms.map(EntityMapper::toAlarmDto));
    }

    @Override
    @Transactional(readOnly = true)
    public AlarmDto findById(Long id) {
        return EntityMapper.toAlarmDto(requireById(id));
    }

    @Override
    @Transactional
    public AlarmDto acknowledge(Long id, String ackBy) {
        Alarm alarm = requireById(id);
        if (alarm.getState() != AlarmState.ACTIVE) {
            throw new ConflictException("La alarma no está en estado ACTIVE (estado actual: " + alarm.getState() + ")");
        }
        alarm.setState(AlarmState.ACKNOWLEDGED);
        alarm.setTsAck(Instant.now());
        alarm.setAckBy(ackBy);
        return EntityMapper.toAlarmDto(alarm);
    }

    @Override
    @Transactional(readOnly = true)
    public AlarmStatsDto stats() {
        long active = alarmRepository.countByState(AlarmState.ACTIVE);
        long acknowledged = alarmRepository.countByState(AlarmState.ACKNOWLEDGED);
        long resolved = alarmRepository.countByState(AlarmState.RESOLVED);
        Map<String, Long> bySeverity = new LinkedHashMap<>();
        for (Object[] row : alarmRepository.countBySeverityWhereStateNot(AlarmState.RESOLVED)) {
            Severity severity = (Severity) row[0];
            bySeverity.put(severity.toJson(), (Long) row[1]);
        }
        return new AlarmStatsDto(active, acknowledged, resolved, bySeverity);
    }

    @Override
    @Transactional
    public void processEvent(String plc, String variable, Severity severity, AlarmState state,
                             String message, String code, Instant ts) {
        Machine machine = machineService.requireByName(plc);
        String alarmCode = (code == null || code.isBlank()) ? variable + ":" + severity.toJson() : code;
        List<Alarm> open = alarmRepository.findByMachineNameAndCodeAndStateIn(plc, alarmCode, OPEN_STATES);
        switch (state) {
            case ACTIVE -> {
                if (!open.isEmpty()) {
                    log.debug("Alarma {} ya abierta; evento ACTIVE ignorado (reentrega)", alarmCode);
                    return;
                }
                Alarm alarm = new Alarm();
                alarm.setMachine(machine);
                alarm.setVariable(variable);
                alarm.setCode(alarmCode);
                alarm.setSeverity(severity);
                alarm.setState(AlarmState.ACTIVE);
                alarm.setMessage(message);
                alarm.setTsActive(ts);
                alarmRepository.save(alarm);
                log.info("Alarma ACTIVE creada: {}/{} ({})", plc, alarmCode, severity.toJson());
            }
            case RESOLVED -> open.forEach(alarm -> {
                alarm.setState(AlarmState.RESOLVED);
                alarm.setTsResolved(ts);
            });
            default -> log.info("Evento de alarma ignorado (estado {}): {}/{}", state, plc, alarmCode);
        }
    }

    private Alarm requireById(Long id) {
        return alarmRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Alarma no encontrada: " + id));
    }
}
