#!/usr/bin/env python3
"""
Sync LinkedIn invitation + messaging signals into pipeline/recruiters.csv (read-only browsing).

Run from `job-search/` (logged-in automation Chrome profile):

  python3 tools/linkedin_followup.py --headed

Requires the same PyYAML + Playwright setup as linkedin_recruiter_bot.py.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:
    yaml = None
    _yaml_exc = exc
else:
    _yaml_exc = None

from playwright.sync_api import sync_playwright

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.campaign import (
    LOGIN_BLOCKERS,
    assert_not_blocked,
    dwell_navigation,
    launch_linkedin_browser_context,
    load_config,
    resolve_browser_channel,
    wait_for_manual_login,
)
from career_job_search.integrations.linkedin.paths import (
    DEFAULT_LINKEDIN_CONFIG,
    PROFILE_DIR,
    RECRUITERS_CSV,
)
from career_job_search.recruiters.log import CSV_HEADER, ensure_recruiter_csv_schema

DEFAULT_CONFIG = DEFAULT_LINKEDIN_CONFIG


def load_all_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_all_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_HEADER))
        w.writeheader()
        for row in rows:
            w.writerow({k: (row.get(k) or "") for k in CSV_HEADER})


def scrape_sent_invitation_cards(page: Any) -> list[dict[str, str]]:
    """Best-effort parse of /mynetwork/invitation-manager/sent/"""
    js = """
    () => {
      const out = [];
      const seen = new Set();
      document.querySelectorAll('a[href*="/in/"]').forEach(a => {
        let u = (a.href || '').split('?')[0].split('#')[0];
        if (!u.includes('/in/') || seen.has(u)) return;
        seen.add(u);
        let block = a.closest('li') || a.closest('div[class*="entity"]') || a.parentElement;
        let t = ((block && block.innerText) || '').toLowerCase();
        let status = 'unknown';
        if (t.includes('accepted')) status = 'accepted';
        else if (t.includes('withdrawn')) status = 'withdrawn';
        else if (t.includes('pending')) status = 'pending';
        out.push({ url: u, status, snippet: t.slice(0, 400) });
      });
      return out;
    }
    """
    try:
        data = page.evaluate(js)
        return list(data) if data else []
    except Exception:
        return []


def scrape_messaging_previews(page: Any) -> list[dict[str, str]]:
    js = """
    () => {
      const out = [];
      const seen = new Set();
      document.querySelectorAll('a[href*="/in/"]').forEach(a => {
        let u = (a.href || '').split('?')[0].split('#')[0];
        if (!u.includes('/in/') || seen.has(u)) return;
        seen.add(u);
        let card = a.closest('li') || a.closest('[class*="msg-conversation"]') || a.parentElement;
        let preview = ((card && card.innerText) || '').trim();
        if (preview.length < 2) return;
        out.push({ url: u, preview });
      });
      return out;
    }
    """
    try:
        data = page.evaluate(js)
        return list(data) if data else []
    except Exception:
        return []


def likely_reply_from_preview(preview: str) -> bool:
    lines = [ln.strip() for ln in preview.splitlines() if ln.strip()]
    if not lines:
        return False
    last = lines[-1]
    if re.match(r"^You\s*:", last, re.I):
        return False
    return True


def run_followup(args: argparse.Namespace, raw_cfg: dict[str, Any]) -> int:
    if yaml is None:
        raise SystemExit(f"Need PyYAML: pip install pyyaml ({_yaml_exc})")

    ensure_recruiter_csv_schema(RECRUITERS_CSV)

    base_url = (raw_cfg.get("linkedin_base_url") or "https://www.linkedin.com").rstrip(
        "/"
    )
    limits = raw_cfg.get("limits") or {}
    sent_url = f"{base_url}/mynetwork/invitation-manager/sent/"
    msg_url = f"{base_url}/messaging/"

    rows = load_all_rows(RECRUITERS_CSV)
    if not rows:
        print("No rows in recruiters.csv — nothing to update.", flush=True)
        return 0

    browser_channel = resolve_browser_channel(raw_cfg, args.browser_channel)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        ctx = launch_linkedin_browser_context(
            pw, headed=args.headed, channel=browser_channel
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{base_url}/feed/", wait_until="domcontentloaded")
        dwell_navigation(limits)

        block = assert_not_blocked(page, scan_html=False)
        if block and block in LOGIN_BLOCKERS:
            if not wait_for_manual_login(page, base_url=base_url, headed=args.headed):
                ctx.close()
                return 3
            block = assert_not_blocked(page)
        if block:
            print(f"Blocked: {block}", flush=True)
            ctx.close()
            return 3

        # --- Sent invitations (accept / withdraw / pending)
        if not args.replies_only:
            page.goto(sent_url, wait_until="domcontentloaded")
            dwell_navigation(limits)
            time.sleep(1.2)
            for _ in range(4):
                try:
                    page.mouse.wheel(0, 900)
                except Exception:
                    break
                time.sleep(0.6)
            cards = scrape_sent_invitation_cards(page)
            by_url: dict[str, str] = {}
            for c in cards:
                canon = lis.canonical_profile_url(c.get("url") or "")
                if canon:
                    by_url[canon] = (c.get("status") or "unknown").lower()

            today = date.today().isoformat()
            accepted_new = 0
            wp_upd = 0
            for row in rows:
                if (row.get("status") or "").strip() != "sent":
                    continue
                canon = lis.canonical_profile_url(
                    (row.get("profile_url") or "").strip()
                )
                if not canon:
                    continue
                st = by_url.get(canon)
                if st == "accepted":
                    if not (row.get("accepted_at") or "").strip():
                        row["accepted_at"] = today
                        accepted_new += 1
                    if (row.get("withdraw_or_pending") or "").strip():
                        row["withdraw_or_pending"] = ""
                        wp_upd += 1
                elif st == "pending":
                    if (row.get("withdraw_or_pending") or "").strip() != "pending":
                        row["withdraw_or_pending"] = "pending"
                        wp_upd += 1
                elif st == "withdrawn":
                    if (row.get("withdraw_or_pending") or "").strip() != "withdrawn":
                        row["withdraw_or_pending"] = "withdrawn"
                        wp_upd += 1
            print(
                f"Invitation manager: new accepted_at={accepted_new}, withdraw_or_pending updates={wp_upd}.",
                flush=True,
            )

        # --- Messaging (reply heuristic)
        if not args.accepts_only:
            page.goto(msg_url, wait_until="domcontentloaded")
            dwell_navigation(limits)
            time.sleep(1.5)
            for _ in range(5):
                try:
                    page.mouse.wheel(0, 700)
                except Exception:
                    break
                time.sleep(0.45)
            previews = scrape_messaging_previews(page)
            pmap: dict[str, str] = {}
            for p in previews:
                canon = lis.canonical_profile_url(p.get("url") or "")
                if canon:
                    pmap[canon] = p.get("preview") or ""

            today = date.today().isoformat()
            rupd = 0
            for row in rows:
                canon = lis.canonical_profile_url(
                    (row.get("profile_url") or "").strip()
                )
                if not canon:
                    continue
                st = (row.get("status") or "").strip()
                if st not in ("sent", "skipped_pending"):
                    continue
                if (row.get("reply_at") or "").strip():
                    continue
                prev = pmap.get(canon)
                if not prev:
                    continue
                if not likely_reply_from_preview(prev):
                    continue
                row["reply_at"] = today
                excerpt = re.sub(r"\s+", " ", prev).strip()[:80]
                row["reply_excerpt"] = excerpt
                rupd += 1
            print(
                f"Messaging: marked reply_at on {rupd} row(s) (heuristic).", flush=True
            )

        ctx.close()

    write_all_rows(RECRUITERS_CSV, rows)
    try:
        from career_job_search.recruiters.persona_stats import write_persona_stats

        write_persona_stats()
    except Exception:
        pass
    print("Wrote pipeline/recruiters.csv", flush=True)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Update recruiters.csv from LinkedIn sent invites + messaging"
    )
    ap.add_argument("--headed", default=True, action=argparse.BooleanOptionalAction)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument(
        "--accepts-only", action="store_true", help="Only scan invitation-manager/sent/"
    )
    ap.add_argument("--replies-only", action="store_true", help="Only scan /messaging/")
    ap.add_argument("--browser-channel", default=None)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.accepts_only and args.replies_only:
        print("Use only one of --accepts-only / --replies-only", file=sys.stderr)
        return 2
    raw = load_config(Path(args.config))
    return run_followup(args, raw)


if __name__ == "__main__":
    sys.exit(main())
