#!/bin/bash
# Run PycrashAI locally without Docker (for quick testing)
# Usage: ./platform/run_local.sh
#
# This starts the FastAPI server directly. No Redis/Celery needed
# for sync endpoints (/simulate/sdof/sync, /extract, /vehicles/lookup).
# Async endpoints (/simulate/sdof, /montecarlo) require Docker.

set -e

cd "$(dirname "$0")/.."

echo "=== PycrashAI Local Dev Server ==="
echo ""
echo "Starting FastAPI on http://localhost:8000"
echo "API docs at http://localhost:8000/docs"
echo ""
echo "Quick test:"
echo '  curl -X POST http://localhost:8000/api/v1/simulate/sdof/sync \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '\''{"w1":3400,"w2":2900,"v1":30,"v2":0,"cor":0.15,"k":50000,"tstop":0.5}'\'''
echo ""

pip install -e "." -q 2>/dev/null
pip install fastapi uvicorn python-multipart pydantic -q 2>/dev/null

uvicorn pycrash_ai.api.main:app --host 0.0.0.0 --port 8000 --reload
