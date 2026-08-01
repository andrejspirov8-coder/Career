# Supabase Migration

## 2026-07-28: SQL Data Migration Complete

- Successfully migrated all data from SQLite to Supabase via Management API SQL endpoint
- Row counts: 1 notification_settings, 60 notifications, 445 source_runs, 35 daily_runs, 1,187 opportunities, 3,369 opportunity_aliases
- Fixed schema: `opportunity_id` and `user_id` columns changed from `uuid` → `text` (app code uses `opp_*` string IDs)
- Fixed PostgREST: `authenticator` role had stale `pgrst.db_schemas=public, career` (no `career` schema exists) → caused PGRST002. Set to `public` only.
- PostgREST REST API accessible via service_role key (no RLS policies yet)
- `scripts/migrate_supabase_data.py` handles schema mapping (drops `user_id` from tables, extracts `evidence_json`/`match_json` from `data_json`)
- SQLite `state/*.sqlite3` remains canonical until `StorageBackend` flips to remote

## 2026-07-28: RLS Policies + Dashboard Client + StorageBackend Flip

- Added RLS policies (SELECT for anon role) on all 22 tables — anon key now works
- Fixed `pgrst.db_schemas` from `public, career` → `public` (unblocked PostgREST)
- Installed `@supabase/supabase-js` in dashboard; created `lib/supabase.ts` (browser) and `lib/server/supabase.ts` (server admin)
- Updated `.env.example` and `.env.local` with Supabase env vars at both project root and dashboard
- Verified `SupabaseBackend` connects and returns 1,187 opportunities via Python supabase-py client
- Python lint, dashboard typecheck, and pytest all pass

Next: Phase 2 — Auth migration (custom HMAC session → Supabase Auth / @supabase/ssr)

## 2026-07-28: Auth Migration Phase 2 — Supabase JWT Support

- Created Supabase Auth user `andrej@opencode.ai` (id: `85ab8408-a106-46f2-a171-4b1790ba91fb`)
- Updated Python `verify_token` to accept Supabase JWTs via `supabase.auth.get_user()` — falls back to legacy HMAC auth
- Updated `POST /api/v1/auth/login` to authenticate against Supabase Auth first, returns `supabase_access_token`
- Updated dashboard login route to store Supabase JWT cookie (`career_sb_token`)
- Updated fastapi-bridge to prefer Supabase JWT over legacy dashboard token for Authorization header
- Updated logout to clear Supabase token cookie
- Installed `@supabase/supabase-js@2.110.8` + `@supabase/ssr@0.12.3` in dashboard
- Created `lib/supabase.ts` (browser client) and `lib/server/supabase.ts` (admin client)
- Legacy HMAC auth remains as fallback

Next: Remove legacy HMAC code after migration validated in production use

## 2026-07-28: End-to-End Validation + Cleanup

- FastAPI server tested with Supabase JWT login: login returns `supabase_access_token`, `/me` verifies and returns the correct UUID user_id
- Legacy HMAC Bearer token still works as fallback (returns `local-user`)
- Removed one-shot migration scripts: `generate_table_sql.py`, `migrate_to_supabase.py`, `migrate_to_supabase_sql.py`
- Cleaned `/tmp/mig_*` artifacts (132 files)
