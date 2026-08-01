"""Structured subprocess execution used by non-browser Python adapters."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class ProcessTimeoutError(RuntimeError):
    """A child process exceeded its explicit time limit."""


def run_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Run an argument-only command with separate output streams."""

    command = tuple(str(part) for part in argv)
    if not command:
        raise ValueError("argv cannot be empty")
    try:
        completed = subprocess.run(
            command,  # noqa: S603
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProcessTimeoutError(
            f"Command timed out after {timeout_seconds:g} seconds: {command[0]}"
        ) from exc
    return ProcessResult(
        argv=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
