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
import jakarta.persistence.Version;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;

@Entity
@Table(name = "alarms")
@Getter
@Setter
public class Alarm {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "machine_id", nullable = false)
    private Machine machine;

    @Column(nullable = false, length = 64)
    private String variable;

    /** Identidad de la alarma (regla que la origina): dos bits distintos de 'estado' son alarmas distintas. */
    @Column(nullable = false, length = 64)
    private String code;

    @JdbcTypeCode(SqlTypes.NAMED_ENUM)
    @Column(nullable = false)
    private Severity severity;

    @JdbcTypeCode(SqlTypes.NAMED_ENUM)
    @Column(nullable = false)
    private AlarmState state;

    @Column(length = 255)
    private String message;

    @Column(name = "ts_active", nullable = false)
    private Instant tsActive;

    @Column(name = "ts_ack")
    private Instant tsAck;

    @Column(name = "ts_resolved")
    private Instant tsResolved;

    @Column(name = "ack_by", length = 64)
    private String ackBy;

    @Version
    @Column(nullable = false)
    private Long version;
}
