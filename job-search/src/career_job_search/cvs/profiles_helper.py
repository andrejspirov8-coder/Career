"""Read and write CV variant profiles from the dashboard."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import yaml

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import project_path

VARIANT_PROFILES_PATH = project_path("cv", "variant_profiles.yaml")


def read_profiles() -> dict[str, Any]:
    if not VARIANT_PROFILES_PATH.exists():
        return {"variants": {}}
    raw = yaml.safe_load(VARIANT_PROFILES_PATH.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def write_profiles(data: dict[str, Any]) -> None:
    path = VARIANT_PROFILES_PATH
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
    parser = argparse.ArgumentParser(description="Manage CV variant profiles")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show")
    save = subparsers.add_parser("save")
    save.add_argument("--json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "show":
            data = read_profiles()
        else:
            raw = json.loads(args.json)
            if not isinstance(raw, dict):
                raise ValueError("Variant profiles must be a JSON object.")
            write_profiles(raw)
            data = read_profiles()
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(helper_json({"ok": False, "error": str(exc)}))
        return 1
    print(helper_json({"ok": True, "data": data}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
