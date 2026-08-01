"""Read and write recruiter runtime settings from the dashboard."""

from __future__ import annotations

import argparse
import json

from career_job_search.core.contracts import helper_json
from career_job_search.recruiters.config import (
    Settings,
    load_settings,
    save_settings,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage recruiter runtime settings")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show")
    save = subparsers.add_parser("save")
    save.add_argument("--json", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "show":
            settings = load_settings()
            data = settings.model_dump(mode="json")
        else:
            raw = json.loads(args.json)
            if not isinstance(raw, dict):
                raise ValueError("Settings must be a JSON object.")
            settings = Settings.model_validate(raw)
            save_settings(settings)
            data = settings.model_dump(mode="json")
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(helper_json({"ok": False, "error": str(exc)}))
        return 1
    print(helper_json({"ok": True, "data": data}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
