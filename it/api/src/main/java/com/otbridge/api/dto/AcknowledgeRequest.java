package com.otbridge.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AcknowledgeRequest(
        @NotBlank @Size(max = 64) String ackBy) {
}
