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
    "postmaster", "abuse", "webmaster", "privacy", "test", "testing",
)
# Found but not useful for outreach — keep searching for a stronger inbox
WEAK_EMAIL_LOCAL = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon",
    "postmaster", "abuse", "webmaster", "privacy", "test", "testing",
    "admin", "root", "hostmaster",
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
    "sales", "wholesale", "info", "contact", "orders", "business", "hello",
    "enquiry", "inquiry", "b2b", "trade", "office", "support", "dealer",
    "distribution", "partners",
)
CONTACT_PATH_HINTS = (
    "contact", "get-in-touch", "getintouch", "enquiry", "inquiry", "connect",
    "about-us", "about", "team", "staff", "support", "sales", "wholesale",
    "wholesaler", "b2b", "distributor", "distribution", "dealer", "dealers",
    "company", "customer-service", "customer-care", "reach-us", "reachus",
    "lets-talk", "talk-to-us", "write-to-us", "email-us", "help-center",
    "faq", "partners", "become-a-dealer", "become-a-distributor", "trade",
    "our-team", "meet-the-team", "management", "leadership", "sales-team",
)
CONTACT_LINK_TEXT = (
    "contact", "contact us", "contactus", "get in touch", "get in-touch",
    "enquire", "enquiry", "inquiry", "reach us", "email us", "write to us",
    "talk to us", "let's talk", "lets talk", "customer service", "support",
    "sales", "wholesale", "b2b", "distributors", "dealers", "about us",
    "about", "our team", "team", "partners", "become a dealer",
    "become a distributor", "faq", "help",
)
# Navigation / crawl priority only (not lead quality).
LINK_SCORE_KEYWORDS: Tuple[Tuple[Tuple[str, ...], int], ...] = (
    (("contact-us", "contact_us", "contactus", "get-in-touch", "getintouch",
      "contact-information", "contact-info", "getintouch"), 100),
    (("contact",), 95),
    (("wholesale", "wholesaler", "wholesalers"), 90),
    (("distributor", "distribution", "distributors"), 90),
    (("sales", "b2b", "trade"), 90),
    (("dealer", "dealers", "become-a-dealer", "become-a-distributor"), 85),
    (("about-us", "about_us", "aboutus", "our-company", "meet-the-team"), 80),
    (("about", "company"), 75),
    (("team", "staff", "management", "leadership", "our-team", "sales-team"), 70),
    (("support", "customer-service", "customer-care", "help"), 60),
    (("home", "index"), 50),
    (("faq", "faqs", "help-center"), 40),
    (("blog", "news", "articles", "category", "tag", "press"), 10),
    (("product", "products", "shop", "store", "cart", "checkout"), 10),
)
NAV_SELECTORS = (
    "nav", "header", "[role='navigation']",
    "[id*='nav']", "[class*='nav']", "[class*='menu']",
    "[id*='menu']", ".navbar", "#navbar", ".main-nav", ".site-nav",
    "[class*='hamburger']", "[class*='mobile-menu']", "[class*='drawer']",
)
SKIP_CRAWL_PATH_PARTS = (
    "/blog", "/news", "/articles", "/category/", "/tag/", "/tags/",
    "/press", "/wp-json", "/cart", "/checkout", "/account", "/login",
    "/signin", "/sign-in", "/register", "/privacy", "/terms", "/cookie",
)
# Prefer true contact pages before about/team
DEFAULT_CONTACT_PATHS = (
    "/contact", "/contact-us", "/contactus", "/contact/",
    "/pages/contact", "/pages/contact-us", "/pages/contactus",
    "/company/contact", "/company/contact-us",
    "/get-in-touch", "/getintouch", "/enquiry", "/inquiry",
    "/customer-service", "/customer-care", "/reach-us", "/lets-talk",
    "/support/contact", "/en/contact", "/us/contact",
    "/sales", "/pages/sales", "/b2b", "/pages/b2b",
    "/wholesale", "/wholesale-program", "/pages/wholesale",
    "/distributors", "/distributor", "/distribution", "/dealers", "/dealer",
    "/pages/distributors", "/pages/wholesale-program",
    "/about", "/about-us", "/pages/about", "/pages/about-us",
    "/company", "/pages/company",
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
PAGE_FOOTER = 30  # footer / site-info block (where B2B emails usually live)

FOOTER_SELECTORS = (
    "footer",
    "[role='contentinfo']",
    "[id*='footer']",
    "[class*='footer']",
    "[class*='site-info']",
    "[class*='copyright']",
    ".site-footer",
    "#footer",
    "#colophon",
)

# Bottom-of-page bands (emails often sit here even without a <footer> tag)
BOTTOM_SELECTORS = (
    "[class*='pre-footer']",
    "[class*='prefooter']",
    "[class*='site-bottom']",
    "[class*='page-bottom']",
    "[class*='bottom-bar']",
    "[class*='bottom-info']",
    "[id*='bottom']",
    "[class*='follow-us']",
    "[class*='followus']",
    "[class*='social-bar']",
    "[class*='connect-with']",
    ".bottom",
    "#bottom",
)

SOCIAL_HOSTS = (
    "facebook.com",
    "fb.com",
    "m.facebook.com",
    "mbasic.facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
)
# Crawl priority for official social links found on the company site
SOCIAL_PRIORITY = (
    ("facebook.com", 100),
    ("fb.com", 100),
    ("mbasic.facebook.com", 100),
    ("m.facebook.com", 95),
    ("linkedin.com", 90),
    ("instagram.com", 60),
    ("twitter.com", 30),
    ("x.com", 30),
    ("youtube.com", 20),
    ("youtu.be", 20),
    ("tiktok.com", 15),
)


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
            "sales", "wholesale", "distributor", "distribution", "dealer",
            "b2b", "about", "company", "team", "staff", "partners", "faq",
        )
    )


def score_internal_link(
    url: str,
    anchor_text: str = "",
    *,
    in_nav: bool = False,
    in_footer: bool = False,
) -> int:
    """Navigation priority for which internal pages to inspect first."""
    path = (urlparse(url or "").path or "/").lower()
    blob = f"{path} {(anchor_text or '').lower()}"
    if any(part in path for part in SKIP_CRAWL_PATH_PARTS):
        # Still allow if explicitly contact-like (rare)
        if not any(h in blob for h in ("contact", "about", "sales", "wholesale")):
            return 5
    score = 15
    for keys, pts in LINK_SCORE_KEYWORDS:
        if any(k in blob for k in keys):
            score = max(score, pts)
            break
    if in_nav:
        score += 25
    if in_footer:
        score += 15
    return score


def page_type_label(url: str) -> str:
    path = (urlparse(url or "").path or "/").lower()
    checks = (
        (("contact", "get-in-touch", "getintouch", "enquiry", "inquiry"), "contact_page"),
        (("wholesale", "wholesaler"), "wholesale_page"),
        (("distributor", "distribution", "dealer"), "sales_page"),
        (("sales", "b2b", "trade", "partners"), "sales_page"),
        (("about", "company", "our-company"), "about_page"),
        (("team", "staff", "management", "leadership"), "team_page"),
        (("faq", "help", "support"), "support_page"),
    )
    for keys, label in checks:
        if any(k in path for k in keys):
            return label
    if path in ("", "/", "/index", "/index.html", "/home"):
        return "homepage"
    return "internal_page"


def _is_weak_email(email: str) -> bool:
    addr = (_clean_email(email) or (email or "").lower()).strip()
    if not addr or "@" not in addr:
        return True
    local = addr.partition("@")[0]
    if local in WEAK_EMAIL_LOCAL:
        return True
    if any(local.startswith(j + "-") or local.startswith(j + ".") for j in WEAK_EMAIL_LOCAL):
        return True
    return False


def _is_strong_email(email: str, site_domain: str) -> bool:
    addr = _clean_email(email) or ""
    if not addr or _is_weak_email(addr):
        return False
    ed = addr.partition("@")[2]
    if _is_same_domain(ed, site_domain) and _local_pref(addr) > 0:
        return True
    # Explicit preferred inbox even on personal mail (rare but real for small B2B)
    if ed in PERSONAL_MAIL_DOMAINS and _local_pref(addr) >= 3:
        return True
    if _is_same_domain(ed, site_domain):
        return True
    return False


def _social_priority(url: str) -> int:
    host = _domain(url)
    best = 0
    for h, pts in SOCIAL_PRIORITY:
        if host == h or host.endswith("." + h):
            best = max(best, pts)
    return best


def _looks_sparse_html(html: str, text: str = "") -> bool:
    """Heuristic: SPA / thin shell where emails appear only after JS render."""
    raw = html or ""
    visible = (text or "").strip()
    if len(visible) < 180 and len(raw) > 800:
        return True
    markers = (
        'id="__next"', "id='__next'", "data-reactroot", "__NUXT__",
        "ng-version=", "data-v-", 'id="root"', "webpackJsonp",
    )
    if any(m in raw for m in markers) and len(visible) < 900:
        return True
    return False


def _ancestor_region(tag: Any) -> str:
    """Classify DOM region for email provenance."""
    cur = tag
    depth = 0
    while cur is not None and depth < 12:
        name = (getattr(cur, "name", None) or "").lower()
        attrs = getattr(cur, "attrs", None) or {}
        id_cls = " ".join(
            [
                str(attrs.get("id") or ""),
                " ".join(attrs.get("class") or []) if isinstance(attrs.get("class"), list) else str(attrs.get("class") or ""),
                str(attrs.get("role") or ""),
            ]
        ).lower()
        if name in ("nav",) or "nav" in id_cls or "menu" in id_cls or attrs.get("role") == "navigation":
            return "navbar"
        if name == "header" or "header" in id_cls:
            return "navbar"
        if name == "footer" or "footer" in id_cls or attrs.get("role") == "contentinfo":
            return "footer"
        if "contact" in id_cls:
            return "contact_section"
        if "hero" in id_cls or "banner" in id_cls:
            return "hero"
        if "about" in id_cls:
            return "about_section"
        cur = getattr(cur, "parent", None)
        depth += 1
    return "homepage"


def _evidence_snippet(blob: str, email: str, radius: int = 60) -> str:
    low = (blob or "").lower()
    needle = (email or "").lower()
    idx = low.find(needle)
    if idx < 0:
        return (email or "")[:120]
    start = max(0, idx - radius)
    end = min(len(blob), idx + len(email) + radius)
    return " ".join((blob[start:end] or "").split())[:180]


def _empty_telemetry() -> Dict[str, Any]:
    return {
        "homepageChecked": False,
        "homepageRendered": False,
        "internalPagesChecked": 0,
        "contactPageChecked": False,
        "aboutPageChecked": False,
        "salesPageChecked": False,
        "wholesalePageChecked": False,
        "socialLinksFound": [],
        "facebookChecked": False,
        "facebookEmailFound": False,
        "linkedinChecked": False,
        "hunterChecked": False,
        "pagesChecked": 0,
        "renderedPages": 0,
    }


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
    # keep only when found via explicit mailto / contact-page attributes / footer
    if same == 0:
        if page_bonus >= PAGE_CONTACT and source >= SRC_ATTR:
            return (page_bonus + source // 2, _local_pref(email), source, -len(email))
        if source >= SRC_MAILTO and page_bonus >= PAGE_SECTION:
            return (page_bonus + source // 2, _local_pref(email), source, -len(email))
        # Small distributors often put Gmail/Yahoo as plain text in the footer
        if (
            domain in PERSONAL_MAIL_DOMAINS
            and page_bonus >= PAGE_SECTION
            and source >= SRC_TEXT
        ):
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
        "footer", "[role='contentinfo']", "[itemtype*='ContactPoint']",
        "[id*='footer']", "[class*='footer']",
    ):
        try:
            if soup.select_one(sel):
                return max(page_bonus, PAGE_SECTION)
        except Exception:
            continue
    return page_bonus


def _is_social_url(url: str) -> bool:
    host = _domain(url)
    return any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS)


def _preferred_inbox(email: str, site_domain: str) -> bool:
    """True when we already have a strong same-domain sales/info-style address."""
    addr = _clean_email(email) or ""
    if not addr:
        return False
    ed = addr.partition("@")[2]
    if not _is_same_domain(ed, site_domain):
        return False
    return _local_pref(addr) > 0


def _bottom_region_nodes(soup: BeautifulSoup) -> List[Any]:
    """Nodes that typically hold emails: footer, pre-footer, or last third of <body>."""
    nodes: List[Any] = []
    for sel in FOOTER_SELECTORS + BOTTOM_SELECTORS:
        try:
            nodes.extend(soup.select(sel))
        except Exception:
            continue
    if nodes:
        return nodes
    body = soup.body
    if not body:
        return []
    kids = [c for c in body.find_all(recursive=False) if getattr(c, "name", None)]
    if len(kids) < 2:
        return kids[-1:] if kids else []
    take = max(1, len(kids) // 3)
    return kids[-take:]


def _facebook_fetch_urls(url: str) -> List[str]:
    """Prefer mbasic Facebook (often exposes About email) over the JS-heavy desktop site."""
    raw = (url or "").strip()
    if not raw:
        return []
    parsed = urlparse(raw)
    path = (parsed.path or "/").split("?")[0]
    # Drop share/intent paths
    low = path.lower()
    if any(x in low for x in ("/share", "/sharer", "/intent", "dialog/")):
        return []
    # Normalize fb.com → facebook path
    host = _domain(raw)
    if "fb.com" in host and "facebook" not in host:
        # fb.com/page → treat path as-is
        pass
    slug = path.rstrip("/") or "/"
    out: List[str] = []
    for host_name in ("mbasic.facebook.com", "m.facebook.com", "www.facebook.com"):
        base = f"https://{host_name}{slug}"
        out.append(base)
        if "/about" not in slug.lower():
            out.append(base + "/about")
            out.append(base + "/about_contact_and_basic_info")
    # Dedupe preserve order
    seen: Set[str] = set()
    uniq: List[str] = []
    for u in out:
        key = u.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(u)
    return uniq[:6]


def _extract_from_html(
    html: str,
    page_url: str,
    site_domain: str,
    *,
    page_bonus: int = PAGE_HOME,
    page_label: str = "",
) -> Dict[str, Any]:
    hits: List[Dict[str, Any]] = []
    phones: List[str] = []
    contact_urls: List[str] = []
    scored_links: List[Dict[str, Any]] = []
    social_urls: List[str] = []
    seen_e: Set[str] = set()
    seen_p: Set[str] = set()
    seen_u: Set[str] = set()
    seen_social: Set[str] = set()
    default_label = page_label or page_type_label(page_url)

    def add(
        email: Optional[str],
        source: int,
        bonus: Optional[int] = None,
        *,
        region: str = "",
        evidence: str = "",
        node: Any = None,
    ) -> None:
        if not email or email in seen_e:
            return
        ed = email.partition("@")[2]
        use_bonus = page_bonus if bonus is None else bonus
        if not _is_same_domain(ed, site_domain) and source < SRC_ATTR:
            if not (
                ed in PERSONAL_MAIL_DOMAINS
                and use_bonus >= PAGE_SECTION
                and source >= SRC_TEXT
            ):
                return
        if ed in PERSONAL_MAIL_DOMAINS:
            strong = source >= SRC_ATTR or (
                use_bonus >= PAGE_SECTION and source >= SRC_TEXT
            )
            if not strong:
                return
        seen_e.add(email)
        reg = region or (_ancestor_region(node) if node is not None else default_label)
        if reg in ("homepage", "") and default_label not in ("", "homepage"):
            reg = default_label
        hits.append({
            "email": email,
            "source": source,
            "page_bonus": use_bonus,
            "region": reg,
            "source_url": page_url,
            "evidence": evidence or email,
            "label": reg if reg not in ("", "homepage") else default_label,
        })

    raw = _normalize_blob(html or "")
    soup = BeautifulSoup(raw, "html.parser")

    for addr in _emails_from_jsonld(soup):
        add(addr, SRC_JSONLD, region="structured_data", evidence=f"JSON-LD: {addr}")

    section_bonus = _contact_section_bonus(soup, page_bonus)

    for tag in soup(["style", "noscript", "svg", "template"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    for tag in soup.find_all("script"):
        t = (tag.get("type") or "").lower()
        if "ld+json" in t:
            continue
        tag.decompose()

    for tag in soup.select("[data-cfemail]"):
        addr = _decode_cfemail(tag.get("data-cfemail") or "")
        add(
            addr, SRC_CF, section_bonus,
            region=_ancestor_region(tag), node=tag,
            evidence=f"Cloudflare email on {default_label}",
        )

    for tag in soup.select(
        "[itemprop=email], [itemprop='email'], [data-email], meta[itemprop=email]"
    ):
        val = (
            tag.get("content")
            or tag.get("data-email")
            or tag.get_text(" ", strip=True)
            or ""
        ).strip()
        add(
            _clean_email(val), SRC_ATTR, section_bonus,
            region=_ancestor_region(tag), node=tag, evidence=val[:120],
        )

    def _note_social(abs_url: str) -> None:
        key = abs_url.split("?")[0].rstrip("/").lower()
        if any(x in key for x in ("/share", "/sharer", "/intent", "dialog/")):
            return
        if key not in seen_social:
            seen_social.add(key)
            social_urls.append(abs_url.split("?")[0])

    def _note_internal(
        abs_url: str, link_text: str, *, in_nav: bool, in_footer: bool
    ) -> None:
        path = (urlparse(abs_url).path or "").lower()
        frag = (urlparse(abs_url).fragment or "").lower()
        same_site = _domain(abs_url) == site_domain or not _domain(abs_url)
        if not same_site:
            return
        looks = (
            any(h in path for h in CONTACT_PATH_HINTS)
            or any(h in frag for h in ("contact", "enquiry", "inquiry", "get-in-touch"))
            or link_text in CONTACT_LINK_TEXT
            or any(link_text.startswith(t) for t in CONTACT_LINK_TEXT)
            or score_internal_link(abs_url, link_text, in_nav=in_nav, in_footer=in_footer) >= 40
        )
        if not looks:
            return
        if frag and (
            path in ("", "/")
            or abs_url.rstrip("/#") == (page_url or "").rstrip("/#")
        ):
            return
        if abs_url.rstrip("/") == (page_url or "").rstrip("/"):
            return
        key = abs_url.rstrip("/").lower()
        if key in seen_u:
            return
        seen_u.add(key)
        contact_urls.append(abs_url)
        scored_links.append({
            "url": abs_url,
            "anchor": link_text,
            "score": score_internal_link(
                abs_url, link_text, in_nav=in_nav, in_footer=in_footer
            ),
            "in_nav": in_nav,
            "in_footer": in_footer,
            "page_type": page_type_label(abs_url),
        })

    nav_nodes: List[Any] = []
    for sel in NAV_SELECTORS:
        try:
            nav_nodes.extend(soup.select(sel))
        except Exception:
            continue
    real_footer = False
    for sel in FOOTER_SELECTORS:
        try:
            if soup.select_one(sel):
                real_footer = True
                break
        except Exception:
            continue
    footer_nodes = _bottom_region_nodes(soup)
    # On /about or /contact, bottom-band text is still that page — not "footer"
    bottom_region = (
        "footer"
        if real_footer or default_label in ("", "homepage")
        else default_label
    )

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        low = href.lower()
        link_text = " ".join((a.get_text(" ", strip=True) or "").lower().split())
        region = _ancestor_region(a)
        in_nav = region == "navbar"
        in_footer = region == "footer"
        if low.startswith("mailto:"):
            mailto_bonus = max(section_bonus, page_bonus)
            if in_footer:
                mailto_bonus = max(mailto_bonus, PAGE_FOOTER)
            addr = _clean_email(href.split(":", 1)[1].split("?", 1)[0])
            add(
                addr, SRC_MAILTO, mailto_bonus,
                region=region, node=a,
                evidence=f"mailto:{addr}" if addr else "",
            )
        elif "cdn-cgi/l/email-protection#" in low:
            add(
                _decode_cfemail(href.split("#", 1)[-1]), SRC_CF, section_bonus,
                region=region, node=a,
            )
        elif low.startswith("tel:"):
            phone = _clean_phone(href.split(":", 1)[1])
            if phone and phone not in seen_p:
                seen_p.add(phone)
                phones.append(phone)
        else:
            abs_url = urljoin(page_url, href)
            if _is_social_url(abs_url):
                _note_social(abs_url)
                continue
            _note_internal(abs_url, link_text, in_nav=in_nav, in_footer=in_footer)

    if footer_nodes:
        footer_blob_tight = " ".join(n.get_text("", strip=True) for n in footer_nodes)
        footer_blob_spaced = " ".join(n.get_text(" ", strip=True) for n in footer_nodes)
        for match in EMAIL_RE.findall(footer_blob_tight):
            addr = _clean_email(match)
            add(
                addr, SRC_TEXT, max(section_bonus, PAGE_FOOTER), region=bottom_region,
                evidence=_evidence_snippet(footer_blob_spaced, addr or match),
            )
        for addr in _emails_from_loose(footer_blob_spaced):
            add(
                addr, SRC_TEXT, max(section_bonus, PAGE_FOOTER), region=bottom_region,
                evidence=_evidence_snippet(footer_blob_spaced, addr),
            )
        for addr in _emails_from_obfuscated(footer_blob_spaced):
            add(
                addr, SRC_OBFUSCATED, max(section_bonus, PAGE_FOOTER), region=bottom_region,
                evidence=_evidence_snippet(footer_blob_spaced, addr),
            )

    if nav_nodes:
        nav_blob = " ".join(n.get_text(" ", strip=True) for n in nav_nodes[:12])
        for match in EMAIL_RE.findall(nav_blob.replace(" ", "")):
            addr = _clean_email(match)
            add(
                addr, SRC_TEXT, max(section_bonus, PAGE_SECTION), region="navbar",
                evidence=_evidence_snippet(nav_blob, addr or match),
            )
        for addr in _emails_from_loose(nav_blob):
            add(
                addr, SRC_TEXT, max(section_bonus, PAGE_SECTION), region="navbar",
                evidence=_evidence_snippet(nav_blob, addr),
            )
        for addr in _emails_from_obfuscated(nav_blob):
            add(
                addr, SRC_OBFUSCATED, max(section_bonus, PAGE_SECTION), region="navbar",
                evidence=_evidence_snippet(nav_blob, addr),
            )

    text_tight = soup.get_text("", strip=True)
    text_spaced = soup.get_text(" ", strip=True)
    for match in EMAIL_RE.findall(text_tight):
        addr = _clean_email(match)
        add(
            addr, SRC_TEXT, section_bonus, region=default_label,
            evidence=_evidence_snippet(text_spaced, addr or match),
        )
    for addr in _emails_from_loose(text_spaced):
        add(
            addr, SRC_TEXT, section_bonus, region=default_label,
            evidence=_evidence_snippet(text_spaced, addr),
        )
    for addr in _emails_from_obfuscated(text_spaced):
        add(
            addr, SRC_OBFUSCATED, section_bonus, region=default_label,
            evidence=_evidence_snippet(text_spaced, addr),
        )

    for match in EMAIL_RE.findall(raw):
        add(
            _clean_email(match), SRC_TEXT, max(section_bonus, page_bonus),
            region=default_label,
        )

    for match in PHONE_RE.findall(text_spaced[:5000]):
        phone = _clean_phone(match)
        if phone and phone not in seen_p:
            seen_p.add(phone)
            phones.append(phone)

    contact_urls.sort(key=lambda u: (-score_internal_link(u), u))
    scored_links.sort(key=lambda x: (-int(x.get("score") or 0), x.get("url") or ""))
    social_urls.sort(key=lambda u: (-_social_priority(u), u))

    emails = _rank_scored(hits, site_domain)
    return {
        "emails": emails[:8],
        "hits": hits,
        "phones": phones[:3],
        "contact_urls": contact_urls[:16],
        "scored_links": scored_links[:16],
        "social_urls": social_urls[:8],
        "text": text_spaced[:12000],
        "sparse": _looks_sparse_html(html, text_spaced),
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
    *,
    use_browser: bool = True,
    max_internal_pages: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Staged public contact discovery (human-like crawl):

      HTTP homepage → scored internal pages → rendered homepage (if needed)
      → rendered top contact/about pages → official social → (Hunter later)

    Early-stops on a high-confidence business email. Weak-only hits continue.
    """
    from app.config import settings

    telemetry = _empty_telemetry()
    base = (website or "").strip()
    if not base:
        return {
            "contacts": [],
            "email": "",
            "phone": seed_phone or "",
            "emailStatus": "website_unreachable",
            "emailSource": "",
            "emailSourceUrl": "",
            "emailEvidence": "",
            "telemetry": telemetry,
            "pagesChecked": 0,
        }

    if not base.startswith("http"):
        base = "https://" + base
    site_domain = _domain(base)
    page_url = homepage_url or base
    contacts: List[Dict[str, Any]] = []
    all_hits: List[Dict[str, Any]] = []
    phones: List[str] = []
    pages_checked = 0
    contact_page_urls: List[str] = []
    scored_queue: List[Dict[str, Any]] = []
    social_urls: List[str] = []
    homepage_unreachable = False
    max_pages = int(
        max_internal_pages
        if max_internal_pages is not None
        else getattr(settings, "CONTACT_MAX_INTERNAL_PAGES", 8)
    )
    max_render = int(getattr(settings, "CONTACT_RENDER_MAX_PAGES", 3))

    def _merge_extracted(extracted: Dict[str, Any], *, mark_home: bool = False) -> None:
        nonlocal pages_checked
        pages_checked += 1
        telemetry["pagesChecked"] = pages_checked
        all_hits.extend(extracted.get("hits") or [])
        for p in extracted.get("phones") or []:
            if p not in phones:
                phones.append(p)
        for link in extracted.get("scored_links") or []:
            scored_queue.append(link)
        for u in extracted.get("contact_urls") or []:
            if not any(
                (x.get("url") or "").rstrip("/").lower() == u.rstrip("/").lower()
                for x in scored_queue
            ):
                scored_queue.append({
                    "url": u,
                    "anchor": "",
                    "score": score_internal_link(u),
                    "in_nav": False,
                    "in_footer": False,
                    "page_type": page_type_label(u),
                })
        for u in extracted.get("social_urls") or []:
            if u not in social_urls:
                social_urls.append(u)
        if mark_home:
            telemetry["homepageChecked"] = True

    def _pick_primary() -> Tuple[str, Dict[str, Any]]:
        ranked = _rank_scored(all_hits, site_domain)
        # Prefer strong; fall back to any ranked (may be weak)
        strong = [e for e in ranked if _is_strong_email(e, site_domain)]
        usable = strong or [e for e in ranked if not _is_weak_email(e)] or ranked
        if not usable:
            return "", {}
        email = usable[0]
        meta = next((h for h in all_hits if h.get("email") == email), {})
        return email, meta

    def _has_strong() -> bool:
        email, _ = _pick_primary()
        return bool(email) and _is_strong_email(email, site_domain)

    for raw in seed_emails or []:
        addr = _clean_email(raw)
        if addr:
            all_hits.append({
                "email": addr,
                "source": SRC_SEED,
                "page_bonus": PAGE_HOME,
                "region": "homepage",
                "source_url": page_url,
                "evidence": addr,
                "label": "homepage",
            })

    if homepage_text:
        blob = _normalize_blob(homepage_text)
        for match in EMAIL_RE.findall(blob):
            addr = _clean_email(match)
            if addr:
                all_hits.append({
                    "email": addr,
                    "source": SRC_TEXT,
                    "page_bonus": PAGE_HOME,
                    "region": "homepage",
                    "source_url": page_url,
                    "evidence": _evidence_snippet(blob, addr),
                    "label": "homepage",
                })
        for addr in _emails_from_loose(blob):
            all_hits.append({
                "email": addr,
                "source": SRC_TEXT,
                "page_bonus": PAGE_HOME,
                "region": "homepage",
                "source_url": page_url,
                "evidence": _evidence_snippet(blob, addr),
                "label": "homepage",
            })
        for addr in _emails_from_obfuscated(blob):
            all_hits.append({
                "email": addr,
                "source": SRC_OBFUSCATED,
                "page_bonus": PAGE_HOME,
                "region": "homepage",
                "source_url": page_url,
                "evidence": _evidence_snippet(blob, addr),
                "label": "homepage",
            })
        for match in PHONE_RE.findall(blob[:5000]):
            phone = _clean_phone(match)
            if phone and phone not in phones:
                phones.append(phone)

    html = homepage_html or ""
    if not html:
        try:
            async with httpx.AsyncClient(
                timeout=10.0, follow_redirects=True, headers=HEADERS
            ) as client:
                res = await client.get(base)
                if res.status_code == 200 and res.text:
                    html = res.text
                    page_url = str(res.url)
                else:
                    homepage_unreachable = True
        except Exception:
            homepage_unreachable = True
            html = ""

    homepage_sparse = False
    if html:
        extracted = _extract_from_html(
            html, page_url, site_domain,
            page_bonus=PAGE_HOME, page_label="homepage",
        )
        _merge_extracted(extracted, mark_home=True)
        homepage_sparse = bool(extracted.get("sparse"))

    # --- Stage: ranked internal pages (static HTTP) ---
    if not _has_strong():
        for path in DEFAULT_CONTACT_PATHS:
            guess = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
            scored_queue.append({
                "url": guess,
                "anchor": path.strip("/"),
                "score": score_internal_link(guess) - 5,
                "in_nav": False,
                "in_footer": False,
                "page_type": page_type_label(guess),
            })

        # Dedupe / sort queue
        best_by_url: Dict[str, Dict[str, Any]] = {}
        for item in scored_queue:
            u = (item.get("url") or "").strip()
            if not u:
                continue
            key = u.rstrip("/").lower()
            if key in {
                base.rstrip("/").lower(),
                (page_url or "").rstrip("/").lower(),
            }:
                continue
            prev = best_by_url.get(key)
            if prev is None or int(item.get("score") or 0) > int(prev.get("score") or 0):
                best_by_url[key] = item
        ordered = sorted(
            best_by_url.values(),
            key=lambda x: (-int(x.get("score") or 0), x.get("url") or ""),
        )[:max_pages]

        async def _fetch_page(url: str) -> Optional[Dict[str, Any]]:
            try:
                async with httpx.AsyncClient(
                    timeout=9.0, follow_redirects=True, headers=HEADERS
                ) as client:
                    res = await client.get(url)
                    if res.status_code != 200 or not res.text:
                        return None
                    final = str(res.url)
                    if (
                        final.rstrip("/").lower()
                        in {
                            base.rstrip("/").lower(),
                            (page_url or "").rstrip("/").lower(),
                        }
                        and not _path_is_contact(url)
                    ):
                        return None
                    label = page_type_label(final) if _path_is_contact(final) else page_type_label(url)
                    bonus = (
                        PAGE_CONTACT
                        if label == "contact_page"
                        else (PAGE_SECTION if label != "homepage" else PAGE_HOME + 10)
                    )
                    extracted = _extract_from_html(
                        res.text, final, site_domain,
                        page_bonus=bonus, page_label=label,
                    )
                    return {
                        "final": final,
                        "bonus": bonus,
                        "label": label,
                        "extracted": extracted,
                        "sparse": bool(extracted.get("sparse")),
                    }
            except Exception:
                return None

        results = await asyncio.gather(*[_fetch_page(item["url"]) for item in ordered])
        render_candidates: List[str] = []
        for item, result in zip(ordered, results):
            if not result:
                continue
            telemetry["internalPagesChecked"] = int(telemetry["internalPagesChecked"]) + 1
            label = result["label"]
            if label == "contact_page":
                telemetry["contactPageChecked"] = True
            elif label == "about_page":
                telemetry["aboutPageChecked"] = True
            elif label == "sales_page":
                telemetry["salesPageChecked"] = True
            elif label == "wholesale_page":
                telemetry["wholesalePageChecked"] = True
            _merge_extracted(result["extracted"])
            contact_page_urls.append(result["final"])
            contacts.append({
                "type": "url",
                "value": result["final"],
                "label": "Contact page" if label == "contact_page" else label.replace("_", " ").title(),
                "source": "site",
            })
            if result.get("sparse") and result["final"] not in render_candidates:
                render_candidates.append(result["final"])
            if _has_strong():
                break

    # --- Stage: rendered browser fallback ---
    need_render = (
        use_browser
        and not _has_strong()
        and (
            homepage_sparse
            or homepage_unreachable
            or not any(h for h in all_hits if not _is_weak_email(h.get("email") or ""))
        )
    )
    if need_render:
        try:
            from app.tools.browser_fetch import browser_available, fetch_rendered
        except Exception:
            browser_available = lambda: False  # type: ignore
            fetch_rendered = None  # type: ignore

        if browser_available() and fetch_rendered:
            # Homepage first
            if not _has_strong():
                rendered = await fetch_rendered(page_url or base, timeout_ms=12000)
                if rendered.get("ok") and rendered.get("html"):
                    telemetry["homepageRendered"] = True
                    telemetry["renderedPages"] = int(telemetry["renderedPages"]) + 1
                    extracted = _extract_from_html(
                        rendered["html"],
                        rendered.get("url") or page_url,
                        site_domain,
                        page_bonus=PAGE_SECTION,
                        page_label="homepage",
                    )
                    _merge_extracted(extracted, mark_home=True)

            # Highest-value internal pages that looked sparse / contact-like
            if not _has_strong():
                to_render: List[str] = []
                for item in sorted(
                    scored_queue,
                    key=lambda x: (-int(x.get("score") or 0), x.get("url") or ""),
                ):
                    u = item.get("url") or ""
                    if not u:
                        continue
                    if int(item.get("score") or 0) < 60:
                        continue
                    key = u.rstrip("/").lower()
                    if key in {base.rstrip("/").lower(), (page_url or "").rstrip("/").lower()}:
                        continue
                    if key not in {x.rstrip("/").lower() for x in to_render}:
                        to_render.append(u)
                    if len(to_render) >= max_render:
                        break
                for u in to_render:
                    if _has_strong():
                        break
                    rendered = await fetch_rendered(u, timeout_ms=10000)
                    if not rendered.get("ok") or not rendered.get("html"):
                        continue
                    telemetry["renderedPages"] = int(telemetry["renderedPages"]) + 1
                    label = page_type_label(rendered.get("url") or u)
                    bonus = PAGE_CONTACT if label == "contact_page" else PAGE_SECTION
                    extracted = _extract_from_html(
                        rendered["html"],
                        rendered.get("url") or u,
                        site_domain,
                        page_bonus=bonus,
                        page_label=label,
                    )
                    _merge_extracted(extracted)
                    if label == "contact_page":
                        telemetry["contactPageChecked"] = True
                    elif label == "about_page":
                        telemetry["aboutPageChecked"] = True

    # --- Stage: official social (Facebook first) ---
    social_urls.sort(key=lambda u: (-_social_priority(u), u))
    platforms_found = []
    for u in social_urls:
        host = _domain(u)
        if "facebook" in host or host.endswith("fb.com"):
            name = "facebook"
        elif "linkedin" in host:
            name = "linkedin"
        elif "instagram" in host:
            name = "instagram"
        elif "twitter" in host or host == "x.com":
            name = "twitter"
        elif "youtube" in host or "youtu.be" in host:
            name = "youtube"
        elif "tiktok" in host:
            name = "tiktok"
        else:
            name = host.split(".")[0] if host else "social"
        if name not in platforms_found:
            platforms_found.append(name)
    telemetry["socialLinksFound"] = platforms_found[:6]

    if not _has_strong() and social_urls:
        fb = next(
            (
                u for u in social_urls
                if any(h in _domain(u) for h in ("facebook.com", "fb.com", "mbasic.facebook.com"))
            ),
            None,
        )
        li = next((u for u in social_urls if "linkedin.com" in _domain(u)), None)
        candidates: List[Tuple[str, str]] = []  # (url, label)
        if fb:
            for u in _facebook_fetch_urls(fb):
                candidates.append((u, "facebook"))
        if li and not _has_strong():
            candidates.append((li, "linkedin"))
        # One Instagram page max if still empty
        ig = next((u for u in social_urls if "instagram.com" in _domain(u)), None)
        if ig and len(candidates) < 2:
            candidates.append((ig, "instagram"))

        facebook_blocked = False
        try:
            async with httpx.AsyncClient(
                timeout=8.0, follow_redirects=True, headers=HEADERS
            ) as client:
                for social_url, plat in candidates[:5]:
                    if _has_strong():
                        break
                    try:
                        res = await client.get(social_url)
                    except Exception:
                        if plat == "facebook":
                            facebook_blocked = True
                        continue
                    if plat == "facebook":
                        telemetry["facebookChecked"] = True
                    if plat == "linkedin":
                        telemetry["linkedinChecked"] = True
                    if res.status_code in (401, 403) or (
                        res.status_code == 200
                        and "login" in (res.url or social_url).lower()
                        and "facebook" in plat
                    ):
                        if plat == "facebook":
                            facebook_blocked = True
                        continue
                    if res.status_code != 200 or not res.text:
                        if plat == "facebook":
                            facebook_blocked = True
                        continue
                    # Login walls / empty about
                    body_l = res.text[:4000].lower()
                    if plat == "facebook" and (
                        "log into facebook" in body_l or "log in to facebook" in body_l
                    ):
                        facebook_blocked = True
                        continue
                    pages_checked += 1
                    telemetry["pagesChecked"] = pages_checked
                    extracted = _extract_from_html(
                        res.text,
                        str(res.url),
                        site_domain,
                        page_bonus=PAGE_SECTION,
                        page_label=plat,
                    )
                    # Force social label on hits from this pass
                    for h in extracted.get("hits") or []:
                        h["label"] = plat
                        h["region"] = plat
                        h["source_url"] = str(res.url)
                        all_hits.append(h)
                    for p in extracted.get("phones") or []:
                        if p not in phones:
                            phones.append(p)
                    if extracted.get("emails"):
                        if plat == "facebook":
                            telemetry["facebookEmailFound"] = True
                        contacts.append({
                            "type": "url",
                            "value": str(res.url),
                            "label": "Social page",
                            "source": plat,
                        })
                        break
        except Exception:
            if fb:
                facebook_blocked = True
        if facebook_blocked and not telemetry.get("facebookEmailFound"):
            telemetry["facebookStatus"] = "facebook_unavailable"

    primary_email, meta = _pick_primary()
    # Drop weak-only if we somehow still have only junk (clean_email already filters most)
    if primary_email and _is_weak_email(primary_email):
        # Continue would have run; if still weak at end, discard for outreach
        stronger = [
            e for e in _rank_scored(all_hits, site_domain)
            if not _is_weak_email(e)
        ]
        if stronger:
            primary_email = stronger[0]
            meta = next((h for h in all_hits if h.get("email") == primary_email), {})
        else:
            primary_email = ""
            meta = {}

    email_source = ""
    email_source_url = ""
    email_evidence = ""
    if primary_email:
        email_source = (
            meta.get("label")
            or meta.get("region")
            or page_type_label(meta.get("source_url") or "")
            or "homepage"
        )
        email_source_url = meta.get("source_url") or page_url or base
        email_evidence = meta.get("evidence") or primary_email
        contacts.insert(0, {
            "type": "email",
            "value": primary_email,
            "label": "Email",
            "source": email_source,
            "sourceUrl": email_source_url,
            "evidence": email_evidence,
            "role": "general",
        })
        # Also list other emails
        for e in _rank_scored(all_hits, site_domain)[:5]:
            if e == primary_email or _is_weak_email(e):
                continue
            if any(c.get("value") == e for c in contacts):
                continue
            h = next((x for x in all_hits if x.get("email") == e), {})
            contacts.append({
                "type": "email",
                "value": e,
                "label": "Email",
                "source": h.get("label") or "site",
                "sourceUrl": h.get("source_url") or "",
                "evidence": h.get("evidence") or e,
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
    for u in (contact_page_urls or [])[:3]:
        if not any(c.get("value") == u for c in contacts):
            contacts.append({
                "type": "url",
                "value": u,
                "label": "Contact page",
                "source": "site",
            })
    for u in social_urls[:3]:
        if not any(c.get("value") == u for c in contacts):
            contacts.append({
                "type": "url",
                "value": u,
                "label": "Social",
                "source": "social",
            })

    if primary_email:
        status = "found"
    elif homepage_unreachable and not html and not telemetry.get("homepageRendered"):
        status = "website_unreachable"
    elif telemetry.get("facebookStatus") == "facebook_unavailable" and not social_urls:
        status = "social_unavailable"
    else:
        status = "not_found"

    return {
        "contacts": contacts[:14],
        "email": primary_email,
        "phone": phones[0] if phones else (seed_phone or ""),
        "pagesChecked": pages_checked,
        "emailStatus": status,
        "emailSource": email_source,
        "emailSourceUrl": email_source_url,
        "emailEvidence": email_evidence,
        "telemetry": telemetry,
    }
