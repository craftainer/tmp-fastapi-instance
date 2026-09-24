#!/usr/bin/env bash
# Entrypoint for the `runner` stage: starts the application.
set -euo pipefail

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
