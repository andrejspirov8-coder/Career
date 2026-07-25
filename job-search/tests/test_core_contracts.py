from __future__ import annotations

import json

from career_job_search.core.contracts import HELPER_ENVELOPE_SCHEMA, helper_envelope, helper_json


def test_helper_envelope_adds_schema():
    payload = {"ok": True, "data": {"count": 42}}
    result = helper_envelope(payload)
    assert result["schema"] == HELPER_ENVELOPE_SCHEMA
    assert result["ok"] is True
    assert result["data"] == {"count": 42}


def test_helper_envelope_raises_on_incompatible_schema():
    payload = {"schema": "some_other_v2", "ok": True}
    try:
        helper_envelope(payload)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "incompatible" in str(exc).lower()


def test_helper_envelope_passes_matching_schema():
    payload = {"schema": HELPER_ENVELOPE_SCHEMA, "ok": True, "data": {}}
    result = helper_envelope(payload)
    assert result["schema"] == HELPER_ENVELOPE_SCHEMA


def test_helper_json_serializes_to_string():
    payload = {"ok": True, "data": {"key": "value"}}
    result = helper_json(payload)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["schema"] == HELPER_ENVELOPE_SCHEMA
    assert parsed["ok"] is True


def test_helper_json_indent_and_sort_keys():
    payload = {"ok": True, "data": {"b": 2, "a": 1}}
    result = helper_json(payload, indent=2, sort_keys=True)
    parsed = json.loads(result)
    assert list(parsed["data"].keys()) == ["a", "b"]


def test_helper_json_no_indent_by_default():
    payload = {"ok": True, "data": {}}
    result = helper_json(payload)
    assert "\n" not in result
