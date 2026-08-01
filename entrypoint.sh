#!/bin/bash
set -e

echo "============================================"
echo "  Claude Code Telemetry Analytics Platform"
echo "============================================"

# Step 1: Run ingestion pipeline (idempotent)
echo ""
echo "[ENTRYPOINT] Running ingestion pipeline..."
python -m src.ingestion

# Step 2: Launch Streamlit dashboard
echo ""
echo "[ENTRYPOINT] Starting Streamlit dashboard on port 8501..."
exec streamlit run src/app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
