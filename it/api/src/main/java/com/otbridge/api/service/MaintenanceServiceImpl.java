package com.otbridge.api.service;

import com.otbridge.api.dto.MaintenanceIndicatorDto;
import com.otbridge.api.dto.MaintenanceRecommendationDto;
import com.otbridge.api.exception.BadRequestException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

/**
 * Score heuristico de mantenimiento (ultima hora). Indicadores:
 * <ul>
 *   <li>Disponibilidad del PLC (heartbeats online).</li>
 *   <li>Velocidad media de P-101 <b>solo con la bomba en marcha</b>: la bomba parada por el ciclo automatico
 *       es operacion normal, no degradacion.</li>
 *   <li>Perdida no medida estimada por el gemelo digital (l/min): la senal fisica de fuga o anomalia
 *       hidraulica. Sustituye al balance ent-sal de 1 h, que es normal en los ciclos de llenado/vaciado.</li>
 *   <li>Senal media del transmisor de nivel en mA (rango valido NAMUR).</li>
 * </ul>
 * Umbrales en application.properties (prefijo maintenance.). Resultado en cache unos segundos porque Grafana
 * consulta el endpoint en cada refresco.
 */
@Service
public class MaintenanceServiceImpl implements MaintenanceService {

    private static final Pattern PLC_NAME = Pattern.compile("^[A-Za-z0-9_-]{1,64}$");

    private final InfluxQueryClient influx;
    private final double availabilityMin;
    private final double speedMin;
    private final double lossMaxLpm;
    private final double maMin;
    private final double maMax;
    private final Duration cacheTtl;
    private final Map<String, Cached> cache = new ConcurrentHashMap<>();

    private record Cached(Instant at, MaintenanceRecommendationDto value) {
    }

    public MaintenanceServiceImpl(InfluxQueryClient influx,
                                  @Value("${maintenance.availability-min:95}") double availabilityMin,
                                  @Value("${maintenance.speed-min:40}") double speedMin,
                                  @Value("${maintenance.loss-max-lpm:3}") double lossMaxLpm,
                                  @Value("${maintenance.ma-min:3.5}") double maMin,
                                  @Value("${maintenance.ma-max:20.5}") double maMax,
                                  @Value("${maintenance.cache-seconds:15}") long cacheSeconds) {
        this.influx = influx;
        this.availabilityMin = availabilityMin;
        this.speedMin = speedMin;
        this.lossMaxLpm = lossMaxLpm;
        this.maMin = maMin;
        this.maMax = maMax;
        this.cacheTtl = Duration.ofSeconds(cacheSeconds);
    }

    @Override
    public MaintenanceRecommendationDto recommendations(String plc) {
        if (!PLC_NAME.matcher(plc).matches()) {
            throw new BadRequestException("Nombre de PLC no valido");
        }
        Cached cached = cache.get(plc);
        if (cached != null && cached.at().plus(cacheTtl).isAfter(Instant.now())) {
            return cached.value();
        }
        MaintenanceRecommendationDto result = compute(plc);
        cache.put(plc, new Cached(Instant.now(), result));
        return result;
    }

    private MaintenanceRecommendationDto compute(String plc) {
        String where = "\"plc\" = '" + plc + "' AND time > now() - 1h";
        Double availability = influx.scalar("SELECT mean(\"online\") * 100.0 FROM \"plc_status\" WHERE " + where);
        Double speedRunning = influx.scalar("SELECT mean(\"value\") FROM \"sensor_readings\" "
                + "WHERE \"variable\" = 'velocidad' AND \"value\" > 0 AND " + where);
        Double loss = influx.scalar("SELECT mean(\"leak_lpm\") FROM \"twin_state\" WHERE " + where);
        Double maRaw = influx.scalar("SELECT mean(\"value\") FROM \"sensor_readings\" "
                + "WHERE \"variable\" = 'nivel_ma' AND " + where);
        Double ma = maRaw == null ? null : maRaw / PlantUnits.MA_DIVISOR;

        boolean availabilityBad = availability == null || availability < availabilityMin;
        boolean speedBad = speedRunning != null && speedRunning < speedMin;
        boolean lossBad = loss != null && Math.abs(loss) > lossMaxLpm;
        boolean sensorBad = ma != null && (ma < maMin || ma > maMax);
        int score = (availabilityBad ? 40 : 0) + (speedBad ? 30 : 0) + (lossBad ? 30 : 0) + (sensorBad ? 30 : 0);

        List<MaintenanceIndicatorDto> indicators = List.of(
                new MaintenanceIndicatorDto("Disponibilidad PLC (1 h, %)", round(availability),
                        availabilityBad ? "DEGRADADA" : "OK"),
                new MaintenanceIndicatorDto("Velocidad media P-101 en marcha (1 h, %)", round(speedRunning),
                        speedBad ? "ATENCION" : "OK"),
                new MaintenanceIndicatorDto("Perdida no medida, gemelo (1 h, l/min)", round(loss),
                        lossBad ? "ANOMALIA" : "OK"),
                new MaintenanceIndicatorDto("Transmisor LT-101 (1 h, mA)", round(ma),
                        sensorBad ? "DEGRADADO" : "OK"));
        String riskLevel = score >= 60 ? "ALTO" : score >= 30 ? "MEDIO" : "BAJO";
        return new MaintenanceRecommendationDto(plc, riskLevel, score, indicators);
    }

    private static Double round(Double value) {
        return value == null ? null : Math.round(value * 100.0) / 100.0;
    }
}
