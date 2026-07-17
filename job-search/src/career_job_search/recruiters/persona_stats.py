"""Persona accept-rate aggregation for learning loop."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from career_job_search.integrations.linkedin.paths import PIPELINE_DIR, RECRUITERS_CSV

PERSONA_STATS_JSON = PIPELINE_DIR / "persona_stats.json"
MIN_SENDS_FOR_BOOST = 5


def aggregate_persona_stats(
    csv_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    path = csv_path or RECRUITERS_CSV
    stats: dict[str, dict[str, int]] = {}
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            persona = (row.get("persona") or "").strip() or "(no persona)"
            if persona.startswith("__meta__"):
                continue
            status = (row.get("status") or "").strip().lower()
            block = stats.setdefault(persona, {"sent": 0, "accepted": 0, "reply": 0})
            if status in {"sent", "pending", "accepted"}:
                block["sent"] += 1
            if (row.get("accepted_at") or "").strip():
                block["accepted"] += 1
            if (row.get("reply_at") or "").strip():
                block["reply"] += 1
    out: dict[str, dict[str, Any]] = {}
    for persona, block in stats.items():
        sent = block["sent"]
        accepted = block["accepted"]
        rate = (accepted / sent) if sent else 0.0
        out[persona] = {
            "sent": sent,
            "accepted": accepted,
            "reply": block["reply"],
            "rate": round(rate, 4),
        }
    return out


def write_persona_stats(
    output_path: Path | None = None,
    csv_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    stats = aggregate_persona_stats(csv_path)
    out = output_path or PERSONA_STATS_JSON
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return stats


def load_persona_stats(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p = path or PERSONA_STATS_JSON
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def persona_boost_factor(
    persona: str, stats: dict[str, dict[str, Any]] | None = None
) -> float:
    """Return multiplier 0.7–1.3 when enough sends exist; else 1.0."""
    block = stats or load_persona_stats()
    entry = block.get(persona) or {}
    sent = int(entry.get("sent") or 0)
    if sent < MIN_SENDS_FOR_BOOST:
        return 1.0
    rate = float(entry.get("rate") or 0.0)
    factor = 0.7 + 0.6 * rate
    return max(0.7, min(1.3, round(factor, 4)))
