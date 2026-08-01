#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_JOB="inbox/jobs/.smoke-repo-$$.job.txt"
DASH_LOG="/tmp/job-search-dashboard-$$.log"
DASH_COOKIE="/tmp/job-search-dashboard-cookie-$$.txt"
DASH_TOKEN="smoke-dashboard-token"
DASH_PID=""
cleanup() {
  if [[ -n "$DASH_PID" ]]; then
    kill "$DASH_PID" > /dev/null 2>&1 || true
  fi
  rm -f "$TMP_JOB" "$DASH_COOKIE" "$DASH_LOG"
}
trap cleanup EXIT

echo "[smoke] pytest"
uv run pytest -q

echo "[smoke] dashboard build"
node -e "require('fs').rmSync('dashboard/.next', { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })"
if [[ -d dashboard/node_modules ]]; then
  (cd dashboard && npm run build)
else
  (cd dashboard && npm ci && npm run build)
fi

echo "[smoke] dashboard runtime"
(cd dashboard && CAREER_DASHBOARD_TOKEN="$DASH_TOKEN" npm run start -- --port 3010 > "$DASH_LOG" 2>&1) &
DASH_PID=$!
sleep 6
test "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3010/api/overview)" = "401"
test "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3010/recruiters)" = "307"
test "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3010/notifications)" = "307"
curl -fsS \
  -c "$DASH_COOKIE" \
  -H 'Origin: http://127.0.0.1:3010' \
  -H 'Content-Type: application/json' \
  -d '{"token":"smoke-dashboard-token"}' \
  http://127.0.0.1:3010/api/auth/login > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/ > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/api/overview > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/api/notifications/overview > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/api/cvs/studio/business-process-operations > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/notifications > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/drilldown/cv > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/drilldown/packs > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/drilldown/pipeline > /dev/null
curl -fsS -b "$DASH_COOKIE" http://127.0.0.1:3010/drilldown/workflows > /dev/null

echo "[smoke] cv build"
uv run python cv/build_cv_pdf.py --all

echo "[smoke] recruiter preflight"
uv run python -m career_job_search.recruiters.orchestrator preflight --browse-status

echo "[smoke] batch match dry-run"
cat > "$TMP_JOB" <<'EOF'
TITLE: Smoke Test Job
COMPANY: Smoke Corp
URL: https://example.com/jobs/smoke-test-job
SOURCE: smoke
JOB_ID: smoke-test-job

---
Smoke test role for validating batch matching, pack generation, and summary reporting.

Requirements:
* premium retail leadership
* operations management
* Vilnius or Lithuania context
EOF
uv run python -m career_job_search.opportunities.batch --dry-run --pattern "$(basename "$TMP_JOB")"

echo "[smoke] mcp payload shape"
uv run python - <<'PY'
from mcp.server import score_recruiter_payload
payload = score_recruiter_payload({
    "headline": "Talent Acquisition Manager",
    "name": "Smoke Tester",
    "profile_url": "https://www.linkedin.com/in/smoke-tester/",
    "company": "Smoke Corp",
    "about": "Hiring premium retail leaders in Vilnius",
    "role_text": "Head of People",
    "location": "Vilnius, Lithuania",
})
assert isinstance(payload, dict)
assert "would_send" in payload
assert "primary_score" in payload
print("ok")
PY

echo "[smoke] done"
