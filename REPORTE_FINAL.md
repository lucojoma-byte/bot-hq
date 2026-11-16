# JOE HQ — Reporte final v1.1

Fecha: 15 de noviembre de 2026. Director: José María. Ubicación: `/Volumes/JOE_HQ/app`. Versión de la app: 0.2.0.
Continúa el avance parcial anterior (Codex). Este reporte sustituye al v1.0.

## Dictamen

**La app corre en `http://127.0.0.1:8787`, pide contraseña y los bots responden con Hermes.** Los cinco requisitos pendientes quedaron construidos y probados con ejecuciones reales en una instancia de ensayo (puerto 8788, datos de prueba dentro del mismo disco).

Tres límites que debes conocer antes de dar la obra por cerrada:

1. **No probé un chat en producción después del reinicio.** No tengo tu contraseña y no la pedí. Producción y ensayo usan el mismo código; lo que cambia son los datos.
2. **Ninguna escritura externa se ejecutó de verdad.** No se envió correo, no se creó evento, no se publicó ni se borró nada. Probé proponer y rechazar; aprobar es tu botón.
3. **Faltan dos acciones tuyas:** pegar la llave de Composio y asignar cada cuenta a un negocio (pestaña Apps).

No se usó ninguna API de modelos de pago. No se modificó `~/.hermes`.

## Los 4 hallazgos de la auditoría anterior

| # | Hallazgo | Resultado | Evidencia |
|---|---|---|---|
| 1 | Fork sin commits | **Corregido.** 24 commits de la adaptación en `lucojoma-byte/bot-hq`, rama `joe-hq`. | `git log`; GitHub compara `main...joe-hq`. |
| 2 | MCP de Composio "falló por DNS" | **Corregido.** No era DNS: el sandbox de la sesión anterior bloqueaba toda la red. En esta Mac resuelve y conecta. | Lecturas reales de las 6 apps. |
| 3 | VibeVoice no corre | **Corregido.** Faltaba un Python con `torch` y `vibevoice` (el de Hermes no los trae) y el tokenizador se buscaba en internet. | Audio generado y dictado de vuelta. |
| 4 | Pide contraseña en incógnito | **Se mantiene.** Toda la API responde 401 sin sesión, incluidas las rutas nuevas. | Captura 01; pruebas HTTP. |

Notas de cada uno:

- **Hallazgo 1.** Dejé `joe-hq` como rama principal del fork para que veas los commits al abrirlo; `main` sigue idéntica al original. El fork es **público**: `drive-folders.json`, `.env` y `references/` quedaron fuera de Git.
- **Hallazgo 2, segunda causa.** La sesión OAuth de Composio que usa Hermes dura 1 hora y solo se renueva con Hermes abierto. Venció a media prueba (18:04) y lo vi fallar. Por eso la app acepta tu llave de consumidor `ck_…`, que no caduca así.
- **Hallazgo 3.** En precisión completa el modelo ocupa unos 11 GB y satura los 16 GB de esta Mac (más de 7 minutos sin terminar una frase). Corre en media precisión: 6.4 GB.

## Requisitos pendientes: qué funciona de verdad

### 1. App viva y bots respondiendo con Hermes

- Proceso escuchando en `127.0.0.1:8787`; página 200; API 401 sin contraseña.
- Tus 3 bots y 4 mensajes previos se conservaron. Respaldo: `backups/joe-hq-antes-0.2.sqlite3`.
- Ensayo: respuestas de Hermes en 7 a 15 segundos; el bot escribió su memoria nativa (`memories/MEMORY.md`).
- **Defecto heredado corregido:** las herramientas de los bots devolvían un objeto y Hermes exige texto. Ninguna herramienta (archivos, tareas, Drive, aprobaciones) funcionaba en la versión anterior.

### 2. Composio desde la propia app

| App | Lectura real probada | Escritura (solo con tu botón) |
|---|---|---|
| Drive / Docs | Listar carpetas de cada negocio. Lectura de un Google Doc: programada, sin prueba real | Enviar a papelera |
| Sheets | Hoja leída como CSV (1,727 caracteres); lectura por rango programada, sin prueba real | Agregar filas |
| Gmail | Búsqueda: 3 correos | Enviar, crear borrador |
| Calendar | Lista de eventos: 0 próximos | Crear evento |
| Instagram | Perfil | Publicar imagen |
| GitHub | 9 repositorios | Crear issue |

- **Aislamiento probado:** el bot de Guardián no pudo listar la carpeta de Casa Kiraz ni leer un documento ajeno; el de Casa Kiraz no pudo leer uno de Guardián.
- **Cuentas exclusivas:** Gmail, Calendar, Instagram y GitHub pertenecen a un solo negocio. Sin asignar, nadie las usa. Con Gmail asignado a Holding, Guardián quedó bloqueado.
- Los bots usaron los conectores por sí mismos dentro del chat (contaron archivos, correos y repos).
- Los bots no reciben la herramienta genérica de Composio ni acceso HTTP: solo funciones cerradas.

### 3. Comunicación nativa entre bots de Hermes

- Los bots usan `message_agent`, la herramienta de Bot Mode de Hermes, con su contrato, su sobre ("Constraints", "Reply needed") y su vía de despacho nativa.
- **Prueba real:** Guardián Ventas preguntó a Guardián Cotizaciones un dato que solo ese bot conocía (COT-7741). Cotizaciones contestó y la respuesta despertó sola a Ventas, que te lo reportó. Capturas 02 y 03.
- Hacia Casa Kiraz: bloqueado. Para el bot de Guardián ese compañero no existe.
- Límites: 3 saltos y 8 mensajes por conversación entre bots.
- **Lo que no es nativo:** el transporte. El de Hermes lanza `hermes -p <perfil>` sobre perfiles globales de `~/.hermes` y un solo directorio para todos. Usarlo exigiría modificar `~/.hermes` y pondría a los dos negocios en la misma lista. La entrega la hace JOE HQ, por negocio.

### 4. Computadora del agente

- Motor: `computer_use` nativo de Hermes (cua-driver), con permisos de Accesibilidad y Grabación de Pantalla ya concedidos.
- **Prueba real:** el bot abrió la Calculadora, pulsó 125 × 8 = con clics reales y leyó "1,000" en pantalla (51 segundos).
- **Paso a paso:** cada clic o tecla espera tu Permitir/Negar. Negué un clic: no se ejecutó.
- **Tomar control:** detuvo el turno del bot en 1.5 segundos; la vista en vivo se apagó.
- Sin préstamo, el bot ni siquiera tiene la herramienta.
- Interfaz: pantalla real en vivo, indicador de puntos animado mientras piensa, lista de acciones, cuenta regresiva de 15 minutos. Captura 06 (solo local, muestra tu escritorio).
- Añadí `open_app`: el driver de Hermes no abre apps cerradas.

### 5. Voz local completa

- **Salida:** VibeVoice-1.5B, pesos de `/Volumes/WinMac_AI/AI-Models`, sin conexión. 8.7 s de audio en 21 s; con el motor caliente, 7 s de audio en 11 s. Primera frase: unos 80 s por la carga.
- **Dictado:** faster-whisper. Antes solo se había probado con silencio.
- **Prueba de ida y vuelta:** VibeVoice dijo "Joe, la cotización del portón quedó lista. Falta tu aprobación para enviarla al cliente." y faster-whisper transcribió "Joe la cotización del portón quedó lista. Falta a tu aprobación para enviarla al cliente."
- El motor de voz se apaga solo tras 10 minutos sin uso.

## Guardarraíles

- Aprobaciones: carga exacta visible, un solo uso, caducan a los 15 minutos. Al aprobar se vuelve a validar negocio, cuenta y carpeta.
- Si una cuenta no está asignada, la aprobación falla cerrada y no se llama a Composio (probado).
- Contraseña con hash scrypt, cookie HttpOnly/SameSite, CSRF, validación de Host y Origin, límite de intentos, CSP sin recursos externos.
- Bitácora en `logs/joe-hq.log`: eventos, sin texto de conversaciones.

## Pruebas

- **49 pruebas unitarias, 0 fallos** (37 anteriores actualizadas más 12 nuevas). Sin red ni cuentas reales.
- **23 verificaciones en Chrome real** del campo de la llave y de las pestañas viejas (ver "Corrección posterior").
- Sintaxis JavaScript válida. Revisión en Chrome limpio: sin errores de consola salvo el 401 del intento con contraseña incorrecta.
- Pruebas reales de extremo a extremo en ensayo: Hermes, 6 conectores, mensajes entre bots, computadora, voz.

## Capturas

| Archivo | Qué muestra |
|---|---|
| `artifacts/captura-01-login-pide-contrasena.png` | Ventana limpia: pide contraseña |
| `artifacts/captura-02-mensajes-entre-bots.png` | Guardián Ventas recibe la respuesta de su compañero |
| `artifacts/captura-03-chat-del-companero.png` | El mensaje como lo recibió Cotizaciones |
| `artifacts/captura-04-apps-por-negocio.png` | Apps con negocio dueño (correos y usuarios difuminados) |
| `artifacts/captura-05-aprobaciones.png` | Evento de calendario esperando tu botón |
| `artifacts/private/06-computadora-paso-pendiente.png` | Pantalla en vivo y paso pendiente. Solo local: muestra tu escritorio |
| `artifacts/captura-07-pestana-vieja-con-aviso.png` | Pestaña con la interfaz anterior: ahora avisa que recargues |
| `artifacts/captura-08-campo-llave-en-apps.png` | Apps → "Credencial de Composio", primer recuadro |
| `artifacts/captura-09-llave-falsa-rechazada.png` | Llave falsa: Composio real la rechaza y no se guarda |
| `artifacts/captura-10-llave-de-prueba-guardada.png` | Llave de prueba guardada (Composio simulado) |

Todas son del ensayo (banda "ENSAYO"), no de tus conversaciones reales.

## Corrección posterior: "el campo de la llave no existe"

**Lo que pasó.** Joe abrió Apps y no vio el campo. Tenía razón en lo que veía y el error fue mío.

- **Causa.** El campo sí estaba en la app, pero su pestaña seguía ejecutando la interfaz anterior. Al reiniciar el servidor, una pestaña abierta vuelve a pedir contraseña sin recargar el programa. No le dije que recargara y no probé ese camino.
- **Prueba de la causa.** Los textos que vio ("Conexiones de…", "Conector pendiente de verificación") solo existen en la interfaz anterior. La cargué a propósito contra el servidor actual y obtuve su misma pantalla (captura 07).

**Lo que cambió.**

- La app lleva una huella de versión. Si cambia, la pestaña se recarga sola.
- Una pestaña demasiado antigua para recargarse sola muestra una barra roja: "Esta pestaña tiene una versión anterior de JOE HQ. Recarga la página (Cmd+R)".
- "Credencial de Composio" subió al primer recuadro de la pestaña Apps; se ve sin desplazarse.
- El ensayo usa su propio `.env`; nunca toca el de producción.

**Probado en Chrome real (23 verificaciones, todas pasan).**

| Prueba | Contra qué | Resultado |
|---|---|---|
| Llave falsa | Composio real | Rechazada: "NO se guardó". No se creó `.env` |
| Llave de prueba | Composio simulado en esta Mac | Guardada; estado "Llave propia en .env"; botón "Reemplazar llave"; archivo con permiso 600; la llave no aparece en pantalla ni en logs; persiste al recargar |
| Pestaña vieja | Servidor actual | Muestra la barra de recarga |
| Actualización con pestaña abierta | Servidor actual | Se recargó sola y conservó la sesión |

**Límites de esta prueba.**

- El guardado se probó contra un Composio simulado: no tengo una llave real. Que Composio real acepte la llave de Joe se verá cuando él la pegue.
- Todo se probó en el ensayo. En producción comprobé, sin contraseña, que un Chrome nuevo recibe la interfaz actual con el campo.

## Pendientes y por qué

| Pendiente | Motivo |
|---|---|
| Chat en producción tras el reinicio | Sin tu contraseña. Pruébalo con un mensaje. |
| Llave de Composio en `.env` | Solo tú la tienes. Sin ella, Composio depende de Hermes abierto. |
| Asignar Gmail, Calendar, Instagram y GitHub | Es tu decisión de negocio; no la supuse. |
| Ejecución real de una escritura | Exige tu aprobación. Probada con dobles de prueba, no contra Gmail/Calendar reales. |
| Lectura de un Google Doc y de Sheets por rango | Programadas; sin prueba real. |
| Micrófono y bocina con clic en el navegador | Probados por la API, no con clic humano. |
| Voz con acento español | Las 2 voces de referencia son en inglés. Falta un WAV tuyo. |
| Riesgo del modo "15 min" | El bot actúa sin pedir permiso por paso sobre tu pantalla real. Podría pulsar "Enviar" en una ventana abierta. Para lo sensible, paso a paso. |
| Pantalla separada por bot | No existe en macOS: el escritorio por bot de Hermes es solo Linux. Hay una pantalla física y un bot a la vez. |
| Descripción de cada paso | Hermes resume "click element #6"; hay que mirar la vista en vivo para saber qué es. |
| Transporte nativo de Hermes entre bots | Exige modificar `~/.hermes`. Ver punto 3. |
| Arranque automático | No se instaló servicio. Tras reiniciar la Mac: `bash iniciar.sh`. |
| Rutas fijas de Hermes | `server.py` apunta a la instalación actual de Hermes; una actualización puede moverla. |
| Gemini con login | No se ofrece: el perfil existente usa API. |
| iMessage | Fase 2, apagado. |
| Respuestas en vivo | La interfaz consulta cada 1 a 3 s; no muestra el texto mientras se escribe. |
| Telemetría de cua-driver | El driver de Hermes envía telemetría "sin contenido" por defecto. No la cambié por ser configuración global. |

## Almacenamiento

| Carpeta en JOE_HQ | Tamaño |
|---|---|
| `app/` | 1.1 GB (1.0 GB es el entorno de voz) |
| `cache/` | 1.0 GB |
| `data/` | 1.8 MB |
| `memoria/` | 132 KB |
| `logs/`, `backups/` | menos de 1 MB |

- Disco JOE_HQ: 1.2 GB usados de 300 GB.
- **Disco interno:** las cachés internas de uv, npm, Hugging Face y Playwright no cambiaron hoy (fechas de modificación anteriores). El entorno de voz, `node_modules` y todas las cachés nuevas están en JOE_HQ.
- El espacio libre interno bajó de 45 a 40 GB durante la sesión. No lo atribuyo al proyecto, pero no medí qué proceso lo usó.
- Dependencias fuera de JOE_HQ que ya existían: Hermes (`~/.hermes`), Python 3.11 de Homebrew, Chrome, el código de VibeVoice (`~/code/VibeVoice`, solo para instalar) y los modelos en WinMac_AI.

## Arranque

```bash
bash /Volumes/JOE_HQ/app/iniciar.sh
```

Abre `http://127.0.0.1:8787`. Guía de uso: `README.md`.

## Tus próximos pasos

1. Entra y manda un mensaje a un bot.
2. Apps → pega la llave `ck_…`.
3. Apps → asigna cada cuenta a su negocio.
4. Aprueba una acción de prueba (por ejemplo, un borrador de correo a ti mismo) para validar la primera escritura real.
5. Agrega un WAV de tu voz en `data/voces/`.
