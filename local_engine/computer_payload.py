"""Carga exacta aprobable de un paso de computadora, sin dependencias de Hermes.

El resumen de una tarjeta puede abreviarse. Esta carga nunca se recorta: si no
cabe, el paso se rechaza antes de pedir aprobación o llamar al controlador.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re

MAX_PAYLOAD_BYTES = 64 * 1024
ALLOWED_TOOLS = frozenset({'computer_use', 'open_app'})


class PayloadError(ValueError):
    """No se puede garantizar que lo ejecutado sea la carga aprobada."""


def _json_value(value, depth=0):
    if depth > 64:
        raise PayloadError('El paso tiene demasiados niveles de argumentos.')
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PayloadError('El paso contiene un número no finito.')
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item, depth + 1)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise PayloadError('Los nombres de argumentos deben ser texto.')
        for item in value.values():
            _json_value(item, depth + 1)
        return
    raise PayloadError('El paso contiene argumentos que no son JSON.')


def _canonical(payload):
    _json_value(payload)
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise PayloadError('No se pudo representar el paso completo.') from None
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise PayloadError('El paso completo supera 64 KiB; divídelo en pasos más pequeños. No se ejecutó nada.')
    return encoded


def freeze_payload(tool, arguments):
    """Devuelve (carga JSON desligada del original, SHA-256 canónico)."""
    if tool not in ALLOWED_TOOLS or not isinstance(arguments, dict):
        raise PayloadError('Herramienta o argumentos de computadora inválidos.')
    encoded = _canonical({'tool': tool, 'arguments': arguments})
    return json.loads(encoded), hashlib.sha256(encoded).hexdigest()


def verify_payload(payload, digest, expected_tool='computer_use'):
    """Valida integridad y devuelve una copia; nunca confía en el resumen."""
    if (not isinstance(payload, dict) or set(payload) != {'tool', 'arguments'}
            or payload.get('tool') != expected_tool):
        raise PayloadError('La carga no corresponde a esta herramienta.')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise PayloadError('Falta la huella íntegra del paso.')
    snapshot, actual = freeze_payload(payload['tool'], payload['arguments'])
    if not hmac.compare_digest(actual, digest):
        raise PayloadError('Los argumentos cambiaron; vuelve a solicitar el paso completo.')
    return snapshot


def approved_arguments(payload, digest, verdict):
    """Solo permite ejecutar los argumentos cuya huella devolvió la compuerta."""
    snapshot = verify_payload(payload, digest, expected_tool=payload.get('tool') if isinstance(payload, dict) else None)
    result = verdict.get('result') if isinstance(verdict, dict) else None
    if (not isinstance(verdict, dict) or verdict.get('ok') is not True
            or not isinstance(result, dict) or result.get('allow') is not True
            or not isinstance(result.get('digest'), str)
            or not hmac.compare_digest(result['digest'], digest)):
        raise PayloadError('La compuerta no aprobó la huella exacta de este paso.')
    return snapshot['arguments']
