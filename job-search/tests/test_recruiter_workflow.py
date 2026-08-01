from __future__ import annotations

from career_job_search.recruiters.run_state import initial_snapshot
from career_job_search.recruiters.workflow import (
    initialise_run_state,
    is_terminal,
    next_stage,
    pipeline_stages,
    resume_from_snapshot,
)
from career_job_search.recruiters.workflow_models import WorkflowMode, WorkflowStage


def test_pipeline_stages_order() -> None:
    assert pipeline_stages()[0] == WorkflowStage.DISCOVER
    assert pipeline_stages()[-1] == WorkflowStage.REPORT


def test_next_stage_progression() -> None:
    assert next_stage(WorkflowStage.DISCOVER) == WorkflowStage.VALIDATE
    assert next_stage(WorkflowStage.REPORT) is None


def test_initialise_run_state_builds_steps() -> None:
    run = initialise_run_state("run-1", mode=WorkflowMode.LIVE)
    assert run.mode == WorkflowMode.LIVE
    assert len(run.stages) == len(pipeline_stages())


def test_resume_from_snapshot_trims_future_steps() -> None:
    run = initialise_run_state("run-2")
    snapshot = initial_snapshot(run, WorkflowStage.ENRICH)
    resumed = resume_from_snapshot(snapshot)
    assert len(resumed.stages) == 3


def test_terminal_stage() -> None:
    assert is_terminal(WorkflowStage.REPORT) is True
