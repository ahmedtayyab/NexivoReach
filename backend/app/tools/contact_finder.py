"""Find public contact channels on a company website (emails, phones, contact pages)."""

from __future__ import annotations

import asyncio
import json
import re
from html import unescape
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, unquote

import httpx
from bs4 import BeautifulSoup, Comment

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)
# Catch emails broken by spaces from tag boundaries: sales @ brand . com
LOOSE_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+\-]{1,64})\s*@\s*([a-zA-Z0-9.\-]+)\s*\.\s*([a-zA-Z]{2,})\b"
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
    "google.com", "googleapis.com", "gstatic.com",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com",
    "github.com", "gravatar.com", "wix.com", "squarespace.com",
    "shopify.com", "myshopify.com", "wordpress.com", "wp.com",
    "sentry-next.wixpress.com", "jquery.com", "cloudfront.net",
)
# Free webmail — keep only from mailto / structured contact fields, never raw page noise
PERSONAL_MAIL_DOMAINS = (
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "icloud.com", "aol.com", "protonmail.com", "proton.me",
)
# Prefer buyer-facing inboxes when ranking same-quality hits
PREFERRED_LOCAL = (
    "sales", "info", "contact", "hello", "enquiry", "inquiry", "wholesale",
    "orders", "b2b", "trade", "office", "support",
)
CONTACT_PATH_HINTS = (
    "contact", "get-in-touch", "getintouch", "enquiry", "inquiry", "connect",
    "about-us", "about", "team", "support", "sales", "wholesale", "b2b",
    "customer-service", "customer-care", "reach-us", "reachus", "lets-talk",
    "talk-to-us", "write-to-us", "email-us", "help-center",
)
CONTACT_LINK_TEXT = (
    "contact", "contact us", "contactus", "get in touch", "get in-touch",
    "enquire", "enquiry", "inquiry", "reach us", "email us", "write to us",
    "talk to us", "let's talk", "lets talk", "customer service", "support",
    "sales", "wholesale", "b2b",
)
# Prefer true contact pages before about/team
DEFAULT_CONTACT_PATHS = (
    "/contact", "/contact-us", "/contactus", "/contact/",
    "/pages/contact", "/pages/contact-us", "/pages/contactus",
    "/company/contact", "/company/contact-us",
    "/get-in-touch", "/getintouch", "/enquiry", "/inquiry",
    "/customer-service", "/customer-care", "/reach-us", "/lets-talk",
    "/support/contact", "/en/contact", "/us/contact",
    "/about", "/about-us", "/pages/about", "/pages/about-us",
)

# Provenance weights — contact-page mailto beats homepage footer noise
SRC_MAILTO = 40
SRC_CF = 35
SRC_ATTR = 28
SRC_JSONLD = 26
SRC_TEXT = 15
SRC_OBFUSCATED = 12
SRC_SEED = 10
PAGE_CONTACT = 50  # bonus when found on /contact
PAGE_HOME = 0
PAGE_SECTION = 25  # homepage #contact / contact-looking block


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
            "contact", "get-in-touch", "getintouch", "enquiry", "inquiry",
            "reach-us", "reachus", "lets-talk", "customer-service",
            "customer-care", "email-us", "write-to-us", "talk-to-us",
        )
    )


def _normalize_blob(raw: str) -> str:
    """Decode entities / zero-width chars so regex can see real emails."""
    text = unescape(raw or "")
    for ch in (
        "\u200b", "\u200c", "\u200d", "\ufeff", "\u00ad",
        "\u2028", "\u2029",
    ):
        text = text.replace(ch, "")
    # Common HTML/JS escapes for @
    text = (
        text.replace("&#64;", "@")
        .replace("&#x40;", "@")
        .replace("&#X40;", "@")
        .replace("%40", "@")
        .replace("\\u0040", "@")
        .replace("\\x40", "@")
    )
    return text


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
    # Off-domain emails are almost never the right contact inbox —
    # keep only when found via explicit mailto / contact-page attributes
    if same == 0:
        if page_bonus >= PAGE_CONTACT and source >= SRC_ATTR:
            return (page_bonus + source // 2, _local_pref(email), source, -len(email))
        if source >= SRC_MAILTO and page_bonus >= PAGE_SECTION:
            return (page_bonus + source // 2, _local_pref(email), source, -len(email))
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


def email_from_contacts(contacts: Any) -> str:
    """First usable email stored on a lead's contacts list."""
    for c in contacts or []:
        if not isinstance(c, dict):
            continue
        ctype = (c.get("type") or "").lower().strip()
        val = (c.get("value") or "").strip()
        if val.lower().startswith("mailto:"):
            val = val.split(":", 1)[1].split("?", 1)[0].strip()
            ctype = "email"
        if ctype and ctype not in ("email", "mail", "e-mail"):
            continue
        # typeless value that looks like an email
        if not ctype and "@" not in val:
            continue
        addr = _clean_email(val)
        if addr:
            return addr
    return ""


def resolve_lead_email(
    email: str = "",
    contacts: Any = None,
    to_email: str = "",
) -> str:
    """Resolve recipient: draft To: → lead.email → contacts[]."""
    for candidate in (to_email, email, email_from_contacts(contacts)):
        addr = _clean_email(candidate or "")
        if addr:
            return addr
    return ""


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


def _emails_from_loose(blob: str) -> List[str]:
    out: List[str] = []
    for m in LOOSE_EMAIL_RE.finditer(blob or ""):
        addr = _clean_email(f"{m.group(1)}@{m.group(2)}.{m.group(3)}")
        if addr:
            out.append(addr)
    return out


def _walk_jsonld_emails(node: Any, out: List[str]) -> None:
    if isinstance(node, dict):
        for key, val in node.items():
            lk = str(key).lower()
            if lk in ("email", "emails", "contactemail", "emailaddress") and isinstance(val, str):
                addr = _clean_email(val)
                if addr:
                    out.append(addr)
            elif lk in ("email", "emails") and isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        addr = _clean_email(item)
                        if addr:
                            out.append(addr)
                    else:
                        _walk_jsonld_emails(item, out)
            else:
                _walk_jsonld_emails(val, out)
    elif isinstance(node, list):
        for item in node:
            _walk_jsonld_emails(item, out)


def _emails_from_jsonld(soup: BeautifulSoup) -> List[str]:
    found: List[str] = []
    for tag in soup.find_all("script"):
        t = (tag.get("type") or "").lower()
        if "ld+json" not in t:
            continue
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            # Sometimes multiple JSON objects concatenated
            try:
                data = json.loads(f"[{raw}]")
            except Exception:
                continue
        _walk_jsonld_emails(data, found)
    return found


def _contact_section_bonus(soup: BeautifulSoup, page_bonus: int) -> int:
    """Bump score for emails living inside a contact-looking block on any page."""
    if page_bonus >= PAGE_CONTACT:
        return page_bonus
    for sel in (
        "#contact", "#contact-us", "#contactus", "#get-in-touch",
        "[id*='contact']", "[class*='contact']", "section.contact",
        "footer", "[itemtype*='ContactPoint']",
    ):
        try:
            if soup.select_one(sel):
                return max(page_bonus, PAGE_SECTION)
        except Exception:
            continue
    return page_bonus


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

    def add(email: Optional[str], source: int, bonus: Optional[int] = None) -> None:
        if not email or email in seen_e:
            return
        ed = email.partition("@")[2]
        use_bonus = page_bonus if bonus is None else bonus
        # Prefer same-domain; keep off-domain only from strong signals
        if not _is_same_domain(ed, site_domain) and source < SRC_ATTR:
            return
        # Free webmail only from explicit mailto / microdata / JSON-LD on contact-ish pages
        if ed in PERSONAL_MAIL_DOMAINS and source < SRC_ATTR:
            return
        if ed in PERSONAL_MAIL_DOMAINS and use_bonus < PAGE_SECTION and source < SRC_MAILTO:
            return
        seen_e.add(email)
        hits.append({"email": email, "source": source, "page_bonus": use_bonus})

    raw = _normalize_blob(html or "")
    soup = BeautifulSoup(raw, "html.parser")

    # JSON-LD before stripping scripts — many sites only publish email there
    for addr in _emails_from_jsonld(soup):
        add(addr, SRC_JSONLD)

    section_bonus = _contact_section_bonus(soup, page_bonus)

    for tag in soup(["style", "noscript", "svg", "template"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    # Drop non-JSON scripts (analytics / bundles) but keep nothing else needed
    for tag in soup.find_all("script"):
        t = (tag.get("type") or "").lower()
        if "ld+json" in t:
            continue
        tag.decompose()

    for tag in soup.select("[data-cfemail]"):
        add(_decode_cfemail(tag.get("data-cfemail") or ""), SRC_CF, section_bonus)

    # Explicit email attributes / microdata (common on Contact sections)
    for tag in soup.select("[itemprop=email], [itemprop='email'], [data-email], meta[itemprop=email]"):
        val = (tag.get("content") or tag.get("data-email") or tag.get_text(" ", strip=True) or "").strip()
        add(_clean_email(val), SRC_ATTR, section_bonus)

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        low = href.lower()
        link_text = " ".join((a.get_text(" ", strip=True) or "").lower().split())
        if low.startswith("mailto:"):
            add(_clean_email(href.split(":", 1)[1].split("?", 1)[0]), SRC_MAILTO, section_bonus)
        elif "cdn-cgi/l/email-protection#" in low:
            add(_decode_cfemail(href.split("#", 1)[-1]), SRC_CF, section_bonus)
        elif low.startswith("tel:"):
            phone = _clean_phone(href.split(":", 1)[1])
            if phone and phone not in seen_p:
                seen_p.add(phone)
                phones.append(phone)
        else:
            abs_url = urljoin(page_url, href)
            path = (urlparse(abs_url).path or "").lower()
            frag = (urlparse(abs_url).fragment or "").lower()
            same_site = _domain(abs_url) == site_domain or not _domain(abs_url)
            looks_contact = (
                any(h in path for h in CONTACT_PATH_HINTS)
                or any(h in frag for h in ("contact", "enquiry", "inquiry", "get-in-touch"))
                or link_text in CONTACT_LINK_TEXT
                or any(link_text.startswith(t) for t in CONTACT_LINK_TEXT)
            )
            if same_site and looks_contact:
                # Skip pure same-page anchors — email is on this page already
                if frag and (path in ("", "/") or abs_url.rstrip("/#") == (page_url or "").rstrip("/#")):
                    continue
                if abs_url not in seen_u and abs_url.rstrip("/") != (page_url or "").rstrip("/"):
                    seen_u.add(abs_url)
                    contact_urls.append(abs_url)

    # Visible text: empty separator so <span>sales</span>@<span>x.com</span> stays intact
    text_tight = soup.get_text("", strip=True)
    text_spaced = soup.get_text(" ", strip=True)
    for match in EMAIL_RE.findall(text_tight):
        add(_clean_email(match), SRC_TEXT, section_bonus)
    for addr in _emails_from_loose(text_spaced):
        add(addr, SRC_TEXT, section_bonus)
    for addr in _emails_from_obfuscated(text_spaced):
        add(addr, SRC_OBFUSCATED, section_bonus)

    # Also scan raw HTML attributes (href/title/content) for mailto-less emails
    for match in EMAIL_RE.findall(raw):
        add(_clean_email(match), SRC_TEXT, page_bonus)

    for match in PHONE_RE.findall(text_spaced[:5000]):
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
        "contact_urls": contact_urls[:8],
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
    blob = _normalize_blob(text or "")
    for raw in seed_emails or []:
        addr = _clean_email(raw)
        if addr:
            hits.append({"email": addr, "source": SRC_SEED, "page_bonus": PAGE_HOME})
    for match in EMAIL_RE.findall(blob):
        addr = _clean_email(match)
        if addr:
            hits.append({"email": addr, "source": SRC_TEXT, "page_bonus": PAGE_HOME})
    for addr in _emails_from_loose(blob):
        hits.append({"email": addr, "source": SRC_TEXT, "page_bonus": PAGE_HOME})
    for addr in _emails_from_obfuscated(blob):
        hits.append({"email": addr, "source": SRC_OBFUSCATED, "page_bonus": PAGE_HOME})
    emails = _rank_scored(hits, site_domain)
    phones: List[str] = []
    for match in PHONE_RE.findall(blob[:5000]):
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
        blob = _normalize_blob(homepage_text)
        for match in EMAIL_RE.findall(blob):
            addr = _clean_email(match)
            if addr:
                all_hits.append({"email": addr, "source": SRC_TEXT, "page_bonus": PAGE_HOME})
        for addr in _emails_from_loose(blob):
            all_hits.append({"email": addr, "source": SRC_TEXT, "page_bonus": PAGE_HOME})
        for match in PHONE_RE.findall(blob[:5000]):
            phone = _clean_phone(match)
            if phone and phone not in phones:
                phones.append(phone)

    html = homepage_html or ""
    if not html:
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
        extracted = _extract_from_html(html, page_url, site_domain, page_bonus=PAGE_HOME)
        all_hits.extend(extracted.get("hits") or [])
        for p in extracted["phones"]:
            if p not in phones:
                phones.append(p)
        found_urls = list(extracted["contact_urls"])

    # Linked contact pages first, then common path guesses
    linked = [u for u in found_urls if _path_is_contact(u)]
    other_linked = [u for u in found_urls if u not in linked]
    guesses: List[str] = []
    for path in DEFAULT_CONTACT_PATHS:
        guess = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
        if guess not in linked and guess not in other_linked and guess not in guesses:
            guesses.append(guess)

    ordered = linked + [g for g in guesses if _path_is_contact(g)] + other_linked
    # Dedupe while preserving order
    seen_fetch: Set[str] = set()
    extra: List[str] = []
    for u in ordered:
        key = u.rstrip("/").lower()
        if key in seen_fetch:
            continue
        # Don't re-fetch homepage
        if key == (page_url or "").rstrip("/").lower() or key == base.rstrip("/").lower():
            continue
        seen_fetch.add(key)
        extra.append(u)
        if len(extra) >= 6:
            break

    if extra:
        async def _fetch_contact(url: str) -> Optional[Dict[str, Any]]:
            try:
                async with httpx.AsyncClient(timeout=9.0, follow_redirects=True, headers=HEADERS) as client:
                    res = await client.get(url)
                    if res.status_code != 200 or not res.text:
                        return None
                    final = str(res.url)
                    # Soft-404 / homepage bounce: ignore if URL collapsed to home with no contact path
                    if (
                        final.rstrip("/").lower() in {
                            base.rstrip("/").lower(),
                            (page_url or "").rstrip("/").lower(),
                        }
                        and not _path_is_contact(url)
                    ):
                        return None
                    bonus = PAGE_CONTACT if _path_is_contact(final) or _path_is_contact(url) else PAGE_HOME + 10
                    extracted = _extract_from_html(
                        res.text, final, site_domain, page_bonus=bonus,
                    )
                    return {
                        "final": final,
                        "bonus": bonus,
                        "extracted": extracted,
                    }
            except Exception:
                return None

        results = await asyncio.gather(*[_fetch_contact(u) for u in extra])
        for result in results:
            if not result:
                continue
            pages_checked += 1
            extracted = result["extracted"]
            all_hits.extend(extracted.get("hits") or [])
            for p in extracted.get("phones") or []:
                if p not in phones:
                    phones.append(p)
            page_emails = extracted.get("emails") or []
            if page_emails or result["bonus"] >= PAGE_CONTACT:
                contact_page_urls.append(result["final"])
                contacts.append({
                    "type": "url",
                    "value": result["final"],
                    "label": "Contact page",
                    "source": "site",
                })

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
