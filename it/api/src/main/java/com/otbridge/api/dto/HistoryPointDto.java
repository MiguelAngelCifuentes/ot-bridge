package com.otbridge.api.dto;

import java.time.Instant;

public record HistoryPointDto(Instant ts, Double value) {
}
