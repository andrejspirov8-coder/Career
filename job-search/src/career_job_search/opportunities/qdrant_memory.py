"""Qdrant-backed career memory for opportunity matching and learning."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

QDRANT_HOST = "http://127.0.0.1:6333"
COLLECTION_NAME = "career_memory"
EMBEDDING_DIM = 768

EMBEDDING_URL = "http://127.0.0.1:1234/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5"


def _get_client() -> Any:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    client = QdrantClient(url=QDRANT_HOST)
    existing = client.get_collections()
    names = [c.name for c in existing.collections]
    if COLLECTION_NAME not in names:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info("Created collection '%s'", COLLECTION_NAME)
    return client


def _embed(text: str) -> list[float]:
    try:
        import httpx

        resp = httpx.post(
            EMBEDDING_URL,
            json={"model": EMBEDDING_MODEL, "input": [text]},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("Embedding error: %s %s", resp.status_code, resp.text[:200])
            return []
        return resp.json()["data"][0]["embedding"]
    except ImportError:
        import json
        import urllib.request

        data = json.dumps({"model": EMBEDDING_MODEL, "input": [text]}).encode()
        req = urllib.request.Request(  # noqa: S310
            EMBEDDING_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                return json.loads(resp.read())["data"][0]["embedding"]
        except Exception as exc:
            logger.warning("Embedding error (urllib): %s", exc)
            return []
    except Exception as exc:
        logger.warning("Embedding error (httpx): %s", exc)
        return []


def _point_id(opportunity_id: str) -> str:
    return hashlib.md5(opportunity_id.encode()).hexdigest()  # noqa: S324


def index_opportunity(
    opportunity: Any, fit_score: float = 0.0, outcome: str = ""
) -> bool:
    try:
        from qdrant_client.models import PointStruct

        client = _get_client()
        text = (
            f"{opportunity.title} {opportunity.company} "
            f"{opportunity.location} {opportunity.description}"
        )[:2000]
        vector = _embed(text)
        if not vector:
            return False
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=_point_id(opportunity.opportunity_id),
                    vector=vector,
                    payload={
                        "opportunity_id": opportunity.opportunity_id,
                        "title": opportunity.title,
                        "company": opportunity.company,
                        "location": opportunity.location,
                        "source_url": opportunity.source_url,
                        "source": opportunity.source,
                        "fit_score": fit_score,
                        "outcome": outcome,
                        "indexed_at": datetime.now(UTC).isoformat(),
                    },
                )
            ],
        )
        return True
    except Exception as exc:
        logger.warning("Failed to index opportunity: %s", exc)
        return False


def search_similar(opportunity: Any, limit: int = 5) -> list[dict]:
    try:
        client = _get_client()
        text = (
            f"{opportunity.title} {opportunity.company} "
            f"{opportunity.location} {opportunity.description}"
        )[:2000]
        vector = _embed(text)
        if not vector:
            return []
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=limit,
            with_payload=True,
        ).points
        return [
            {
                "opportunity_id": r.payload.get("opportunity_id", ""),
                "title": r.payload.get("title", ""),
                "company": r.payload.get("company", ""),
                "fit_score": r.payload.get("fit_score", 0.0),
                "outcome": r.payload.get("outcome", ""),
                "score": r.score,
            }
            for r in results
        ]
    except Exception as exc:
        logger.warning("Failed to search similar: %s", exc)
        return []


def record_outcome(opportunity_id: str, outcome: str) -> bool:
    try:
        client = _get_client()
        client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={"outcome": outcome},
            points=[_point_id(opportunity_id)],
        )
        return True
    except Exception as exc:
        logger.warning("Failed to record outcome: %s", exc)
        return False


def build_context_for_llm(opportunity: Any, limit: int = 3) -> str:
    similar = search_similar(opportunity, limit=limit)
    if not similar:
        return ""
    lines = ["Past similar applications:"]
    for s in similar:
        outcome = s["outcome"] or "unknown"
        lines.append(
            f"- Company: {s['company']}, Role: {s['title']} "
            f"(score: {s['fit_score']}, outcome: {outcome})"
        )
    return "\n".join(lines)


def stats() -> dict:
    try:
        client = _get_client()
        count = client.count(collection_name=COLLECTION_NAME).count
        results = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=1,
            with_payload=["indexed_at"],
        )
        last_indexed = None
        if results[0]:
            last_indexed = results[0][0].payload.get("indexed_at")
        return {"total_vectors": count, "last_indexed_at": last_indexed}
    except Exception as exc:
        logger.warning("Failed to get stats: %s", exc)
        return {"total_vectors": 0, "last_indexed_at": None}
