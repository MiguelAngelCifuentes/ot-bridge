package com.otbridge.api.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.otbridge.api.exception.UpstreamUnavailableException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.net.http.HttpClient;
import java.time.Duration;

/** Cliente de consultas InfluxQL (solo lectura) compartido por los servicios que leen el historian. */
@Component
public class InfluxQueryClient {

    private final RestClient client;
    private final String database;
    private final String user;
    private final String password;

    public InfluxQueryClient(@Value("${influx.url}") String url,
                             @Value("${influx.database:plant}") String database,
                             @Value("${influx.user:}") String user,
                             @Value("${influx.password:}") String password) {
        HttpClient httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
        JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory(httpClient);
        requestFactory.setReadTimeout(Duration.ofSeconds(10));
        this.client = RestClient.builder().requestFactory(requestFactory).baseUrl(url).build();
        this.database = database;
        this.user = user;
        this.password = password;
    }

    /** Ejecuta una consulta y devuelve el primer resultado (results[0]). */
    public JsonNode query(String influxQl) {
        try {
            JsonNode root = client.get()
                    .uri(uriBuilder -> {
                        uriBuilder.path("/query").queryParam("db", database).queryParam("q", influxQl);
                        if (!user.isBlank()) {
                            uriBuilder.queryParam("u", user).queryParam("p", password);
                        }
                        return uriBuilder.build();
                    })
                    .retrieve()
                    .body(JsonNode.class);
            return root == null ? null : root.path("results").path(0);
        } catch (RestClientException ex) {
            throw new UpstreamUnavailableException("Historian (InfluxDB) no disponible");
        }
    }

    /** Primer valor de la primera serie (consultas de agregado), o null si no hay datos. */
    public Double scalar(String influxQl) {
        JsonNode result = query(influxQl);
        JsonNode series = result == null ? null : result.path("series");
        if (series == null || !series.isArray() || series.isEmpty()) {
            return null;
        }
        JsonNode values = series.get(0).path("values");
        if (!values.isArray() || values.isEmpty() || values.get(0).size() < 2 || values.get(0).get(1).isNull()) {
            return null;
        }
        return values.get(0).get(1).asDouble();
    }
}
