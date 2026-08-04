"""Clean and extract useful fields from opportunity descriptions.

The source adapters intentionally preserve the original payload.  Matching and
dashboard presentation use these helpers so encoded HTML and browser-accessibility
labels do not become CV keywords.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from html.parser import HTMLParser


class _VisibleTextParser(HTMLParser):
    """Collect readable text while keeping block boundaries."""

    _BLOCK_TAGS = {
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


_BROWSER_LABEL_RE = re.compile(
    r"(?:^|\s)-\s*(?:strong|text|list|emphasis|link|paragraph|heading):\s*",
    re.IGNORECASE,
)
_SPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SALARY_RE = re.compile(
    r"(?i)(?:salary|compensation|pay|atlyginimas|darbo\s+u[mž]mokestis)?\s*:?[ \t]*"
    r"(?:€|eur|usd|\$|gbp|£)\s*\d[\d\s,.]*(?:\s*[-–—]\s*(?:€|eur|usd|\$|gbp|£)?\s*\d[\d\s,.]*)?"
    r"(?:\s*(?:gross|net|bruto|before\s+tax|per\s+(?:hour|month|year)|/\s*(?:h|hr|month|year)))?"
)
_SALARY_AMOUNT_FIRST_RE = re.compile(
    r"(?i)\b\d[\d\s,.]*(?:\s*[-–—]\s*\d[\d\s,.]*)?\s*"
    r"(?:€|eur|usd|\$|gbp|£)(?:\s*(?:gross|net|bruto|per\s+(?:hour|month|year)))?"
)
_AMOUNT_RE = re.compile(r"\d[\d\s,.]*")
_ISO_DEADLINE_RE = re.compile(
    r"(?i)(?:deadline|apply\s+by|closing\s+date|valid\s+until|galioja\s+iki)\s*:?[ \t]*"
    r"(20\d{2}-\d{2}-\d{2})"
)
_EU_DEADLINE_RE = re.compile(
    r"(?i)(?:deadline|apply\s+by|closing\s+date|valid\s+until|galioja\s+iki)\s*:?[ \t]*"
    r"(\d{1,2}[./-]\d{1,2}[./-]20\d{2})"
)


def clean_opportunity_text(value: str) -> str:
    """Return readable plain text without source-UI markup."""

    raw = value or ""
    # Some ATS feeds encode a complete HTML fragment as entities.  Two passes
    # cover nested encodings without repeatedly transforming arbitrary text.
    decoded = html.unescape(html.unescape(raw))
    if re.search(r"<\/?[A-Za-z][^>]*>", decoded):
        parser = _VisibleTextParser()
        try:
            parser.feed(decoded)
            decoded = "".join(parser.parts)
        except Exception:
            decoded = re.sub(r"<[^>]+>", " ", decoded)
    decoded = _BROWSER_LABEL_RE.sub(" ", decoded)
    decoded = decoded.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACE_RE.sub(" ", line).strip() for line in decoded.split("\n")]
    return _BLANK_LINES_RE.sub(
        "\n\n", "\n".join(line for line in lines if line)
    ).strip()


def extract_salary_text(value: str) -> str:
    """Extract a conservative salary phrase, or return an empty string."""

    text = clean_opportunity_text(value)
    for pattern in (_SALARY_RE, _SALARY_AMOUNT_FIRST_RE):
        match = pattern.search(text)
        if not match:
            continue
        amounts: list[float] = []
        for raw in _AMOUNT_RE.findall(match.group(0)):
            try:
                amounts.append(float(raw.replace(" ", "").replace(",", "")))
            except ValueError:
                continue
        if not amounts or max(amounts) < 100:
            continue
        return _SPACE_RE.sub(" ", match.group(0)).strip(" :;,.-")[:160]
    return ""


def extract_deadline(value: str) -> str:
    """Extract an explicitly labelled deadline as an ISO date."""

    text = clean_opportunity_text(value)
    match = _ISO_DEADLINE_RE.search(text)
    if match:
        try:
            return date.fromisoformat(match.group(1)).isoformat()
        except ValueError:
            return ""
    match = _EU_DEADLINE_RE.search(text)
    if not match:
        return ""
    raw = match.group(1).replace("/", ".").replace("-", ".")
    try:
        return datetime.strptime(raw, "%d.%m.%Y").date().isoformat()
    except ValueError:
        return ""
