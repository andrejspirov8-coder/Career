from __future__ import annotations

import pytest

from career_job_search.integrations.linkedin.campaign_config import (
    CAMPAIGN_CONFIG_SCHEMA_VERSION,
    load_config,
)


def test_load_config_accepts_known_schema_version(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        f"schema_version: {CAMPAIGN_CONFIG_SCHEMA_VERSION!r}\nlimits:\n  a: 1\n"
    )
    cfg = load_config(config)
    assert cfg["schema_version"] == CAMPAIGN_CONFIG_SCHEMA_VERSION
    assert cfg["limits"] == {"a": 1}


def test_load_config_rejects_unknown_schema_version(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text('schema_version: "config_v999"\n')
    with pytest.raises(
        SystemExit, match=r"Unsupported linkedin/config.yaml schema_version"
    ):
        load_config(config)


def test_load_config_accepts_missing_schema_version(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("limits:\n  a: 1\n")
    cfg = load_config(config)
    assert cfg["limits"] == {"a": 1}
