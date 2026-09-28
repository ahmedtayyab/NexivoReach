"""Optional rendered HTML fetch for JS-heavy contact pages.

Used only when static HTTP finds no email. Prefer Playwright Chromium;
fall back to installed Chrome / Edge. No-ops if Playwright is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import settings

log = logging.getLogger(__name__)

_browser = None
_playwright = None
_lock = None

_LAUNCH_ARGS = (
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-extensions",
)


def browser_available() -> bool:
    if not getattr(settings, "CONTACT_BROWSER_ENABLED", True):
        return False
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


async def _ensure_browser():
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
        for kwargs in (
            {"headless": True, "args": list(_LAUNCH_ARGS)},
            {"channel": "chrome", "headless": True, "args": list(_LAUNCH_ARGS)},
            {"channel": "msedge", "headless": True, "args": list(_LAUNCH_ARGS)},
        ):
            try:
                _browser = await _playwright.chromium.launch(**kwargs)
                log.info(
                    "contact browser via %s",
                    kwargs.get("channel") or "chromium",
                )
                return _browser
            except Exception as exc:
                last_err = exc
        raise RuntimeError(f"No usable browser: {last_err}")


async def fetch_rendered(
    url: str,
    *,
    timeout_ms: int = 10000,
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
            try:
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=min(3500, timeout_ms // 2),
                )
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
            return {
                "ok": True,
                "html": html or "",
                "text": text or "",
                "url": page.url or target,
                "error": "",
            }
        finally:
            await context.close()
    except Exception as exc:
        log.debug("browser_fetch failed for %s: %s", target, exc)
        return {
            "ok": False,
            "html": "",
            "text": "",
            "url": target,
            "error": str(exc)[:200],
        }


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
            await page.wait_for_timeout(200)
            return
        except Exception:
            continue
