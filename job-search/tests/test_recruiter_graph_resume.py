from __future__ import annotations

from career_job_search.recruiters.graph_workflow import workflow_core_for_stage
from career_job_search.recruiters.workflow_models import WorkflowStage


def test_workflow_core_for_dispatch_stage() -> None:
    stages = workflow_core_for_stage("dispatch")
    assert stages == [WorkflowStage.PREPARE_DISPATCH, WorkflowStage.DISPATCH]


def test_workflow_core_for_all_stage() -> None:
    stages = workflow_core_for_stage("all")
    assert WorkflowStage.DISCOVER in stages
    assert WorkflowStage.REPORT in stages
