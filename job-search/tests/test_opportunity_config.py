from __future__ import annotations

import pytest

from career_job_search.opportunities.config_validation import (
    canonicalise_opportunities_config,
    load_and_validate_config,
)


def source_config(name: str, block: dict[str, object]) -> dict[str, object]:
    return {"opportunities": {"sources": {name: block}}}


def test_example_config_is_local_safe() -> None:
    config = load_and_validate_config("config/opportunities.example.yaml")
    enabled = {
        name
        for name, block in config["opportunities"]["sources"].items()
        if block.get("enabled")
    }
    assert enabled == {"inbox"}


def test_known_broken_artifact_is_rejected() -> None:
    with pytest.raises((ValueError, FileNotFoundError)):
        load_and_validate_config("config/opportunities.yaml.new")


def test_string_queries_are_rejected_with_path() -> None:
    with pytest.raises(ValueError, match=r"cvonline_public_search\.queries"):
        canonicalise_opportunities_config(
            source_config(
                "cvonline_public_search",
                {
                    "enabled": True,
                    "base_url": "https://www.cvonline.lt/lt/search",
                    "queries": "manager",
                },
            )
        )


def test_enabled_search_requires_non_empty_queries() -> None:
    with pytest.raises(ValueError, match=r"cvonline_public_search\.queries"):
        canonicalise_opportunities_config(
            source_config(
                "cvonline_public_search",
                {
                    "enabled": True,
                    "base_url": "https://www.cvonline.lt/lt/search",
                    "queries": [],
                },
            )
        )


def test_plain_string_links_are_rejected() -> None:
    with pytest.raises(ValueError, match=r"job_board\.links"):
        canonicalise_opportunities_config(
            source_config(
                "job_board", {"enabled": True, "links": ["https://example.com"]}
            )
        )


def test_unknown_nested_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match=r"inbox\.unexpected"):
        canonicalise_opportunities_config(
            source_config("inbox", {"enabled": True, "unexpected": True})
        )


def test_source_alias_collision_is_rejected() -> None:
    raw = {"opportunities": {"sources": {"uzt": {}, "uzt_open_data": {}}}}
    with pytest.raises(ValueError, match=r"uzt.*uzt_open_data"):
        canonicalise_opportunities_config(raw)


def test_field_alias_collision_is_rejected() -> None:
    raw = source_config(
        "cvmarket_rss",
        {
            "enabled": False,
            "rss_url": "https://example.com/a",
            "feed_url": "https://example.com/b",
        },
    )
    with pytest.raises(ValueError, match=r"rss_url.*feed_url"):
        canonicalise_opportunities_config(raw)


def test_invalid_search_url_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"cvonline_public_search\.base_url"):
        canonicalise_opportunities_config(
            source_config(
                "cvonline_public_search",
                {
                    "enabled": True,
                    "base_url": "https://www.cvonline.lt",
                    "queries": ["manager"],
                },
            )
        )


def test_aliases_return_canonical_runtime_shape() -> None:
    config = canonicalise_opportunities_config(
        {
            "opportunities": {
                "sources": {
                    "uzt": {"enabled": False},
                    "work_in_lithuania": {"enabled": False},
                    "cvmarket_rss": {"rss_url": "https://example.com/rss"},
                }
            }
        }
    )
    sources = config["opportunities"]["sources"]
    assert "uzt_open_data" in sources
    assert "workinlithuania_public_search" in sources
    assert sources["cvmarket_rss"]["feed_url"] == "https://example.com/rss"
