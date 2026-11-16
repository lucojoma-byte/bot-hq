# iMessage — fase 2, sin activar

Este módulo no lee mensajes ni contactos, no solicita permisos macOS y no envía mensajes.

Contrato previsto: adaptador recibe un mensaje dirigido a un bot ya identificado; el servidor valida negocio y crea un hilo en su memoria aislada. Las respuestas salientes se guardan como propuestas y requieren aprobación explícita en la UI. No debe reutilizar la base de datos Messages como memoria compartida ni usar AppleScript libre como bypass de aprobación.

Antes de implementar: definir identidad de cada conversación, permisos mínimos de macOS, vínculo de cuenta por negocio, idempotencia de envíos, cancelación y pruebas con datos ficticios. Cualquier conector de pago queda excluido. Mantener apagado por defecto.
