"""
Browser backends for recruiter automation:

* ``PlaywrightLinkedInAutomator`` — wraps a Playwright page.

* ``BrowseWsLinkedInAutomator`` — ``browse --ws <cdp>`` subprocess + helper Chrome launcher.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.connect_flow import (
    playwright_try_send_invitation,
)
from career_job_search.integrations.linkedin.paths import PROFILE_DIR
from career_job_search.integrations.linkedin.profile_lock import (
    release_stale_chrome_profile_lock,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_CURSOR_BROWSE = (
    Path.home()
    / ".cursor/plugins/cache/cursor-public/browse/release_v0.2.4/node_modules/.bin/browse"
)


def resolve_browse_binary() -> str:
    explicit = (
        os.environ.get("JOB_SEARCH_BROWSE_CLI") or os.environ.get("BROWSE_CLI") or ""
    ).strip()
    if explicit:
        return explicit
    if DEFAULT_CURSOR_BROWSE.is_file():
        return str(DEFAULT_CURSOR_BROWSE)
    found = shutil.which("browse")
    return found or str(DEFAULT_CURSOR_BROWSE)


def _mac_chrome_exe() -> str | None:
    p = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if p.is_file():
        return str(p)
    return None


def chrome_executable(cfg: dict[str, Any]) -> str:
    exe = (cfg.get("browser") or {}).get("chrome_executable") or ""
    if isinstance(exe, str) and exe.strip():
        return exe.strip()
    if os.environ.get("JOB_SEARCH_CHROME_EXECUTABLE", "").strip():
        return os.environ["JOB_SEARCH_CHROME_EXECUTABLE"].strip()
    ghost = (
        shutil.which("google-chrome-stable")
        or shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or _mac_chrome_exe()
    )
    if ghost:
        return ghost
    return "google-chrome"


def websocket_debugger_url(port: int) -> str:
    with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=30) as r:
        blob = json.loads(r.read())
    ws = blob.get("webSocketDebuggerUrl")
    if not ws:
        raise RuntimeError("/json/version missing webSocketDebuggerUrl")
    return str(ws)


def wait_for_ws(port: int, *, deadline_s: float = 35.0) -> str:
    t0 = time.time()
    last = ""
    while time.time() - t0 < deadline_s:
        try:
            return websocket_debugger_url(port)
        except (URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
            last = repr(exc)
        time.sleep(0.35)
    raise RuntimeError(f"Chrome debugger not ready on {port}: {last}")


def wrap_iife_arrow(js_fn: str) -> str:
    s = js_fn.strip()
    if not s.startswith("("):
        s = f"({s})"
    return f"{s}()"


def _invite_ref_priority(line: str) -> int:
    nl = line.lower()
    rm = re.search(r"\[([0-9]+-[0-9]+)\]", line)
    if not rm:
        return 0
    if not ("button" in nl or "link" in nl):
        return 0
    if re.search(r"invite\s+.+\s+to\s+connect", nl):
        return 140
    if "invite" in nl and "connect" in nl:
        return 120
    if re.search(r"\bconnect\b", nl):
        return 55
    if "invite" in nl:
        return 70
    return 0


def _refs_connect_sorted(tree: str) -> list[str]:
    scored: list[tuple[int, str]] = []
    for line in tree.splitlines():
        pri = _invite_ref_priority(line)
        if pri <= 0:
            continue
        m = re.search(r"\[([0-9]+-[0-9]+)\]", line)
        if m:
            scored.append((pri, "@" + m.group(1)))
    scored.sort(reverse=True)
    return [r for _p, r in scored]


class LinkedInAutomatorBase(ABC):
    limits: dict[str, Any]

    @abstractmethod
    def goto(self, url: str) -> None: ...

    @abstractmethod
    def current_url(self) -> str: ...

    @abstractmethod
    def html_sample(self, limit: int) -> str: ...

    @abstractmethod
    def evaluate(self, js_expression: str) -> Any: ...

    @abstractmethod
    def mouse_wheel(self, delta_y: int) -> None: ...

    def eval_on_selector_all_hrefs(self, selector: str) -> list[str]:
        qsel = json.dumps(selector)
        expr = (
            "(JSON.stringify(Array.from(document.querySelectorAll("
            + qsel
            + ")).map(el => el.getAttribute('href')||'')"
            ".filter(Boolean)))"
        )
        raw = self.evaluate(expr)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return []
        if isinstance(raw, list):
            return [str(x) for x in raw]
        return []

    def locator_count(self, selector: str) -> int:
        expr = json.dumps(selector)
        return int(self.evaluate(f"document.querySelectorAll({expr}).length") or 0)

    def screenshot_file(self, path: Path, full_page: bool = False) -> None:
        _ = path, full_page
        ...

    def try_send_invitation(
        self,
        *,
        note_text: str,
        run_logs_dir: Path,
        profile_tag: str,
        jitter_sleep: Callable[[float, float], None],
    ) -> tuple[bool, str, str]:
        _ = jitter_sleep

        raise NotImplementedError


class PlaywrightLinkedInAutomator(LinkedInAutomatorBase):
    def __init__(self, page: Any, limits: dict[str, Any]) -> None:
        self.page = page

        self.limits = limits

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")

    def current_url(self) -> str:
        try:
            return self.page.url

        except Exception:
            return ""

    def html_sample(self, limit: int) -> str:
        try:
            return self.page.content()[:limit]

        except Exception:
            return ""

    def evaluate(self, js_expression: str) -> Any:
        return self.page.evaluate(js_expression)

    def mouse_wheel(self, delta_y: int) -> None:
        try:
            self.page.mouse.wheel(0, delta_y)

        except Exception:
            self.page.evaluate("(y)=>window.scrollBy(0,y)", delta_y)

    def screenshot_file(self, path: Path, full_page: bool = False) -> None:
        self.page.screenshot(path=str(path), full_page=full_page)

    def try_send_invitation(
        self,
        *,
        note_text: str,
        run_logs_dir: Path,
        profile_tag: str,
        jitter_sleep: Callable[[float, float], None],
    ) -> tuple[bool, str, str]:
        return playwright_try_send_invitation(
            self.page,
            note_text=note_text,
            run_logs_dir=run_logs_dir,
            profile_tag=profile_tag,
            jitter_fn=jitter_sleep,
        )


class BrowseWsLinkedInAutomator(LinkedInAutomatorBase):
    """Drive tabs via Cursor Browse MCP CLI attaching to debugger port Chrome."""

    def __init__(
        self,
        *,
        ws_url: str,
        browse_binary: str,
        headless_flag: bool,
        limits: dict[str, Any],
    ) -> None:
        self.ws_url = ws_url

        self.browse_binary = browse_binary

        self.headless_flag = headless_flag

        self.limits = limits

    def _cmd_base(self) -> list[str]:
        cmd = [
            self.browse_binary,
            "--ws",
            self.ws_url,
            "--json",
            "--headed" if not self.headless_flag else "--headless",
        ]

        return cmd

    def _run_raw(self, pieces: list[str]) -> subprocess.CompletedProcess[str]:
        full = [*self._cmd_base(), *pieces]

        return subprocess.run(full, capture_output=True, text=True, timeout=180)

    def _run(self, pieces: list[str]) -> dict[str, Any]:
        proc = self._run_raw(pieces)

        txt = (proc.stdout or proc.stderr).strip()

        if proc.returncode != 0:
            raise RuntimeError(f"browse failed ({pieces[0]}): {txt[-520:]}")

        try:
            return json.loads(txt)

        except json.JSONDecodeError:
            bra = txt.rfind("{")

            if bra >= 0:
                return json.loads(txt[bra:])

            raise

    def goto(self, url: str) -> None:
        self._run(["open", "--wait", "domcontentloaded", "--timeout", "45000", url])

    def current_url(self) -> str:
        data = self._run(["get", "url"])

        r = data.get("result")

        return str(r) if r is not None else ""

    def html_sample(self, limit: int) -> str:
        data = self._run(["get", "html"])

        blob = str(data.get("result") or "")

        return blob[:limit]

    def evaluate(self, js_expression: str) -> Any:
        data = self._run(["eval", js_expression])

        return data.get("result")

    def mouse_wheel(self, delta_y: int) -> None:
        self._run(["scroll", "0", "0", "0", str(int(delta_y))])

    def screenshot_file(self, path: Path, full_page: bool = False) -> None:
        args = ["screenshot"]

        if full_page:
            args.append("--full-page")

        args.append(str(path))

        self._run(args)

    def browse_click(self, ref: str, *, timeout_ms: int = 9000) -> None:
        self._run(["click", "--timeout", str(timeout_ms), ref])

    def browse_fill(self, ref_or_sel: str, value: str, *, press_enter: bool) -> None:
        extras: list[str] = []

        if not press_enter:
            extras.append("--no-press-enter")

        self._run(["fill", *extras, ref_or_sel, value])

    def snapshot_compact(self) -> str:
        data = self._run(["snapshot", "-c"])

        inner = data.get("tree")

        return str(inner) if inner is not None else json.dumps(data)

    def _dialog_blob(self, snap: str) -> bool:
        lb = snap.lower()

        return "invite" in lb or "invitation" in lb or "connection" in lb

    def try_send_invitation(
        self,
        *,
        note_text: str,
        run_logs_dir: Path,
        profile_tag: str,
        jitter_sleep: Callable[[float, float], None],
    ) -> tuple[bool, str, str]:
        jitter_sleep_ = jitter_sleep

        try:
            self.evaluate(
                "(()=>{try{document.querySelector('main')"
                '.scrollIntoView({block:"start"});}catch(_e){}})()'
            )

        except Exception:  # noqa: S110
            pass

        connect_path = "none"

        try:
            if bool(self.evaluate(wrap_iife_arrow(lis.CONNECT_CLICK_NEAR_H1_JS))):
                connect_path = "primary"

        except Exception:
            connect_path = "primary" if False else "none"

        if connect_path == "none":
            snap0 = self.snapshot_compact()

            for rf in _refs_connect_sorted(snap0)[:9]:
                try:
                    self.browse_click(rf)

                    jitter_sleep_(0.45, 0.95)

                    s1 = self.snapshot_compact()

                    if self._dialog_blob(s1):
                        connect_path = "primary"

                        break

                except Exception:  # noqa: S112
                    continue

        if connect_path == "none":
            run_logs_dir.mkdir(parents=True, exist_ok=True)

            ts = time.strftime("%Y%m%d-%H%M%S")

            safe = re.sub(r"[^\w\-]+", "_", profile_tag)[:88] or "profile"

            shot = run_logs_dir / f"{safe}-noconnect-{ts}.png"

            try:
                self.screenshot_file(shot)

            except Exception:  # noqa: S110
                pass

            return False, "connect_button_missing_or_hidden", connect_path

        jitter_sleep_(0.55, 1.35)

        snap = self.snapshot_compact()

        if not self._dialog_blob(snap):
            for _ in range(10):
                if self._dialog_blob(self.snapshot_compact()):
                    break

                for line in snap.splitlines():
                    li = line.lower()

                    if re.search(r"\b(note|pastab|rug)\w*", li) and (
                        "button" in li or "link" in li
                    ):
                        m = re.search(r"\[([0-9]+-[0-9]+)\]", line)

                        if m:
                            try:
                                self.browse_click("@" + m.group(1))

                                jitter_sleep_(0.35, 0.8)

                                break

                            except Exception:  # noqa: S110
                                pass

                jitter_sleep_(0.2, 0.5)

                snap = self.snapshot_compact()

        # Add note shortcut

        for line in snap.splitlines():
            li = line.lower()

            if re.search(r"\b(note|pastab|rug)\w*", li) and ("button" in li):
                m = re.search(r"\[([0-9]+-[0-9]+)\]", line)

                if m:
                    try:
                        self.browse_click("@" + m.group(1))

                        jitter_sleep_(0.35, 0.9)

                    except Exception:  # noqa: S110
                        pass

        snap2 = self.snapshot_compact()

        area_ref = None

        scored: list[tuple[int, str]] = []

        for line in snap2.splitlines():
            nl = line.lower()

            if "textarea" not in nl and "text box" not in nl and "tekstą" not in nl:
                continue

            rm = re.search(r"\[([0-9]+-[0-9]+)\]", line)

            if rm:
                pr = 2 if ("invite" in nl or "pastab" in nl) else 0

                scored.append((pr, "@" + rm.group(1)))

        scored.sort(reverse=True)

        area_ref = scored[0][1] if scored else None

        if area_ref:
            try:
                self.browse_fill(area_ref, note_text[:300], press_enter=False)

                jitter_sleep_(0.35, 1.0)

            except Exception:
                area_ref = None

        if not area_ref:
            note_js = json.dumps(note_text[:300])

            js_fill = (
                "(function(){var dlg=document.querySelector('[role=dialog]');if(!dlg)return false;"
                "var ta=dlg.querySelector("
                "'textarea#custom-message,textarea[name=\"message\"],textarea');"
                "if(!ta)return false;ta.value="
                + note_js
                + ";ta.dispatchEvent(new Event('input',{bubbles:true}));return true;})()"
            )

            ok = bool(self.evaluate(js_fill))

            if not ok:
                return False, "invite_modal_missing_textarea:no_fill", connect_path

        jitter_sleep_(0.35, 1.0)

        send_ref = self._find_send_ref(self.snapshot_compact())

        if send_ref:
            try:
                self.browse_click(send_ref)

                jitter_sleep_(0.8, 1.9)

                return True, "", connect_path

            except Exception as exc:
                return False, f"send_click_failure:{exc}", connect_path

        clicked = bool(
            self.evaluate(
                r"""() => {
  const dialogs = [...document.querySelectorAll('[role="dialog"]')];
  const dlg = dialogs.find(
    (el) => /(invite|invitation)/i.test(el.innerText || ''),
  );
  if (!dlg) return false;
  const bs = [...dlg.querySelectorAll('button')];
  for (const b of bs) {
    const t = (b.innerText || '').toLowerCase().replace(/\s+/g, ' ');
    if (
      /send|invite|išsiųsti/.test(t) &&
      !/without(\s|\u00a0)*note|send(\s|\u00a0)*without/i.test(t)
    ) {
      b.click();
      return true;
    }
  }
  return false;
}"""
            )
        )

        jitter_sleep_(0.8, 1.9)

        if clicked:
            return True, "", connect_path

        return False, "send_button_not_clicked", connect_path

    def _find_send_ref(self, tree: str) -> str | None:
        best: tuple[int, str] | None = None

        for line in tree.splitlines():
            m = re.search(r"\[([0-9]+-[0-9]+)\]", line)

            if not m:
                continue

            low = line.lower()

            if "button" not in low:
                continue

            if any(bad in low for bad in ("without note", "send without")):
                continue

            if re.search(r"\b(send|invite|išsiųsti)\b", low):
                score = 2 if "send" in low else 1

                cand = ("@" + m.group(1), score)

                if best is None or cand[1] > best[1]:
                    best = cand

        return best[0] if best else None


class BrowseChromeDaemon:
    """Launch Chrome pointing at PROFILE_DIR so cookies match Playwright."""

    def __init__(self, *, profile_dir: Path, chrome_path: str, port: int) -> None:
        self.profile_dir = profile_dir

        self.chrome_path = chrome_path

        self.port = port

        self.proc: subprocess.Popen[bytes] | None = None

        self._owns = False

    def start(self, *, reuse_if_running: bool = True) -> str:
        ws: str | None = None

        if reuse_if_running:
            try:
                ws = websocket_debugger_url(self.port)

            except Exception:
                ws = None

        if ws:
            self._owns = False

            return ws

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        release_stale_chrome_profile_lock(self.profile_dir)

        argv = [
            self.chrome_path,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--remote-allow-origins=*",
        ]

        self.proc = subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        self._owns = True

        return wait_for_ws(self.port)

    def stop(self) -> None:
        if self.proc:
            try:
                self.proc.terminate()

                self.proc.wait(timeout=14)

            except Exception:
                try:
                    self.proc.kill()

                except Exception:  # noqa: S110
                    pass

            self.proc = None


def backend_from_cfg(raw_cfg: dict[str, Any]) -> str:
    b = raw_cfg.get("browser") or {}

    return str(b.get("backend") or "playwright").strip().lower()


def browse_debug_port(cfg: dict[str, Any]) -> int:
    try:
        return int((cfg.get("browser") or {}).get("browse_debug_port") or 9247)

    except (TypeError, ValueError):
        return 9247


def start_browse_ws_session(
    cfg: dict[str, Any],
) -> tuple[BrowseWsLinkedInAutomator, BrowseChromeDaemon]:
    port = browse_debug_port(cfg)

    chrome_path = chrome_executable(cfg)

    browse_bin = resolve_browse_binary()

    daemon = BrowseChromeDaemon(
        profile_dir=PROFILE_DIR, chrome_path=chrome_path, port=port
    )

    ws_url = daemon.start()

    headless_browser = bool((cfg.get("browser") or {}).get("browse_headless", False))

    driver = BrowseWsLinkedInAutomator(
        ws_url=ws_url,
        browse_binary=browse_bin,
        headless_flag=headless_browser,
        limits=cfg.get("limits") or {},
    )

    return driver, daemon
