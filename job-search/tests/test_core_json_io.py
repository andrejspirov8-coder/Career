from __future__ import annotations

import json
import stat
from pathlib import Path

from career_job_search.core.json_io import write_json_atomic


def test_write_json_atomic_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "state" / "data.json"
    payload = {"key": "value", "count": 42}
    write_json_atomic(path, payload)
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {"count": 42, "key": "value"}


def test_write_json_atomic_sorts_keys_and_indents(tmp_path: Path) -> None:
    path = tmp_path / "sorted.json"
    write_json_atomic(path, {"z": 1, "a": 2})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data.keys()) == ["a", "z"]


def test_write_json_atomic_sets_private_permissions(tmp_path: Path) -> None:
    path = tmp_path / "secret.json"
    write_json_atomic(path, {"token": "abc"}, mode=0o600)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_write_json_atomic_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "c" / "deep.json"
    write_json_atomic(path, {"nested": True})
    assert path.exists()


def test_write_json_atomic_overwrites_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "overwrite.json"
    path.write_text("{}", encoding="utf-8")
    write_json_atomic(path, {"new": "data"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": "data"}


def test_write_json_atomic_writes_newline_terminated(tmp_path: Path) -> None:
    path = tmp_path / "nl.json"
    write_json_atomic(path, {"x": 1})
    content = path.read_bytes()
    assert content.endswith(b"\n")


def test_write_json_atomic_temp_file_cleaned_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "fail.json"

    class Unserializable:
        pass

    try:
        write_json_atomic(path, {"bad": Unserializable()})
        raise AssertionError("Expected TypeError")
    except TypeError:
        pass
    assert not path.exists()
    leftovers = list(tmp_path.glob(".*.json.tmp"))
    assert len(leftovers) == 0
