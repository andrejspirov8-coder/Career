"""
LinkedIn DOM hints + safety checks. Consolidated so brittle selectors are easy to retune.
"""

from __future__ import annotations

from urllib.parse import urlparse

BLOCK_URL_FRAGMENTS = (
    "/checkpoint/",
    "/uas/",
    "/login",
    "/login?",
    "/signup",
)

# Lowercased substrings scanned from the raw HTML snippet (cheap safety net).
# LinkedIn profile page failed to render (transient or rate-limit); skip, do not halt whole run.
PROFILE_LOAD_ERROR_PHRASES = (
    "something went wrong when opening your profile",
    "something went wrong when opening",
    "this profile can't be accessed",
    "profile isn't available",
)

BLOCK_PAGE_TEXT_HINTS = (
    "quick security check",
    "security verification",
    "unusual activity",
    "let's verify",
    "enter the pin",
    "prove you're human",
    "prove youre human",
    "captcha",
    "authenticate your account",
    "temporarily restricted",
)


def canonical_profile_url(href: str) -> str:
    """Strip tracking params; keep canonical https profile path."""
    if not href or "/in/" not in href.lower():
        return ""

    trimmed = href.split("?", 1)[0].strip()
    if not trimmed.startswith("http"):
        trimmed = "https://" + trimmed.lstrip("/")

    parsed = urlparse(trimmed)
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    host = parsed.netloc.lower() if parsed.netloc else ""
    # Always normalize to www.linkedin.com so callers (e.g. profile enrichment)
    # can match against URLs returned by Exa/Firecrawl that strip the www.
    if host.endswith("linkedin.com"):
        host = "www.linkedin.com"
    else:
        host = "www.linkedin.com"

    segments = [s for s in (parsed.path or "").split("/") if s]
    if len(segments) < 2 or segments[0].lower() != "in":
        return ""

    slug = segments[1]
    if slug.lower() in frozenset({"company", "school", "showcase", "pub", "learning"}):
        return ""

    return f"{scheme}://{host}/in/{slug}/"


LOGIN_FIELD_SELECTORS = (
    '#username[name="session_key"]',
    "input#username",
    'input[name="session_key"]',
    'input[name="session_password"]',
    'input[data-id="sign-in-password"]',
)

# Profile header action row (primary Connect lives here, not in sidebar suggestions).
PROFILE_ACTIONS_BAR_SELECTORS = (
    ".pvs-profile-actions",
    ".pv-top-card-v2-cta",
    ".pv-top-card-v2-cta__container",
    ".ph5 .mt2",
)

CONNECT_BUTTON_FALLBACK_SELECTORS = (
    # Case-insensitive aria-label (Playwright CSS); matches "Invite Lina … to connect".
    'button[aria-label*="Invite" i][aria-label*="connect" i]:not([disabled])',
    'button[aria-label*="connect" i]:not([disabled])',
    ".pvs-profile-actions button.artdeco-button--primary:not([disabled])",
    ".pv-top-card-v2-cta button.artdeco-button--primary:not([disabled])",
    "button.artdeco-button--primary:not([disabled])",
)

# Modern profile header often uses a link, not a button (a11y name: "Invite <Name> to connect").
CONNECT_LINK_FALLBACK_SELECTORS = (
    'a[aria-label*="Invite" i][aria-label*="connect" i]',
    'a[href*="custom-invite"]',
    ".pvs-profile-actions a[aria-label*='connect' i]",
    'main a[aria-label*="connect" i]',
)

# LinkedIn often labels the control "Invite <Name> to connect", not plain "Connect".
CONNECT_ROLE_NAME_RE = (
    r"(invite\s+.+\s+to\s+connect|invite\s+to\s+connect|^connect$|^invite$)"
)

# Click the top-card Connect control near main h1 (avoids sidebar suggestion buttons).
CONNECT_CLICK_NEAR_H1_JS = r"""
() => {
  function isDisabled(el) {
    return !el || el.disabled || el.getAttribute("aria-disabled") === "true";
  }

  function connectScore(el) {
    if (isDisabled(el)) return 0;
    if (el.closest("aside")) return 0;
    var label = (el.getAttribute("aria-label") || "").trim();
    var text = (el.innerText || "").trim();
    var ll = label.toLowerCase();
    var tt = text.toLowerCase();
    if (/invite\s+.+\s+to\s+connect/i.test(label)) return 100;
    if (/^invite\s+to\s+connect$/i.test(label)) return 95;
    if (/^connect$/i.test(tt)) return 90;
    if (el.tagName === "A" && /invite.+to\s+connect/i.test(label)) return 92;
    if (ll.indexOf("invite") !== -1 && ll.indexOf("connect") !== -1) return 85;
    if (/^invite$/i.test(tt)) return 50;
    if (
      el.matches &&
      el.matches("button.artdeco-button--primary") &&
      ll.indexOf("connect") !== -1
    ) {
      return 80;
    }
    return 0;
  }

  var main = document.querySelector("main");
  if (!main) return { ok: false, reason: "no_main" };
  var h1 = main.querySelector("h1");
  if (!h1) return { ok: false, reason: "no_h1" };

  var scopes = [];
  var node = h1;
  for (var depth = 0; depth < 14 && node; depth++) {
    if (!node.closest("aside")) scopes.push(node);
    node = node.parentElement;
  }

  var candidates = [];
  for (var si = 0; si < scopes.length; si++) {
    var scope = scopes[si];
    var nodes = scope.querySelectorAll('button, [role="button"], a[href], a[role="link"]');
    for (var i = 0; i < nodes.length; i++) {
      var btn = nodes[i];
      if (btn.closest("aside")) continue;
      var score = connectScore(btn);
      if (score <= 0) continue;
      var rect = btn.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) continue;
      candidates.push({ btn: btn, score: score, depth: si });
    }
    if (candidates.some(function (c) { return c.score >= 90; })) break;
  }

  if (!candidates.length) return { ok: false, reason: "no_candidate" };
  candidates.sort(function (a, b) {
    if (b.score !== a.score) return b.score - a.score;
    return a.depth - b.depth;
  });

  var pick = candidates[0].btn;
  try {
    pick.scrollIntoView({ block: "center", inline: "nearest" });
  } catch (eScroll) {}
  pick.click();
  return {
    ok: true,
    reason: "clicked",
    label: (pick.getAttribute("aria-label") || pick.innerText || "").slice(0, 120),
  };
}
"""


def profile_page_load_failed(html_sample: str) -> bool:
    """True when LinkedIn shows a broken profile shell (skip one URL, keep scouting)."""
    blob = (html_sample or "").lower()
    return any(phrase in blob for phrase in PROFILE_LOAD_ERROR_PHRASES)


def detect_blockers(
    *, url: str, html_sample: str, scan_html: bool = True
) -> str | None:
    """Return blocker code if automation should halt; otherwise None."""
    u = url.lower()
    if any(seg in u for seg in BLOCK_URL_FRAGMENTS):
        return "checkpoint_or_auth_url"

    if not scan_html:
        return None

    blob = html_sample.lower()
    # Require a strong phrase so normal search/feed pages do not false-positive.
    strong_html_blockers = (
        "quick security check",
        "let's do a quick security check",
        "unusual activity from your account",
        "prove you're human",
        "prove youre human",
        "enter the pin we sent",
        "temporarily restricted from sending invitations",
    )
    if any(phrase in blob for phrase in strong_html_blockers):
        return "suspected_challenge_or_review_page"

    weak_hits = sum(1 for hint in BLOCK_PAGE_TEXT_HINTS if hint in blob)
    if weak_hits >= 3:
        return "suspected_challenge_or_review_page"

    return None


PROFILE_SCRAPER_JS = r"""
() => {
  function clamp(text, limit) {
    var lim = typeof limit === "number" ? limit : 24000;
    return (text || "").slice(0, lim);
  }

  function looksLikeStatsLine(t) {
    if (!t) return true;
    return /\b(connections|followers|following|contact info|mutual)\b/i.test(t);
  }

  var out = {
    name: "",
    headline: "",
    location: "",
    about: "",
    role_text: "",
    companyGuess: "",
    errors: [],
  };

  try {
    var mainEl = document.querySelector("main");
    if (!mainEl) {
      out.errors.push("no_main");
      return out;
    }

    var h1 = mainEl.querySelector("h1");
    if (h1) {
      var rawH1 = (h1.innerText || "").trim();
      var lines = rawH1.split(/\n+/).map(function (l) {
        return (l || "").trim();
      }).filter(Boolean);

      if (lines.length >= 2) {
        out.name = lines[0];
        out.headline = lines.slice(1).join(" ").trim();
      } else if (lines.length === 1) {
        out.name = lines[0];
      }

      if (!out.name) {
        var vis = h1.querySelector("span[aria-hidden='true']");
        if (vis && vis.innerText) {
          out.name = (vis.innerText || "").trim();
        }
      }

      if (!out.name) {
        var bits = [];
        Array.prototype.forEach.call(h1.querySelectorAll("span"), function (sp) {
          var tx = (sp.innerText || "").trim();
          if (tx && tx.length < 90 && !looksLikeStatsLine(tx)) bits.push(tx);
        });
        if (bits.length) out.name = bits.slice(0, 3).join(" ").trim();
      }
    }

    if (!out.name && document.title) {
      out.name = document.title.replace(/\s*\|\s*LinkedIn.*$/i, "").trim();
    }

    if (!out.headline) {
      var candidates = mainEl.querySelectorAll(
        "div.text-body-medium.break-words, .text-body-medium.break-words"
      );
      Array.prototype.some.call(candidates, function (el, ci) {
        if (ci > 30) return true;
        if (!el || el.closest("section[data-section='education']")) return false;
        var tx = clamp((el.innerText || "").trim(), 500);
        if (!tx || tx.length > 500) return false;
        if (looksLikeStatsLine(tx)) return false;
        if (out.name && tx === out.name) return false;
        out.headline = tx;
        return true;
      });
    }

    try {
      var secs = mainEl.querySelectorAll("section.artdeco-card, section");
      for (var si = 0; si < secs.length; si++) {
        var sec = secs[si];
        var ttl = clamp((sec.innerText || "").trim(), 200).split(/\n/).shift() || "";
        if (!/experience|employment|išsilavinimas|^patirtis/i.test(ttl.trim())) continue;
        var lines = clamp((sec.innerText || "").trim(), 2400).split(/\n+/);
        lines = lines.map(function (x) {
          return (x || "").trim();
        }).filter(Boolean);
        if (lines.length >= 3) {
          var guessLine = "";
          if ((/\bexperience\b|^patirtis/i).test(lines[1] || "") && lines[2]) guessLine = lines[2];
          else guessLine = lines[1];
          guessLine = (guessLine || "").trim();
          if (guessLine.indexOf("·") !== -1) {
            guessLine = guessLine.split("·")[0].trim();
          }
          guessLine = guessLine.replace(/^\s*(\d{4}\s?([–\-]|to)\s*)+/, "").trim();
          if (guessLine && guessLine.length >= 2 && guessLine.length < 160) out.companyGuess = guessLine;
        }
        break;
      }
    } catch (eGuess) {}

    var spans = mainEl.querySelectorAll("span");
    Array.prototype.some.call(spans, function (span, si) {
      if (si > 480) return true;
      try {
        var cls = (span.className || "").toString();
        var tx = clamp((span.innerText || "").trim(), 720);
        if (/\btext-body-small\b/i.test(cls) && tx.indexOf(",") !== -1) {
          out.location = tx;
          return true;
        }
      } catch (e3) {
        out.errors.push("span_" + String(e3 || ""));
      }
      return false;
    });

    var sections = mainEl.querySelectorAll("section");
    Array.prototype.forEach.call(sections, function (sec) {
      var titleBits = "";
      Array.prototype.forEach.call(sec.querySelectorAll("h2,h3"), function (tg) {
        titleBits += " " + clamp((tg && tg.innerText) || "");
      });
      titleBits = titleBits.trim();
      var body = clamp((sec.innerText || "").trim(), 24000);
      var ttlLower = titleBits.toLowerCase();

      if (!body) return;
      if (/^\s*about\b/i.test(ttlLower) || ttlLower.indexOf("apie") === 0) {
        var stripped = body.replace(/^[^\n]+\n+/m, "").trim();
        out.about = stripped.length > 40 ? stripped : body.replace(/^\s*about\s+/i, "").trim();
      } else if (
        /experience|education|volunteering|skills|languages|projects|certifications/i.test(
          ttlLower
        )
      ) {
        out.role_text += "\n\n[[" + titleBits + "]]\n" + body;
      }
    });
  } catch (e) {
    out.errors.push(String(e || "scrape_failed"));
  }

  out.name = (out.name || "").trim();
  out.headline = (out.headline || "").trim();
  out.about = clamp(out.about, 24000);
  out.role_text = clamp(out.role_text, 24000);
  return out;
}
"""
