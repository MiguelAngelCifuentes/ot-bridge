package com.otbridge.api.mapper;

import com.otbridge.api.dto.AlarmDto;
import com.otbridge.api.dto.MachineDto;
import com.otbridge.api.dto.SensorDto;
import com.otbridge.api.dto.ThresholdDto;
import com.otbridge.api.entity.Alarm;
import com.otbridge.api.entity.Machine;
import com.otbridge.api.entity.Sensor;
import com.otbridge.api.entity.Threshold;

public final class EntityMapper {

    private EntityMapper() {
    }

    public static MachineDto toMachineDto(Machine machine, long activeAlarms) {
        return new MachineDto(
                machine.getId(),
                machine.getName(),
                machine.getDescription(),
                machine.isOnline(),
                machine.getLastSeenTs(),
                machine.getSensors().size(),
                activeAlarms);
    }

    public static SensorDto toSensorDto(Sensor sensor) {
        return new SensorDto(
                sensor.getId(),
                sensor.getMachine().getId(),
                sensor.getMachine().getName(),
                sensor.getVariable(),
                sensor.getUnit(),
                sensor.getDescription(),
                sensor.getLastValue(),
                sensor.getLastTs());
    }

    public static AlarmDto toAlarmDto(Alarm alarm) {
        return new AlarmDto(
                alarm.getId(),
                alarm.getMachine().getId(),
                alarm.getMachine().getName(),
                alarm.getVariable(),
                alarm.getCode(),
                alarm.getSeverity(),
                alarm.getState(),
                alarm.getMessage(),
                alarm.getTsActive(),
                alarm.getTsAck(),
                alarm.getTsResolved(),
                alarm.getAckBy());
    }

    public static ThresholdDto toThresholdDto(Threshold threshold) {
        return new ThresholdDto(
                threshold.getId(),
                threshold.getVariable(),
                threshold.getOperator(),
                threshold.getValue(),
                threshold.getSeverity(),
                threshold.getMessage(),
                threshold.isEnabled(),
                threshold.getDeadband(),
                threshold.getDelaySeconds());
    }
}
