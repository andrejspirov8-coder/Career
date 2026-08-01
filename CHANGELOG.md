# Changelog

## [0.1.0] — 2026-07-24

### Initial release

- Python package with CV matching, recruiter automation, opportunity tracking, and local dev agents
- Next.js dashboard with HMAC-authenticated sessions and 30+ API routes
- Raycast extension for keyboard-driven workflows
- LinkedIn recruiter automation with multi-gate safety system
- Encrypted backup/restore with AES-256-GCM
- Encrypted backup/restore with AES-256-GCM + scrypt KDF
- Architecture tests enforcing layering and dependency direction

### Security

- Implemented `is_untrusted_content()` with injection pattern detection
- Wired dashboard middleware for CSP headers and auth redirects
- Fixed dashboard layout to redirect unauthenticated users to `/login`
- Pinned all dependency versions
- Added `linkedin/config.yaml` to `.gitignore`

### Infrastructure

- CI pipeline with Python lint, 605 tests, dashboard build/typecheck/browser tests
- npm and pip-audit for supply-chain security scanning
- Pre-commit hooks for ruff, trailing whitespace, and large file checks
- `.editorconfig` for cross-editor consistency

### Data layer

- Fixed `save_snapshot()` and `save_run_state()` — atomic writes with temp file + fsync + replace
- Fixed `append_jsonl()` and `write_jsonl()` — now atomic, crash-safe
- Fixed `save_processed_jobs()` — now atomic write
- Added `busy_timeout` to all SQLite connection functions
- Added `S` (security) rule set to ruff configuration
