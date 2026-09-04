from app.tools.contact_finder import _clean_email, _extract_from_html, _rank_scored, PAGE_CONTACT, PAGE_HOME, SRC_MAILTO, SRC_TEXT


def test_clean_email_filters_junk():
    assert _clean_email("sales@brand.com") == "sales@brand.com"
    assert _clean_email("foo@example.com") is None
    assert _clean_email("logo@cdn.com.png") is None
    assert _clean_email("noreply@brand.com") is None


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
    """Contact-page mailto must outrank a different homepage address."""
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
