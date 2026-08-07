"""Opportunity discovery, deduplication, and primary-record persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from career_job_search.core.context import current_user_id
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityStatus,
    company_title_location_key,
    content_hash_from_parts,
    native_source_identity,
    next_action_for_opportunity,
    utc_now_iso,
)
from career_job_search.opportunities.repository_db import (
    DEFAULT_OPPORTUNITY_DB,
    connect,
    init_db,
)


def _uid() -> str:
    return current_user_id.get()


def upsert_opportunities(
    opportunities: list[Opportunity],
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> int:
    init_db(db_path)
    now = utc_now_iso()
    with connect(db_path) as con:
        for opportunity in opportunities:
            aliases = _alias_specs(opportunity)
            row = _resolve_discovery_row(con, opportunity, now=now, user_id=_uid())
            existing = _row_to_opportunity(row) if row else None
            created_at = str(row["created_at"]) if row else now
            if existing is not None:
                opportunity.opportunity_id = existing.opportunity_id
                opportunity.dedupe_key = existing.dedupe_key
                opportunity.canonical_identity = existing.canonical_identity
                if existing.native_source_id and opportunity.source != existing.source:
                    opportunity.source = existing.source
                    opportunity.native_source_id = existing.native_source_id
            opportunity = _merge_fresh_discovery(opportunity, existing, now=now)
            _write_discovered_opportunity(
                con,
                opportunity,
                created_at=created_at,
                now=now,
                exists=existing is not None,
                user_id=_uid(),
            )
            _register_aliases(
                con,
                aliases,
                opportunity_id=opportunity.opportunity_id,
                now=now,
                user_id=_uid(),
            )
    return len(opportunities)


def _alias_specs(opportunity: Opportunity) -> list[tuple[str, str, str, str]]:
    aliases: list[tuple[str, str, str, str]] = []
    if opportunity.source_url:
        aliases.append(
            (
                f"url:{opportunity.source_url}",
                "url",
                opportunity.source,
                opportunity.native_source_id,
            )
        )
    if opportunity.native_source_id:
        aliases.append(
            (
                native_source_identity(
                    opportunity.source, opportunity.native_source_id
                ),
                "native",
                opportunity.source,
                opportunity.native_source_id,
            )
        )
    semantic = company_title_location_key(
        opportunity.company, opportunity.title, opportunity.location
    )
    if semantic != "ctl:":
        aliases.append(
            (
                semantic,
                "semantic",
                opportunity.source,
                opportunity.native_source_id,
            )
        )
    return aliases


def _resolve_discovery_row(
    con: sqlite3.Connection,
    opportunity: Opportunity,
    *,
    now: str,
    user_id: str,
) -> sqlite3.Row | None:
    aliases = _alias_specs(opportunity)
    exact_aliases = [alias for alias in aliases if alias[1] in {"native", "url"}]
    for alias_key, _, _, _ in exact_aliases:
        row = _row_for_alias(con, alias_key, user_id=user_id)
        if row and not _is_new_same_source_native(opportunity, row):
            return row

    cutoff = (
        datetime.fromisoformat(now).astimezone(UTC) - timedelta(days=30)
    ).isoformat()
    for alias_key, alias_type, _, _ in aliases:
        if alias_type != "semantic":
            continue
        row = con.execute(
            """
            SELECT o.data_json, o.created_at
            FROM opportunity_aliases AS a
            JOIN opportunities AS o ON o.opportunity_id = a.opportunity_id
            WHERE a.alias_key = ? AND o.user_id = ? AND a.last_seen_at >= ?
            LIMIT 1
            """,
            (alias_key, user_id, cutoff),
        ).fetchone()
        if row and not _is_new_same_source_native(opportunity, row):
            return row

    return con.execute(
        """
        SELECT data_json, created_at
        FROM opportunities
        WHERE (dedupe_key = ? OR opportunity_id = ?) AND user_id = ?
        ORDER BY CASE WHEN dedupe_key = ? THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (
            opportunity.dedupe_key,
            opportunity.opportunity_id,
            user_id,
            opportunity.dedupe_key,
        ),
    ).fetchone()


def _row_for_alias(
    con: sqlite3.Connection,
    alias_key: str,
    *,
    user_id: str,
) -> sqlite3.Row | None:
    return con.execute(
        """
        SELECT o.data_json, o.created_at
        FROM opportunity_aliases AS a
        JOIN opportunities AS o ON o.opportunity_id = a.opportunity_id
        WHERE a.alias_key = ? AND o.user_id = ?
        LIMIT 1
        """,
        (alias_key, user_id),
    ).fetchone()


def _is_new_same_source_native(
    opportunity: Opportunity,
    row: sqlite3.Row,
) -> bool:
    if not opportunity.native_source_id:
        return False
    existing = _row_to_opportunity(row)
    return bool(
        existing.source == opportunity.source
        and existing.native_source_id
        and existing.native_source_id != opportunity.native_source_id
    )


def _write_discovered_opportunity(
    con: sqlite3.Connection,
    opportunity: Opportunity,
    *,
    created_at: str,
    now: str,
    exists: bool,
    user_id: str,
) -> None:
    values = (
        user_id,
        opportunity.dedupe_key,
        opportunity.source_kind.value,
        opportunity.source_url,
        opportunity.title,
        opportunity.company,
        opportunity.location,
        opportunity.status.value,
        json.dumps(
            opportunity.to_json_dict(),
            ensure_ascii=False,
            sort_keys=True,
        ),
        now,
        opportunity.opportunity_id,
    )
    if exists:
        con.execute(
            """
            UPDATE opportunities
            SET user_id = ?, dedupe_key = ?, source_kind = ?, source_url = ?, title = ?,
                company = ?, location = ?, status = ?, data_json = ?,
                updated_at = ?
            WHERE opportunity_id = ? AND user_id = ?
            """,
            (*values, user_id),
        )
        return
    con.execute(
        """
        INSERT INTO opportunities(
          opportunity_id, user_id, dedupe_key, source_kind, source_url, title,
          company, location, status, data_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            opportunity.opportunity_id,
            *values[:9],
            created_at,
            now,
        ),
    )


def _register_aliases(
    con: sqlite3.Connection,
    aliases: list[tuple[str, str, str, str]],
    *,
    opportunity_id: str,
    now: str,
    user_id: str,
) -> None:
    for alias_key, alias_type, source, native_source_id in aliases:
        con.execute(
            """
            INSERT OR IGNORE INTO opportunity_aliases(
              alias_key, user_id, alias_type, opportunity_id, source,
              native_source_id, created_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alias_key,
                user_id,
                alias_type,
                opportunity_id,
                source,
                native_source_id,
                now,
                now,
            ),
        )
        con.execute(
            """
            UPDATE opportunity_aliases
            SET last_seen_at = ?
            WHERE alias_key = ? AND opportunity_id = ? AND user_id = ?
            """,
            (now, alias_key, opportunity_id, user_id),
        )


def _merge_fresh_discovery(
    opportunity: Opportunity,
    existing: Opportunity | None,
    *,
    now: str,
) -> Opportunity:
    opportunity.last_seen_at = now
    opportunity.last_checked_at = now
    if existing is None:
        opportunity.first_seen_at = opportunity.first_seen_at or now
        opportunity.likely_closed = False
        opportunity.evidence.risk_flags = [
            flag for flag in opportunity.evidence.risk_flags if flag != "likely_closed"
        ]
        return opportunity

    detail_liveness_preserved = _preserve_detailed_browser_observation(
        opportunity,
        existing,
    )
    previous_hash = _semantic_content_hash(existing)
    opportunity.content_hash = _semantic_content_hash(opportunity)
    opportunity.first_seen_at = existing.first_seen_at or existing.discovered_at
    opportunity.discovered_at = existing.discovered_at
    opportunity.duplicate_cluster_id = (
        opportunity.duplicate_cluster_id
        or existing.duplicate_cluster_id
        or opportunity.opportunity_id
    )
    opportunity.pack = opportunity.pack or existing.pack
    opportunity.source_updated_at = existing.source_updated_at
    if not detail_liveness_preserved:
        opportunity.likely_closed = False
    opportunity.first_eligible_at = (
        opportunity.first_eligible_at or existing.first_eligible_at
    )
    confirmed_eligibility = {
        "eligible_vilnius",
        "eligible_lt_remote",
        "eligible_eu_remote",
    }
    if (
        not opportunity.first_eligible_at
        and opportunity.location_eligibility in confirmed_eligibility
        and existing.location_eligibility not in confirmed_eligibility
    ):
        opportunity.first_eligible_at = now

    flags = [
        flag for flag in opportunity.evidence.risk_flags if flag != "likely_closed"
    ]
    if detail_liveness_preserved and opportunity.live_status == "closed":
        opportunity.likely_closed = True
        opportunity.status = OpportunityStatus.EXPIRED
        flags.append("likely_closed")
    preserved_statuses = {
        OpportunityStatus.APPLIED,
        OpportunityStatus.SKIPPED,
        OpportunityStatus.APPLY_READY,
        OpportunityStatus.FOLLOW_UP,
        OpportunityStatus.EXPIRED,
    }
    if existing.status in preserved_statuses:
        opportunity.status = existing.status
    if previous_hash and previous_hash != opportunity.content_hash:
        opportunity.source_updated_at = now
        flags.append("role_updated")
        if existing.status not in preserved_statuses:
            opportunity.status = OpportunityStatus.REVIEW

    opportunity.evidence.risk_flags = list(dict.fromkeys(flags))
    opportunity.next_action = next_action_for_opportunity(opportunity)
    return opportunity


def _preserve_detailed_browser_observation(
    opportunity: Opportunity,
    existing: Opportunity,
) -> bool:
    """Keep detail-page evidence when a later browser refresh only has a card."""

    detailed_source_fact = "chrome:linkedin_job_detail"
    if existing.source != "linkedin" or opportunity.source != "linkedin":
        return False
    if detailed_source_fact not in existing.evidence.source_facts:
        return False
    if detailed_source_fact in opportunity.evidence.source_facts:
        return False

    if existing.description:
        opportunity.description = existing.description
    if existing.salary_text and not opportunity.salary_text:
        opportunity.salary_text = existing.salary_text
    if existing.location and opportunity.location.strip() in {
        "",
        opportunity.title.strip(),
    }:
        opportunity.location = existing.location
    if existing.remote_policy and not opportunity.remote_policy:
        opportunity.remote_policy = existing.remote_policy

    opportunity.evidence.source_facts = list(
        dict.fromkeys(
            existing.evidence.source_facts + opportunity.evidence.source_facts
        )
    )
    opportunity.evidence.company_facts = list(
        dict.fromkeys(
            existing.evidence.company_facts + opportunity.evidence.company_facts
        )
    )
    opportunity.evidence.role_facts = list(
        dict.fromkeys(existing.evidence.role_facts + opportunity.evidence.role_facts)
    )
    opportunity.evidence.location_facts = list(
        dict.fromkeys(
            existing.evidence.location_facts + opportunity.evidence.location_facts
        )
    )
    opportunity.evidence.confidence = max(
        existing.evidence.confidence,
        opportunity.evidence.confidence,
    )

    if _recent_browser_detail(existing, opportunity):
        opportunity.live_status = existing.live_status
        opportunity.live_checked_at = existing.live_checked_at
        opportunity.live_check_note = existing.live_check_note

    if existing.live_status == "closed":
        opportunity.live_status = "closed"
        opportunity.live_checked_at = existing.live_checked_at
        opportunity.live_check_note = existing.live_check_note

    return True


def _recent_browser_detail(
    existing: Opportunity,
    incoming: Opportunity,
) -> bool:
    if existing.live_check_method != "linkedin_browser":
        return False
    if not existing.live_checked_at or not incoming.live_checked_at:
        return False
    try:
        existing_checked = datetime.fromisoformat(
            existing.live_checked_at.replace("Z", "+00:00")
        )
        incoming_checked = datetime.fromisoformat(
            incoming.live_checked_at.replace("Z", "+00:00")
        )
    except ValueError:
        return False
    return abs(incoming_checked - existing_checked) <= timedelta(hours=24)


def _semantic_content_hash(opportunity: Opportunity) -> str:
    return content_hash_from_parts(
        opportunity.title,
        opportunity.company,
        opportunity.location,
        opportunity.remote_policy,
        opportunity.description,
        opportunity.salary_text,
        opportunity.deadline,
    )


def _row_to_opportunity(row: sqlite3.Row) -> Opportunity:
    data = json.loads(str(row["data_json"] or "{}"))
    return Opportunity.model_validate(data)


def list_opportunities(
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> list[Opportunity]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT data_json FROM opportunities
            WHERE user_id = ?
            ORDER BY updated_at DESC, created_at DESC
            """,
            (_uid(),),
        ).fetchall()
    return [_row_to_opportunity(row) for row in rows]


def get_opportunity(
    opportunity_id: str,
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> Opportunity | None:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT data_json FROM opportunities
            WHERE opportunity_id = ? AND user_id = ? LIMIT 1
            """,
            (opportunity_id, _uid()),
        ).fetchone()
    return _row_to_opportunity(row) if row else None


def save_opportunity(
    opportunity: Opportunity,
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
) -> Opportunity:
    init_db(db_path)
    now = utc_now_iso()
    data = opportunity.to_json_dict()
    user_id = _uid()
    with connect(db_path) as con:
        existing = con.execute(
            """
            SELECT created_at FROM opportunities
            WHERE dedupe_key = ? AND user_id = ? LIMIT 1
            """,
            (opportunity.dedupe_key, user_id),
        ).fetchone()
        created_at = str(existing["created_at"]) if existing else now
        con.execute(
            """
            INSERT INTO opportunities(
              opportunity_id, user_id, dedupe_key, source_kind, source_url, title,
              company, location, status, data_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, dedupe_key) DO UPDATE SET
              opportunity_id = excluded.opportunity_id,
              source_kind = excluded.source_kind,
              source_url = excluded.source_url,
              title = excluded.title,
              company = excluded.company,
              location = excluded.location,
              status = excluded.status,
              data_json = excluded.data_json,
              updated_at = excluded.updated_at
            """,
            (
                opportunity.opportunity_id,
                user_id,
                opportunity.dedupe_key,
                opportunity.source_kind.value,
                opportunity.source_url,
                opportunity.title,
                opportunity.company,
                opportunity.location,
                opportunity.status.value,
                json.dumps(data, ensure_ascii=False, sort_keys=True),
                created_at,
                now,
            ),
        )
    return opportunity
