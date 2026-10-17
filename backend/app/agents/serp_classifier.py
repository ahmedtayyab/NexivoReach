"""Cheap SERP-row classification. Discovery only — not qualification."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse


ARTICLE_HOSTS = (
    "wikipedia.org", "medium.com", "quora.com",
    "reuters.com", "techcrunch.com", "forbes.com",
    "businessinsider.com", "prnewswire.com", "globenewswire.com",
)
REVIEW_HOSTS = (
    "trustpilot.com", "sitejabber.com", "consumeraffairs.com",
    "wirecutter.com", "g2.com", "capterra.com",
)
DIRECTORY_HOSTS = (
    "europages.com", "europages.co.uk", "kompass.com", "yell.com",
    "yelp.com", "yelp.co.uk", "thomasnet.com", "yellowpages.com",
    "yellowpages.co.uk", "hotfrog.com", "hotfrog.co.uk", "cylex.co.uk",
    "brownbook.net", "scoot.co.uk", "192.com", "tradekey.com",
)
SEARCH_HOSTS = (
    "google.com", "duckduckgo.com",
)
ARTICLE_TITLE = re.compile(
    r"\b(top\s+\d+|best\s+\d+|complete guide|how to|what is)\b",
    re.I,
)
REVIEW_TITLE = re.compile(r"\b(review|reviews|roundup|listicle)\b", re.I)
ARTICLE_PATH = re.compile(
    r"/(blog|blogs|news|press|articles?|wiki|reviews?|guides?|insights|learn|resources|roundups?)(/|$)",
    re.I,
)
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


def _path(url: str) -> str:
    return (urlparse(url or "").path or "").lower()


def _is_homepage(url: str) -> bool:
    path = _path(url).rstrip("/")
    return path in ("", "/index.html", "/index.php", "/home", "/en")


def classify_page(url: str, title: str = "") -> Dict[str, Any]:
    """
    article / directory / company.

    burn_domain is true only for a host that is itself an article or review site.
    A /blog URL on a company domain is skipped without blocking that company's homepage.
    Directory hosts are not burned so later listing pages can still be mined.
    """
    host = _host(url)
    path = _path(url)
    if host and _endswith_any(host, DIRECTORY_HOSTS):
        return {"page_kind": "directory", "burn_domain": False, "reason": "Directory page"}
    if host and (_endswith_any(host, ARTICLE_HOSTS) or _endswith_any(host, REVIEW_HOSTS) or "/wiki" in (url or "").lower()):
        return {"page_kind": "article", "burn_domain": True, "reason": "Article or review site"}
    if ARTICLE_PATH.search(path) or "/best-" in path:
        return {"page_kind": "article", "burn_domain": False, "reason": "Article or review URL"}
    if ARTICLE_TITLE.search(title or ""):
        return {
            "page_kind": "article",
            "burn_domain": _is_homepage(url),
            "reason": "Article or listicle title",
        }
    if REVIEW_TITLE.search(title or "") and not _is_homepage(url):
        return {"page_kind": "article", "burn_domain": False, "reason": "Review page"}
    return {"page_kind": "company", "burn_domain": False, "reason": ""}


_OUTBOUND_SKIP_HOSTS = SEARCH_HOSTS + ARTICLE_HOSTS + REVIEW_HOSTS + DIRECTORY_HOSTS + (
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "youtu.be", "pinterest.com", "tiktok.com", "reddit.com",
)


def extract_directory_companies(html: str, page_url: str, limit: int = 12) -> List[str]:
    """Company websites linked from a directory page. The directory itself is not a lead."""
    if not html or not page_url:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    page_host = _host(page_url)
    soup = BeautifulSoup(html, "html.parser")
    found: List[str] = []
    seen: set[str] = set()
    for link in soup.select("a[href]"):
        href = str(link.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute = urljoin(page_url, href)
        host = _host(absolute)
        if not host or host == page_host or _endswith_any(host, _OUTBOUND_SKIP_HOSTS):
            continue
        if classify_page(absolute, link.get_text(" ", strip=True))["page_kind"] != "company":
            continue
        key = host
        if key in seen:
            continue
        seen.add(key)
        found.append(absolute.split("#", 1)[0])
        if len(found) >= max(1, limit):
            break
    return found


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

    if page["page_kind"] != "company":
        reject, entity, reason = True, page["page_kind"], page["reason"]
        burn_domain = bool(page.get("burn_domain"))

    elif not host and not (row.get("company_name") and row.get("source") == "maps"):
        reject, entity, reason = True, "unknown", "No website or Maps identity"

    elif _endswith_any(host, SEARCH_HOSTS):
        reject, entity, reason = True, "skip_domain", "Search engine page"
        burn_domain = True

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
