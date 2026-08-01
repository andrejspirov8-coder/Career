#!/usr/bin/env python3
"""Safe, fixed-path CV editing, versioning, building, and comparison helper."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT
from career_job_search.cvs.matching import (
    keyword_gaps,
    load_profiles,
    match_job_to_variants,
)
from career_job_search.cvs.pdf_builder import CV_VARIANTS, build_canva_paste, build_pdf
from career_job_search.opportunities.repository import get_opportunity
from career_job_search.opportunities.text import clean_opportunity_text

CV_ROOT = JOB_ROOT / "cv"

CV_STUDIO_SCHEMA = "career_cv_studio_v1"
CV_VERSION_SCHEMA = "career_cv_source_version_v1"
MAX_SOURCE_BYTES = 100_000
MAX_HISTORY_ITEMS = 50
VERSION_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[a-f0-9]{12}$")
OPPORTUNITY_ID_RE = re.compile(r"^opp_[A-Za-z0-9_-]{1,128}$")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
REQUIRED_SECTIONS = {
    "Target Title",
    "Professional Summary",
    "Languages",
    "Experience",
}
SKILL_SECTIONS = {"Core Skills", "Skills", "Technical Skills"}


@dataclass(frozen=True)
class VariantPaths:
    slug: str
    root: Path
    source: Path
    visual_pdf: Path
    ats_pdf: Path
    canva_text: Path


_VARIANT_FILES = {
    slug: (md_path.name, out_pdf.name, paste_path.name)
    for slug, md_path, out_pdf, paste_path in CV_VARIANTS
}


def _variant_paths(slug: str, *, root: Path = JOB_ROOT) -> VariantPaths:
    filenames = _VARIANT_FILES.get(slug)
    if filenames is None:
        raise ValueError("Choose a known CV variant.")
    source_name, visual_name, paste_name = filenames
    visual_pdf = root / "output" / visual_name
    return VariantPaths(
        slug=slug,
        root=root,
        source=root / "cv" / source_name,
        visual_pdf=visual_pdf,
        ats_pdf=visual_pdf.with_name(f"{visual_pdf.stem}-ats.pdf"),
        canva_text=root / "output" / "canva" / paste_name,
    )


def _normalize_source(content: Any) -> str:
    if not isinstance(content, str):
        raise ValueError("CV content must be text.")
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("\ufeff"):
        normalized = normalized.removeprefix("\ufeff")
    normalized = normalized.rstrip() + "\n"
    if not normalized.strip():
        raise ValueError("CV content cannot be empty.")
    if len(normalized.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("CV content is too large.")
    if CONTROL_CHAR_RE.search(normalized):
        raise ValueError("CV content contains unsupported control characters.")
    _validate_source_shape(normalized)
    return normalized


def _validate_source_shape(content: str) -> None:
    lines = content.splitlines()
    if not lines or not lines[0].startswith("# ") or not lines[0][2:].strip():
        raise ValueError("The CV must start with `# Name`.")
    headings = re.findall(r"^## ([^\n]+)$", content, flags=re.MULTILINE)
    duplicates = {heading for heading in headings if headings.count(heading) > 1}
    if duplicates:
        raise ValueError(f"Duplicate CV section: {sorted(duplicates)[0]}.")
    missing = sorted(REQUIRED_SECTIONS.difference(headings))
    if missing:
        raise ValueError(f"Missing required CV section: {missing[0]}.")
    if not SKILL_SECTIONS.intersection(headings):
        raise ValueError("Missing a Core Skills, Skills, or Technical Skills section.")
    experience = content.split("## Experience", 1)[1]
    if not re.search(r"^### .+", experience, flags=re.MULTILINE):
        raise ValueError("Experience must include at least one role heading.")
    if not re.search(r"^- .+", experience, flags=re.MULTILINE):
        raise ValueError("Experience must include at least one bullet.")


def _source_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _file_time(path: Path) -> str | None:
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace(
        "+00:00", "Z"
    )


def _version_root(paths: VariantPaths) -> Path:
    return paths.root / "state" / "cv_versions" / paths.slug


def _version_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version_id": str(payload["version_id"]),
        "created_at": str(payload["created_at"]),
        "reason": str(payload["reason"]),
        "content_hash": str(payload["content_hash"]),
        "character_count": int(payload["character_count"]),
        "word_count": int(payload["word_count"]),
    }


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=".cv-version-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _snapshot_current(paths: VariantPaths, reason: str) -> dict[str, Any]:
    if not paths.source.is_file():
        raise FileNotFoundError("The selected CV source file is missing.")
    content = _normalize_source(paths.source.read_text(encoding="utf-8"))
    content_hash = _source_hash(content)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    version_id = f"{timestamp}-{content_hash[:12]}"
    payload = {
        "schema": CV_VERSION_SCHEMA,
        "version_id": version_id,
        "variant": paths.slug,
        "source_filename": paths.source.name,
        "created_at": _iso_now(),
        "reason": reason,
        "content_hash": content_hash,
        "character_count": len(content),
        "word_count": len(re.findall(r"\S+", content)),
        "content": content,
    }
    version_path = _version_root(paths) / f"{version_id}.json"
    if not version_path.exists():
        _write_private_json(version_path, payload)
    return _version_metadata(payload)


def _read_version(paths: VariantPaths, version_id: str) -> dict[str, Any]:
    if not VERSION_ID_RE.fullmatch(version_id):
        raise ValueError("Choose a valid CV version.")
    version_path = _version_root(paths) / f"{version_id}.json"
    if version_path.is_symlink() or not version_path.is_file():
        raise FileNotFoundError("The selected CV version was not found.")
    if version_path.stat().st_size > MAX_SOURCE_BYTES * 2:
        raise ValueError("The selected CV version is too large.")
    payload = json.loads(version_path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != CV_VERSION_SCHEMA
        or payload.get("variant") != paths.slug
        or payload.get("version_id") != version_id
    ):
        raise ValueError("The selected CV version is invalid.")
    content = _normalize_source(payload.get("content"))
    if payload.get("content_hash") != _source_hash(content):
        raise ValueError("The selected CV version failed its integrity check.")
    payload["content"] = content
    return payload


def list_versions(slug: str, *, root: Path = JOB_ROOT) -> list[dict[str, Any]]:
    paths = _variant_paths(slug, root=root)
    history_root = _version_root(paths)
    if not history_root.is_dir():
        return []
    versions: list[dict[str, Any]] = []
    for version_path in sorted(history_root.glob("*.json"), reverse=True):
        if len(versions) >= MAX_HISTORY_ITEMS:
            break
        if version_path.is_symlink() or not VERSION_ID_RE.fullmatch(version_path.stem):
            continue
        try:
            payload = _read_version(paths, version_path.stem)
            versions.append(_version_metadata(payload))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    return versions


def get_document(slug: str, *, root: Path = JOB_ROOT) -> dict[str, Any]:
    paths = _variant_paths(slug, root=root)
    if not paths.source.is_file():
        raise FileNotFoundError("The selected CV source file is missing.")
    content = _normalize_source(paths.source.read_text(encoding="utf-8"))
    return {
        "schema": CV_STUDIO_SCHEMA,
        "variant": slug,
        "source_filename": paths.source.name,
        "content": content,
        "content_hash": _source_hash(content),
        "source_updated_at": _file_time(paths.source),
        "versions": list_versions(slug, root=root),
    }


@contextmanager
def _studio_lock(root: Path) -> Iterator[None]:
    state_root = root / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    lock_path = state_root / "cv_studio.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        lock_path.chmod(0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _build_variant_files(
    paths: VariantPaths,
    content: str,
    transaction_root: Path,
) -> dict[str, Path]:
    source = transaction_root / paths.source.name
    visual_pdf = transaction_root / paths.visual_pdf.name
    ats_pdf = transaction_root / paths.ats_pdf.name
    canva_text = transaction_root / paths.canva_text.name
    source.write_text(content, encoding="utf-8")
    source.chmod(0o600)
    photo = paths.root / "cv" / "assets" / "andrej-spirov-headshot.png"
    build_pdf(source, visual_pdf, layout="canva", photo=photo if photo.is_file() else None)
    build_pdf(source, ats_pdf, layout="plain")
    build_canva_paste(source, canva_text)
    for output in (visual_pdf, ats_pdf, canva_text):
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("The selected CV did not produce every expected output.")
        output.chmod(0o600)
    return {
        "source": source,
        "visual": visual_pdf,
        "ats": ats_pdf,
        "canva": canva_text,
    }


def _commit_files(
    paths: VariantPaths,
    prepared: dict[str, Path],
    *,
    include_source: bool,
    transaction_root: Path,
) -> None:
    targets = {
        "visual": paths.visual_pdf,
        "ats": paths.ats_pdf,
        "canva": paths.canva_text,
    }
    if include_source:
        targets = {"source": paths.source, **targets}
    backup_root = transaction_root / "previous"
    backup_root.mkdir(parents=True, exist_ok=True)
    backups: dict[str, Path | None] = {}
    modes: dict[str, int] = {}
    committed: list[str] = []
    for key, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            backup = backup_root / f"{key}-{target.name}"
            shutil.copy2(target, backup)
            backups[key] = backup
            modes[key] = stat.S_IMODE(target.stat().st_mode)
        else:
            backups[key] = None
    try:
        for key, target in targets.items():
            os.replace(prepared[key], target)
            target.chmod(modes.get(key, 0o600))
            committed.append(key)
    except Exception:
        for key in reversed(committed):
            target = targets[key]
            backup = backups[key]
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                shutil.copy2(backup, target)
        raise


def _build_status(paths: VariantPaths) -> dict[str, Any]:
    return {
        "variant": paths.slug,
        "visual_pdf": {
            "filename": paths.visual_pdf.name,
            "size_bytes": paths.visual_pdf.stat().st_size,
            "updated_at": _file_time(paths.visual_pdf),
        },
        "ats_pdf": {
            "filename": paths.ats_pdf.name,
            "size_bytes": paths.ats_pdf.stat().st_size,
            "updated_at": _file_time(paths.ats_pdf),
        },
        "canva_text": {
            "filename": paths.canva_text.name,
            "size_bytes": paths.canva_text.stat().st_size,
            "updated_at": _file_time(paths.canva_text),
        },
    }


def save_and_rebuild(
    slug: str,
    content: Any,
    *,
    root: Path = JOB_ROOT,
) -> dict[str, Any]:
    paths = _variant_paths(slug, root=root)
    normalized = _normalize_source(content)
    with _studio_lock(root):
        if not paths.source.is_file():
            raise FileNotFoundError("The selected CV source file is missing.")
        current = _normalize_source(paths.source.read_text(encoding="utf-8"))
        changed = current != normalized
        state_root = root / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".cv-studio-", dir=state_root) as temporary:
            transaction_root = Path(temporary)
            prepared = _build_variant_files(paths, normalized, transaction_root)
            version = _snapshot_current(paths, "before_save") if changed else None
            _commit_files(
                paths,
                prepared,
                include_source=changed,
                transaction_root=transaction_root,
            )
        return {
            "changed": changed,
            "saved_version": version,
            "document": get_document(slug, root=root),
            "build": _build_status(paths),
        }


def rebuild_variant(slug: str, *, root: Path = JOB_ROOT) -> dict[str, Any]:
    paths = _variant_paths(slug, root=root)
    with _studio_lock(root):
        if not paths.source.is_file():
            raise FileNotFoundError("The selected CV source file is missing.")
        content = _normalize_source(paths.source.read_text(encoding="utf-8"))
        state_root = root / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".cv-studio-", dir=state_root) as temporary:
            transaction_root = Path(temporary)
            prepared = _build_variant_files(paths, content, transaction_root)
            _commit_files(
                paths,
                prepared,
                include_source=False,
                transaction_root=transaction_root,
            )
        return {
            "changed": False,
            "document": get_document(slug, root=root),
            "build": _build_status(paths),
        }


def restore_version(
    slug: str,
    version_id: str,
    *,
    root: Path = JOB_ROOT,
) -> dict[str, Any]:
    paths = _variant_paths(slug, root=root)
    if not paths.source.is_file():
        raise FileNotFoundError("The selected CV source file is missing.")
    with _studio_lock(root):
        payload = _read_version(paths, version_id)
        restored = _normalize_source(payload["content"])
        current = _normalize_source(paths.source.read_text(encoding="utf-8"))
        changed = current != restored
        state_root = root / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".cv-studio-", dir=state_root) as temporary:
            transaction_root = Path(temporary)
            prepared = _build_variant_files(paths, restored, transaction_root)
            version = _snapshot_current(paths, "before_restore") if changed else None
            _commit_files(
                paths,
                prepared,
                include_source=changed,
                transaction_root=transaction_root,
            )
        return {
            "changed": changed,
            "restored_version": version_id,
            "saved_version": version,
            "document": get_document(slug, root=root),
            "build": _build_status(paths),
        }


def compare_with_opportunity(slug: str, opportunity_id: str) -> dict[str, Any]:
    _variant_paths(slug)
    if not OPPORTUNITY_ID_RE.fullmatch(opportunity_id):
        raise ValueError("Choose a valid opportunity.")
    opportunity = get_opportunity(opportunity_id)
    if opportunity is None:
        raise FileNotFoundError("The selected opportunity was not found.")
    body = clean_opportunity_text(opportunity.description)
    parsed_job = {
        "title": opportunity.title,
        "company": opportunity.company,
        "url": opportunity.source_url,
        "source": opportunity.source,
        "job_id": opportunity.opportunity_id,
        "body": body,
        "job_file": None,
        "title_boost_region": f"{opportunity.title} {opportunity.company}".lower(),
    }
    profiles = load_profiles()
    result = match_job_to_variants(parsed_job, profiles)
    ranked = list(result["variants_ranked"])
    selected = next((row for row in ranked if row.get("slug") == slug), None)
    if selected is None:
        raise ValueError("The selected CV is not configured for matching.")
    gaps, notes = keyword_gaps(slug, body, profiles, max_suggestions=12)
    stored_match = opportunity.match
    recommended_variant = (
        stored_match.best_variant
        if stored_match and stored_match.best_variant
        else str(result["recommendation"]["variant_slug"])
    )
    return {
        "schema": "career_cv_job_comparison_v1",
        "variant": slug,
        "opportunity": {
            "opportunity_id": opportunity.opportunity_id,
            "title": opportunity.title,
            "company": opportunity.company,
            "location": opportunity.location,
        },
        "score": float(selected.get("primary_score") or 0.0),
        "tie_break_score": float(selected.get("tie_break_score") or 0.0),
        "rank": ranked.index(selected) + 1,
        "variant_count": len(ranked),
        "keyword_hits": list(selected.get("keyword_hits") or []),
        "negative_hits": list(selected.get("negative_hits") or []),
        "keyword_gaps": [
            {"keyword": keyword, "count": count} for keyword, count in gaps
        ],
        "gap_notes": notes,
        "recommended_variant": recommended_variant,
        "is_recommended": recommended_variant == slug,
        "confidence": (
            stored_match.confidence
            if stored_match and stored_match.confidence
            else str(result["recommendation"]["confidence"])
        ),
    }


def _stdin_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("CV Studio input must be a JSON object.")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe local CV Studio helper.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for command in ("get", "save", "rebuild"):
        action = sub.add_parser(command)
        action.add_argument("--variant", required=True, choices=tuple(_VARIANT_FILES))
    restore = sub.add_parser("restore")
    restore.add_argument("--variant", required=True, choices=tuple(_VARIANT_FILES))
    restore.add_argument("--version-id", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--variant", required=True, choices=tuple(_VARIANT_FILES))
    compare.add_argument("--opportunity-id", required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.cmd == "get":
        return get_document(args.variant)
    if args.cmd == "save":
        return save_and_rebuild(args.variant, _stdin_payload().get("content"))
    if args.cmd == "rebuild":
        return rebuild_variant(args.variant)
    if args.cmd == "restore":
        return restore_version(args.variant, args.version_id)
    if args.cmd == "compare":
        return compare_with_opportunity(args.variant, args.opportunity_id)
    raise ValueError("Unsupported CV Studio action.")


def main() -> int:
    try:
        data = _run(_build_parser().parse_args())
        print(helper_json({"ok": True, "data": data}))
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(helper_json({"ok": False, "error": str(exc)}))
        return 1
    except Exception:
        print(helper_json({"ok": False, "error": "The CV Studio action failed safely."}))
        return 1


if __name__ == "__main__":
    from career_job_search.core.entrypoint import entry
    from career_job_search.core.schema import CV_STUDIO_SCHEMA

    entry(CV_STUDIO_SCHEMA, main)
