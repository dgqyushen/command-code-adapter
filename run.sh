#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
    echo "Loading .env file..."
    set -a
    source .env
    set +a
fi

LOG_LEVEL="${CC_ADAPTER_LOG_LEVEL:-info}"
LOG_LEVEL="$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"

exec poetry run uvicorn cc_adapter.main:app \
    --host "${CC_ADAPTER_HOST:-0.0.0.0}" \
    --port "${CC_ADAPTER_PORT:-8080}" \
    --log-level "$LOG_LEVEL"
