package com.otbridge.api.repository;

import com.otbridge.api.dto.TelemetrySample;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.util.Collection;

@Repository
public class SensorWriteRepository {

    private static final String UPDATE_LAST_VALUE = """
            UPDATE sensors s
               SET last_value = ?, last_ts = ?
              FROM machines m
             WHERE s.machine_id = m.id
               AND m.name = ?
               AND s.variable = ?
            """;

    private final JdbcTemplate jdbc;

    public SensorWriteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void updateLastValues(Collection<TelemetrySample> samples) {
        if (samples.isEmpty()) {
            return;
        }
        jdbc.batchUpdate(UPDATE_LAST_VALUE, samples, samples.size(),
                (ps, sample) -> {
                    ps.setDouble(1, sample.value());
                    ps.setTimestamp(2, Timestamp.from(sample.ts()));
                    ps.setString(3, sample.machine());
                    ps.setString(4, sample.variable());
                });
    }
}
