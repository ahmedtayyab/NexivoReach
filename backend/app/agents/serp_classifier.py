"""Cheap SERP-row classification. Discovery only — not qualification."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


ARTICLE_HOSTS = (
    "wikipedia.org", "medium.com", "quora.com",
    "reuters.com", "techcrunch.com", "forbes.com",
    "businessinsider.com", "prnewswire.com", "globenewswire.com",
)
# Hosts that are never a company website. A hit here is skipped and the host is remembered.
NON_BUSINESS_HOSTS = (
    "onlyfans.com", "github.com", "github.io", "gitlab.com",
    "amazon.com", "amazon.co.uk", "amazon.ca", "amazon.de", "amazon.com.au", "amzn.to", "amzn.eu",
    "ebay.com", "ebay.co.uk", "etsy.com", "aliexpress.com", "alibaba.com", "made-in-china.com",
    "indiamart.com", "walmart.com", "temu.com", "wish.com",
    "reddit.com", "pinterest.com", "pinterest.co.uk", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "tiktok.com", "youtube.com", "youtu.be", "linkedin.com",
    "scribd.com", "slideshare.net", "issuu.com", "academia.edu", "researchgate.net",
    "glassdoor.com", "indeed.com", "indeed.co.uk", "crunchbase.com", "zoominfo.com",
    "dnb.com", "bloomberg.com", "opencorporates.com", "companieshouse.gov.uk",
    "find-and-update.company-information.service.gov.uk", "endole.co.uk", "companycheck.co.uk",
    "bizstats.co.uk", "trustpilot.com", "tripadvisor.com",
)
# Business directories. Companies linked from the page are worth reading; the page itself is not a lead.
DIRECTORY_HOSTS = (
    "europages.com", "europages.co.uk", "kompass.com", "yell.com",
    "yelp.com", "yelp.co.uk", "thomasnet.com", "yellowpages.com",
    "yellowpages.co.uk", "esources.co.uk", "thewholesaler.co.uk", "wholesaledeals.co.uk",
    "cylex-uk.co.uk", "cylex.co.uk", "hotfrog.com", "hotfrog.co.uk", "freeindex.co.uk",
    "scoot.co.uk", "192.com", "manta.com", "bbb.org", "globalsources.com", "tradekey.com",
    "exportersindia.com", "ec21.com", "wlw.de", "wlw.co.uk", "ensun.io", "4imprint.com",
)
SEARCH_HOSTS = (
    "google.com", "duckduckgo.com", "yahoo.com", "bing.com",
)
ARTICLE_TITLE = re.compile(
    r"\b(top\s+\d+|best\s+\d+|complete guide|how to|what is|product review|buyer'?s guide)\b",
    re.I,
)
ARTICLE_PATH = re.compile(
    r"/(blog|blogs|news|press|articles?|wiki|reviews?|guides?|roundups?|jobs|careers)(/|$)",
    re.I,
)
_INSTITUTION_HOST = re.compile(
    r"(^|\.)(edu|mil)(\.[a-z]{2})?$|(^|\.)ac\.[a-z]{2}$|(^|\.)gov(\.[a-z]{2})?$|(^|\.)edu\.[a-z]{2}$",
    re.I,
)
_DOCUMENT_EXT = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx")
MFR_RE = re.compile(
    r"\b(manufacturer|manufacturing|factory|factories|oem|odm|textile mill|foundry)\b",
    re.I,
)
BUYER_RE = re.compile(
    r"\b(brand|retailer|distributor|importer|wholesaler|boutique|stockist|clinic|hospital|gym)\b",
    re.I,
)


def _host(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _endswith_any(host: str, suffixes: tuple[str, ...]) -> bool:
    return any(host == s or host.endswith("." + s) for s in suffixes)


from app.agents.geo import places_mentioned


def classify_page(url: str, title: str = "") -> Dict[str, Any]:
    """
    What kind of page a URL is: company, directory, or article.

    burn_domain is true only when the host itself can never be a company
    website. A blog URL on a company site is skipped, and that company's
    homepage can still be saved later.
    """
    host = _host(url)
    path = (urlparse(url or "").path or "").lower()
    if host and (_endswith_any(host, NON_BUSINESS_HOSTS) or _INSTITUTION_HOST.search(host)):
        return {"page_kind": "article", "burn_domain": True, "reason": "Not a company website"}
    if host and _endswith_any(host, DIRECTORY_HOSTS):
        return {"page_kind": "directory", "burn_domain": False, "reason": "Directory page"}
    if path.endswith(_DOCUMENT_EXT):
        return {"page_kind": "article", "burn_domain": False, "reason": "Document, not a company page"}
    if host and (_endswith_any(host, ARTICLE_HOSTS) or "/wiki" in (url or "").lower()):
        return {"page_kind": "article", "burn_domain": True, "reason": "Article or wiki page"}
    if ARTICLE_PATH.search(path) or "/best-" in path:
        return {"page_kind": "article", "burn_domain": False, "reason": "Article, review, or jobs URL"}
    if ARTICLE_TITLE.search(title or ""):
        return {"page_kind": "article", "burn_domain": False, "reason": "Article or listicle title"}
    return {"page_kind": "company", "burn_domain": False, "reason": ""}


def classify_serp_row(
    row: Dict[str, Any],
    *,
    hunting_buyers: bool,
    target_places: List[str],
    strict_geo: bool = False,
    offer_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    url = (row.get("website") or "").strip()
    title = (row.get("title") or row.get("company_name") or "")
    snippet = (row.get("snippet") or "")
    location = (row.get("location") or "")
    blob = f"{title} {snippet} {url} {location}"
    host = _host(url)
    entity = "company"
    reject = False
    reason = ""
    page = classify_page(url, title)
    burn_domain = bool(page.get("burn_domain"))

    if not host and not (row.get("company_name") and row.get("source") == "maps"):
        reject, entity, reason = True, "unknown", "No website or Maps identity"

    elif _endswith_any(host, SEARCH_HOSTS):
        reject, entity, reason = True, "skip_domain", "Search engine page"
        burn_domain = True

    elif page["page_kind"] != "company":
        reject, entity, reason = True, page["page_kind"], page["reason"]

    elif hunting_buyers and MFR_RE.search(blob) and not BUYER_RE.search(blob):
        # Tag only — do not drop organic Google companies that look like factories
        entity, reason = "manufacturer", "Manufacturer language — kept as organic Google hit"

    elif hunting_buyers and MFR_RE.search(blob):
        entity, reason = "manufacturer", "Manufacturer language present"

    # Google already chose this result. Articles and wiki pages are the only skips.

    geo_source = (location or "").strip() or blob
    geo_ok = places_mentioned(geo_source, target_places) if target_places else None
    if target_places and strict_geo and not reject:
        from app.agents.geo import location_conflicts_with_targets

        if location.strip() and location_conflicts_with_targets(location, target_places):
            reject, entity, reason = True, "wrong_geo", "Address is outside the requested location"
        elif geo_ok is False and _foreign_geo_conflict(geo_source, target_places):
            reject, entity, reason = True, "wrong_geo", "Geography conflicts with target markets"

    # Do not treat manufacturers as auto-rejects — organic Google hits stay
    competitor_seed = False


    return {
        **row,
        "entity_type": entity,
        "reject": reject or competitor_seed,
        "reject_reason": reason,
        "competitor_seed": competitor_seed,
        "geo_mentioned": geo_ok,
        "title": title,
        "page_kind": entity if entity in ("article", "directory") else "company",
        "burn_domain": burn_domain,
    }


def extract_directory_companies(html: str, page_url: str, limit: int = 12) -> List[str]:
    """Company websites linked from a directory page. The directory page is not a lead."""
    if not html or not page_url:
        return []
    try:
        from urllib.parse import urljoin

        from bs4 import BeautifulSoup
    except Exception:
        return []
    page_host = _host(page_url)
    soup = BeautifulSoup(html, "html.parser")
    found: List[str] = []
    seen: set[str] = set()
    skip_hosts = SEARCH_HOSTS + ARTICLE_HOSTS + NON_BUSINESS_HOSTS + DIRECTORY_HOSTS
    for link in soup.select("a[href]"):
        href = str(link.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute = urljoin(page_url, href)
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        host = _host(absolute)
        if not host or host == page_host or host.endswith("." + page_host) or _endswith_any(host, skip_hosts):
            continue
        if classify_page(absolute, link.get_text(" ", strip=True))["page_kind"] != "company":
            continue
        if host in seen:
            continue
        seen.add(host)
        found.append(absolute.split("#", 1)[0])
        if len(found) >= max(1, limit):
            break
    return found


def _foreign_geo_conflict(blob: str, places: List[str]) -> bool:
    """True when another country/state is named and none of the target markets are."""
    if places_mentioned(blob, places):
        return False
    countries = (
        "china", "india", "pakistan", "bangladesh", "vietnam", "turkey",
        "germany", "france", "italy", "spain", "canada", "australia",
        "mexico", "brazil", "japan", "korea", "nigeria", "kenya",
    )
    targets = " ".join(places).lower()
    low = blob.lower()
    for c in countries:
        if c in low and c not in targets:
            return True
    # Other US states when hunting a specific state (full name + postal abbrev)
    from app.agents.geo import US_STATE_ALIASES, location_conflicts_with_targets, place_aliases
    if location_conflicts_with_targets(blob, places):
        return True
    target_aliases = set()
    for p in places:
        target_aliases.update(place_aliases(p))
    if any(a in US_STATE_ALIASES for a in target_aliases) or any(
        p.lower() in US_STATE_ALIASES for p in places
    ):
        for state in US_STATE_ALIASES:
            if state in target_aliases or state in {p.lower() for p in places}:
                continue
            if re.search(rf"\b{re.escape(state)}\b", low):
                return True
    return False


def summarize_classifications(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows) or 1
    junk_types = {"directory", "jobs", "news", "article", "marketplace", "skip_domain"}
    junk = sum(1 for r in rows if r.get("entity_type") in junk_types)
    mfr = sum(1 for r in rows if r.get("entity_type") == "manufacturer")
    wrong = sum(1 for r in rows if r.get("entity_type") == "wrong_geo")
    relevant = [r for r in rows if not r.get("reject") and r.get("entity_type") == "company"]
    seeds = []
    for r in rows:
        if r.get("competitor_seed"):
            name = (r.get("company_name") or "")[:80]
            if name and name not in seeds:
                seeds.append(name)

    learned = []
    for r in relevant[:8]:
        title = r.get("company_name") or r.get("title") or ""
        # pull 2–4 word phrases that aren't the company legal name
        for m in re.findall(r"\b([A-Za-z][A-Za-z]+(?:\s+[A-Za-z]+){0,2})\b", title):
            if 4 <= len(m) <= 40 and m.lower() not in {"inc", "llc", "ltd", "the"}:
                learned.append(m)
    # unique learned terms that appeared often-ish
    return {
        "junk_ratio": junk / n,
        "manufacturer_ratio": mfr / n,
        "wrong_geo_ratio": wrong / n,
        "relevant_count": len(relevant),
        "competitor_names": seeds[:4],
        "learned_terms": _uniq_keep(learned, 6),
        "classified": len(rows),
        "rejected": sum(1 for r in rows if r.get("reject")),
    }


def _uniq_keep(items: List[str], limit: int) -> List[str]:
    seen = set()
    out = []
    for i in items:
        k = i.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(i)
        if len(out) >= limit:
            break
    return out
