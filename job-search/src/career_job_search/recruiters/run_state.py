"""Persistence helpers for workflow run state and audit snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from career_job_search.recruiters.workflow_models import (
    WorkflowRun,
    WorkflowStage,
    WorkflowStateSnapshot,
)

JOB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_STATE_DIR = JOB_ROOT / "state"
DEFAULT_RUN_STATE_JSON = DEFAULT_RUN_STATE_DIR / "workflow_run_state.json"


def save_run_state(run: WorkflowRun, path: Path = DEFAULT_RUN_STATE_JSON) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_run_state(path: Path = DEFAULT_RUN_STATE_JSON) -> WorkflowRun | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return WorkflowRun.model_validate(raw)


def save_snapshot(
    snapshot: WorkflowStateSnapshot, path: Path = DEFAULT_RUN_STATE_JSON
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_snapshot(path: Path = DEFAULT_RUN_STATE_JSON) -> WorkflowStateSnapshot | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return WorkflowStateSnapshot.model_validate(raw)


def initial_snapshot(run: WorkflowRun, stage: WorkflowStage) -> WorkflowStateSnapshot:
    return WorkflowStateSnapshot(run=run, current_stage=stage)


def update_snapshot_errors(
    snapshot: WorkflowStateSnapshot,
    *,
    blockers: list[str] | None = None,
    errors: list[str] | None = None,
) -> WorkflowStateSnapshot:
    data: dict[str, Any] = snapshot.model_dump()
    if blockers is not None:
        data["blockers"] = list(blockers)
    if errors is not None:
        data["errors"] = list(errors)
    return WorkflowStateSnapshot.model_validate(data)


def advance_snapshot_stage(
    snapshot: WorkflowStateSnapshot,
    next_stage: WorkflowStage,
) -> WorkflowStateSnapshot:
    data: dict[str, Any] = snapshot.model_dump()
    data["current_stage"] = next_stage
    return WorkflowStateSnapshot.model_validate(data)


def snapshot_run_id(snapshot: WorkflowStateSnapshot) -> str:
    return snapshot.run.run_id
