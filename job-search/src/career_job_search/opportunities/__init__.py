"""Opportunity discovery and lifecycle services."""

from .normalization import (
    canonical_linkedin_job_url,
    infer_remote_policy,
    linkedin_job_id_from_url,
)

__all__ = [
    "canonical_linkedin_job_url",
    "infer_remote_policy",
    "linkedin_job_id_from_url",
]
