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
