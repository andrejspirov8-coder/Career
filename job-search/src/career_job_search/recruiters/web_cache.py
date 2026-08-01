"""SQLite cache for web search results (24h TTL by default)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from career_job_search.integrations.linkedin.paths import PIPELINE_DIR
from career_job_search.recruiters.web_models import WebResearchResult, WebSearchHit

DEFAULT_CACHE_PATH = PIPELINE_DIR / "web_search_cache.sqlite"

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS searches (
    backend TEXT NOT NULL,
    query TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (backend, query)
)
"""


def _cache_path(full_cfg: dict[str, Any] | None = None) -> Path:
    if full_cfg:
        wd = full_cfg.get("web_discovery") or {}
        raw = wd.get("cache_path")
        if raw:
            p = Path(str(raw))
            return p if p.is_absolute() else PIPELINE_DIR.parent / p
    return DEFAULT_CACHE_PATH


def cache_enabled(full_cfg: dict[str, Any]) -> bool:
    wd = full_cfg.get("web_discovery") or {}
    return bool(wd.get("cache_enabled", False))


def cache_ttl_hours(full_cfg: dict[str, Any]) -> float:
    wd = full_cfg.get("web_discovery") or {}
    return float(wd.get("cache_ttl_hours") or 24)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA_SQL)
    return conn


def _serialize(result: WebResearchResult) -> str:
    payload = {
        "query": result.query,
        "backend": result.backend,
        "error": result.error,
        "hits": [
            {
                "title": h.title,
                "url": h.url,
                "snippet": h.snippet,
                "source": h.source,
            }
            for h in result.hits
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _deserialize(raw: str) -> WebResearchResult:
    data = json.loads(raw)
    hits = [
        WebSearchHit(
            title=str(h.get("title") or ""),
            url=str(h.get("url") or ""),
            snippet=str(h.get("snippet") or ""),
            source=str(h.get("source") or ""),
        )
        for h in data.get("hits") or []
    ]
    return WebResearchResult(
        query=str(data.get("query") or ""),
        hits=hits,
        backend=str(data.get("backend") or ""),
        error=str(data.get("error") or ""),
    )


def get_cached(
    query: str,
    backend: str,
    *,
    full_cfg: dict[str, Any] | None = None,
    ttl_hours: float | None = None,
    cache_path: Path | None = None,
) -> WebResearchResult | None:
    path = cache_path or _cache_path(full_cfg)
    ttl = (
        ttl_hours
        if ttl_hours is not None
        else (cache_ttl_hours(full_cfg) if full_cfg else 24.0)
    )
    cutoff = datetime.now(UTC) - timedelta(hours=ttl)
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT fetched_at, payload_json FROM searches WHERE backend=? AND query=?",
            (backend, query),
        ).fetchone()
    if not row:
        return None
    fetched_at = datetime.fromisoformat(str(row[0]))
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    if fetched_at < cutoff:
        return None
    return _deserialize(str(row[1]))


def put(
    query: str,
    backend: str,
    result: WebResearchResult,
    *,
    cache_path: Path | None = None,
    full_cfg: dict[str, Any] | None = None,
) -> None:
    path = cache_path or _cache_path(full_cfg)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    payload = _serialize(result)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO searches (backend, query, fetched_at, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(backend, query) DO UPDATE SET
                fetched_at=excluded.fetched_at,
                payload_json=excluded.payload_json
            """,
            (backend, query, now, payload),
        )
        conn.commit()
