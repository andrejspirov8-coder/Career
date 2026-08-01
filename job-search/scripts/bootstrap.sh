#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 2
fi

echo "[bootstrap] locked Python environment"
uv sync --locked --all-groups

echo "[bootstrap] Python browser runtime"
uv run playwright install chromium

echo "[bootstrap] dashboard dependencies"
(
  cd dashboard
  npm ci
  npx playwright install chromium
)

echo "[bootstrap] complete; run make preflight or make verify-release to verify the checkout"
