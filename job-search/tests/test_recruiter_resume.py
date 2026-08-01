from __future__ import annotations

from career_job_search.recruiters.run_state import initial_snapshot
from career_job_search.recruiters.workflow import (
    initialise_run_state,
    resume_from_snapshot,
)
from career_job_search.recruiters.workflow_models import WorkflowStage


def test_resume_from_snapshot_keeps_current_stage() -> None:
    run = initialise_run_state("resume-run")
    snapshot = initial_snapshot(run, WorkflowStage.VALIDATE)
    resumed = resume_from_snapshot(snapshot)
    assert resumed.stages[-1].stage == WorkflowStage.VALIDATE
