#!/bin/bash
set -e

echo "============================================"
echo "  Claude Code Telemetry Analytics Platform"
echo "============================================"
export PYTHONPATH="${PYTHONPATH}:/app:."

# Step 0: Generate dataset if missing
if [ ! -f "output/telemetry_logs.jsonl" ]; then
    echo ""
    echo "[ENTRYPOINT] Dataset output/telemetry_logs.jsonl not found. Generating synthetic dataset..."
    python generate_fake_data.py --num-users 100 --num-sessions 5000 --days 60
fi

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

