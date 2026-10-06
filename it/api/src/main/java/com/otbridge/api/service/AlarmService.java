package com.otbridge.api.service;

import com.otbridge.api.dto.AlarmDto;
import com.otbridge.api.dto.AlarmStatsDto;
import com.otbridge.api.dto.PagedResponse;
import com.otbridge.api.entity.AlarmState;
import com.otbridge.api.entity.Severity;

import java.time.Instant;

public interface AlarmService {

    PagedResponse<AlarmDto> search(AlarmState state, Severity severity, Long machineId, int page, int size);

    AlarmDto findById(Long id);

    AlarmDto acknowledge(Long id, String ackBy);

    AlarmStatsDto stats();

    /**
     * Aplica un evento del bus. {@code code} identifica la alarma (regla que la origina); si el productor
     * no lo envia se usa {@code variable:severidad}. ACTIVE crea la alarma solo si no hay una abierta con ese
     * codigo (idempotente ante reentregas QoS 1); RESOLVED cierra todas las abiertas con ese codigo.
     */
    void processEvent(String plc, String variable, Severity severity, AlarmState state,
                      String message, String code, Instant ts);
}
