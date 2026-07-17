#!/usr/bin/env python3
# ruff: noqa: F401
"""Public compatibility facade for the bounded local-agent coordinator modules."""

from __future__ import annotations

import shutil as shutil
from uuid import uuid4 as uuid4

from career_job_search.dev_agents import benchmark as _benchmark_module
from career_job_search.dev_agents import execution as _execution
from career_job_search.dev_agents.application import (
    apply_run,
    cancel_run,
    export_patch,
    maybe_auto_apply_run,
    reject_run,
    verify_run,
)
from career_job_search.dev_agents.benchmark import (
    _benchmark_implementer,
    _benchmark_implementer_case,
    _initialise_fixture,
    _initialise_implementation_fixture,
)
from career_job_search.dev_agents.cli import (
    _paths_from_args,
    build_parser,
    json_response,
    main,
)
from career_job_search.dev_agents.common import (
    ACTIVE_STATUSES,
    AUTO_APPLY_POLICY_VERSION,
    BENCHMARK_MODEL_TIMEOUT_SECONDS,
    CODEX_INNER_SANDBOX_MODE,
    DEFAULT_BACKUP_ROOT,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_WORKTREE_ROOT,
    EXEC_POLICY_REJECTION_MARKERS,
    JOB_ROOT,
    MAX_PATCH_PREVIEW_CHARS,
    MAX_STREAM_CHARS,
    PLANNER_POLICY_VERSION,
    PLANNER_RUN_ID_PATTERN,
    PROPOSAL_ID_PATTERN,
    SAFE_NPM_COMMANDS,
    SCHEMA_SQL,
    SENSITIVE_OBJECTIVE_TERMS,
    SENSITIVE_SNAPSHOT_BASENAMES,
    SENSITIVE_SNAPSHOT_SUFFIXES,
    TASK_ID_PATTERN,
    TERMINAL_STATUSES,
    WRITE_FORBIDDEN_PATHS,
    AgentProcessError,
    CoordinatorError,
    CoordinatorPaths,
    PatchInfo,
    SnapshotInfo,
    _json_dump,
    _json_load,
    atomic_write_json,
    atomic_write_text,
    load_settings,
    utc_now_iso,
)
from career_job_search.dev_agents.doctor import (
    _doctor_check,
    _ollama_model_context,
    _ollama_models,
    doctor,
)
from career_job_search.dev_agents.execution import (
    _finish_run,
    _is_cancel_requested,
    _ollama_model_identities,
    _patch_result,
    _resolve_check_command,
    agent_response_search_text,
    build_agent_prompt,
    find_agent_policy_rejections,
    load_structured_response,
    run_agent_process,
    run_checks,
    serial_model_slot,
)
from career_job_search.dev_agents.models import (
    AgentFinding,
    AgentResponse,
    AgentRole,
    AgentTaskSpec,
    AutonomySettings,
    CheckResult,
    LimitsSettings,
    LocalAgentSettings,
    ModelSettings,
    PlannerProposalDraft,
    PlannerResponse,
    PlannerSettings,
    ResourceSettings,
    RoleSettings,
    SnapshotSettings,
    VerificationCheck,
    normalise_relative_path,
)
from career_job_search.dev_agents.planner import (
    _planner_evidence,
    _planner_row_to_dict,
    build_planner_prompt,
    list_planner_runs,
    resource_status,
    run_planner,
)
from career_job_search.dev_agents.policy import (
    _path_matches,
    is_snapshot_forbidden,
    is_write_forbidden,
    path_is_allowed,
    validate_check,
    validate_task_policy,
)
from career_job_search.dev_agents.proposals import (
    _local_date,
    _proposal_fingerprint,
    _proposal_row_to_dict,
    _validate_proposal_policy,
    approve_proposal,
    get_proposal,
    list_proposals,
    reject_proposal,
    store_planner_proposals,
    verification_checks_for_preset,
)
from career_job_search.dev_agents.review import (
    _assert_patch_fresh,
    _is_auto_apply_path,
    _load_task_input,
    _manifest_for_run,
    _record_apply_result,
    approve_run,
    auto_apply_eligibility,
    create_workspace_backup,
    evaluate_autonomy,
    record_model_safety_violation,
    set_autonomy_paused,
)
from career_job_search.dev_agents.run_flow import execute_run
from career_job_search.dev_agents.runs import (
    _ensure_column,
    _row_to_run,
    _update_run,
    connect,
    create_run,
    get_rollout,
    get_run,
    init_db,
    list_runs,
    validate_planner_run_id,
    validate_proposal_id,
    validate_task_id,
)
from career_job_search.dev_agents.sandbox import (
    _exec_rules,
    _redact_stream,
    _seatbelt_home_filter,
    _seatbelt_string,
    build_sandbox_profile,
    safe_agent_environment,
    write_model_catalog,
)
from career_job_search.dev_agents.service import (
    _coordinator_command,
    _next_planner_at,
    _planner_schedule_due,
    _spawn_service_child,
    _stop_service_child,
    _update_service_status,
    build_overview,
    claim_next_run,
    cleanup_old_runs,
    get_service_status,
    run_development_agent_service,
    run_worker,
    spawn_worker,
)
from career_job_search.dev_agents.snapshots import (
    _git,
    _git_bytes,
    _isolate_worktree_git,
    _link_dependencies,
    _parse_name_status,
    _parse_tree_manifest,
    _snapshot_candidates,
    _validate_no_sensitive_artifacts,
    _validate_snapshot_files,
    _zlist,
    build_patch,
    cleanup_worktree,
    create_snapshot,
)


def _run_with_process_retry(**kwargs):
    """Preserve the original patchable process-runner compatibility point."""
    original = _execution.run_agent_process
    _execution.run_agent_process = run_agent_process
    try:
        return _execution._run_with_process_retry(**kwargs)
    finally:
        _execution.run_agent_process = original


def _selected_implementer_identity(
    *, settings: LocalAgentSettings, paths: CoordinatorPaths
):
    """Preserve the original patchable model-identity compatibility point."""
    original = _execution._ollama_model_identities
    _execution._ollama_model_identities = _ollama_model_identities
    try:
        return _execution._selected_implementer_identity(
            settings=settings,
            paths=paths,
        )
    finally:
        _execution._ollama_model_identities = original


def benchmark(*, settings: LocalAgentSettings, paths: CoordinatorPaths):
    """Run qualification while preserving patchable health/model probes."""
    original_models = _benchmark_module._ollama_model_identities
    original_resources = _benchmark_module.resource_status
    _benchmark_module._ollama_model_identities = _ollama_model_identities
    _benchmark_module.resource_status = resource_status
    try:
        return _benchmark_module.benchmark(settings=settings, paths=paths)
    finally:
        _benchmark_module._ollama_model_identities = original_models
        _benchmark_module.resource_status = original_resources


__all__ = tuple(name for name in globals() if not name.startswith("__"))


if __name__ == "__main__":
    raise SystemExit(main())
