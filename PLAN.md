# JOE HQ — Plan de ejecución

1. Verificar montaje APFS, permisos, espacio, Hermes instalado y proveedor sin API de pago; no modificar `~/.hermes`.
2. Clonar y estudiar bot-hq, grokbot-clone, bops y hermes-agent. Hacer fork de bot-hq si la autenticación lo permite y conservar su procedencia.
3. Adaptar bot-hq: localhost con contraseña, tres identidades persistentes, máximo cinco bots, memoria nativa y archivos aislados por negocio.
4. Integrar Hermes openai-codex, perfiles permitidos, sesiones, tareas y mensajes entre bots. Aplicar aislamiento y aprobaciones en el servidor.
5. Integrar Composio MCP existente con carpetas autorizadas, computadora local con toma de control y voz local. Marcar capacidades bloqueadas sin simular éxitos.
6. Probar arranque, creación, conversación, perfiles, controles, aislamiento, voz y Drive. Auditar seguridad y corregir fallos.
7. Entregar arranque de un comando, README en español, reporte con evidencia y capturas; crear el Google Doc de auditoría si la conexión lo permite.

## Restricciones
- Cero proveedores de API de pago; solo Hermes openai-codex y alternativa Gemini con login si está disponible.
- Secretos exclusivamente en `.env` excluido de Git. Ningún cambio a configuración global de Hermes.
- Código, dependencias, cachés, memoria, datos, logs y respaldos en `/Volumes/JOE_HQ`.
- No enviar mensajes externos, publicar, crear eventos ni eliminar archivos sin aprobación explícita mediante UI.
- iMessage queda para fase 2.

## Evidencia y estado
Implementación parcial terminada y auditada en esta sesión. Ver `REPORTE_FINAL.md`.

- Fork creado; 173 archivos de texto de bot-hq recuperados y hashes verificados. Clones completos bloqueados por DNS.
- UI local y backend implementados; 37 tests pasan, sin red ni sockets.
- Memoria nativa Hermes y STT local comprobados; conversación Codex bloqueada por DNS.
- Lectura Drive real por Composio de esta conversación confirmada; MCP local bloqueado por red.
- Arranque real bloqueado por permisos de escritura fuera de `app` y bind localhost.
- Creación de `.git` bloqueada por sandbox; no se generaron commits ni push de la adaptación.
- Computadora macOS real, VibeVoice, comunicación Hermes nativa y escrituras externas siguen pendientes de implementación. No se presentan como éxitos.

Orden para completar fuera de este entorno: probar almacenamiento/arranque → chat y MCP con red → runtime VibeVoice → escritorio macOS aislado → transporte Hermes nativo → adaptadores de escritura y cuentas por negocio → E2E real y commits.
