#!/bin/bash
# Start the AgentLens API (SQLite, zero setup). Run from apps/api/.
cd "$(dirname "$0")"
mkdir -p data
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
