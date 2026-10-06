package com.otbridge.api.repository;

import com.otbridge.api.entity.Sensor;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface SensorRepository extends JpaRepository<Sensor, Long> {

    List<Sensor> findByMachineIdOrderByIdAsc(Long machineId);

    Optional<Sensor> findByMachineNameAndVariable(String machineName, String variable);

    boolean existsByVariable(String variable);
}
