from __future__ import annotations

from recruiter_models import CandidateProfile, WorkflowMode, WorkflowRun, WorkflowStage


def test_candidate_profile_canonicalises_url() -> None:
    profile = CandidateProfile(profile_url="linkedin.com/in/example-person/")
    assert profile.profile_url == "https://www.linkedin.com/in/example-person"


def test_workflow_run_defaults() -> None:
    run = WorkflowRun(run_id="run-1")
    assert run.mode == WorkflowMode.DRY_RUN
    assert run.dry_run is True
    assert run.stages == []


def test_workflow_stage_values() -> None:
    assert WorkflowStage.DISCOVER.value == "discover"
    assert WorkflowStage.DISPATCH.value == "dispatch"
