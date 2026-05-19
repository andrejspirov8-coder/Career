"""Chrome profile singleton lock helpers for linkedin/.browser-profile."""

from __future__ import annotations

import os
import re
from pathlib import Path

_LOCK_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def profile_lock_pid(profile_dir: Path) -> int | None:
    """Parse PID from Chrome's SingletonLock symlink (hostname-PID)."""
    lock = profile_dir / "SingletonLock"
    if not lock.exists():
        return None
    try:
        if lock.is_symlink():
            target = os.readlink(lock)
        else:
            target = lock.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    match = re.search(r"-(\d+)$", str(target))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we cannot signal it — treat as alive.
        return True
    return True


def profile_lock_files_present(profile_dir: Path) -> bool:
    return any((profile_dir / name).exists() for name in _LOCK_NAMES)


def describe_profile_lock(profile_dir: Path) -> str:
    if not profile_dir.is_dir():
        return "profile folder missing (first run will create it)"
    if not profile_lock_files_present(profile_dir):
        return "unlocked (ready to launch)"
    pid = profile_lock_pid(profile_dir)
    if pid is None:
        return "lock files present (could not read PID — may be stale)"
    if process_is_alive(pid):
        return f"locked by Chrome PID {pid} (quit that window before starting the bot)"
    return f"stale lock from dead PID {pid} (safe to clear)"


def release_stale_chrome_profile_lock(profile_dir: Path) -> bool:
    """
    Remove Chrome singleton files when the locking process is gone.

    Returns True if any lock file was removed.
    """
    if not profile_dir.is_dir():
        return False
    pid = profile_lock_pid(profile_dir)
    if pid is not None and process_is_alive(pid):
        return False
    removed = False
    for name in _LOCK_NAMES:
        path = profile_dir / name
        try:
            if path.is_symlink() or path.exists():
                path.unlink(missing_ok=True)
                removed = True
        except OSError:
            continue
    return removed


def is_profile_in_use_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "profile is already in use" in msg
        or "opening in existing browser session" in msg
        or "singletonlock" in msg
    )
