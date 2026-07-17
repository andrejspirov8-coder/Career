from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

import cv_studio
from build_cv_pdf import build_variant

SLUG = "business-process-operations"
OLD_SOURCE = """# Andrej Spirov

contact@example.com | Vilnius

---

## Target Title

Operations Manager

---

## Professional Summary

Operations leader with reporting experience.

---

## Core Skills

- Operations
- Reporting

---

## Languages

- English

---

## Experience

### Area Manager

- Led five stores.
"""
NEW_SOURCE = OLD_SOURCE.replace(
    "Operations leader with reporting experience.",
    "Customer operations leader with reporting and implementation experience.",
)


def _prepare_workspace(root: Path) -> cv_studio.VariantPaths:
    paths = cv_studio._variant_paths(SLUG, root=root)
    paths.source.parent.mkdir(parents=True)
    paths.visual_pdf.parent.mkdir(parents=True)
    paths.canva_text.parent.mkdir(parents=True)
    paths.source.write_text(OLD_SOURCE, encoding="utf-8")
    paths.visual_pdf.write_bytes(b"old visual")
    paths.ats_pdf.write_bytes(b"old ats")
    paths.canva_text.write_text("old canva", encoding="utf-8")
    return paths


def _fake_build(
    paths: cv_studio.VariantPaths,
    content: str,
    transaction_root: Path,
) -> dict[str, Path]:
    prepared = {
        "source": transaction_root / paths.source.name,
        "visual": transaction_root / paths.visual_pdf.name,
        "ats": transaction_root / paths.ats_pdf.name,
        "canva": transaction_root / paths.canva_text.name,
    }
    prepared["source"].write_text(content, encoding="utf-8")
    prepared["visual"].write_bytes(f"visual:{content}".encode())
    prepared["ats"].write_bytes(f"ats:{content}".encode())
    prepared["canva"].write_text(f"canva:{content}", encoding="utf-8")
    return prepared


def test_save_builds_only_selected_variant_and_keeps_private_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _prepare_workspace(tmp_path)
    monkeypatch.setattr(cv_studio, "_build_variant_files", _fake_build)

    result = cv_studio.save_and_rebuild(SLUG, NEW_SOURCE, root=tmp_path)

    assert result["changed"] is True
    assert paths.source.read_text(encoding="utf-8") == NEW_SOURCE
    assert paths.visual_pdf.read_bytes().startswith(b"visual:# Andrej")
    assert not (tmp_path / "output" / "andrej-spirov-cv-it-business.pdf").exists()
    versions = result["document"]["versions"]
    assert len(versions) == 1
    version_path = (
        tmp_path / "state" / "cv_versions" / SLUG / f"{versions[0]['version_id']}.json"
    )
    payload = json.loads(version_path.read_text(encoding="utf-8"))
    assert payload["content"] == OLD_SOURCE
    assert "content" not in versions[0]
    assert stat.S_IMODE(version_path.stat().st_mode) == 0o600


def test_failed_build_leaves_source_outputs_and_history_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _prepare_workspace(tmp_path)

    def fail_build(*_args: object, **_kwargs: object) -> dict[str, Path]:
        raise RuntimeError("synthetic build failure")

    monkeypatch.setattr(cv_studio, "_build_variant_files", fail_build)

    with pytest.raises(RuntimeError, match="synthetic build failure"):
        cv_studio.save_and_rebuild(SLUG, NEW_SOURCE, root=tmp_path)

    assert paths.source.read_text(encoding="utf-8") == OLD_SOURCE
    assert paths.visual_pdf.read_bytes() == b"old visual"
    assert cv_studio.list_versions(SLUG, root=tmp_path) == []


def test_restore_keeps_the_current_source_as_another_recovery_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _prepare_workspace(tmp_path)
    monkeypatch.setattr(cv_studio, "_build_variant_files", _fake_build)
    saved = cv_studio.save_and_rebuild(SLUG, NEW_SOURCE, root=tmp_path)
    old_version = saved["document"]["versions"][0]["version_id"]

    restored = cv_studio.restore_version(SLUG, old_version, root=tmp_path)

    assert restored["restored_version"] == old_version
    assert paths.source.read_text(encoding="utf-8") == OLD_SOURCE
    assert any(
        version["reason"] == "before_restore"
        for version in restored["document"]["versions"]
    )
    with pytest.raises(ValueError, match="valid CV version"):
        cv_studio.restore_version(SLUG, "../../source", root=tmp_path)


@pytest.mark.parametrize(
    "content, message",
    [
        ("", "cannot be empty"),
        ("# Name\n", "Missing required CV section"),
        (OLD_SOURCE + "\x00", "control characters"),
    ],
)
def test_source_validation_rejects_incomplete_or_unsafe_text(
    content: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        cv_studio._normalize_source(content)


def test_comparison_rejects_untrusted_opportunity_identifiers() -> None:
    with pytest.raises(ValueError, match="valid opportunity"):
        cv_studio.compare_with_opportunity(SLUG, "../../state/opportunities.sqlite3")


def test_build_variant_accepts_only_the_fixed_variant_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[tuple[str, str]] = []

    def fake_pdf(md_path: Path, out_path: Path, *, layout: str, photo: Path | None = None) -> None:
        del md_path, photo
        built.append((out_path.name, layout))

    def fake_paste(md_path: Path, out_path: Path, *, design_hint: str | None = None) -> None:
        del md_path, design_hint
        built.append((out_path.name, "paste"))

    monkeypatch.setattr("build_cv_pdf.build_pdf", fake_pdf)
    monkeypatch.setattr("build_cv_pdf.build_canva_paste", fake_paste)

    visual, ats, paste = build_variant(SLUG)

    assert visual.name == "andrej-spirov-cv-business-process-operations.pdf"
    assert ats.name.endswith("-ats.pdf")
    assert paste.name.endswith("-canva.txt")
    assert [layout for _name, layout in built] == ["canva", "plain", "paste"]
    with pytest.raises(ValueError, match="Unknown CV variant"):
        build_variant("../../unknown")
