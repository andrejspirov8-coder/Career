"""Read and write opportunity sources config from the dashboard."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import yaml

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import project_path

DEFAULT_CONFIG = project_path("config", "opportunities.example.yaml")
USER_CONFIG = project_path("config", "opportunities.yaml")


def read_config() -> dict[str, Any]:
    path = USER_CONFIG if USER_CONFIG.exists() else DEFAULT_CONFIG
    if not path.exists():
        return {"opportunities": {"sources": {}}}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def write_config(data: dict[str, Any]) -> None:
    path = USER_CONFIG
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
    parser = argparse.ArgumentParser(description="Manage opportunity sources")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show")
    subparsers.add_parser("show-defaults")
    save = subparsers.add_parser("save")
    save.add_argument("--json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "show":
            data = read_config()
        elif args.command == "show-defaults":
            if DEFAULT_CONFIG.exists():
                data = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8")) or {}
            else:
                data = {}
        else:
            raw = json.loads(args.json)
            if not isinstance(raw, dict):
                raise ValueError("Opportunity sources must be a JSON object.")
            write_config(raw)
            data = read_config()
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(helper_json({"ok": False, "error": str(exc)}))
        return 1
    print(helper_json({"ok": True, "data": data}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
