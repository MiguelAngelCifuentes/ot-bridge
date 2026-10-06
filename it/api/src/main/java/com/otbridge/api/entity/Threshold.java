package com.otbridge.api.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "thresholds")
@Getter
@Setter
public class Threshold {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String variable;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 4)
    private Operator operator;

    @Column(nullable = false)
    private Double value;

    @JdbcTypeCode(SqlTypes.NAMED_ENUM)
    @Column(nullable = false)
    private Severity severity;

    @Column(length = 255)
    private String message;

    @Column(nullable = false)
    private boolean enabled;

    /** Histeresis para resolver (unidades de la variable); no aplica a reglas de bit. */
    @Column(nullable = false)
    private double deadband;

    /** Segundos que la condicion debe mantenerse para activar y para resolver. */
    @Column(name = "delay_seconds", nullable = false)
    private int delaySeconds;
}
