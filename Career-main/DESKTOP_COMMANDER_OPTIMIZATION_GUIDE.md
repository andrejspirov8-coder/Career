# 🎯 DESKTOP COMMANDER OPTIMIZATION GUIDE

**Purpose:** Master Desktop Commander for Career workspace automation  
**Date:** 20 May 2026 | **Level:** Advanced

---

## Problem: Long-Running Processes

### Current Issue
```
❌ Scout process takes 5-15 minutes
❌ Browser automation blocks terminal
❌ Can't easily monitor progress
❌ Hard to see real-time results
```

### Solution: Detach & Monitor Pattern

**Instead of blocking on scout:**
```bash
# DON'T do this (blocks):
uv run python3 tools/recruiter_orchestrate.py scout --headed

# DO this instead (detaches):
nohup uv run python3 tools/recruiter_orchestrate.py scout --headed > scout.log 2>&1 &
```

Then monitor progress:
```bash
# Watch real-time log
tail -f scout.log

# Check results file growing
watch -n 2 'wc -l pipeline/recruiter_action_plan.jsonl'

# See latest profiles
tail -5 pipeline/recruiter_action_plan.jsonl | jq .
```

---

## Efficient Workflow Patterns

### Pattern 1: Script Everything

**Instead of running commands manually:**

Create `~/Downloads/Career-main/job-search/run_scout.sh`:
```bash
#!/bin/bash
echo "🎬 SCOUT PHASE STARTED: $(date)"
nohup uv run python3 tools/recruiter_orchestrate.py scout --headed > pipeline/scout.log 2>&1 &
echo "Scout running in background (PID: $!)"
echo "Monitor with: tail -f pipeline/scout.log"
```

Then just:
```bash
chmod +x run_scout.sh
./run_scout.sh
```

**Benefits:**
- Repeatable
- Easy to modify
- Can be scheduled
- Logs everything

### Pattern 2: Pipeline Chaining

Create `~/Downloads/Career-main/job-search/run_full_cycle.sh`:
```bash
#!/bin/bash
set -e  # Exit on error

echo "🎬 FULL CYCLE: Scout → Plan → Dispatch → Analytics"
echo "=================================================="
echo ""

# Phase 1: Scout (background)
echo "📍 Phase 1: Scout (discovering profiles)..."
nohup uv run python3 tools/recruiter_orchestrate.py scout --headed > pipeline/scout.log 2>&1 &
SCOUT_PID=$!
echo "   Scout running (PID: $SCOUT_PID)"
echo "   Monitor: tail -f pipeline/scout.log"
echo ""

# Wait for scout to complete
echo "⏳ Waiting for scout to complete..."
wait $SCOUT_PID
echo "✅ Scout complete"
echo ""

# Phase 2: Plan
echo "📍 Phase 2: Plan (building queue)..."
uv run python3 tools/recruiter_orchestrate.py plan --tier tier_1 --tier tier_2
echo "✅ Plan complete"
echo ""

# Phase 3: Dispatch (dry-run)
echo "📍 Phase 3: Dispatch (preview, dry-run)..."
uv run python3 tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --dry-run
echo "✅ Dispatch preview complete"
echo ""

# Phase 4: Analytics
echo "📍 Phase 4: Analytics (measuring results)..."
python3 tools/recruiter_quarterly_report.py --output pipeline/report.md
echo "✅ Analytics report generated"
echo ""

echo "=================================================="
echo "🎉 FULL CYCLE COMPLETE"
echo ""
echo "Results available in:"
echo "  - Scout: pipeline/recruiter_action_plan.jsonl"
echo "  - Plan: pipeline/recruiter_session_state.json"
echo "  - Analytics: pipeline/report.md"
```

Then:
```bash
./run_full_cycle.sh
```

**This does everything automatically!**

---

## Desktop Commander Specific Optimizations

### 1. Use Makefile Instead of Raw Commands

Create `~/Downloads/Career-main/job-search/Makefile.dc`:
```makefile
.PHONY: scout plan dispatch analytics full-cycle monitor

scout:
	@echo "🎬 Scout: Discovering profiles..."
	nohup uv run python3 tools/recruiter_orchestrate.py scout --headed > pipeline/scout.log 2>&1 &

plan:
	@echo "📍 Plan: Building queue..."
	uv run python3 tools/recruiter_orchestrate.py plan --tier tier_1 --tier tier_2

dispatch-preview:
	@echo "📍 Dispatch: Preview (dry-run)..."
	uv run python3 tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --dry-run

analytics:
	@echo "📊 Analytics: Measuring results..."
	python3 tools/recruiter_quarterly_report.py --output pipeline/report.md

full-cycle: scout
	@echo "⏳ Waiting for scout..."
	@while [ ! -f pipeline/recruiter_action_plan.jsonl ]; do sleep 2; done
	@make plan dispatch-preview analytics
	@echo "✅ Full cycle complete"

monitor:
	@tail -f pipeline/scout.log

results:
	@echo "📊 Latest results:"
	@tail -5 pipeline/recruiter_action_plan.jsonl | jq .

status:
	@echo "Current files:"
	@wc -l pipeline/recruiter_action_plan.jsonl
	@echo "Latest activity:"
	@ls -lt pipeline/ | head -5
```

Then use from Desktop Commander:
```bash
make -f Makefile.dc scout
make -f Makefile.dc monitor
make -f Makefile.dc full-cycle
make -f Makefile.dc results
```

### 2. Create Desktop Commander Skills

**Instead of manual commands, create a Skill:**

`~/.config/raycast-skills/career-automation.md`:
```markdown
# Career Automation

## Commands

### Scout Profiles
```bash
cd ~/Downloads/Career-main/job-search && ./run_scout.sh
```

Monitor:
```bash
tail -f ~/Downloads/Career-main/job-search/pipeline/scout.log
```

### Build Plan
```bash
cd ~/Downloads/Career-main/job-search && \
uv run python3 tools/recruiter_orchestrate.py plan --tier tier_1 --tier tier_2
```

### Preview Dispatch
```bash
cd ~/Downloads/Career-main/job-search && \
uv run python3 tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --dry-run
```

### Generate Analytics
```bash
cd ~/Downloads/Career-main/job-search && \
python3 tools/recruiter_quarterly_report.py --output pipeline/report.md
```

### Full Cycle
```bash
cd ~/Downloads/Career-main/job-search && ./run_full_cycle.sh
```

### Check Status
```bash
cd ~/Downloads/Career-main/job-search && \
echo "Scout results: $(wc -l < pipeline/recruiter_action_plan.jsonl) rows" && \
echo "Latest profiles:" && \
tail -3 pipeline/recruiter_action_plan.jsonl | jq -r '.name, .company'
```
```

Then invoke from Raycast or Desktop Commander:
```
Career Automation: Scout Profiles
Career Automation: Build Plan
Career Automation: Preview Dispatch
Career Automation: Full Cycle
```

### 3. Use Python Scripts for Complex Orchestration

`~/Downloads/Career-main/job-search/tools/automated_workflow.py`:
```python
#!/usr/bin/env python3
"""
Automated Career Workspace Workflow
Orchestrates scout → plan → dispatch → analytics
"""

import subprocess
import time
import os
from pathlib import Path

class CareerWorkflow:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.pipeline_dir = self.base_dir / "pipeline"
    
    def run_command(self, cmd, description, background=False):
        """Run command with logging"""
        print(f"\n{'='*60}")
        print(f"📍 {description}")
        print(f"{'='*60}")
        print(f"Command: {cmd}\n")
        
        if background:
            os.system(f"nohup {cmd} > {self.pipeline_dir}/workflow.log 2>&1 &")
            print(f"✅ Running in background")
            return
        
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            print(f"✅ {description} complete")
        else:
            print(f"❌ {description} failed")
            raise RuntimeError(f"{description} failed")
    
    def wait_for_file(self, filepath, timeout=600):
        """Wait for file to have content"""
        start = time.time()
        while time.time() - start < timeout:
            if filepath.exists() and filepath.stat().st_size > 0:
                return
            time.sleep(2)
        raise TimeoutError(f"Timeout waiting for {filepath}")
    
    def scout_phase(self):
        """Phase 1: Scout & Score"""
        cmd = "cd {} && uv run python3 tools/recruiter_orchestrate.py scout --headed".format(self.base_dir)
        self.run_command(cmd, "Scout: Discovering & Scoring Profiles", background=True)
        
        # Wait for scout to produce results
        self.wait_for_file(self.pipeline_dir / "recruiter_action_plan.jsonl")
    
    def plan_phase(self):
        """Phase 2: Build Queue"""
        cmd = "cd {} && uv run python3 tools/recruiter_orchestrate.py plan --tier tier_1 --tier tier_2".format(self.base_dir)
        self.run_command(cmd, "Plan: Building Dispatch Queue")
    
    def dispatch_phase(self):
        """Phase 3: Preview (Dry-run)"""
        cmd = "cd {} && uv run python3 tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --dry-run".format(self.base_dir)
        self.run_command(cmd, "Dispatch: Preview (Dry-run)")
    
    def analytics_phase(self):
        """Phase 4: Analytics"""
        cmd = "cd {} && python3 tools/recruiter_quarterly_report.py --output pipeline/report.md".format(self.base_dir)
        self.run_command(cmd, "Analytics: Measuring Results")
    
    def show_results(self):
        """Display results"""
        print(f"\n{'='*60}")
        print("📊 RESULTS")
        print(f"{'='*60}\n")
        
        action_plan = self.pipeline_dir / "recruiter_action_plan.jsonl"
        if action_plan.exists():
            with open(action_plan) as f:
                lines = f.readlines()
                print(f"✅ Profiles discovered: {len(lines)}")
                if lines:
                    print("\nLatest profiles:")
                    for line in lines[-3:]:
                        print(f"  - {line.strip()[:80]}...")
        
        report = self.pipeline_dir / "report.md"
        if report.exists():
            print(f"\n✅ Analytics report generated")
            print(f"   Location: {report}")
    
    def run_full_cycle(self):
        """Execute full workflow"""
        print("\n🚀 CAREER WORKSPACE: FULL EXECUTION CYCLE")
        print("="*60)
        
        try:
            self.scout_phase()
            self.plan_phase()
            self.dispatch_phase()
            self.analytics_phase()
            self.show_results()
            
            print(f"\n{'='*60}")
            print("🎉 FULL CYCLE COMPLETE")
            print(f"{'='*60}\n")
        
        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise

if __name__ == "__main__":
    import sys
    
    workflow = CareerWorkflow()
    
    if len(sys.argv) > 1:
        phase = sys.argv[1]
        if phase == "scout":
            workflow.scout_phase()
        elif phase == "plan":
            workflow.plan_phase()
        elif phase == "dispatch":
            workflow.dispatch_phase()
        elif phase == "analytics":
            workflow.analytics_phase()
        else:
            workflow.run_full_cycle()
    else:
        workflow.run_full_cycle()
```

Then use:
```bash
python3 tools/automated_workflow.py              # Full cycle
python3 tools/automated_workflow.py scout        # Scout only
python3 tools/automated_workflow.py plan         # Plan only
```

---

## Best Practices for Desktop Commander

### 1. **Use Skills Instead of Raw Commands**
```
❌ Bad: Manually typing commands in terminal
✅ Good: Create a Skill that wraps commands
```

### 2. **Background Long-Running Tasks**
```
❌ Bad: uv run python3 tools/recruiter_orchestrate.py scout --headed
✅ Good: nohup uv run python3 ... > log.txt 2>&1 &
```

### 3. **Monitor, Don't Wait**
```
❌ Bad: Sitting in terminal waiting for results
✅ Good: tail -f log.txt in separate terminal
```

### 4. **Organize with Makefiles**
```
❌ Bad: Remembering complex commands
✅ Good: make scout, make plan, make full-cycle
```

### 5. **Automate Everything**
```
❌ Bad: Manual 4-phase workflow
✅ Good: One script that does all 4 phases
```

---

## Recommended Workflow for Career Automation

### Setup (One-time)

```bash
cd ~/Downloads/Career-main/job-search

# 1. Create scripts
cat > run_scout.sh << 'SCRIPT'
#!/bin/bash
nohup uv run python3 tools/recruiter_orchestrate.py scout --headed > pipeline/scout.log 2>&1 &
echo "Scout running (PID: $!)"
SCRIPT
chmod +x run_scout.sh

# 2. Create automated workflow
# (Copy python script above to tools/automated_workflow.py)

# 3. Test
python3 tools/automated_workflow.py
```

### Daily Usage

From Desktop Commander:
```
1. "Run career workflow"
2. Monitor: "tail -f pipeline/scout.log"
3. Check: "Make results"
4. Review: "open pipeline/report.md"
```

---

## Summary: Efficient Desktop Commander Usage

| Task | Method | Efficiency |
|------|--------|------------|
| **Single command** | Direct in terminal | ⭐ Quick |
| **Repeated commands** | Create a script | ⭐⭐⭐ Better |
| **Complex workflow** | Python orchestration | ⭐⭐⭐⭐ Best |
| **Long-running task** | Background + monitor | ⭐⭐⭐⭐ Prevents blocking |
| **Full automation** | Makefile + scripts | ⭐⭐⭐⭐⭐ Maximum efficiency |

---

## Next Steps

1. **Create `run_full_cycle.sh`** (5 mins)
   - Copy script above
   - Test: `./run_full_cycle.sh`

2. **Create `Makefile.dc`** (5 mins)
   - Copy Makefile above
   - Test: `make -f Makefile.dc scout`

3. **Deploy `automated_workflow.py`** (5 mins)
   - Copy Python script
   - Test: `python3 tools/automated_workflow.py`

4. **Create Raycast Skill** (10 mins)
   - Wrap scripts in Skill
   - Invoke from Raycast

---

**GOAL:** Never type a long command again. Everything orchestrated, automated, and monitored efficiently.

---

Generated by Desktop Commander | 20 May 2026
