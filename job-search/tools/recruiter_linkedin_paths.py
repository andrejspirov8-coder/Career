"""Shared filesystem paths for LinkedIn recruiter tooling."""

from __future__ import annotations

from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
JOB_ROOT = TOOLS_DIR.parent
PIPELINE_DIR = JOB_ROOT / "pipeline"
CV_DIR = JOB_ROOT / "cv"

# Persistent Chrome automation profile (Playwright + WS-backed browse backend).
PROFILE_DIR = JOB_ROOT / "linkedin" / ".browser-profile"
RUN_LOGS_DIR = JOB_ROOT / "linkedin" / "run_logs"

DEFAULT_LINKEDIN_CONFIG = JOB_ROOT / "linkedin" / "config.yaml"
RECRUITERS_CSV = PIPELINE_DIR / "recruiters.csv"
ACTION_PLAN_JSONL = PIPELINE_DIR / "recruiter_action_plan.jsonl"
SESSION_STATE_JSON = PIPELINE_DIR / "recruiter_session_state.json"
OUTREACH_LOG_CSV = PIPELINE_DIR / "recruiter_outreach_log.csv"
HIRING_NETWORK_ACTION_PLAN_JSONL = PIPELINE_DIR / "hiring_network_action_plan.jsonl"
HIRING_NETWORK_RUN_STATE_JSON = PIPELINE_DIR / "hiring_network_run_state.json"
MCP_DISCOVERY_BATCH_JSONL = PIPELINE_DIR / "mcp_discovery_batch.jsonl"
CANDIDATES_DISCOVERY_CSV = PIPELINE_DIR / "candidates_discovery.csv"
CANDIDATES_VALIDATED_CSV = PIPELINE_DIR / "candidates_validated.csv"
LLM_TRACE_JSONL = PIPELINE_DIR / "llm_trace.jsonl"

FRESH_RUN_ARTIFACTS = (
    ACTION_PLAN_JSONL,
    HIRING_NETWORK_ACTION_PLAN_JSONL,
    HIRING_NETWORK_RUN_STATE_JSON,
)


def clear_fresh_run_artifacts() -> list[Path]:
    """Truncate action-plan JSONL files so a new run does not merge stale rows."""
    cleared: list[Path] = []
    for path in FRESH_RUN_ARTIFACTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        cleared.append(path)
    return cleared
