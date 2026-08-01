"""Atomic file write utilities for runtime state persistence.

All public functions write to a temporary file on the same filesystem,
fsync the data, then atomically rename over the target path. This
guarantees that a concurrent reader sees either the old file or the
new file -- never a partial write.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(
    path: Path,
    value: str | bytes,
    *,
    mode: int = 0o600,
    suffix: str = ".tmp",
    dir_fsync: bool = True,
) -> None:
    """Write text or bytes atomically to ``path``.

    Args:
        path: Destination file path.
        value: String (UTF-8) or bytes to write.
        mode: File permissions (default 0o600 for private runtime files).
        suffix: Suffix for the temporary file (default ".tmp").
        dir_fsync: If True, fsync the parent directory after rename to
            ensure directory metadata is persisted (default True).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=suffix, dir=path.parent
    )
    temp_path = Path(raw_temp)
    try:
        if isinstance(value, bytes):
            with os.fdopen(handle, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
        temp_path.chmod(mode)
        os.replace(temp_path, path)
        if dir_fsync:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def atomic_write_json(
    path: Path,
    value: Any,
    *,
    mode: int = 0o600,
    suffix: str = ".tmp",
    dir_fsync: bool = True,
) -> None:
    """Write ``value`` as JSON atomically to ``path``.

    Uses sorted keys and 2-space indentation for deterministic output,
    plus a trailing newline.
    """
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        mode=mode,
        suffix=suffix,
        dir_fsync=dir_fsync,
    )
