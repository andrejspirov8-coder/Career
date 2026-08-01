#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_REQUIREMENTS="$(mktemp /tmp/job-search-runtime-requirements.XXXXXX.txt)"
RELEASE_LOCK="$ROOT_DIR/runtime/release-check.lock"
mkdir -p "$(dirname "$RELEASE_LOCK")"
if ! mkdir "$RELEASE_LOCK" 2>/dev/null; then
  echo "[verify] another release gate is already running" >&2
  exit 2
fi
cleanup() {
  rm -f "$RUNTIME_REQUIREMENTS"
  rmdir "$RELEASE_LOCK" 2>/dev/null || true
}
trap cleanup EXIT

cd "$ROOT_DIR"

echo "[verify] locked Python environment"
uv lock --check
uv sync --locked --all-groups

echo "[verify] Python lint and tests"
uv run ruff check tools cv tests
uv run --group dev pytest -q

echo "[verify] CV outputs"
uv run python cv/build_cv_pdf.py --all
uv run --group dev pytest -q tests/test_cv_build_validation.py

echo "[verify] Python runtime dependency audit"
uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file "$RUNTIME_REQUIREMENTS" > /dev/null
uvx pip-audit -r "$RUNTIME_REQUIREMENTS"

echo "[verify] dashboard"
(
  cd dashboard
  npm ci
  npm test
  npm run typecheck
  npm run build
  npx playwright install chromium
  CAREER_DASHBOARD_TOKEN=release-verification-token npm run e2e
  npm audit --audit-level=high
)

echo "[verify] repository smoke test"
./scripts/smoke_repo.sh

echo "[verify] all release checks passed"
