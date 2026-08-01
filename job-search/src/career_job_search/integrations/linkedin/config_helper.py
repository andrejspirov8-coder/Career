"""Read and write linkedin/config.yaml from the dashboard."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import yaml

from career_job_search.core.contracts import helper_json
from career_job_search.integrations.linkedin.paths import DEFAULT_LINKEDIN_CONFIG


def read_config() -> dict[str, Any]:
    if not DEFAULT_LINKEDIN_CONFIG.exists():
        return {}
    raw = yaml.safe_load(DEFAULT_LINKEDIN_CONFIG.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def write_config(data: dict[str, Any]) -> None:
    path = DEFAULT_LINKEDIN_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage LinkedIn config")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show")
    save = subparsers.add_parser("save")
    save.add_argument("--json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "show":
            data = read_config()
        else:
            raw = json.loads(args.json)
            if not isinstance(raw, dict):
                raise ValueError("LinkedIn config must be a JSON object.")
            write_config(raw)
            data = read_config()
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(helper_json({"ok": False, "error": str(exc)}))
        return 1
    print(helper_json({"ok": True, "data": data}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
