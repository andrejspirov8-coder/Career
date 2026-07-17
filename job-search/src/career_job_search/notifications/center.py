#!/usr/bin/env python3
"""Private notification inbox state for the local Career dashboard."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT

DEFAULT_NOTIFICATION_DB = JOB_ROOT / "state" / "notifications.sqlite3"
NOTIFICATION_ID_PATTERN = re.compile(r"^notification_[a-f0-9]{32}$")
MAX_INPUT_BYTES = 1_000_000
MAX_CANDIDATES = 200
MAX_DESKTOP_IDS = 50

SCOPES = frozenset({"automation", "opportunity", "application", "development"})
CATEGORIES = frozenset(
    {"automation", "opportunity", "application", "development", "system"}
)
KINDS = frozenset(
    {
        "automation_completed",
        "strong_role",
        "application_deadline",
        "follow_up_due",
        "source_health",
        "schedule_missed",
        "dev_proposals_ready",
        "dev_agent_failed",
        "dev_auto_apply_succeeded",
        "dev_autonomy_paused",
        "dev_model_requalification",
    }
)
PRIORITIES = frozenset({"urgent", "attention", "info"})
LIFECYCLES = frozenset({"event", "condition"})
INDIVIDUAL_ACTIONS = frozenset(
    {"read", "unread", "dismiss", "restore", "snooze_day", "snooze_week", "clear_snooze"}
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS notifications (
  notification_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  category TEXT NOT NULL,
  kind TEXT NOT NULL,
  priority TEXT NOT NULL,
  lifecycle TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  href TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  source_updated_at TEXT,
  desktop_eligible INTEGER NOT NULL DEFAULT 0,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  read_at TEXT,
  dismissed_at TEXT,
  snoozed_until TEXT,
  resolved_at TEXT,
  desktop_delivered_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_notifications_active
ON notifications(resolved_at, dismissed_at, occurred_at);

CREATE INDEX IF NOT EXISTS idx_notifications_scope_lifecycle
ON notifications(scope, lifecycle, resolved_at);

CREATE TABLE IF NOT EXISTS notification_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  desktop_enabled INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
"""


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def connect(db_path: Path | str = DEFAULT_NOTIFICATION_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return con


def init_db(db_path: Path | str = DEFAULT_NOTIFICATION_DB) -> Path:
    path = Path(db_path)
    now = utc_now_iso()
    with connect(path) as con:
        con.executescript(SCHEMA_SQL)
        con.execute(
            """
            INSERT OR IGNORE INTO notification_settings(id, desktop_enabled, updated_at)
            VALUES (1, 0, ?)
            """,
            (now,),
        )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _clean_text(value: Any, name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text.")
    clean = value.strip()
    if not clean or len(clean) > max_length or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", clean):
        raise ValueError(f"{name} is invalid.")
    return clean


def _clean_optional_timestamp(value: Any, name: str) -> str | None:
    if value in {None, ""}:
        return None
    return _clean_timestamp(value, name)


def _clean_timestamp(value: Any, name: str) -> str:
    clean = _clean_text(value, name, 64)
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone.")
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat()


def validate_notification_id(value: Any) -> str:
    if not isinstance(value, str) or not NOTIFICATION_ID_PATTERN.fullmatch(value):
        raise ValueError("Choose a valid notification.")
    return value


def _clean_href(value: Any) -> str:
    clean = _clean_text(value, "Notification link", 500)
    if (
        not clean.startswith("/")
        or clean.startswith("//")
        or "\\" in clean
        or re.search(r"[\x00-\x1f\x7f]", clean)
    ):
        raise ValueError("Notification links must stay inside the dashboard.")
    return clean


def validate_candidate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Notification candidates must be objects.")
    scope = value.get("scope")
    category = value.get("category")
    kind = value.get("kind")
    priority = value.get("priority")
    lifecycle = value.get("lifecycle")
    if scope not in SCOPES:
        raise ValueError("Notification scope is invalid.")
    if category not in CATEGORIES:
        raise ValueError("Notification category is invalid.")
    if kind not in KINDS:
        raise ValueError("Notification kind is invalid.")
    if priority not in PRIORITIES:
        raise ValueError("Notification priority is invalid.")
    if lifecycle not in LIFECYCLES:
        raise ValueError("Notification lifecycle is invalid.")
    desktop_eligible = value.get("desktop_eligible")
    if not isinstance(desktop_eligible, bool):
        raise ValueError("Notification desktop eligibility is invalid.")
    return {
        "notification_id": validate_notification_id(value.get("notification_id")),
        "scope": scope,
        "category": category,
        "kind": kind,
        "priority": priority,
        "lifecycle": lifecycle,
        "title": _clean_text(value.get("title"), "Notification title", 180),
        "body": _clean_text(value.get("body"), "Notification body", 500),
        "href": _clean_href(value.get("href")),
        "occurred_at": _clean_timestamp(value.get("occurred_at"), "Notification time"),
        "source_updated_at": _clean_optional_timestamp(
            value.get("source_updated_at"), "Notification source time"
        ),
        "desktop_eligible": desktop_eligible,
    }


def _row_to_item(row: sqlite3.Row, *, now_text: str) -> dict[str, Any]:
    snoozed_until = row["snoozed_until"]
    is_snoozed = bool(snoozed_until and str(snoozed_until) > now_text)
    return {
        "notification_id": str(row["notification_id"]),
        "category": str(row["category"]),
        "kind": str(row["kind"]),
        "priority": str(row["priority"]),
        "title": str(row["title"]),
        "body": str(row["body"]),
        "href": str(row["href"]),
        "occurred_at": str(row["occurred_at"]),
        "read_at": row["read_at"],
        "dismissed_at": row["dismissed_at"],
        "snoozed_until": snoozed_until,
        "resolved_at": row["resolved_at"],
        "desktop_delivered_at": row["desktop_delivered_at"],
        "is_unread": row["read_at"] is None,
        "is_snoozed": is_snoozed,
    }


def build_overview(
    *, db_path: Path | str = DEFAULT_NOTIFICATION_DB, now: datetime | None = None
) -> dict[str, Any]:
    init_db(db_path)
    current = (now or utc_now()).astimezone(UTC).replace(microsecond=0)
    now_text = current.isoformat()
    with connect(db_path) as con:
        settings = con.execute(
            "SELECT desktop_enabled, updated_at FROM notification_settings WHERE id = 1"
        ).fetchone()
        active_rows = con.execute(
            """
            SELECT * FROM notifications
            WHERE resolved_at IS NULL AND dismissed_at IS NULL
            ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'attention' THEN 2 ELSE 3 END,
                     occurred_at DESC
            """
        ).fetchall()
        archived_rows = con.execute(
            """
            SELECT * FROM notifications
            WHERE resolved_at IS NOT NULL OR dismissed_at IS NOT NULL
            ORDER BY COALESCE(dismissed_at, resolved_at, occurred_at) DESC
            LIMIT 100
            """
        ).fetchall()

    active_pairs = [(_row_to_item(row, now_text=now_text), row) for row in active_rows]
    active = [item for item, _row in active_pairs]
    inbox_pairs = [(item, row) for item, row in active_pairs if not item["is_snoozed"]]
    inbox = [item for item, _row in inbox_pairs]
    snoozed = [item for item, _row in active_pairs if item["is_snoozed"]]
    archived = [_row_to_item(row, now_text=now_text) for row in archived_rows]
    desktop_enabled = bool(settings["desktop_enabled"]) if settings else False
    desktop_pending = [
        item
        for item, row in inbox_pairs
        if desktop_enabled
        and item["is_unread"]
        and item["desktop_delivered_at"] is None
        and bool(row["desktop_eligible"])
    ][:20]
    return {
        "schema": "career_notification_overview_v1",
        "generated_at": now_text,
        "counts": {
            "active": len(active),
            "unread": sum(item["is_unread"] for item in inbox),
            "urgent": sum(item["priority"] == "urgent" for item in inbox),
            "attention": sum(item["priority"] == "attention" for item in inbox),
            "snoozed": len(snoozed),
            "archived": len(archived),
        },
        "inbox": inbox,
        "snoozed": snoozed,
        "archived": archived,
        "desktop_pending": desktop_pending,
        "settings": {
            "desktop_enabled": desktop_enabled,
            "updated_at": str(settings["updated_at"]) if settings else now_text,
        },
    }


def sync_candidates(
    payload: Any,
    *,
    db_path: Path | str = DEFAULT_NOTIFICATION_DB,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Notification sync payload must be an object.")
    raw_candidates = payload.get("candidates")
    raw_scopes = payload.get("synced_scopes")
    if not isinstance(raw_candidates, list) or len(raw_candidates) > MAX_CANDIDATES:
        raise ValueError("Notification sync contains too many candidates.")
    if not isinstance(raw_scopes, list) or any(scope not in SCOPES for scope in raw_scopes):
        raise ValueError("Notification sync scopes are invalid.")
    scopes = set(raw_scopes)
    candidates = [validate_candidate(candidate) for candidate in raw_candidates]
    if len({candidate["notification_id"] for candidate in candidates}) != len(candidates):
        raise ValueError("Notification sync contains duplicate candidates.")
    if any(candidate["scope"] not in scopes for candidate in candidates):
        raise ValueError("Notification candidate scope was not synchronized.")

    init_db(db_path)
    now_text = (now or utc_now()).astimezone(UTC).replace(microsecond=0).isoformat()
    with connect(db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        for candidate in candidates:
            con.execute(
                """
                INSERT INTO notifications(
                  notification_id, scope, category, kind, priority, lifecycle,
                  title, body, href, occurred_at, source_updated_at,
                  desktop_eligible, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(notification_id) DO UPDATE SET
                  scope = excluded.scope,
                  category = excluded.category,
                  kind = excluded.kind,
                  priority = excluded.priority,
                  lifecycle = excluded.lifecycle,
                  title = excluded.title,
                  body = excluded.body,
                  href = excluded.href,
                  occurred_at = excluded.occurred_at,
                  source_updated_at = excluded.source_updated_at,
                  desktop_eligible = excluded.desktop_eligible,
                  last_seen_at = excluded.last_seen_at,
                  resolved_at = NULL
                """,
                (
                    candidate["notification_id"],
                    candidate["scope"],
                    candidate["category"],
                    candidate["kind"],
                    candidate["priority"],
                    candidate["lifecycle"],
                    candidate["title"],
                    candidate["body"],
                    candidate["href"],
                    candidate["occurred_at"],
                    candidate["source_updated_at"],
                    int(candidate["desktop_eligible"]),
                    now_text,
                    now_text,
                ),
            )

        for scope in scopes:
            condition_ids = [
                candidate["notification_id"]
                for candidate in candidates
                if candidate["scope"] == scope and candidate["lifecycle"] == "condition"
            ]
            if condition_ids:
                placeholders = ",".join("?" for _ in condition_ids)
                con.execute(
                    f"""
                    UPDATE notifications
                    SET resolved_at = ?
                    WHERE scope = ? AND lifecycle = 'condition' AND resolved_at IS NULL
                      AND notification_id NOT IN ({placeholders})
                    """,  # noqa: S608 - placeholders are generated, values stay parameterized
                    (now_text, scope, *condition_ids),
                )
            else:
                con.execute(
                    """
                    UPDATE notifications
                    SET resolved_at = ?
                    WHERE scope = ? AND lifecycle = 'condition' AND resolved_at IS NULL
                    """,
                    (now_text, scope),
                )
        con.commit()
    return build_overview(db_path=db_path, now=now)


def _require_existing(con: sqlite3.Connection, notification_id: str) -> None:
    row = con.execute(
        "SELECT 1 FROM notifications WHERE notification_id = ?", (notification_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Notification was not found.")


def perform_action(
    payload: Any,
    *,
    db_path: Path | str = DEFAULT_NOTIFICATION_DB,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Notification action payload must be an object.")
    action = payload.get("action")
    current = (now or utc_now()).astimezone(UTC).replace(microsecond=0)
    now_text = current.isoformat()
    init_db(db_path)

    with connect(db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        if action in INDIVIDUAL_ACTIONS:
            notification_id = validate_notification_id(payload.get("notification_id"))
            _require_existing(con, notification_id)
            if action == "read":
                con.execute(
                    "UPDATE notifications SET read_at = ? WHERE notification_id = ?",
                    (now_text, notification_id),
                )
            elif action == "unread":
                con.execute(
                    "UPDATE notifications SET read_at = NULL WHERE notification_id = ?",
                    (notification_id,),
                )
            elif action == "dismiss":
                con.execute(
                    """
                    UPDATE notifications
                    SET dismissed_at = ?, read_at = COALESCE(read_at, ?)
                    WHERE notification_id = ?
                    """,
                    (now_text, now_text, notification_id),
                )
            elif action == "restore":
                con.execute(
                    "UPDATE notifications SET dismissed_at = NULL WHERE notification_id = ?",
                    (notification_id,),
                )
            elif action in {"snooze_day", "snooze_week"}:
                days = 1 if action == "snooze_day" else 7
                snoozed_until = (current + timedelta(days=days)).isoformat()
                con.execute(
                    """
                    UPDATE notifications
                    SET snoozed_until = ?, read_at = COALESCE(read_at, ?)
                    WHERE notification_id = ?
                    """,
                    (snoozed_until, now_text, notification_id),
                )
            else:
                con.execute(
                    "UPDATE notifications SET snoozed_until = NULL WHERE notification_id = ?",
                    (notification_id,),
                )
        elif action == "read_all":
            con.execute(
                """
                UPDATE notifications SET read_at = ?
                WHERE resolved_at IS NULL AND dismissed_at IS NULL AND read_at IS NULL
                """,
                (now_text,),
            )
        elif action == "set_desktop":
            enabled = payload.get("enabled")
            mark_existing = payload.get("mark_existing", False)
            if not isinstance(enabled, bool) or not isinstance(mark_existing, bool):
                raise ValueError("Desktop notification setting is invalid.")
            con.execute(
                """
                UPDATE notification_settings
                SET desktop_enabled = ?, updated_at = ? WHERE id = 1
                """,
                (int(enabled), now_text),
            )
            if enabled and mark_existing:
                con.execute(
                    """
                    UPDATE notifications SET desktop_delivered_at = ?
                    WHERE resolved_at IS NULL AND dismissed_at IS NULL
                      AND desktop_delivered_at IS NULL
                    """,
                    (now_text,),
                )
        elif action == "desktop_delivered":
            raw_ids = payload.get("notification_ids")
            if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > MAX_DESKTOP_IDS:
                raise ValueError("Desktop delivery list is invalid.")
            notification_ids = [validate_notification_id(value) for value in raw_ids]
            if len(set(notification_ids)) != len(notification_ids):
                raise ValueError("Desktop delivery list contains duplicates.")
            placeholders = ",".join("?" for _ in notification_ids)
            con.execute(
                f"""
                UPDATE notifications SET desktop_delivered_at = ?
                WHERE notification_id IN ({placeholders})
                """,  # noqa: S608 - placeholders are generated, values stay parameterized
                (now_text, *notification_ids),
            )
        else:
            raise ValueError("Unsupported notification action.")
        con.commit()
    return build_overview(db_path=db_path, now=now)


def _read_payload() -> Any:
    raw = sys.stdin.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Notification request is too large.")
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Notification request must be valid JSON.") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career notification inbox helper")
    parser.add_argument("--db", type=Path, default=DEFAULT_NOTIFICATION_DB)
    parser.add_argument("command", choices=("overview", "sync", "action"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "overview":
            data = build_overview(db_path=args.db)
        elif args.command == "sync":
            data = sync_candidates(_read_payload(), db_path=args.db)
        else:
            data = perform_action(_read_payload(), db_path=args.db)
    except Exception as exc:
        print(helper_json({"ok": False, "error": str(exc)}))
        return 1
    print(helper_json({"ok": True, "data": data}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
