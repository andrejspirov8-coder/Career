from __future__ import annotations

from recruiter_graph_workflow import workflow_core_for_stage
from recruiter_models import WorkflowStage


def test_workflow_core_full_stage_sequence() -> None:
    stages = workflow_core_for_stage("all")
    assert stages[0] == WorkflowStage.DISCOVER
    assert stages[-1] == WorkflowStage.REPORT


def test_workflow_core_rank_stage() -> None:
    stages = workflow_core_for_stage("rank")
    assert stages == [WorkflowStage.ENRICH, WorkflowStage.RANK]
