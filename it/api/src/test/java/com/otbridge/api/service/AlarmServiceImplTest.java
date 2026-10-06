package com.otbridge.api.service;

import com.otbridge.api.entity.Alarm;
import com.otbridge.api.entity.AlarmState;
import com.otbridge.api.entity.Machine;
import com.otbridge.api.entity.Severity;
import com.otbridge.api.exception.ConflictException;
import com.otbridge.api.repository.AlarmRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AlarmServiceImplTest {

    private static final Instant TS = Instant.parse("2026-09-30T10:00:00Z");

    private AlarmRepository repository;
    private AlarmServiceImpl service;
    private Machine machine;

    @BeforeEach
    void setUp() {
        repository = mock(AlarmRepository.class);
        MachineService machines = mock(MachineService.class);
        machine = new Machine();
        machine.setName("plc01");
        when(machines.requireByName("plc01")).thenReturn(machine);
        service = new AlarmServiceImpl(repository, machines);
    }

    private Alarm open(String code, AlarmState state) {
        Alarm alarm = new Alarm();
        alarm.setMachine(machine);
        alarm.setCode(code);
        alarm.setSeverity(Severity.HIGH);
        alarm.setState(state);
        return alarm;
    }

    private void givenOpen(String code, Alarm... alarms) {
        when(repository.findByMachineNameAndCodeAndStateIn(eq("plc01"), eq(code), anyList())).thenReturn(List.of(alarms));
    }

    @Test
    void activeCreatesAlarmWithCode() {
        givenOpen("estado:bit4");
        service.processEvent("plc01", "estado", Severity.CRITICAL, AlarmState.ACTIVE, "Fallo sensor", "estado:bit4", TS);

        ArgumentCaptor<Alarm> saved = ArgumentCaptor.forClass(Alarm.class);
        verify(repository).save(saved.capture());
        assertThat(saved.getValue().getCode()).isEqualTo("estado:bit4");
        assertThat(saved.getValue().getState()).isEqualTo(AlarmState.ACTIVE);
        assertThat(saved.getValue().getTsActive()).isEqualTo(TS);
    }

    @Test
    void activeRedeliveryIsIdempotent() {
        givenOpen("th3", open("th3", AlarmState.ACTIVE));
        service.processEvent("plc01", "nivel_x10", Severity.HIGH, AlarmState.ACTIVE, "m", "th3", TS);
        verify(repository, never()).save(any());
    }

    @Test
    void reactivationOfAcknowledgedAlarmDoesNotCreateOrphan() {
        // D6: una alarma reconocida sigue abierta; un ACTIVE posterior no crea otra
        givenOpen("th3", open("th3", AlarmState.ACKNOWLEDGED));
        service.processEvent("plc01", "nivel_x10", Severity.HIGH, AlarmState.ACTIVE, "m", "th3", TS);
        verify(repository, never()).save(any());
    }

    @Test
    void resolvedClosesEveryOpenAlarmWithThatCode() {
        Alarm active = open("comunicacion", AlarmState.ACTIVE);
        Alarm acknowledged = open("comunicacion", AlarmState.ACKNOWLEDGED);
        givenOpen("comunicacion", active, acknowledged);
        service.processEvent("plc01", "comunicacion", Severity.CRITICAL, AlarmState.RESOLVED, "m", "comunicacion", TS);

        assertThat(List.of(active, acknowledged)).allSatisfy(a -> {
            assertThat(a.getState()).isEqualTo(AlarmState.RESOLVED);
            assertThat(a.getTsResolved()).isEqualTo(TS);
        });
    }

    @Test
    void blankCodeFallsBackToVariableAndSeverity() {
        givenOpen("velocidad:high");
        service.processEvent("plc01", "velocidad", Severity.HIGH, AlarmState.ACTIVE, "m", " ", TS);
        verify(repository).findByMachineNameAndCodeAndStateIn(eq("plc01"), eq("velocidad:high"), anyList());
    }

    @Test
    void acknowledgeOnlyFromActive() {
        Alarm resolved = open("th3", AlarmState.RESOLVED);
        when(repository.findById(7L)).thenReturn(Optional.of(resolved));
        assertThatThrownBy(() -> service.acknowledge(7L, "operador")).isInstanceOf(ConflictException.class);

        Alarm active = open("th3", AlarmState.ACTIVE);
        when(repository.findById(8L)).thenReturn(Optional.of(active));
        service.acknowledge(8L, "operador");
        assertThat(active.getState()).isEqualTo(AlarmState.ACKNOWLEDGED);
        assertThat(active.getAckBy()).isEqualTo("operador");
    }
}
