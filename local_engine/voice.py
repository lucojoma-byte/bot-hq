#!/usr/bin/env python3
"""Voz local JOE HQ: stdin JSON {command:diagnose|transcribe|synthesize,...}.

Transcribe fields: input_path, optional language (es by default). Files must be
inside /Volumes/JOE_HQ. Uses existing faster-whisper and frozen local weights,
never downloads or installs. VibeVoice reports missing runtime explicitly.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import re
import sys

VOLUME = Path('/Volumes/JOE_HQ')
MODELS = Path('/Volumes/WinMac_AI/AI-Models/hermes-huggingface/hub')
WHISPER = MODELS / 'models--Systran--faster-whisper-base/snapshots/ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66'
VIBE = MODELS / 'models--vibevoice--VibeVoice-1.5B/snapshots/d374386b2a51d8e05277a64d85b296c89ec52376'


def available(name):
    try:
        return bool(importlib.util.find_spec(name))
    except Exception:
        return False


def diagnosis():
    return {
        'stt': {'provider': 'faster-whisper', 'runtime': available('faster_whisper'),
                'weights': all((WHISPER / name).is_file() for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')),
                'model_path': str(WHISPER)},
        'tts': {'provider': 'VibeVoice', 'runtime': available('vibevoice') and available('torch'),
                'weights': all((VIBE / name).is_file() for name in ('config.json', 'model.safetensors.index.json',
                    'model-00001-of-00003.safetensors', 'model-00002-of-00003.safetensors', 'model-00003-of-00003.safetensors')),
                'model_path': str(VIBE)},
        'cloud_calls': False,
    }


def run(request):
    if not VOLUME.is_mount():
        return {'ok': False, 'error': 'El volumen /Volumes/JOE_HQ no está montado.'}
    sys.dont_write_bytecode = True
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
    command = request.get('command', 'diagnose')
    state = diagnosis()
    if command == 'diagnose':
        return {'ok': True, 'diagnosis': state,
                'limitations': [] if state['tts']['runtime'] else ['VibeVoice tiene pesos locales, pero falta el runtime compatible; TTS no está operativo.']}
    if command == 'synthesize':
        return {'ok': False, 'error': 'VibeVoice no está operativo: falta un runtime compatible probado. Los pesos locales por sí solos no generan audio.', 'diagnosis': state}
    if command != 'transcribe':
        return {'ok': False, 'error': 'Comando de voz desconocido.'}
    if not state['stt']['runtime'] or not state['stt']['weights']:
        return {'ok': False, 'error': 'Faster-whisper o sus pesos locales no están disponibles.', 'diagnosis': state}
    value = request.get('input_path')
    if not isinstance(value, str) or len(value) > 1024:
        return {'ok': False, 'error': 'Ruta de audio inválida.'}
    audio = Path(value)
    if not audio.is_absolute():
        return {'ok': False, 'error': 'La ruta de audio debe ser absoluta.'}
    audio = audio.resolve()
    if VOLUME not in audio.parents or not audio.is_file() or audio.stat().st_size > 30_000_000:
        return {'ok': False, 'error': 'Audio fuera del volumen, inexistente o mayor a 30 MB.'}
    language = request.get('language', 'es')
    if not isinstance(language, str) or not re.fullmatch(r'[a-z]{2,3}', language):
        return {'ok': False, 'error': 'Idioma inválido.'}
    from faster_whisper import WhisperModel
    model = WhisperModel(str(WHISPER), device='cpu', compute_type='int8', local_files_only=True)
    segments, info = model.transcribe(str(audio), language=language, beam_size=3, vad_filter=True,
                                      condition_on_previous_text=False, no_speech_threshold=0.6)
    text = ' '.join(segment.text.strip() for segment in segments if segment.avg_logprob > -1.0).strip()
    return {'ok': True, 'text': text, 'language': info.language, 'provider': 'faster-whisper', 'local': True}


def main():
    logging.disable(logging.CRITICAL)
    try:
        raw = sys.stdin.buffer.read(32_769)
        if len(raw) > 32_768:
            raise ValueError('size')
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError('object')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = run(request)
    except Exception as exc:
        result = {'ok': False, 'error': f'No fue posible procesar voz local ({type(exc).__name__}).'}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
