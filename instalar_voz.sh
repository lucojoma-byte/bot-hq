#!/bin/bash
# Instala (una sola vez) el entorno de voz de salida: torch + VibeVoice, todo dentro de JOE_HQ.
# Uso:  bash /Volumes/JOE_HQ/app/instalar_voz.sh
# Requiere: uv, Python 3.11 de Homebrew y el código de VibeVoice en ~/code/VibeVoice (ya presentes en esta Mac).
set -euo pipefail
/sbin/mount | grep -q ' on /Volumes/JOE_HQ ' || { echo "Conecta el disco JOE_HQ primero." >&2; exit 1; }
cd /Volumes/JOE_HQ/app
export UV_CACHE_DIR=/Volumes/JOE_HQ/cache/uv UV_PYTHON_INSTALL_DIR=/Volumes/JOE_HQ/cache/uv-python
export TMPDIR=/Volumes/JOE_HQ/cache/tmp PIP_CACHE_DIR=/Volumes/JOE_HQ/cache/pip
PY=/opt/homebrew/opt/python@3.11/bin/python3.11
FUENTE="${VIBEVOICE_SRC:-$HOME/code/VibeVoice}"
[ -x "$PY" ] || { echo "Falta Python 3.11 (brew install python@3.11)." >&2; exit 1; }
[ -d "$FUENTE/vibevoice" ] || { echo "No encuentro el código de VibeVoice en $FUENTE." >&2; exit 1; }
[ -d .venv-voz ] || uv venv .venv-voz --python "$PY"
uv pip install --python .venv-voz/bin/python "torch==2.14.0" "transformers==4.51.3" "accelerate==1.6.0" \
  "diffusers==0.39.0" numpy scipy librosa soundfile ml-collections absl-py tqdm
uv pip install --python .venv-voz/bin/python --no-deps "$FUENTE"
mkdir -p /Volumes/JOE_HQ/data/voces
for v in en-Carter_man:carter en-Alice_woman:alice; do
  [ -f "/Volumes/JOE_HQ/data/voces/${v#*:}.wav" ] || cp "$FUENTE/demo/voices/${v%%:*}.wav" "/Volumes/JOE_HQ/data/voces/${v#*:}.wav"
done
.venv-voz/bin/python -c "import torch, vibevoice; print('Voz lista. torch', torch.__version__, '| MPS:', torch.backends.mps.is_available())"
echo "Para usar tu propia voz en español: guarda un WAV de 10 a 30 s en /Volumes/JOE_HQ/data/voces/ (ej. joe.wav) y elígelo en Apps → Voz local."
