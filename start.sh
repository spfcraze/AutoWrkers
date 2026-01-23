#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate

PORT="${ULTRACLAUDE_PORT:-8420}"
HOST="${ULTRACLAUDE_HOST:-0.0.0.0}"

echo "Starting UltraClaude on http://$HOST:$PORT"
echo "Press Ctrl+C to stop"
echo ""

python -m uvicorn src.server:app --host "$HOST" --port "$PORT"
