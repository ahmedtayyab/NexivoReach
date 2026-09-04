"""Find public contact channels on a company website (emails, phones, contact pages)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple
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
OBFUSCATED_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+\-]{1,64})\s*(?:\[\s*at\s*\]|\(\s*at\s\)|\s+at\s+)\s*"
    r"([a-zA-Z0-9.\-]{2,120})\s*(?:\[\s*dot\s*\]|\(\s*dot\s\)|\s+dot\s+)\s*"
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
    "example", "email", "domain", "sentry", "wixpress", "webpack",
    "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon",
    "postmaster", "abuse", "webmaster",
)
JUNK_EMAIL_DOMAINS = (
    "example.com", "email.com", "domain.com", "yoursite.com",
    "sentry.io", "wixpress.com", "cloudflare.com", "schema.org",
    "google.com", "gmail.com", "googleapis.com", "gstatic.com",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com",
    "github.com", "gravatar.com", "wix.com", "squarespace.com",
    "shopify.com", "myshopify.com", "wordpress.com", "wp.com",
    "sentry-next.wixpress.com",
)
# Prefer buyer-facing inboxes when ranking same-quality hits
PREFERRED_LOCAL = (
    "sales", "info", "contact", "hello", "enquiry", "inquiry", "wholesale",
    "orders", "b2b", "trade", "office", "support",
)
CONTACT_PATH_HINTS = (
    "contact", "get-in-touch", "enquiry", "inquiry", "connect",
    "about-us", "about", "team", "support", "sales", "wholesale", "b2b",
)
# Prefer true contact pages before about/team
DEFAULT_CONTACT_PATHS = (
    "/contact", "/contact-us", "/contactus", "/pages/contact",
    "/company/contact", "/get-in-touch", "/enquiry", "/inquiry",
    "/about", "/about-us",
)

# Provenance weights — contact-page mailto beats homepage footer noise
SRC_MAILTO = 40
SRC_CF = 35
SRC_TEXT = 15
SRC_OBFUSCATED = 12
SRC_SEED = 10
PAGE_CONTACT = 50  # bonus when found on /contact
PAGE_HOME = 0


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_same_domain(email_domain: str, site_domain: str) -> bool:
    if not email_domain or not site_domain:
        return False
    ed = email_domain.lower()
    sd = site_domain.lower()
    return ed == sd or ed.endswith("." + sd)


def _path_is_contact(url: str) -> bool:
    path = (urlparse(url or "").path or "").lower()
    return any(
        h in path
        for h in (
            "contact", "get-in-touch", "enquiry", "inquiry", "connect-with",
        )
    )


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
    if local in JUNK_EMAIL_LOCAL or any(
        local.startswith(j + "-") or local.startswith(j + ".")
        for j in ("noreply", "no-reply", "donotreply")
    ):
        return None
    if any(j in local for j in ("noreply", "no-reply", "donotreply", "mailer-daemon")):
        return None
    if domain in JUNK_EMAIL_DOMAINS or any(domain.endswith("." + d) for d in JUNK_EMAIL_DOMAINS):
        return None
    if domain.endswith(".png") or domain.endswith(".jpg"):
        return None
    if local.startswith("u00") or len(local) > 64:
        return None
    # Reject lookalike fragments from minified JS (oper@ions.learn)
    if domain.count(".") == 0 or len(domain.split(".")[-1]) < 2:
        return None
    tld = domain.rsplit(".", 1)[-1]
    if tld in ("js", "css", "map", "json", "xml", "learn", "test"):
        return None
    return email


def _local_pref(email: str) -> int:
    local = email.partition("@")[0]
    for i, pref in enumerate(PREFERRED_LOCAL):
        if local == pref or local.startswith(pref + ".") or local.startswith(pref + "-"):
            return len(PREFERRED_LOCAL) - i
    return 0


def _score_hit(
    email: str,
    *,
    site_domain: str,
    source: int,
    page_bonus: int,
) -> Tuple[int, int, int, int]:
    """Higher is better. Tuple used for sorting."""
    _, _, domain = email.partition("@")
    same = 2 if _is_same_domain(domain, site_domain) else 0
    # Off-domain emails are almost never the right contact inbox
    if same == 0:
        return (0, 0, 0, 0)
    return (page_bonus + source + same * 20, _local_pref(email), source, -len(email))


def _rank_scored(hits: List[Dict[str, Any]], site_domain: str) -> List[str]:
    """hits: {email, source, page_bonus}"""
    best: Dict[str, Tuple[int, int, int, int]] = {}
    for h in hits:
        email = h.get("email") or ""
        if not email:
            continue
        score = _score_hit(
            email,
            site_domain=site_domain,
            source=int(h.get("source") or 0),
            page_bonus=int(h.get("page_bonus") or 0),
        )
        if score[0] <= 0 and not _is_same_domain(email.partition("@")[2], site_domain):
            continue
        prev = best.get(email)
        if prev is None or score > prev:
            best[email] = score
    ranked = sorted(best.keys(), key=lambda e: best[e], reverse=True)
    # If nothing same-domain survived, fall back to any cleaned hit (rare)
    if not ranked:
        for h in hits:
            e = h.get("email") or ""
            if e and e not in ranked:
                ranked.append(e)
    return ranked


def _clean_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 8 or len(digits) > 15:
        return None
    return re.sub(r"\s+", " ", (raw or "").strip())[:32]


def _decode_cfemail(hex_str: str) -> Optional[str]:
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


def _extract_from_html(
    html: str,
    page_url: str,
    site_domain: str,
    *,
    page_bonus: int = PAGE_HOME,
) -> Dict[str, Any]:
    hits: List[Dict[str, Any]] = []
    phones: List[str] = []
    contact_urls: List[str] = []
    seen_e: Set[str] = set()
    seen_p: Set[str] = set()
    seen_u: Set[str] = set()

    def add(email: Optional[str], source: int) -> None:
        if not email or email in seen_e:
            return
        # Prefer same-domain; keep off-domain only from explicit mailto (rare partner)
        ed = email.partition("@")[2]
        if not _is_same_domain(ed, site_domain) and source < SRC_MAILTO:
            return
        if not _is_same_domain(ed, site_domain) and source == SRC_MAILTO:
            # mailto to gmail/etc. — keep only if no site domain later; mark weak
            pass
        seen_e.add(email)
        hits.append({"email": email, "source": source, "page_bonus": page_bonus})

    raw = html or ""
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()

    for tag in soup.select("[data-cfemail]"):
        add(_decode_cfemail(tag.get("data-cfemail") or ""), SRC_CF)

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        low = href.lower()
        if low.startswith("mailto:"):
            add(_clean_email(href.split(":", 1)[1].split("?", 1)[0]), SRC_MAILTO)
        elif "cdn-cgi/l/email-protection#" in low:
            add(_decode_cfemail(href.split("#", 1)[-1]), SRC_CF)
        elif low.startswith("tel:"):
            phone = _clean_phone(href.split(":", 1)[1])
            if phone and phone not in seen_p:
                seen_p.add(phone)
                phones.append(phone)
        else:
            abs_url = urljoin(page_url, href)
            path = (urlparse(abs_url).path or "").lower()
            if any(h in path for h in CONTACT_PATH_HINTS) and _domain(abs_url) == site_domain:
                if abs_url not in seen_u and abs_url.rstrip("/") != (page_url or "").rstrip("/"):
                    seen_u.add(abs_url)
                    contact_urls.append(abs_url)

    # Visible text only (scripts already removed)
    text = soup.get_text(" ", strip=True)
    for match in EMAIL_RE.findall(text):
        add(_clean_email(match), SRC_TEXT)
    for addr in _emails_from_obfuscated(text):
        add(addr, SRC_OBFUSCATED)

    for match in PHONE_RE.findall(text[:4000]):
        phone = _clean_phone(match)
        if phone and phone not in seen_p:
            seen_p.add(phone)
            phones.append(phone)

    # Contact-page links: put true /contact before /about
    contact_urls.sort(key=lambda u: (0 if _path_is_contact(u) else 1, u))

    emails = _rank_scored(hits, site_domain)
    return {
        "emails": emails[:8],
        "hits": hits,
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
    hits: List[Dict[str, Any]] = []
    for raw in seed_emails or []:
        addr = _clean_email(raw)
        if addr:
            hits.append({"email": addr, "source": SRC_SEED, "page_bonus": PAGE_HOME})
    for match in EMAIL_RE.findall(text or ""):
        addr = _clean_email(match)
        if addr:
            hits.append({"email": addr, "source": SRC_TEXT, "page_bonus": PAGE_HOME})
    for addr in _emails_from_obfuscated(text or ""):
        hits.append({"email": addr, "source": SRC_OBFUSCATED, "page_bonus": PAGE_HOME})
    emails = _rank_scored(hits, site_domain)
    phones: List[str] = []
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
    Always opens /contact (when linked or guessed) so contact-page emails win
    over homepage footer / widget addresses.
    """
    base = (website or "").strip()
    if not base:
        return {"contacts": [], "email": "", "phone": seed_phone or ""}

    if not base.startswith("http"):
        base = "https://" + base
    site_domain = _domain(base)
    page_url = homepage_url or base
    contacts: List[Dict[str, Any]] = []
    all_hits: List[Dict[str, Any]] = []
    phones: List[str] = []
    pages_checked = 0
    contact_page_urls: List[str] = []

    for raw in seed_emails or []:
        addr = _clean_email(raw)
        if addr:
            all_hits.append({"email": addr, "source": SRC_SEED, "page_bonus": PAGE_HOME})

    if homepage_text:
        for match in EMAIL_RE.findall(homepage_text):
            addr = _clean_email(match)
            if addr:
                all_hits.append({"email": addr, "source": SRC_TEXT, "page_bonus": PAGE_HOME})
        for match in PHONE_RE.findall(homepage_text[:4000]):
            phone = _clean_phone(match)
            if phone and phone not in phones:
                phones.append(phone)

    html = homepage_html or ""
    if not html:
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
        extracted = _extract_from_html(html, page_url, site_domain, page_bonus=PAGE_HOME)
        all_hits.extend(extracted.get("hits") or [])
        for p in extracted["phones"]:
            if p not in phones:
                phones.append(p)
        found_urls = list(extracted["contact_urls"])

    # Always try real contact pages — even when homepage already had an email
    for path in DEFAULT_CONTACT_PATHS:
        guess = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
        if guess not in found_urls:
            found_urls.append(guess)
    found_urls.sort(key=lambda u: (0 if _path_is_contact(u) else 1, u))
    extra = found_urls[:3]

    if extra:
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=HEADERS) as client:
                for url in extra:
                    try:
                        res = await client.get(url)
                        if res.status_code != 200 or not res.text:
                            continue
                        # Skip soft-404s that bounce to homepage with tiny body change
                        final = str(res.url)
                        pages_checked += 1
                        bonus = PAGE_CONTACT if _path_is_contact(final) or _path_is_contact(url) else PAGE_HOME + 10
                        extracted = _extract_from_html(
                            res.text, final, site_domain, page_bonus=bonus,
                        )
                        page_emails = extracted.get("emails") or []
                        all_hits.extend(extracted.get("hits") or [])
                        for p in extracted["phones"]:
                            if p not in phones:
                                phones.append(p)
                        if page_emails or _path_is_contact(final):
                            contact_page_urls.append(final)
                            contacts.append({
                                "type": "url",
                                "value": final,
                                "label": "Contact page",
                                "source": "site",
                            })
                        # Stop early once contact page yielded a same-domain email
                        if page_emails and bonus >= PAGE_CONTACT:
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    emails = _rank_scored(all_hits, site_domain)
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
    for u in (contact_page_urls or found_urls)[:3]:
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
