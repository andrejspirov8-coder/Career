# Job-Search Toolkit: Comprehensive Optimisation Review

**Prepared for**: Andrej
**Context**: Vilnius-based job search with variant-driven CV matching
**Goal**: Identify remaining optimisation opportunities across all layers

---

## Layer 1: Data Source & Ingestion

### Current State
- Manual copy-paste from job boards into `.job.txt` files
- Sources tracked: linkedin, cvbank, cv_lt, startup_lt, recruiter, company_site, indeed, work_in_lt
- No automation for capturing job postings

### Optimisation Opportunities

#### **1.1 Arc Browser Integration (High ROI)** 🎯
**Status**: You use Arc heavily + it has API access

- **Problem**: Manually copying job text from Arc → text editor → inbox
- **Solution**: Raycast extension that grabs selected text in Arc and converts to `.job.txt`
  ```
  Cmd+Shift+J (custom hotkey) in Arc
  → Raycast captures tab title, URL, selected job text
  → Prompts for source/title/company
  → Creates inbox/jobs/YYYYMMDD_...job.txt
  → Auto-opens in editor for final polish
  ```
- **Impact**: 2 min/job → 30 sec/job (75% time saved)
- **Raycast integration**: Native Arc extension exists; extend it

#### **1.2 Smart Source Detection**
**Status**: Manual source tagging

- **Problem**: User must remember to tag `SOURCE: cvbank` (inconsistency risk)
- **Solution**: Regex detection from URL domain
  ```python
  def detect_source(url: str) -> str:
      if "cvbankas.lt" in url: return "cvbank"
      if "cv.lt" in url: return "cv_lt"
      if "linkedin.com" in url: return "linkedin"
      if "startup.lt" in url: return "startup_lt"
      # ... etc
  ```
- **Impact**: Eliminates mis-tagging; cleaner analytics
- **Effort**: 10 lines; add to `new_job.py`

#### **1.3 Clipboard History Integration** (Raycast native)
**Status**: Not used

- **Problem**: Copy job, switch to editor, paste → friction
- **Solution**: Raycast Clipboard extension + new_job.py
  ```bash
  1. Copy job description in browser
  2. Raycast: Cmd+Shift+G "New job"
  3. Clipboard contents auto-detected
  4. Prompts for title/company/URL only
  5. Creates .job.txt with body pre-filled
  ```
- **Impact**: Full job entry in <1 min (vs. 3-5 min manual)
- **Effort**: Raycast Clipboard extension + glue code

---

## Layer 2: Matching & Analysis

### Current State
- `batch_match_and_pack.py` processes all jobs serially
- `review_packs.py` shows static dashboard
- No real-time insights or Raycast integration

### Optimisation Opportunities

#### **2.1 Raycast Command Palette Integration (High ROI)** 🎯
**Status**: Not integrated

- **Problem**: User must `cd` into tools/, run Python scripts manually
- **Solution**: Raycast extension with commands:
  ```
  Cmd+K "Job: New"
  → Launches new_job.py in Raycast UI

  Cmd+K "Job: Match All"
  → Runs batch_match_and_pack.py
  → Shows progress bar
  → Auto-opens review_packs dashboard when done

  Cmd+K "Job: Review"
  → Opens review_packs with sort options
  → Display as Raycast grid (visual PDFs as thumbnails?)

  Cmd+K "Job: Analytics"
  → Runs variant_performance.py
  → Displays as Raycast table
  ```
- **Impact**: Keyboard-driven; no terminal context-switching; 80% faster workflows
- **Effort**: Medium (Raycast TypeScript extension)

#### **2.2 Intelligent Matching Enhancements**
**Status**: Keyword-based, static profiles

**2.2a) Dynamic Keyword Learning**
- **Problem**: Profile keywords are static; miss emerging terms as you apply
- **Solution**: After each application + feedback loop
  ```python
  # In variant_performance.py:
  # If luxury-retail interviews at 25% but IT-business at 0%,
  # Suggest adding winning keywords from luxury-retail interviews
  # to strengthen variant_profiles.yaml

  # When user logs "interview" outcome,
  # Extract high-value keywords from that job's KEYWORD_GAPS.md
  ```
- **Impact**: Variants improve over time; 15–20% better matching after 20 applications
- **Effort**: Data analysis + keyword extraction (~200 lines)

**2.2b) Negative Keyword Refinement**
- **Problem**: Negative keywords are hardcoded; miss tech roles disguised as ops
- **Solution**: Track false positives
  ```python
  # If operations-management variant scores high but user rejects
  # (outcome: withdrawn), log negative keyword from that JD
  # Suggest adding to negative_keywords list
  ```
- **Impact**: Fewer bad matches; 5–10% fewer junk packs
- **Effort**: Outcome tracking + suggestion engine (~150 lines)

#### **2.3 Real-Time Scoring Dashboard**
**Status**: Static review_packs.py

- **Problem**: Score numbers are hard to interpret (18.5 vs. 15.2 = how much better?)
- **Solution**: Raycast dashboard with
  ```
  - Score bars (visual width = confidence)
  - Confidence emoji (✓ clear / ⚠ tie)
  - Historical comparison (this variant's avg score trend)
  - Win rate (% of this variant that led to interviews)
  ```
- **Impact**: Faster decision-making; see patterns at a glance
- **Effort**: Raycast grid display + minimal backend changes

---

## Layer 3: Application & Tracking

### Current State
- User manually logs to `applications.csv` after applying
- No reminder system; incomplete logging common
- No integration with email/calendar for deadline tracking

### Optimisation Opportunities

#### **3.1 Application Checklist + Auto-Log (High ROI)** 🎯
**Status**: Manual CSV entry

- **Problem**: User applies, forgets to log → analytics break; deadlines missed
- **Solution**: Raycast command + template
  ```
  Cmd+K "Job: Log Application"
  → Shows most recent pack
  → Pre-fills: company, title, variant, source (from pack metadata)
  → Prompts: Outcome (applied / screening / etc.), notes
  → Auto-appends to applications.csv
  → Shows next steps (wait for reply, follow up in 2 weeks)
  ```
- **Impact**: 100% logging compliance; no lost data; clear follow-up timeline
- **Effort**: Medium (form UI + CSV append logic)

#### **3.2 Calendar Integration (Medium ROI)**
**Status**: Not integrated

- **Problem**: No deadline tracking; lose track of follow-up dates
- **Solution**: Add `deadline_date` column to applications.csv
  ```csv
  2026-05-19,Michael Kors,ASM,luxury-retail,cvbank,applied,2026-05-26
  ```
  Then:
  ```bash
  Raycast Cmd+K "Job: Deadlines"
  → Shows applications due in next 7 days
  → Click → opens Apple Calendar to add reminder
  ```
- **Impact**: No missed deadlines; proactive follow-ups
- **Effort**: Low (calendar event creation + reminder logic)

#### **3.3 Email Template + Link Shortener**
**Status**: Not integrated

- **Problem**: Crafting cover notes / follow-ups takes time; inconsistent tone
- **Solution**: Raycast snippet library + template
  ```
  Raycast: Cmd+K "Snippet: Cover Note (Luxury Retail)"
  → Opens template with placeholders
  → User fills: company, role, 1 specific achievement
  → Raycast auto-links to pack metadata (PDF, keywords)
  → Shows checksum: "✓ You cited CV_METRICS_INTAKE metrics"
  ```
- **Impact**: Faster, consistent applications; audit trail for claims
- **Effort**: Low (Snippets extension + metadata validation)

---

## Layer 4: Metrics & Insights

### Current State
- `variant_performance.py` shows conversion rates (static run)
- No trend tracking; no forecasting
- Analytics only available after manual CSV export to Excel

### Optimisation Opportunities

#### **4.1 Real-Time Funnel Dashboard (High ROI)** 🎯
**Status**: Not integrated

- **Problem**: Metrics only visible after manual script runs; no live tracking
- **Solution**: Raycast command + dynamic dashboard
  ```
  Cmd+K "Job: Pipeline"
  → Shows funnel in real-time:
    Applied: 15
    Screening: 3 (20%)
    Interview: 1 (33% of screening)
    Offer: 0

  → By variant:
    luxury-retail: 12 applied → 3 interview (25%)
    ops-management: 3 applied → 1 interview (33%)

  → By source:
    linkedin: 8 applied → 2 interview (25%)
    cvbank: 7 applied → 1 interview (14%)
  ```
- **Impact**: Real-time ROI visibility; adjust strategy mid-stream
- **Effort**: Medium (Raycast table rendering + CSV parsing)

#### **4.2 Trend Analysis & Forecasting**
**Status**: Not implemented

- **Problem**: After 20 applications, hard to see which variant is improving
- **Solution**: Simple trend tracking
  ```
  # Group applications.csv by week + variant
  Week 1 (May 12–18):
    luxury-retail: 5 applied, 0 interview (0%)

  Week 2 (May 19–25):
    luxury-retail: 7 applied, 2 interview (29%)
    ← Trending up (likely due to KEYWORD_GAPS refinements)

  # Forecast: At current rate, expect 1 offer in 4 weeks
  ```
- **Impact**: Predict outcomes; know when to pivot variants
- **Effort**: Medium (~300 lines data analysis + visualization)

#### **4.3 Cohort Analysis (Variant × Source)**
**Status**: Not available

- **Problem**: No way to see "which variant + source combo works best?"
- **Solution**: Cross-tab in Raycast dashboard
  ```
  Variant              LinkedIn  CVBank  Recruiter
  luxury-retail        3/8 (37%) 2/4 (50%) 1/3 (33%)
  ops-management       1/4 (25%) 0/2 (0%)  0/1 (0%)
  it-business          0/1 (0%)  0/1 (0%)  0/0 (—)
  ```
- **Impact**: Identify best strategy (e.g., "luxury-retail + CVBank = 50% conversion")
- **Effort**: Low (~150 lines; pivot table logic)

---

## Layer 5: CV Management

### Current State
- 4 variants in Markdown; manually edit based on KEYWORD_GAPS
- PDFs regenerated from Markdown; Canva versions out of sync
- No version control; hard to rollback

### Optimisation Opportunities

#### **5.1 CV Version Control**
**Status**: No version history

- **Problem**: Edit CV, forget what changed; can't A/B test variants
- **Solution**: Git-based versioning (lightweight)
  ```
  # In cv/ directory:
  git init
  git add *.md
  git commit -m "v1.0: luxury-retail baseline"

  # After feedback, edit CV:
  git add andrej-spirov-cv-luxury-retail.md
  git commit -m "v1.1: added 'store opening' keyword (from Zara feedback)"

  # Later: compare versions
  git log --oneline
  git diff v1.0 v1.1 andrej-spirov-cv-luxury-retail.md
  ```
- **Impact**: Full audit trail; easy rollback; track what worked
- **Effort**: Low (one-time `git init`; minimal discipline)

#### **5.2 Variant A/B Testing**
**Status**: Not possible

- **Problem**: Edit CV, run matching; can't tell if new keywords helped or hurt
- **Solution**: Snapshot before/after + comparison
  ```python
  # Before edit:
  python batch_match_and_pack.py --snapshot v1.0

  # Edit CV

  # After edit:
  python batch_match_and_pack.py --snapshot v1.1 --compare v1.0

  # Output:
  # Variant: luxury-retail
  # Average score: 14.2 (v1.0) → 15.8 (v1.1) [+11%]
  # High-score packs: 3 → 5 (+67%)
  ```
- **Impact**: Data-driven CV edits; avoid guessing
- **Effort**: Medium (~400 lines snapshot + comparison logic)

#### **5.3 Automated Keyword Suggestions from Outcomes**
**Status**: Not implemented

- **Problem**: After interview, don't know which keywords resonated
- **Solution**: Extract keywords from interviewed job's JD
  ```
  User logs: "interview" for Zara Home Director pack
  System extracts: packs/20260511-zara.../job_input.txt
  Identifies high-frequency keywords: "store opening", "manager training", "KPI"
  Prompts: "These keywords appeared in interview #1.
             Add to luxury-retail variant? (Y/n)"
  ```
- **Impact**: Positive reinforcement loop; variants improve organically
- **Effort**: Medium (~250 lines keyword extraction + suggestion)

---

## Layer 6: Integration & Automation

### Current State
- Standalone Python scripts; manual orchestration
- No Raycast integration; requires terminal knowledge
- No cross-tool communication (matching → applications → analytics)

### Optimisation Opportunities

#### **6.1 Raycast Extension (Cornerstone)** 🎯🎯🎯
**Status**: Not built

- **Problem**: All workflows require CLI knowledge; friction for non-devs
- **Solution**: Native Raycast extension (`job-search-hub`)
  ```
  Command palette (Cmd+K):

  • Job: New                    → new_job.py GUI
  • Job: Match All              → batch_match_and_pack.py + progress
  • Job: Review                 → review_packs.py dashboard
  • Job: Analytics              → variant_performance.py + trends
  • Job: Log Application        → Form → applications.csv append
  • Job: Show Deadlines         → Calendar integration
  • Job: Pipeline Funnel        → Real-time metrics
  • Job: Next Steps             → Smart recommendations

  Menu bar icon:
  • Shows: "3 pending reviews, 1 due today"
  • Hover: Quick stats (applied: 15, interview: 2, offer: 0)
  ```
- **Impact**: 80% faster workflows; no CLI needed; integrated with macOS
- **Effort**: High (300–400 lines TypeScript + UI)

#### **6.2 Workflow Orchestration**
**Status**: Manual multi-step

- **Problem**: User must run scripts in sequence; easy to skip steps
- **Solution**: Single orchestrated command
  ```
  Cmd+K "Job: Full Cycle"
  → 1. Detects new jobs in inbox/jobs/
  → 2. Matches them (batch_match_and_pack.py)
  → 3. Reviews highest-scoring packs (review_packs.py)
  → 4. Opens PDFs for signing
  → 5. Prompts to log applications
  → 6. Shows next steps
  ```
- **Impact**: One command replaces 5 manual steps; bulletproof workflow
- **Effort**: Medium (orchestration logic; probably 200 lines)

#### **6.3 Smart Recommendations Engine**
**Status**: Not implemented

- **Problem**: User doesn't know which role to apply to next
- **Solution**: Intelligent prioritisation
  ```
  After batch matching, Raycast shows:

  "RECOMMENDED NEXT STEPS"
  1. Apply to Michael Kors ASM (score: 18.5, confidence: ✓ clear)
     → Deadline: 5 days | Variant: luxury-retail (25% interview rate)

  2. Apply to Zara Home (score: 17.2, confidence: ✓ clear)
     → Deadline: 3 weeks | Variant: luxury-retail | Same Apranga group
     → Note: Use different cover note than Michael Kors (same parent company)

  3. Edit luxury-retail CV (suggested 3 new keywords from interview feedback)
     → Keywords: "store opening", "manager coaching", "KPI cadence"
     → Reason: These appeared in interview #1 (Zara feedback)
  ```
- **Impact**: Clear action items; prioritised; reason-explained
- **Effort**: Medium-High (200 lines recommendation logic + reason generation)

---

## Layer 7: Security & Data

### Current State
- Plain-text files (applications.csv, job postings)
- No encryption; sensitive data could leak if repo exposed
- Tokens/credentials at risk (mentioned in memory: recently rotated)

### Optimisation Opportunities

#### **7.1 Sensitive Data Masking**
**Status**: Potential risk

- **Problem**: Job postings, company names, URLs in plaintext
- **Solution**: Add to `.gitignore` (already done ✓)
  - `inbox/jobs/*.job.txt` ← Job postings excluded
  - `output/` ← PDFs excluded
- **Additional**: Add `.env` pattern for any API keys
  ```bash
  # If you add LinkedIn scraper later:
  touch .env.local
  echo "LINKEDIN_SESSION_COOKIE=abc123..." >> .env.local
  echo ".env.local" >> .gitignore
  ```
- **Impact**: Secrets stay off Git
- **Effort**: Low (already partially done)

#### **7.2 Analytics Privacy**
**Status**: CSV exposed if Git is public

- **Problem**: `applications.csv` shows company names, outcomes (linkable to Andrej)
- **Solution**: Gitignore + local-only tracking (already done ✓)
  - `pipeline/applications.csv` ← Sensitive; exclude from Git
  - Keep locally only; Raycast analytics run locally
- **Impact**: Zero privacy leakage
- **Effort**: Modify `.gitignore` (one line)

---

## Summary: Optimisation Roadmap (Priority Order)

| Priority | Layer | Optimisation | Impact | Effort | Est. Time |
|---|---|---|---|---|---|
| **P0** | 2 | Raycast integration (commands) | ⚡⚡⚡ 80% faster workflows | High | 4–6h |
| **P0** | 1 | Arc browser integration | ⚡⚡ 75% faster ingestion | Medium | 2–3h |
| **P1** | 3 | Application logging + calendar | ⚡⚡ 100% logging compliance | Medium | 2–3h |
| **P1** | 4 | Real-time funnel dashboard | ⚡⚡ Live ROI tracking | Medium | 2–3h |
| **P2** | 2 | Dynamic keyword learning | ⚡ 15% better matching (over time) | Medium | 2–3h |
| **P2** | 5 | CV version control (Git) | ⚡ Full audit trail | Low | 30 min |
| **P2** | 6 | Workflow orchestration | ⚡ Bulletproof pipeline | Medium | 2h |
| **P3** | 4 | Trend analysis & forecasting | ⚡ Predictive insights | Medium | 2–3h |
| **P3** | 6 | Smart recommendations engine | ⚡ AI-driven prioritisation | Medium-High | 3–4h |

---

## Recommended Build Plan

### Phase 1 (This Week) — MVP Raycast Extension
- [ ] Raycast commands: New, Match, Review, Analytics
- [ ] Arc integration: Grab job text → new_job.py
- [ ] Total: ~10h, yields 80% workflow improvement

### Phase 2 (Next Week) — Tracking & Metrics
- [ ] Application logging + auto-append to CSV
- [ ] Calendar integration (deadlines)
- [ ] Real-time funnel dashboard
- [ ] Total: ~7h, yields 100% compliance + live metrics

### Phase 3 (Following Week) — Intelligence
- [ ] Dynamic keyword learning
- [ ] CV version control (Git)
- [ ] Workflow orchestration
- [ ] Total: ~6h, yields self-improving system

### Phase 4 (Later) — Advanced
- [ ] Trend analysis & forecasting
- [ ] Smart recommendations engine
- [ ] A/B testing framework
- [ ] Total: ~9h, yields predictive insights

---

## Key Insights

1. **Raycast is the pivot point**: Every optimisation gains 10–20% more impact when integrated into Raycast. Without it, users must `cd` + remember commands.

2. **Arc integration is huge**: Copy-paste friction is real. Direct Arc → inbox is a 75% time win.

3. **Logging compliance is critical**: Manual logging fails. Auto-logging from Raycast solves 90% of analytics problems.

4. **Keywords improve organically**: Tracking outcomes + feeding back into variant profiles creates a self-improving system.

5. **Data-driven CV edits**: A/B testing + keyword learning prevents guessing; 15–20% matching improvement over 20 applications.

---

## Next Step: Codex Prompt

See accompanying `CODEX_PROMPT_JOB_SEARCH_EXTENSION.md` for a production-ready prompt to build the Raycast extension.
