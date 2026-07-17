"""
Shared logic for assistive job ↔ CV variant matching (no auto-submit).
Uses stdlib only by default; PyYAML is used if it is available.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # Keep Raycast usable when system Python cannot install packages.
    yaml = None

from career_job_search.core.paths import project_path

TOOLS_DIR = project_path("tools")
JOB_ROOT = project_path()
CV_DIR = JOB_ROOT / "cv"
OUTPUT_DIR = JOB_ROOT / "output"
PROFILES_PATH = CV_DIR / "variant_profiles.yaml"

TOKEN_RE = re.compile(r"[A-Za-ząčęėįšųūžĄČĘĖĮŠŲŪŽ0-9]{2,}", re.UNICODE)

# Minimal EN + LT stopwords for keyword-gap suggestions (not exhaustive).
STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "her",
        "was",
        "one",
        "our",
        "out",
        "day",
        "get",
        "has",
        "him",
        "his",
        "how",
        "its",
        "may",
        "new",
        "now",
        "old",
        "see",
        "two",
        "way",
        "who",
        "boy",
        "did",
        "let",
        "put",
        "say",
        "she",
        "too",
        "use",
        "that",
        "this",
        "with",
        "from",
        "your",
        "have",
        "will",
        "what",
        "when",
        "where",
        "which",
        "while",
        "about",
        "after",
        "before",
        "being",
        "between",
        "both",
        "each",
        "into",
        "more",
        "most",
        "other",
        "some",
        "such",
        "than",
        "then",
        "there",
        "these",
        "those",
        "under",
        "very",
        "also",
        "back",
        "even",
        "just",
        "like",
        "only",
        "over",
        "work",
        "year",
        "years",
        "role",
        "team",
        "join",
        "looking",
        "company",
        # Source markup and browser accessibility labels.  Job descriptions
        # are cleaned before gap analysis, and these remain as a second guard.
        "class",
        "content",
        "div",
        "emphasis",
        "href",
        "http",
        "https",
        "intro",
        "list",
        "paragraph",
        "quot",
        "strong",
        "text",
        "www",
        # LT common
        "ir",
        "su",
        "iš",
        "į",
        "kad",
        "jūs",
        "mes",
        "jų",
        "kaip",
        "tai",
        "būti",
        "turi",
        "dėl",
        "arba",
        "apie",
        "visi",
        "mūsų",
        "jos",
        "jis",
        "nei",
        "per",
        "prie",
        "vienas",
        "gali",
        "jau",
        "dar",
        "bus",
        "buvo",
    }
)

# Cache for professional summaries (per-variant, per-run)
_summary_cache: dict[Path, str] = {}


def load_profiles(path: Path | None = None) -> dict[str, Any]:
    p = path or PROFILES_PATH
    if not p.exists():
        raise FileNotFoundError(f"Missing profiles: {p}")
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) if yaml is not None else _parse_variant_profiles_yaml(raw)
    variants = data.get("variants") if isinstance(data, dict) else None
    if not isinstance(variants, dict):
        raise ValueError("variant_profiles.yaml must contain a 'variants' mapping")
    return variants


def _parse_variant_profiles_yaml(raw: str) -> dict[str, Any]:
    """Parse the simple variant_profiles.yaml shape without an external package."""
    variants: dict[str, dict[str, Any]] = {}
    current_slug: str | None = None
    current_list_key: str | None = None

    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped == "variants:":
            continue

        if indent == 2 and stripped.endswith(":"):
            current_slug = stripped[:-1]
            variants[current_slug] = {}
            current_list_key = None
            continue

        if current_slug is None:
            raise ValueError(f"Unexpected profile content on line {line_number}: {raw_line}")

        if indent == 4 and ":" in stripped:
            key, _, value = stripped.partition(":")
            value = value.strip()
            if value:
                variants[current_slug][key] = _yaml_scalar(value)
                current_list_key = None
            else:
                variants[current_slug][key] = []
                current_list_key = key
            continue

        if indent >= 6 and stripped.startswith("- ") and current_list_key:
            variants[current_slug][current_list_key].append(_yaml_scalar(stripped[2:].strip()))
            continue

        raise ValueError(f"Unsupported profile YAML on line {line_number}: {raw_line}")

    return {"variants": variants}


def _yaml_scalar(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_job_file(raw: str, *, job_file_path: str | None = None) -> dict[str, Any]:
    """Parse inbox job .txt: KEY: value header until '---', then body."""
    lines = raw.splitlines()
    meta: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == "---":
            i += 1
            break
        if not stripped:
            i += 1
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            key = k.strip().upper()
            meta[key] = v.strip()
        i += 1
    body = "\n".join(lines[i:]).strip()

    title = meta.get("TITLE", "")
    company = meta.get("COMPANY", "")
    url = meta.get("URL", "")
    source = meta.get("SOURCE", "")
    job_id_meta = meta.get("JOB_ID", "").strip()

    title_boost_parts = [title, company]
    if body:
        first_line = body.split("\n", 1)[0].strip()
        if first_line and len(first_line) < 220:
            title_boost_parts.append(first_line)
    title_boost_region = " ".join(title_boost_parts).strip().lower()

    return {
        "title": title,
        "company": company,
        "url": url,
        "source": source,
        "job_id": job_id_meta,
        "body": body,
        "title_boost_region": title_boost_region,
        "job_file": job_file_path,
    }


def tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in TOKEN_RE.finditer(text)}


def extract_professional_summary(md_path: Path) -> str:
    """Extract professional summary, with in-memory caching."""
    if md_path in _summary_cache:
        return _summary_cache[md_path]

    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    summary = ""

    for i, line in enumerate(lines):
        if line.strip() == "## Professional Summary":
            chunk: list[str] = []
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("## "):
                    break
                t = lines[j].strip()
                if t and t != "---":
                    chunk.append(t)
            summary = " ".join(chunk)
            break

    _summary_cache[md_path] = summary
    return summary


def variant_markdown_path(slug: str, variants: dict[str, Any]) -> Path:
    entry = variants[slug]
    rel = entry.get("markdown") or entry["markdown"]
    return CV_DIR / rel


def _keyword_score(keyword: str, jd_lower: str, title_boost_lower: str) -> tuple[float, int]:
    """Returns (weighted score, hit count capped)."""
    kw = keyword.lower().strip()
    if not kw or len(kw) < 2:
        return 0.0, 0
    count = jd_lower.count(kw)
    if count <= 0:
        return 0.0, 0
    capped = min(count, 3)
    score = float(capped)
    # Only check title_boost if keyword was found (early exit optimisation)
    if kw in title_boost_lower:
        score += min(3.0, 2.0 + 0.5 * capped)
    return score, capped


def _target_title_matches(target_title: str, job_title_lower: str) -> bool:
    """Return whether a multi-word target phrase appears in the actual job title."""

    title = target_title.lower().strip()
    return len(tokenize(title)) >= 2 and title in job_title_lower


def score_variant(
    slug: str,
    jd_lower: str,
    title_boost_lower: str,
    entry: dict[str, Any],
    job_title_lower: str = "",
    jd_tokens_cached: set[str] | None = None,
) -> dict[str, Any]:
    keywords = entry.get("keywords") or []
    target_titles = entry.get("target_titles") or []
    negatives = entry.get("negative_keywords") or []
    primary = 0.0
    hits: list[str] = []
    target_title_hits: list[str] = []
    neg_hits: list[str] = []

    target_title_hits = [
        str(target_title)
        for target_title in target_titles
        if _target_title_matches(str(target_title), job_title_lower)
    ]
    if target_title_hits:
        primary += 25.0

    for kw in keywords:
        pts, _capped = _keyword_score(str(kw), jd_lower, title_boost_lower)
        if pts > 0:
            primary += pts
            hits.append(str(kw))

    penalty = 0.0
    for neg in negatives:
        ns = str(neg).lower()
        if ns and ns in jd_lower:
            neg_hits.append(str(neg))
            penalty += 6.0

    primary_after = max(0.0, primary - penalty)
    md_path = CV_DIR / entry["markdown"]
    summary = extract_professional_summary(md_path)
    summary_tokens = tokenize(summary)
    # Use cached tokens if provided (optimisation: avoid re-tokenization)
    jd_tokens = jd_tokens_cached if jd_tokens_cached is not None else tokenize(jd_lower)
    if summary_tokens:
        tie_break = len(jd_tokens & summary_tokens) / len(summary_tokens)
    else:
        tie_break = 0.0

    return {
        "slug": slug,
        "primary_score_raw": round(primary, 4),
        "primary_score": round(primary_after, 4),
        "negative_penalty": round(penalty, 4),
        "target_title_hits": sorted(set(target_title_hits)),
        "keyword_hits": sorted(set(hits)),
        "negative_hits": neg_hits,
        "tie_break_score": round(tie_break, 6),
    }


def match_job_to_variants(parsed_job: dict[str, Any], variants: dict[str, Any]) -> dict[str, Any]:
    body = parsed_job.get("body") or ""
    tb = parsed_job.get("title_boost_region") or ""
    job_title_lower = str(parsed_job.get("title") or "").lower()
    jd_full = f"{tb}\n\n{body}".strip().lower()
    if not jd_full:
        raise ValueError("Job description is empty after parsing (nothing to match).")

    # Tokenise once (optimisation: 75% reduction in tokenization overhead)
    jd_tokens_cached = tokenize(jd_full)

    scores: list[dict[str, Any]] = []
    for slug, entry in variants.items():
        if not isinstance(entry, dict):
            continue
        scores.append(
            score_variant(
                slug,
                jd_full,
                tb,
                entry,
                job_title_lower=job_title_lower,
                jd_tokens_cached=jd_tokens_cached,
            )
        )

    scores.sort(key=lambda r: (r["primary_score"], r["tie_break_score"]), reverse=True)
    top = scores[0]
    second = scores[1] if len(scores) > 1 else {"slug": "", "primary_score": 0.0, "tie_break_score": 0.0}

    margin = float(round(top["primary_score"] - second["primary_score"], 4))
    if top["primary_score"] <= 0:
        confidence = "tie_review"
    elif margin >= max(5.0, 0.15 * max(top["primary_score"], 1.0)):
        confidence = "clear_winner"
    else:
        confidence = "tie_review"

    return {
        "job": {k: v for k, v in parsed_job.items() if k != "title_boost_region"},
        "jd_scoring_excerpt_chars": min(2000, len(jd_full)),
        "variants_ranked": scores,
        "recommendation": {
            "variant_slug": top["slug"],
            "confidence": confidence,
            "primary_score": top["primary_score"],
            "tie_break_score": top["tie_break_score"],
            "margin_over_second": margin,
        },
        "runner_up": {
            "variant_slug": second.get("slug", ""),
            "primary_score": second["primary_score"],
        },
    }


def keyword_gaps(
    chosen_slug: str,
    job_body: str,
    variants: dict[str, Any],
    *,
    max_suggestions: int = 15,
) -> tuple[list[tuple[str, int]], list[str]]:
    """
    JD token frequencies minus stopwords minus tokens appearing in variant markdown.
    Returns (sorted list (token, count), rationale lines).
    """
    md_text = variant_markdown_path(chosen_slug, variants).read_text(encoding="utf-8").lower()

    jd_tokens_list = [m.group(0).lower() for m in TOKEN_RE.finditer(job_body)]
    freq: dict[str, int] = {}
    for t in jd_tokens_list:
        if t in STOPWORDS or len(t) < 3:
            continue
        freq[t] = freq.get(t, 0) + 1

    md_tokens = tokenize(md_text)
    gaps: dict[str, int] = {}
    for t, c in freq.items():
        if t in md_tokens:
            continue
        gaps[t] = c

    sorted_gaps = sorted(gaps.items(), key=lambda x: (-x[1], x[0]))[:max_suggestions]
    notes = [
        "Suggestions are lexical only: add only phrases you can defend in interview.",
        f"Capped at {max_suggestions} tokens by frequency in the JD.",
    ]
    return sorted_gaps, notes


def matching_result_json(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False) + "\n"


def derive_job_id(parsed: dict[str, Any]) -> str:
    if parsed.get("job_id"):
        return re.sub(r"[^\w\-]+", "-", parsed["job_id"].strip()).strip("-").lower()

    safe = lambda s: re.sub(r"[^\w]+", "-", (s or "").strip().lower()).strip("-")  # noqa: E731

    parts = []
    company = parsed.get("company") or "company"
    title = parsed.get("title") or "role"
    parts.append(__import__("datetime").datetime.now().strftime("%Y%m%d"))
    short_co = "-".join(safe(company).split("-")[:3])
    short_ti = "-".join(safe(title).split("-")[:4])
    base = "-".join(filter(None, [parts[0], short_co or "co", short_ti or "role"]))
    return base[:120] if len(base) > 120 else base


def pdf_paths_for_slug(slug: str, variants: dict[str, Any]) -> dict[str, Path]:
    stem = variants[slug]["pdf_stem"]
    visual = OUTPUT_DIR / f"{stem}.pdf"
    ats = OUTPUT_DIR / f"{stem}-ats.pdf"
    return {"visual": visual, "ats": ats, "stem": Path(stem)}
