#!/bin/bash
set -euo pipefail
cd /Volumes/JOE_HQ/app
export PYTHONDONTWRITEBYTECODE=1
exec /opt/homebrew/bin/python3 -B server.py "$@"
