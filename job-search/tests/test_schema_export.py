from __future__ import annotations

import importlib.util
from pathlib import Path


def test_schema_module_exists():
    spec = importlib.util.spec_from_file_location(
        "schema", Path("src/career_job_search/core/schema.py")
    )
    assert spec is not None, "schema.py must exist"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "HELPER_ENVELOPE_SCHEMA")
    assert module.HELPER_ENVELOPE_SCHEMA["properties"]["schema"]["const"] == "career_python_helper_v1"