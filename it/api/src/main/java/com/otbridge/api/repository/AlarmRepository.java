package com.otbridge.api.repository;

import com.otbridge.api.entity.Alarm;
import com.otbridge.api.entity.AlarmState;
import com.otbridge.api.entity.Severity;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface AlarmRepository extends JpaRepository<Alarm, Long>, JpaSpecificationExecutor<Alarm> {

    Page<Alarm> findByStateOrderByTsActiveDesc(AlarmState state, Pageable pageable);

    List<Alarm> findByMachineIdAndStateOrderByTsActiveDesc(Long machineId, AlarmState state);

    List<Alarm> findByMachineNameAndCodeAndStateIn(String machineName, String code, Collection<AlarmState> states);

    long countByMachineIdAndState(Long machineId, AlarmState state);

    long countByState(AlarmState state);

    @Query("SELECT a.severity, COUNT(a) FROM Alarm a WHERE a.state <> :state GROUP BY a.severity")
    List<Object[]> countBySeverityWhereStateNot(@Param("state") AlarmState state);
}
