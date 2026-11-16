# JOE HQ — Cierre de v1 local

Actualización: 15/11/2026, 23:40. **App 0.3.2 corriendo en `http://127.0.0.1:8787`.** Rama GitHub `joe-hq`.

Alcance aceptado por Joe (sin cambios): una pantalla compartida, un bot a la vez, modos Solo ver / Paso a paso; `message_agent` de Hermes con entrega por JOE HQ; Guardián y Casa Kiraz bloqueados para mensajes y tareas directos; Holding se comunica con cada negocio sin servir de puente. Gemini, pantalla por bot, transporte Hermes nativo completo, auditoría de `SOUL.md` e iMessage quedan para después.

Este cierre lo escribe Claude al retomar el trabajo. Entre mi sesión anterior y esta trabajó Codex (0.3.1: aprobación con huella exacta, bloqueo entre hermanos). Su cierre queda abajo como "Registro anterior — v1.5".

## Qué cambió en este cierre

| Asunto | Estado |
|---|---|
| Bloqueo Guardián ↔ Casa Kiraz en el proceso vivo | **Activo.** Producción se reinició a las 23:30 con la 0.3.2 (log de arranque). El reporte anterior lo tenía pendiente. |
| Pruebas en navegador de hermanos, puente y tareas | **Ejecutadas** en Chrome real contra el ensayo (mismo código). Detalle abajo. |
| Mac bloqueada | **Nuevo en 0.3.2.** La app detecta la pantalla de bloqueo, lo avisa en rojo y niega todo paso. |
| Git local y remoto | **Conciliados.** El checkout local ya parte de `f955924`; los cambios nuevos están en commits normales. |
| Google Doc de auditoría | **Actualizado** con este cierre, por la instrucción de Joe de actualizarlo al terminar. |

## Evidencia por tipo

### Probado en Chrome real, con Hermes real (ensayo 8788)

| Escenario | Resultado | Qué se vio |
|---|---|---|
| Guardián ↔ Casa Kiraz | 8/8 | Casa Kiraz aparece deshabilitada como destino ("bloqueado · negocios separados"). La ruta de la interfaz devuelve 403 en ambos sentidos. No se creó mensaje, tarea ni aprobación. |
| Holding como puente | 3/3 | Holding recibió la respuesta de Guardián y nada llegó a Casa Kiraz. |
| Tarea Guardián → Holding | 3/3 | Aparece en Tareas de Holding "asignada por Guardián Ventas" y Holding la cerró. |
| Guardián ↔ Holding, mensaje | 5/5 | Pregunta entregada, Holding respondió y la respuesta volvió sola. Corrida anterior a la 0.3.1; esa ruta no cambió. |
| Solo ver | 6/6 | Clic, texto, Return y clic por coordenadas bloqueados; solo corrió la captura. Corrido en 0.3.1. |
| Mac bloqueada | 5/5 | Aviso rojo en la interfaz; captura y tecla negadas; ningún paso ofrecido. Corrido en 0.3.2. |

Matices que no quiero que se pierdan:

- **Hermanos.** En la última corrida el bot se negó por sí mismo a llamar la herramienta, así que ahí no se ejerció el servidor. Sí se ejerció en la ruta de la interfaz (403) y en una corrida previa donde el bot llamó y recibió "Bloqueado: Guardián Ventas y Casa Kiraz no pueden enviarse mensajes ni tareas directamente".
- **Puente.** Holding tampoco intentó reenviar. El bloqueo del servidor para esa cadena está probado solo en la suite automatizada.

### Confirmado por Joe en producción

- Paso a paso: clic en 7 ejecutado; el clic en 8 pidió un Permitir nuevo (0.3.1).
- Llave de Composio propia, cuentas asignadas a Guardián, chat, dictado y voz.

### Solo pruebas automatizadas

- **77/77** pasan (sin red, sin modelos, sin acciones reales). Incluyen huella exacta del paso, modos, bloqueo entre hermanos, puente, tareas y Mac bloqueada.

### No probado

| Pendiente | Motivo |
|---|---|
| Paso a paso en 0.3.2, en navegador | Lo intenté a las 23:25 y falló porque la Mac estaba bloqueada: 0 elementos y teclas sin entregar. No es defecto del código. Repetir con la Mac desbloqueada: `node tests/e2e/control_y_mensajes.mjs … paso`. |
| Cualquier cosa en la sesión de producción de Joe | No tengo su contraseña. Comprobé arranque, página 200 y API 401. |
| Dictado con micrófono, sonido audible | Igual que en el cierre anterior. |
| Primera escritura externa real desde un bot | Requiere el botón de Joe. |

## Estado de producción

- 0.3.2 iniciada a las 23:30. La instancia anterior (0.3.1, 20:59) se cerró con la señal equivalente a Control+C; estaba inactiva desde las 21:54.
- Datos conservados: 3 bots, 22 mensajes, 4 cuentas. Respaldo: `backups/joe-hq-antes-0.3.2.sqlite3`.
- Corre en segundo plano, ya no en la Terminal de Joe. Para detenerla: `kill -INT $(lsof -nP -iTCP:8787 -sTCP:LISTEN -t)`. Para arrancarla: `bash /Volumes/JOE_HQ/app/iniciar.sh`.
- Hay que volver a entrar; la pestaña se recarga sola.

## Un error mío en esta sesión

Al retomar, edité `tests/e2e/control_y_mensajes.mjs` sin revisar antes si el árbol había cambiado. Sobrescribí dos bloques que Codex tenía sin commit (escenarios "hermanos" y "puente"). No tocó código de la app. Reescribí ambos para la política vigente y son los que produjeron los resultados de arriba. La versión exacta de Codex de esos dos bloques no se recuperó.

## Escrituras externas

- Desde los bots: **0**. Sin correos, eventos, publicaciones, filas ni borrados.
- Desde esta sesión: el Google Doc de auditoría y los commits a GitHub, ambos pedidos por Joe.

No se modificó `SOUL.md`, `~/.hermes` ni configuración global. No hay credenciales en este reporte.

---

## Registro anterior — v1.5 (sesión Codex, antes del reinicio)

Actualización: 15/11/2026. Código de origen 0.3.1; rama GitHub `joe-hq`. Alcance aceptado por Joe: una pantalla compartida, un bot a la vez, modos Solo ver/Paso a paso; se informa que puede ver todas las ventanas abiertas durante el préstamo. `message_agent` mantiene su contrato de Hermes con entrega por JOE HQ. Gemini, pantalla independiente por bot y transporte Hermes nativo completo pasan a fase posterior. Guardián y Casa Kiraz quedan bloqueados para mensajes y tareas directos; Holding conserva comunicación con cada negocio, sin servir de puente en una cadena. `SOUL.md` se reserva para la auditoría acordada e iMessage queda en fase 2.

## Estado de cierre

La app 0.3.1 abre en **http://127.0.0.1:8787** en Chrome. Joe confirmó hoy que Guardián Ventas ejecutó el clic en 7 y el clic en 8 requirió que él pulsara **Permitir** en una tarjeta nueva. La instancia visible sigue siendo la versión ya arrancada; el parche de bloqueo directo entre Guardián y Casa Kiraz aún no se ha podido cargar porque esta sesión no puede escribir en `/Volumes/JOE_HQ/data` ni acceder a localhost desde terminal para reiniciar con seguridad.

| Prueba o dato | Estado y tipo de evidencia |
|---|---|
| Arranque 0.3.1 / localhost | **En vivo, visible en Chrome** en `127.0.0.1:8787`; también consta el log de arranque de Joe a las 20:59:07. |
| Bots, cuentas | **En vivo:** aparecen los 3 bots y las 4 conexiones/cuentas están registradas en Apps. El número actual de mensajes no se usa como criterio, pues el chat de prueba añadió mensajes. |
| Calculadora 7→8 | **En vivo, confirmada por Joe:** clic en 7 ejecutado; clic en 8 esperó Permitir en una tarjeta nueva. |
| Google Doc de auditoría | **Lectura en vivo por Composio desde la UI:** `SYS_JOE-HQ_Reporte-Final_v1.0` se leyó y devolvió su título y primeras líneas. |
| Drive por negocio | **Lectura en vivo por Composio desde la UI:** carpetas de Guardián y Holding enumeradas en sus raíces cercadas. No se modificó ningún archivo. |
| Selector de perfil | **En vivo:** Holding cambió de Codex Terra a Codex Sol y volvió a Codex Terra. |
| Sheets por rango | **En vivo, por la UI:** lectura `A1` de la primera hoja de cálculo autorizada terminó con resultado “funcionó”. No se copió el valor a este reporte ni al chat de usuario. |
| Voz | **En vivo, parcial:** la síntesis VibeVoice terminó desde el botón de escucha y el control volvió a habilitarse. No puedo confirmar que el sonido se haya oído físicamente. Dictado con micrófono no se completó. |
| Mensajes/tareas Guardian↔Kiraz | **Implementado en el código local y pruebas automatizadas** como bloqueo 403 antes de crear aprobación, DM o tarea. Prueba de interfaz y carga en el proceso vivo pendientes del reinicio. |
| Reenvío por Holding | **Prueba automatizada** bloquea ambas direcciones cuando la cadena incluye al negocio hermano; comunicación normal con Holding conserva sus pruebas. E2E en la UI nueva queda pendiente del reinicio. |
| Escrituras externas | **0 ejecutadas.** No se envió correo, evento, publicación, fila o borrado. La actualización de este reporte en Google Docs también espera la aprobación concreta de Joe. |
| SOUL.md | Sin cambios; reservado a la auditoría posterior. |
| Suite automatizada | **75/75** pasan en código local (7.971 s; sin red, sin modelos reales ni acciones externas). Reemplaza el dato histórico de 74; no es prueba de interfaz ni de producción. |

### Bloqueo operativo pendiente

El archivo local contiene el bloqueo total para mensajes/tareas directos entre Guardián y Casa Kiraz, incluida la imposibilidad de aprobar tarjetas antiguas de `cross_message`; pero el servidor que está corriendo no recarga código automáticamente. `bash /Volumes/JOE_HQ/app/iniciar.sh --doctor` en esta sesión informó que no puede escribir `/Volumes/JOE_HQ/data`; `curl` a localhost también está bloqueado. No detuve la instancia que Joe dejó corriendo. Para activar el parche, desde la Terminal de macOS con acceso al volumen: **Control+C en la Terminal que corre JOE HQ**, luego ejecutar `bash /Volumes/JOE_HQ/app/iniciar.sh`. Después hay que repetir los E2E de hermanos, puente y tarea contra la instancia actualizada.

### Evidencia de voz y conectores

En la UI, Composio reportó disponibilidad de Drive/Docs y Sheets para Holding, con cercado visible a sus dos carpetas asignadas; correo, Calendar, Instagram y GitHub siguen asignados a Guardián y se muestran no disponibles para Holding. Se verificó la lectura del documento existente, sin edición. No se comparte su contenido aquí. La lectura por rango Sheets y el resultado final de VibeVoice/dictado siguen pendientes de confirmación observable.

El diálogo de prueba de Docs devolvió `SYS_JOE-HQ_Reporte-Final_v1.0` como “JOE HQ — Reporte final v1.2”; esto confirma la lectura actual del documento remoto y, a la vez, que aún no está alineado con este cierre v1.

### GitHub y documentación

La rama remota `joe-hq` termina en `f955924fce8c4189d1c659a4650eff5056bf6878`; el checkout local sigue en `d215586315851fdeea5631a79bd818bfb706dafc` con cambios sin commit local. La conciliación de los cambios nuevos con GitHub queda pendiente de crear y verificar el siguiente commit remoto; no se afirmará que local y remoto coinciden hasta comprobar ese commit.

README y este reporte se están alineando con el alcance aceptado. El Google Doc `SYS_JOE-HQ_Reporte-Final_v1.0` está en `04_SISTEMAS_MARKETING_Y_VIRALIDAD / 01_Borradores_y_Materia_Prima`. Para sincronizarlo, la acción concreta es **reemplazar el cuerpo de ese Google Doc por el REPORTE_FINAL.md v1 de esta carpeta**; no la ejecutaré hasta recibir tu aprobación explícita para esa escritura externa.

No se registran credenciales en este reporte. No se modificó `SOUL.md`, `~/.hermes` ni ninguna configuración global.

---

---

---

## Registro anterior — v1.4

## Reanudación de validación — 15/11/2026, 20:50 local

Joe informó que `iniciar.sh --doctor` ejecutado desde Terminal de macOS devolvió `storage: listo`. Se comprobó el acceso de esta sesión **antes de apagar nada**, como pidió.

**Resultado: esta sesión continúa bloqueada. La instancia actual permanece encendida; no se envió señal de cierre ni se intentó reemplazarla.** Que el diagnóstico funcione en la Terminal de Joe no cambia los permisos efectivos de esta ejecución.

| Verificación nueva | Resultado |
|---|---|
| Doctor desde esta sesión | Código 1: `Sin permiso de escritura en /Volumes/JOE_HQ/data. Ejecuta desde Terminal con acceso al volumen.` |
| HTTP 127.0.0.1:8787 y localhost:8787 | Ambos bloqueados: `<urlopen error [Errno 1] Operation not permitted>`. No se comprobó la página abierta. |
| Instancia anterior | Listener Python PID 98561 en 127.0.0.1:8787. No se detuvo. |
| Código en disco | server.py declara versión 0.3.1. HEAD Git local sigue d215586 con cambios. La comparación de código con f955924 se documenta en la revisión anterior. No se confirmó la versión dentro del proceso vivo. |
| Datos | Nueva consulta SQLite de solo lectura: 3 bots, 8 mensajes y 4 cuentas registradas. No se leyeron credenciales ni detalles de cuentas. |
| Calculadora y aprobación humana | No iniciadas: no se pudo acceder a la app desde esta sesión ni reiniciar el backend. Ningún clic 7/8 ni aprobación humana se presenta como comprobado. |
| SOUL.md | No modificado; queda reservado para auditoría posterior. |

### Paso concreto en Terminal de macOS

En la Terminal original donde está corriendo JOE HQ, pulsa **Control+C** y espera el cierre; esto detiene esa instancia, sin usar comandos que maten todas las instancias Python. Luego ejecuta:

```bash
bash /Volumes/JOE_HQ/app/iniciar.sh
```

Abre **http://127.0.0.1:8787** e inicia sesión. La versión esperada después del reinicio es **0.3.1**. Si iniciar.sh dice “ya está corriendo”, solo ha detectado la instancia anterior y no la ha actualizado.

### Guía de la prueba pendiente 7 → 8

1. Abre Calculadora y selecciona un bot de JOE HQ. Presta la computadora en **paso a paso**, no en solo ver.
2. Pide: “Captura Calculadora y solicita únicamente un clic en el botón 7. Espera mi aprobación. No pulses otras teclas ni botones”.
3. Revisa la tarjeta y sus argumentos completos. Pulsa tú **Permitir**. Debe ejecutarse un solo clic y la Calculadora debe mostrar 7.
4. Pide después: “Ahora solicita únicamente un clic en el botón 8 y espera mi aprobación”. Debe aparecer una tarjeta nueva, con identificador/huella distintos, y no debe ejecutarse el 8 con el permiso del 7. Puedes **Negar** el segundo paso tras comprobarlo.
5. Cambiar argumentos manteniendo la huella vieja provoca rechazo, no una aprobación automática. Una solicitud válida para los argumentos nuevos exige otro permiso.

Estos pasos son instrucciones para la validación aún pendiente; no son resultados observados. Las **74 pruebas automatizadas anteriores** continúan separadas de esta comprobación en vivo y no se volvieron a ejecutar. Este intento solo verificó listener, código declarado, registros de datos y los bloqueos efectivos de la sesión.

Registro local: `artifacts/validacion-vivo-reanudada.json`. Se conservó el reporte anterior como `artifacts/anterior/REPORTE_FINAL-v1.3.md`. No se incluyeron credenciales en el reporte ni se cambió SOUL.md.

---

## Registro anterior — v1.3

## Validación en vivo solicitada desde la terminal — 15/11/2026, 20:32 local

**Resultado: bloqueada antes de detener y reiniciar la instancia anterior.** Se conservó la instancia existente para no provocar una interrupción que esta sesión no podría recuperar. No se declara cerrada la validación con la app abierta.

### Código y proceso

- Directorio: `/Volumes/JOE_HQ/app`; rama `joe-hq`.
- HEAD Git local: `d215586315851fdeea5631a79bd818bfb706dafc`, con cambios locales. No es un checkout limpio de f955924.
- Nueve archivos de código/pruebas en disco se compararon por hash de blob Git con el árbol remoto del commit `f955924fce8c4189d1c659a4650eff5056bf6878`: **9 coinciden, 0 discrepancias**. El servidor en disco declara `0.3.1`.
- Listener observado: un proceso Python, PID **98561**, en `127.0.0.1:8787`; su directorio actual es `/Volumes/JOE_HQ/app`.
- No se pudo identificar el commit cargado dentro de ese proceso: la inspección `/bin/ps` falló con `PermissionError: [Errno 1] Operation not permitted: '/bin/ps'`.
- El último registro de arranque disponible es de las **19:59:09**, versión **JOE HQ 0.2.0**. Es evidencia de log; no demuestra un SHA exacto del proceso.
- No se mató, reinició ni sustituyó ningún proceso, ni se tocó otra aplicación.

### Resultado de las cuatro comprobaciones

| Comprobación | Resultado de esta sesión |
|---|---|
| 1. Arranque y apertura localhost | Existe listener en 127.0.0.1:8787. Las solicitudes HTTP a 127.0.0.1 y localhost desde esta terminal devolvieron `<urlopen error [Errno 1] Operation not permitted>`. No se comprobó la página abierta ni un arranque nuevo. URL para Joe: **http://127.0.0.1:8787**. |
| 2. Datos | Consulta SQLite `mode=ro`, con `PRAGMA query_only=ON`: **3 bots, 8 mensajes, 4 cuentas registradas**. No se leyeron ni imprimieron las credenciales o los detalles de esas cuentas. Registros conservados; disponibilidad en la UI no verificada aquí. |
| 3. Aprobación de computadora | No realizada en vivo. No se creó una acción de computadora, no se pidió una aprobación a Joe ni se ejecutó un clic. El bloqueo ocurrió antes del reinicio y del acceso HTTP necesarios. |
| 4. Evidencia | Este reporte y `artifacts/validacion-vivo-terminal.json` actualizados; respaldo del reporte anterior en `artifacts/anterior/REPORTE_FINAL-v1.2.md`. SOUL.md reservado para su auditoría posterior, sin modificaciones. |

### Comandos y bloqueo exacto

Se ejecutó `bash /Volumes/JOE_HQ/app/iniciar.sh --doctor`. Terminó con código **1** y este mensaje:

```text
Sin permiso de escritura en /Volumes/JOE_HQ/data. Ejecuta desde Terminal con acceso al volumen.
```

Al ejecutar exactamente `bash /Volumes/JOE_HQ/app/iniciar.sh`, el script detectó el listener existente y terminó con código **0**, diciendo:

```text
JOE HQ ya está corriendo. Ábrelo en http://127.0.0.1:8787
```

Ese mensaje **no es un reinicio ni una prueba de apertura**. La sesión se detuvo antes de enviar una señal de cierre: el diagnóstico ya demostraba que no podría levantar la app después. Además, la inspección completa del comando del proceso quedó bloqueada. No se usó Terminal por automatización de escritorio para evadir el sandbox.

### Acción concreta que corresponde hacer en la Mac

1. En la ventana de Terminal original donde está corriendo JOE HQ, pulsa **Control+C** y espera a que cierre. Esto apunta a esa instancia concreta; no uses `pkill python` ni detengas procesos por nombre.
2. Ejecuta:

```bash
bash /Volumes/JOE_HQ/app/iniciar.sh
```

3. Abre **http://127.0.0.1:8787**. El código en disco es 0.3.1; el servidor debe cargarlo al arrancar. Si el script vuelve a decir “ya está corriendo”, la instancia anterior no se ha detenido: ese mensaje no confirma actualización.
4. Para la prueba inocua, abre Calculadora, presta la computadora en **paso a paso** y pide un clic en el botón 7. Revisa la carga completa y pulsa tú **Permitir**. Después solicita un clic en el botón 8: debe aparecer otra tarjeta antes de ejecutarlo. Se puede negar ese segundo paso tras comprobar que requiere nueva aprobación.

**Matiz del protocolo:** alterar un argumento conservando la huella anterior provoca rechazo; no crea automáticamente otra tarjeta. Una nueva solicitud válida con argumentos y huella nuevos requiere un identificador y aprobación nuevos. No se afirmó que esa interacción ya se hubiera observado con Joe y la app abierta.

### Pruebas automatizadas frente a validación abierta

Las **74 pruebas automatizadas** corresponden a la suite anterior (`.test-runtime/interbot-suite-1794802483391681000.log`, 74/74, 2.051 s), sin red y con HTTP/controlador en memoria o dobles. No se repitieron en esta sesión, que no modificó el código.

**Lo comprobado ahora:** listener/cwd, estado Git, coincidencia de nueve archivos de código con f955924, diagnóstico de arranque, mensajes exactos del script, registros de datos por consulta de solo lectura y bloqueos HTTP/proceso.

**Lo no comprobado ahora:** commit exacto dentro del Python vivo, reinicio, página abierta, aprobación humana, acción física con argumentos exactos y nueva tarjeta ante un cambio. Estos puntos siguen pendientes; las 74 pruebas no los sustituyen.

No se incluyeron credenciales en esta evidencia ni se modificó SOUL.md. Esta revalidación es un anexo local nuevo; el Google Doc conserva la entrega v1.2 de la continuación anterior y no se presenta como actualizado por esta comprobación.

---

## Informe de implementación anterior — v1.2

Fecha: 15 de noviembre de 2026. App en código: **0.3.1**. Continuación autorizada desde `d215586`, rama `joe-hq`.

## Dictamen de esta continuación

**Correcciones implementadas, 74 pruebas locales aprobadas y código publicado en GitHub. La actualización de la instancia en ejecución y las pruebas E2E reales nuevas no pudieron completarse desde este sandbox.** No se presenta esta entrega como validación operativa total.

Joe pidió expresamente **dejar SOUL.md tal como está y auditarlo después**. Se conservó su carga en los turnos de sala limpia; no se cambió ese comportamiento ni se declara resuelto. No se cambiaron permisos de Accesibilidad/Grabación de Pantalla, credenciales, cuentas asignadas o configuración global de Hermes.

El reporte v1.1 de Claude queda conservado en `artifacts/anterior/REPORTE_FINAL-v1.1.md`. Sus resultados reales previos se distinguen de las verificaciones de esta sesión.

## Qué se corrigió

### Aprobación exacta de computadora

El defecto era concreto: la tarjeta recortaba texto a 2,000 caracteres y su resumen a 400, mientras el controlador recibía los argumentos completos. La parte autorizada podía diferir de la ejecutada.

Ahora:

- El paso incluye su carga JSON íntegra, herramienta y argumentos, con huella SHA-256 canónica.
- La interfaz muestra **Acción completa · sin recortes** y permite inspeccionar toda la carga, incluida cualquier parte final del texto. El resumen puede abreviarse; la carga autorizada no.
- El clic de Permitir envía la huella del paso visto por Joe. El servidor rechaza huellas ausentes o distintas y decisiones repetidas.
- El puente ejecuta una copia independiente de los argumentos, únicamente si recibe aprobación para esa misma huella. Cambiar el objeto original después no cambia lo ejecutado.
- Si la carga excede 64 KiB UTF-8 se rechaza completa; no se trunca ni se ejecuta parcialmente.
- Las acciones desconocidas se rechazan. Un segundo paso no sustituye una tarjeta que ya está esperando.
- Cambiar de modo, renovar el préstamo o tomar control invalida el paso pendiente anterior.
- Una interfaz o un servidor antiguos sin el nuevo contrato no pueden autorizar un paso mediante el puente actualizado. La UI deshabilita Permitir si falta la carga íntegra.

Archivos: `local_engine/computer_payload.py`, `local_engine/hermes_bridge.py`, `server.py`, `local_web/app.js` y `local_web/styles.css`.

**Límite:** esto garantiza los argumentos autorizados. No garantiza que una ventana o un elemento sigan en el mismo estado entre la captura y la acción. La pantalla física sigue siendo compartida.

### Mensajes y tareas entre bots

Se mantuvo la política existente: mismo negocio y Holding con cada negocio tienen entrega directa; Guardián con Casa Kiraz requiere aprobar el texto exacto. El destino entre hermanos usa turno restringido, con la excepción SOUL vigente.

Se añadieron pruebas deterministas de la ruta autenticada `/relay`, rechazo, aprobación, CSRF y repetición. También de tareas rechazadas por ruta, aprobaciones expiradas/manipuladas y ausencia de tareas escritas antes de validar la ruta.

El escenario E2E de hermanos ya no depende de que el modelo decida invocar message_agent: crea la propuesta por la misma API autenticada de la interfaz y usa los botones reales de Rechazar/Aprobar. La respuesta posterior sigue exigiendo Hermes real. Una negativa del modelo antes de llegar a la compuerta no cuenta como prueba de esta.

El guion solo admite ensayo local en el puerto **8788**, rechaza escenarios desconocidos y capturas fuera de JOE_HQ. Timeout, error o cero verificaciones no pueden producir un PASS vacío. Se eliminaron las comprobaciones incondicionales; el modo solo ver exige los cuatro intentos bloqueados previstos, y la lectura del número 7 exige una captura posterior al clic permitido.

## Modos de computadora vigentes

| Modo | Comportamiento |
|---|---|
| Prestar · solo ver | Mirar, listar ventanas/apps, esperar y desplazarse sobre una zona identificada no editable. Traer al frente apps ya abiertas. Clic, tecla, texto, arrastre, valor o abrir app cerrada: bloqueados, sin opción de permitir en este modo. |
| Prestar · paso a paso | Toda acción con efecto espera Permitir/Negar para su carga exacta. |
| Tomar control | Revoca el préstamo y la compuerta; detiene el turno del bot que tenía la pantalla. |

Los **15 minutos son la caducidad del préstamo**, no un modo de acciones autónomas. Esta es la política conservada en la continuación; no se reintrodujo el modo anterior.

Solo ver limita acciones, pero no aísla información visual: un bot puede ver datos de otras aplicaciones abiertas en la pantalla prestada. No hay pantalla física independiente por bot en esta instalación.

## Pruebas realizadas en esta sesión

**74 pruebas unitarias aprobadas, 0 fallos, 2.051 segundos.** Evidencia completa: `.test-runtime/interbot-suite-1794802483391681000.log`.

| Grupo | Evidencia nueva |
|---|---|
| Carga exacta | Texto largo y Unicode con sufijo; claves/valores sin recorte; copia inmutable; huella y herramienta alteradas; límite UTF-8; rechazo de valores no JSON y números no finitos. |
| Ejecución del puente | Solo ejecuta la copia aprobada; recibo sin huella o cambiado bloqueado; excepción del controlador no expone detalles privados. Controlador sustituido por doble de prueba, sin acciones físicas. |
| Compuerta del servidor | Solo ver, paso a paso, decisión con huella, repetición, paso concurrente, cambio de modo y toma de control. |
| Mensajes/tareas | Ruta HTTP en memoria, rechazo/aprobación exacta, CSRF, ausencia de entrega previa, tarea de ruta prohibida sin escritura, expiración y alteración. |
| Regresiones | Contraseña, cuentas por negocio, rutas y symlinks, memoria/respaldo, máximo cinco bots, alcance Drive y proveedores permitidos. |

También pasaron `node --check local_web/app.js`, `node --check tests/e2e/control_y_mensajes.mjs`, análisis de sintaxis Python y `git diff --check`.

**Estas pruebas no usaron red, navegador conectado, modelos en vivo ni acciones reales de computadora.** Las respuestas controladas de conectores no equivalen a lecturas reales de Drive. No se envió correo, creó evento, publicó o borró ningún archivo como prueba.

## Datos preservados

Una consulta SQLite en modo solo lectura comprobó **3 bots, 8 mensajes y 4 cuentas asignadas** en la base de producción. No se leyó ni imprimió el contenido de las conversaciones o de las credenciales. Evidencia: `artifacts/estado-datos-continuacion.json`.

No se reinició producción ni se modificó su contraseña, sus cuentas, sus memorias o su configuración. Las pruebas guardaron fixtures ficticios dentro de `app/.test-runtime/`, sin borrarlos.

## Evidencia real anterior, atribuida a Claude

La entrega anterior registra ejecución en producción 8787 y ensayo 8788, chat Hermes Codex, memoria nativa, lecturas reales de seis conectores, computadora con Calculadora y audio VibeVoice transcrito con faster-whisper. El reporte posterior de Claude registra pruebas de solo ver, permiso/negación y comunicación Guardián con Holding. **No repetí esos resultados en esta sesión.**

Las capturas existentes se conservaron:

| Archivo | Evidencia anterior |
|---|---|
| `artifacts/captura-01-login-pide-contrasena.png` | Login sin sesión |
| `artifacts/captura-02-mensajes-entre-bots.png` y `captura-03-chat-del-companero.png` | Mensajes entre compañeros |
| `artifacts/captura-04-apps-por-negocio.png` | Cuentas con negocio dueño |
| `artifacts/captura-05-aprobaciones.png` | Propuesta esperando aprobación |
| `artifacts/captura-07-pestana-vieja-con-aviso.png` | Aviso de versión anterior |
| `artifacts/captura-08-campo-llave-en-apps.png` | Campo de credencial Composio |
| `artifacts/captura-09-llave-falsa-rechazada.png` y `captura-10-llave-de-prueba-guardada.png` | Validación y guardado con sus límites anteriores |
| `artifacts/private/` | Capturas de escritorio; permanecen privadas y no se publicaron |

No se generó una captura nueva que simule la UI conectada ni se reutilizó una imagen anterior como prueba del cambio actual.

## GitHub y estado local

Repositorio: https://github.com/lucojoma-byte/bot-hq , rama `joe-hq`.

- Código y pruebas de carga exacta: commit `897a019b1ca60ce7055f8e75797ea1f1dc6f769c`.
- Guion E2E: commit `b1e7678a786d82531a7aa29f88e506902f6f0830`.
- Los blobs del primer commit se compararon con los archivos locales y coinciden.
- Documentación y evidencia final: su commit y verificación se registran en `artifacts/entrega-github.json`.

El sandbox impidió crear `.git/index.lock`. Por eso los commits se realizaron a través del conector GitHub autorizado, sin forzar ni reescribir historia. **La referencia Git local sigue en d215586 y los archivos del trabajo quedan como cambios locales**, aunque su contenido ya está publicado en los commits remotos. No se fingió un commit local ni se alteró el índice por otro medio.

No se incluyeron `.env`, configuración privada de Drive, credenciales, fixtures ni capturas privadas en las publicaciones.

## Bloqueos de la sesión y validación pendiente

| Pendiente | Causa y límite |
|---|---|
| Reiniciar y probar el código 0.3.1 en producción/ensayo | El sandbox no permite escribir data/cache/logs fuera de app ni acceder a localhost desde la terminal. No se intentó evadirlo abriendo una terminal sin restricciones por UI. |
| E2E reales nuevos de hermanos, Holding como puente y tareas | Guion preparado y validado sintácticamente; no ejecutado contra servidor actualizado. No deben presentarse como aprobados. |
| Navegador de esta sesión | El host de automatización de navegador estaba indisponible. Los intentos de revisión nativa se detuvieron porque Chrome cambió de estado durante la interacción; no se obtuvo validación visual nueva. |
| Chat, conectores y voz en vivo nuevos | Red/DNS de terminal y escritura de los directorios operativos restringidos. Se conserva la evidencia previa sin convertirla en prueba actual. |
| Primera escritura externa real | Sigue requiriendo el botón de Joe para la operación concreta. Las pruebas actuales son con dobles; no autorizan enviar/publicar/borrar de verdad. |

Al actualizar, hay que **detener la instancia anterior y arrancarla otra vez**, porque el servidor Python no recarga su código automáticamente. `iniciar.sh` avisa si ya hay una instancia; ejecutar otra vez ese comando sin detener la anterior no actualiza el backend. Hasta el reinicio, un servidor antiguo y el puente nuevo deniegan los pasos sin el nuevo recibo: es un bloqueo seguro de compatibilidad, no un despliegue confirmado.

## Auditorías diferidas y límites conocidos

1. **SOUL conservado por decisión de Joe.** La sala limpia no tiene memoria nativa, historial, biblioteca ni apps, pero sí carga SOUL.md. Puede contener datos del negocio. No se auditó ni corrigió su contenido en esta continuación; pendiente para auditoría posterior.
2. **Pantalla compartida.** Solo ver no evita que aparezcan datos del otro negocio o de otras aplicaciones. La carga exacta tampoco impide que la pantalla cambie entre captura y acción.
3. **Holding como puente.** El servidor bloquea rutas según la cadena de mensajes. No analiza semánticamente cada texto ni garantiza detectar datos copiados entre conversaciones independientes.
4. **Mensajería Hermes.** Se usa el contrato/sobre de message_agent, con transporte y retorno de JOE HQ. No es transporte nativo completo. No se afirma que modificar ~/.hermes sea la única solución técnica posible.
5. **Privacidad del driver.** La entrega anterior registra telemetría por defecto de cua-driver; no se cambió la configuración global. Requiere auditoría aparte.
6. **Otros pendientes heredados.** Lectura real de Docs y Sheets por rango desde la app; micrófono/bocina desde navegador; voz propia en español; rutas fijas de instalación Hermes; Gemini por login sin API de pago. iMessage sigue apagado como fase 2. Arranque automático no se instaló.

## Almacenamiento observado

Mediciones de `du -sk` en esta continuación; incluyen dependencias/fixtures ya existentes:

| Carpeta JOE_HQ | KiB reportados |
|---|---|
| app | 1,200,428 |
| cache | 1,065,404 |
| data | 2,140 |
| memoria | 140 |
| logs | 48 |
| backups | 8 |

`df` reportó 1,314,344 KiB usados y 312,912,632 KiB disponibles en el volumen APFS JOE_HQ. Las medidas de du y df son distintas; no se suman como consumo físico único. Los archivos finales del reporte añaden unos KiB.

Disco interno: 41,449,120 KiB disponibles en la medición. No se instalaron paquetes, modelos ni cachés de proyecto en el disco interno durante esta continuación. Se reutilizaron dependencias existentes. No hay una medición de delta atribuible a este trabajo que permita certificar consumo interno total cero; los datos propios de Chrome/Codex quedan fuera de esa afirmación.

## Arranque y entrega de auditoría

Después de detener la instancia anterior en su Terminal:

```bash
bash /Volumes/JOE_HQ/app/iniciar.sh
```

URL: `http://127.0.0.1:8787`. Para ensayo: `bash iniciar.sh --staging` y puerto 8788. La app y los datos son locales; Codex y conectores necesitan internet. Se mantiene contraseña, localhost y cero APIs de modelos de pago.

Este reporte y README sustituyen las descripciones antiguas de Prestar 15 min. El Google Doc de auditoría mantiene su identificador y nombre `SYS_JOE-HQ_Reporte-Final_v1.0` en la carpeta solicitada; el cuerpo se actualiza a este reporte v1.2 y su verificación queda en `artifacts/entrega-google-doc.json`.
