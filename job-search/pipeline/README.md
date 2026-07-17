# Application pipeline log

Append one row per submission to **`applications.csv`** (open in Excel, LibreOffice, or Sheets).

Columns:

| Column | Meaning |
|--------|---------|
| `date_iso` | YYYY-MM-DD you clicked submit or sent the CV |
| `company` | Employer; match `COMPANY` in inbox files when you can |
| `title` | Advertised role |
| `variant_slug` | `luxury-retail` \| `luxury-retail-lt` \| `operations-management` \| `operations-management-lt` \| `business-process-operations` \| `it-business` |
| `source` | e.g. `company_site`, `linkedin`, `cvbank` |
| `outcome` | `applied`, `rejected`, `screening`, `interview`, `offer`, `withdrawn` |
| `deadline_date` | Optional YYYY-MM-DD closing date for the advert |
| `match_score` | Optional score copied from the generated `MATCH.json` |
| `match_confidence` | Optional `clear_winner` or `tie_review` from `MATCH.json` |
| `salary_range` | Gross salary range from the advert, if shown |
| `tailored_cv` | `yes` if the CV was adjusted for the role; otherwise `no` |
| `response_date` | YYYY-MM-DD when the first employer/recruiter response arrived |
| `opportunity_id` | Optional ID from the opportunity dashboard, e.g. `opp_123` |
| `pack_dir` | Optional local folder path for the generated application pack |
| `application_url` | Optional final page where you submitted or will submit manually |
| `notes` | Interviewers, links, salary, lessons learned |

Use `business-process-operations` as the default for Vilnius business analyst, process analyst, operations analyst, customer operations, and implementation support roles.

Review weekly which **variant_slug**, source, match score, and tailoring choice leads to funnel progress. Wait for at least 10 applications per lane before treating the signal as reliable.

---

## Opportunity intelligence state

The broader opportunity workflow stores local SQLite state under
`state/opportunities.sqlite3` and keeps generated application packs under
`packs/`. Both locations are intentionally gitignored.

Start with:

```bash
uv run python tools/opportunity_orchestrate.py --config config/opportunities.example.yaml discover --dry-run
uv run python tools/opportunity_orchestrate.py --config config/opportunities.example.yaml discover
uv run python tools/opportunity_orchestrate.py match
```

Then review `/opportunities` in the local dashboard. The workflow can generate a
local pack and track manual outcomes, but it does not auto-apply.

---

## LinkedIn recruiter scout log

The Playwright recruiter bot appends **`recruiters.csv`** (tracked locally via `.gitignore`) every time it scores or pings a recruiter.

Columns:

| Column | Meaning |
|--------|---------|
| `date_iso` | YYYY-MM-DD of the scrape / invite attempt |
| `profile_url` | Canonical `/in/username/` permalink |
| `name` | Display name scraped from the profile chrome |
| `headline` | Headline scraped when available |
| `variant_slug` | Best matching CV slug (sector + CV hybrid; see `recruiter_match.py`) |
| `primary_score` | Unified score snapshot |
| `runner_up_slug` | Second-place variant from CV matcher (audit aid) |
| `runner_up_score` | Second-place score |
| `margin_over_second` | Gap between #1 and #2 (threshold in `linkedin/config.yaml`) |
| `top_signals` | Sector keywords that fired on the recruiter profile |
| `connect_path` | `primary`, `more_menu`, or `none` (how Connect was reached) |
| `confidence` | `clear_winner` vs `tie_review` (sector/CV hybrid) |
| `status` | `sent`, `skipped`, `blocked`, `skipped_pending`, `dry_run_*`, etc. |
| `skip_reason` | Machine-readable reason when not sent |
| `note_preview` | First ~220 chars of the drafted invite note |
| `accepted_at` | Filled by `tools/linkedin_followup.py` when invite shows as accepted |
| `withdraw_or_pending` | From sent-invite list: `pending`, `withdrawn`, or empty when accepted/unknown |
| `reply_at` | Filled by follow-up script when messaging preview suggests a reply |
| `reply_excerpt` | Short snippet from the messaging preview |
| `interview_at` | Optional: add manually after a recruiter call |

Reference header without personal data lives in **`recruiters.example.csv`**.

**Funnel KPIs:** acceptance rate = rows with `accepted_at` / rows with `status=sent`; reply rate uses `reply_at`; interview rate uses `interview_at` (manual). Run `python3 tools/recruiter_performance.py` for a variant summary (and a `note_preview` rollup for sent rows). For machine-readable note-level stats: `python3 tools/recruiter_performance.py --csv --notes-csv`.
