package com.otbridge.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mqtt")
public record MqttProperties(String broker, String clientId, String user, String pass) {
}
