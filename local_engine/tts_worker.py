#!/usr/bin/env python3
"""Voz de salida local con VibeVoice-1.5B. Proceso residente, sin red.

Se ejecuta con el entorno propio /Volumes/JOE_HQ/app/.venv-voz (torch + vibevoice);
el Python de Hermes NO trae estos paquetes: ese era el componente que faltaba.

Protocolo: una línea JSON por petición en stdin
    {"id": "...", "text": "...", "voice": "/ruta/voz.wav", "out": "/ruta/salida.wav"}
y una línea JSON por respuesta en stdout. Primera línea al arrancar: {"ready": true, ...}.
Los pesos se leen de /Volumes/WinMac_AI/AI-Models (ya descargados); HF queda sin conexión.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time

VOLUME = Path('/Volumes/JOE_HQ')
HUB = Path('/Volumes/WinMac_AI/AI-Models/hermes-huggingface/hub')
MODEL = HUB / 'models--vibevoice--VibeVoice-1.5B/snapshots/d374386b2a51d8e05277a64d85b296c89ec52376'
QWEN = HUB / 'models--Qwen--Qwen2.5-1.5B/snapshots'
MAX_CHARS = 1200

# El procesador pide el tokenizador por nombre («Qwen/Qwen2.5-1.5B»): se resuelve sin red
# apuntando la caché de Hugging Face al disco donde ya están los modelos.
os.environ.update({'HF_HUB_CACHE': str(HUB), 'HUGGINGFACE_HUB_CACHE': str(HUB),
                   'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
                   'HF_HUB_DISABLE_PROGRESS_BARS': '1', 'PYTORCH_ENABLE_MPS_FALLBACK': '1',
                   'TOKENIZERS_PARALLELISM': 'false', 'PYTHONDONTWRITEBYTECODE': '1'})
sys.dont_write_bytecode = True

protocol = sys.stdout          # canal limpio para el servidor
sys.stdout = sys.stderr        # todo lo que impriman las librerías va a stderr


def emit(payload):
    protocol.write(json.dumps(payload, ensure_ascii=False) + '\n')
    protocol.flush()


def inside_volume(value):
    path = Path(str(value)).resolve()
    return path if VOLUME in path.parents else None


def speakable(text):
    """Texto plano para leer en voz alta: sin markdown, URLs ni símbolos."""
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'https?://\S+', ' enlace ', text)
    text = re.sub(r'[*_#`>|\[\]{}~^]+', ' ', text)
    text = re.sub(r'^\s*[-•·]\s+', '', text, flags=re.M)
    text = re.sub(r'\s*\n+\s*', '. ', text)
    text = re.sub(r'\s+', ' ', text).replace('..', '.').strip()
    text = text.replace(':', ',')  # «Speaker N:» es sintaxis reservada del modelo
    if len(text) > MAX_CHARS:
        cut = text[:MAX_CHARS]
        text = cut[:max(cut.rfind('. '), cut.rfind(', '), MAX_CHARS - 200) + 1].strip()
    return text


def load():
    import torch
    from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference
    from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor
    if not (MODEL / 'config.json').is_file():
        raise RuntimeError('No se encontraron los pesos de VibeVoice en WinMac_AI. ¿Está conectado ese disco?')
    snapshots = sorted(p for p in QWEN.iterdir() if (p / 'tokenizer.json').is_file()) if QWEN.is_dir() else []
    if not snapshots:
        raise RuntimeError('Falta el tokenizador Qwen2.5-1.5B local que usa VibeVoice.')
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    processor = VibeVoiceProcessor.from_pretrained(str(MODEL))
    dtype = torch.float16 if (device == 'mps' and os.environ.get('JOE_HQ_TTS_DTYPE', 'float16') == 'float16') else torch.float32
    model = VibeVoiceForConditionalGenerationInference.from_pretrained(
        str(MODEL), torch_dtype=dtype, attn_implementation='sdpa', device_map=None)
    model.to(device)
    model.eval()
    model.set_ddpm_inference_steps(num_steps=int(os.environ.get('JOE_HQ_TTS_STEPS', '8')))
    return torch, processor, model, device, str(dtype).replace('torch.', '')


def synthesize(state, request):
    torch, processor, model, device, _ = state
    text = speakable(str(request.get('text') or ''))
    if not text:
        return {'ok': False, 'error': 'No hay texto que leer.'}
    voice = inside_volume(request.get('voice'))
    out = inside_volume(request.get('out'))
    if not voice or not voice.is_file() or voice.suffix.lower() != '.wav':
        return {'ok': False, 'error': 'Voz de referencia no encontrada dentro de JOE_HQ.'}
    if not out or out.suffix.lower() != '.wav':
        return {'ok': False, 'error': 'Ruta de salida inválida.'}
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.time()
    inputs = processor(text=['Speaker 1: ' + text], voice_samples=[[str(voice)]], padding=True,
                       return_tensors='pt', return_attention_mask=True)
    for key, value in inputs.items():
        if torch.is_tensor(value):
            inputs[key] = value.to(device)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=None, cfg_scale=1.3, tokenizer=processor.tokenizer,
                                 generation_config={'do_sample': False}, verbose=False, is_prefill=True)
    audio = outputs.speech_outputs[0] if outputs.speech_outputs else None
    if audio is None:
        return {'ok': False, 'error': 'VibeVoice no devolvió audio.'}
    processor.save_audio(audio, output_path=str(out))
    os.chmod(out, 0o600)
    samples = audio.shape[-1]
    return {'ok': True, 'path': str(out), 'audio_seconds': round(samples / 24000, 2),
            'compute_seconds': round(time.time() - started, 1), 'chars': len(text), 'provider': 'VibeVoice-1.5B', 'local': True}


def main():
    if not VOLUME.is_mount():
        emit({'ready': False, 'error': 'El volumen /Volumes/JOE_HQ no está montado.'})
        return 1
    started = time.time()
    try:
        state = load()
    except Exception as exc:
        emit({'ready': False, 'error': f'VibeVoice no pudo cargar ({type(exc).__name__}): {str(exc)[:300]}'})
        return 1
    emit({'ready': True, 'device': state[3], 'dtype': state[4], 'load_seconds': round(time.time() - started, 1)})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            emit({'ok': False, 'error': 'Petición inválida.'})
            continue
        try:
            result = synthesize(state, request)
        except Exception as exc:
            result = {'ok': False, 'error': f'No se pudo generar la voz ({type(exc).__name__}): {str(exc)[:200]}'}
        result['id'] = request.get('id')
        emit(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
