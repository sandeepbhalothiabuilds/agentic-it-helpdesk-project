#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONPATH="/app:${PYTHONPATH:-}"
export STREAMLIT_SERVER_ADDRESS=0.0.0.0
export STREAMLIT_SERVER_PORT=8501
export STREAMLIT_SERVER_HEADLESS=true

cd /app

exec streamlit run /app/app/frontend/Streamlit_App.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true