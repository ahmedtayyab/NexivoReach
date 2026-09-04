from app.tools.contact_finder import _clean_email, _extract_from_html


def test_clean_email_filters_junk():
    assert _clean_email("sales@brand.com") == "sales@brand.com"
    assert _clean_email("foo@example.com") is None
    assert _clean_email("logo@cdn.com.png") is None


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
    # Cloudflare: key 0x0a, "info@brand.com"
    plain = "info@brand.com"
    key = 0x0A
    encoded = bytes([key] + [ord(c) ^ key for c in plain]).hex()
    html = f"""
    <html><body>
      <span class="__cf_email__" data-cfemail="{encoded}">[email protected]</span>
      <p>Reach sales [at] otherbrand [dot] com</p>
    </body></html>
    """
    found = _extract_from_html(html, "https://brand.com/", "brand.com")
    assert "info@brand.com" in found["emails"]
    assert "sales@otherbrand.com" in found["emails"]
