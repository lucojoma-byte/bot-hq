# JOE HQ

Tu sede local de agentes. Cada bot es Hermes Agent trabajando con tu suscripción ChatGPT Pro (proveedor `openai-codex`). Corre solo en esta Mac mini, con contraseña, y no usa ninguna API de modelos de pago.

Estado real, pruebas y pendientes: [REPORTE_FINAL.md](REPORTE_FINAL.md).

El reporte de Claude registra pruebas reales de la app en producción (`8787`) y ensayo (`8788`). La revisión posterior confirmó el código y 55 pruebas unitarias; no volvió a comprobar la sesión de producción desde el sandbox actual. El reporte final distingue esas evidencias de las verificaciones nuevas.

## Abrir

1. Conecta el disco **JOE_HQ**.
2. En Terminal pega:

```bash
bash /Volumes/JOE_HQ/app/iniciar.sh
```

3. Abre **http://127.0.0.1:8787** en Chrome y entra con tu contraseña local.

Para cerrar: **Control+C** en esa Terminal. Para aplicar una actualización, primero detén esa instancia y vuelve a ejecutar el comando: el servidor Python no recarga su código solo, y `iniciar.sh` avisa si ya hay una instancia en vez de reiniciarla. Si el disco no está conectado, la app no arranca y te lo dice. No se instala como servicio: después de reiniciar la Mac hay que volver a ejecutar el comando.

Diagnóstico rápido: `bash /Volumes/JOE_HQ/app/iniciar.sh --doctor`

## Qué puedes hacer

| En pantalla | Qué hace |
|---|---|
| **Chat** | Le escribes a un bot; responde Hermes. El micrófono dicta con faster-whisper. La bocina lee la respuesta con VibeVoice. |
| **Crear bot** | Hasta 5 bots. Cada uno pertenece a Guardián, Casa Kiraz o Holding y no se puede cambiar. |
| **Memoria** | Identidad (SOUL), memoria y contexto de Joe de ese bot. Guarda respaldo antes de cada cambio. |
| **Tareas** | Tareas del bot y "Pedirle que le escriba a un compañero". |
| **Archivos** | Biblioteca privada del bot. |
| **Apps** | Drive, Sheets, Gmail, Calendar, Instagram y GitHub por Composio. Aquí asignas cada cuenta a un negocio. |
| **Aprobar** | Todo envío, evento, publicación o borrado espera tu botón. |
| **Computadora del agente** | Le prestas la pantalla a un bot y lo ves trabajar en vivo. |

## Separación y límites actuales

- **Memoria, biblioteca, carpetas de Drive y cuentas asignadas están separadas por negocio.** Un bot no recibe las herramientas genéricas de archivos, terminal o Composio.
- **Mensajes entre bots:** dentro del mismo negocio y entre Holding y cada negocio se entregan directamente. Un mensaje entre Guardián y Casa Kiraz espera que apruebes su texto exacto en **Aprobar**. El receptor lo atiende en un turno restringido, sin su historial, memoria nativa, biblioteca ni apps. **Excepción vigente:** sí carga su `SOUL.md`; Joe pidió conservar ese comportamiento para auditarlo después. No guardes secretos ni datos de clientes en SOUL mientras siga esa excepción.
- **Holding:** el servidor bloquea una cadena de mensajes que pretenda pasar de un negocio hermano al otro. No analiza el significado del texto ni garantiza detectar información copiada por un bot en una conversación nueva.
- **Nada sale sin tu botón.** Los bots solo *preparan* correos, eventos, publicaciones y borrados; se ejecutan cuando pulsas **Aprobar**. Cada aprobación sirve una vez y caduca en 15 minutos.
- **Solo localhost.** Escucha en `127.0.0.1`. Las rutas de datos y acciones exigen sesión con tu contraseña; los callbacks de Hermes usan credenciales internas temporales.
- **Cero API de pago.** Único proveedor de modelos: Hermes `openai-codex`. Única llave permitida: Composio.

Los bots llaman `message_agent` con el contrato de Hermes, pero la entrega y el retorno de respuestas los realiza JOE HQ. Esto no es el transporte nativo completo de Hermes y no requiere cambiar la configuración global existente.

## Apps (Composio)

1. Elige cualquier bot → panel derecho → pestaña **Apps** → primer recuadro, **"Credencial de Composio"** → pega tu llave de consumidor (`ck_…`) → **Guardar solo en .env**. Se prueba antes de guardarse y queda solo en `app/.env`.
2. En Gmail, Calendar, Instagram y GitHub elige el **Negocio dueño**. Sin asignar, ningún bot las usa.
3. Drive y Sheets no se asignan: cada negocio ve solo su carpeta (definidas en `drive-folders.json`).

Sin llave, la app usa la sesión OAuth existente de Composio que tiene Hermes. En las pruebas anteriores esa sesión venció aproximadamente a la hora. Si vence, hay que renovarla desde Hermes o usar la llave propia validada en `.env`; la app no modifica los tokens globales.

## Computadora del agente

- **Prestar · solo ver:** puede capturar la pantalla, listar ventanas, esperar, desplazarse sobre una zona identificada que no sea un control de valor y traer al frente apps ya abiertas. Clics, teclas, texto, arrastres, cambios de valor y apertura de apps cerradas se bloquean en el servidor, sin botón para autorizarlos dentro de este modo.
- **Prestar · paso a paso:** cada acción con efecto espera tu **Permitir/Negar**. La tarjeta muestra un resumen y **Acción completa · sin recortes**: revisa los argumentos completos antes de permitir. Se ejecuta únicamente esa carga; si cambia, falta su huella o supera el límite, el paso se rechaza. Una interfaz/servidor antiguos deben actualizarse antes de permitir. Negarlo o dejar vencer la espera impide ese paso.
- **Tomar control:** revoca el préstamo y solicita detener el turno del bot que tenía la pantalla. Los pasos aún pendientes dejan de estar autorizados.

Ambos préstamos caducan a los **15 minutos**; ese plazo no habilita acciones autónomas. Solo un bot puede tener la computadora a la vez.

Es la pantalla física real de tu Mac, con tus sesiones abiertas. **“Solo ver” bloquea acciones, pero no aísla la información visible por negocio:** el bot puede ver datos de otra app que esté abierta. No hay una pantalla independiente por bot. Antes de prestar la pantalla, cierra u oculta las ventanas que no correspondan a ese negocio.

Claude reportó Accesibilidad y Grabación de Pantalla ya concedidas a Hermes, con una captura real de otras apps. No hace falta volver a activarlas como paso rutinario. Si la vista falla, primero revisa el error del proceso que la solicita.

## Voz

- Dictado: faster-whisper. Salida: VibeVoice-1.5B. Todo local; los modelos se leen de `/Volumes/WinMac_AI/AI-Models` (ese disco debe estar conectado).
- En las pruebas previas, la primera frase tardó cerca de un minuto en cargar y las siguientes unos 10 segundos; depende de la memoria y carga de la Mac. El motor se apaga solo tras 10 minutos sin uso.
- Para una voz en español: guarda un WAV tuyo de 10 a 30 segundos en `/Volumes/JOE_HQ/data/voces/` y elígelo en Apps → Voz local.
- Si falta el entorno de voz: `bash /Volumes/JOE_HQ/app/instalar_voz.sh`

## Dónde vive cada cosa (todo en el disco JOE_HQ)

| Carpeta | Contenido |
|---|---|
| `app/` | Código, `.env`, entorno de voz (`.venv-voz`), `node_modules` de pruebas |
| `data/` | Base de datos, bibliotecas de cada bot, voces |
| `memoria/guardian/`, `memoria/casa_kiraz/`, `memoria/holding/` | Memoria nativa de Hermes de cada negocio |
| `cache/` | Cachés de npm, pip, uv, Playwright, audio temporal y datos de ensayo |
| `logs/` | `joe-hq.log` (eventos, sin contenido de conversaciones) y `voz.log` |
| `backups/` | Versiones anteriores de memoria y de la base |

No se modifica `~/.hermes`. La app lee su sesión Codex sin copiarla.

## Si algo falla

| Mensaje | Qué hacer |
|---|---|
| "el disco JOE_HQ no está conectado" | Conecta el disco y repite el comando. |
| "JOE HQ ya está corriendo" | Abre http://127.0.0.1:8787. |
| "Esta pestaña tiene una versión anterior" o ves "Conexiones de…" | Recarga la página (Cmd+R). Tras una actualización la app se recarga sola; una pestaña muy antigua necesita esa recarga manual una vez. |
| "La sesión OAuth de Composio venció" | Abre Hermes o guarda tu llave en Apps. |
| "…no está asignado a este negocio" | Asigna la cuenta en Apps → Negocio dueño. |
| El bot no responde | Revisa internet y `logs/joe-hq.log`. |

## Mantenimiento técnico

```bash
cd /Volumes/JOE_HQ/app
python3 -B -m unittest discover -s tests -v       # pruebas locales, sin red ni cuentas reales; total vigente en el reporte
node --check local_web/app.js
bash iniciar.sh --staging                         # ensayo: puerto 8788, datos en cache/staging
node tests/e2e/capturas.mjs http://127.0.0.1:8788 /Volumes/JOE_HQ/cache/staging/.staging-password artifacts
node tests/e2e/llave.mjs …                        # campo de la llave y pestañas viejas en Chrome real (ver cabecera del archivo)
node tests/e2e/control_y_mensajes.mjs …          # solo ensayo: modos de control, mensajes y tareas (ver cabecera)
```

Los guiones E2E pueden hacer acciones y mensajes reales en el ensayo; no deben apuntar a producción ni presentarse como aprobados sin ejecutar el escenario correspondiente. La negativa del modelo a intentar una acción tampoco prueba por sí sola que el servidor la haya bloqueado.

Rutas fijas que pueden cambiar si actualizas Hermes: `HERMES_PYTHON` en `server.py` y `SOURCE` en `local_engine/hermes_bridge.py`.

## Procedencia

Adaptación del fork [lucojoma-byte/bot-hq](https://github.com/lucojoma-byte/bot-hq) (rama `joe-hq`) de [nickvasilescu/bot-hq](https://github.com/nickvasilescu/bot-hq), licencia MIT. `bot-hq/` se conserva como referencia y no se arranca; el servidor Python y la interfaz local reemplazan sus integraciones de nube. iMessage queda para fase 2 ([FASE_2_IMESSAGE.md](FASE_2_IMESSAGE.md)).
