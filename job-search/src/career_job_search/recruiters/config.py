#!/usr/bin/env python3
"""Typed settings loader for recruiter/job-search runtime controls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT
from career_job_search.recruiters.policy import MAX_LIVE_DISPATCH

DEFAULT_SETTINGS = JOB_ROOT / "config" / "settings.yaml"
EXAMPLE_SETTINGS = JOB_ROOT / "config" / "settings.example.yaml"


class RuntimeConfig(BaseModel):
    mode: str = "review_first"
    dry_run_default: bool = True
    require_live_dispatch_ack: bool = True
    require_approval_ledger: bool = True


class LimitsConfig(BaseModel):
    max_live_dispatch_batch: int = Field(
        default=MAX_LIVE_DISPATCH,
        ge=1,
        le=MAX_LIVE_DISPATCH,
    )
    stop_on_captcha: bool = True
    stop_on_checkpoint: bool = True
    stop_on_unusual_activity: bool = True


class StateConfig(BaseModel):
    database_path: str = "state/recruiter_state.sqlite3"
    export_csv: bool = True


class Settings(BaseModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    state: StateConfig = Field(default_factory=StateConfig)


def load_settings(path: Path | str = DEFAULT_SETTINGS) -> Settings:
    candidate = Path(path)
    if not candidate.exists():
        candidate = EXAMPLE_SETTINGS
    raw: dict[str, Any] = {}
    if candidate.exists():
        loaded = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    return Settings.model_validate(raw)
