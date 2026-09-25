"""Contact / email discovery regression tests (human-like enrichment)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from app.tools.contact_finder import (
    PAGE_CONTACT,
    PAGE_HOME,
    SRC_MAILTO,
    SRC_TEXT,
    _clean_email,
    _extract_from_html,
    _rank_scored,
    discover_contacts,
    page_type_label,
    score_internal_link,
)


def test_clean_email_filters_junk():
    assert _clean_email("sales@brand.com") == "sales@brand.com"
    assert _clean_email("foo@example.com") is None
    assert _clean_email("logo@cdn.com.png") is None
    assert _clean_email("noreply@brand.com") is None
    assert _clean_email("privacy@brand.com") is None


def test_extract_mailto_and_contact_links():
    html = """
    <html><body>
      <a href="mailto:hello@acmewear.com">Email us</a>
      <a href="/contact-us">Contact</a>
      <p>Call +1 212-555-0199</p>
    </body></html>
    """
    found = _extract_from_html(html, "https://acmewear.com/", "acmewear.com")
    assert "hello@acmewear.com" in found["emails"]
    assert any("contact" in u for u in found["contact_urls"])


def test_extract_obfuscated_and_cfemail():
    plain = "info@brand.com"
    key = 0x0A
    encoded = bytes([key] + [ord(c) ^ key for c in plain]).hex()
    html = f"""
    <html><body>
      <span class="__cf_email__" data-cfemail="{encoded}">[email protected]</span>
      <p>Reach sales [at] brand [dot] com</p>
    </body></html>
    """
    found = _extract_from_html(html, "https://brand.com/", "brand.com")
    assert "info@brand.com" in found["emails"]
    assert "sales@brand.com" in found["emails"]


def test_contact_page_email_beats_homepage_footer():
    hits = [
        {"email": "privacy@brand.com", "source": SRC_TEXT, "page_bonus": PAGE_HOME},
        {"email": "sales@brand.com", "source": SRC_MAILTO, "page_bonus": PAGE_CONTACT},
        {"email": "partner@other.com", "source": SRC_MAILTO, "page_bonus": PAGE_HOME},
    ]
    ranked = _rank_scored(hits, "brand.com")
    assert ranked[0] == "sales@brand.com"
    assert "partner@other.com" not in ranked


def test_off_domain_text_email_dropped():
    html = """
    <html><body>
      <p>Built with help@wix.com and support@google.com</p>
      <a href="mailto:orders@desertmartial.com">Email</a>
    </body></html>
    """
    found = _extract_from_html(html, "https://desertmartial.com/", "desertmartial.com")
    assert found["emails"][0] == "orders@desertmartial.com"
    assert "help@wix.com" not in found["emails"]
    assert "support@google.com" not in found["emails"]


def test_email_split_across_tags():
    html = """
    <html><body>
      <div id="contact" class="contact-section">
        <p>Email us at <span>sales</span>@<span>acmewear.com</span></p>
      </div>
    </body></html>
    """
    found = _extract_from_html(html, "https://acmewear.com/", "acmewear.com")
    assert "sales@acmewear.com" in found["emails"]


def test_jsonld_organization_email():
    html = """
    <html><body>
      <script type="application/ld+json">
        {"@type":"Organization","name":"Acme","email":"hello@acmewear.com",
         "contactPoint":{"@type":"ContactPoint","email":"sales@acmewear.com"}}
      </script>
      <p>Welcome</p>
    </body></html>
    """
    found = _extract_from_html(html, "https://acmewear.com/", "acmewear.com")
    assert "hello@acmewear.com" in found["emails"] or "sales@acmewear.com" in found["emails"]


def test_contact_link_text_discovers_nonobvious_path():
    html = """
    <html><body>
      <a href="/pages/help">Contact Us</a>
      <span itemprop="email">info@acmewear.com</span>
    </body></html>
    """
    found = _extract_from_html(html, "https://acmewear.com/", "acmewear.com")
    assert "info@acmewear.com" in found["emails"]
    assert any("/pages/help" in u for u in found["contact_urls"])


def test_html_entity_at_sign():
    html = """
    <html><body>
      <div class="contact">Write to office&#64;brand.com</div>
    </body></html>
    """
    found = _extract_from_html(html, "https://brand.com/", "brand.com")
    assert "office@brand.com" in found["emails"]


def test_footer_email_and_mailto_are_found():
    html = """
    <html><body>
      <main><h1>Welcome</h1><p>We sell gear.</p></main>
      <footer class="site-footer">
        <p>Email: sales@sandiegogear.com</p>
        <a href="mailto:info@sandiegogear.com">info</a>
        <a href="https://www.facebook.com/sandiegogear">Facebook</a>
      </footer>
    </body></html>
    """
    found = _extract_from_html(html, "https://sandiegogear.com/", "sandiegogear.com")
    assert "sales@sandiegogear.com" in found["emails"] or "info@sandiegogear.com" in found["emails"]
    assert any("facebook.com" in u for u in found.get("social_urls") or [])
    footer_hits = [h for h in found["hits"] if h.get("region") == "footer" or h.get("label") == "footer"]
    assert footer_hits


def test_footer_personal_gmail_kept():
    html = """
    <html><body>
      <footer>
        <p>Contact us: orders.sd.fitness@gmail.com</p>
      </footer>
    </body></html>
    """
    found = _extract_from_html(html, "https://sdfitness.example/", "sdfitness.example")
    assert "orders.sd.fitness@gmail.com" in found["emails"]


def test_bottom_of_page_email_without_footer_tag():
    html = """
    <html><body>
      <header>Shop</header>
      <main><p>Products</p></main>
      <div class="site-bottom pre-footer">
        <p>Email sales@bottomgear.com</p>
        <a href="https://www.facebook.com/bottomgear">Follow us</a>
      </div>
    </body></html>
    """
    found = _extract_from_html(html, "https://bottomgear.com/", "bottomgear.com")
    assert "sales@bottomgear.com" in found["emails"]
    assert any("facebook.com" in u for u in found.get("social_urls") or [])


def test_facebook_fetch_urls_prefer_mbasic():
    from app.tools.contact_finder import _facebook_fetch_urls

    urls = _facebook_fetch_urls("https://www.facebook.com/AcmeWearCo")
    assert urls
    assert "mbasic.facebook.com" in urls[0]
    assert any("/about" in u for u in urls)


# --- Spec scenarios 1–8 ---

def test_navbar_email_source():
    """Test 1 — Navbar email → source = navbar."""
    html = """
    <html><body>
      <nav class="main-nav">
        Contact: sales@navbrand.com
      </nav>
      <main><p>Welcome to our store.</p></main>
    </body></html>
    """
    found = _extract_from_html(html, "https://navbrand.com/", "navbrand.com")
    assert "sales@navbrand.com" in found["emails"]
    nav_hits = [h for h in found["hits"] if h.get("email") == "sales@navbrand.com"]
    assert any(h.get("region") == "navbar" or h.get("label") == "navbar" for h in nav_hits)


def test_footer_email_source():
    """Test 2 — Footer email → source = footer."""
    html = """
    <html><body>
      <main><p>Products only here.</p></main>
      <footer>
        info@footerbrand.com
      </footer>
    </body></html>
    """
    found = _extract_from_html(html, "https://footerbrand.com/", "footerbrand.com")
    assert "info@footerbrand.com" in found["emails"]
    hits = [h for h in found["hits"] if h.get("email") == "info@footerbrand.com"]
    assert any(h.get("region") == "footer" for h in hits)


def test_link_scoring_prioritizes_contact_and_skips_blog():
    assert score_internal_link("https://x.com/contact-us", "Contact Us", in_nav=True) >= 100
    assert score_internal_link("https://x.com/pages/about-the-company", "About") >= 70
    assert score_internal_link("https://x.com/blog/post-1", "News") <= 15
    assert page_type_label("https://x.com/wholesale-program") == "wholesale_page"
    assert page_type_label("https://x.com/contact-us-today") == "contact_page"


@pytest.mark.asyncio
async def test_about_page_email_discovery():
    """Test 3 — Homepage empty; About page has email."""
    home = """
    <html><body>
      <nav><a href="/about-us">About Us</a></nav>
      <main><p>We make gear.</p></main>
    </body></html>
    """
    about = """
    <html><body>
      <h1>About</h1>
      <p>Reach us at contact@aboutbrand.com</p>
    </body></html>
    """

    class FakeResp:
        def __init__(self, url: str, text: str, code: int = 200):
            self.status_code = code
            self.text = text
            self.url = url

    async def fake_get(url, *a, **k):
        u = str(url)
        if "about" in u:
            return FakeResp(u, about)
        return FakeResp(u, "<html><body>nope</body></html>", 404)

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            return await fake_get(url)

    with patch("app.tools.contact_finder.httpx.AsyncClient", FakeClient):
        result = await discover_contacts(
            "https://aboutbrand.com",
            homepage_html=home,
            homepage_url="https://aboutbrand.com/",
            use_browser=False,
            max_internal_pages=4,
        )
    assert result["email"] == "contact@aboutbrand.com"
    assert result["emailStatus"] == "found"
    assert "about" in (result.get("emailSource") or "")


@pytest.mark.asyncio
async def test_contact_page_path_discovered():
    """Test 4 — Discover /contact-us from nav."""
    home = """
    <html><body>
      <header><nav>
        <a href="/contact-us">Contact Us</a>
      </nav></header>
      <main><p>Home</p></main>
    </body></html>
    """
    contact = """
    <html><body>
      <h1>Contact</h1>
      <a href="mailto:sales@touchbrand.com">Email sales</a>
    </body></html>
    """

    class FakeResp:
        def __init__(self, url: str, text: str, code: int = 200):
            self.status_code = code
            self.text = text
            self.url = url

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            u = str(url)
            if "contact" in u:
                return FakeResp("https://touchbrand.com/contact-us", contact)
            return FakeResp(u, "<html></html>", 404)

    with patch("app.tools.contact_finder.httpx.AsyncClient", FakeClient):
        result = await discover_contacts(
            "https://touchbrand.com",
            homepage_html=home,
            homepage_url="https://touchbrand.com/",
            use_browser=False,
            max_internal_pages=4,
        )
    assert result["email"] == "sales@touchbrand.com"
    assert result["emailStatus"] == "found"
    assert "contact" in (result.get("emailSource") or "")


@pytest.mark.asyncio
async def test_javascript_rendered_email_fallback():
    """Test 5 — Static miss → rendered scan finds email."""
    static = """
    <html><body>
      <div id="__next"></div>
      <script>/* spa */</script>
    </body></html>
    """
    rendered = """
    <html><body>
      <div id="__next">
        <footer>Email us at render@jsbrand.com</footer>
      </div>
    </body></html>
    """

    class FakeResp:
        def __init__(self, url: str, text: str, code: int = 200):
            self.status_code = code
            self.text = text
            self.url = url

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            return FakeResp(str(url), "<html><body>empty</body></html>", 404)

    async def fake_rendered(url, **kwargs):
        return {"ok": True, "html": rendered, "text": "Email us at render@jsbrand.com", "url": url, "error": ""}

    with patch("app.tools.contact_finder.httpx.AsyncClient", FakeClient):
        with patch("app.tools.browser_fetch.browser_available", return_value=True):
            with patch("app.tools.browser_fetch.fetch_rendered", AsyncMock(side_effect=fake_rendered)):
                result = await discover_contacts(
                    "https://jsbrand.com",
                    homepage_html=static,
                    homepage_url="https://jsbrand.com/",
                    use_browser=True,
                    max_internal_pages=1,
                )
    assert result["email"] == "render@jsbrand.com"
    assert result["emailStatus"] == "found"
    assert result["telemetry"].get("homepageRendered") is True


def test_obfuscated_email_normalized():
    """Test 6 — info [at] example [dot] com."""
    html = """
    <html><body>
      <footer>info [at] examplebrand [dot] com</footer>
    </body></html>
    """
    found = _extract_from_html(html, "https://examplebrand.com/", "examplebrand.com")
    assert "info@examplebrand.com" in found["emails"]


@pytest.mark.asyncio
async def test_facebook_fallback_email():
    """Test 7 — Website has FB link, no email; public FB About has email."""
    home = """
    <html><body>
      <main><p>No email here.</p></main>
      <footer>
        <a href="https://www.facebook.com/fbbrandco">Facebook</a>
      </footer>
    </body></html>
    """
    fb_about = """
    <html><body>
      <div>Email: sales@fbbrand.com</div>
    </body></html>
    """

    class FakeResp:
        def __init__(self, url: str, text: str, code: int = 200):
            self.status_code = code
            self.text = text
            self.url = url

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            u = str(url).lower()
            if "facebook" in u or "mbasic" in u:
                return FakeResp(str(url), fb_about)
            return FakeResp(str(url), "<html><body>nope</body></html>", 404)

    with patch("app.tools.contact_finder.httpx.AsyncClient", FakeClient):
        result = await discover_contacts(
            "https://fbbrand.com",
            homepage_html=home,
            homepage_url="https://fbbrand.com/",
            use_browser=False,
            max_internal_pages=2,
        )
    assert result["email"] == "sales@fbbrand.com"
    assert result["emailStatus"] == "found"
    assert result.get("emailSource") == "facebook"
    assert result["telemetry"].get("facebookChecked") is True
    assert result["telemetry"].get("facebookEmailFound") is True


@pytest.mark.asyncio
async def test_genuine_no_email_company():
    """Test 8 — No public email anywhere → not_found, no guessing."""
    home = """
    <html><body>
      <nav><a href="/about">About</a></nav>
      <main><p>John Smith, CEO</p></main>
      <footer><p>Visit our store.</p></footer>
    </body></html>
    """
    about = """
    <html><body>
      <p>Our team: Jane Doe</p>
      <form><input type="email" placeholder="your email"/></form>
    </body></html>
    """

    class FakeResp:
        def __init__(self, url: str, text: str, code: int = 200):
            self.status_code = code
            self.text = text
            self.url = url

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            u = str(url)
            if "about" in u:
                return FakeResp(u, about)
            return FakeResp(u, "<html></html>", 404)

    with patch("app.tools.contact_finder.httpx.AsyncClient", FakeClient):
        result = await discover_contacts(
            "https://noemailbrand.com",
            homepage_html=home,
            homepage_url="https://noemailbrand.com/",
            use_browser=False,
            max_internal_pages=3,
        )
    assert result["email"] == ""
    assert result["emailStatus"] == "not_found"
    assert "john@" not in str(result.get("contacts")).lower()
    assert "info@noemailbrand.com" not in str(result.get("contacts")).lower()
