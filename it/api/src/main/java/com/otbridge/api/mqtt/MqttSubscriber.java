package com.otbridge.api.mqtt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.otbridge.api.config.MqttProperties;
import com.otbridge.api.dto.TelemetrySample;
import com.otbridge.api.service.AlarmService;
import com.otbridge.api.service.MachineService;
import com.otbridge.api.service.SensorService;
import jakarta.annotation.PreDestroy;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * Suscriptor MQTT de la API.
 *
 * <p>Un unico {@link MqttClient} para toda la vida de la aplicacion: la primera conexion se reintenta desde
 * {@link #ensureConnected()} y, una vez conectado, paho reconecta solo ({@code automaticReconnect}). Crear un
 * cliente nuevo con el mismo clientId mientras el anterior reconecta provocaba "session taken over" y fugas.
 *
 * <p>El trabajo de base de datos se hace fuera del hilo de paho, en un ejecutor de un hilo (conserva el
 * orden de los eventos) con cola acotada, para no bloquear la recepcion ni agotar memoria.
 */
@Component
public class MqttSubscriber {

    private static final Logger log = LoggerFactory.getLogger(MqttSubscriber.class);

    private static final String TOPIC_TELEMETRY = "factory/+/telemetry/#";
    private static final String TOPIC_STATUS = "factory/+/status";
    private static final String TOPIC_ALARMS = "factory/alarms/events";
    private static final int QUEUE_CAPACITY = 1_000;

    private final ObjectMapper objectMapper;
    private final MqttProperties properties;
    private final MachineService machineService;
    private final SensorService sensorService;
    private final AlarmService alarmService;

    private final Map<String, TelemetrySample> telemetryBuffer = new ConcurrentHashMap<>();
    /** Las suscripciones se hacen fuera del hilo de callbacks de paho: un subscribe bloqueante dentro de
     *  connectComplete se interbloquea con la cola que el broker entrega al reconectar una sesion persistente. */
    private final ExecutorService subscriber = Executors.newSingleThreadExecutor(r -> new Thread(r, "mqtt-subscribe"));
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(QUEUE_CAPACITY), runnable -> new Thread(runnable, "mqtt-worker"),
            (runnable, executor) -> log.warn("Cola de eventos MQTT llena: evento descartado"));
    private volatile MqttClient client;
    /** Tras la primera conexion la reconexion es de paho: no se vuelve a llamar a connect(). */
    private volatile boolean connectedOnce;

    public MqttSubscriber(ObjectMapper objectMapper,
                          MqttProperties properties,
                          MachineService machineService,
                          SensorService sensorService,
                          AlarmService alarmService) {
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.machineService = machineService;
        this.sensorService = sensorService;
        this.alarmService = alarmService;
    }

    /** Primera conexion con reintento; despues la reconexion es automatica y este metodo no hace nada. */
    @Scheduled(initialDelay = 3_000, fixedDelay = 15_000)
    public synchronized void ensureConnected() {
        if (connectedOnce) {
            return;
        }
        try {
            if (client == null) {
                client = new MqttClient(properties.broker(), properties.clientId(), new MemoryPersistence());
                client.setCallback(new Callback());
            }
            client.connect(connectOptions());
            connectedOnce = true;
        } catch (MqttException ex) {
            log.warn("MQTT no disponible en {} ({}); reintento en 15 s", properties.broker(), ex.getMessage());
        }
    }

    private MqttConnectOptions connectOptions() {
        MqttConnectOptions options = new MqttConnectOptions();
        // sesion persistente: con un unico cliente es seguro, y el broker guarda los eventos QoS 1 mientras
        // la API esta desconectada (reinicio del broker o de la API) en vez de perderlos
        options.setCleanSession(false);
        options.setAutomaticReconnect(true);
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(60);
        if (properties.user() != null && !properties.user().isBlank()) {
            options.setUserName(properties.user());
            options.setPassword(properties.pass() == null ? new char[0] : properties.pass().toCharArray());
        }
        return options;
    }

    private final class Callback implements MqttCallbackExtended {
        @Override
        public void connectComplete(boolean reconnect, String serverURI) {
            subscriber.execute(() -> {
                try {
                    // telemetria y estado: QoS 0 (solo importa el ultimo valor; el broker no los acumula mientras
                    // la API esta desconectada). Eventos de alarma: QoS 1 (se guardan en la sesion persistente).
                    client.subscribe(new String[]{TOPIC_TELEMETRY, TOPIC_STATUS, TOPIC_ALARMS}, new int[]{0, 0, 1});
                    log.info("MQTT conectado a {} y suscrito (reconexion={})", serverURI, reconnect);
                } catch (MqttException ex) {
                    log.error("Fallo al suscribir topics MQTT", ex);
                }
            });
        }

        @Override
        public void connectionLost(Throwable cause) {
            log.warn("Conexion MQTT perdida ({}); reconexion automatica", cause.getMessage());
        }

        @Override
        public void messageArrived(String topic, MqttMessage message) {
            byte[] payload = message.getPayload();
            if (topic.contains("/telemetry/")) {
                bufferTelemetry(topic, payload);      // barato: solo actualiza un mapa
            } else {
                worker.execute(() -> handleEvent(topic, payload));
            }
        }

        @Override
        public void deliveryComplete(IMqttDeliveryToken token) {
        }
    }

    private void bufferTelemetry(String topic, byte[] payload) {
        try {
            TelemetryPayload telemetry = objectMapper.readValue(payload, TelemetryPayload.class);
            if (telemetry.q() != 1) {
                return;
            }
            telemetryBuffer.put(telemetry.plc() + "|" + telemetry.variable(), new TelemetrySample(
                    telemetry.plc(), telemetry.variable(), telemetry.value(), Instant.ofEpochSecond(telemetry.ts())));
        } catch (Exception ex) {
            log.warn("Telemetria descartada en {}: {}", topic, ex.getMessage());
        }
    }

    private void handleEvent(String topic, byte[] payload) {
        try {
            if (topic.endsWith("/status")) {
                StatusPayload status = objectMapper.readValue(payload, StatusPayload.class);
                // el LWT llega con ts=0 (caida brusca): se registra offline con la hora de recepcion
                Instant ts = status.ts() > 0 ? Instant.ofEpochSecond(status.ts()) : Instant.now();
                machineService.updateStatus(status.plc(), status.online(), ts);
            } else if (TOPIC_ALARMS.equals(topic)) {
                AlarmEventPayload event = objectMapper.readValue(payload, AlarmEventPayload.class);
                alarmService.processEvent(event.plc(), event.variable(), event.severity(), event.state(),
                        event.message(), event.code(), Instant.ofEpochSecond(event.ts()));
            }
        } catch (Exception ex) {
            log.warn("Mensaje MQTT descartado en {}: {}", topic, ex.getMessage());
        }
    }

    @Scheduled(fixedRate = 1_000)
    public void flushTelemetry() {
        if (telemetryBuffer.isEmpty()) {
            return;
        }
        List<TelemetrySample> batch = new ArrayList<>(telemetryBuffer.values());
        telemetryBuffer.clear();
        worker.execute(() -> sensorService.writeTelemetry(batch));
    }

    @PreDestroy
    public void shutdown() {
        worker.shutdown();
        subscriber.shutdown();
        try {
            if (client != null) {
                if (client.isConnected()) {
                    client.disconnect();
                }
                client.close();
            }
        } catch (MqttException ex) {
            log.debug("Error al cerrar cliente MQTT", ex);
        }
    }
}
