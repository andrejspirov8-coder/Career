#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[verify-patch] running focused tests"
uv run --group dev pytest -q \
  tests/test_mcp_server.py \
  tests/test_cv_build_validation.py \
  tests/test_recruiter_match_helpers.py \
  tests/test_variant_performance.py

echo "[verify-patch] running full test suite"
uv run --group dev pytest -q

echo "[verify-patch] running recruiter preflight"
uv run --group dev python -m career_job_search.recruiters.orchestrator preflight --browse-status

echo "[verify-patch] rebuilding CVs"
uv run --group dev python cv/build_cv_pdf.py --all

echo "[verify-patch] done"
