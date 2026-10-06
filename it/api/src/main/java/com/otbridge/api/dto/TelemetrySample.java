package com.otbridge.api.dto;

import java.time.Instant;

public record TelemetrySample(String machine, String variable, double value, Instant ts) {
}
