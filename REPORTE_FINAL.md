# JOE HQ — Reporte final v1.0

Fecha: 15 de noviembre de 2026. Director: José María. Ubicación: `/Volumes/JOE_HQ/app`.

## Dictamen

**La entrega es parcial. La app no quedó corriendo en localhost y no está lista para operación completa.** Hay código, interfaz, adaptadores locales y 37 pruebas aprobadas; el entorno de esta sesión bloquea escribir fuera de `app/`, abrir puertos locales y resolver los servicios de modelos desde la terminal. Además quedan funciones que requieren implementación adicional, detalladas abajo.

No se usaron APIs de modelos de pago, Orgo ni xAI. No se cambió la configuración global de Hermes. No se envió ningún correo, evento, publicación o mensaje a clientes ni se eliminó ningún archivo. No fue necesario pedir COMPOSIO_API_KEY: existe OAuth para `composio-lucojoma`, leído solamente en memoria.

## Entregables locales

- `PLAN.md`: plan escrito antes de implementar y resultado de ejecución.
- `README.md`: instrucciones en español y arranque de un comando.
- `server.py` y `local_engine/`: persistencia, autenticación, límites por negocio, puente Hermes, cliente MCP y transcripción.
- `local_web/`: interfaz de mensajes, panel por bot, memoria editable, tareas, archivos, modelos, Drive, voz y aprobaciones.
- `tests/test_core.py`: 37 pruebas de lógica, concurrencia y seguridad, sin cuentas reales ni sockets.
- `FASE_2_IMESSAGE.md`: módulo definido y apagado.
- `artifacts/captura-vista-estatica.png`: captura real de Chrome mostrando la vista estática rotulada.
- `artifacts/vista_estatica.html`: revisión visual sin servidor, sin scripts, sin conversaciones inventadas y con controles deshabilitados.
- `artifacts/source-manifest.json` y `artifacts/upstream.json`: procedencia y hashes de fuentes.
- `.test-runtime/`: evidencia local y fixtures conservados, excluidos de Git.

## Qué funciona y qué se comprobó

| Capacidad | Resultado y límite de la evidencia |
|---|---|
| Tres identidades iniciales | Guardián Ventas, Casa Kiraz y Holding D7 persistentes; creación y reapertura comprobadas con SQLite en entorno de prueba. |
| Máximo cinco bots | Límite de servidor probado incluso con solicitudes concurrentes. Los demás trabajos se organizan como hilos. |
| Separación de negocios | Memoria y biblioteca por negocio/bot; rutas absolutas, traversal y symlinks cruzados rechazados en pruebas. Holding tampoco sirve como puente automático entre negocios. |
| Memoria nativa Hermes | Escritura real con la herramienta nativa de Hermes y lectura de su archivo `memories/MEMORY.md` en un home de prueba dentro del volumen. No es una memoria simulada en la base de datos de la app. |
| Edición SOUL/memoria | Implementada; respaldo de la versión previa y bloqueo durante un turno comprobados. |
| Tareas y biblioteca | Creación, listado y lectura de texto implementados. Sobrescritura de archivos existentes bloqueada. |
| Autenticación local | Contraseña sin valor predeterminado, hash scrypt, cookie HttpOnly/SameSite, CSRF, Host/Origin y límite de intentos probados en memoria. No se configuró una contraseña de producción por Joe. |
| Proveedor | Puente construido con Hermes instalado, endpoint Codex fijo y sin fallbacks de pago. Se comprobó construcción de AIAgent y lista exacta de seis herramientas permitidas. |
| Selector de modelo | Codex Terra y Codex Sol, detectados en configuración existente. Cambio persistido y memoria conservada en prueba. No se adoptan los homes, conexiones ni memorias de perfiles globales. |
| STT local | Faster-whisper cargó los pesos existentes y procesó realmente un WAV de silencio, devolviendo texto vacío. Esto verifica el pipeline local, no la precisión con habla española ni el micrófono del navegador. |
| Drive por Composio | Lectura real de las cuatro raíces y listado de cuatro elementos en la carpeta Guardián por el conector autorizado de esta conversación. No equivale a validar el MCP desde la app local. |
| Aprobaciones | Propuestas con carga exacta, expiración, rechazo y aprobación atómica de un solo uso. Prueba concurrente confirma una sola llamada al ejecutor de prueba. Las escrituras reales siguen deshabilitadas. |
| Control humano | Coordinación de estado, revocación de todos los tickets y detención de procesos activos implementadas. No equivale a controlar ratón/teclado ni a mostrar la pantalla real. |
| Interfaz | Sintaxis JavaScript válida; tokens de Bot HQ conservados; escape HTML y CSP sin recursos externos. Inspección visual en Chrome de la vista estática, sin afirmar E2E. |

## Pendientes y causas

| Requisito | Estado pendiente |
|---|---|
| App corriendo en localhost | No conseguido. `bash iniciar.sh` se detuvo correctamente por falta de escritura en `/Volumes/JOE_HQ/data`. Un intento independiente de bind a `127.0.0.1:8787` devolvió `PermissionError: Operation not permitted`. No se evadieron esas restricciones. |
| Conversación real | No validada. El puente devuelve el bloqueo DNS de `chatgpt.com`; no se generó una respuesta de modelo de prueba. |
| Lectura por MCP local de Hermes | Cliente implementado leyendo OAuth existente, sin refrescar ni modificar tokens globales. La inicialización local no pudo conectar; falta verificar protocolo, descubrimiento y lectura con red real. Evidencia: `artifacts/mcp-local-check.json`. |
| Gemini con login | No habilitado. El perfil existente usa proveedor Gemini de API; no hay prueba de acceso mediante login sin llave. |
| Comunicación nativa Hermes | No implementada. Hay relay servidor del mismo negocio y bloqueo entre negocios; no usa `message_agent` nativo ni devuelve respuestas automáticamente al emisor. Requiere integrar roster y runners aislados de Hermes. |
| Computadora real por bot | No implementada. La esfera Dots es un indicador visual. No hay captura, input remoto, Spaces ni escritorios independientes de macOS. No se expusieron terminal/navegador libres que evadan los guardarraíles. |
| Voz VibeVoice | No operativa. Pesos 1.5B presentes, pero falta runtime compatible probado; la app informa el pendiente y no sustituye por voz de pago. |
| Conectores completos | Drive/Docs/Sheets tienen lectura acotada implementada, pendiente de prueba MCP local. Gmail, Calendar e Instagram solo pueden preparar propuestas; su ejecutor devuelve pendiente incluso tras aprobar. GitHub de los bots aún no está integrado. Falta asignar cuentas/permisos por negocio y probar cada escritura autorizada. |
| Pruebas de navegador completas | No realizadas: servidor HTTP bloqueado. No se probó login, crear bot, chat, micrófono o control real desde la UI conectada. |
| Clones y commits pequeños | `git clone` falló por DNS. `gh auth status` no pudo validar sus tokens en este entorno. `git init` falló al crear `.git` por sandbox. No hay commits locales ni push de la adaptación. |
| iMessage | Preparado solo como documentación de fase 2; no lee ni envía mensajes. |

## Procedencia y adaptación

Fork creado y confirmado en la cuenta solicitada: https://github.com/lucojoma-byte/bot-hq . Upstream estudiado: https://github.com/nickvasilescu/bot-hq , commit `decf9a215cddd8792a5f20f4a11a87d4dffa6d15`.

Se recuperaron 173 archivos originales de texto por el conector GitHub; todos coinciden con sus hashes Git. Se omitieron 20 archivos binarios, incluidas capturas originales y WAV de prueba. Los otros tres repositorios tienen snapshots parciales de documentación/referencia; **no son clones completos**. Hermes ejecuta su instalación existente, sin moverla.

Se reutilizan los tokens de diseño de Bot HQ, su estructura visual sidebar/chat/composer/computadora y su formato de memoria. El backend Python y la interfaz local sin dependencias reemplazan los componentes cloud y los accesos sin aislamiento del original. La UI React y el servidor originales se conservan para referencia y no se arrancan ni se presentan como compilados. Esta es una adaptación sustancial, no el repositorio original íntegro funcionando.

Bot HQ conserva licencia MIT y avisos de terceros. No se incorporó código de Bops al runtime. La UI usa iconos propios y no activos de Grok.

## Almacenamiento

El volumen está realmente montado: `/dev/disk9s1 on /Volumes/JOE_HQ (apfs, local, ...)`. Capacidad observada: aproximadamente 300 GiB, casi todo disponible.

Medición antes de cerrar el reporte: `du -sk /Volumes/JOE_HQ/app` = **14,800 KiB, aproximadamente 14.5 MiB**, principalmente código, referencias, captura y fixtures conservados. El reporte y los registros finales añadirán unos KiB. Las carpetas `data/`, `memoria/`, `cache/`, `logs/` y `backups/` de producción siguen sin nuevos datos: el sandbox impidió escribirlas. Las pruebas viven temporalmente bajo `app/.test-runtime/`, dentro del mismo volumen; no deben confundirse con datos de producción.

**Disco interno:** no se instalaron paquetes, modelos, node_modules ni cachés de proyecto nuevos allí. Se reutilizan Hermes/Python ya instalados internamente y modelos ya existentes en WinMac_AI, conforme a la instrucción de no mover Hermes. No hay una medición inicial exacta que permita certificar el delta global del disco interno; Chrome/Codex pueden mantener sus propios datos fuera del control del proyecto. No se afirma un consumo interno total de cero.

La app prepara cachés de npm, pnpm, pip, uv, Playwright, Hugging Face, Torch y temporales en JOE_HQ. `.npmrc` y `pip.conf` son configuraciones locales del proyecto. `node_modules`, si se instalan después, quedan dentro de `app/`. No se alteraron configuraciones globales de gestores. El arranque se detiene si falta el volumen o los permisos; no existe fallback silencioso al disco interno.

## Pruebas y correcciones

Resultado final: **37 pruebas aprobadas, 0 fallos, 0.969 segundos**. `node --check local_web/app.js` también terminó con código 0. HTTP se probó con peticiones en memoria y Drive con respuestas controladas para los escenarios de aislamiento; eso no demuestra red real.

Se corrigieron dos defectos detectados por auditoría adversaria: número incorrecto de parámetros SQL al guardar aprobaciones y respaldo de memoria que podía seguir un symlink hacia otro negocio. Se añadieron límites de modelos, control humano global, permisos privados de SQLite, rechazo temprano de raíces Drive ajenas y conexión HTTP cerrada tras cada respuesta.

Evidencias adicionales: `.test-runtime/hermes-construction.json`, `hermes-native-memory.json`, `hermes-live.json`, `voice-silence.json` y `voice-tts.json`. No contienen credenciales. Los fixtures se conservan; no se borraron archivos.

## Captura

La captura `artifacts/captura-vista-estatica.png` muestra la revisión real en Chrome de `artifacts/vista_estatica.html`. Tiene el rótulo visible **“Vista estática · servidor no iniciado”** y controles deshabilitados. El panel señala que no es una captura del escritorio. No existe una captura de la app conectada a localhost porque no pudo arrancar en esta sesión.

## Arranque y continuación

Comando preparado para una Terminal con acceso al volumen:

```bash
cd /Volumes/JOE_HQ/app && bash iniciar.sh
```

Dirección prevista: `http://127.0.0.1:8787`. No hay exposición pública ni servicio automático instalado. La app, los archivos y la memoria son locales; Codex y Drive necesitan internet.

Para completar: verificar primero almacenamiento y arranque fuera del sandbox; después conversación y MCP reales, VibeVoice, computadora macOS aislada, comunicación Hermes nativa y adaptadores de escritura por negocio. Finalmente ejecutar E2E completo, crear commits y subir la adaptación al fork. Estos pasos permanecen pendientes y no se presentan como realizados.

La copia para auditoría se solicita con el nombre `SYS_JOE-HQ_Reporte-Final_v1.0` en `04_SISTEMAS_MARKETING_Y_VIRALIDAD / 01_Borradores_y_Materia_Prima`. Su identificador y verificación de ubicación se registran por separado en `artifacts/entrega-google-doc.json`, para conservar este mismo contenido en ambos entregables.
