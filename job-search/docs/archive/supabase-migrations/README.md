# Dormant Supabase artifacts

The application does **not** use Supabase or another remote database for
runtime persistence. Local SQLite databases under the git-ignored `state/`
directory remain the only supported persistence layer.

The SQL files in `migrations/` are retained as historical, unapplied design
material. They have not been validated against a live project and must not be
executed as part of normal development, release verification, or scheduled
workflows.

`migrate_private.py` is an intentionally fail-closed placeholder. Do not run it
expecting a migration; it exits non-zero and explains that local SQLite is the
supported architecture.

A future remote-persistence project would require a separate reviewed plan
covering, at minimum:

* a reconciled schema and migration strategy;
* row-level-security and access-policy design;
* credential provisioning, rotation, and secret storage;
* backup, rollback, and recovery procedures;
* runtime ownership and observability; and
* explicit owner approval before any connection or migration code is restored.

Do not place credentials in this directory or in tracked source files.
