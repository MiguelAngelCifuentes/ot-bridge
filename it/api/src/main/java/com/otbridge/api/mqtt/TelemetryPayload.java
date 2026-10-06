package com.otbridge.api.mqtt;

public record TelemetryPayload(long ts, String plc, String variable, double value, String unit, int q) {
}
