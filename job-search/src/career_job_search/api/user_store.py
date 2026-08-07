from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from datetime import UTC, datetime

from career_job_search.api.user_models import User
from career_job_search.core.paths import project_path
from career_job_search.core.sqlite import connect_sqlite, migrate_schema

USERS_DB_PATH = project_path("state", "users.sqlite3")
_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16

_MAX_FAILED_ATTEMPTS = 5
_FAILURE_WINDOW_SECONDS = 15 * 60

_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def _is_locked_out(identity: str) -> bool:
    with _failures_lock:
        now = time.monotonic()
        recent = [
            ts
            for ts in _failures.get(identity, [])
            if now - ts < _FAILURE_WINDOW_SECONDS
        ]
        _failures[identity] = recent
        return len(recent) >= _MAX_FAILED_ATTEMPTS


def _record_failure(identity: str) -> None:
    with _failures_lock:
        now = time.monotonic()
        recent = [
            ts
            for ts in _failures.get(identity, [])
            if now - ts < _FAILURE_WINDOW_SECONDS
        ]
        recent.append(now)
        _failures[identity] = recent


def _clear_failures(identity: str) -> None:
    with _failures_lock:
        _failures.pop(identity, None)


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt_bytes = (
        secrets.token_bytes(_SALT_BYTES) if salt is None else bytes.fromhex(salt)
    )
    salt_hex = salt_bytes.hex()
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        _PBKDF2_ITERATIONS,
    )
    return key.hex(), salt_hex


def _get_con() -> sqlite3.Connection:
    con = connect_sqlite(USERS_DB_PATH, wal=True)
    migrate_schema(
        con,
        """
        CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """,
        current_version=1,
        db_name="users",
    )
    return con


def create_user(email: str, password: str) -> User:
    con = _get_con()
    try:
        password_hash, password_salt = _hash_password(password)
        user_id = "user_" + secrets.token_hex(16)
        created_at = datetime.now(UTC).isoformat()
        con.execute(
            "INSERT INTO users (user_id, email, password_hash, password_salt, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email.lower().strip(), password_hash, password_salt, created_at),
        )
        con.commit()
        return User(
            user_id=user_id,
            email=email.lower().strip(),
            created_at=datetime.fromisoformat(created_at),
        )
    except sqlite3.IntegrityError:
        raise ValueError(f"Email already registered: {email}") from None
    finally:
        con.close()


def verify_user(email: str, password: str) -> User | None:
    identity = email.lower().strip()
    if _is_locked_out(identity):
        return None
    con = _get_con()
    try:
        row = con.execute(
            "SELECT user_id, email, password_hash, password_salt, created_at FROM users WHERE email = ?",
            (identity,),
        ).fetchone()
        if row is None:
            _record_failure(identity)
            return None
        user_id, stored_email, stored_hash, stored_salt, created_at_str = row
        computed_hash, _ = _hash_password(password, stored_salt)
        if not secrets.compare_digest(computed_hash, stored_hash):
            _record_failure(identity)
            return None
        _clear_failures(identity)
        return User(
            user_id=user_id,
            email=stored_email,
            created_at=datetime.fromisoformat(created_at_str),
        )
    finally:
        con.close()


def get_user(user_id: str) -> User | None:
    con = _get_con()
    try:
        row = con.execute(
            "SELECT user_id, email, created_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return User(
            user_id=row[0], email=row[1], created_at=datetime.fromisoformat(row[2])
        )
    finally:
        con.close()
