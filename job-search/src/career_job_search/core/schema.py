"""JSON Schema definitions for Python helper contracts (envelope + data shapes)."""

from __future__ import annotations

from typing import Any

HELPER_ENVELOPE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "PythonHelperEnvelopeV1",
    "type": "object",
    "properties": {
        "schema": {"const": "career_python_helper_v1"},
        "ok": {"type": "boolean"},
        "data": {"type": "object"},
        "error": {"type": "string"},
    },
    "required": ["schema"],
}


AUTOMATION_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AutomationOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "career_automation_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "settings": {
            "type": "object",
            "required": ["schedule_enabled", "schedule_time", "timezone", "updated_at"],
            "properties": {
                "schedule_enabled": {"type": "boolean"},
                "schedule_time": {
                    "type": "string",
                    "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$",
                },
                "timezone": {"type": "string"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        },
        "worker": {
            "type": "object",
            "properties": {
                "online": {"type": "boolean"},
                "status": {"type": "string"},
                "mode": {"type": ["string", "null"]},
                "started_at": {"type": ["string", "null"], "format": "date-time"},
                "heartbeat_at": {"type": ["string", "null"], "format": "date-time"},
                "age_seconds": {"type": ["number", "null"]},
            },
        },
        "counts": {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        },
        "active_runs": {"type": "array"},
        "recent_runs": {"type": "array"},
        "source_health": {
            "type": "object",
            "properties": {
                "overall_status": {
                    "type": "string",
                    "enum": ["healthy", "stale", "attention", "failed", "not_run"],
                },
                "last_checked_at": {"type": ["string", "null"], "format": "date-time"},
                "age_hours": {"type": ["number", "null"]},
                "message": {"type": "string"},
                "sources": {"type": "array"},
            },
        },
        "available_actions": {"type": "array", "items": {"type": "string"}},
        "safety": {
            "type": "object",
            "properties": {
                "scheduled_linkedin_enabled": {"type": "boolean"},
                "live_linkedin_dispatch_enabled": {"type": "boolean"},
                "message": {"type": "string"},
            },
        },
    },
    "required": [
        "schema",
        "generated_at",
        "settings",
        "worker",
        "counts",
        "active_runs",
        "recent_runs",
        "source_health",
        "available_actions",
        "safety",
    ],
}


OPPORTUNITY_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "OpportunityOverview",
    "type": "object",
    "properties": {
        "schema": {
            "type": "string",
            "enum": [
                "opportunity_dashboard_overview_v1",
                "opportunity_dashboard_overview_v2",
            ],
        },
        "generated_at": {"type": "string", "format": "date-time"},
        "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
        "funnel": {"type": "object", "additionalProperties": {"type": "integer"}},
        "pipeline": {"type": "object", "additionalProperties": {"type": "integer"}},
        "queues": {"type": "object"},
        "safe_actions": {"type": "array", "items": {"type": "string"}},
        "search_profile": {
            "type": "object",
            "properties": {
                "daily_queue_size": {"type": "integer"},
                "updated_at": {"type": "string"},
            },
        },
        "helperError": {"type": ["string", "null"]},
    },
    "required": [
        "schema",
        "generated_at",
        "counts",
        "funnel",
        "pipeline",
        "queues",
        "safe_actions",
    ],
}


RECRUITER_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "RecruiterOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "recruiter_dashboard_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "queue": {"type": "array"},
        "saved_views": {"type": "object"},
        "metrics": {"type": "object"},
        "live_dispatch": {"type": "object"},
        "operators": {"type": "array"},
    },
    "required": [
        "schema",
        "generated_at",
        "queue",
        "saved_views",
        "metrics",
        "live_dispatch",
        "operators",
    ],
}


CV_CATALOGUE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CvCatalogue",
    "type": "object",
    "properties": {
        "schema": {"const": "cv_catalogue_v1"},
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "slug",
                    "name",
                    "language",
                    "focus",
                    "display_order",
                    "source_filename",
                    "pdf_stem",
                    "target_titles",
                    "keywords",
                    "negative_keywords",
                ],
                "properties": {
                    "slug": {"type": "string"},
                    "name": {"type": "string"},
                    "language": {"type": "string"},
                    "focus": {"type": "string"},
                    "display_order": {"type": "integer"},
                    "source_filename": {"type": "string"},
                    "pdf_stem": {"type": "string"},
                    "target_titles": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "negative_keywords": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    "required": ["schema", "variants"],
}


CV_STUDIO_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CvStudioStatus",
    "type": "object",
    "properties": {
        "schema": {"const": "career_cv_studio_status_v1"},
        "variant": {"type": "string"},
        "source": {"type": "string"},
        "sections": {"type": "array", "items": {"type": "string"}},
        "unsaved_changes": {"type": "boolean"},
        "visual_pdf_exists": {"type": "boolean"},
        "ats_pdf_exists": {"type": "boolean"},
        "canva_text_exists": {"type": "boolean"},
        "history": {"type": "array"},
    },
    "required": [
        "schema",
        "variant",
        "source",
        "sections",
        "unsaved_changes",
        "visual_pdf_exists",
        "ats_pdf_exists",
        "canva_text_exists",
        "history",
    ],
}


LOCAL_DRAFTING_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "LocalDraftingStatus",
    "type": "object",
    "properties": {
        "schema": {"const": "career_local_drafting_status_v1"},
        "enabled": {"type": "boolean"},
        "model": {"type": ["string", "null"]},
        "url": {"type": "string"},
    },
    "required": ["schema", "enabled", "model", "url"],
}


NOTIFICATIONS_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "NotificationOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "career_notification_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "items": {"type": "array"},
        "unread_count": {"type": "integer"},
        "settings": {"type": "object"},
    },
    "required": ["schema", "generated_at", "items", "unread_count", "settings"],
}


SEARCH_PREFERENCES_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "SearchPreferences",
    "type": "object",
    "properties": {
        "schema": {"const": "career_search_preferences_v1"},
        "daily_queue_size": {"type": "integer", "minimum": 1, "maximum": 50},
        "work_arrangements": {"type": "array", "items": {"type": "string"}},
        "role_tracks": {"type": "array", "items": {"type": "string"}},
        "excluded_companies": {"type": "array", "items": {"type": "string"}},
        "excluded_keywords": {"type": "array", "items": {"type": "string"}},
        "min_fit_score": {"type": "number", "minimum": 0, "maximum": 100},
        "locations": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}},
        "updated_at": {"type": "string", "format": "date-time"},
    },
    "required": [
        "schema",
        "daily_queue_size",
        "work_arrangements",
        "role_tracks",
        "excluded_companies",
        "excluded_keywords",
        "min_fit_score",
        "locations",
        "sources",
        "updated_at",
    ],
}


WORKSPACE_CONTROLS_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "WorkspaceControls",
    "type": "object",
    "properties": {
        "schema": {"const": "career_workspace_controls_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "dashboard_runtime": {"type": "object"},
        "keychain": {"type": "object"},
        "startup": {"type": "object"},
        "backup": {"type": "object"},
    },
    "required": [
        "schema",
        "generated_at",
        "dashboard_runtime",
        "keychain",
        "startup",
        "backup",
    ],
}


ANALYTICS_OVERVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AnalyticsOverview",
    "type": "object",
    "properties": {
        "schema": {"const": "career_analytics_overview_v1"},
        "generated_at": {"type": "string", "format": "date-time"},
        "funnel": {"type": "object"},
        "data_quality": {"type": "object"},
        "by_source": {"type": "array"},
        "by_variant": {"type": "array"},
        "by_tailoring": {"type": "array"},
        "by_score": {"type": "array"},
        "outcome_history": {"type": "array"},
        "weekly_trend": {"type": "array"},
        "recruiters": {"type": "array"},
        "recommendations": {"type": "array"},
    },
    "required": [
        "schema",
        "generated_at",
        "funnel",
        "data_quality",
        "by_source",
        "by_variant",
        "by_tailoring",
        "by_score",
        "outcome_history",
        "weekly_trend",
        "recruiters",
        "recommendations",
    ],
}


__all__ = [
    "ANALYTICS_OVERVIEW_SCHEMA",
    "AUTOMATION_OVERVIEW_SCHEMA",
    "CV_CATALOGUE_SCHEMA",
    "CV_STUDIO_SCHEMA",
    "HELPER_ENVELOPE_SCHEMA",
    "LOCAL_DRAFTING_SCHEMA",
    "NOTIFICATIONS_OVERVIEW_SCHEMA",
    "OPPORTUNITY_OVERVIEW_SCHEMA",
    "RECRUITER_OVERVIEW_SCHEMA",
    "SEARCH_PREFERENCES_SCHEMA",
    "WORKSPACE_CONTROLS_SCHEMA",
]
