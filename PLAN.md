# JOE HQ — Plan de ejecución

## Etapa 1 (sesión anterior, Codex)
Estructura, núcleo de datos, puente Hermes, interfaz local y 37 pruebas. Quedó sin arrancar por el sandbox de esa sesión.

## Etapa 2 (15 de noviembre de 2026) — hecha
1. Leer plan, guía, reporte y evidencia anteriores. Confirmar app viva y Hermes real.
2. Hallazgo 1: repositorio local ligado al fork, commits pequeños y push.
3. Hallazgo 2: diagnosticar Composio (sandbox sin red; OAuth de 1 hora) y probar las 6 apps.
4. Hallazgo 3: entorno de voz propio en JOE_HQ y VibeVoice generando audio.
5. Hallazgo 4: mantener la contraseña; cubrir las rutas nuevas.
6. Composio desde la app con cuentas por negocio y escritura solo tras aprobación.
7. Mensajes entre bots con `message_agent` de Hermes, cercados por negocio.
8. Computadora: `computer_use` de Hermes con préstamo, paso a paso y toma de control.
9. Voz: dictado y salida locales, probados de ida y vuelta.
10. Interfaz, 47 pruebas, capturas, guía, reporte y documento de auditoría.

## Etapa 3 — pendiente (detalle en REPORTE_FINAL.md)
- Joe: probar chat en producción, pegar llave de Composio, asignar cuentas, aprobar la primera escritura real.
- Voz de referencia en español.
- Descripción más clara de cada paso de computadora.
- Arranque automático al encender la Mac, si se desea.
- iMessage (fase 2).

## Restricciones vigentes
- Cero API de modelos de pago: solo Hermes `openai-codex`. Única llave: Composio, en `.env`.
- Todo en `/Volumes/JOE_HQ`. No se toca `~/.hermes`.
- Guardián y Casa Kiraz jamás se mezclan.
- Ninguna acción externa sin el botón de aprobación de Joe.
- Solo localhost con contraseña.
