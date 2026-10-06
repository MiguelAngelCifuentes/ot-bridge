package com.otbridge.api.entity;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

import java.util.Locale;

public enum AlarmState {

    ACTIVE, ACKNOWLEDGED, RESOLVED;

    @JsonValue
    public String toJson() {
        return name();
    }

    @JsonCreator
    public static AlarmState fromJson(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return valueOf(value.trim().toUpperCase(Locale.ROOT));
    }
}
