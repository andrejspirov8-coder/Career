---
description: Write a session handoff to .memory/sessions/
---

Read `job-search/.memory/index.md` to understand existing context, then run:
```
cd job-search && make handoff GOAL="$1" DONE="$2" NEXT="$3" BLOCKERS="$4"
```
Capture the result and confirm the handoff was recorded.
