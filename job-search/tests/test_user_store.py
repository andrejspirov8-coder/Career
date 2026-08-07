from __future__ import annotations

import pytest

from career_job_search.api import user_store
from career_job_search.api.user_store import create_user, get_user, verify_user


def test_create_and_verify_user(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3"
    )
    user = create_user("alice@example.com", "secure-password-123")
    assert user.email == "alice@example.com"
    assert user.user_id.startswith("user_")

    verified = verify_user("alice@example.com", "secure-password-123")
    assert verified is not None
    assert verified.user_id == user.user_id

    assert verify_user("alice@example.com", "wrong-password") is None
    assert verify_user("bob@example.com", "anything") is None


def test_duplicate_email(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3"
    )
    create_user("alice@example.com", "password-1")
    with pytest.raises(ValueError, match="already registered"):
        create_user("alice@example.com", "password-2")


def test_get_user(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3"
    )
    created = create_user("alice@example.com", "password")
    fetched = get_user(created.user_id)
    assert fetched is not None
    assert fetched.email == "alice@example.com"
    assert fetched.user_id == created.user_id
    assert get_user("nonexistent") is None


def test_login_lockout_after_repeated_failures(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3"
    )
    user_store._failures.clear()
    create_user("alice@example.com", "secure-password-123")

    for _ in range(user_store._MAX_FAILED_ATTEMPTS):
        assert verify_user("alice@example.com", "wrong-password") is None

    assert verify_user("alice@example.com", "secure-password-123") is None

    user_store._failures.clear()
    assert verify_user("alice@example.com", "secure-password-123") is not None


def test_login_lockout_is_per_user(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3"
    )
    user_store._failures.clear()
    create_user("alice@example.com", "alice-password-1")
    create_user("bob@example.com", "bob-password-2")

    for _ in range(user_store._MAX_FAILED_ATTEMPTS):
        assert verify_user("alice@example.com", "wrong") is None

    assert verify_user("bob@example.com", "bob-password-2") is not None


def test_successful_login_clears_failures(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3"
    )
    user_store._failures.clear()
    create_user("alice@example.com", "secure-password-123")

    for _ in range(user_store._MAX_FAILED_ATTEMPTS - 1):
        assert verify_user("alice@example.com", "wrong") is None

    assert verify_user("alice@example.com", "secure-password-123") is not None
    assert verify_user("alice@example.com", "secure-password-123") is not None
