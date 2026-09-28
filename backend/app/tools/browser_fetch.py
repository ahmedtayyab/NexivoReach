"""Optional rendered HTML fetch for JS-heavy contact pages.

Used only when static HTTP finds no email. Prefer Playwright Chromium;
fall back to installed Chrome / Edge. No-ops if Playwright is unavailable.

Memory posture for small hosts (Render free):
  - at most one browser job at a time
  - ephemeral launch/quit by default (no long-lived Chromium singleton)
  - low-memory Chromium flags + small viewport
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from app.config import settings

log = logging.getLogger(__name__)

_browser = None
_playwright = None
_lock: Optional[asyncio.Lock] = None
_slot: Optional[asyncio.Semaphore] = None
_idle_close_task: Optional[asyncio.Task] = None

_LAUNCH_ARGS = (
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--mute-audio",
    "--no-first-run",
    "--renderer-process-limit=1",
    "--js-flags=--max-old-space-size=128",
    # Single process trades some stability for much lower peak RAM on tiny VMs.
    "--single-process",
)


def _ephemeral() -> bool:
    return bool(getattr(settings, "CONTACT_BROWSER_EPHEMERAL", True))


def _max_concurrent() -> int:
    return max(1, int(getattr(settings, "CONTACT_BROWSER_MAX_CONCURRENT", 1) or 1))


def _idle_close_sec() -> float:
    return float(getattr(settings, "CONTACT_BROWSER_IDLE_CLOSE_SEC", 8) or 8)


def browser_available() -> bool:
    if not getattr(settings, "CONTACT_BROWSER_ENABLED", True):
        return False
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _slot_sem() -> asyncio.Semaphore:
    global _slot
    if _slot is None:
        _slot = asyncio.Semaphore(_max_concurrent())
    return _slot


async def _close_browser() -> None:
    global _browser, _playwright, _idle_close_task
    if _idle_close_task and not _idle_close_task.done():
        _idle_close_task.cancel()
        _idle_close_task = None
    browser, pw = _browser, _playwright
    _browser = None
    _playwright = None
    if browser is not None:
        try:
            await browser.close()
        except Exception as exc:
            log.debug("browser close: %r", exc)
    if pw is not None:
        try:
            await pw.stop()
        except Exception as exc:
            log.debug("playwright stop: %r", exc)


async def _schedule_idle_close() -> None:
    global _idle_close_task
    delay = _idle_close_sec()
    if delay <= 0 or _ephemeral():
        await _close_browser()
        return

    async def _deferred() -> None:
        try:
            await asyncio.sleep(delay)
            async with _lock:  # type: ignore[arg-type]
                await _close_browser()
                log.info("contact browser closed after idle")
        except asyncio.CancelledError:
            return

    if _idle_close_task and not _idle_close_task.done():
        _idle_close_task.cancel()
    _idle_close_task = asyncio.create_task(_deferred())


async def _ensure_browser():
    global _browser, _playwright, _lock
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _browser is not None:
            return _browser
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()
        last_err: Exception | None = None
        for kwargs in (
            {"headless": True, "args": list(_LAUNCH_ARGS)},
            {"channel": "chrome", "headless": True, "args": list(_LAUNCH_ARGS)},
            {"channel": "msedge", "headless": True, "args": list(_LAUNCH_ARGS)},
        ):
            try:
                _browser = await _playwright.chromium.launch(**kwargs)
                log.info(
                    "contact browser via %s (ephemeral=%s)",
                    kwargs.get("channel") or "chromium",
                    _ephemeral(),
                )
                return _browser
            except Exception as exc:
                last_err = exc
        await _close_browser()
        raise RuntimeError(f"No usable browser: {last_err}")


async def fetch_rendered(
    url: str,
    *,
    timeout_ms: int = 8000,
    wait_until: str = "domcontentloaded",
    click_menu: bool = True,
) -> Dict[str, Any]:
    """Render a URL; return {ok, html, text, url, error}."""
    target = (url or "").strip()
    if not target:
        return {"ok": False, "html": "", "text": "", "url": "", "error": "empty_url"}
    if not browser_available():
        return {
            "ok": False,
            "html": "",
            "text": "",
            "url": target,
            "error": "browser_unavailable",
        }

    async with _slot_sem():
        try:
            browser = await _ensure_browser()
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1024, "height": 720},
                java_script_enabled=True,
            )
            page = await context.new_page()
            try:
                await page.goto(target, wait_until=wait_until, timeout=timeout_ms)
                # Skip networkidle — it holds Chromium longer for little gain.
                if click_menu:
                    await _try_open_mobile_menu(page)
                html = await page.content()
                text = ""
                try:
                    text = await page.inner_text("body")
                except Exception:
                    text = ""
                return {
                    "ok": True,
                    "html": html or "",
                    "text": text or "",
                    "url": page.url or target,
                    "error": "",
                }
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
        except Exception as exc:
            log.debug("browser_fetch failed for %s: %s", target, exc)
            return {
                "ok": False,
                "html": "",
                "text": "",
                "url": target,
                "error": str(exc)[:200],
            }
        finally:
            if _ephemeral():
                global _lock
                if _lock is None:
                    _lock = asyncio.Lock()
                async with _lock:
                    await _close_browser()
            else:
                await _schedule_idle_close()


async def _try_open_mobile_menu(page) -> None:
    selectors = (
        "button[aria-label*='menu' i]",
        "button[aria-label*='Menu' i]",
        "button.navbar-toggler",
        ".navbar-toggler",
        ".hamburger",
        ".menu-toggle",
        "#menu-toggle",
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            if not await loc.is_visible(timeout=250):
                continue
            await loc.click(timeout=700)
            await page.wait_for_timeout(150)
            return
        except Exception:
            continue
