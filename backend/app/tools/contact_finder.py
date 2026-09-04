"""Find public contact channels on a company website (emails, phones, contact pages)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; NexivoReach/1.0; +https://nexivoreach.onrender.com)"
    ),
}

EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,4}\)?[\s\-.]?)?\d{3,4}[\s\-.]?\d{3,4}"
)
JUNK_EMAIL_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
)
JUNK_EMAIL_LOCAL = ("example", "email", "domain", "sentry", "wixpress", "webpack")
CONTACT_PATH_HINTS = (
    "contact", "about", "team", "connect", "get-in-touch", "enquiry", "inquiry",
    "support", "sales", "wholesale", "b2b", "partner",
)


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _clean_email(raw: str) -> Optional[str]:
    email = (raw or "").strip().lower().rstrip(".,;:)>]")
    if not email or "@" not in email:
        return None
    if any(email.endswith(s) for s in JUNK_EMAIL_SUFFIXES):
        return None
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return None
    if any(j in local for j in JUNK_EMAIL_LOCAL):
        return None
    if domain in ("example.com", "email.com", "domain.com", "yoursite.com"):
        return None
    return email


def _clean_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 8 or len(digits) > 15:
        return None
    return re.sub(r"\s+", " ", (raw or "").strip())[:32]


def _extract_from_html(html: str, page_url: str, site_domain: str) -> Dict[str, Any]:
    emails: List[str] = []
    phones: List[str] = []
    contact_urls: List[str] = []
    seen_e: Set[str] = set()
    seen_p: Set[str] = set()
    seen_u: Set[str] = set()

    soup = BeautifulSoup(html or "", "html.parser")

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href.lower().startswith("mailto:"):
            addr = _clean_email(href.split(":", 1)[1].split("?", 1)[0])
            if addr and addr not in seen_e:
                seen_e.add(addr)
                emails.append(addr)
        elif href.lower().startswith("tel:"):
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
            # Prefer same-domain emails but keep others as secondary
            seen_e.add(addr)
            if site_domain and site_domain in addr.split("@")[-1]:
                emails.insert(0, addr)
            else:
                emails.append(addr)

    for match in PHONE_RE.findall(text[:4000]):
        phone = _clean_phone(match)
        if phone and phone not in seen_p:
            seen_p.add(phone)
            phones.append(phone)

    return {
        "emails": emails[:5],
        "phones": phones[:3],
        "contact_urls": contact_urls[:4],
    }


async def discover_contacts(
    website: str,
    homepage_html: str = "",
    homepage_text: str = "",
    homepage_url: str = "",
    seed_phone: str = "",
) -> Dict[str, Any]:
    """
    Return public contacts found on the site.
    Shape: { contacts: [...], email: str, phone: str }
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

    # Seed from already-fetched homepage text (no extra request)
    if homepage_text:
        for match in EMAIL_RE.findall(homepage_text):
            addr = _clean_email(match)
            if addr and addr not in emails:
                if site_domain and site_domain in addr.split("@")[-1]:
                    emails.insert(0, addr)
                else:
                    emails.append(addr)
        for match in PHONE_RE.findall(homepage_text[:4000]):
            phone = _clean_phone(match)
            if phone and phone not in phones:
                phones.append(phone)

    html = homepage_html or ""
    if not html and not homepage_text:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=HEADERS) as client:
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
        found_urls = extracted["contact_urls"]
    elif homepage_text:
        # Guess common contact paths when we only have text
        for path in ("/contact", "/contact-us", "/about", "/about-us"):
            found_urls.append(urljoin(base.rstrip("/") + "/", path.lstrip("/")))

    # Follow contact/about pages only when homepage text lacked an email
    extra = [] if emails else found_urls[:2]
    if extra:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=HEADERS) as client:
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
                    except Exception:
                        continue
        except Exception:
            pass

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
