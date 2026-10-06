# Mapa de registros Modbus — OT-Bridge

Contrato de interfaz entre la capa de campo (simulador Python) y el nivel de
control (PLC). Cualquier cliente Modbus que se conecte al sistema debe
atenerse a este documento.

Los valores aquí descritos se corresponden con las constantes definidas en
`ot/field/config.py`. Si se modifica una, debe actualizarse este documento.

---

## Dispositivos

| Dispositivo | Puerto | Unit ID | Espacio Modbus | Acceso | Equivale a |
|---|---|---|---|---|---|
| Sensores  | 5020 | 1 | Input Registers (FC 04) | Solo lectura | Tarjetas de entrada |
| Actuadores | 5021 | 1 | Holding Registers (FC 03/06/16) | Lectura/escritura | Tarjetas de salida |
| Simulación | 5022 | 1 | Holding (FC 03/06/16) + Input (FC 04) | Mixto | Estación de instructor (no existe en planta real) |

**Host de escucha:** variable `OTB_FIELD_BIND`. En el contenedor `otb-field-simulator` es `0.0.0.0`, alcanzable
solo dentro de la red Docker de la zona OT. Ejecutado fuera de Docker, por defecto `127.0.0.1`.

**Direccionamiento del cliente:**
- PLC y SCADA (en la red `otb-ot`): `field-simulator`
- Simulador ejecutado en el propio equipo (`python ot/field/main.py`): `127.0.0.1`

### Por qué dos espacios de direcciones distintos

Los sensores se exponen como *input registers* porque el protocolo Modbus los
define como solo lectura: no existe función de escritura sobre ellos. Un
cliente no puede modificar una medida, igual que no se puede cambiar la
temperatura de una sala escribiendo en el termómetro.

Los actuadores se exponen como *holding registers* porque deben admitir
escritura: es por ahí por donde el PLC envía sus órdenes.

Esta separación no es una convención del proyecto, es semántica del protocolo.

---

## Sensores — puerto 5020 (Input Registers, FC 04)

| Dir. | Nombre | Transmitido | Rango válido | Unidad de ingeniería |
|---|---|---|---|---|
| 0 | Nivel del depósito | mA × 100 | 400–2000 | 0–1000 L |
| 1 | Caudal de entrada | mA × 100 | 400–2000 | 0–150 lpm |
| 2 | Caudal de salida | mA × 100 | 400–2000 | 0–150 lpm |
| 3 | Confirmación de marcha de bomba | booleano | 0 / 1 | 0 = parada, 1 = confirmada |
| 4 | Seta de emergencia | booleano | 0 / 1 | 0 = libre, 1 = pulsada |
| 5 | Velocidad real de bomba | porcentaje | 0–100 | 0–100 % |

### Conversión de señales analógicas (registros 0, 1, 2)

**Registro → corriente:**
```
mA = registro / 100
```

**Corriente → unidad de ingeniería:**
```
valor = ((mA - 4.0) / 16.0) × (max_rango - min_rango) + min_rango
```

**Ejemplo (registro de nivel):**
```
registro 1142  →  11.42 mA  →  ((11.42 - 4) / 16) × 1000 = 463.75 L
```

### Diagnóstico de instrumentación

Las señales analógicas siguen el estándar 4-20 mA con *live zero*: el extremo
inferior del rango de medida es 4 mA, no 0 mA. Esto permite distinguir una
medida válida de un fallo de instrumentación.

| Corriente leída | Interpretación | Acción esperada del PLC |
|---|---|---|
| < 3.5 mA (registro < 350) | Cable cortado o sensor sin alimentación | Enclavamiento por fallo de sensor |
| 3.5 – 4.0 mA | Zona de tolerancia del extremo inferior | Tratar como 0 % de rango |
| 4.0 – 20.0 mA | Medida válida | Operación normal |
| 20.0 – 20.5 mA | Zona de tolerancia del extremo superior | Tratar como 100 % de rango |
| > 20.5 mA (registro > 2050) | Cortocircuito en el lazo | Enclavamiento por fallo de sensor |

**Importante:** un valor de 0 mA NO significa "depósito vacío". Significa
"no hay señal". Un PLC que no compruebe el rango antes de escalar
interpretaría un cable roto como depósito vacío y arrancaría la bomba en
seco.

Los márgenes de 3.5 y 20.5 mA (en lugar de 4.0 y 20.0 exactos) absorben la
tolerancia y el ruido propios de un transmisor real, evitando alarmas falsas
en los extremos del rango.

---

## Actuadores — puerto 5021 (Holding Registers, FC 03/06/16)

| Dir. | Nombre | Transmitido | Rango | Significado |
|---|---|---|---|---|
| 0 | Comando de marcha de bomba | booleano | 0 / 1 | 0 = parar, 1 = arrancar |
| 1 | Consigna de velocidad de bomba | porcentaje | 0–100 | 0–100 % |
| 2 | Comando de válvula de salida | booleano | 0 / 1 | 0 = cerrada, 1 = abierta |

Los registros de actuadores no llevan escalado 4-20 mA: representan órdenes
digitales y consignas porcentuales, no medidas de campo.

### Comando frente a confirmación

El registro 0 de actuadores (comando) y el registro 3 de sensores
(confirmación) son variables distintas y deben tratarse como tales.

El PLC ordena la marcha escribiendo en el comando, pero no debe dar por hecho
que la bomba ha arrancado: debe esperar la confirmación de retorno. Si tras el
retardo esperado la confirmación no llega, se trata de un fallo de arranque
(contactor quemado, pegado o sin alimentación).

Retardo de confirmación en el simulador: definido en `CONTACTOR_CONFIRM_DELAY_S`.

---

## Simulación — puerto 5022 (estación de instructor)

Interfaz exclusiva del simulador para inyectar fallos y observar la física
real. **No existe en una planta real y el PLC no la consume**: la usa FUXA
(dispositivo `SIM_Campo`, vista "Simulador") y el teclado de `ot/field/main.py`.
Los registros de fallos son la fuente de verdad: teclado y SCADA escriben en
ellos, por lo que siempre están sincronizados.

### Mandos — Holding Registers (FC 03/06/16)

| Dir. | Nombre | Rango | Significado |
|---|---|---|---|
| 0 | Fallo bomba averiada | 0 / 1 | 1 = inyectado |
| 1 | Fallo cable de nivel cortado | 0 / 1 | 1 = inyectado |
| 2 | Fallo cortocircuito de nivel | 0 / 1 | 1 = inyectado |
| 3 | Fallo contactor sin confirmación | 0 / 1 | 1 = inyectado |
| 4 | Seta de emergencia de campo | 0 / 1 | 1 = pulsada |
| 5 | Quitar todos los fallos | pulso | 1 → el simulador pone 0–5 a 0 |
| 6 | Nivel a forzar | 0–1000 | litros |
| 7 | Aplicar nivel forzado | pulso | 1 → el nivel salta al valor de dir. 6; vuelve a 0 |

### Verdad física — Input Registers (FC 04)

| Dir. | Nombre | Transmitido | Unidad |
|---|---|---|---|
| 0 | Nivel real del depósito | valor × 10 | L |
| 1 | Caudal de entrada real | valor × 10 | lpm |
| 2 | Caudal de salida real | valor × 10 | lpm |
| 3 | Caudal de desbordamiento | valor × 10 (máx. 32767) | lpm |
| 4 | Velocidad real de bomba | porcentaje | % |
| 5 | Contactor confirmado | booleano | 0 / 1 |
| 6 | Orden de marcha recibida en campo | booleano | 0 / 1 |
| 7 | Consigna de velocidad recibida | porcentaje | % |
| 8 | Orden de válvula recibida | booleano | 0 / 1 |
| 9 | Fallos activos | bitmask | 1 bomba, 2 cable, 4 corto, 8 contactor, 16 seta |
| 10 | Señal de nivel enviada al PLC | mA × 100 | igual que sensor reg 0 |

Estos registros **no** usan 4-20 mA: son la verdad del modelo, no una medida
de instrumentación. Comparar el nivel real (dir. 0) con el del PLC es lo que
permite ver el efecto de un fallo de sensor.

---

## Fallos inyectables desde el simulador

Disponibles por teclado en la consola de `ot/field/main.py` y desde la vista
"Simulación" de FUXA (registros 0–5 del puerto 5022), para verificar el
comportamiento del PLC ante averías. La tecla `0` quita todos los fallos.

| Tecla | Fallo | Efecto observable |
|---|---|---|
| 1 | Bomba averiada | La bomba no da caudal aunque reciba orden de marcha |
| 2 | Cable de sensor de nivel cortado | Registro 0 de sensores pasa a 0 |
| 3 | Cortocircuito en sensor de nivel | Registro 0 de sensores supera 2050 |
| 4 | Contactor sin confirmación | Registro 3 de sensores permanece en 0 pese al comando |
| 5 | Seta de emergencia pulsada | Registro 4 de sensores pasa a 1; la bomba se detiene |

El fallo de cable cortado afecta únicamente al sensor de nivel. Los sensores
de caudal siguen reportando con normalidad, ya que se trata de instrumentos
independientes con lazos de señal separados.

---

## Consideraciones de escalado del proyecto

Al ampliar a varias máquinas, cada una dispondrá de su propio par de
dispositivos Modbus en puertos distintos, manteniendo la misma estructura de
registros. La convención de escalado (mA × 100) se mantiene constante en todo
el sistema.

El PLC expone además su estado procesado como servidor Modbus (`:502`,
`%MW100..%MW111`) para el SCADA y el gateway OT→IT. Ese mapa está en
[mqtt-contract.md §5](mqtt-contract.md#5-registros-modbus-de-origen-y-escalado-plc-plc01-unit_id-1).
