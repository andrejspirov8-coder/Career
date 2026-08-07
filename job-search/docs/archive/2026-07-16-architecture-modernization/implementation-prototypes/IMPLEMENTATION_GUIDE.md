# Implementation Guide: Career Workspace Improvements

**Generated:** 20 May 2026 | **Status:** Ready to implement
**Source:** Desktop Commander Comprehensive Review & Recommendations

---

## 📋 What You're Implementing

Three interconnected improvements to your recruiter automation system:

1. **Config Changes** (10 mins) — Add staffing agencies + fix tier gates
2. **Persona Detection** (1.5 hours) — Classify recruiters by authority level
3. **MCP Server** (2 hours) — Expose scorer as composable tool
4. **Analytics Template** (15 mins) — Set up quarterly reporting

**Total effort:** ~4 hours | **Expected payoff:** +5–10 percentage points response rate

---

## ✅ STEP 1: Config Changes (10 minutes)

**Status:** ✅ COMPLETED in `/job-search/linkedin/config.yaml`

### What Changed

1. **Added staffing agency keywords** (lines 103–112)
   ```yaml
   - "executive search"
   - "retained search"
   - "michael page"
   - "korn ferry"
   - "experis"
   - "in-house recruiter"
   ```

   **Impact:** Michael Page recruiters now score +5 sector points (vs 0 before)

2. **Fixed Tier 2 confidence gate** (line 88)
   ```yaml
   require_clear_winner: true  # was: false
   ```

   **Impact:** Tier 2 no longer accepts ambiguous (tie_review) profiles. Your tie_review profiles had 0% response rate.

3. **Raised Tier 3 threshold** (line 97)
   ```yaml
   min_primary_score: 13  # was: 12
   ```

   **Impact:** Only high-confidence Tier 3 profiles accepted. Reduces noise in backlog queue.

### ✅ Verify Changes

```bash
cd job-search

# Check config is valid YAML
python3 -c "import yaml; yaml.safe_load(open('linkedin/config.yaml'))"

# Test with dry-run
python3 tools/recruiter_orchestrate.py daily --headed --dry-run

# Inspect: Do tier assignments look better?
# - Michael Page recruiters in Tier 1–2 (not Tier 3)?
# - Fewer tie_review profiles in Tier 2?
# - Tier 3 candidates scoring ≥13?
```

---

## 📦 STEP 2: Persona Detection (1.5 hours)

**Status:** Code ready in `/implementation/01_persona_detection.py`

### What It Does

Classifies recruiters into 6 authority levels:

```
executive_search (95)       ← Retained search, C-level access
internal_hr_leader (90)     ← VP People, Head of HR
hiring_manager (85)         ← Area Manager, Store Director
in_house_recruiter (80)     ← Corporate talent team
staffing_agency (70)        ← Michael Page, Experis
generic_hr (60)             ← HR Admin, no hiring power
```

Enables tier rules like: **"Tier 1 requires authority ≥85"** (filters out generic HR)

### Implementation

1. **Copy the function:**
   ```bash
   # Open: implementation/01_persona_detection.py
   # Copy: detect_recruiter_persona() and PERSONA_AUTHORITY_WEIGHTS
   # Paste into: job-search/tools/recruiter_match.py (after imports)
   ```

2. **Integrate into match_recruiter_profile():**
   ```python
   # Around line 240 in recruiter_match.py, after creating blob_lower:

   persona_slug, persona_authority = detect_recruiter_persona(blob_lower)

   # Store in result:
   result["recruiter_meta"]["persona_slug"] = persona_slug
   result["recruiter_meta"]["persona_authority"] = persona_authority
   ```

3. **Integrate into assign_best_tier():**
   ```python
   # Around line 380, in the tier loop:

   min_auth = rule.get("min_persona_authority", 0)
   if persona_authority < min_auth:
       continue  # Skip this tier, try next
   ```

4. **Update config.yaml tiers:**
   ```yaml
   tiers:
     tier_1:
       min_persona_authority: 85   # NEW: Only exec search + in-house + hiring managers
     tier_2:
       min_persona_authority: 70   # NEW: Staffing OK, but not generic HR
     tier_3:
       min_persona_authority: 0    # Allow any (backlog testing)
   ```

5. **Test:**
   ```bash
   python3 tools/recruiter_orchestrate.py daily --headed --dry-run

   # Verify:
   # - Exec search consultants (authority=95) → Tier 1
   # - Michael Page (authority=70) → Tier 1–2
   # - Generic HR (authority=60) → Tier 3 or rejected
   ```

### Expected Outcome

- **Tier 1:** Higher authority (90+), more likely to respond
- **Tier 2:** Still strong (70+), but faster recruitment
- **Tier 3:** Lower authority (60–70), for backlog/testing
- **Response rate:** 33% → 40%+ (cleaner signal)

---

## 🔧 STEP 3: MCP Server (2 hours)

**Status:** Code ready in `/implementation/02_mcp_server.py`

### What It Does

Exposes your scorer as a **composable, network-accessible tool**:

```
Other Agents (Desktop Commander, LangGraph, external Claude)
    ↓ (sends HTTP request or MCP call)
MCP Server (localhost:8000 or stdio)
    ↓ (calls your match_recruiter_profile)
Your Scoring Engine
    ↓ (returns variant, score, tier, note)
Result: {"variant": "luxury-retail", "score": 18.5, "tier": "tier_1"}
```

### Installation

1. **Install MCP SDK:**
   ```bash
   cd job-search
   pip install mcp
   ```

2. **Create MCP directory structure:**
   ```bash
   mkdir -p job-search/mcp
   touch job-search/mcp/__init__.py  # Empty file
   ```

3. **Copy server file:**
   ```bash
   cp implementation/02_mcp_server.py job-search/mcp/server.py
   ```

4. **Verify imports:**
   ```bash
   cd job-search
   python3 -c "from mcp.server import Server; print('MCP SDK OK')"
   python3 -c "from tools.recruiter_match import match_recruiter_profile; print('Recruiter modules OK')"
   ```

### Launch

**Option A: Stdio mode (for Desktop Commander)**

```bash
cd job-search
python -m mcp.server

# Now Desktop Commander can call score_recruiter tool
```

**Option B: HTTP mode (for external clients)**

```bash
cd job-search
python -m mcp.server --http --port 8000

# Test with curl:
curl http://127.0.0.1:8000/tools/score_recruiter \
  -H "Content-Type: application/json" \
  -d '{
    "headline": "VP People at Michael Kors",
    "name": "Jane Doe",
    "profile_url": "https://linkedin.com/in/jane-doe",
    "company": "Michael Kors",
    "about": "20 years recruiting luxury brand leaders"
  }'

# Returns:
# {
#   "variant_slug_best": "luxury-retail",
#   "primary_score": 18.5,
#   "tier": "tier_1",
#   "would_send": true,
#   ...
# }
```

### Integration with Desktop Commander

Once MCP server is running:

```
User (in Desktop Commander):
"Score this recruiter:
Name: John Smith
Headline: Senior Recruiter at Michael Page
Company: Michael Page
About: 15 years staffing for retail"

Desktop Commander:
→ Calls MCP tool: score_recruiter(...)
→ Server calls your match_recruiter_profile()
→ Returns: {tier: tier_1, score: 16.2, confidence: clear_winner}

Desktop Commander:
"John is Tier 1 (score 16.2). Would send message:
'Hi John, I'm exploring premium retail leadership...'"
```

### Expected Outcome

- **Desktop Commander** can score any profile you paste
- **LangGraph workflows** can use your scorer as a decision tool
- **External agents** can evaluate candidates
- **Unlocks agentic automation:** Other tools can now call your scoring logic

---

## 📊 STEP 4: Analytics Template (15 minutes)

**Status:** Code ready in `/implementation/03_recruiter_quarterly_report.py`

### What It Does

Generates quarterly reports showing:

```
Summary
-------
Total contacts: 22
Total responses: 5
Overall response rate: 23% (target: 25%)

By Tier
-------
Tier 1:  2 sent, 1 response (50%)  ✓ Met target
Tier 2: 12 sent, 4 responses (33%) ✓ Met target
Tier 3:  8 sent, 0 responses (0%)  ❌ Below target

Top Companies
-------------
Michael Kors:   3 sent, 2 responses (67%)
Michael Page:   5 sent, 2 responses (40%)
Experis:        2 sent, 1 response  (50%)

Recommendations
---------------
⚠️ Tier 3 at 0% response. Raise min_primary_score to 13.
```

### Installation

1. **Copy script:**
   ```bash
   cp implementation/03_recruiter_quarterly_report.py job-search/tools/
   chmod +x job-search/tools/recruiter_quarterly_report.py
   ```

2. **Test:**
   ```bash
   cd job-search
   python3 tools/recruiter_quarterly_report.py

   # Or save to file:
   python3 tools/recruiter_quarterly_report.py --output report.md

   # Or analyze since a specific date:
   python3 tools/recruiter_quarterly_report.py --since 2026-05-01
   ```

3. **Add to Makefile:**
   ```makefile
   report:
   	$(PY) tools/recruiter_quarterly_report.py --output pipeline/recruiter_quarterly_report.md
   	open pipeline/recruiter_quarterly_report.md
   ```

4. **Run after 20+ contacts:**
   ```bash
   make report  # or: python3 tools/recruiter_quarterly_report.py
   ```

### Expected Outcome

- **Measure what matters:** Response rates by tier, company, variant
- **Detect patterns:** Which recruiter sources are most effective
- **Drive decisions:** Data-backed threshold adjustments
- **Track progress:** Month-over-month improvements

---

## 🚀 Full Implementation Checklist

### Week 1 (This Week)

- [x] **Config changes** (10 mins)
  - [x] Add staffing agency keywords to sector_keywords
  - [x] Set Tier 2 require_clear_winner: true
  - [x] Raise Tier 3 min_primary_score to 13
  - [x] Test with dry-run

- [ ] **Set up analytics** (15 mins)
  - [ ] Copy recruiter_quarterly_report.py to tools/
  - [ ] Test: python3 tools/recruiter_quarterly_report.py
  - [ ] Add to Makefile

### Week 2 (Next Week)

- [ ] **Persona detection** (1.5 hours)
  - [ ] Copy detect_recruiter_persona() into recruiter_match.py
  - [ ] Integrate into match_recruiter_profile()
  - [ ] Integrate into assign_best_tier()
  - [ ] Add min_persona_authority gates to config.yaml
  - [ ] Test with 5–10 profiles

- [ ] **Monitor response rates**
  - [ ] After 10+ new contacts, run: make report
  - [ ] Check: Did tier assignments improve? Did response rate increase?

### Week 3 (Following Week)

- [ ] **MCP server** (2 hours)
  - [ ] pip install mcp
  - [ ] mkdir mcp && touch mcp/__init__.py
  - [ ] Copy mcp/server.py
  - [ ] Test: python -m mcp.server
  - [ ] Verify Desktop Commander can call score_recruiter

- [ ] **Test agentic scoring**
  - [ ] Paste a recruiter profile into Desktop Commander
  - [ ] Ask DC to score it using MCP tool
  - [ ] Verify output is correct (tier, score, confidence)

### Week 4 (Following Week)

- [ ] **Integration testing**
  - [ ] Run end-to-end: scout → plan → dispatch (dry-run)
  - [ ] Verify all three improvements working together
  - [ ] Generate first monthly report
  - [ ] Make threshold adjustments if needed

---

## 📝 File Locations

```
job-search/
├── linkedin/config.yaml                          ✅ MODIFIED
├── tools/
│   ├── recruiter_match.py                       🔲 ADD persona detection
│   ├── recruiter_orchestrate.py                 🔲 No changes needed
│   └── recruiter_quarterly_report.py            🔲 COPY from implementation/
├── mcp/
│   ├── __init__.py                              🔲 CREATE (empty)
│   └── server.py                                🔲 COPY from implementation/
└── implementation/
    ├── 01_persona_detection.py                  (reference)
    ├── 02_mcp_server.py                         (reference)
    ├── 03_recruiter_quarterly_report.py         (reference)
    └── IMPLEMENTATION_GUIDE.md                  (this file)
```

---

## 🧪 Testing Each Stage

### After Config Changes
```bash
python3 tools/recruiter_orchestrate.py daily --headed --dry-run

# Check:
# - Michael Page profiles tier assignment
# - Fewer tie_review profiles in Tier 2
# - Tier 3 only has score ≥13
```

### After Persona Detection
```bash
python3 tools/recruiter_orchestrate.py daily --headed --dry-run

# Check logs for:
# persona_slug = "executive_search" (authority 95)
# persona_slug = "staffing_agency_recruiter" (authority 70)
# persona_slug = "generic_hr" (authority 60)
```

### After MCP Server
```bash
cd job-search
python -m mcp.server

# In separate terminal:
curl http://127.0.0.1:8000/tools/score_recruiter \
  -H "Content-Type: application/json" \
  -d '{"headline": "VP People", "name": "Jane", "profile_url": "https://...", ...}'

# Should return valid JSON with score, tier, etc.
```

### After Analytics Setup
```bash
python3 tools/recruiter_quarterly_report.py

# Should print Markdown report to stdout
```

---

## ⚠️ Troubleshooting

### Config changes don't take effect
- **Check:** Python correctly parses YAML
  ```bash
  python3 -c "import yaml; print(yaml.safe_load(open('linkedin/config.yaml')).keys())"
  ```
- **Fix:** Restart python process (kill any running CLI commands)

### Persona detection not imported
- **Check:** Python can find recruiter_match module
  ```bash
  cd job-search && python3 -c "from tools.recruiter_match import detect_recruiter_persona"
  ```
- **Fix:** Verify `from recruiter_match import detect_recruiter_persona` syntax (no `tools.` prefix)

### MCP server won't start
- **Check:** MCP SDK installed
  ```bash
  python3 -c "from mcp.server import Server; print(Server)"
  ```
- **Fix:** `pip install mcp`

### Analytics script can't find CSV
- **Check:** CSV exists
  ```bash
  ls -la job-search/pipeline/recruiters.csv
  ```
- **Fix:** Run `recruiter_orchestrate.py` at least once to generate CSV

---

## 📞 Support

**Issue:** Tier assignments still look wrong
**Debug:** Run dry-run with verbose output, check if persona detection is running

**Issue:** MCP server crashes
**Debug:** Check stderr for import errors, verify config.yaml is valid

**Issue:** Analytics report is empty
**Debug:** Check that recruiters.csv has ≥1 row

---

## 🎯 Success Criteria

After implementation, you should see:

✅ **Staffing agencies weighted correctly** — Michael Page tier ≥1–2 (not 3)
✅ **Persona authority working** — Exec search scores higher than generic HR
✅ **MCP tool available** — Desktop Commander can call score_recruiter
✅ **Analytics running** — Monthly reports show response rates by tier
✅ **Response rate improving** — 23% → 28%+ (after 20+ contacts)

---

## 🚀 Next Steps After Implementation

**Week 5:** Monitor response rates, adjust thresholds based on data
**Week 6:** Integrate MCP into hiring_network_workflow.py
**Week 7:** Full agentic end-to-end automation (discovery → score → send)

---

**Generated by Desktop Commander | 20 May 2026**
