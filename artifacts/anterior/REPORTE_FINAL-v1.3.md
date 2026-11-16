# JOE HQ — Reporte final v1.3

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
