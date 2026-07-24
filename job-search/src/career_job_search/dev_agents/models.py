"""Validated records for the local development-agent coordinator."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

AgentRole = Literal["planner", "explorer", "implementer", "reviewer"]
AgentRisk = Literal["low", "medium", "high"]
AgentSeverity = Literal["critical", "major", "minor", "note"]
ProposalCategory = Literal[
    "documentation",
    "tests",
    "investigation",
    "bounded_fix",
    "small_change",
    "refactor",
]
ProposalPriority = Literal["high", "medium", "low"]
ProposalCheckPreset = Literal["none", "python", "dashboard", "raycast", "architecture"]
ProposalStatus = Literal[
    "proposed",
    "approved",
    "queued",
    "running",
    "applied",
    "rejected",
    "cancelled",
    "blocked",
]
AgentRunStatus = Literal[
    "queued",
    "snapshotting",
    "running",
    "local_review",
    "verifying",
    "ready_for_codex_review",
    "approved",
    "applied",
    "blocked",
    "failed",
    "timed_out",
    "cancelled",
    "stale",
    "rejected",
]


def normalise_relative_path(value: str, *, allow_root: bool = True) -> str:
    """Return a safe repository-relative POSIX path."""

    clean = value.strip().replace("\\", "/")
    while clean.startswith("./"):
        clean = clean[2:]
    clean = clean.rstrip("/") or "."
    parts = clean.split("/")
    if (
        not clean
        or clean.startswith("/")
        or "\x00" in clean
        or any(part in {"", ".", ".."} for part in parts if clean != ".")
        or (clean == "." and not allow_root)
    ):
        raise ValueError(f"Unsafe repository-relative path: {value!r}")
    return clean


class VerificationCheck(BaseModel):
    """A deterministic, shell-free check run by the coordinator."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    argv: list[str] = Field(min_length=1, max_length=40)
    cwd: str = "."
    timeout_seconds: int = Field(default=600, ge=1, le=1800)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Check name cannot be empty.")
        return clean

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, value: list[str]) -> list[str]:
        clean = [item.strip() for item in value]
        if any(not item or "\x00" in item or "\n" in item for item in clean):
            raise ValueError("Check arguments must be non-empty single-line values.")
        return clean

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, value: str) -> str:
        return normalise_relative_path(value)


class AgentTaskSpec(BaseModel):
    """A bounded development task safe to hand to a local model."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["career_local_dev_task_v1"] = "career_local_dev_task_v1"
    objective: str = Field(min_length=10, max_length=5000)
    role: AgentRole = "implementer"
    allowed_paths: list[str] = Field(min_length=1, max_length=50)
    acceptance_checks: list[VerificationCheck] = Field(default_factory=list)
    risk: AgentRisk = "low"
    context_notes: str = Field(default="", max_length=8000)
    max_changed_files: int = Field(default=15, ge=1, le=15)
    max_diff_lines: int = Field(default=1000, ge=1, le=1000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=1500)

    @field_validator("objective", "context_notes")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("allowed_paths")
    @classmethod
    def validate_allowed_paths(cls, value: list[str]) -> list[str]:
        clean: list[str] = []
        for item in value:
            path = normalise_relative_path(item)
            if path not in clean:
                clean.append(path)
        return clean

    @model_validator(mode="after")
    def validate_role_limits(self) -> AgentTaskSpec:
        if self.role == "implementer" and "." in self.allowed_paths:
            raise ValueError(
                "Implementer tasks require bounded paths; repository root is not allowed."
            )
        if self.timeout_seconds is None:
            self.timeout_seconds = 1500 if self.role == "implementer" else 600
        elif self.role != "implementer" and self.timeout_seconds > 600:
            raise ValueError("Explorer and reviewer tasks are limited to 600 seconds.")
        return self


class AgentFinding(BaseModel):
    """One reviewer finding returned by a local model."""

    model_config = ConfigDict(extra="forbid")

    severity: AgentSeverity
    title: str = Field(min_length=1, max_length=160)
    detail: str = Field(min_length=1, max_length=1200)
    path: str | None = Field(default=None, max_length=500)
    line: int | None = Field(default=None, ge=1)


class AgentResponse(BaseModel):
    """Structured final response required from every local Codex process."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["career_local_dev_agent_response_v1"] = (
        "career_local_dev_agent_response_v1"
    )
    status: Literal["completed", "blocked"]
    summary: str = Field(min_length=1, max_length=2000)
    details: list[str] = Field(default_factory=list, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=20)
    blocking_reason: str | None = Field(default=None, max_length=1500)
    findings: list[AgentFinding] = Field(default_factory=list, max_length=30)
    requested_checks: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("findings", mode="before")
    @classmethod
    def normalise_plain_text_findings(cls, value: Any) -> Any:
        """Keep local-model prose usable without inventing blocker severity."""

        if not isinstance(value, list):
            return value
        normalised: list[Any] = []
        for item in value:
            if isinstance(item, str):
                detail = item.strip()
                if not detail:
                    continue
                normalised.append(
                    {
                        "severity": "note",
                        "title": detail[:160],
                        "detail": detail[:1200],
                    }
                )
            else:
                normalised.append(item)
        return normalised

    @model_validator(mode="after")
    def validate_blocked_response(self) -> AgentResponse:
        if self.status == "blocked" and not self.blocking_reason:
            raise ValueError("A blocked response requires blocking_reason.")
        return self


class PlannerProposalDraft(BaseModel):
    """One bounded development proposal produced by the read-only planner."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=10, max_length=2000)
    category: ProposalCategory
    evidence: list[str] = Field(min_length=1, max_length=8)
    allowed_paths: list[str] = Field(min_length=1, max_length=10)
    check_preset: ProposalCheckPreset
    risk: Literal["low", "medium"] = "low"
    priority: ProposalPriority = "medium"
    estimated_files: int = Field(default=1, ge=1, le=8)
    estimated_diff_lines: int = Field(default=100, ge=1, le=600)

    @field_validator("objective")
    @classmethod
    def strip_objective(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence")
    @classmethod
    def clean_evidence(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("A proposal requires concrete repository evidence.")
        return cleaned

    @field_validator("allowed_paths")
    @classmethod
    def clean_allowed_paths(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            path = normalise_relative_path(item, allow_root=False)
            if path not in cleaned:
                cleaned.append(path)
        return cleaned


class PlannerResponse(BaseModel):
    """Structured output required from the scheduled read-only planner."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["career_local_dev_planner_response_v1"] = (
        "career_local_dev_planner_response_v1"
    )
    status: Literal["completed", "blocked"]
    summary: str = Field(min_length=1, max_length=2000)
    proposals: list[PlannerProposalDraft] = Field(default_factory=list, max_length=5)
    risks: list[str] = Field(default_factory=list, max_length=10)
    blocking_reason: str | None = Field(default=None, max_length=1500)

    @model_validator(mode="after")
    def validate_blocked_response(self) -> PlannerResponse:
        if self.status == "blocked" and not self.blocking_reason:
            raise ValueError("A blocked planner response requires blocking_reason.")
        return self


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_window: int = Field(ge=32768)
    use_cli_output_schema: bool = True
    digest: str = Field(min_length=64, max_length=64)

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        clean = value.strip().casefold()
        if not re.fullmatch(r"[a-f0-9]{64}", clean):
            raise ValueError("Model digests must be full 64-character SHA-256 values.")
        return clean


class RoleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    timeout_seconds: int = Field(ge=1, le=1500)
    sandbox: Literal["read-only", "workspace-write"]


class SnapshotSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_file_bytes: int = Field(ge=1)
    max_total_bytes: int = Field(ge=1)
    forbidden_prefixes: list[str]
    forbidden_parts: list[str]


class LimitsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_changed_files: int = Field(ge=1, le=15)
    max_diff_lines: int = Field(ge=1, le=1000)
    retry_count: Literal[1]
    retention_days: int = Field(ge=1, le=365)
    required_safe_runs: int = Field(ge=1, le=100)


class PlannerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = "Europe/Vilnius"
    schedule_time: str = "19:00"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    max_proposals_per_run: int = Field(default=5, ge=1, le=5)
    max_approved_implementations_per_day: int = Field(default=2, ge=1, le=5)
    scan_paths: list[str] = Field(min_length=1, max_length=20)

    @field_validator("schedule_time")
    @classmethod
    def validate_schedule_time(cls, value: str) -> str:
        clean = value.strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clean):
            raise ValueError("Planner schedule_time must use 24-hour HH:MM format.")
        return clean

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        clean = sorted(set(value))
        if not clean or any(day < 0 or day > 6 for day in clean):
            raise ValueError("Planner weekdays must contain values from 0 to 6.")
        return clean

    @field_validator("scan_paths")
    @classmethod
    def validate_scan_paths(cls, value: list[str]) -> list[str]:
        return [normalise_relative_path(item, allow_root=False) for item in value]


class AutonomySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier_one_safe_runs: int = Field(default=10, ge=1, le=100)
    tier_two_safe_runs: int = Field(default=20, ge=2, le=200)
    minimum_first_pass_rate: float = Field(default=0.8, ge=0.5, le=1.0)
    rolling_window: int = Field(default=20, ge=5, le=100)
    auto_apply_max_files: int = Field(default=3, ge=1, le=5)
    auto_apply_max_diff_lines: int = Field(default=300, ge=1, le=500)
    auto_apply_categories: list[Literal["documentation", "tests"]] = Field(
        default_factory=lambda: ["documentation", "tests"]
    )

    @model_validator(mode="after")
    def validate_thresholds(self) -> AutonomySettings:
        if self.tier_two_safe_runs <= self.tier_one_safe_runs:
            raise ValueError("Tier two must require more safe runs than tier one.")
        return self


class ResourceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_free_disk_bytes: int = Field(default=20 * 1024**3, ge=1024**3)
    planner_min_battery_percent: int = Field(default=50, ge=1, le=100)
    implementer_requires_ac_power: bool = True
    defer_during_job_automation: bool = True


class LocalAgentSettings(BaseModel):
    """Validated repository policy loaded from YAML."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[
        "career_local_dev_agent_settings_v1",
        "career_local_dev_agent_settings_v2",
    ]
    ollama_host: str
    roles: dict[AgentRole, RoleSettings]
    models: dict[str, ModelSettings]
    implementer_candidates: list[str]
    implementer_fallback: str
    secondary_reviewer_model: str
    snapshot: SnapshotSettings
    limits: LimitsSettings
    planner: PlannerSettings
    autonomy: AutonomySettings
    resources: ResourceSettings

    @field_validator("ollama_host")
    @classmethod
    def validate_ollama_host(cls, value: str) -> str:
        clean = value.strip().rstrip("/")
        if clean != "http://127.0.0.1:11434":
            raise ValueError(
                "Ollama must use the fixed local-only endpoint http://127.0.0.1:11434."
            )
        return clean

    @model_validator(mode="after")
    def validate_model_references(self) -> LocalAgentSettings:
        required_roles = {"planner", "explorer", "implementer", "reviewer"}
        if set(self.roles) != required_roles:
            raise ValueError(f"roles must contain exactly {sorted(required_roles)}")
        references = {
            *(role.model for role in self.roles.values()),
            *self.implementer_candidates,
            self.implementer_fallback,
            self.secondary_reviewer_model,
        }
        missing = sorted(references - set(self.models))
        if missing:
            raise ValueError(f"Missing model metadata for: {missing}")
        if not self.implementer_candidates:
            raise ValueError("At least one implementer candidate is required.")
        return self


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    argv: list[str]
    cwd: str
    status: Literal["passed", "failed", "timed_out", "cancelled"]
    exit_code: int | None = None
    duration_seconds: float = Field(ge=0)
    stdout: str = ""
    stderr: str = ""
