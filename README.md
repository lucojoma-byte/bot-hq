# JOE HQ

Tu sede local para conversar con Guardián Ventas, Casa Kiraz y Holding D7. Usa Hermes con tu sesión ChatGPT Pro. No utiliza xAI, Orgo ni llaves de modelos de pago.

**Estado: implementación parcial. Esta sesión restringida no permitió iniciar el servidor. Lee [REPORTE_FINAL.md](REPORTE_FINAL.md) antes de usarla.**

## Abrir

Conecta el disco JOE_HQ. Abre Terminal y pega esta línea:

```bash
cd /Volumes/JOE_HQ/app && bash iniciar.sh
```

Abre **http://127.0.0.1:8787** en Chrome. La primera vez, crea una contraseña de al menos 12 caracteres. No hay contraseña predeterminada. Para cerrar, vuelve a Terminal y presiona **Control+C**. No se instala ningún servicio automático ni se publica en internet.

Si aparece “Sin permiso de escritura”, el proceso no tiene acceso al volumen. Esta versión se detiene; no guarda datos en el disco interno. Si dice que el puerto está ocupado, cierra la otra instancia de JOE HQ. Para ver el diagnóstico:

```bash
cd /Volumes/JOE_HQ/app && bash iniciar.sh --doctor
```

## Usarlo

- Selecciona un bot y escribe un mensaje. La respuesta usa Hermes; necesita internet para tu sesión Codex.
- **Nuevo hilo** conserva la memoria del bot y empieza otra conversación.
- El selector ofrece Codex Terra y Codex Sol, detectados en la instalación. Cambia el ajuste de modelo del bot; no adopta memoria, secretos ni conexiones de los perfiles globales.
- **Memoria** permite editar identidad, memoria y perfil de Joe. Guarda una copia previa en `backups/`.
- **Tareas** y **Archivos** pertenecen exclusivamente a ese bot. No se sobrescriben archivos existentes.
- **Conexiones** intenta leer las carpetas Drive autorizadas por el MCP `composio-lucojoma`. Incluye navegación, paginación y lectura de documentos y hojas como texto/CSV; falta verificarlo con red desde la app.
- El micrófono transcribe con faster-whisper. La transcripción queda como borrador; tú decides enviarla. VibeVoice todavía no genera audio porque falta el runtime compatible.
- **Tomar control** detiene los turnos activos. **Devolver control** permite trabajar de nuevo. Esto coordina los agentes; la captura, ratón, teclado y pantallas separadas de macOS siguen pendientes.
- Las propuestas externas aparecen con su carga exacta en **Aprobaciones**. Los adaptadores de escritura aún no están habilitados; aprobar actualmente devuelve el pendiente sin enviar nada.

Máximo cinco bots. Los bots adicionales tienen identidad y memoria propia dentro de su negocio. Un bot nuevo debe asignarse a Guardián, Casa Kiraz o Holding. No se permite cambiar después su negocio. Los mensajes entre bots de distintos negocios están bloqueados; los del mismo negocio usan transporte JOE HQ, todavía no el protocolo nativo de Hermes.

## Dónde se guarda

| Carpeta del disco JOE_HQ | Contenido |
|---|---|
| `app/` | Código y documentación |
| `data/` | Base de datos y biblioteca de cada bot |
| `memoria/guardian/` | Identidad y memoria nativa de Guardián |
| `memoria/casa_kiraz/` | Identidad y memoria nativa de Casa Kiraz |
| `memoria/holding/` | Identidad y memoria nativa de Holding |
| `cache/` | Cachés npm/pnpm/pip/uv/Playwright y temporales |
| `logs/` | Reservado para diagnóstico operativo sin contenidos privados |
| `backups/` | Versiones anteriores de memoria |

La app no mueve ni cambia `~/.hermes`. Lee la sesión existente Codex y OAuth MCP en memoria, sin copiar las credenciales. No se requiere llave Composio mientras ese OAuth funcione. Si se integra una llave más adelante, solo puede guardarse en `app/.env`, nunca en Git.

## Lo que falta

Verificar arranque y chat real fuera del sandbox, integrar voz VibeVoice, computadora macOS con aislamiento y control real, protocolo nativo interbot y escritura por conectores con cuentas separadas. Gemini no se ofrece porque el perfil existente utiliza proveedor de API; no se comprobó login gratuito. iMessage está documentado en [FASE_2_IMESSAGE.md](FASE_2_IMESSAGE.md) y apagado.

## Para mantenimiento técnico

No se necesita instalar npm ni pip para el servidor. Se reutiliza el Python ya instalado por Hermes y los pesos locales de voz. Las rutas detectadas están en `server.py` y `local_engine/voice.py`; si Hermes cambia su instalación, hay que volver a detectarlas.

```bash
python3 -B -m unittest discover -s tests -v
node --check local_web/app.js
```

Los tests conservan sus archivos dentro de `app/.test-runtime/`, excluidos de Git. No usan cuentas reales ni borran datos. Configuración de caché por proyecto: `.npmrc`, `pip.conf` y variables preparadas por `iniciar.sh`/`server.py`; no se alteró la configuración global de herramientas.

## Procedencia

Fork solicitado: [lucojoma-byte/bot-hq](https://github.com/lucojoma-byte/bot-hq). Se estudiaron Bot HQ, grokbot-clone, Bops y Hermes. `bot-hq/` conserva 173 archivos originales de texto con hashes Git verificados. El entorno impidió `git clone`, descargas binarias y crear `.git`; se obtuvieron snapshots mediante el conector GitHub. Las referencias son parciales y **no equivalen a clones completos**.

La UI local reutiliza los tokens originales de Bot HQ, su estructura de chats y el formato de memoria nativa. El backend local reemplaza las integraciones Orgo/xAI y el acceso libre del agente por herramientas validadas. Los servidores anteriores se conservan solo como referencia y no se arrancan. La UI React original no fue compilada; se preparó una interfaz local sin dependencias de navegador para poder ejecutarla sin instalar paquetes.

Licencia original Bot HQ: MIT en `bot-hq/LICENSE`; avisos en `bot-hq/THIRD_PARTY_NOTICES.md`. Bops se usó como referencia visual, sin incorporar su código ni activos a la app. No se utilizan ilustraciones ni marcas de Grok en la UI local.
