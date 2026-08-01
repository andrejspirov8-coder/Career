from __future__ import annotations

import json
import subprocess
from pathlib import Path

HELPER = "src/career_job_search/cvs/profiles_helper.py"
PROFILES_PATH = Path("cv/variant_profiles.yaml")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", HELPER, *args],
        capture_output=True, text=True, cwd=".",
    )


def test_show_returns_envelope():
    result = _run("show")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload.get("schema") == "career_python_helper_v1"
    assert payload.get("ok") is True
    assert "data" in payload


def test_show_contains_variants():
    result = _run("show")
    payload = json.loads(result.stdout)
    data = payload["data"]
    assert "variants" in data
    assert len(data["variants"]) >= 6


def test_show_variant_has_expected_fields():
    result = _run("show")
    payload = json.loads(result.stdout)
    variant = payload["data"]["variants"].get("luxury-retail", {})
    assert variant.get("name") == "Luxury Retail"
    assert "target_titles" in variant
    assert "keywords" in variant
    assert "negative_keywords" in variant
    assert "focus" in variant


def test_save_and_show_round_trip():
    backup = PROFILES_PATH.read_text(encoding="utf-8") if PROFILES_PATH.exists() else None

    try:
        minimal = {
            "variants": {
                "test-variant": {
                    "name": "Test Variant",
                    "language": "English",
                    "focus": "Test focus description",
                    "display_order": 1,
                    "pdf_stem": "test-cv",
                    "markdown": "test-cv.md",
                    "target_titles": ["Role One", "Role Two"],
                    "keywords": ["keyword1", "keyword2"],
                    "negative_keywords": ["avoid"],
                },
            },
        }
        result = _run("save", "--json", json.dumps(minimal))
        assert result.returncode == 0, f"save failed: {result.stderr}"
        payload = json.loads(result.stdout)
        assert payload.get("ok") is True

        verify = _run("show")
        vpayload = json.loads(verify.stdout)
        variants = vpayload["data"]["variants"]
        assert "test-variant" in variants
        assert variants["test-variant"]["name"] == "Test Variant"
        assert variants["test-variant"]["focus"] == "Test focus description"
        assert variants["test-variant"]["target_titles"] == ["Role One", "Role Two"]
        assert variants["test-variant"]["keywords"] == ["keyword1", "keyword2"]
        assert variants["test-variant"]["negative_keywords"] == ["avoid"]
    finally:
        if backup is not None:
            PROFILES_PATH.write_text(backup, encoding="utf-8")


def test_save_rejects_invalid_json():
    result = _run("save", "--json", "bad")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload.get("ok") is False
    assert "error" in payload


def test_save_rejects_non_object():
    result = _run("save", "--json", '"string"')
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload.get("ok") is False
    assert "error" in payload
