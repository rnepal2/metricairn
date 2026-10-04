#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec uv run uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 "$@"
