# Session memory

- [[project-re-review]] — 2026-07-26 re-review of previous PROJECT-REVIEW.md; corrected false findings about proxy.ts and Vite version
- [[remember-system]] — 2026-07-26: created .memory/ + scripts/remember.sh + make remember/save targets for cross-session persistence
- [[sessions/2026-07-26-2043]] — 2026-07-26 20:43: test handoff
- [[sessions/2026-07-26-2044]] — 2026-07-26 20:44: Update Career workflow to opencode best practices
- [[workflow-improvements]] — 2026-07-26: implemented opencode best practices: opencode.json, review-agent, session-handoff agent, handoff.sh, career-context skill, build fix, pre-commit activation
- [[project-re-review]] — 2026-07-26: F3 resolved: hiring_models.py now imports canonical_linkedin_profile_url from core.linkedin_urls instead of integrations.linkedin.selectors; architecture test passes
- [[mcp-decisions]] — 2026-07-28: 2026-07-28: Decided NOT to add Desktop Commander MCP. Reason: redundant with existing Playwright (browser) and opencode CLI built-in tools (terminal/files). No gap to fill.
- [[2026-07-28-supabase-auth-migration]] — 2026-07-28: Stripped legacy HMAC session auth: removed _parse_session_cookie, dashboardSessionValue, isDashboardSessionAuthorized, DASHBOARD_SESSION_COOKIE from Python and dashboard code. Login/logout routes now only set/clear career_sb_token (Supabase JWT). Dashboard page auth checks career_sb_token cookie existence instead of HMAC session. fastapi-bridge no longer forwards session cookie. Removed duplicate app/api/ routes (conflicted with app/(dashboard)/api/). Updated tests. Python lint, vitest, and dashboard typecheck all pass.
