"""Find public contact channels on a company website (emails, phones, contact pages)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse, unquote

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
}

EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)
# Obfuscated: sales [at] brand.com / sales(at)brand.com / sales AT brand DOT com
OBFUSCATED_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+\-]{1,64})\s*(?:\[?\s*at\s*\]?|\(\s*at\s\)|\s+at\s+)\s*"
    r"([a-zA-Z0-9.\-]{1,120})\s*(?:\[?\s*dot\s*\]?|\(\s*dot\s\)|\s+dot\s+|\.)\s*"
    r"([a-zA-Z]{2,})\b",
    re.I,
)
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,4}\)?[\s\-.]?)?\d{3,4}[\s\-.]?\d{3,4}"
)
JUNK_EMAIL_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
)
JUNK_EMAIL_LOCAL = (
    "example", "email", "domain", "sentry", "wixpress", "webpack", "noreply", "no-reply",
)
JUNK_EMAIL_DOMAINS = (
    "example.com", "email.com", "domain.com", "yoursite.com",
    "sentry.io", "wixpress.com", "cloudflare.com", "schema.org",
)
PREFERRED_LOCAL = (
    "sales", "info", "contact", "hello", "enquiry", "inquiry", "wholesale",
    "orders", "b2b", "trade", "office", "admin", "support",
)
CONTACT_PATH_HINTS = (
    "contact", "about", "team", "connect", "get-in-touch", "enquiry", "inquiry",
    "support", "sales", "wholesale", "b2b", "partner",
)
DEFAULT_CONTACT_PATHS = (
    "/contact", "/contact-us", "/contactus", "/about", "/about-us",
    "/pages/contact", "/company/contact",
)


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _clean_email(raw: str) -> Optional[str]:
    email = unquote((raw or "").strip()).lower().rstrip(".,;:)>]\"'")
    email = email.replace(" ", "")
    if not email or "@" not in email:
        return None
    if any(email.endswith(s) for s in JUNK_EMAIL_SUFFIXES):
        return None
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return None
    if any(j in local for j in JUNK_EMAIL_LOCAL):
        return None
    if domain in JUNK_EMAIL_DOMAINS or domain.endswith(".png") or domain.endswith(".jpg"):
        return None
    if local.startswith("u00") or len(local) > 64:
        return None
    return email


def _email_sort_key(email: str, site_domain: str) -> tuple:
    local, _, domain = email.partition("@")
    preferred = 0
    for i, pref in enumerate(PREFERRED_LOCAL):
        if local == pref or local.startswith(pref):
            preferred = len(PREFERRED_LOCAL) - i
            break
    same = 1 if site_domain and (domain == site_domain or domain.endswith("." + site_domain)) else 0
    return (same, preferred, -len(email))


def _rank_emails(emails: List[str], site_domain: str) -> List[str]:
    uniq: List[str] = []
    seen: Set[str] = set()
    for e in emails:
        if e and e not in seen:
            seen.add(e)
            uniq.append(e)
    uniq.sort(key=lambda e: _email_sort_key(e, site_domain), reverse=True)
    return uniq


def _clean_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 8 or len(digits) > 15:
        return None
    return re.sub(r"\s+", " ", (raw or "").strip())[:32]


def _decode_cfemail(hex_str: str) -> Optional[str]:
    """Decode Cloudflare email-protection data-cfemail payloads."""
    try:
        data = bytes.fromhex(hex_str)
    except ValueError:
        return None
    if len(data) < 2:
        return None
    key = data[0]
    decoded = "".join(chr(b ^ key) for b in data[1:])
    return _clean_email(decoded)


def _emails_from_obfuscated(blob: str) -> List[str]:
    out: List[str] = []
    for m in OBFUSCATED_EMAIL_RE.finditer(blob or ""):
        addr = _clean_email(f"{m.group(1)}@{m.group(2)}.{m.group(3)}")
        if addr:
            out.append(addr)
    return out


def _extract_from_html(html: str, page_url: str, site_domain: str) -> Dict[str, Any]:
    emails: List[str] = []
    phones: List[str] = []
    contact_urls: List[str] = []
    seen_e: Set[str] = set()
    seen_p: Set[str] = set()
    seen_u: Set[str] = set()

    raw = html or ""
    # Strip script/style before raw regex — avoids junk like oper@ions.learn from minified JS
    soup_pre = BeautifulSoup(raw, "html.parser")
    for tag in soup_pre(["script", "style", "noscript", "svg"]):
        tag.decompose()
    raw_clean = str(soup_pre)

    for match in EMAIL_RE.findall(raw_clean):
        addr = _clean_email(match)
        if addr and addr not in seen_e:
            seen_e.add(addr)
            emails.append(addr)
    for addr in _emails_from_obfuscated(raw_clean):
        if addr not in seen_e:
            seen_e.add(addr)
            emails.append(addr)

    soup = BeautifulSoup(raw, "html.parser")

    for tag in soup.select("[data-cfemail]"):
        addr = _decode_cfemail(tag.get("data-cfemail") or "")
        if addr and addr not in seen_e:
            seen_e.add(addr)
            emails.append(addr)

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        low = href.lower()
        if low.startswith("mailto:"):
            addr = _clean_email(href.split(":", 1)[1].split("?", 1)[0])
            if addr and addr not in seen_e:
                seen_e.add(addr)
                emails.insert(0, addr)
        elif "cdn-cgi/l/email-protection#" in low:
            frag = href.split("#", 1)[-1]
            addr = _decode_cfemail(frag)
            if addr and addr not in seen_e:
                seen_e.add(addr)
                emails.insert(0, addr)
        elif low.startswith("tel:"):
            phone = _clean_phone(href.split(":", 1)[1])
            if phone and phone not in seen_p:
                seen_p.add(phone)
                phones.append(phone)
        else:
            abs_url = urljoin(page_url, href)
            path = (urlparse(abs_url).path or "").lower()
            if any(h in path for h in CONTACT_PATH_HINTS) and _domain(abs_url) == site_domain:
                if abs_url not in seen_u and abs_url.rstrip("/") != page_url.rstrip("/"):
                    seen_u.add(abs_url)
                    contact_urls.append(abs_url)

    text = soup.get_text(" ", strip=True)
    for match in EMAIL_RE.findall(text):
        addr = _clean_email(match)
        if addr and addr not in seen_e:
            seen_e.add(addr)
            emails.append(addr)
    for addr in _emails_from_obfuscated(text):
        if addr not in seen_e:
            seen_e.add(addr)
            emails.append(addr)

    for match in PHONE_RE.findall(text[:4000]):
        phone = _clean_phone(match)
        if phone and phone not in seen_p:
            seen_p.add(phone)
            phones.append(phone)

    emails = _rank_emails(emails, site_domain)
    return {
        "emails": emails[:8],
        "phones": phones[:3],
        "contact_urls": contact_urls[:6],
    }


def contacts_from_text(
    text: str,
    website: str = "",
    seed_phone: str = "",
    seed_emails: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Cheap email/phone extract from already-fetched page text (no HTTP)."""
    site_domain = _domain(website) if website else ""
    emails: List[str] = []
    for raw in seed_emails or []:
        addr = _clean_email(raw)
        if addr and addr not in emails:
            emails.append(addr)
    phones: List[str] = []
    for match in EMAIL_RE.findall(text or ""):
        addr = _clean_email(match)
        if addr and addr not in emails:
            emails.append(addr)
    for addr in _emails_from_obfuscated(text or ""):
        if addr not in emails:
            emails.append(addr)
    emails = _rank_emails(emails, site_domain)
    for match in PHONE_RE.findall((text or "")[:4000]):
        phone = _clean_phone(match)
        if phone and phone not in phones:
            phones.append(phone)
    if seed_phone and seed_phone not in phones:
        phones.insert(0, seed_phone)

    contacts: List[Dict[str, Any]] = []
    for e in emails[:5]:
        contacts.append({
            "type": "email",
            "value": e,
            "label": "Email",
            "source": "site",
            "role": "general",
        })
    for p in phones[:3]:
        contacts.append({
            "type": "phone",
            "value": p,
            "label": "Phone",
            "source": "site",
        })
    return {
        "contacts": contacts,
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else (seed_phone or ""),
    }


async def discover_contacts(
    website: str,
    homepage_html: str = "",
    homepage_text: str = "",
    homepage_url: str = "",
    seed_phone: str = "",
    seed_emails: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Return public contacts found on the site.
    Shape: { contacts: [...], email: str, phone: str }
    Always tries /contact when homepage has no email — many sites hide mailto off-home.
    """
    base = (website or "").strip()
    if not base:
        return {"contacts": [], "email": "", "phone": seed_phone or ""}

    if not base.startswith("http"):
        base = "https://" + base
    site_domain = _domain(base)
    page_url = homepage_url or base
    contacts: List[Dict[str, Any]] = []
    emails: List[str] = []
    phones: List[str] = []
    pages_checked = 0

    for raw in seed_emails or []:
        addr = _clean_email(raw)
        if addr and addr not in emails:
            emails.append(addr)

    if homepage_text:
        for match in EMAIL_RE.findall(homepage_text):
            addr = _clean_email(match)
            if addr and addr not in emails:
                emails.append(addr)
        for addr in _emails_from_obfuscated(homepage_text):
            if addr not in emails:
                emails.append(addr)
        for match in PHONE_RE.findall(homepage_text[:4000]):
            phone = _clean_phone(match)
            if phone and phone not in phones:
                phones.append(phone)

    html = homepage_html or ""
    if not html:
        # Prefer fetching homepage HTML so mailto: hrefs are not missed
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=HEADERS) as client:
                res = await client.get(base)
                if res.status_code == 200 and res.text:
                    html = res.text
                    page_url = str(res.url)
        except Exception:
            html = ""

    found_urls: List[str] = []
    if html:
        pages_checked += 1
        extracted = _extract_from_html(html, page_url, site_domain)
        for e in extracted["emails"]:
            if e not in emails:
                emails.append(e)
        for p in extracted["phones"]:
            if p not in phones:
                phones.append(p)
        found_urls = list(extracted["contact_urls"])

    if not emails:
        for path in DEFAULT_CONTACT_PATHS:
            guess = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
            if guess not in found_urls:
                found_urls.append(guess)

    # Follow contact/about pages when homepage lacked an email
    extra = [] if emails else found_urls[:3]
    if extra:
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=HEADERS) as client:
                for url in extra:
                    try:
                        res = await client.get(url)
                        if res.status_code != 200 or not res.text:
                            continue
                        pages_checked += 1
                        extracted = _extract_from_html(res.text, str(res.url), site_domain)
                        for e in extracted["emails"]:
                            if e not in emails:
                                emails.append(e)
                        for p in extracted["phones"]:
                            if p not in phones:
                                phones.append(p)
                        contacts.append({
                            "type": "url",
                            "value": str(res.url),
                            "label": "Contact page",
                            "source": "site",
                        })
                        if emails:
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    emails = _rank_emails(emails, site_domain)
    for e in emails[:5]:
        contacts.append({
            "type": "email",
            "value": e,
            "label": "Email",
            "source": "site",
            "role": "general",
        })
    if seed_phone and seed_phone not in phones:
        phones.insert(0, seed_phone)
    for p in phones[:3]:
        contacts.append({
            "type": "phone",
            "value": p,
            "label": "Phone",
            "source": "site" if p != seed_phone else "maps",
        })
    for u in found_urls[:3]:
        if not any(c.get("value") == u for c in contacts):
            contacts.append({
                "type": "url",
                "value": u,
                "label": "Contact page",
                "source": "site",
            })

    primary_email = emails[0] if emails else ""
    primary_phone = phones[0] if phones else (seed_phone or "")
    return {
        "contacts": contacts[:12],
        "email": primary_email,
        "phone": primary_phone,
        "pagesChecked": pages_checked,
    }
