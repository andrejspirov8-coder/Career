from __future__ import annotations

import stat
from datetime import UTC, datetime

import pytest

from career_job_search.notifications import center as notifications

NOW = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)


def candidate(
    number: int,
    *,
    scope: str = "automation",
    lifecycle: str = "event",
    kind: str = "automation_completed",
    category: str = "automation",
    priority: str = "info",
    href: str = "/automation",
    desktop_eligible: bool = True,
) -> dict[str, object]:
    return {
        "notification_id": f"notification_{number:032x}",
        "scope": scope,
        "category": category,
        "kind": kind,
        "priority": priority,
        "lifecycle": lifecycle,
        "title": f"Notification {number}",
        "body": "A bounded local notification summary.",
        "href": href,
        "occurred_at": "2026-07-15T07:00:00+00:00",
        "source_updated_at": "2026-07-15T07:00:00+00:00",
        "desktop_eligible": desktop_eligible,
    }


def sync(db_path, rows, scopes):
    return notifications.sync_candidates(
        {"candidates": rows, "synced_scopes": scopes},
        db_path=db_path,
        now=NOW,
    )


def action(db_path, payload):
    return notifications.perform_action(payload, db_path=db_path, now=NOW)


def test_sync_preserves_user_state_and_resolves_missing_conditions(tmp_path):
    db_path = tmp_path / "notifications.sqlite3"
    event = candidate(1)
    condition = candidate(
        2,
        scope="application",
        lifecycle="condition",
        kind="follow_up_due",
        category="application",
        priority="urgent",
        href="/applications?opportunity=opp_test",
    )

    first = sync(db_path, [event, condition], ["automation", "application"])
    assert first["counts"]["unread"] == 2
    assert first["counts"]["urgent"] == 1
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600

    action(
        db_path,
        {"action": "read", "notification_id": event["notification_id"]},
    )
    snoozed = action(
        db_path,
        {"action": "snooze_day", "notification_id": condition["notification_id"]},
    )
    assert snoozed["counts"]["unread"] == 0
    assert snoozed["counts"]["snoozed"] == 1

    resolved = sync(db_path, [event], ["automation", "application"])
    assert [item["notification_id"] for item in resolved["inbox"]] == [
        event["notification_id"]
    ]
    assert resolved["inbox"][0]["read_at"] is not None
    assert any(
        item["notification_id"] == condition["notification_id"]
        and item["resolved_at"] is not None
        for item in resolved["archived"]
    )


def test_read_dismiss_restore_and_snooze_actions_are_fixed(tmp_path):
    db_path = tmp_path / "notifications.sqlite3"
    row = candidate(3)
    sync(db_path, [row], ["automation"])

    dismissed = action(
        db_path,
        {"action": "dismiss", "notification_id": row["notification_id"]},
    )
    assert dismissed["counts"]["active"] == 0
    assert dismissed["archived"][0]["dismissed_at"] is not None

    restored = action(
        db_path,
        {"action": "restore", "notification_id": row["notification_id"]},
    )
    assert restored["counts"]["active"] == 1

    action(
        db_path,
        {"action": "snooze_week", "notification_id": row["notification_id"]},
    )
    unsnoozed = action(
        db_path,
        {"action": "clear_snooze", "notification_id": row["notification_id"]},
    )
    assert unsnoozed["counts"]["snoozed"] == 0

    read = action(db_path, {"action": "read_all"})
    assert read["counts"]["unread"] == 0

    with pytest.raises(ValueError, match="Unsupported"):
        action(
            db_path, {"action": "run_shell", "notification_id": row["notification_id"]}
        )


def test_desktop_opt_in_skips_existing_items_and_delivers_new_items(tmp_path):
    db_path = tmp_path / "notifications.sqlite3"
    existing = candidate(4)
    sync(db_path, [existing], ["automation"])

    enabled = action(
        db_path,
        {"action": "set_desktop", "enabled": True, "mark_existing": True},
    )
    assert enabled["settings"]["desktop_enabled"] is True
    assert enabled["desktop_pending"] == []

    newer = candidate(5, priority="attention")
    pending = sync(db_path, [existing, newer], ["automation"])
    assert [item["notification_id"] for item in pending["desktop_pending"]] == [
        newer["notification_id"]
    ]

    delivered = action(
        db_path,
        {
            "action": "desktop_delivered",
            "notification_ids": [newer["notification_id"]],
        },
    )
    assert delivered["desktop_pending"] == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("notification_id", "../../state/secrets", "valid notification"),
        ("href", "https://example.com", "inside the dashboard"),
        ("href", "//example.com/path", "inside the dashboard"),
        ("kind", "linkedin_dispatch", "kind is invalid"),
    ],
)
def test_candidate_validation_rejects_paths_and_unknown_kinds(field, value, message):
    row = candidate(6)
    row[field] = value

    with pytest.raises(ValueError, match=message):
        notifications.validate_candidate(row)


def test_failed_source_sync_does_not_resolve_unsynchronized_scope(tmp_path):
    db_path = tmp_path / "notifications.sqlite3"
    condition = candidate(
        7,
        scope="application",
        lifecycle="condition",
        kind="application_deadline",
        category="application",
    )
    sync(db_path, [condition], ["application"])

    overview = sync(db_path, [], ["automation"])

    assert overview["counts"]["active"] == 1
    assert overview["inbox"][0]["notification_id"] == condition["notification_id"]
