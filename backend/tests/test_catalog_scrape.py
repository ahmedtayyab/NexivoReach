"""Fixture tests for the catalog scrape cascade (no live network)."""
import asyncio

import httpx
import pytest

from app.tools import web_search
from app.tools.web_search import (
    WebSearchTool,
    _looks_like_product_url,
    _pagination_urls,
    _parse_sitemap_xml,
    _shop_products,
    _shopify_row_to_product,
)

HOST = "shop.test"


SHOPIFY_PAGE_1 = {
    "products": [
        {
            "id": 1,
            "title": "Ceramic Mug",
            "handle": "ceramic-mug",
            "body_html": "<p>Hand-thrown mug</p>",
            "product_type": "Drinkware",
            "tags": "gift, kitchen",
            "images": [{"src": "https://cdn.shop.test/mug.jpg"}],
            "variants": [{"price": "18.00"}],
        },
        {
            "id": 2,
            "title": "Linen Napkin",
            "handle": "linen-napkin",
            "body_html": "",
            "product_type": "Table",
            "tags": "",
            "images": [],
            "variants": [{"price": "12.00"}],
        },
    ]
}

SHOPIFY_PAGE_2 = {
    "products": [
        {
            "id": 3,
            "title": "Soy Candle",
            "handle": "soy-candle",
            "body_html": "<p>Lavender</p>",
            "product_type": "Home",
            "tags": "gift",
            "image": {"src": "https://cdn.shop.test/candle.jpg"},
            "variants": [{"price": "22.00"}],
        },
    ]
}

LISTING_PAGE_1 = """
<html><body>
<ul class="products">
  <li class="product">
    <a href="/product/alpha-widget/"><h2>Alpha Widget</h2></a>
    <span class="price">$10</span>
  </li>
  <li class="product">
    <a href="/product/beta-widget/"><h2>Beta Widget</h2></a>
  </li>
</ul>
<a rel="next" href="/shop/?page=2">Next</a>
</body></html>
"""

LISTING_PAGE_2 = """
<html><body>
<ul class="products">
  <li class="product">
    <a href="/product/gamma-widget/"><h2>Gamma Widget</h2></a>
  </li>
</ul>
</body></html>
"""

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://shop.test/products/red-vase</loc></url>
  <url><loc>https://shop.test/products/blue-bowl</loc></url>
  <url><loc>https://shop.test/collections/all</loc></url>
  <url><loc>https://shop.test/pages/about</loc></url>
</urlset>
"""

HOME_HTML = """
<html><body>
<a href="/collections/gifts">Gifts</a>
<a href="/shop">Shop</a>
<div class="product-card">
  <a href="/products/home-sample"><h3>Home Sample</h3></a>
</div>
</body></html>
"""


def _transport_html_cascade() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/") or "/"
        qs_page = request.url.params.get("page")
        if path == "/products.json":
            return httpx.Response(404, text="no")
        if path.startswith("/wp-json"):
            return httpx.Response(404, text="no")
        if path == "/sitemap.xml":
            return httpx.Response(200, text=SITEMAP_XML, headers={"content-type": "application/xml"})
        if path == "/shop" and qs_page == "2":
            return httpx.Response(200, text=LISTING_PAGE_2)
        if path == "/shop":
            return httpx.Response(200, text=LISTING_PAGE_1)
        if path in ("/", ""):
            return httpx.Response(200, text=HOME_HTML)
        if path.startswith("/collections/"):
            return httpx.Response(200, text=LISTING_PAGE_1)
        return httpx.Response(404, text="missing")

    return httpx.MockTransport(handler)


@pytest.fixture
def patch_client(monkeypatch):
    def install(transport: httpx.MockTransport):
        monkeypatch.setattr(web_search.settings, "SCRAPE_PROXY_URL", "", raising=False)
        monkeypatch.setattr(web_search.settings, "SCRAPE_PROXY_TOKEN", "", raising=False)
        real_init = httpx.AsyncClient.__init__

        def init(self, *args, **kwargs):
            kwargs["transport"] = transport
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", init)

    return install


def test_shopify_row_mapping():
    row = SHOPIFY_PAGE_1["products"][0]
    product = _shopify_row_to_product(row, "https://shop.test")
    assert product is not None
    assert product["name"] == "Ceramic Mug"
    assert product["productUrl"] == "https://shop.test/products/ceramic-mug"
    assert product["category"] == "Drinkware"
    assert product["price"] == "18.00"
    assert "mug.jpg" in product["imageUrl"]


def test_shopify_products_json_cascade(patch_client):
    # products.json stops when a page returns <250 items — pad page 1 to force page 2.
    page1_products = []
    for i in range(250):
        page1_products.append({
            "id": i + 1,
            "title": f"Item {i + 1}",
            "handle": f"item-{i + 1}",
            "body_html": "",
            "product_type": "General",
            "tags": "",
            "images": [],
            "variants": [{"price": "1.00"}],
        })

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/products.json":
            page = request.url.params.get("page", "1")
            if page == "1":
                return httpx.Response(200, json={"products": page1_products})
            if page == "2":
                return httpx.Response(200, json=SHOPIFY_PAGE_2)
            return httpx.Response(200, json={"products": []})
        return httpx.Response(404, text="missing")

    patch_client(httpx.MockTransport(handler))
    tool = WebSearchTool()
    pages, products = asyncio.run(tool.scrape_shop_catalog(f"https://{HOST}/"))
    names = [p["name"] for p in products]
    assert len(products) == 251
    assert names[-1] == "Soy Candle"
    assert any("products.json" in u for u, _ in pages)
    assert tool.last_catalog_error == ""


def test_sitemap_parse_filters_products():
    locs, children = _parse_sitemap_xml(SITEMAP_XML, "https://shop.test")
    assert children == []
    assert "https://shop.test/products/red-vase" in locs
    assert "https://shop.test/products/blue-bowl" in locs
    product_only = [u for u in locs if _looks_like_product_url(u)]
    assert product_only == [
        "https://shop.test/products/red-vase",
        "https://shop.test/products/blue-bowl",
    ]
    assert not _looks_like_product_url("https://shop.test/pages/about")
    assert not _looks_like_product_url("https://shop.test/collections/all")


def test_pagination_urls_rel_next():
    urls = _pagination_urls(LISTING_PAGE_1, "https://shop.test/shop/")
    assert any("page=2" in u for u in urls)


def test_shop_products_woo_cards():
    found = _shop_products(LISTING_PAGE_1, "https://shop.test/shop/", set())
    assert {p["name"] for p in found} == {"Alpha Widget", "Beta Widget"}


def test_html_cascade_uses_sitemap_and_pagination(patch_client):
    patch_client(_transport_html_cascade())
    tool = WebSearchTool()
    pages, products = asyncio.run(tool.scrape_shop_catalog(f"https://{HOST}/"))
    urls = {p["productUrl"] for p in products}
    names = {p["name"] for p in products}
    assert any("red-vase" in u for u in urls) or "Red Vase" in names
    assert any("blue-bowl" in u for u in urls) or "Blue Bowl" in names
    # Listing crawl should pick Woo cards across pages
    assert "Alpha Widget" in names or "Gamma Widget" in names
    assert tool.last_catalog_error == ""
    assert len(pages) >= 2
