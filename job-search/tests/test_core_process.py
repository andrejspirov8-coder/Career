from __future__ import annotations

import sys
from pathlib import Path

import pytest

from career_job_search.core.process import (
    ProcessResult,
    ProcessTimeoutError,
    run_process,
)


def test_process_result_ok_true_on_zero():
    result = ProcessResult(argv=("echo",), returncode=0, stdout="", stderr="")
    assert result.ok is True


def test_process_result_ok_false_on_nonzero():
    result = ProcessResult(argv=("false",), returncode=1, stdout="", stderr="")
    assert result.ok is False


def test_process_result_frozen():
    result = ProcessResult(argv=("a",), returncode=0, stdout="", stderr="")
    with pytest.raises(AttributeError):
        result.stdout = "mutated"  # type: ignore[misc]


def test_process_result_attributes():
    result = ProcessResult(argv=("ls", "-la"), returncode=0, stdout="files", stderr="")
    assert result.argv == ("ls", "-la")
    assert result.stdout == "files"
    assert result.stderr == ""


def test_run_process_echo(tmp_path: Path):
    result = run_process(
        [sys.executable, "-c", "print('hello world')"],
        cwd=tmp_path,
        timeout_seconds=5.0,
    )
    assert result.ok
    assert "hello world" in result.stdout


def test_run_process_stderr(tmp_path: Path):
    result = run_process(
        [sys.executable, "-c", "import sys; print('err', file=sys.stderr)"],
        cwd=tmp_path,
        timeout_seconds=5.0,
    )
    assert result.ok
    assert "err" in result.stderr


def test_run_process_nonzero_exit(tmp_path: Path):
    result = run_process(
        [sys.executable, "-c", "exit(42)"],
        cwd=tmp_path,
        timeout_seconds=5.0,
    )
    assert not result.ok
    assert result.returncode == 42


def test_run_process_timeout(tmp_path: Path):
    with pytest.raises(ProcessTimeoutError, match="timed out"):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            cwd=tmp_path,
            timeout_seconds=0.1,
        )


def test_run_process_empty_argv(tmp_path: Path):
    with pytest.raises(ValueError, match="argv cannot be empty"):
        run_process([], cwd=tmp_path, timeout_seconds=5.0)


def test_run_process_env_custom(tmp_path: Path):
    result = run_process(
        [sys.executable, "-c", "import os; print(os.environ.get('MY_VAR'))"],
        cwd=tmp_path,
        timeout_seconds=5.0,
        env={"MY_VAR": "custom_value"},
    )
    assert "custom_value" in result.stdout


def test_run_process_cwd(tmp_path: Path):
    result = run_process(
        [sys.executable, "-c", "import os; print(os.getcwd())"],
        cwd=tmp_path,
        timeout_seconds=5.0,
    )
    assert str(tmp_path) in result.stdout


def test_process_timeout_error_is_runtime_error():
    assert issubclass(ProcessTimeoutError, RuntimeError)
