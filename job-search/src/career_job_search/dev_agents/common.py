#!/usr/bin/env python3
"""Safe local Ollama development-agent coordinator.

The coordinator is deliberately separate from job-search automation. It creates
an immutable snapshot of the current (possibly dirty) workspace, gives a local
Codex/Ollama process a disposable Git worktree, validates the resulting patch,
and requires a patch-hash review receipt before touching the active workspace.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from career_job_search.core.paths import PROJECT_ROOT
from career_job_search.dev_agents.models import (
    LocalAgentSettings,
)

JOB_ROOT = PROJECT_ROOT

DEFAULT_CONFIG_PATH = JOB_ROOT / "config" / "local_dev_agents.yaml"
DEFAULT_RUNTIME_ROOT = JOB_ROOT / "runtime" / "local-dev-agents"
DEFAULT_DB_PATH = DEFAULT_RUNTIME_ROOT / "agent_runs.sqlite3"
DEFAULT_WORKTREE_ROOT = Path.home() / ".career-local-agent-worktrees" / "job-search"
DEFAULT_BACKUP_ROOT = (
    Path.home() / ".career-agent-backups" / "job-search" / "agent-applies"
)

TASK_ID_PATTERN = re.compile(r"^agent_[a-f0-9]{32}$")
PROPOSAL_ID_PATTERN = re.compile(r"^proposal_[a-f0-9]{32}$")
PLANNER_RUN_ID_PATTERN = re.compile(r"^planner_[a-f0-9]{32}$")
ACTIVE_STATUSES = frozenset(
    {"queued", "snapshotting", "running", "local_review", "verifying"}
)
TERMINAL_STATUSES = frozenset(
    {
        "ready_for_codex_review",
        "approved",
        "applied",
        "blocked",
        "failed",
        "timed_out",
        "cancelled",
        "stale",
        "rejected",
    }
)
MAX_STREAM_CHARS = 2_000_000
MAX_PATCH_PREVIEW_CHARS = 400_000
BENCHMARK_MODEL_TIMEOUT_SECONDS = 300
PLANNER_POLICY_VERSION = "career_local_dev_planner_v1"
AUTO_APPLY_POLICY_VERSION = "career_local_auto_apply_v1"
CODEX_INNER_SANDBOX_MODE = "danger-full-access"
StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)
SENSITIVE_SNAPSHOT_BASENAMES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        "auth.json",
        "cookies.json",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "token.json",
    }
)
SENSITIVE_SNAPSHOT_SUFFIXES = (
    ".db",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
)

WRITE_FORBIDDEN_PATHS = (
    ".codex",
    ".github",
    ".gitignore",
    "AGENTS.md",
    "SECURITY.md",
    "pyproject.toml",
    "uv.lock",
    "config/local_dev_agents.yaml",
    "tools/local_dev_agents.py",
    "tools/local_dev_agent_models.py",
    "dashboard/lib/dashboard-auth.ts",
    "dashboard/app/api/auth",
    "dashboard/package.json",
    "dashboard/package-lock.json",
    "raycast-job-search-hub/package.json",
    "raycast-job-search-hub/package-lock.json",
    "scripts/verify_release.sh",
    "tools/linkedin",
    "linkedin",
)
SENSITIVE_OBJECTIVE_TERMS = (
    "authentication",
    "authorization",
    "password",
    "secret",
    "database migration",
    "schema migration",
    "dependency upgrade",
    "lockfile",
    "security policy",
    "agent policy",
    "database schema",
    "file deletion",
    "rename file",
    "deploy",
    "production release",
    "linkedin send",
    "linkedin dispatch",
    "git history",
    "force push",
)
SAFE_NPM_COMMANDS = {
    ("test",),
    ("run", "test"),
    ("run", "typecheck"),
    ("run", "lint"),
    ("run", "lint:ci"),
    ("run", "build"),
}
EXEC_POLICY_REJECTION_MARKERS = (
    "Git mutations are controlled by the coordinator",
    "Dependency installation is disabled",
    "External network tools are disabled",
    "Local agents may not control desktop applications or browsers",
    "Job-search and LinkedIn actions are outside development-agent scope",
    "Recruiter execution is outside development-agent scope",
)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS local_agent_runs (
  task_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  phase TEXT NOT NULL,
  role TEXT NOT NULL,
  model TEXT NOT NULL,
  model_digest TEXT,
  proposal_id TEXT,
  task_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  snapshot_commit TEXT,
  worktree_path TEXT,
  run_dir TEXT NOT NULL,
  patch_path TEXT,
  patch_sha256 TEXT,
  reviewed_patch_sha256 TEXT,
  reviewed_by TEXT,
  reviewed_at TEXT,
  child_pid INTEGER,
  attempt INTEGER NOT NULL DEFAULT 0,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  result_json TEXT NOT NULL DEFAULT '{}',
  local_review_json TEXT NOT NULL DEFAULT '{}',
  secondary_review_json TEXT NOT NULL DEFAULT '{}',
  verification_json TEXT NOT NULL DEFAULT '[]',
  post_apply_verification_json TEXT NOT NULL DEFAULT '[]',
  first_pass_ok INTEGER NOT NULL DEFAULT 0,
  approval_policy TEXT,
  auto_apply_receipt_json TEXT NOT NULL DEFAULT '{}',
  error TEXT NOT NULL DEFAULT '',
  safety_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_local_agent_runs_status
ON local_agent_runs(status, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_local_agent_runs_proposal
ON local_agent_runs(proposal_id)
WHERE proposal_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS local_agent_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  safe_applied_runs INTEGER NOT NULL DEFAULT 0,
  local_first_enabled INTEGER NOT NULL DEFAULT 0,
  qualified_at TEXT,
  selected_implementer_model TEXT,
  selected_implementer_digest TEXT,
  qualification_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_agent_model_qualifications (
  model_tag TEXT NOT NULL,
  model_digest TEXT NOT NULL,
  qualified INTEGER NOT NULL DEFAULT 0,
  qualified_at TEXT,
  qualification_json TEXT NOT NULL DEFAULT '{}',
  safe_applied_runs INTEGER NOT NULL DEFAULT 0,
  safe_apply_streak INTEGER NOT NULL DEFAULT 0,
  total_applied_runs INTEGER NOT NULL DEFAULT 0,
  first_pass_applied_runs INTEGER NOT NULL DEFAULT 0,
  scope_violations INTEGER NOT NULL DEFAULT 0,
  privacy_violations INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(model_tag, model_digest)
);

CREATE TABLE IF NOT EXISTS local_agent_planner_runs (
  planner_run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  trigger_source TEXT NOT NULL,
  scheduled_for TEXT,
  status TEXT NOT NULL,
  model TEXT NOT NULL,
  model_digest TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  result_json TEXT NOT NULL DEFAULT '{}',
  error TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(task_id) REFERENCES local_agent_runs(task_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_local_agent_planner_schedule
ON local_agent_planner_runs(scheduled_for)
WHERE scheduled_for IS NOT NULL;

CREATE TABLE IF NOT EXISTS local_agent_proposals (
  proposal_id TEXT PRIMARY KEY,
  planner_run_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  status TEXT NOT NULL,
  category TEXT NOT NULL,
  objective TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  allowed_paths_json TEXT NOT NULL,
  check_preset TEXT NOT NULL,
  risk TEXT NOT NULL,
  priority TEXT NOT NULL,
  estimated_files INTEGER NOT NULL,
  estimated_diff_lines INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  approved_at TEXT,
  rejected_at TEXT,
  task_id TEXT,
  FOREIGN KEY(planner_run_id) REFERENCES local_agent_planner_runs(planner_run_id),
  FOREIGN KEY(task_id) REFERENCES local_agent_runs(task_id)
);

CREATE INDEX IF NOT EXISTS idx_local_agent_proposals_status
ON local_agent_proposals(status, priority, created_at);

CREATE TABLE IF NOT EXISTS local_agent_autonomy (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  tier INTEGER NOT NULL DEFAULT 0,
  auto_apply_enabled INTEGER NOT NULL DEFAULT 0,
  manually_paused INTEGER NOT NULL DEFAULT 0,
  paused_reason TEXT NOT NULL DEFAULT '',
  last_evaluated_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_agent_service (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  pid INTEGER,
  status TEXT NOT NULL DEFAULT 'stopped',
  started_at TEXT,
  heartbeat_at TEXT,
  next_planner_at TEXT,
  last_planner_at TEXT,
  last_defer_reason TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class CoordinatorPaths:
    repo_root: Path = JOB_ROOT
    runtime_root: Path = DEFAULT_RUNTIME_ROOT
    db_path: Path = DEFAULT_DB_PATH
    worktree_root: Path = DEFAULT_WORKTREE_ROOT
    backup_root: Path = DEFAULT_BACKUP_ROOT
    config_path: Path = DEFAULT_CONFIG_PATH


@dataclass(frozen=True)
class SnapshotInfo:
    commit: str
    tree: str
    worktree: Path
    manifest_path: Path
    excluded_paths: tuple[str, ...]


@dataclass(frozen=True)
class PatchInfo:
    path: Path
    sha256: str
    changed_files: tuple[str, ...]
    statuses: dict[str, str]
    diff_lines: int


class CoordinatorError(RuntimeError):
    """A safe, user-displayable coordinator failure."""


class AgentProcessError(CoordinatorError):
    def __init__(self, message: str, *, status: str = "failed") -> None:
        super().__init__(message)
        self.status = status


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def atomic_write_text(path: Path, value: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        temp_path.chmod(mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def atomic_write_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        mode=mode,
    )


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> LocalAgentSettings:
    if not path.is_file():
        raise CoordinatorError(f"Local-agent configuration is missing: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return LocalAgentSettings.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise CoordinatorError(f"Invalid local-agent configuration: {exc}") from exc
