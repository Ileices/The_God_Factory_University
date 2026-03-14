#!/usr/bin/env bash
# ── The God Factory University: Start (macOS / Linux) ──────────────────────────────
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[START] Environment missing. Running setup first..."
    bash setup.sh
fi

source .venv/bin/activate

python -c "from core.database import init_db; init_db()" 2>/dev/null || true

echo "[START] Launching The God Factory University..."
streamlit run app.py --server.headless false
