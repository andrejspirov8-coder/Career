from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest

from opportunity_alerts import (
    AlertPayloadError,
    load_alert_payloads,
    opportunities_from_alert,
)
from opportunity_models import OpportunitySourceKind

NOW = datetime(2026, 7, 8, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("source", "url", "expected_source", "expected_native_id"),
    [
        (
            "CVBankas",
            "https://www.cvbankas.lt/operations-manager-vilniuje/1-123456",
            "cvbankas",
            "123456",
        ),
        (
            "CV-Online",
            "https://www.cvonline.lt/en/vacancy/987654",
            "cvonline",
            "987654",
        ),
        (
            "Work in Lithuania",
            "https://jobs.workinlithuania.com/job/customer-operations-abc123",
            "workinlithuania",
            "customer-operations-abc123",
        ),
        (
            "LinkedIn",
            "https://www.linkedin.com/jobs/view/4567890123/?trackingId=private",
            "linkedin",
            "4567890123",
        ),
        (
            "LinkedIn Jobs",
            "https://uk.linkedin.com/jobs/view/4567890123/",
            "linkedin",
            "4567890123",
        ),
    ],
)
def test_structured_alert_link_normalizes_supported_sources(
    source: str,
    url: str,
    expected_source: str,
    expected_native_id: str,
) -> None:
    result = opportunities_from_alert(
        {
            "message_id": "gmail-message-1",
            "source": source,
            "received_at": "2026-07-08T07:30:00+00:00",
            "subject": "New jobs",
            "body": "A long email body that must not be persisted.",
            "links": [
                {
                    "url": url,
                    "title": "Customer Operations Manager",
                    "company": "Example UAB",
                    "location": "Vilnius",
                    "salary": "3000-4000 EUR gross",
                    "snippet": "Lead a customer operations team and improve service processes.",
                }
            ],
        },
        now=NOW,
    )

    assert result.errors == []
    assert result.messages_processed == 1
    assert len(result.opportunities) == 1
    row = result.opportunities[0]
    assert row.source == expected_source
    assert row.source_kind == OpportunitySourceKind.JOB_ALERT
    assert row.native_source_id == expected_native_id
    assert row.title == "Customer Operations Manager"
    assert row.company == "Example UAB"
    assert row.location == "Vilnius"
    assert row.salary_text == "3000-4000 EUR gross"
    assert row.live_status == "live"
    assert row.live_check_method == "official_job_alert"
    assert "long email body" not in row.description
    assert row.description.startswith("Lead a customer operations team")
    assert "gmail:gmail-message-1" in row.evidence.source_facts


def test_multiple_jobs_use_message_and_native_job_identity() -> None:
    result = opportunities_from_alert(
        {
            "message_id": "gmail-digest-1",
            "source": "LinkedIn",
            "received_at": "2026-07-08T08:00:00+00:00",
            "subject": "2 new jobs in Vilnius",
            "body": "",
            "links": [
                {
                    "url": "https://www.linkedin.com/jobs/view/1001",
                    "title": "Operations Lead",
                    "company": "Alpha",
                    "location": "Vilnius",
                },
                {
                    "url": "https://www.linkedin.com/jobs/view/1002",
                    "title": "Process Manager",
                    "company": "Beta",
                    "location": "Remote EU",
                },
            ],
        },
        now=NOW,
    )

    assert [row.native_source_id for row in result.opportunities] == ["1001", "1002"]
    assert len({row.canonical_identity for row in result.opportunities}) == 2


def test_recent_official_alert_is_live_but_old_alert_is_unverified() -> None:
    payload = {
        "message_id": "gmail-old-1",
        "source": "CVBankas",
        "received_at": "2026-07-01T08:00:00+00:00",
        "subject": "Old alert",
        "body": "",
        "links": [
            {
                "url": "https://www.cvbankas.lt/role/1-222",
                "title": "Store Manager",
                "company": "Retail UAB",
                "location": "Vilnius",
            }
        ],
    }

    row = opportunities_from_alert(payload, now=NOW).opportunities[0]

    assert row.live_status == "unverified"
    assert row.live_check_method == "official_job_alert"
    assert "needs_live_verification" in row.evidence.risk_flags


def test_import_keeps_only_short_matching_snippet() -> None:
    result = opportunities_from_alert(
        {
            "message_id": "gmail-private-1",
            "source": "CV-Online",
            "received_at": "2026-07-08T08:00:00+00:00",
            "subject": "Private digest",
            "body": "private mailbox content " * 200,
            "links": [
                {
                    "url": "https://www.cvonline.lt/en/vacancy/444",
                    "title": "Business Process Lead",
                    "company": "Example",
                    "location": "Vilnius, hybrid",
                    "snippet": "process improvement " * 200,
                }
            ],
        },
        now=NOW,
    )

    assert len(result.opportunities[0].description) <= 1000
    assert "private mailbox content" not in result.opportunities[0].description


def test_invalid_or_unsupported_links_are_reported_without_stopping_message() -> None:
    result = opportunities_from_alert(
        {
            "message_id": "gmail-mixed-1",
            "source": "LinkedIn",
            "received_at": "2026-07-08T08:00:00+00:00",
            "subject": "Mixed links",
            "body": "",
            "links": [
                {"url": "https://tracking.example.com/click/1", "title": "Tracking"},
                {
                    "url": "https://www.linkedin.com/jobs/view/555",
                    "title": "Operations Manager",
                    "company": "Example",
                    "location": "Vilnius",
                },
            ],
        },
        now=NOW,
    )

    assert len(result.opportunities) == 1
    assert len(result.errors) == 1
    assert "unsupported job URL" in result.errors[0]


def test_missing_required_message_fields_raise_clear_error() -> None:
    with pytest.raises(AlertPayloadError, match="message_id"):
        opportunities_from_alert(
            {
                "source": "CVBankas",
                "received_at": "2026-07-08T08:00:00+00:00",
                "links": [],
            },
            now=NOW,
        )


def test_load_alert_payloads_reads_ndjson_and_reports_line_number() -> None:
    stream = io.StringIO(
        '{"message_id":"one","source":"LinkedIn","received_at":"2026-07-08T08:00:00Z","links":[]}\n'
        "\n"
        '{"message_id":"two","source":"CVBankas","received_at":"2026-07-08T08:00:00Z","links":[]}\n'
    )

    payloads = load_alert_payloads(stream)

    assert [payload["message_id"] for payload in payloads] == ["one", "two"]

    with pytest.raises(AlertPayloadError, match="line 2"):
        load_alert_payloads(io.StringIO('{"message_id":"ok"}\nnot-json\n'))


def test_plain_string_link_uses_subject_and_body_fallback() -> None:
    result = opportunities_from_alert(
        {
            "message_id": "gmail-fallback-1",
            "source": "Work in Lithuania",
            "received_at": "2026-07-08T08:00:00+00:00",
            "subject": "Senior Service Delivery Manager @Telia",
            "body": "Vilnius, Remote job\n3760 - 5000 EUR gross",
            "links": [
                "https://jobs.workinlithuania.com/job/senior-service-delivery-manager-77"
            ],
        },
        now=NOW,
    )

    row = result.opportunities[0]
    assert row.title == "Senior Service Delivery Manager"
    assert row.company == "Telia"
    assert row.location == "Vilnius, Remote job"
    assert row.salary_text == "3760 - 5000 EUR gross"
    assert row.remote_policy == "Remote"
