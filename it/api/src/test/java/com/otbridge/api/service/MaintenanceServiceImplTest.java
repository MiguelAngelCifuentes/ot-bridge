package com.otbridge.api.service;

import com.otbridge.api.dto.MaintenanceRecommendationDto;
import com.otbridge.api.exception.BadRequestException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MaintenanceServiceImplTest {

    private InfluxQueryClient influx;
    private MaintenanceServiceImpl service;

    @BeforeEach
    void setUp() {
        influx = mock(InfluxQueryClient.class);
        service = new MaintenanceServiceImpl(influx, 95, 40, 3, 3.5, 20.5, 15);
    }

    private void given(Double availability, Double speedRunning, Double leakLpm, Double maX100) {
        when(influx.scalar(contains("plc_status"))).thenReturn(availability);
        when(influx.scalar(contains("'velocidad'"))).thenReturn(speedRunning);
        when(influx.scalar(contains("twin_state"))).thenReturn(leakLpm);
        when(influx.scalar(contains("'nivel_ma'"))).thenReturn(maX100);
    }

    @Test
    void healthyPlantIsLowRisk() {
        given(100.0, 75.0, 0.2, 1200.0);
        MaintenanceRecommendationDto result = service.recommendations("plc01");
        assertThat(result.score()).isZero();
        assertThat(result.riskLevel()).isEqualTo("BAJO");
    }

    @Test
    void stoppedPumpIsNotPenalized() {
        // D2: sin datos de velocidad > 0 (bomba parada por el ciclo) no hay penalizacion
        given(100.0, null, 0.0, 1200.0);
        assertThat(service.recommendations("plc01").score()).isZero();
    }

    @Test
    void unmeasuredLossAndDegradedSensorRaiseRisk() {
        given(100.0, 75.0, -4.5, 2150.0);                    // 21.5 mA fuera de NAMUR
        MaintenanceRecommendationDto result = service.recommendations("plc01");
        assertThat(result.score()).isEqualTo(60);
        assertThat(result.riskLevel()).isEqualTo("ALTO");
    }

    @Test
    void noAvailabilityDataCountsAsDegraded() {
        given(null, null, null, null);
        assertThat(service.recommendations("plc01").score()).isEqualTo(40);
    }

    @Test
    void queriesFilterByPlcAndResultIsCached() {
        given(100.0, 75.0, 0.0, 1200.0);
        service.recommendations("plc01");
        service.recommendations("plc01");
        verify(influx, times(4)).scalar(contains("\"plc\" = 'plc01'"));
    }

    @Test
    void invalidPlcNameIsRejectedBeforeQuerying() {
        assertThatThrownBy(() -> service.recommendations("plc01' OR 1=1")).isInstanceOf(BadRequestException.class);
        verify(influx, never()).scalar(anyString());
    }
}
