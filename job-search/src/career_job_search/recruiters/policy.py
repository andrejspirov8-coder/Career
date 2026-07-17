"""Central policy gates for job-search workflow orchestration."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from career_job_search.core.limits import MAX_LIVE_DISPATCH
from career_job_search.recruiters.identity import (
    normalise_profile_url as normalise_profile_url,
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def validate_live_dispatch_max(
    value: int | None,
    *,
    dry_run: bool,
    option_name: str = "--max",
) -> int | None:
    """Validate the explicit live-send ceiling before any browser can start."""

    if value is None:
        if dry_run:
            return None
        raise SystemExit(
            f"Live dispatch requires an explicit {option_name} in the range "
            f"1..{MAX_LIVE_DISPATCH}."
        )
    parsed = int(value)
    if parsed < 1:
        raise SystemExit(
            f"{option_name} must be in the range 1..{MAX_LIVE_DISPATCH}."
        )
    if not dry_run and parsed > MAX_LIVE_DISPATCH:
        raise SystemExit(
            f"Live {option_name} cannot exceed {MAX_LIVE_DISPATCH}; received {parsed}."
        )
    return parsed


def live_dispatch_slots_remaining(
    successful_sends_today: int,
    *,
    requested_max: int = MAX_LIVE_DISPATCH,
) -> int:
    cap = min(MAX_LIVE_DISPATCH, max(0, int(requested_max)))
    return max(0, cap - max(0, int(successful_sends_today)))


def note_hash(note: str) -> str:
    return sha256((note or "").strip().encode("utf-8")).hexdigest()


def current_send_mode(env: dict[str, str] | None = None) -> str:
    """Return the configured LinkedIn send posture.

    Manual is the safe default. cli_gated still requires the existing explicit
    CLI acknowledgement and exact SQLite approval checks.
    """

    source = env if env is not None else os.environ
    mode = (source.get("LINKEDIN_SEND_MODE") or "manual").strip().lower()
    if mode in {"manual", "cli_gated"}:
        return mode
    return "manual"


def can_dispatch_live(*, profile_url: str, note: str, db_path: Path) -> PolicyDecision:
    from career_job_search.recruiters.repository import approval_check

    check = approval_check(profile_url=profile_url, note=note, db_path=db_path)
    if check.approved:
        return PolicyDecision(True, "approved")
    return PolicyDecision(False, check.reason)


def require_live_dispatch_approvals(
    invites: Iterable[tuple[str, str]], *, db_path: Path
) -> list[PolicyDecision]:
    failures: list[PolicyDecision] = []
    for profile_url, note in invites:
        decision = can_dispatch_live(profile_url=profile_url, note=note, db_path=db_path)
        if not decision.allowed:
            failures.append(decision)
    return failures


def can_attempt_live_dispatch(
    invites: Iterable[tuple[str, str]],
    *,
    allow_live_dispatch: bool,
    db_path: Path,
    send_mode: str | None = None,
) -> PolicyDecision:
    mode = (send_mode or current_send_mode()).strip().lower()
    if mode != "cli_gated":
        return PolicyDecision(False, "manual_send_mode")
    if not allow_live_dispatch:
        return PolicyDecision(False, "missing_cli_acknowledgement")
    failures = require_live_dispatch_approvals(invites, db_path=db_path)
    if failures:
        return PolicyDecision(False, failures[0].reason)
    return PolicyDecision(True, "approved")


def risk_stop_state(
    *,
    screen_state: str = "",
    failure_rate: float = 0.0,
    pending_invites: int = 0,
    daily_cap_reached: bool = False,
    failure_rate_threshold: float = 0.35,
    pending_invite_threshold: int = 25,
) -> dict[str, Any]:
    blocker = (screen_state or "").strip().lower().replace(" ", "_")
    hard_blockers = {
        "checkpoint",
        "captcha",
        "unusual_activity",
        "login_wall",
    }
    signals: list[str] = []
    reason = ""

    if blocker in hard_blockers:
        reason = blocker
        signals.append(blocker)
    if daily_cap_reached:
        reason = reason or "daily_cap_reached"
        signals.append("daily_cap_reached")
    if failure_rate >= failure_rate_threshold:
        reason = reason or "high_failure_rate"
        signals.append("high_failure_rate")
    if pending_invites >= pending_invite_threshold:
        reason = reason or "repeated_pending_invites"
        signals.append("repeated_pending_invites")

    return {
        "stopped": bool(signals),
        "reason": reason,
        "signals": signals,
        "failure_rate": failure_rate,
        "pending_invites": pending_invites,
        "daily_cap_reached": daily_cap_reached,
        "screen_state": blocker,
    }


def is_untrusted_content(_text: str) -> bool:
    return True
