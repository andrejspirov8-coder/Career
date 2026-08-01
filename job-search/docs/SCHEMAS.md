# Database & persistence schemas

The career system is single-process and local-first. Persistence is **local
SQLite** under the git-ignored `state/` directory. There is no database
server, no network dependency, and no cross-database data migration.

All SQLite databases share the same versioning mechanism from
`core/sqlite.py`:

- `schema_meta(key, value)` holds a `schema_version` row.
- `migrate_schema()` applies the domain's `SCHEMA_SQL` only when the recorded
  version is behind the module's `SCHEMA_VERSION`, and never downgrades.
- Migrations are **additive** — new migrations append to the `SCHEMA_SQL`
  string and bump `SCHEMA_VERSION`.

Every timestamp is stored as ISO-8601 text in UTC. `TEXT` columns that hold
JSON are named `*_json` (e.g. `data_json`, `metadata_json`).

## Databases

| Database file (under `state/`) | Owner module | Tables |
|---|---|---|
| `opportunities.sqlite3` | `opportunities/repository_db.py` | opportunities, opportunity_actions, source_runs, daily_runs, opportunity_aliases, deliveries |
| `recruiter_state.sqlite3` | `recruiters/repository.py` | recruiter_profiles, workflow_runs, recruiter_decisions, approval_expirations, profile_evidence, operator_actions, followup_tasks, campaign_runs |
| `automation.sqlite3` | `automation/queue.py` | automation_runs, automation_settings, automation_workers |
| `notifications.sqlite3` | `notifications/center.py` | notifications, notification_settings |
| `users.sqlite3` | `api/user_store.py` | users |

The dashboard/API never touches these files directly — it goes through the
FastAPI bridge and helper modules. Backups of every `state/*.sqlite3` are
handled by `workspace/backups.py`.

### `opportunities.sqlite3` — opportunity pipeline

Owned by `opportunities/repository_db.py`. Schema version 1.

- **opportunities** — one row per deduplicated job opportunity. Keyed by
  `opportunity_id`; `dedupe_key` is unique per `user_id`. `data_json` holds
  the full source payload. `status` is the pipeline state.
- **opportunity_actions** — append-only action log per opportunity
  (`status` transitions, source events). `FK → opportunities.opportunity_id`.
- **source_runs** — one row per scrape/source snapshot (LinkedIn, jobs board,
  …) with `item_count` and `duration_ms`.
- **daily_runs** — one row per daily digest run (`output_json` holds the
  digest).
- **opportunity_aliases** — maps external source IDs to an internal
  `opportunity_id`, enabling cross-source deduplication.
  `FK → opportunities.opportunity_id`.
- **deliveries** — records which canonical identity was delivered a given
  opportunity on a given date; unique on `(delivery_date,
  canonical_identity)` to prevent duplicate sends.

Opportunity tables include a `user_id` column
(`TEXT NOT NULL DEFAULT 'local-user'`, injected via the `USER_ID_DDL`
placeholder) to allow per-user partitioning while keeping single-user
defaults.

### `recruiter_state.sqlite3` — recruiter scoring & approvals

Owned by `recruiters/repository.py`. Schema version 1.

- **recruiter_profiles** — normalized LinkedIn recruiter profiles, keyed by
  canonical `profile_url`.
- **workflow_runs** — one row per recruiter workflow run (`mode`, `dry_run`,
  `config_hash`).
- **recruiter_decisions** — per-profile decisions (`status`: `approved` /
  `sent` / `rejected` / …). Unique approval constraint on
  `(profile_url, note_hash, status)` where `status = 'approved'`.
  `FK → recruiter_profiles(profile_url)` and `FK → workflow_runs(run_id)`.
- **approval_expirations** — expiring approvals, keyed on
  `(profile_url, note_hash)`.
- **profile_evidence** — cached evidence buckets per profile
  (`company_facts_json`, `persona_evidence_json`, `cv_fit_evidence_json`,
  `geo_evidence_json`, `risk_flags_json`).
- **operator_actions** — audit log of operator interventions.
- **followup_tasks** — scheduled recruiter follow-ups.
- **campaign_runs** — recruiter campaign lifecycle state.

### `automation.sqlite3` — automation run queue

Owned by `automation/queue.py`. Schema version 1.

- **automation_runs** — queued/active/finished runs. Self-referential
  `FK → automation_runs(run_id)` for parent/child runs. `unique_key` has a
  partial unique index so retries cannot enqueue duplicates.
- **automation_settings** — single-row table (`CHECK (id = 1)`) for the daily
  schedule (`schedule_enabled`, `schedule_time`, `timezone`).
- **automation_workers** — heartbeat rows for worker processes (`pid`, `mode`,
  `status`).

### `notifications.sqlite3` — notification center

Owned by `notifications/center.py`. Schema version 1.

- **notifications** — one row per notification. Lifecycle fields:
  `read_at`, `dismissed_at`, `snoozed_until`, `resolved_at`,
  `desktop_delivered_at`. Active notifications are indexed on
  `(resolved_at, dismissed_at, occurred_at)`.
- **notification_settings** — single-row table (`CHECK (id = 1)`) for
  desktop-notification enablement.

### `users.sqlite3` — local auth fallback

Owned by `api/user_store.py`. Schema version 1.

- **users** — `user_id`, unique `email`, `password_hash`/`password_salt`
  (PBKDF2-HMAC-SHA256), `created_at`. Used as the **fallback** login store;
  when Supabase Auth is configured (`SUPABASE_URL` + `SUPABASE_ANON_KEY` set)
  the API authenticates against Supabase first and the local store is bypassed.

## Non-SQLite persisted state

Several domains persist small preference/catalogue documents as JSON or YAML
files rather than SQLite. Each carries a `schema_version` field for forward
compatibility, but these are **not** under SQLite migration management
(TDEBT-005 tracks bringing them under versioned migration).

| Store | Module | `schema_version` |
|---|---|---|
| CV catalogue index | `cvs/catalogue.py` | `cv_catalogue_v1` |
| Drafting preferences | `cvs/drafting.py` | `career_local_drafting_preferences_v1` |
| Search preferences | `opportunities/preferences.py` | `career_search_preferences_v1` |
| LinkedIn campaign config | `integrations/linkedin/campaign_config.py` | — |

Generated CVs and CV versions live as files under `state/cv_versions/`
(see `README.md`).

## Conventions

- Open connections with `core/sqlite.connect_sqlite()` (enables foreign keys
  and a busy timeout). Use `wal=True` for high-write databases.
- Write through the domain repository modules, never ad-hoc SQL from callers.
- All DB paths resolve under the git-ignored `state/` directory via
  `project_path("state", …)` or `JOB_ROOT / "state" / …`.
