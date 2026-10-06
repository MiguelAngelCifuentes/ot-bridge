<div align="center">

# Instalación de OT-Bridge

**Un comando · 13 servicios · una planta industrial completa funcionando en tu equipo**

[Requisitos](#1-requisitos) ·
[Instalación](#2-instalación-en-3-comandos) ·
[Primeros pasos](#4-primeros-pasos) ·
[Operación](#5-operación-diaria) ·
[OpenPLC Editor](#6-trabajar-con-el-plc-desde-openplc-editor) ·
[Problemas frecuentes](#9-solución-de-problemas)

</div>

---

OT-Bridge se instala con un único script, `otb.py`, que **comprueba los requisitos, genera todos los secretos,
construye y arranca los 13 servicios, carga el programa en el PLC, despliega el SCADA y verifica el sistema de
extremo a extremo**. No necesitas instalar OpenPLC Editor, FUXA, Grafana ni ninguna librería de Python: todo
corre en contenedores.

> [!TIP]
> ¿Solo quieres verlo funcionando? Ve directamente al [paso 2](#2-instalación-en-3-comandos). En unos minutos
> tendrás la planta en marcha, con el SCADA y los dashboards llenándose de datos en tiempo real.

## 1. Requisitos

| Requisito | Versión | Cómo comprobarlo | Dónde conseguirlo |
|---|---|---|---|
| **Docker** con Compose v2 | Docker Desktop 4.x o Docker Engine 24+ | `docker compose version` | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| **Python** | 3.10 o superior | `python --version` | [python.org/downloads](https://www.python.org/downloads/) |
| **Git** | cualquiera | `git --version` | [git-scm.com](https://git-scm.com/downloads) |
| **Memoria para Docker** | 4 GB o más | Docker Desktop → *Settings → Resources* | — |
| **Disco** | ~10 GB libres | — | imágenes (~6 GB) y servicios construidos |
| **Internet** | solo en la primera instalación | — | descarga de imágenes y del driver Modbus de FUXA |

**Sistemas:** Windows 10/11 y Linux probados (Linux en cada ejecución de la CI). Todas las imágenes son
multiarquitectura (`amd64` y `arm64`), así que macOS con Apple Silicon debería funcionar, aunque no se ha probado.

> [!IMPORTANT]
> Docker tiene que estar **arrancado** antes de instalar. En Windows y macOS, abre Docker Desktop y espera a que
> indique *Engine running*.

## 2. Instalación en 3 comandos

```bash
git clone https://github.com/MiguelAngelCifuentes/ot-bridge.git
cd ot-bridge
python otb.py install
```

> [!NOTE]
> Según tu sistema, el comando de Python puede ser `python`, `python3` (Linux y macOS) o `py` (Windows).

La primera vez tarda **entre 5 y 15 minutos**, según tu conexión: hay que descargar las imágenes, construir
los servicios y compilar el programa del PLC. Las siguientes, menos de un minuto. Al terminar verás algo así:

```text
[1/7] Comprobando requisitos
      OK   Python 3.11.9
      OK   Docker 27.3.1 en marcha
      OK   Docker Compose 2.29.7
      OK   Puertos locales disponibles

[2/7] Secretos y credenciales
      OK   it/.env completo con secretos aleatorios
      OK   Usuarios del broker MQTT generados (uno por servicio)

[3/7] Capa OT: simulador de planta, PLC y SCADA
      OK   Capa OT: 3 servicios en marcha y sanos

[4/7] Capa IT: broker, historico, API, alarmas, gemelo, OPC UA y dashboards
      OK   Capa IT: 10 servicios en marcha y sanos

[5/7] Programa del PLC
      OK   PLC compilado y en RUN

[6/7] SCADA: proyecto generado desde codigo, seguridad y estacion de instructor
      OK   Driver Modbus de FUXA (modbus-serial) instalado
      OK   Proyecto FUXA desplegado (13 vistas)
      OK   Usuarios por rol y autenticacion activados
      OK   Vista Simulador (estacion de instructor) anadida

[7/7] Verificacion de extremo a extremo
      OK   SCADA con datos en vivo del PLC y del simulador
      OK   RESULTADO: 23/23 OK

OT-Bridge en marcha

  SCADA FUXA        http://localhost:1881
  Grafana           http://localhost:3000
  ...
```

> [!TIP]
> El instalador es **idempotente**: si algo falla (Docker parado, un puerto ocupado, un corte de red), corrige el
> problema y vuelve a ejecutar `python otb.py install`. Retoma sin perder nada. El registro completo de cada
> ejecución queda en `.otb/`.

## 3. Qué hace el instalador

| Paso | Qué ocurre | Por qué |
|:---:|---|---|
| **1** | Comprueba Python, Docker, Compose, la memoria y los puertos locales | Falla pronto y con un mensaje claro, antes de tocar nada |
| **2** | Crea `it/.env` y genera **22 secretos aleatorios**; crea un usuario MQTT por servicio | Ninguna instalación comparte contraseñas y no hay credenciales por defecto |
| **3** | Arranca la zona OT: simulador de planta, PLC y SCADA | Capa de control, aislada en su propia red Docker |
| **4** | Construye y arranca los 10 servicios IT y espera a que estén *healthy* | El orden de arranque lo gestionan los healthchecks |
| **5** | Crea la cuenta del runtime del PLC, sube el programa, lo compila y lo pone en RUN | Arranque explícito ([ADR 0004](docs/adr/0004-arranque-seguro-del-plc.md)) |
| **6** | Instala el driver Modbus de FUXA, despliega el SCADA generado desde código, activa los roles y añade la estación de instructor | El HMI se versiona como código ([ADR 0003](docs/adr/0003-hmi-y-dashboards-como-codigo.md)) |
| **7** | Comprueba que el SCADA recibe datos en vivo y ejecuta la prueba de extremo a extremo | Confirma que todo funciona, no solo que arrancó |

## 4. Primeros pasos

### Accesos

| Herramienta | Dirección | Usuario |
|---|---|---|
| **SCADA FUXA** | <http://localhost:1881> | `operador` para operar · `supervisor` para todo · `visitante` solo lectura |
| **Grafana** | <http://localhost:3000> | `admin` |
| **API REST** | <http://localhost:8080/api/machines> | cabecera `X-API-Key` |
| **OPC UA** | `opc.tcp://localhost:4840` | `otbridge` (Basic256Sha256 Sign & Encrypt) |
| **OpenPLC runtime** | `https://localhost:8443` | `otb-admin` (lo usa OpenPLC Editor) |

Las contraseñas son aleatorias y únicas de tu instalación. Para verlas:

```bash
python otb.py credentials          # usuarios (contraseñas ocultas)
python otb.py credentials --show   # con las contraseñas
```

### Un recorrido de 5 minutos

1. **FUXA → Visión general.** Entra como `operador`: verás el depósito llenándose y vaciándose solo. El PLC arranca
   la bomba en 300 L y la para en 900 L.
2. **FUXA → Proceso.** El P&ID vivo: tuberías animadas, caudales y estado de cada equipo.
3. **FUXA → Simulador.** Entra como `supervisor` y pulsa **INYECTAR** en *Cable LT-101 cortado*. Observa cómo el
   PLC detecta el fallo (NAMUR), para la bomba y cierra el consumo, y cómo salta la alarma. Pulsa
   **QUITAR TODOS LOS FALLOS** para recuperar la planta.
4. **Grafana → 00 · Visión general.** La misma planta vista desde IT: KPIs, gemelo digital y alarmas, con el
   episodio del fallo registrado.
5. **Grafana → 02 · Alarmas.** El ciclo de vida de la alarma que acabas de provocar, con sus tiempos MTTA y MTTR.

## 5. Operación diaria

| Comando | Para qué |
|---|---|
| `python otb.py status` | Estado de los 13 servicios y direcciones de acceso |
| `python otb.py stop` | Para la plataforma; los datos se conservan |
| `python otb.py start` | La vuelve a arrancar y recarga el programa del PLC |
| `python otb.py deploy-plc` | Recarga el programa del PLC (por ejemplo, tras reiniciar solo su contenedor) |
| `python otb.py credentials [--show]` | Usuarios y contraseñas |
| `python otb.py install` | Actualiza tras un `git pull` y lo verifica todo de nuevo |
| `python otb.py uninstall [--volumes \| --all]` | Desinstala ([detalle](#10-desinstalación)) |

Pruebas y diagnóstico avanzado: [docs/runbook.md](docs/runbook.md) y [docs/validation.md](docs/validation.md).

## 6. Trabajar con el PLC desde OpenPLC Editor

No hace falta para usar la plataforma, pero sí para **modificar la lógica del PLC**.

1. Instala [OpenPLC Editor v4](https://autonomylogic.com/).
2. Abre la carpeta `ot/plc`. El programa está en `pous/programs/main.st`.
3. Conecta con el runtime en `https://localhost:8443`, con el usuario `otb-admin` y la contraseña de
   `python otb.py credentials --show`.
4. Edita y pulsa **Build**: el Editor compila, sube el programa y pone el PLC en RUN.

> [!NOTE]
> Por seguridad, **el PLC arranca siempre vacío** cuando se reinicia su contenedor: solo un despliegue explícito
> lo pone en marcha. Hazlo con *Build* en el Editor o con `python otb.py deploy-plc`. Si cambias el programa y
> quieres que `otb.py` despliegue tu versión, copia la salida de *Build* (`build/OpenPLC Runtime v4/src`) en
> `ot/plc/dist/runtime-v4`.

## 7. Seguridad de la instalación

- **Nada queda expuesto a la red.** Todas las interfaces se publican solo en `127.0.0.1`. Los puertos Modbus del
  simulador (`5020`-`5022`) y del PLC (`502`) ni siquiera salen de la red Docker de la zona OT.
- **Sin contraseñas por defecto.** Cada instalación genera las suyas. Compose **se niega a arrancar** si falta
  alguna.
- **`it/.env` nunca se sube al repositorio** (está en `.gitignore`); en Linux y macOS queda con permisos `600`.
- **Roles en el SCADA y mínimo privilegio en MQTT, bases de datos, API y OPC UA.**

Antes de abrir algo a tu red local (por ejemplo, el SCADA con `FUXA_BIND`), lee
[docs/security.md](docs/security.md) y [docs/network.md](docs/network.md).

## 8. OT e IT en hosts separados

La topología realista, con el PLC y el SCADA en un equipo y la capa IT en otro, unidos por un conducto de solo
lectura con firewall, está descrita paso a paso en **[docs/deployment.md](docs/deployment.md)**.

## 9. Solución de problemas

<details>
<summary><b>«Docker esta instalado pero no responde»</b></summary>

Docker Desktop no está arrancado o no ha terminado de iniciarse. Ábrelo, espera a *Engine running* y repite
`python otb.py install`. En Linux: `sudo systemctl start docker`, y añade tu usuario al grupo `docker` para no
usar `sudo` (`sudo usermod -aG docker $USER`, cerrar sesión y volver a entrar).
</details>

<details>
<summary><b>«Estos puertos locales estan ocupados por otro programa»</b></summary>

Otro programa usa alguno de los puertos `1881`, `1883`, `3000`, `4840`, `8080`, `8086` u `8443`; los más
habituales son otro Grafana (`3000`) u otra aplicación web (`8080`). Ciérralo o para su contenedor y repite.
Para ver quién lo usa: `netstat -ano | findstr :3000` en Windows, o `sudo lsof -i :3000` en Linux y macOS.
</details>

<details>
<summary><b>La primera instalación tarda mucho o se corta</b></summary>

La primera vez se descargan las imágenes base (unos 6 GB en disco una vez descomprimidas) y se construyen 7 servicios. Si se corta la conexión,
vuelve a ejecutar `python otb.py install`: retoma desde donde estaba. Detrás de un proxy corporativo, configura
el proxy en Docker Desktop (*Settings → Resources → Proxies*).
</details>

<details>
<summary><b>El SCADA abre pero muestra «???» o «SIN DATOS»</b></summary>

El PLC no está en RUN, normalmente porque se reinició su contenedor. Ejecuta `python otb.py deploy-plc`. Si
persiste, `python otb.py install` vuelve a comprobarlo todo, incluido el driver Modbus de FUXA.
</details>

<details>
<summary><b>He olvidado una contraseña</b></summary>

`python otb.py credentials --show`. Están en `it/.env`; no las borres mientras la instalación exista.
</details>

<details>
<summary><b>«El runtime ya tiene usuarios y OPENPLC_USER/OPENPLC_PASSWORD no coinciden»</b></summary>

El volumen del runtime conserva una cuenta de una instalación anterior con otro `it/.env`. Pon esas credenciales
en `it/.env` o reinicia la instalación con `python otb.py uninstall --volumes` y `python otb.py install`
(borra también el histórico).
</details>

<details>
<summary><b>Windows: Docker se queda sin memoria</b></summary>

Con WSL 2, la memoria se configura en `%UserProfile%\.wslconfig` (por ejemplo, `memory=6GB`). Después ejecuta
`wsl --shutdown` y reinicia Docker Desktop.
</details>

<details>
<summary><b>Ver qué está fallando</b></summary>

```bash
python otb.py status                       # qué servicio no está sano
docker logs --tail 50 otb-<servicio>       # p. ej. otb-gateway, otb-openplc, otb-fuxa
```

El registro completo de la última ejecución está en `.otb/`. Si abres un issue, adjunta la parte relevante:
**los registros no contienen contraseñas**.
</details>

## 10. Desinstalación

| Comando | Qué elimina | Cuándo usarlo |
|---|---|---|
| `python otb.py uninstall` | Contenedores y redes. **Conserva** datos, imágenes y contraseñas | Liberar memoria; volver con `python otb.py start` |
| `python otb.py uninstall --volumes` | Lo anterior **y los datos**: histórico, bases de datos, proyecto SCADA y cuenta del PLC | Empezar de cero manteniendo las imágenes descargadas |
| `python otb.py uninstall --all` | **Todo**: lo anterior, las imágenes de Docker (~7 GB), `it/.env`, el `passwd` de MQTT, las copias del SCADA y los registros | Dejar el equipo como antes de instalar |

`--all` muestra exactamente qué va a borrar y pide escribir `BORRAR` para confirmar. Nunca elimina una imagen que
use otro contenedor de tu equipo, y no toca el código del repositorio. Al terminar, solo queda borrar la carpeta:

```bash
python otb.py uninstall --all
cd .. && rm -rf ot-bridge          # Windows: rmdir /s /q ot-bridge
```

> [!NOTE]
> Ninguna desinstalación toca contenedores, imágenes en uso ni volúmenes de otros proyectos. Si detectara que ha
> desaparecido algún contenedor ajeno durante una operación, lo avisaría por su nombre.

---

<div align="center">
<sub>¿Algo no funciona como se describe aquí? Abre un <a href="../../issues">issue</a>. Para vulnerabilidades,
sigue <a href="SECURITY.md">SECURITY.md</a>.</sub>
</div>
