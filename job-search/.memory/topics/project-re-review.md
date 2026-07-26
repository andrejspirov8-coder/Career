# Project Re-Review

- 2026-07-26 — started second-pass re-review of `/career` project to verify every finding from previous review
- 2026-07-26 — confirmed `proxy.ts` is valid Next.js 16 middleware (PROXY_FILENAME convention, registered in functions-config-manifest with runtime: nodejs); previous F1 was false
- 2026-07-26 — confirmed vite@8.0.16 is installed and resolves correctly; previous F12 was false
- 2026-07-26 — confirmed SQLite backup handles WAL correctly (sqlite3.backup() API); previous F11 was false
- 2026-07-26 — confirmed `hiring_models.py` architecture violation is real (F3), test catches it
- 2026-07-26 — confirmed `/_not-found` prerender failure (F14) blocks production build
- 2026-07-26 — confirmed no live secrets in git history; .env files properly gitignored
- 2026-07-26 — wrote re-review to Obsidian vault at `~/Documents/Obsidian Vault/Career Project Review.md`
- 2026-07-26 — F3 resolved: hiring_models.py now imports canonical_linkedin_profile_url from core.linkedin_urls instead of integrations.linkedin.selectors; architecture test passes
