from __future__ import annotations

from recruiter_models import WorkflowMode, WorkflowStage
from recruiter_run_state import (
    advance_snapshot_stage,
    initial_snapshot,
    load_run_state,
    load_snapshot,
    save_run_state,
    save_snapshot,
    snapshot_run_id,
)
from recruiter_workflow import initialise_run_state


def test_save_and_load_run_state(tmp_path):
    run = initialise_run_state("run-1", mode=WorkflowMode.LIVE)
    path = tmp_path / "run.json"
    save_run_state(run, path)
    loaded = load_run_state(path)
    assert loaded is not None
    assert loaded.run_id == "run-1"
    assert loaded.mode == WorkflowMode.LIVE


def test_initial_snapshot(tmp_path):
    run = initialise_run_state("run-2")
    snapshot = initial_snapshot(run, WorkflowStage.DISCOVER)
    path = tmp_path / "snapshot.json"
    save_snapshot(snapshot, path)
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.current_stage == WorkflowStage.DISCOVER


def test_advance_snapshot_stage() -> None:
    run = initialise_run_state("run-3")
    snapshot = initial_snapshot(run, WorkflowStage.DISCOVER)
    advanced = advance_snapshot_stage(snapshot, WorkflowStage.VALIDATE)
    assert advanced.current_stage == WorkflowStage.VALIDATE
    assert snapshot_run_id(advanced) == "run-3"
