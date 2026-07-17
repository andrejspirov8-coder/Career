#!/usr/bin/env python3
"""
MCP Server: Expose Recruiter Scorer as Composable Tool

This is a minimal Model Context Protocol (MCP) server that exposes your recruiter
scoring logic as a callable tool. Other agents (Desktop Commander, LangGraph, 
external Claude instances) can now ask: \"Score this recruiter profile.\"

Why MCP?
--------
Currently, scoring is trapped in CLI (python tools/recruiter_orchestrate.py).
With MCP, scoring becomes a **composable service**:
- Desktop Commander can score profiles you paste
- LangGraph can use your scorer as a decision-making tool
- External agents can evaluate candidates
- Future integrations: Slack bots, web APIs, etc.

Installation:
-----------
1. Install MCP SDK: pip install mcp
2. Copy this file to: job-search/mcp/server.py
3. Create: job-search/mcp/__init__.py (empty file)

Launch:
------
# Stdio mode (for Desktop Commander integration):
python -m mcp.server

# HTTP mode (for external clients):
python -m mcp.server --http --port 8000

# WebSocket mode:
python -m mcp.server --ws --port 8000

Testing:
-------
# Example curl (HTTP mode):
curl http://127.0.0.1:8000/tools/score_recruiter \\
  -H \"Content-Type: application/json\" \\
  -d '{
    \"headline\": \"Senior Recruiter, Premium Retail | Michael Kors\",
    \"name\": \"Jane Doe\",
    \"profile_url\": \"https://linkedin.com/in/jane-doe\",
    \"company\": \"Michael Kors\",\n    \"about\": \"10+ years recruiting luxury brands\"\n  }'

Generated: 20 May 2026 | Desktop Commander Recommendations
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# MCP framework (install with: pip install mcp)
try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent, ToolResult, ToolError
except ImportError:
    print(\"ERROR: MCP SDK not installed. Run: pip install mcp\")
    sys.exit(1)

# Add tools directory to path so we can import your modules
TOOLS_DIR = Path(__file__).parent.parent / \"tools\"
sys.path.insert(0, str(TOOLS_DIR))

try:
    from recruiter_match import (\n        match_recruiter_profile,\n        assign_best_tier,\n        prepare_outreach_note_bundle,\n        should_send_recruiter_connection,\n    )\n    from recruiter_config import load_recruiter_config\nexcept ImportError as e:\n    print(f\"ERROR: Could not import recruiter modules: {e}\")\n    print(f\"Make sure job-search/tools/*.py files exist and are readable\")\n    sys.exit(1)\n\n\nclass RecruiterScorerServer:\n    \"\"\"MCP Server for recruiter profile scoring.\"\"\"\n    \n    def __init__(self):\n        self.server = Server(\"recruiter-scorer\")\n        self.config = load_recruiter_config()\n        self.register_tools()\n    \n    def register_tools(self):\n        \"\"\"Register available MCP tools.\"\"\"\n        \n        @self.server.call_tool()\n        async def score_recruiter(\n            headline: str,\n            name: str,\n            profile_url: str,\n            company: str = \"\",\n            about: str = \"\",\n            location: str = \"\",\n            variant_hint: str = \"luxury-retail\",\n        ) -> ToolResult:\n            \"\"\"\n            Score a LinkedIn recruiter profile against your CV variants.\n            \n            Returns:\n            - variant_slug_best: Best matching CV variant\n            - primary_score: Numeric score (0–20 typical range)\n            - confidence: 'clear_winner' or 'tie_review'\n            - tier: 'tier_1', 'tier_2', 'tier_3', or 'tier_rest'\n            - recruiter_gate_ok: Passes hiring ecosystem signal check\n            - would_send: True if profile passes all gates (safe to contact)\n            - skip_reason: If would_send=false, reason why profile was rejected\n            - top_signals: Keyword hits that drove the score\n            - note_preview: Personalized connection note (first 220 chars)\n            \"\"\"\n            try:\n                # Run the scoring pipeline\n                result = match_recruiter_profile(\n                    headline=headline,\n                    name=name,\n                    profile_url=profile_url,\n                    company=company,\n                    about=about,\n                    location=location,\n                    recruiter_cfg=self.config,\n                )\n                \n                # Assign tier\n                tier, tier_reason = assign_best_tier(\n                    result=result,\n                    cfg=self.config,\n                    company_blob_lower=(company + \" \" + result.get(\"job\", {}).get(\"company\", \"\")).lower(),\n                )\n                \n                # Check if should send\n                rec = result.get(\"recommendation\") or {}\n                meta = result.get(\"recruiter_meta\") or {}\n                \n                ok_send, skip_reason = should_send_recruiter_connection(\n                    result,\n                    min_primary_score=float(self.config.get(\"matching\", {}).get(\"min_primary_score\", 12.0)),\n                    min_margin_over_second=float(self.config.get(\"matching\", {}).get(\"min_margin_over_second\", 4.0)),\n                    require_clear_winner=bool(self.config.get(\"matching\", {}).get(\"require_clear_winner\", False)),\n                    require_recruiter_gate=bool(self.config.get(\"matching\", {}).get(\"require_recruiter_gate\", True)),\n                    full_cfg=self.config,\n                )\n                \n                # Prepare note\n                note_bundle = prepare_outreach_note_bundle(\n                    match_result=result,\n                    headline=headline,\n                    about=about,\n                    location_txt=location,\n                    display_name=name,\n                    search_variant_slug=variant_hint,\n                    meta_signals_csv=meta.get(\"top_signals\", \"\"),\n                    note_templates_raw=self.config.get(\"connection_notes\", {}),\n                    matching_cfg=self.config.get(\"matching\", {}),\n                )\n                \n                output = {\n                    \"variant_slug_best\": str(rec.get(\"variant_slug\", \"\")),\n                    \"primary_score\": float(rec.get(\"primary_score\", 0.0)),\n                    \"margin_over_second\": float(rec.get(\"margin_over_second\", 0.0)),\n                    \"confidence\": str(rec.get(\"confidence\", \"\")),\n                    \"tier\": tier,\n                    \"tier_reason\": tier_reason,\n                    \"recruiter_gate_ok\": bool(meta.get(\"recruiter_gate_ok\", False)),\n                    \"would_send\": ok_send,\n                    \"skip_reason\": skip_reason if not ok_send else \"\",\n                    \"top_signals\": meta.get(\"top_signals\", \"\"),\n                    \"note_preview\": note_bundle.get(\"note_preview_trim\", \"\"),\n                    \"note_full\": note_bundle.get(\"note_live_full\", \"\"),\n                    \"profile_url\": profile_url,\n                }\n                \n                return ToolResult(\n                    content=[TextContent(\n                        type=\"text\",\n                        text=json.dumps(output, indent=2, ensure_ascii=False)\n                    )],\n                    is_error=False\n                )\n            \n            except Exception as e:\n                return ToolResult(\n                    content=[TextContent(\n                        type=\"text\",\n                        text=json.dumps({\"error\": str(e), \"type\": type(e).__name__}, indent=2)\n                    )],\n                    is_error=True\n                )\n        \n        @self.server.list_tools()\n        async def list_tools() -> list[Tool]:\n            \"\"\"Return list of available tools.\"\"\"\n            return [\n                Tool(\n                    name=\"score_recruiter\",\n                    description=\"Score a LinkedIn recruiter profile against your CV variants and tier rules. Returns variant match, score, tier, and personalized connection note.\",\n                    inputSchema={\n                        \"type\": \"object\",\n                        \"properties\": {\n                            \"headline\": {\n                                \"type\": \"string\",\n                                \"description\": \"LinkedIn headline (current job title + company)\",\n                            },\n                            \"name\": {\n                                \"type\": \"string\",\n                                \"description\": \"Full name or display name\",\n                            },\n                            \"profile_url\": {\n                                \"type\": \"string\",\n                                \"description\": \"LinkedIn profile URL\",\n                            },\n                            \"company\": {\n                                \"type\": \"string\",\n                                \"description\": \"Current company name\",\n                            },\n                            \"about\": {\n                                \"type\": \"string\",\n                                \"description\": \"About/bio section (up to 1000 chars)\",\n                            },\n                            \"location\": {\n                                \"type\": \"string\",\n                                \"description\": \"Location (city, country)\",\n                            },\n                            \"variant_hint\": {\n                                \"type\": \"string\",\n                                \"enum\": [\n                                    \"luxury-retail\",\n                                    \"luxury-retail-lt\",\n                                    \"operations-management\",\n                                    \"it-business\",\n                                ],\n                                \"description\": \"Expected CV variant (used as tiebreaker)\",\n                            },\n                        },\n                        \"required\": [\"headline\", \"name\", \"profile_url\"],\n                    },\n                ),\n            ]\n    \n    async def run(self):\n        \"\"\"Run the MCP server.\"\"\"\n        async with self.server:\n            print(f\"Recruiter Scorer MCP Server started\", file=sys.stderr)\n            print(f\"Available tools: score_recruiter\", file=sys.stderr)\n            print(f\"Listening on stdio...\", file=sys.stderr)\n            await self.server.wait_closed()\n\n\ndef main():\n    \"\"\"Entry point.\"\"\"\n    server = RecruiterScorerServer()\n    \n    # Run the server\n    asyncio.run(server.run())\n\n\nif __name__ == \"__main__\":\n    main()\n