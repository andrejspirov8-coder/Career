"""
Playwright-only path: locate Connect UI, optionally add invitation note, send.

Kept separate from Browse WS driver so recruiter pipeline can reuse the battle-tested selectors.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from career_job_search.integrations.linkedin import selectors as lis


def jitter_sleep(seconds_min: float, seconds_max: float) -> None:
    lo, hi = min(seconds_min, seconds_max), max(seconds_min, seconds_max)
    import random

    time.sleep(random.uniform(lo, hi))  # noqa: S311


def pick_textarea(dialog: Any) -> Any:
    for sel in (
        "textarea#custom-message",
        'textarea[name="message"]',
        "textarea#custom-invite-note",
        "textarea",
    ):
        locator = dialog.locator(sel)

        try:
            if locator.count() >= 1 and locator.first.is_visible(timeout=1500):
                return locator.first
        except Exception:  # noqa: S112
            continue

    tail = dialog.locator("textarea")
    try:
        if tail.count() >= 1:
            return tail.last
        return dialog.locator("textarea").first

    except Exception:
        return dialog.locator("textarea").first


def _try_connect_click(locator: Any, *, timeout_ms: int = 7000) -> bool:
    try:
        if not locator.is_visible(timeout=900):
            return False
        locator.click(timeout=timeout_ms)
        return True

    except Exception:
        try:
            if locator.is_visible(timeout=500):
                locator.click(timeout=timeout_ms, force=True)
                return True
        except Exception:  # noqa: S110
            pass

    return False


def _profile_top_card_root(page: Any) -> Any:
    h1 = page.locator("main h1").first
    try:
        if h1.count() > 0:
            for xpath in (
                "xpath=ancestor::*[contains(@class,'pvs-profile-actions')][1]",
                "xpath=ancestor::section[contains(@class,'artdeco-card')][1]",
                "xpath=ancestor::*[contains(@class,'pv-top-card')][1]",
                "xpath=ancestor::*[contains(@class,'ph5')][1]",
            ):
                card = h1.locator(xpath)
                try:
                    if card.count() > 0 and card.is_visible(timeout=900):
                        return card

                except Exception:  # noqa: S112
                    continue

    except Exception:  # noqa: S110
        pass

    for selector in (
        "main .pv-top-card",
        "main section.artdeco-card:has(h1)",
        "main section.artdeco-card",
        "main .ph5.pb5",
        "main",
    ):
        loc = page.locator(selector).first
        try:
            if loc.count() > 0 and loc.is_visible(timeout=800):
                return loc
        except Exception:  # noqa: S112
            continue
    return page.locator("main").first


def _click_connect_candidates_in(root: Any, *, timeout_ms: int = 7000) -> bool:
    connect_re = re.compile(lis.CONNECT_ROLE_NAME_RE, re.I)

    try:
        invite_links = root.get_by_role("link", name=connect_re)
        n_links = invite_links.count()
        for idx in range(min(n_links, 4)):
            if _try_connect_click(invite_links.nth(idx), timeout_ms=timeout_ms):
                return True

    except Exception:  # noqa: S110
        pass

    for selector in lis.CONNECT_LINK_FALLBACK_SELECTORS:
        try:
            loc = root.locator(selector).first

            if _try_connect_click(loc, timeout_ms=timeout_ms):
                return True
        except (PlaywrightTimeout, Exception):  # noqa: S112
            continue

    try:
        by_label = root.locator(
            'button[aria-label*="connect" i]:not([disabled]), '
            'button[aria-label*="Invite" i][aria-label*="connect" i]:not([disabled])'
        )

        n = by_label.count()

        for idx in range(min(n, 4)):
            if _try_connect_click(by_label.nth(idx), timeout_ms=timeout_ms):
                return True

    except Exception:  # noqa: S110
        pass

    try:
        buttons = root.get_by_role("button", name=connect_re)
        n = buttons.count()

        for idx in range(min(n, 6)):
            if _try_connect_click(buttons.nth(idx), timeout_ms=timeout_ms):
                return True

    except Exception:  # noqa: S110
        pass

    for selector in lis.CONNECT_BUTTON_FALLBACK_SELECTORS:
        try:
            loc = root.locator(selector).first

            if _try_connect_click(loc, timeout_ms=timeout_ms):
                return True

        except (PlaywrightTimeout, Exception):  # noqa: S112
            continue

    try:
        exact = root.get_by_role("button", name=re.compile(r"^connect$", re.I))

        if exact.count() > 0 and _try_connect_click(exact.first, timeout_ms=timeout_ms):
            return True

    except Exception:  # noqa: S110
        pass

    try:
        text_btn = (
            root.locator("button").filter(has_text=re.compile(r"^connect$", re.I)).first
        )

        if _try_connect_click(text_btn, timeout_ms=timeout_ms):
            return True

    except Exception:  # noqa: S110
        pass

    return False


def _click_visible_connect_in(root: Any, *, timeout_ms: int = 7000) -> bool:
    for bar_selector in lis.PROFILE_ACTIONS_BAR_SELECTORS:
        try:
            bar = root.locator(bar_selector).first

            if bar.count() > 0 and bar.is_visible(timeout=500):
                if _click_connect_candidates_in(bar, timeout_ms=timeout_ms):
                    return True

        except Exception:  # noqa: S112
            continue

    return _click_connect_candidates_in(root, timeout_ms=timeout_ms)


def _click_connect_near_h1_js(page: Any) -> bool:
    try:
        result = page.evaluate(lis.CONNECT_CLICK_NEAR_H1_JS) or {}

        return bool(result.get("ok"))

    except Exception:
        return False


def click_profile_connect(
    page: Any,
    *,
    run_logs_dir: Path,
    profile_tag: str,
    jitter_cb: Callable[[float, float], None] | None = None,
) -> str:
    sleep_j = jitter_cb or jitter_sleep

    try:
        page.locator("main h1").first.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        try:
            page.locator("main").first.scroll_into_view_if_needed(timeout=4000)
        except Exception:  # noqa: S110
            pass

    sleep_j(0.35, 0.75)
    top = _profile_top_card_root(page)

    connect_re = re.compile(lis.CONNECT_ROLE_NAME_RE, re.I)

    try:
        page.get_by_role("link", name=connect_re).first.wait_for(
            state="visible", timeout=12_000
        )
    except Exception:  # noqa: S110
        pass

    if _click_visible_connect_in(top):
        return "primary"

    if _click_connect_near_h1_js(page):
        return "primary"

    try:
        more_btn = top.get_by_role("button", name=re.compile(r"^more\b", re.I)).first

        if not more_btn.is_visible(timeout=1200):
            more_btn = page.get_by_role(
                "button", name=re.compile(r"^more\b", re.I)
            ).first

        if more_btn.is_visible(timeout=1600):
            more_btn.click(timeout=5000)

            sleep_j(0.45, 0.95)

            menu_connect_re = re.compile(lis.CONNECT_ROLE_NAME_RE, re.I)

            menu_connect = page.get_by_role("button", name=menu_connect_re).first

            if menu_connect.is_visible(timeout=2800):
                menu_connect.click(timeout=7000)

                return "more_menu"

            menu_item = page.locator(
                'motion.div[role="button"], div[role="button"], span[role="button"]'
            ).filter(has_text=re.compile(r"^connect$", re.I))

            if menu_item.count() > 0 and menu_item.first.is_visible(timeout=2000):
                menu_item.first.click(timeout=7000)

                return "more_menu"

    except Exception:  # noqa: S110
        pass

    run_logs_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d-%H%M%S")

    safe = re.sub(r"[^\w\-]+", "_", profile_tag)[:88] or "profile"

    shot = run_logs_dir / f"{safe}-noconnect-{ts}.png"

    try:
        page.screenshot(path=str(shot), full_page=False)

    except Exception:  # noqa: S110
        pass

    return "none"


def playwright_try_send_invitation(
    page: Any,
    *,
    note_text: str,
    run_logs_dir: Path,
    profile_tag: str,
    jitter_fn: Callable[[float, float], None] | None = None,
) -> tuple[bool, str, str]:
    jitter_cb = jitter_fn or jitter_sleep

    try:
        page.locator("main").first.scroll_into_view_if_needed(timeout=4000)
    except Exception:  # noqa: S110
        pass

    connect_path = click_profile_connect(
        page, run_logs_dir=run_logs_dir, profile_tag=profile_tag, jitter_cb=jitter_cb
    )

    if connect_path == "none":
        return False, "connect_button_missing_or_hidden", connect_path

    jitter_cb(0.55, 1.35)

    try:
        dialog = (
            page.locator('[role="dialog"]')
            .filter(has_text=re.compile(r"(invite|invitation)", re.I))
            .first
        )

        dialog.wait_for(state="visible", timeout=9000)

    except Exception:
        dialog = page.locator('[role="dialog"]').first

        dialog.wait_for(state="visible", timeout=4000)

    try:
        add_note_candidates = dialog.get_by_role(
            "button",
            name=re.compile(r"\b(note|pastab|rugštyn)\w*", re.I),
        )

        if add_note_candidates.count() >= 1 and add_note_candidates.first.is_visible(
            timeout=2500
        ):
            add_note_candidates.first.click(timeout=7000)
            jitter_cb(0.3, 0.9)

    except Exception:  # noqa: S110
        pass

    try:
        textarea = pick_textarea(dialog)

        textarea.wait_for(state="visible", timeout=5000)

        textarea.fill(note_text[:300])

        jitter_cb(0.35, 1.0)

    except Exception as exc_txt:
        return False, f"invite_modal_missing_textarea:{exc_txt}", connect_path

    try:
        buttons = dialog.get_by_role(
            "button",
            name=re.compile(r"\b(send|invite|išsiųsti)", re.I),
        )

        clicked = False

        for idx in range(buttons.count()):
            btn = buttons.nth(idx)

            try:
                if not btn.is_visible():
                    continue

                lbl = (btn.inner_text() or "").lower()

                if any(bad in lbl for bad in ["without note", "send without"]):
                    continue

                btn.click(timeout=9500)

                clicked = True

                break

            except Exception:  # noqa: S112
                continue

        if not clicked:
            return False, "send_button_not_clicked", connect_path

        jitter_cb(0.8, 1.9)

        return True, "", connect_path

    except Exception as exc2:
        return False, f"send_click_failure:{exc2}", connect_path
