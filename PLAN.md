# JOE HQ — Plan de ejecución

## Cierre de v1 local — alcance decidido; 0.3.2 desplegada el 15/11 a las 23:30

Estado al cierre: bloqueo Guardián↔Casa Kiraz activo en producción; hermanos, puente y tareas probados en navegador (ensayo); detección de Mac bloqueada añadida. Pendiente: repetir «paso a paso» en navegador con la Mac desbloqueada. Detalle en REPORTE_FINAL.md.

Joe pidió completar el trabajo y reportar dudas/fallas al final. **Excepción explícita: conservar el comportamiento actual de SOUL.md, incluida su carga en sala limpia; auditarlo después.** No modificar ese comportamiento ni declararlo resuelto.

1. Aprobación exacta de computadora y prueba viva 7→8: completadas, la última confirmada por Joe en la UI.
2. Bloquear mensajes y tareas directos Guardián↔Casa Kiraz. Holding continúa con cada negocio, sin servir de puente en una cadena.
3. Conservar pantalla compartida, un bot a la vez, Solo ver/Paso a paso; avisar que durante el préstamo el bot ve las ventanas abiertas.
4. Mantener `message_agent` con entrega JOE HQ. Gemini, pantalla independiente y transporte nativo completo se aplazan; `SOUL.md` queda para auditoría; iMessage sigue en fase 2.
5. Alinear README, reporte y Google Doc, preservando secretos y las aprobaciones humanas.

Resultado parcial de esta sesión: 75 pruebas automatizadas pasan en el árbol local; lecturas en vivo de Drive y Docs por la interfaz y cambio/restauración de perfil verificados. Reiniciar con el parche de mensajería está bloqueado por permisos efectivos de escritura en `/Volumes/JOE_HQ/data`. Sheets por rango y voz continúan bajo prueba. La actualización del Google Doc espera la aprobación explícita de Joe para esta escritura externa.

## Punto de partida comprobado

- Rama `joe-hq`, commit de inicio `d215586`.
- En la revisión previa a esta continuación pasaron **55 pruebas unitarias**, sin red ni cuentas reales.
- El reporte de Claude registra app en producción `127.0.0.1:8787`, ensayo `127.0.0.1:8788`, voz local, lecturas de conectores y pruebas reales de computadora. Es evidencia de la sesión anterior; esta continuación no debe presentarla como verificación repetida.
- La sesión actual tiene restricciones de escritura fuera de `app/` y de red desde la terminal. No se deben evadir ni atribuir a permisos macOS de Accesibilidad o Grabación de Pantalla.

## Cierre de la continuación

1. Verificar la suite apropiada tras corregir el paso autorizado. La carga debe ser completa, visible, inmutable y vinculada a la aprobación; rechazar cargas que no puedan revisarse completas.
2. Completar escenarios deterministas de mensajes, tareas, aprobación y bloqueo de puentes. Una negativa espontánea del modelo no sustituye una prueba de la compuerta del servidor.
3. Ejecutar escenarios E2E de hermanos, Holding como posible puente y tareas, únicamente en ensayo y cuando el entorno permita servidor, red y navegador. Distinguir controles simulados, tests en memoria y ejecución real con Hermes.
4. Conservar ambos modos de computadora: **solo ver** y **paso a paso**. Los 15 minutos son la caducidad del préstamo, no un modo de ejecución autónoma.
5. Actualizar README, reporte y Google Doc con las reglas, resultados y límites vigentes. El reporte final debe identificar evidencia anterior y nueva, pendientes de implementación y bloqueos de esta sesión por separado.
6. Crear commits pequeños y subirlos al fork solo si Git y red lo permiten. No afirmar push ni despliegue sin comprobarlos.

## Auditorías y límites que deben permanecer visibles

- `SOUL.md` se sigue cargando por instrucción de Joe, aunque el turno entrante entre Guardián y Casa Kiraz no tenga memoria nativa, historial, biblioteca ni apps. Esa identidad editable puede contener información sensible y se auditará después.
- La pantalla física no aísla información por negocio. “Solo ver” limita acciones; todavía puede mostrar otras apps y datos abiertos.
- Holding bloquea reenvíos según la cadena de mensajes; no inspecciona semánticamente cada texto ni garantiza detectar datos copiados entre conversaciones independientes.
- `message_agent` usa contrato y sobre de Hermes, con transporte y retorno de respuestas de JOE HQ. No es transporte nativo completo.
- Las escrituras reales a servicios externos deben conservar el botón de Joe; no ejecutar correos, eventos, publicaciones o borrados como prueba automática.
- No confundir el código corregido en disco con una instancia de producción reiniciada y verificada. Preservar datos, contraseña y cuentas existentes.

## Fuera del cierre actual

Voz de referencia propia en español, arranque automático si Joe lo decide, Gemini mediante login sin API de pago y transporte nativo completo requieren seguimiento explícito en el reporte. iMessage permanece como fase 2, apagado.

## Restricciones vigentes
- Cero API de modelos de pago: solo Hermes `openai-codex`. Única llave: Composio, en `.env`.
- Todo en `/Volumes/JOE_HQ`. No se toca `~/.hermes`.
- Guardián y Casa Kiraz mantienen sus carpetas, memorias, bibliotecas y cuentas separadas. Las excepciones de mensajería se documentan con sus límites y aprobación.
- Ninguna acción externa sin el botón de aprobación de Joe.
- Solo localhost con contraseña.
