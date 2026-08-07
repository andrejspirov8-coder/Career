# Job-to-CV Batch Matching Automation

This automation suite matches job postings to your available CV variants and automatically generates application packs.

## Overview

You have three automation tools:

1. **`job_match.py`** — Match a single job to CV variants (existing)
2. **`batch_match_and_pack.py`** — Batch process all jobs in inbox and generate summary report
3. **`watch_and_match.py`** — Continuous monitoring: auto-matches new jobs as they arrive

## Available CV Variants

The system recognizes **4 CV variants** defined in `cv/variant_profiles.yaml`:

| Variant | PDF Stem | Focus |
|---------|----------|-------|
| `luxury-retail` | `andrej-spirov-cv-luxury-retail` | Boutique, store management, luxury goods, clienteling |
| `luxury-retail-lt` | `andrej-spirov-cv-luxury-retail-lt` | Lithuanian-language premium retail and store leadership |
| `operations-management` | `andrej-spirov-cv-operations-management` | Multi-site ops, team leadership, KPIs, retail operations |
| `it-business` | `andrej-spirov-cv-it-business` | Technical support, business analysis, automation, systems |

Each variant has:
- Markdown CV source: `cv/andrej-spirov-cv-<slug>.md`
- Visual PDF: `output/andrej-spirov-cv-<slug>.pdf`
- ATS PDF: `output/andrej-spirov-cv-<slug>-ats.pdf`
- Profile: Keywords and negative keywords in `variant_profiles.yaml`

## Quick Start

### Option 1: Batch Process All Jobs (One-Time)

```bash
cd tools
python3 batch_match_and_pack.py
```

This:
- Scans `inbox/jobs/` for all `*.job.txt` files
- Matches each to your CV variants
- Generates application pack for each job
- Creates summary report with all matches

**Output:**
- Application packs in `packs/<job-id>/` (each contains README, MATCH.json, KEYWORD_GAPS.md)
- Summary report: `summary_report_YYYYMMDD_HHMMSS.md`

### Option 2: Watch Continuously (Daemon Mode)

```bash
cd tools
python3 watch_and_match.py
```

This:
- Monitors `inbox/jobs/` every 5 seconds
- Auto-processes any new `*.job.txt` files
- Generates pack for each new job
- Tracks processed jobs (won't re-process)
- Runs indefinitely until interrupted (`Ctrl+C`)

**Configuration:**

```bash
# Check every 30 seconds instead of 5
python3 watch_and_match.py --interval 30

# One-time scan (like batch but continuous monitoring)
python3 watch_and_match.py --once
```

### Option 3: Single Job (Manual)

```bash
cd tools
python3 job_match.py ../inbox/jobs/your_job.job.txt
```

## Job File Format

Place job postings in `inbox/jobs/` with extension `.job.txt`.

**Template:** `inbox/jobs/JOB_TEMPLATE.txt`

```
TITLE: Job Title
COMPANY: Company Name
URL: https://example.com/jobs/123
SOURCE: linkedin
JOB_ID: (optional - unique identifier)
---
Paste full job description here.
Can span multiple lines.
All text after --- is treated as job body.
```

**Example:** `inbox/jobs/_example_luxury_Vilnius.job.txt` (already included)

## Generated Application Packs

Each pack is a directory: `packs/<YYYYMMDD>-<company>-<title>/`

**Contents:**

1. **README.txt** — Checklist before applying
   - Confirms variant choice
   - Lists PDF locations
   - Workflow reminder

2. **MATCH.json** — Full matching results (machine-readable)
   - Job metadata
   - All variants ranked with scores
   - Recommendation details
   - PDF paths

3. **KEYWORD_GAPS.md** — Gap analysis
   - Terms in job but missing from chosen CV
   - Suggestions for optional weaving in

4. **job_input.txt** — Copy of original job file (for reference)

## Matching Algorithm

The system scores each CV variant against the job posting:

1. **Keyword Scoring**: Counts matches for variant-specific keywords
   - Title & company given 2-3x weight boost
   - Each keyword occurrence capped at 3 hits
   - **Formula**: `score = sum(keyword_hits) - (negative_keyword_penalties)`

2. **Tie-Breaking**: Uses "summary token overlap"
   - Extracts "Professional Summary" from variant's Markdown CV
   - Calculates overlap with job's tokenized text
   - Used only to break close scores

3. **Confidence Levels**:
   - **`clear_winner`**: Top score ≥ 5 points ahead of runner-up (or ≥15% margin)
   - **`tie_review`**: Close match; recommendation suggests manual review of top 2

## Workflow After Matching

Once a pack is generated:

1. **Review** the recommended variant in README.txt
2. **Edit** your CV Markdown if needed (add suggested keywords truthfully; cite metrics only if already listed in `cv/CV_METRICS_INTAKE.md`)
3. **Rebuild** PDFs:
   ```bash
   cd cv
   python3 build_cv_pdf.py --all
   ```
4. **Check metrics** in `CV_METRICS_INTAKE.md` — only cite numbers here
5. **Submit** using the appropriate PDF:
   - ATS portals: `*-ats.pdf`
   - Direct email: `*.pdf` (visual version)

## Profiles Customization

**Edit** `cv/variant_profiles.yaml` to adjust matching:

```yaml
variants:
  your-variant:
    pdf_stem: andrej-spirov-cv-your-variant
    markdown: andrej-spirov-cv-your-variant.md
    target_titles:
      - Title 1
      - Title 2
    keywords:
      - keyword1
      - keyword2
      - "multi-word phrase"
    negative_keywords:
      - avoid_if_jd_contains_this
```

**Keywords**: Searched as substrings (lowercase, case-insensitive)
**Negative Keywords**: Penalize variant if found in JD (6 points)

## Commands Reference

| Command | Purpose |
|---------|---------|
| `batch_match_and_pack.py` | Batch process all jobs, generate summary |
| `batch_match_and_pack.py --dry-run` | Scan & match without writing files |
| `batch_match_and_pack.py --report path/file.md` | Custom report location |
| `batch_match_and_pack.py --json-report path/file.json` | Also export raw JSON |
| `watch_and_match.py` | Continuous monitoring (Ctrl+C to stop) |
| `watch_and_match.py --once` | One-time scan |
| `watch_and_match.py --interval 60` | Check every 60 seconds |
| `job_match.py file.job.txt` | Match single job (existing tool) |
| `job_match.py file.job.txt --quiet` | JSON only (no human summary) |

## Tracking & Logs

**`watch_and_match.py` tracking:**
- `.job_processing_log.json` tracks which jobs have been processed
- Prevents re-processing the same file
- Delete this file to reset tracking

**Summary reports:**
- Stored as `summary_report_YYYYMMDD_HHMMSS.md`
- Always printable to stdout
- Optional JSON export with `--json-report`

## Tips & Best Practices

1. **Batch First**: Run `batch_match_and_pack.py` once to process backlog
2. **Then Watch**: Switch to `watch_and_match.py` for ongoing additions
3. **Review Regularly**: Check generated packs before submitting
4. **Update Keywords**: As you get callbacks, update variant profiles
5. **Rebuild PDFs**: After any CV edit, run `python3 cv/build_cv_pdf.py --all`
6. **Verify Metrics**: Any stat you cite must be in `CV_METRICS_INTAKE.md`

## Troubleshooting

**No jobs found:**
```bash
# Check inbox/jobs exists and contains *.job.txt files
ls -la inbox/jobs/
```

**Import errors:**
```bash
# Ensure dependencies installed
python3 -m pip install -r requirements.txt
```

**Watch script exits unexpectedly:**
```bash
# Check for errors in processing log
python3 watch_and_match.py --once  # Dry run
```

**Variant not appearing:**
- Confirm variant is in `cv/variant_profiles.yaml`
- Check `markdown` and `pdf_stem` match actual files
- Verify Markdown file exists: `cv/andrej-spirov-cv-<slug>.md`
