#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1

python -m uvicorn app.backend.main:app \
  --host 0.0.0.0 \
  --port 8000
