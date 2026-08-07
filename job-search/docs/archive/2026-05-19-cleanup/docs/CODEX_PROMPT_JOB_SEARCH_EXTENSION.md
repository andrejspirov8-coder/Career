# Codex Prompt: Job-Search Raycast Extension

**Project**: `raycast-job-search-hub`
**Language**: TypeScript (Raycast native)
**Purpose**: Unified command palette for job-search toolkit
**User**: Andrej (macOS M3 Max, Vilnius-based developer)

---

## Context & Requirements

### Existing System
You have a **job-search toolkit** (Python-based) in `/Users/andrejspirov/Career/job-search/`:

```
job-search/
├── tools/
│   ├── new_job.py                # Create .job.txt files interactively
│   ├── batch_match_and_pack.py   # Match all jobs to CV variants
│   ├── review_packs.py           # Dashboard for matching results
│   └── variant_performance.py    # Analytics: which variant converts best?
├── inbox/jobs/                   # Job posting files (*.job.txt)
├── packs/                        # Generated application packs
├── cv/                           # CV variants + build scripts
└── pipeline/applications.csv     # Application tracking log
```

### User Workflow (Current State)
```
1. cd ~/Career/job-search/tools
2. python new_job.py              # Create job file
3. python batch_match_and_pack.py # Match & generate packs
4. python review_packs.py         # View results
5. python variant_performance.py  # Analyze (after 10+ apps)
6. Manually edit applications.csv # Log outcomes
```

### Desired Workflow (With Raycast Extension)
```
Cmd+K "Job: New"          → Interactive form → .job.txt created
Cmd+K "Job: Match All"    → Background process → Opens review dashboard
Cmd+K "Job: Review"       → Tabular dashboard in Raycast
Cmd+K "Job: Analytics"    → Performance metrics in Raycast
Cmd+K "Job: Log App"      → Form → Auto-appends to CSV
```

---

## Specification

### 1. Command: `job-new`

**Title**: "Job: New"
**Description**: Create a new job posting file interactively

**Form Fields**:
1. `title` (text) — Job title (required)
2. `company` (text) — Company name (required)
3. `url` (text) — Job posting URL (optional)
4. `source` (dropdown) — Job source
   - Options: linkedin, cvbank, cv_lt, startup_lt, recruiter, company_site, indeed, work_in_lt
   - Default: linkedin
5. `job_id` (text) — Custom job ID (optional; auto-generated if blank)

**On Submit**:
1. Validate: `title` and `company` not empty
2. If `job_id` blank: auto-generate from YYYYMMDD + company slug + title slug
   - Example: `20260519_michael_kors_assistant`
3. Create file: `~/Career/job-search/inbox/jobs/{job_id}.job.txt`
4. File template:
   ```
   TITLE: {title}
   COMPANY: {company}
   URL: {url}
   SOURCE: {source}
   JOB_ID: {job_id}
   ---
   [Paste full job description here]
   ```
5. Show success popup: ✅ Created: `{filename}`
6. Offer: "Open in editor?" → Opens file in default editor (e.g., VS Code)

**Error Handling**:
- If file exists: Show confirm dialog "File exists. Overwrite? (Y/n)"
- If directory missing: Create `~/Career/job-search/inbox/jobs/` automatically

---

### 2. Command: `job-match`

**Title**: "Job: Match All"
**Description**: Batch match all jobs in inbox to CV variants

**Execution**:
1. Call Python script: `/Users/andrejspirov/Career/job-search/tools/batch_match_and_pack.py`
2. Show progress:
   - Animated status: "Processing job 1 of N..."
   - Real-time updates (stream stdout)
3. On completion:
   - Show summary: ✅ "Processed 5 jobs. 3 clear winners, 2 ties."
   - Offer: "Review packs?" → Runs `job-review` command

**Error Handling**:
- If no jobs found: "❌ No .job.txt files in inbox/jobs/"
- If Python error: Show error message with suggestion to check `MATCH.json` in pack

---

### 3. Command: `job-review`

**Title**: "Job: Review"
**Description**: Dashboard of all generated application packs

**Display Format** (Raycast List/Table):

```
📦 APPLICATION PACKS

[Filter: All Variants ▼]  [Sort: By Score (↓) ▼]

20260511-michael-kors-asm
├─ Michael Kors | Assistant Store Manager
├─ Variant: luxury-retail | ✓ Clear (18.5)
├─ Runner-up: ops-management (14.2)
└─ [View Gaps] [Open PDF] [Log Application]

20260511-zara-home-director
├─ Zara Home | Director
├─ Variant: luxury-retail | ✓ Clear (17.2)
├─ Runner-up: ops-management (12.8)
└─ [View Gaps] [Open PDF] [Log Application]

20260511-mango-director
├─ MANGO | Store Director
├─ Variant: ops-management | ⚠ Tie (14.5 vs 14.1)
├─ Runner-up: luxury-retail (14.1)
└─ [View Gaps] [Open PDF] [Log Application]
```

**Filters** (Dropdown):
- All Variants
- luxury-retail
- luxury-retail-lt
- operations-management
- it-business

**Sort Options** (Dropdown):
- By Score (descending)
- By Date (newest first)
- By Company (alphabetical)
- By Confidence (clear_winner first)

**Actions** (each pack):
- `[View Gaps]` → Opens KEYWORD_GAPS.md in editor
- `[Open PDF]` → Opens PDF in Finder/Preview
- `[Log Application]` → Launches `job-log` command with pre-filled pack metadata

**Summary Footer**:
```
📊 Total: 3 packs
   ✓ Clear: 2 | ⚠ Tie: 1
   Variant distribution: luxury-retail: 2, ops-management: 1
```

---

### 4. Command: `job-log`

**Title**: "Job: Log Application"
**Description**: Log an application to `applications.csv`

**Trigger**:
- Standalone: Cmd+K "Job: Log App"
- From review: Click `[Log Application]` on a pack

**Pre-fill** (if triggered from pack):
- `company` (from pack metadata)
- `title` (from pack metadata)
- `variant_slug` (from pack metadata)
- `source` (from pack metadata)

**Form Fields**:
1. `date_iso` (date) — Application date (default: today)
2. `company` (text) — Company name (pre-filled if from pack)
3. `title` (text) — Role title (pre-filled if from pack)
4. `variant_slug` (dropdown) — CV variant used (pre-filled if from pack)
   - Options: luxury-retail, luxury-retail-lt, operations-management, it-business
5. `source` (dropdown) — Job source (pre-filled if from pack)
   - Options: linkedin, cvbank, cv_lt, startup_lt, recruiter, company_site, indeed, work_in_lt
6. `outcome` (dropdown) — Application status
   - Options: applied, rejected, screening, interview, offer, withdrawn
   - Default: applied
7. `notes` (text) — Optional notes (e.g., "Applied via email", "Interviewer: Jane Doe")

**On Submit**:
1. Validate: all required fields filled
2. Append to `~/Career/job-search/pipeline/applications.csv`:
   ```csv
   2026-05-19,Michael Kors,ASM,luxury-retail,cvbank,applied,"Applied via email"
   ```
3. Show success: ✅ "Logged: Michael Kors | ASM | applied"
4. If `outcome` is "interview":
   - Show bonus: "🎉 Interview! Extract keywords from pack? (Y/n)"
   - If yes: Run keyword extraction (see Layer 5.3 in OPTIMISATION_ROADMAP.md)

**Error Handling**:
- If CSV missing: Create with header:
  ```csv
  date_iso,company,title,variant_slug,source,outcome,notes
  ```
- If date parsing fails: Show error; suggest YYYY-MM-DD format

---

### 5. Command: `job-analytics`

**Title**: "Job: Analytics"
**Description**: Real-time performance metrics

**Display Sections**:

#### Section A: Pipeline Funnel
```
📊 APPLICATION PIPELINE

Applied:      12   ████████████░░░░░░░░ 100%
Screening:     3   ████░░░░░░░░░░░░░░░░  25%
Interview:     1   ██░░░░░░░░░░░░░░░░░░  33% (of screening)
Offer:         0   ░░░░░░░░░░░░░░░░░░░░   0%

Interview rate: 1/12 (8.3%)
Rejected:      8 (67%)
Withdrawn:     0 (0%)
```

#### Section B: Variant Performance
```
Variant              Applied  Interview  Rate    Trend
──────────────────────────────────────────────────────
luxury-retail            8        2     25.0%    ↑
operations-management    3        1     33.3%    ↑
it-business              1        0      0.0%    ↔
```
(Trend: ↑ improving, ↓ declining, ↔ stable, ? insufficient data)

#### Section C: Source (Job Board) Performance
```
Source          Total  Interviews  Rate
────────────────────────────────────
linkedin           6        1    16.7%
cvbank             4        2    50.0%
recruiter          2        1    50.0%
startup_lt         1        0     0.0%
```

**Refresh** Button:
- Re-reads `applications.csv`
- Re-calculates metrics
- Shows "Last updated: 2 min ago"

**Export** (Optional):
- Button: "Export as CSV"
- Saves summary tables to `~/Desktop/job-search-analytics.csv`

---

### 6. Command: `job-deadlines`

**Title**: "Job: Deadlines"
**Description**: Show upcoming application deadlines

**Requirements** (Future Enhancement):
- Add `deadline_date` column to `applications.csv`
  ```csv
  date_iso,company,title,variant_slug,source,outcome,deadline_date,notes
  2026-05-19,Michael Kors,ASM,luxury-retail,cvbank,applied,2026-05-26,"Deadline 5 days"
  ```

**Display**:
```
⏳ UPCOMING DEADLINES

Due in 3 days (May 22):
  • Michael Kors | ASM
    Variant: luxury-retail
    Applied: 2026-05-19
    [Add Reminder]

Due in 7 days (May 26):
  • Zara Home | Director
    Variant: luxury-retail
    Applied: 2026-05-18
    [Add Reminder]

No upcoming deadlines beyond 7 days.
```

**Action**: `[Add Reminder]` → Opens Apple Calendar, pre-fills event

---

### 7. Menu Bar Icon (Optional)

**Display**:
```
💼 3 Pending
    Applied: 12
    Interview: 1
    Offer: 0
```

**Click → Menu**:
```
📊 Quick Stats
  Applied: 12 | Interview: 1 (8.3%)

🎯 Next Steps
  1. Review Michael Kors pack (score: 18.5)
  2. Follow up on Zara Home (due in 3 days)

⚡ Quick Actions
  New Job
  Match All
  Review
  Log Application
```

---

## Implementation Guidelines

### Directory Structure
```
raycast-job-search-hub/
├── src/
│   ├── commands/
│   │   ├── job-new.ts
│   │   ├── job-match.ts
│   │   ├── job-review.ts
│   │   ├── job-log.ts
│   │   ├── job-analytics.ts
│   │   └── job-deadlines.ts
│   ├── utils/
│   │   ├── python-runner.ts         # Invoke Python scripts
│   │   ├── csv-parser.ts            # Read/write CSV
│   │   ├── metadata-extractor.ts    # Extract pack metadata
│   │   └── constants.ts             # Paths, defaults
│   └── types.ts                     # TypeScript interfaces
├── package.json
├── tsconfig.json
├── raycast-env.d.ts
└── README.md
```

### Key Implementation Details

#### 1. Python Script Integration
```typescript
// utils/python-runner.ts
import { execSync } from 'child_process';

export function runBatchMatch(): Promise<string> {
  const result = execSync(
    'python3 /Users/andrejspirov/Career/job-search/tools/batch_match_and_pack.py',
    { encoding: 'utf8' }
  );
  return result;
}
```

#### 2. CSV Parsing
```typescript
// utils/csv-parser.ts
import { readFileSync, appendFileSync } from 'fs';
import { parse, stringify } from 'csv/sync';

export function readApplications() {
  const content = readFileSync(
    '/Users/andrejspirov/Career/job-search/pipeline/applications.csv',
    'utf8'
  );
  return parse(content, { columns: true });
}

export function logApplication(row: any) {
  appendFileSync(
    '/Users/andrejspirov/Career/job-search/pipeline/applications.csv',
    stringify([row])
  );
}
```

#### 3. Pack Metadata Extraction
```typescript
// utils/metadata-extractor.ts
import { readFileSync } from 'fs';

export function extractPackMetadata(packDir: string) {
  const matchJson = readFileSync(`${packDir}/MATCH.json`, 'utf8');
  const match = JSON.parse(matchJson);
  return {
    title: match.job.title,
    company: match.job.company,
    variant: match.recommendation.variant_slug,
    score: match.recommendation.primary_score,
    confidence: match.recommendation.confidence,
  };
}
```

#### 4. Form Pre-filling
```typescript
// commands/job-log.ts
const props = useRouterSearch<{ packDir?: string }>();

const [initialData] = useState(() => {
  if (props.packDir) {
    const metadata = extractPackMetadata(props.packDir);
    return {
      company: metadata.company,
      title: metadata.title,
      variant_slug: metadata.variant,
      source: 'linkedin', // Default; could extract from job_input.txt
    };
  }
  return {};
});
```

### Dependencies
```json
{
  "dependencies": {
    "@raycast/api": "latest",
    "csv": "^6.0.0",
    "date-fns": "^2.30.0"
  }
}
```

---

## Prompts for Codex

### Prompt 1: Core Structure
```
Build a Raycast extension for job-search toolkit management.

Context:
- User has Python scripts in ~/Career/job-search/tools/
- Scripts: new_job.py, batch_match_and_pack.py, review_packs.py, variant_performance.py
- CSV tracking file: ~/Career/job-search/pipeline/applications.csv
- Generated packs in: ~/Career/job-search/packs/

Commands to create:
1. job-new: Interactive form to create .job.txt files
2. job-match: Run batch_match_and_pack.py with progress
3. job-review: Tabular dashboard of packs with filtering/sorting
4. job-log: Form to append applications to CSV
5. job-analytics: Show variant/source performance from CSV

Requirements:
- All paths hardcoded to ~/Career/job-search/
- Python scripts invoked via execSync
- CSV parsing and writing (csv npm package)
- Forms with validation
- Result tables with filters
- Error handling and user feedback

Deliverables:
- Complete TypeScript source in src/ directory
- package.json with dependencies
- Brief setup instructions
```

### Prompt 2: Job-New Command
```
Create Raycast command: job-new.ts

Form fields:
- title (text, required): Job title
- company (text, required): Company name
- url (text, optional): Job posting URL
- source (dropdown): [linkedin, cvbank, cv_lt, startup_lt, recruiter, company_site, indeed, work_in_lt]
- job_id (text, optional): Custom ID (auto-generated if blank)

On submit:
1. Generate job_id from YYYYMMDD + slugs if blank
2. Create ~/Career/job-search/inbox/jobs/{job_id}.job.txt
3. Fill template with submitted data
4. Show success popup
5. Offer to open in editor

File template:
TITLE: {title}
COMPANY: {company}
URL: {url}
SOURCE: {source}
JOB_ID: {job_id}
---
[Paste full job description here]

Error handling:
- Validate title/company not empty
- If file exists, confirm overwrite
- Create inbox/jobs/ directory if missing
```

### Prompt 3: Job-Review Command
```
Create Raycast command: job-review.ts

Display all packs as list with details:
- Pack ID (directory name)
- Job title + company
- Recommended variant + score + confidence
- Runner-up variant + score

Filters:
- By variant: All / luxury-retail / ops-management / it-business / luxury-retail-lt
- Default: All

Sort options:
- By score (desc)
- By date (desc)
- By company (asc)

For each pack, show actions:
- View Gaps (open KEYWORD_GAPS.md)
- Open PDF (open visual PDF from output/)
- Log Application (jump to job-log with pre-filled data)

Footer summary:
- Total packs
- Count by confidence level
- Variant distribution

Data source:
- Scan ~/Career/job-search/packs/ for YYYYMMDD-* directories
- Read MATCH.json from each pack
```

### Prompt 4: Job-Analytics Command
```
Create Raycast command: job-analytics.ts

Parse ~/Career/job-search/pipeline/applications.csv and display:

Section A: Pipeline funnel
- Applied, Screening, Interview, Offer counts
- Percentage bars
- Interview rate
- Rejected/Withdrawn counts

Section B: Variant performance table
- Variant | Applied | Interview | Rate | Trend
- Trend indicators: ↑↓↔?

Section C: Source (job board) performance
- Source | Total | Interviews | Rate

Footer:
- Last updated: [timestamp]
- Data refresh button
- Export to CSV button

CSV columns expected:
date_iso, company, title, variant_slug, source, outcome, notes
(Outcomes: applied, rejected, screening, interview, offer, withdrawn)
```

### Prompt 5: Job-Log Command
```
Create Raycast command: job-log.ts

Form to log application outcome to CSV.

Input (form):
- date_iso (date): Default today, format YYYY-MM-DD
- company (text, required)
- title (text, required)
- variant_slug (dropdown): [luxury-retail, luxury-retail-lt, operations-management, it-business]
- source (dropdown): [linkedin, cvbank, cv_lt, startup_lt, recruiter, company_site, indeed, work_in_lt]
- outcome (dropdown): [applied, rejected, screening, interview, offer, withdrawn]
- notes (text, optional)

Pre-fill from context:
- If triggered from job-review pack, pre-fill: company, title, variant_slug, source

On submit:
1. Validate required fields
2. Append row to ~/Career/job-search/pipeline/applications.csv
3. Ensure CSV header exists; create if missing
4. Show success: "✅ Logged: {company} | {title} | {outcome}"
5. If outcome is "interview", offer: "Extract keywords from pack?"

CSV header (create if missing):
date_iso,company,title,variant_slug,source,outcome,notes
```

---

## Acceptance Criteria

- [ ] All 6 commands functional (new, match, review, log, analytics, deadlines)
- [ ] Forms validate and handle errors gracefully
- [ ] Python scripts invoked successfully with output parsing
- [ ] CSV read/write operations work correctly
- [ ] Tables display with proper formatting
- [ ] Filters and sorting work as expected
- [ ] File paths are correct (tests with real ~/Career/job-search/)
- [ ] No external dependencies beyond `csv` and `date-fns`
- [ ] Code is type-safe (no `any` types except where necessary)
- [ ] README provides setup + usage instructions

---

## Success Metrics

After extension is deployed:

1. **Workflow speed**: Job entry 5 min → 1 min (80% faster)
2. **Compliance**: CSV logging goes from 30% to 90%+ (manual → automatic)
3. **Decision-making**: Variant selection <30 sec (vs. manual review of 5+ packs)
4. **Data quality**: No missed deadlines; all applications tracked

---

## Notes for Codex

1. **Hardcoded paths**: All paths reference `/Users/andrejspirov/Career/job-search/`. Consider adding environment variable for flexibility (optional).

2. **Python integration**: Use `execSync` for blocking operations; consider `spawn` for long-running scripts (batch matching).

3. **CSV parsing**: Use `csv` npm package; handle edge cases (commas in company names, UTF-8 encoding).

4. **Real-time updates**: `job-review` should scan packs on every render; `job-analytics` should re-read CSV on every render.

5. **Error messages**: Show actionable errors (e.g., "No jobs in inbox/jobs/ — create one with 'Job: New'").

6. **Future-proofing**: Add `deadline_date` column support in `job-log` (for calendar integration later).

7. **Type safety**: Use proper TypeScript interfaces for packs, applications, analytics data.

---

## Next Steps

1. **Codex builds the extension** (TypeScript)
2. **Test in Raycast dev environment**
3. **Refine based on actual usage**
4. **Deploy to Raycast Store (optional)**
5. **Integrate with Arc browser** (separate project)

---

End of prompt. Use the 5 sub-prompts above (Prompt 1–5) to guide Codex through implementation.
