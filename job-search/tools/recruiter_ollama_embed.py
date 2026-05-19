"""Ollama embedding blend for CV matching (nomic-embed-text)."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from matching_lib import PROFILES_PATH
from recruiter_ollama_client import embeddings_client, llm_cfg

CV_DIR = Path(__file__).resolve().parent.parent / "cv"


def embed_enabled(full_cfg: dict[str, Any]) -> bool:
    block = llm_cfg(full_cfg)
    if not block.get("enabled"):
        return False
    embed = block.get("embed") or {}
    return bool(embed.get("enabled", False))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@lru_cache(maxsize=16)
def _variant_text(slug: str) -> str:
    if not PROFILES_PATH.is_file():
        return slug
    raw = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8")) or {}
    block = (raw.get("variants") or {}).get(slug) or {}
    if not isinstance(block, dict):
        return slug
    parts = [slug]
    parts.extend(str(x) for x in (block.get("target_titles") or [])[:8])
    parts.extend(str(x) for x in (block.get("keywords") or [])[:24])
    md = CV_DIR / str(block.get("markdown") or "")
    if md.is_file():
        parts.append(md.read_text(encoding="utf-8")[:1200])
    return " ".join(parts)


def cv_embedding_score(
    profile_text: str, variant_slug: str, full_cfg: dict[str, Any]
) -> float | None:
    if not embed_enabled(full_cfg) or not profile_text.strip():
        return None
    try:
        emb = embeddings_client(full_cfg)
        vec_p = emb.embed_query(profile_text[:2000])
        vec_v = emb.embed_query(_variant_text(variant_slug))
        sim = _cosine(vec_p, vec_v)
        return max(0.0, min(100.0, sim * 100.0))
    except Exception:
        return None


def blend_cv_score(
    keyword_score: float, profile_text: str, variant_slug: str, full_cfg: dict[str, Any]
) -> float:
    embed = cv_embedding_score(profile_text, variant_slug, full_cfg)
    if embed is None:
        return keyword_score
    w = float((llm_cfg(full_cfg).get("embed") or {}).get("cv_blend_weight", 0.3))
    w = max(0.0, min(1.0, w))
    return round((1.0 - w) * keyword_score + w * embed, 4)
