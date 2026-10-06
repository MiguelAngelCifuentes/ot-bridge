package com.otbridge.api.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.Getter;
import lombok.Setter;

import java.time.Instant;

@Entity
@Table(name = "sensors",
        uniqueConstraints = @UniqueConstraint(name = "uq_sensors_machine_variable",
                columnNames = {"machine_id", "variable"}))
@Getter
@Setter
public class Sensor {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "machine_id", nullable = false)
    private Machine machine;

    @Column(nullable = false, length = 64)
    private String variable;

    @Column(length = 32)
    private String unit;

    @Column(length = 255)
    private String description;

    @Column(name = "last_value")
    private Double lastValue;

    @Column(name = "last_ts")
    private Instant lastTs;
}
