#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python -m career_job_search.recruiters.orchestrator preflight --browse-status || true
uv run pytest -q
