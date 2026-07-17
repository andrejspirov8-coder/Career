#!/bin/bash

# Career Workspace: Full Execution Cycle
# Scout → Plan → Dispatch → Analytics

set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_DIR="$BASE_DIR/pipeline"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🚀 CAREER WORKSPACE: FULL EXECUTION CYCLE"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📍 Phase 1: SCOUT (Discovering & Scoring Profiles)"
echo "────────────────────────────────────────────────────────────────"

cd "$BASE_DIR"

# Phase 1: Scout
echo "Starting scout..."
nohup uv run python3 tools/recruiter_orchestrate.py scout --headed > "$PIPELINE_DIR/scout.log" 2>&1 &
SCOUT_PID=$!

echo "✅ Scout running (PID: $SCOUT_PID)"
echo "📌 Monitor: tail -f $PIPELINE_DIR/scout.log"
echo ""
echo "⏳ Waiting for scout to complete..."

wait $SCOUT_PID

echo "✅ Scout complete"
PROFILE_COUNT=$(wc -l < "$PIPELINE_DIR/recruiter_action_plan.jsonl" 2>/dev/null || echo "0")
echo "✅ Profiles discovered: $PROFILE_COUNT"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "📍 Phase 2: PLAN (Building Dispatch Queue)"
echo "────────────────────────────────────────────────────────────────"
echo ""

uv run python3 tools/recruiter_orchestrate.py plan --tier tier_1 --tier tier_2

echo "✅ Plan complete"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "📍 Phase 3: DISPATCH (Preview - Dry Run)"
echo "────────────────────────────────────────────────────────────────"
echo ""

uv run python3 tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --dry-run

echo "✅ Dispatch preview complete"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "📍 Phase 4: ANALYTICS (Measuring Results)"
echo "────────────────────────────────────────────────────────────────"
echo ""

python3 tools/recruiter_quarterly_report.py --output "$PIPELINE_DIR/report.md"

echo "✅ Analytics report generated"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "🎉 FULL CYCLE COMPLETE"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📊 Results:"
echo "   • Scout: $PROFILE_COUNT profiles"
echo "   • Plan: $PIPELINE_DIR/recruiter_session_state.json"
echo "   • Analytics: $PIPELINE_DIR/report.md"
echo ""
