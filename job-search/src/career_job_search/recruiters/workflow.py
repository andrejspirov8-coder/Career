"""Deterministic workflow core for recruiter/job-search orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from career_job_search.recruiters.workflow_models import (
    WorkflowMode,
    WorkflowRun,
    WorkflowStage,
    WorkflowStateSnapshot,
    WorkflowStep,
)


@dataclass
class WorkflowTransition:
    stage: WorkflowStage
    next_stage: WorkflowStage | None
    allowed_modes: set[WorkflowMode] = field(
        default_factory=lambda: {WorkflowMode.DRY_RUN, WorkflowMode.LIVE}
    )
    blockers: list[str] = field(default_factory=list)


DEFAULT_PIPELINE: list[WorkflowStage] = [
    WorkflowStage.DISCOVER,
    WorkflowStage.VALIDATE,
    WorkflowStage.ENRICH,
    WorkflowStage.RANK,
    WorkflowStage.PREPARE_DISPATCH,
    WorkflowStage.DISPATCH,
    WorkflowStage.FOLLOW_UP,
    WorkflowStage.REPORT,
]


def pipeline_stages() -> list[WorkflowStage]:
    return list(DEFAULT_PIPELINE)


def build_run(run_id: str, *, mode: WorkflowMode = WorkflowMode.DRY_RUN) -> WorkflowRun:
    return WorkflowRun(run_id=run_id, mode=mode, dry_run=mode == WorkflowMode.DRY_RUN)


def add_step(
    run: WorkflowRun, stage: WorkflowStage, *, status: str = "pending"
) -> WorkflowRun:
    run.stages.append(WorkflowStep(stage=stage, status=status))
    return run


def stage_index(stage: WorkflowStage) -> int:
    try:
        return DEFAULT_PIPELINE.index(stage)
    except ValueError:
        return -1


def next_stage(stage: WorkflowStage) -> WorkflowStage | None:
    idx = stage_index(stage)
    if idx < 0 or idx + 1 >= len(DEFAULT_PIPELINE):
        return None
    return DEFAULT_PIPELINE[idx + 1]


def run_transition(
    *,
    current: WorkflowStage,
    mode: WorkflowMode,
    blockers: Iterable[str] | None = None,
) -> WorkflowTransition:
    blockers_list = list(blockers or [])
    nxt = next_stage(current)
    if blockers_list:
        return WorkflowTransition(
            stage=current, next_stage=None, blockers=blockers_list
        )
    return WorkflowTransition(stage=current, next_stage=nxt)


def is_terminal(stage: WorkflowStage) -> bool:
    return next_stage(stage) is None


def initialise_run_state(
    run_id: str, *, mode: WorkflowMode = WorkflowMode.DRY_RUN
) -> WorkflowRun:
    run = build_run(run_id, mode=mode)
    for stage in DEFAULT_PIPELINE:
        add_step(run, stage)
    return run


def resume_from_snapshot(snapshot: WorkflowStateSnapshot) -> WorkflowRun:
    run = snapshot.run
    stage = snapshot.current_stage
    idx = stage_index(stage)
    if idx < 0:
        return run
    run.stages = [step for step in run.stages[: idx + 1]]
    return run
