"""Optional Playwright-rendered HTML fetch for JS-heavy sites.

Used only as a fallback after static HTTP contact discovery misses.
Gracefully no-ops when Playwright / Chromium are not installed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.config import settings

log = logging.getLogger(__name__)

_browser = None
_playwright = None
_lock = None


def browser_available() -> bool:
    if not getattr(settings, "CONTACT_BROWSER_ENABLED", True):
        return False
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


_LAUNCH_ARGS = (
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-extensions",
)


async def _ensure_browser():
    """Launch bundled Chromium, or fall back to installed Chrome / Edge."""
    global _browser, _playwright, _lock
    if _lock is None:
        import asyncio
        _lock = asyncio.Lock()
    async with _lock:
        if _browser is not None:
            return _browser
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()
        last_err: Exception | None = None
        # Prefer Playwright's Chromium; if CDN install failed, use system browsers.
        for kwargs in (
            {"headless": True, "args": list(_LAUNCH_ARGS)},
            {"channel": "chrome", "headless": True, "args": list(_LAUNCH_ARGS)},
            {"channel": "msedge", "headless": True, "args": list(_LAUNCH_ARGS)},
        ):
            try:
                _browser = await _playwright.chromium.launch(**kwargs)
                log.info("contact browser launched via %s", kwargs.get("channel") or "chromium")
                return _browser
            except Exception as exc:
                last_err = exc
                log.debug("browser launch failed (%s): %s", kwargs.get("channel") or "chromium", exc)
        raise RuntimeError(f"No usable browser: {last_err}")


async def fetch_rendered(
    url: str,
    *,
    timeout_ms: int = 12000,
    wait_until: str = "domcontentloaded",
    click_menu: bool = True,
) -> Dict[str, Any]:
    """
    Render a URL in Chromium and return HTML + visible text.
    Returns {ok, html, text, url, error}. Never raises for expected failures.
    """
    target = (url or "").strip()
    if not target:
        return {"ok": False, "html": "", "text": "", "url": "", "error": "empty_url"}
    if not browser_available():
        return {"ok": False, "html": "", "text": "", "url": target, "error": "browser_unavailable"}

    try:
        browser = await _ensure_browser()
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1365, "height": 900},
            java_script_enabled=True,
        )
        page = await context.new_page()
        try:
            await page.goto(target, wait_until=wait_until, timeout=timeout_ms)
            # Short settle for late client-side content (not a long sleep).
            try:
                await page.wait_for_load_state("networkidle", timeout=min(4000, timeout_ms // 2))
            except Exception:
                pass
            if click_menu:
                await _try_open_mobile_menu(page)
            html = await page.content()
            text = ""
            try:
                text = await page.inner_text("body")
            except Exception:
                text = ""
            final = page.url or target
            return {"ok": True, "html": html or "", "text": text or "", "url": final, "error": ""}
        finally:
            await context.close()
    except Exception as exc:
        log.debug("browser_fetch failed for %s: %s", target, exc)
        return {"ok": False, "html": "", "text": "", "url": target, "error": str(exc)[:200]}


async def _try_open_mobile_menu(page) -> None:
    """Best-effort: expand hamburger / mobile nav so hidden Contact links enter the DOM."""
    selectors = (
        "button[aria-label*='menu' i]",
        "button[aria-label*='Menu' i]",
        "button[aria-label*='navigation' i]",
        "[aria-controls*='menu' i]",
        ".hamburger",
        ".menu-toggle",
        "#menu-toggle",
        "button.navbar-toggler",
        ".navbar-toggler",
        "[data-action='toggle-nav']",
        "button[class*='menu-btn']",
        "a[class*='menu-toggle']",
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            if not await loc.is_visible(timeout=300):
                continue
            await loc.click(timeout=800)
            await page.wait_for_timeout(250)
            return
        except Exception:
            continue


async def try_open_contact_modal(page_or_url: Any = None) -> Optional[str]:
    """Reserved hook — modal emails are captured from rendered DOM text instead."""
    return None
