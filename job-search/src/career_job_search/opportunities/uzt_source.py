"""Official Lithuanian Employment Service open-data adapter."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)
from career_job_search.opportunities.sources.base import SourceDiscovery
from career_job_search.opportunities.uzt_live_source import (
    discover_uzt_live_search_source,
)

DEFAULT_FETCH_TIMEOUT_SECONDS = 20
DEFAULT_UZT_OPEN_DATA_URL = "https://get.data.gov.lt/datasets/gov/uzt/ldv/Vieta"
DEFAULT_UZT_DETAIL_URL = "https://uzt.lt/laisvos-darbo-vietos/436/skelbimas"
MAX_PUBLIC_DESCRIPTION_CHARS = 6000
SEARCH_TIMEZONE = ZoneInfo("Europe/Vilnius")

_UZT_PUBLIC_FIELDS = (
    "darbo_vietos_id",
    "ikelimo_data",
    "prelim_darbo_uzmokestis",
    "maks_darbo_uzmokestis",
    "valiuta",
    "uzmokescio_komentaras_lt",
    "profesijos_pareigybes_pav",
    "kontrakto_tipas",
    "darbo_aprasymas_lt",
    "galioja_iki",
    "darbo_vietu_skaicius",
    "darbo_vietos_sav_pav",
    "darbdavys",
    "reik_darbo_patirtis",
    "reik_kompetencijos_lt",
    "reik_gebejimai",
    "reik_issilavinimo_pav",
)


@dataclass
class UztSourceDiscovery(SourceDiscovery):
    opportunities: list[Opportunity] = field(default_factory=list)
    complete: bool = True
    status: str | None = None
    note: str = ""


def discover_uzt_open_data_source(
    config: dict[str, Any],
    *,
    fetcher: Callable[..., Any],
    live_fetcher: Callable[..., str] | None = None,
    now: datetime | None = None,
) -> UztSourceDiscovery:
    """Read public vacancies without requesting personal contact columns."""

    block = _source_cfg(config, "uzt_open_data")
    if not _enabled(block, default=False):
        return UztSourceDiscovery()

    timeout = int(block.get("network_timeout_seconds") or DEFAULT_FETCH_TIMEOUT_SECONDS)
    api_url = str(block.get("api_url") or DEFAULT_UZT_OPEN_DATA_URL).strip()
    municipality = str(block.get("municipality") or "Vilniaus miesto sav.").strip()
    max_records = _non_negative_int(
        block.get("max_records", 500),
        "max_records",
    )
    if max_records == 0:
        raise ValueError("max_records must be greater than zero.")
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    local_search_date = clock.astimezone(SEARCH_TIMEZONE).date().isoformat()
    query = urlencode(
        [
            ("ar_aktuali_siandien", json.dumps("1")),
            ("darbo_vietos_sav_pav", json.dumps(municipality)),
            ("galioja_iki._ge", json.dumps(local_search_date)),
            ("_sort", "-ikelimo_data"),
            ("_limit", str(max_records + 1)),
            ("_select", ",".join(_UZT_PUBLIC_FIELDS)),
        ]
    )
    try:
        payload = fetcher(f"{api_url}?{query}", timeout=timeout)
    except ValueError:
        raise
    except Exception as primary_error:
        if not bool(block.get("live_fallback_enabled", True)) or not live_fetcher:
            raise
        try:
            live_result = discover_uzt_live_search_source(
                block,
                fetcher=live_fetcher,
                now=clock,
            )
        except ValueError:
            raise
        except Exception as fallback_error:
            raise primary_error from fallback_error
        if live_result.status is None and live_result.opportunities:
            note = (
                "Employment Service open data was unavailable. Current official "
                "public-search fallback supplied "
                f"{len(live_result.opportunities)} vacancy summaries."
            )
            if live_result.note:
                note = f"{note} {live_result.note}"
            return UztSourceDiscovery(
                opportunities=live_result.opportunities,
                complete=live_result.complete,
                status=None,
                note=note,
            )
        raise primary_error
    raw_rows = _payload_rows(payload)
    complete = len(raw_rows) <= max_records
    selected = raw_rows[:max_records]
    latest_update = _latest_iso_date(
        str(row.get("ikelimo_data") or "") for row in selected
    )
    max_age_days = max(1, int(block.get("max_feed_age_days") or 3))
    status, note = _feed_freshness(
        latest_update,
        now=clock,
        max_age_hours=max_age_days * 24,
        source_label="Employment Service open data",
    )
    stale = status == "stale"
    opportunities = [
        opportunity
        for row in selected
        if (opportunity := _row_to_opportunity(row, stale=stale)) is not None
    ]
    if stale and bool(block.get("live_fallback_enabled", True)) and live_fetcher:
        try:
            live_result = discover_uzt_live_search_source(
                block,
                fetcher=live_fetcher,
                now=clock,
            )
        except ValueError:
            raise
        except Exception:
            note = (
                f"{note} Official public-search fallback failed safely; "
                "stale open-data rows remain verification-only."
            )
        else:
            if live_result.status is None and live_result.opportunities:
                fallback_note = (
                    f"{note} Current official public-search fallback supplied "
                    f"{len(live_result.opportunities)} vacancy summaries."
                )
                if live_result.note:
                    fallback_note = f"{fallback_note} {live_result.note}"
                return UztSourceDiscovery(
                    opportunities=live_result.opportunities,
                    complete=live_result.complete,
                    status=None,
                    note=fallback_note,
                )
            note = (
                f"{note} Official public-search fallback did not provide "
                "a current page."
            )
    return UztSourceDiscovery(
        opportunities=opportunities,
        complete=complete,
        status=status,
        note=note,
    )


def _source_cfg(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get(name) or {}
    return block if isinstance(block, dict) else {}


def _enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("_data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _row_to_opportunity(
    row: dict[str, Any],
    *,
    stale: bool,
) -> Opportunity | None:
    native_id = str(row.get("darbo_vietos_id") or "").strip()
    title = " ".join(str(row.get("profesijos_pareigybes_pav") or "").split())
    company = " ".join(str(row.get("darbdavys") or "").split())
    if not native_id or not title or not company:
        return None

    description_parts = [
        _safe_public_job_text(str(row.get("darbo_aprasymas_lt") or "")),
        _labelled_public_fact("Sutartis", row.get("kontrakto_tipas")),
        _labelled_public_fact("Patirtis", row.get("reik_darbo_patirtis")),
        _labelled_public_fact("Kompetencijos", row.get("reik_kompetencijos_lt")),
        _labelled_public_fact("Gebėjimai", row.get("reik_gebejimai")),
        _labelled_public_fact("Išsilavinimas", row.get("reik_issilavinimo_pav")),
    ]
    description = "\n".join(part for part in description_parts if part)[
        :MAX_PUBLIC_DESCRIPTION_CHARS
    ]
    risk_flags = ["needs_live_verification"]
    if stale:
        risk_flags.append("stale_source")
    source_updated_at = str(row.get("ikelimo_data") or "").strip()
    return Opportunity(
        source="uzt_open_data",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id=native_id,
        source_url=f"{DEFAULT_UZT_DETAIL_URL}/{native_id}",
        title=title,
        company=company,
        location="Vilnius",
        description=description,
        salary_text=_salary_text(row),
        deadline=str(row.get("galioja_iki") or "").strip(),
        source_updated_at=source_updated_at,
        live_status="unverified",
        live_check_method="official_open_data",
        live_check_note=(
            "source_feed_is_stale"
            if stale
            else "open_data_record_requires_listing_verification"
        ),
        evidence=OpportunityEvidence(
            source_facts=["official_open_data:uzt", "license:CC-BY-4.0"],
            company_facts=[company],
            role_facts=[title],
            location_facts=["Vilnius"],
            risk_flags=risk_flags,
            confidence=0.55 if stale else 0.7,
        ),
    )


def _salary_text(row: dict[str, Any]) -> str:
    lower = _number_text(row.get("prelim_darbo_uzmokestis"))
    upper = _number_text(row.get("maks_darbo_uzmokestis"))
    currency = str(row.get("valiuta") or "").strip()
    comment = _safe_public_job_text(str(row.get("uzmokescio_komentaras_lt") or ""))
    if lower and upper and lower != upper:
        base = f"{lower}–{upper} {currency}".strip()
    else:
        base = f"{lower or upper} {currency}".strip()
    return " · ".join(part for part in (base, comment) if part)[:500]


def _number_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}".rstrip("0")


def _labelled_public_fact(label: str, value: Any) -> str:
    safe = _safe_public_job_text(str(value or ""))
    return f"{label}: {safe}" if safe else ""


def _safe_public_job_text(value: str) -> str:
    text = " ".join(value.split())
    text = re.sub(
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[contact removed]",
        text,
    )
    text = re.sub(
        r"(?<!\w)(?:\+370|00370|370)(?:[\s().-]*\d){8}(?!\d)",
        "[contact removed]",
        text,
    )
    text = re.sub(
        r"(?i)\b(?:cv\s+siųskite|skambinkite|susisiekite|kreipkitės)\b"
        r"[^.!?]*(?:[.!?]|$)",
        "[contact instructions removed] ",
        text,
    )
    return " ".join(text.split())


def _feed_freshness(
    updated_at: datetime | None,
    *,
    now: datetime,
    max_age_hours: int,
    source_label: str,
) -> tuple[str | None, str]:
    if updated_at is None:
        return "stale", f"{source_label} did not provide a usable update time."
    age_hours = max(
        0,
        int((now.astimezone(UTC) - updated_at.astimezone(UTC)).total_seconds() // 3600),
    )
    if age_hours > max_age_hours:
        return (
            "stale",
            f"{source_label} is {age_hours} hours old; verify listings before use.",
        )
    return None, ""


def _latest_iso_date(values: Any) -> datetime | None:
    parsed: list[datetime] = []
    for value in values:
        try:
            item = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
        if item.tzinfo is None:
            item = item.replace(tzinfo=UTC)
        parsed.append(item.astimezone(UTC))
    return max(parsed, default=None)


def _non_negative_int(value: Any, name: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer.") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return parsed
