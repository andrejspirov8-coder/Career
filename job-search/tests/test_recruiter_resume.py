from __future__ import annotations

from recruiter_models import WorkflowStage
from recruiter_run_state import initial_snapshot
from recruiter_workflow import initialise_run_state, resume_from_snapshot


def test_resume_from_snapshot_keeps_current_stage() -> None:
    run = initialise_run_state("resume-run")
    snapshot = initial_snapshot(run, WorkflowStage.VALIDATE)
    resumed = resume_from_snapshot(snapshot)
    assert resumed.stages[-1].stage == WorkflowStage.VALIDATE
