# Seguridad — OT-Bridge

Defensa en profundidad según **IEC 62443** (zonas y conductos). Este documento recoge los controles
implementados, el modelo de amenazas, los riesgos aceptados y el roadmap.

## 1. Modelo de amenazas (resumen)

| Activo | Amenaza | Control principal |
|---|---|---|
| Lógica y mando del PLC | Escritura no autorizada por Modbus (sin autenticación) | Segmentación + firewall de origen; IT nunca escribe en el PLC (gateway solo FC03) |
| Arranque de la planta | El PLC pasa a RUN al reiniciarse con un programa antiguo | El runtime arranca **sin programa**: solo un despliegue explícito desde el Editor lo pone en marcha |
| Operación desde el SCADA | Operador no autorizado | Autenticación JWT, roles (visitante, operador, supervisor), confirmación en mandos críticos |
| Bus de datos IT | Suplantación de un servicio o inyección de alarmas | Un usuario MQTT por servicio, ACL de mínimo privilegio, sin anónimos |
| Históricos y BBDD | Lectura o borrado indebido | Usuarios por rol en InfluxDB y PostgreSQL; Grafana con rol de solo lectura |
| API REST | Uso indebido de endpoints de escritura | API key por cliente con permisos distintos (lectura / operador), comparación en tiempo constante |
| Secretos | Fuga en el repositorio, logs o backups | `.env` fuera de git, generado con valores aleatorios; escaneo de secretos en CI y pre-commit |
| Contenedores | Escalada de privilegios | No-root, `no-new-privileges`, `cap_drop: ALL`, imágenes fijadas, límites de memoria |

## 2. Controles implementados

| Área | Control | Dónde |
|---|---|---|
| **Red** | Todos los puertos IT publicados solo en `127.0.0.1`; `1883` en la LAN únicamente si se define `MQTT_LAN_BIND` | `it/docker-compose.yml` |
| | Puertos OT en loopback por defecto (`FUXA_BIND`, `MODBUS_BIND` para abrirlos de forma explícita) | `ot/scada/docker-compose.yml` |
| | Reglas de firewall de origen para Modbus `502` y MQTT `1883` en despliegue separado | [network.md](network.md) |
| **PLC** | Arranque seguro: el programa compilado se elimina en cada arranque del runtime | `ot/scada/docker-compose.yml` |
| | Seguridades con prioridad sobre cualquier mando: seta, fallo de sensor (NAMUR), fallo de arranque (contactor) | `ot/plc/pous/programs/main.st` |
| **SCADA** | Autenticación y roles; el build del HMI **rechaza** cualquier mando sin permiso | `ot/scada/hmi/` |
| | Credenciales MQTT de FUXA en su almacén de seguridad, nunca dentro del proyecto exportable | `ot/scada/hmi/deploy.py` |
| **MQTT** | `allow_anonymous false`, un usuario por servicio, ACL de lectura/escritura por topic | `it/mosquitto/config/` |
| | `passwd` regenerado y validado por script desde `.env`, recarga en caliente | `it/scripts/mqtt_passwd.py` |
| **Datos** | InfluxDB con autenticación: `admin`, escritura (historian) y lectura (Grafana, API, backup) | `it/scripts/influx_users.py` |
| | PostgreSQL: rol `grafana_ro` con `SELECT` y nada más | `it/scripts/postgres_roles.py` |
| **API** | API key por cliente; perfil `prod` sin Swagger; DTOs, validación y errores 4xx controlados; CORS restrictivo | `it/api/` |
| **OPC UA** | `Basic256Sha256` Sign & Encrypt + usuario; sin acceso anónimo | `it/opcua-server/` |
| **Contenedores** | No-root, `no-new-privileges`, `cap_drop: ALL` (+ `cap_add` mínimo), healthchecks, límites de memoria, rotación de logs | `it/docker-compose.yml` |
| **Suministro** | Imágenes fijadas por versión o digest; dependencias Python con `==` y Maven con versión | compose, `requirements.txt`, `pom.xml` |
| **Secretos** | `.env` gitignored; `ensure_secrets.py` genera valores aleatorios y sustituye los marcadores de la plantilla sin imprimirlos | `it/scripts/ensure_secrets.py` |
| **Backups** | Sin secretos (`.env` y `passwd` excluidos), con `manifest.sha256` y prueba de restauración aislada | `it/scripts/backup.ps1`, `restore_test.ps1` |
| **Repositorio** | gitleaks en pre-commit y en CI, Trivy sobre configuración e imágenes, Dependabot | `.pre-commit-config.yaml`, `.github/` |

## 3. Riesgos aceptados

Riesgos conocidos y asumidos para un entorno de laboratorio, con su mitigación:

1. **MQTT sin TLS.** Las credenciales viajan en claro en la LAN cuando FUXA está en otro host. Mitigación: usuario `fuxa` de solo lectura y firewall de origen. Roadmap: TLS en `8883`.
2. **API y Grafana por HTTP** en `127.0.0.1`. Aceptable mientras no se expongan en la LAN.
3. **Modbus TCP sin autenticación** (limitación del protocolo). Mitigación: segmentación, firewall de origen y lectura estricta FC03 desde IT.
4. **OPC UA acepta cualquier certificado de cliente** (cifra el canal y autentica al usuario). Roadmap: lista de confianza.
5. **FUXA 1.3.4 no comprueba el grupo del usuario en las escrituras** (solo que esté autenticado; el filtrado por rol lo hace la interfaz). Mitigación: cuentas nominales, sin escritura para invitados y seguridades en el PLC.
6. **`.env` sin cifrar en disco.** Roadmap: Docker secrets.
7. **Claves de API sin caducidad.** Se rotan cambiándolas en `.env` y recreando los servicios afectados.

## 4. Lecciones aprendidas

Hallazgos reales durante el desarrollo, corregidos y convertidos en controles:

- **Una regla Allow no basta frente a Docker Desktop.** Docker añade su propia regla Allow genérica al publicar un puerto: hace falta una regla **Block** explícita para el resto de orígenes.
- **Docker Desktop reescribe la IP de origen** del tráfico que entra en un contenedor: el filtrado por origen debe hacerse en el firewall del host, no dentro del contenedor.
- **El testamento MQTT (LWT) de una caída brusca llega con `ts = 0`** y envenenaba el búfer del historian. Ahora se descarta como punto y se trata como pérdida de comunicación.
- **El proyecto exportable de un SCADA no debe contener credenciales.** La primera versión guardaba la contraseña MQTT dentro del proyecto de FUXA, servido por su API. Se movió al almacén de seguridad y se rotó.
- **Un PLC que arranca solo es un riesgo de proceso.** El runtime pasaba a RUN al reiniciar el contenedor con el último programa: ahora arranca vacío.
- **Usuarios compartidos rompen el mínimo privilegio.** OPC UA y el gemelo digital compartían usuario MQTT, lo que permitía al servidor OPC UA publicar alarmas: ahora cada servicio tiene el suyo.

## 5. Roadmap de seguridad

- TLS en MQTT (`8883`) y en API/Grafana.
- Lista de confianza de certificados de cliente en OPC UA.
- Docker secrets en lugar de `.env` plano y rotación periódica de claves.
- Conducto OT→IT con proxy unidireccional (data diode) si el proyecto crece.

## 6. Notificar una vulnerabilidad

Consulta [SECURITY.md](../SECURITY.md).
