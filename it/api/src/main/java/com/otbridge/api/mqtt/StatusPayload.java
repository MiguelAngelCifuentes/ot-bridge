package com.otbridge.api.mqtt;

public record StatusPayload(long ts, String plc, boolean online) {
}
