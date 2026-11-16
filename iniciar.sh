#!/bin/bash
# JOE HQ — arranque de un solo comando:  bash /Volumes/JOE_HQ/app/iniciar.sh
# Opciones:  --doctor (diagnóstico sin arrancar)   --staging (ensayo en el puerto 8788)
set -euo pipefail
if ! /sbin/mount | grep -q ' on /Volumes/JOE_HQ '; then
  echo "JOE HQ no puede iniciar: el disco JOE_HQ no está conectado (/Volumes/JOE_HQ)." >&2
  echo "Conéctalo y vuelve a ejecutar este comando. No se guarda nada en el disco interno." >&2
  exit 1
fi
cd /Volumes/JOE_HQ/app
PUERTO=8787; [[ " $* " == *" --staging "* ]] && PUERTO=8788
if [[ " $* " != *" --doctor "* ]] && /usr/sbin/lsof -nP -iTCP:$PUERTO -sTCP:LISTEN >/dev/null 2>&1; then
  echo "JOE HQ ya está corriendo. Ábrelo en http://127.0.0.1:$PUERTO"
  exit 0
fi
export PYTHONDONTWRITEBYTECODE=1
exec /opt/homebrew/bin/python3 -B server.py "$@"
