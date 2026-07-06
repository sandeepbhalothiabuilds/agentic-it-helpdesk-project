#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
export STREAMLIT_SERVER_ADDRESS=0.0.0.0
export STREAMLIT_SERVER_PORT=8501

streamlit run app/frontend/Streamlit_App.py \
  --server.address 0.0.0.0 \
  --server.port 8501
