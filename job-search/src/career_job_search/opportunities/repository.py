"""Stable opportunity repository API with independently owned subdomains."""

from career_job_search.opportunities.repository_activity import (
    actions_for_opportunity,
    claim_deliveries,
    count_by_status,
    delivery_identity,
    get_daily_run,
    latest_daily_run,
    mark_unseen_linkedin_browser_unverified,
    mark_unseen_opportunities_expired,
    record_action,
    record_source_run,
    save_daily_run,
    undelivered_opportunities,
)
from career_job_search.opportunities.repository_db import (
    DEFAULT_OPPORTUNITY_DB,
    connect,
    init_db,
)
from career_job_search.opportunities.repository_discovery import (
    get_opportunity,
    list_opportunities,
    save_opportunity,
    upsert_opportunities,
)

__all__ = [
    "DEFAULT_OPPORTUNITY_DB",
    "actions_for_opportunity",
    "claim_deliveries",
    "connect",
    "count_by_status",
    "delivery_identity",
    "get_daily_run",
    "get_opportunity",
    "init_db",
    "latest_daily_run",
    "list_opportunities",
    "mark_unseen_linkedin_browser_unverified",
    "mark_unseen_opportunities_expired",
    "record_action",
    "record_source_run",
    "save_daily_run",
    "save_opportunity",
    "undelivered_opportunities",
    "upsert_opportunities",
]
