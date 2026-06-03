# Career job-search workspace

> Current source of truth: use `/Users/andrejspirov/Career/Career-main/job-search` for CV edits, matching, packs, and application tracking. This duplicate folder is kept for reference unless you intentionally choose to migrate it back.

This folder keeps CV source files, finished PDFs, job adverts, matching results, and application tracking in one place.

The daily workflow starts in Raycast. Raycast is the macOS command launcher opened with a keyboard shortcut.

## Daily flow

1. Open Raycast and run `Job: New`.
2. Paste the full job advert into the new `.job.txt` file.
3. Run `Job: Match All` to score the advert against the CV variants.
4. Run `Job: Review` to inspect the recommended CV and keyword gaps.
5. Submit the right PDF yourself.
6. Run `Job: Log Application` after applying.
7. Run `Job: Analytics` to review which CV variants and sources perform best.

## CV source of truth

Edit Markdown files in `cv/`. These are the editable CV sources:

| Variant | Source file | Use for |
| --- | --- | --- |
| `luxury-retail` | `cv/andrej-spirov-cv-luxury-retail.md` | Premium retail, boutique, store leadership |
| `luxury-retail-lt` | `cv/andrej-spirov-cv-luxury-retail-lt.md` | Lithuanian-language retail roles |
| `operations-management` | `cv/andrej-spirov-cv-operations-management.md` | Operations, service, multi-site leadership |
| `it-business` | `cv/andrej-spirov-cv-it-business.md` | IT support, business analysis, systems roles |

Before adding a metric to a CV, record it in `cv/CV_METRICS_INTAKE.md` so it is easy to defend in an interview.

## Finished files

Send or upload files from `output/`.

| File type | Location | When to use |
| --- | --- | --- |
| Visual PDF | `output/andrej-spirov-cv-<variant>.pdf` | Emailing a person or sharing a polished CV |
| ATS PDF | `output/andrej-spirov-cv-<variant>-ats.pdf` | Online application portals |
| Canva paste text | `output/canva/` | Rebuilding the design in Canva |

ATS means applicant tracking system: the software many hiring portals use to read uploaded CVs.

Rebuild all CV outputs:

```bash
python3 cv/build_cv_pdf.py --all
```

Or use Raycast: `Job: Rebuild CVs`.

## Job matching

Job adverts live in `inbox/jobs/` as `.job.txt` files. Each file uses this shape:

```text
TITLE: Job Title
COMPANY: Company Name
URL: https://example.com/jobs/123
SOURCE: linkedin
JOB_ID:
---
Paste the full job advert here.
```

Application packs are generated in `packs/<job-id>/`. Each pack contains the match result, keyword gaps, and absolute paths to the recommended PDFs.

## Application tracking

Log every submitted application in `pipeline/applications.csv`.

Use consistent source names:

| Channel | Source value |
| --- | --- |
| LinkedIn | `linkedin` |
| CVbank.lt | `cvbank` |
| CV.lt | `cv_lt` |
| Startup or tech listing | `startup_lt` |
| Work in Lithuania | `work_in_lt` |
| Employer site | `company_site` |
| Recruiter | `recruiter` |
| Indeed | `indeed` |

After 10 or more applications, run analytics:

```bash
python3 tools/variant_performance.py
python3 tools/variant_performance.py --by source
```

## Useful commands

```bash
# Install Python requirements
python3 -m pip install -r requirements.txt

# Create a job file from the terminal
python3 tools/new_job.py

# Match all inbox jobs
python3 tools/batch_match_and_pack.py

# Review generated packs
python3 tools/review_packs.py --sort score

# Rebuild all CV PDFs and Canva text files
python3 cv/build_cv_pdf.py --all
```

## LinkedIn recruiter scout (optional)

Playwright-backed outreach that reuses CV keyword scoring (`matching_lib`). It launches **installed Google Chrome** (see `linkedin/config.yaml`). Documentation and safeguards live in [`linkedin/README.md`](linkedin/README.md)—read before running because high-volume invites can throttle your account.

Older planning and optimization notes are archived under `archive/2026-05-19-cleanup/docs/`.
