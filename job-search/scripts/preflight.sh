#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python tools/recruiter_orchestrate.py preflight --browse-status || true
uv run pytest -q
