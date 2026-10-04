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
SEARCH_HOSTS = (
    "google.com", "duckduckgo.com",
)
ARTICLE_TITLE = re.compile(
    r"\b(top\s+\d+|best\s+\d+|complete guide|how to|what is)\b",
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

    if not host and not (row.get("company_name") and row.get("source") == "maps"):
        reject, entity, reason = True, "unknown", "No website or Maps identity"

    elif _endswith_any(host, SEARCH_HOSTS):
        reject, entity, reason = True, "skip_domain", "Search engine page"

    elif _endswith_any(host, ARTICLE_HOSTS) or "/wiki" in url.lower():
        reject, entity, reason = True, "article", "Article or wiki page"

    elif ARTICLE_TITLE.search(title):
        reject, entity, reason = True, "article", "Article or listicle title"

    elif re.search(r"/(news|press|article|wiki)(/|$)", url.lower()):
        reject, entity, reason = True, "article", "Article URL"

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
