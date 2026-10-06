package com.otbridge.api.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.otbridge.api.dto.ApiError;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Set;

/**
 * Autenticacion por API key (cabecera {@code X-API-Key}) para {@code /api/**}.
 *
 * <ul>
 *   <li>{@code api.keys.read}: clientes de solo lectura (Grafana, motor de alarmas): solo GET.</li>
 *   <li>{@code api.keys.operator}: operacion (ACK de alarmas, umbrales): todos los metodos.</li>
 * </ul>
 * Sin clave o con clave invalida: 401. Clave de lectura en un metodo de escritura: 403.
 * {@code /actuator/health} queda fuera (healthcheck de Docker).
 */
@Component
public class ApiKeyFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(ApiKeyFilter.class);
    private static final String HEADER = "X-API-Key";
    private static final Set<String> READ_METHODS = Set.of("GET", "HEAD", "OPTIONS");

    private final boolean enabled;
    private final byte[][] readKeys;
    private final byte[] operatorKey;
    private final ObjectMapper objectMapper;

    public ApiKeyFilter(@Value("${api.security.enabled:true}") boolean enabled,
                        @Value("${api.keys.read:}") String readKeys,
                        @Value("${api.keys.operator:}") String operatorKey,
                        ObjectMapper objectMapper) {
        this.enabled = enabled;
        this.readKeys = java.util.Arrays.stream(readKeys.split(","))
                .map(String::trim).filter(k -> !k.isEmpty())
                .map(k -> k.getBytes(StandardCharsets.UTF_8)).toArray(byte[][]::new);
        this.operatorKey = operatorKey.isBlank() ? null : operatorKey.getBytes(StandardCharsets.UTF_8);
        this.objectMapper = objectMapper;
        if (enabled && this.readKeys.length == 0 && this.operatorKey == null) {
            log.warn("api.security.enabled=true sin claves configuradas: toda peticion a /api sera rechazada");
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !enabled || !request.getRequestURI().startsWith("/api/")
                || "OPTIONS".equalsIgnoreCase(request.getMethod());      // preflight CORS
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String presented = request.getHeader(HEADER);
        byte[] key = presented == null ? null : presented.getBytes(StandardCharsets.UTF_8);
        if (key != null && operatorKey != null && MessageDigest.isEqual(key, operatorKey)) {
            chain.doFilter(request, response);
            return;
        }
        boolean readKey = false;
        if (key != null) {
            for (byte[] candidate : readKeys) {
                readKey |= MessageDigest.isEqual(key, candidate);   // sin cortocircuito: tiempo constante
            }
        }
        if (!readKey) {
            reject(response, HttpStatus.UNAUTHORIZED, "API key ausente o no valida (cabecera " + HEADER + ")");
        } else if (!READ_METHODS.contains(request.getMethod().toUpperCase())) {
            reject(response, HttpStatus.FORBIDDEN, "La clave presentada es de solo lectura");
        } else {
            chain.doFilter(request, response);
        }
    }

    private void reject(HttpServletResponse response, HttpStatus status, String message) throws IOException {
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        objectMapper.writeValue(response.getOutputStream(),
                ApiError.of(status.value(), status.getReasonPhrase(), message));
    }
}
