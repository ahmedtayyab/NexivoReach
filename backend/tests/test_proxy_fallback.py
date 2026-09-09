"""Catalog scraping must survive a host that firewalls our egress IP."""
import asyncio

import httpx
import pytest

from app.tools import web_search
from app.tools.web_search import WebSearchTool

BLOCKED_HOST = "blocked-shop.example"
REST_PATH = "/wp-json/wp/v2/product"

PAGE_ONE = [
    {"id": 1, "slug": "widget-a", "link": f"https://{BLOCKED_HOST}/product/widget-a/",
     "title": {"rendered": "Widget A"}, "excerpt": {"rendered": "<p>First widget</p>"}},
    {"id": 2, "slug": "widget-b", "link": f"https://{BLOCKED_HOST}/product/widget-b/",
     "title": {"rendered": "Widget B"}, "excerpt": {"rendered": "<p>Second widget</p>"}},
]
PAGE_TWO = [
    {"id": 3, "slug": "widget-c", "link": f"https://{BLOCKED_HOST}/product/widget-c/",
     "title": {"rendered": "Widget C"}, "excerpt": {"rendered": "<p>Third widget</p>"}},
]

PROXY_URL = "https://worker.test/"
PROXY_TOKEN = "s3cret"


def _worker(request: httpx.Request) -> httpx.Response:
    """Stand-in for infra/cloudflare-worker/worker.js."""
    if request.headers.get("X-Proxy-Token") != PROXY_TOKEN:
        return httpx.Response(403, text="Forbidden")
    target = httpx.URL(str(request.url)).params.get("url")
    if not target:
        return httpx.Response(400, text="Missing ?url=")
    upstream = httpx.URL(target)
    if upstream.path != REST_PATH:
        return httpx.Response(404, text="Not found")
    page = upstream.params.get("page", "1")
    body = PAGE_ONE if page == "1" else PAGE_TWO
    return httpx.Response(
        200,
        json=body,
        headers={"X-WP-TotalPages": "2", "X-Proxy-Final-Url": target},
    )


def _transport(direct_blocked: bool) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "worker.test":
            return _worker(request)
        if direct_blocked:
            raise httpx.ConnectTimeout("", request=request)
        return _worker(
            httpx.Request(
                "GET",
                httpx.URL(PROXY_URL, params={"url": str(request.url)}),
                headers={"X-Proxy-Token": PROXY_TOKEN},
            )
        )
    return httpx.MockTransport(handler)


@pytest.fixture
def patched(monkeypatch):
    def install(direct_blocked: bool, proxy_configured: bool):
        monkeypatch.setattr(
            web_search.settings, "SCRAPE_PROXY_URL", PROXY_URL if proxy_configured else "", raising=False
        )
        monkeypatch.setattr(
            web_search.settings, "SCRAPE_PROXY_TOKEN", PROXY_TOKEN if proxy_configured else "", raising=False
        )
        real_init = httpx.AsyncClient.__init__

        def init(self, *args, **kwargs):
            kwargs["transport"] = _transport(direct_blocked)
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", init)
    return install


def test_relays_through_proxy_when_host_blocks_us(patched):
    patched(direct_blocked=True, proxy_configured=True)
    tool = WebSearchTool()
    _, products = asyncio.run(tool.scrape_shop_catalog(f"https://{BLOCKED_HOST}/"))
    assert [p["name"] for p in products] == [
        "Widget A (widget-a)", "Widget B (widget-b)", "Widget C (widget-c)",
    ]
    assert tool.last_catalog_error == ""


def test_reports_unreachable_when_no_proxy_configured(patched):
    patched(direct_blocked=True, proxy_configured=False)
    tool = WebSearchTool()
    _, products = asyncio.run(tool.scrape_shop_catalog(f"https://{BLOCKED_HOST}/"))
    assert products == []
    assert tool.last_catalog_error == "unreachable"


def test_skips_proxy_when_direct_fetch_works(patched):
    patched(direct_blocked=False, proxy_configured=True)
    tool = WebSearchTool()
    _, products = asyncio.run(tool.scrape_shop_catalog(f"https://{BLOCKED_HOST}/"))
    assert len(products) == 3
    assert tool.last_catalog_error == ""
