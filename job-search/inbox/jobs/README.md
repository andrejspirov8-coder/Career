# Job inbox (paste job ads here)

Save each role as a **`.job.txt`** file in this folder before running the matcher (required for `batch_match_and_pack.py` and `watch_and_match.py`, which glob `*.job.txt`).

## File naming

Suggested pattern:

`YYYYMMDD_company_short-role.job.txt`

Examples:

- `20260511_zara_vilnius-assistant-manager.job.txt`
- `20260512_acme_customer-success.job.txt`

The name is only for your organisation; matching uses the file contents. See the main [README.md](../../README.md) for Lithuania/Vilnius sourcing and `SOURCE` examples.

## File format

1. **Metadata block** (recommended): key `KEY: value`, one per line. Blank lines are ignored in the header until the `---` line.
2. **Separator**: a line containing only `---`
3. **Job description**: paste the full advert (title, bullets, requirements).

Required keys (for best packs):

- `TITLE` — role title as advertised
- `COMPANY` — employer name
- `URL` — link to the posting (or `n/a`)

Optional keys:

- `JOB_ID` — pack folder id; if omitted, the pack tool derives one from date + company slug
- `SOURCE` — e.g. `linkedin`, `cvbank`, `company_site` (see main README table)

After the `---`, the first line often repeats the title; that is fine.

## Template

Copy [`JOB_TEMPLATE.txt`](JOB_TEMPLATE.txt) and fill it in.

For a quick matching smoke-test, see `_example_luxury_Vilnius.job.txt` (fiction).
