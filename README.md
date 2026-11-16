# JOE HQ

Tu sede local de agentes. Cada bot es Hermes Agent trabajando con tu suscripción ChatGPT Pro (proveedor `openai-codex`). Corre solo en esta Mac mini, con contraseña, y no usa ninguna API de modelos de pago.

Estado real, pruebas y pendientes: [REPORTE_FINAL.md](REPORTE_FINAL.md).

## Abrir

1. Conecta el disco **JOE_HQ**.
2. En Terminal pega:

```bash
bash /Volumes/JOE_HQ/app/iniciar.sh
```

3. Abre **http://127.0.0.1:8787** en Chrome y entra con tu contraseña local.

Para cerrar: **Control+C** en esa Terminal. Si el disco no está conectado, la app no arranca y te lo dice. No se instala como servicio: después de reiniciar la Mac hay que volver a ejecutar el comando.

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

## Reglas que el servidor hace cumplir

- **Guardián y Casa Kiraz nunca se mezclan.** Memoria, archivos, carpetas de Drive, cuentas y mensajes entre bots están separados por negocio. Holding tampoco sirve de puente.
- **Nada sale sin tu botón.** Los bots solo *preparan* correos, eventos, publicaciones y borrados; se ejecutan cuando pulsas **Aprobar**. Cada aprobación sirve una vez y caduca en 15 minutos.
- **Solo localhost.** Escucha en `127.0.0.1`. Toda la API exige tu contraseña.
- **Cero API de pago.** Único proveedor de modelos: Hermes `openai-codex`. Única llave permitida: Composio.

## Apps (Composio)

1. Elige cualquier bot → panel derecho → pestaña **Apps** → primer recuadro, **"Credencial de Composio"** → pega tu llave de consumidor (`ck_…`) → **Guardar solo en .env**. Se prueba antes de guardarse y queda solo en `app/.env`.
2. En Gmail, Calendar, Instagram y GitHub elige el **Negocio dueño**. Sin asignar, ningún bot las usa.
3. Drive y Sheets no se asignan: cada negocio ve solo su carpeta (definidas en `drive-folders.json`).

Sin llave, la app usa la sesión de Composio que tiene Hermes. Esa sesión dura 1 hora y solo se renueva con Hermes abierto.

## Computadora del agente

- **Prestar · paso a paso:** apruebas cada clic y cada tecla. Úsalo para todo lo sensible.
- **Prestar · 15 min:** el bot actúa solo mientras lo ves en vivo.
- **Tomar control:** corta al bot en el acto.

Es tu pantalla real, con tus sesiones abiertas. En modo 15 min el bot podría pulsar un botón de enviar en una ventana abierta: solo lo frenan sus instrucciones y tu vigilancia. Si la vista en vivo falla, da permiso de Grabación de Pantalla a Terminal en Ajustes del Sistema.

## Voz

- Dictado: faster-whisper. Salida: VibeVoice-1.5B. Todo local; los modelos se leen de `/Volumes/WinMac_AI/AI-Models` (ese disco debe estar conectado).
- La primera frase tarda cerca de un minuto en cargar; las siguientes, unos 10 segundos. El motor se apaga solo tras 10 minutos sin uso.
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
python3 -B -m unittest discover -s tests          # 49 pruebas, sin red ni cuentas reales
node --check local_web/app.js
bash iniciar.sh --staging                         # ensayo: puerto 8788, datos en cache/staging
node tests/e2e/capturas.mjs http://127.0.0.1:8788 /Volumes/JOE_HQ/cache/staging/.staging-password artifacts
node tests/e2e/llave.mjs …                        # campo de la llave y pestañas viejas en Chrome real (ver cabecera del archivo)
```

Rutas fijas que pueden cambiar si actualizas Hermes: `HERMES_PYTHON` en `server.py` y `SOURCE` en `local_engine/hermes_bridge.py`.

## Procedencia

Adaptación del fork [lucojoma-byte/bot-hq](https://github.com/lucojoma-byte/bot-hq) (rama `joe-hq`) de [nickvasilescu/bot-hq](https://github.com/nickvasilescu/bot-hq), licencia MIT. El original se conserva íntegro en `bot-hq/` como referencia y no se arranca; el servidor Python y la interfaz local reemplazan sus integraciones de nube. iMessage queda para fase 2 ([FASE_2_IMESSAGE.md](FASE_2_IMESSAGE.md)).
