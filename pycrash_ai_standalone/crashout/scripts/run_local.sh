#!/bin/bash
# Run Crashout locally without Docker (for quick testing)
# Usage: ./crashout/scripts/run_local.sh
#
# This starts the FastAPI server directly. No Redis/Celery needed
# for sync endpoints (/simulate/sdof/sync, /extract, /vehicles/lookup).
# Async endpoints (/simulate/sdof, /montecarlo) require Docker.

set -e

cd "$(dirname "$0")/../.."

echo "=== Crashout Local Dev Server ==="
echo ""
echo "Starting FastAPI on http://localhost:8100"
echo "API docs at http://localhost:8100/docs"
echo ""
echo "Quick test:"
echo '  curl -X POST http://localhost:8100/api/v1/simulate/sdof/sync \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '\''{"w1":3400,"w2":2900,"v1":30,"v2":0,"cor":0.15,"k":50000,"tstop":0.5}'\'''
echo ""

pip install -e "." -q 2>/dev/null
pip install fastapi uvicorn python-multipart pydantic -q 2>/dev/null

uvicorn crashout.app:app --host 0.0.0.0 --port 8100 --reload
