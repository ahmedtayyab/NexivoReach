"""
Business list sources for the hunt.

A web search ranks pages. These sources list businesses: trade directories
(no key), Companies House (free UK registry key), and OpenStreetMap (mapped
shops, gyms and clubs, no key). Google Places stays off unless a key is set;
it is not required. Each source hands the hunt a company name, a website,
and an address. The hunt then opens the site, reads it, checks the country,
finds emails, checks duplicates, and saves the lead exactly as it does for
a search result.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.config import settings

log = logging.getLogger(__name__)

USER_AGENT = "NexivoReach/1.0 (B2B lead hunt; contact via app)"

# Country name (as used by geo.COUNTRY_ALIASES) -> ISO 3166-1 alpha-2.
COUNTRY_ISO: Dict[str, str] = {
    "united states": "US",
    "united kingdom": "GB",
    "united arab emirates": "AE",
    "saudi arabia": "SA",
    "canada": "CA",
    "germany": "DE",
    "france": "FR",
    "netherlands": "NL",
    "australia": "AU",
    "india": "IN",
    "pakistan": "PK",
    "qatar": "QA",
    "singapore": "SG",
    "malaysia": "MY",
    "turkey": "TR",
    "south africa": "ZA",
    "new zealand": "NZ",
    "china": "CN",
    "spain": "ES",
    "italy": "IT",
    "mexico": "MX",
    "brazil": "BR",
}

# Buyer roles that are shops, gyms, or clubs. OpenStreetMap maps these; it does not map distributors.
RETAIL_ROLES = {"retailer", "retailers", "shop", "shops", "store", "stores", "stockist", "stockists"}
GYM_ROLES = {"gym", "gyms", "fitness centre", "fitness centres", "fitness center", "fitness centers", "studio", "studios"}
CLUB_ROLES = {"club", "clubs", "academy", "academies", "team", "teams", "school", "schools"}
CHANNEL_ROLES = {
    "distributor", "distributors", "wholesaler", "wholesalers", "importer", "importers",
    "supplier", "suppliers", "dealer", "dealers", "trader", "traders", "agent", "agents",
}

# UK SIC 2007 codes by buyer role. 46499 is "wholesale of household goods n.e.c.",
# which is where sports goods and gym equipment wholesalers are registered.
SIC_BY_ROLE: Dict[str, Tuple[str, ...]] = {
    "channel": ("46499", "46160", "46420", "46900"),
    "retail": ("47640", "47710", "47910"),
    "gym": ("93130",),
    "club": ("93120", "93110", "93199"),
}

# Hosts that describe companies but are not the company. A name lookup must not land here.
_REGISTRY_HOSTS = (
    "companieshouse.gov.uk", "company-information.service.gov.uk", "endole.co.uk",
    "companycheck.co.uk", "bizstats.co.uk", "opencorporates.com", "dnb.com", "duedil.com",
    "checkcompany.co.uk", "companieslist.co.uk", "ukbusinessdb.com", "cbonds.com",
    "globaldatabase.com", "find-and-update.company-information.service.gov.uk",
    "zoominfo.com", "crunchbase.com", "bloomberg.com", "linkedin.com", "facebook.com",
    "instagram.com", "twitter.com", "x.com", "yell.com", "192.com", "cylex-uk.co.uk",
    "glassdoor.com", "indeed.com", "indeed.co.uk", "reuters.com", "wikipedia.org",
    "trustpilot.com", "amazon.co.uk", "amazon.com", "ebay.co.uk", "ebay.com", "etsy.com",
    "europages.co.uk", "europages.com", "kompass.com", "thomasnet.com", "hotfrog.co.uk",
    "freeindex.co.uk", "scoot.co.uk", "yelp.co.uk", "yelp.com", "ukdirectory.co.uk",
    "thegazette.co.uk", "gov.uk", "wikidata.org", "pinterest.com", "youtube.com",
)
_LEGAL_SUFFIX = re.compile(
    r"\b(ltd|limited|plc|llp|llc|inc|co|company|corp|corporation|gmbh|uk|holdings|group|trading|international|the)\b\.?",
    re.I,
)


@dataclass
class BusinessCandidate:
    """One business handed to the hunt pipeline."""

    name: str
    website: str = ""
    address: str = ""
    source: str = ""
    ref: str = ""


@dataclass
class SourceStep:
    """What one page of one source produced."""

    source: str
    query: str
    candidates: List[BusinessCandidate] = field(default_factory=list)
    next_cursor: str = ""
    exhausted: bool = False
    note: str = ""
    requests_used: int = 0
    skipped_without_website: int = 0


def _now_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _host(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _host_in(host: str, suffixes: Tuple[str, ...]) -> bool:
    return any(host == s or host.endswith("." + s) for s in suffixes)


# ---------------------------------------------------------------------------
# Planning: which sources apply to one hunt line
# ---------------------------------------------------------------------------


def hunt_country(place: str) -> Tuple[str, str]:
    """('united kingdom', 'GB') for 'Manchester, United Kingdom'. ('', '') when unknown."""
    from app.agents.location_verify import _target_countries

    parts = [p.strip() for p in re.split(r"[,/|]", place or "") if p.strip()]
    found = _target_countries(parts) if parts else set()
    if not found and place:
        found = _target_countries([place])
    for name in sorted(found):
        return name, COUNTRY_ISO.get(name, "")
    return "", ""


def hunt_city(place: str, country_name: str) -> str:
    """The locality part of the hunt place, without the country."""
    from app.agents.location_verify import _is_country_place

    parts = [p.strip() for p in re.split(r"[,/|]", place or "") if p.strip()]
    for part in parts:
        if _is_country_place(part):
            continue
        if country_name and part.lower() == country_name:
            continue
        return part
    return ""


def role_family(role: str) -> str:
    low = (role or "").strip().lower()
    if low in RETAIL_ROLES:
        return "retail"
    if low in GYM_ROLES:
        return "gym"
    if low in CLUB_ROLES:
        return "club"
    if low in CHANNEL_ROLES or not low:
        return "channel"
    return "other"


def source_plan_for_intent(query: str, place: str) -> Dict[str, Any]:
    """
    Which list sources a hunt line can use, and the pieces each one needs.
    The line is not rewritten; sources get the product and role parsed from it.
    """
    from app.agents.geo import parse_discovery_query

    product, role, parsed_place = parse_discovery_query(query)
    product = _clean(product)
    role = _clean(role).lower()
    place = _clean(place or parsed_place)
    country_name, iso = hunt_country(place)
    city = hunt_city(place, country_name)
    family = role_family(role)

    sources: List[str] = []
    # Places stays opt-in. It needs a billed Google Cloud project; never turn it
    # on just because some other Google key is present.
    if settings.GOOGLE_PLACES_API_KEY:
        sources.append("places")
    # Stockists list independent shops and regional dealers — the companies
    # more likely to buy than the industry giants on page 1. Exhibitors stay
    # last and off by default; those show sites are JS shells.
    if settings.STOCKIST_SOURCE_ENABLED:
        sources.append("stockists")
    if settings.EXHIBITOR_SOURCE_ENABLED:
        sources.append("exhibitors")
    if settings.COMPANIES_HOUSE_API_KEY and iso == "GB" and family in SIC_BY_ROLE:
        sources.append("companies_house")
    if settings.OSM_SOURCE_ENABLED and family in ("retail", "gym", "club") and (iso or city):
        sources.append("osm")
    if settings.DIRECTORY_SOURCE_ENABLED:
        sources.append("directory")
    return {
        "product": product,
        "role": role,
        "family": family,
        "place": place,
        "country": country_name,
        "iso": iso,
        "city": city,
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# Google Places Text Search (New)
# ---------------------------------------------------------------------------

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELDS = (
    "places.id,places.displayName,places.formattedAddress,places.websiteUri,"
    "places.businessStatus,places.types,nextPageToken"
)


def places_requests_this_month(session) -> int:
    from sqlmodel import select

    from app.models.schemas import ApiUsageMonth

    row = session.exec(
        select(ApiUsageMonth).where(
            ApiUsageMonth.provider == "google_places",
            ApiUsageMonth.month == _now_month(),
        )
    ).first()
    return int(row.count or 0) if row else 0


def record_places_request(session, n: int = 1) -> int:
    from sqlmodel import select

    from app.models.schemas import ApiUsageMonth

    month = _now_month()
    row = session.exec(
        select(ApiUsageMonth).where(
            ApiUsageMonth.provider == "google_places",
            ApiUsageMonth.month == month,
        )
    ).first()
    if not row:
        row = ApiUsageMonth(
            id=f"usage-{uuid4().hex[:10]}", provider="google_places", month=month, count=0,
        )
    row.count = int(row.count or 0) + n
    row.updated_at = datetime.now(timezone.utc).isoformat()
    session.add(row)
    session.commit()
    return row.count


def places_budget_allows(used_this_month: int, cap: Optional[int] = None) -> bool:
    """False once the month's ledger reaches the cap. The cap sits under Google's free allowance."""
    limit = int(cap if cap is not None else settings.GOOGLE_PLACES_MONTHLY_CAP or 0)
    return limit > 0 and used_this_month < limit


def parse_places_payload(payload: Dict[str, Any]) -> Tuple[List[BusinessCandidate], str, int]:
    """Candidates with a website, the next page token, and how many had no website."""
    out: List[BusinessCandidate] = []
    skipped = 0
    for item in payload.get("places") or []:
        status = str(item.get("businessStatus") or "")
        if status and status != "OPERATIONAL":
            continue
        website = str(item.get("websiteUri") or "").strip()
        name = _clean(str((item.get("displayName") or {}).get("text") or ""))
        if not website:
            skipped += 1
            continue
        out.append(BusinessCandidate(
            name=name,
            website=website,
            address=_clean(str(item.get("formattedAddress") or "")),
            source="places",
            ref=str(item.get("id") or ""),
        ))
    return out, str(payload.get("nextPageToken") or ""), skipped


def places_step(
    query: str,
    cursor: str,
    *,
    region_code: str = "",
    api_key: str = "",
    client: Optional[httpx.Client] = None,
) -> SourceStep:
    """One page of Google Places for the exact hunt line. The caller checks the ledger first."""
    key = api_key or settings.GOOGLE_PLACES_API_KEY
    step = SourceStep(source="places", query=query)
    if not key:
        step.exhausted = True
        step.note = "Google Places is off (no key)."
        return step
    body: Dict[str, Any] = {"textQuery": query, "pageSize": 20}
    if region_code:
        body["regionCode"] = region_code.lower()
    if cursor:
        body["pageToken"] = cursor
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": PLACES_FIELDS,
        "User-Agent": USER_AGENT,
    }
    own = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        res = client.post(PLACES_URL, headers=headers, json=body)
        step.requests_used = 1
        if res.status_code >= 400:
            step.exhausted = True
            step.note = f"Google Places answered {res.status_code}: {res.text[:160]}"
            return step
        cands, token, skipped = parse_places_payload(res.json())
        step.candidates = cands
        step.skipped_without_website = skipped
        step.next_cursor = token
        step.exhausted = not token
        step.note = f"Google Places listed {len(cands)} businesses with websites for “{query}”."
        return step
    except Exception as exc:
        step.exhausted = True
        step.note = f"Google Places did not answer: {exc}"
        return step
    finally:
        if own:
            client.close()


# ---------------------------------------------------------------------------
# Companies House (UK registry)
# ---------------------------------------------------------------------------

CH_URL = "https://api.company-information.service.gov.uk/advanced-search/companies"
CH_PAGE = 15

_NAME_WORDS_BY_TRADE: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...] = (
    (("boxing", "mma", "martial", "fight", "combat", "kick"), ("boxing", "fight", "martial", "combat")),
    (("knee", "sleeve", "sleeves"), ("sleeve", "knee")),
    (("wrist", "wrap", "wraps", "strap", "straps", "hook", "hooks", "grip", "grips"), ("wrap", "strap")),
    (("weight", "lifting", "strength", "gym", "fitness", "powerlifting", "crossfit"), ("fitness", "gym", "strength", "lifting")),
    (("sport", "sports", "athletic", "team", "football", "cricket", "rugby", "hockey"), ("sport", "athletic")),
    (("yoga", "pilates"), ("yoga", "pilates")),
    (("cycle", "cycling", "bike"), ("cycle", "bike")),
    (("outdoor", "camping", "hiking"), ("outdoor",)),
)
_DEFAULT_NAME_WORDS = ("sport", "fitness", "gym")


def company_name_words(product: str, role: str = "") -> List[str]:
    """Words a UK company in this trade is likely to carry in its registered name."""
    blob = f"{product} {role}".lower()
    out: List[str] = []
    for triggers, words in _NAME_WORDS_BY_TRADE:
        if any(t in blob for t in triggers):
            for w in words:
                if w not in out:
                    out.append(w)
    for w in _DEFAULT_NAME_WORDS:
        if w not in out:
            out.append(w)
    return out[:6]


def parse_ch_cursor(raw: str) -> Dict[str, int]:
    try:
        data = json.loads(raw or "{}")
    except Exception:
        data = {}
    return {"word": int(data.get("word") or 0), "start": int(data.get("start") or 0)}


def ch_cursor_json(word: int, start: int) -> str:
    return json.dumps({"word": int(word), "start": int(start)})


def parse_ch_items(payload: Dict[str, Any]) -> List[BusinessCandidate]:
    out: List[BusinessCandidate] = []
    for item in payload.get("items") or []:
        name = _clean(str(item.get("company_name") or ""))
        if not name:
            continue
        addr = item.get("registered_office_address") or {}
        parts = [
            str(addr.get(k) or "").strip()
            for k in ("address_line_1", "locality", "region", "postal_code", "country")
        ]
        address = ", ".join(p for p in parts if p)
        if address and "united kingdom" not in address.lower() and not str(addr.get("country") or "").strip():
            address = f"{address}, United Kingdom"
        out.append(BusinessCandidate(
            name=name,
            website="",
            address=address,
            source="companies_house",
            ref=str(item.get("company_number") or ""),
        ))
    return out


def company_name_core(name: str) -> List[str]:
    """Meaningful name tokens: 'Prime Gear Sports Ltd' -> ['prime', 'gear', 'sports']."""
    text = re.sub(r"[^a-z0-9& ]+", " ", (name or "").lower().replace("&", " and "))
    text = _LEGAL_SUFFIX.sub(" ", text)
    tokens = [t for t in text.split() if len(t) >= 2 and t not in {"and", "of", "for"}]
    return tokens[:5]


# Name words shared by half the trade. They never identify a company on their own.
_GENERIC_NAME_WORDS = {
    "sport", "sports", "fitness", "gym", "gyms", "equipment", "supplies", "supply",
    "europe", "european", "international", "global", "direct", "online", "shop", "store",
    "stores", "trading", "uk", "england", "london", "british", "britain", "boxing", "fight",
    "martial", "arts", "athletic", "athletics", "health", "leisure", "outdoor", "outdoors",
    "wholesale", "distribution", "imports", "exports", "services", "solutions", "products",
}


def website_matches_company(name: str, url: str, title: str = "") -> bool:
    """
    True when a search hit is the company's own site, judged by the domain.

    A page title is not evidence: directories and news sites print the
    company name in their titles. The domain has to carry the name.
    """
    del title
    host = _host(url)
    if not host or _host_in(host, _REGISTRY_HOSTS):
        return False
    tokens = company_name_core(name)
    if not tokens:
        return False
    distinct = [t for t in tokens if t not in _GENERIC_NAME_WORDS]
    label_compact = re.sub(r"[^a-z0-9]", "", host.split(".")[0])
    joined = "".join(tokens)
    if joined and joined in label_compact:
        return True
    if len(tokens) >= 2 and "".join(tokens[:2]) in label_compact:
        return True
    if distinct and len(distinct[0]) >= 5 and distinct[0] in label_compact:
        return True
    distinct_hits = sum(1 for t in distinct if len(t) >= 3 and t in label_compact)
    all_hits = sum(1 for t in tokens if len(t) >= 3 and t in label_compact)
    return distinct_hits >= 1 and all_hits >= max(2, (len(tokens) + 1) // 2)


def domain_guesses(name: str, tlds: Tuple[str, ...] = (".co.uk", ".com", ".uk")) -> List[str]:
    """Likely domains for a company name: 'Kukri Sports Ltd' -> kukrisports.co.uk, kukrisports.com, ..."""
    tokens = company_name_core(name)
    if not tokens:
        return []
    labels: List[str] = []
    joined = "".join(tokens)
    if len(joined) >= 4:
        labels.append(joined)
    if len(tokens) >= 3:
        labels.append("".join(tokens[:2]))
    # A single name word ("thomas") is not tried: thomas.co is somebody else.
    if len(tokens) >= 2:
        hyphen = "-".join(tokens)
        if hyphen not in labels:
            labels.append(hyphen)
    out: List[str] = []
    for label in labels[:3]:
        for tld in tlds:
            out.append(f"{label}{tld}")
    return out


def _page_names_company(html: str, name: str) -> bool:
    """A live page that mentions the company's own words is the company's site, not a parked domain."""
    low = (html or "").lower()
    if not low or "domain is for sale" in low or "buy this domain" in low or "parked" in low[:4000]:
        return False
    tokens = company_name_core(name)
    distinct = [t for t in tokens if t not in _GENERIC_NAME_WORDS] or tokens
    return any(t in low for t in distinct[:2])


def probe_domain_guesses(
    name: str,
    *,
    tlds: Tuple[str, ...] = (".co.uk", ".com", ".uk"),
    client: Optional[httpx.Client] = None,
    fetch: Optional[Callable[[str], Tuple[int, str, str]]] = None,
) -> str:
    """
    Try the likely domains directly. No search engine, no rate limit.
    Returns the homepage that answered 200 and names the company, or ''.
    """
    guesses = domain_guesses(name, tlds)
    if not guesses:
        return ""
    own = client is None and fetch is None
    client = client or (httpx.Client(timeout=5.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) if fetch is None else None)

    def _get(url: str) -> Tuple[int, str, str]:
        if fetch is not None:
            return fetch(url)
        res = client.get(url)
        return res.status_code, str(res.url), res.text[:60000]

    try:
        for host in guesses:
            for scheme in ("https://", "http://"):
                url = f"{scheme}{host}/"
                try:
                    status, final_url, html = _get(url)
                except Exception:
                    continue
                if status != 200:
                    continue
                final_host = _host(final_url)
                if not final_host or _host_in(final_host, _REGISTRY_HOSTS):
                    break
                if _page_names_company(html, name):
                    parsed = urlparse(final_url)
                    return f"{parsed.scheme}://{parsed.netloc}/"
                break
        return ""
    finally:
        if own and client is not None:
            client.close()


def resolve_company_website(
    name: str,
    searcher: Callable[[str], List[Dict[str, str]]],
    *,
    place_hint: str = "",
    prober: Optional[Callable[[str], str]] = None,
) -> str:
    """
    A registered company's own website, or ''.

    Likely domains are tried first (no search engine involved). Then one web
    search with the plain name; only a hit whose domain carries the name counts.
    """
    guess = (prober or probe_domain_guesses)(name)
    if guess:
        return guess
    query = _clean(name)
    if place_hint:
        query = f"{query} {place_hint}"
    try:
        hits = searcher(query) or []
    except Exception as exc:
        log.warning("Website lookup failed for %s: %s", name, exc)
        return ""
    for hit in hits[:8]:
        url = str(hit.get("href") or "").strip()
        if not url.startswith("http"):
            continue
        if website_matches_company(name, url, str(hit.get("title") or "")):
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}/"
    return ""


def companies_house_step(
    *,
    product: str,
    role: str,
    city: str,
    cursor: str,
    searcher: Callable[[str], List[Dict[str, str]]],
    api_key: str = "",
    client: Optional[httpx.Client] = None,
    resolve_limit: int = CH_PAGE,
    pause_sec: float = 0.8,
    prober: Optional[Callable[[str], str]] = None,
) -> SourceStep:
    """
    One page of the UK register for this trade and role, with each company
    name resolved to its own website. Names that do not resolve are dropped.
    """
    key = (api_key or settings.COMPANIES_HOUSE_API_KEY or "").strip().strip("\"'")
    label = f"{product} {role}".strip()
    step = SourceStep(source="companies_house", query=label)
    if not key:
        step.exhausted = True
        step.note = "Companies House is off (no key)."
        return step
    words = company_name_words(product, role)
    sic = SIC_BY_ROLE.get(role_family(role)) or SIC_BY_ROLE["channel"]
    pos = parse_ch_cursor(cursor)
    word_i, start = pos["word"], pos["start"]
    if word_i >= len(words):
        step.exhausted = True
        step.note = "Companies House: every name word for this trade has been read."
        return step
    params: Dict[str, Any] = {
        "company_status": "active",
        "sic_codes": ",".join(sic),
        "company_name_includes": words[word_i],
        "size": CH_PAGE,
        "start_index": start,
    }
    if city:
        params["location"] = city
    own = client is None
    client = client or httpx.Client(timeout=15.0, headers={"User-Agent": USER_AGENT})
    try:
        res = client.get(CH_URL, params=params, auth=(key, ""))
        step.requests_used = 1
        if res.status_code == 404:
            items: List[BusinessCandidate] = []
        elif res.status_code == 401:
            step.exhausted = False
            step.next_cursor = cursor
            step.note = (
                "Companies House rejected the key (401). Create a live REST key "
                "(not test, not streaming) and paste it again."
            )
            return step
        elif res.status_code >= 400:
            step.exhausted = False
            step.next_cursor = cursor
            step.note = f"Companies House answered {res.status_code}: {res.text[:160]}"
            return step
        else:
            items = parse_ch_items(res.json())
    except Exception as exc:
        step.exhausted = False
        step.next_cursor = cursor
        step.note = f"Companies House did not answer: {exc}"
        return step
    finally:
        if own:
            client.close()

    resolved: List[BusinessCandidate] = []
    for n, cand in enumerate(items[:resolve_limit]):
        if n:
            time.sleep(pause_sec)
        site = resolve_company_website(cand.name, searcher, place_hint="", prober=prober)
        if site:
            cand.website = site
            resolved.append(cand)
    step.candidates = resolved
    step.skipped_without_website = len(items) - len(resolved)

    if len(items) < CH_PAGE:
        word_i, start = word_i + 1, 0
    else:
        start += CH_PAGE
    step.exhausted = word_i >= len(words)
    step.next_cursor = "" if step.exhausted else ch_cursor_json(word_i, start)
    step.note = (
        f"Companies House listed {len(items)} “{words[pos['word']]}” companies"
        + (f" in {city}" if city else "")
        + f"; {len(resolved)} have a website."
    )
    return step


# ---------------------------------------------------------------------------
# OpenStreetMap via Overpass
# ---------------------------------------------------------------------------

# Public instances. All of them are slow (30–90 s a query) and sometimes time out,
# so this source makes one call per hunt line and is never on the critical path twice.
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
OVERPASS_TIMEOUT_SEC = 60.0
# Exact tag values only. A regex filter makes Overpass scan every object in the area.
_OSM_SELECTORS: Dict[str, Tuple[str, ...]] = {
    "retail": ('["shop"="sports"]', '["shop"="fitness"]', '["shop"="outdoor"]'),
    "gym": ('["leisure"="fitness_centre"]',),
    "club": ('["club"="sport"]', '["leisure"="sports_centre"]'),
}


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode_bbox(city: str, iso: str = "", client: Optional[httpx.Client] = None) -> Tuple[float, float, float, float]:
    """(south, west, north, east) for a city from Nominatim. Zeros when unknown."""
    if not (city or "").strip():
        return (0.0, 0.0, 0.0, 0.0)
    params: Dict[str, Any] = {"q": city, "format": "json", "limit": 1}
    if iso:
        params["countrycodes"] = iso.lower()
    own = client is None
    client = client or httpx.Client(timeout=12.0, headers={"User-Agent": USER_AGENT})
    try:
        res = client.get(NOMINATIM_URL, params=params)
        if res.status_code != 200:
            return (0.0, 0.0, 0.0, 0.0)
        rows = res.json() or []
        if not rows:
            return (0.0, 0.0, 0.0, 0.0)
        box = rows[0].get("boundingbox") or []
        if len(box) != 4:
            return (0.0, 0.0, 0.0, 0.0)
        south, north, west, east = (float(v) for v in box)
        return (south, west, north, east)
    except Exception as exc:
        log.warning("Nominatim lookup failed for %s: %s", city, exc)
        return (0.0, 0.0, 0.0, 0.0)
    finally:
        if own:
            client.close()


def overpass_query(
    family: str,
    *,
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    iso: str = "",
    limit: int = 300,
) -> str:
    """
    Overpass QL for mapped businesses of this kind that carry a website tag.
    A bounding box is the fast path. A country area is the fallback.
    """
    selectors = _OSM_SELECTORS.get(family) or ()
    if not selectors:
        return ""
    south, west, north, east = bbox
    area = ""
    scope = ""
    if any(bbox) and south < north and west < east:
        scope = f"({south:.5f},{west:.5f},{north:.5f},{east:.5f})"
    elif iso:
        area = f'area["ISO3166-1"="{iso.upper()}"]["admin_level"="2"]->.a;'
        scope = "(area.a)"
    else:
        return ""
    body = []
    for sel in selectors:
        body.append(f'nwr{sel}["website"]{scope};')
        body.append(f'nwr{sel}["contact:website"]{scope};')
    return f"[out:json][timeout:40];{area}({''.join(body)});out tags center {int(limit)};"


def parse_overpass_payload(payload: Dict[str, Any], country_label: str = "") -> List[BusinessCandidate]:
    out: List[BusinessCandidate] = []
    seen_hosts: set[str] = set()
    for el in payload.get("elements") or []:
        tags = el.get("tags") or {}
        website = str(tags.get("website") or tags.get("contact:website") or "").strip()
        name = _clean(str(tags.get("name") or ""))
        if not website or not name:
            continue
        if not website.lower().startswith("http"):
            website = f"https://{website}"
        host = _host(website)
        if not host or host in seen_hosts:
            continue
        seen_hosts.add(host)
        parts = [
            str(tags.get(k) or "").strip()
            for k in ("addr:street", "addr:city", "addr:postcode", "addr:country")
        ]
        address = ", ".join(p for p in parts if p)
        if country_label and country_label.lower() not in address.lower():
            address = f"{address}, {country_label}" if address else country_label
        out.append(BusinessCandidate(
            name=name,
            website=website,
            address=address,
            source="osm",
            ref=f"{el.get('type', '')}/{el.get('id', '')}",
        ))
    return out


def osm_step(
    *,
    family: str,
    city: str,
    iso: str,
    country_label: str,
    client: Optional[httpx.Client] = None,
) -> SourceStep:
    """One Overpass query. The result is the whole list, so the step is final."""
    step = SourceStep(source="osm", query=f"{family} in {city or iso}", exhausted=True)
    own = client is None
    client = client or httpx.Client(timeout=OVERPASS_TIMEOUT_SEC, headers={"User-Agent": USER_AGENT})
    try:
        bbox = geocode_bbox(city, iso, client=client) if city else (0.0, 0.0, 0.0, 0.0)
        if city and not any(bbox):
            step.note = f"OpenStreetMap could not place “{city}” on the map."
            return step
        ql = overpass_query(family, bbox=bbox, iso=iso)
        if not ql:
            step.note = "OpenStreetMap: nothing to ask for this kind of buyer."
            return step
        last_error = ""
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                res = client.post(endpoint, data={"data": ql})
                step.requests_used += 1
                if res.status_code in (429, 504, 502, 503):
                    last_error = f"{endpoint} answered {res.status_code}"
                    continue
                if res.status_code >= 400:
                    last_error = f"{endpoint} answered {res.status_code}"
                    continue
                cands = parse_overpass_payload(res.json(), country_label)
                step.candidates = cands
                step.note = f"OpenStreetMap listed {len(cands)} mapped {family} businesses with websites in {city or country_label or iso}."
                return step
            except Exception as exc:
                last_error = str(exc)
                continue
        step.note = f"OpenStreetMap did not answer: {last_error}"
        return step
    finally:
        if own:
            client.close()


# ---------------------------------------------------------------------------
# Public trade directories (no key)
# ---------------------------------------------------------------------------

_EUROPAGES_ROLE = {
    "channel": "wholesaler",
    "retail": "retailer",
    "gym": "wholesaler",
    "club": "wholesaler",
    "other": "wholesaler",
}
_DIR_KEYWORDS: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...] = (
    (("boxing", "mma", "martial", "fight", "combat", "kick"), ("boxing", "sport")),
    (("knee", "sleeve", "sleeves", "wrap", "wraps", "strap", "straps"), ("fitness", "sports-goods")),
    (("weight", "lifting", "strength", "gym", "fitness", "powerlifting", "crossfit"), ("fitness", "sport")),
    (("yoga", "pilates"), ("fitness", "sport")),
    (("sport", "sports", "athletic", "team", "football", "cricket", "rugby", "hockey"), ("sport", "sports-goods")),
)
_DEFAULT_DIR_KEYWORDS = ("sport", "sports-goods", "fitness")


def directory_keywords(product: str) -> List[str]:
    """Europages-style category slugs for this product. Product words stay in the hunt query; these are only list-page paths."""
    blob = (product or "").lower()
    out: List[str] = []
    for triggers, words in _DIR_KEYWORDS:
        if any(t in blob for t in triggers):
            for w in words:
                if w not in out:
                    out.append(w)
    for w in _DEFAULT_DIR_KEYWORDS:
        if w not in out:
            out.append(w)
    return out[:3]


def europages_country_slug(country_name: str, iso: str = "") -> str:
    name = (country_name or "").strip().lower()
    if not name and iso == "GB":
        name = "united kingdom"
    if not name and iso == "US":
        name = "united states"
    return name.replace(" ", "%20") if name else ""


def directory_urls_for_plan(plan: Dict[str, Any]) -> List[str]:
    """Public list pages for this hunt line. The pages themselves are never leads."""
    product = _clean(str(plan.get("product") or ""))
    family = str(plan.get("family") or "channel")
    country = str(plan.get("country") or "")
    iso = str(plan.get("iso") or "")
    keywords = directory_keywords(product)
    role_slug = _EUROPAGES_ROLE.get(family, "wholesaler")
    country_slug = europages_country_slug(country, iso)
    urls: List[str] = []

    def _add(url: str) -> None:
        if url and url not in urls:
            urls.append(url)

    if country_slug:
        for kw in keywords:
            _add(f"https://www.europages.co.uk/companies/{country_slug}/{role_slug}/{kw}.html")
    for kw in keywords[:2]:
        _add(f"https://www.europages.co.uk/companies/{kw}.html")
    if iso == "GB" and family == "channel":
        _add("https://www.esources.co.uk/wholesale-suppliers/330/1/2/Equipment/")
        _add("https://www.thewholesaler.co.uk/wholesalers/sports-and-leisure/")
    return urls[:8]


def parse_dir_cursor(raw: str) -> int:
    try:
        return max(0, int(raw or 0))
    except Exception:
        return 0


def directory_step(
    *,
    urls: List[str],
    cursor: str,
    client: Optional[httpx.Client] = None,
    extractor: Optional[Callable[[str, str], List[str]]] = None,
) -> SourceStep:
    """
    One public directory page. Company websites on it go to the hunt;
    the directory host is never saved as a lead.
    """
    from app.agents.serp_classifier import extract_directory_companies

    index = parse_dir_cursor(cursor)
    step = SourceStep(source="directory", query=urls[index] if 0 <= index < len(urls) else "")
    if index >= len(urls):
        step.exhausted = True
        step.note = "Every directory page for this hunt line has been read."
        return step
    url = urls[index]
    pull = extractor or extract_directory_companies
    own = client is None
    client = client or httpx.Client(
        timeout=12.0, follow_redirects=True, headers={"User-Agent": USER_AGENT},
    )
    try:
        res = client.get(url)
        step.requests_used = 1
        if res.status_code >= 400 or not res.text:
            step.next_cursor = str(index + 1)
            step.exhausted = (index + 1) >= len(urls)
            step.note = f"Directory page did not load ({res.status_code}): {url}"
            return step
        links = pull(res.text, str(res.url)) or []
        step.candidates = [
            BusinessCandidate(name="", website=link, source="directory") for link in links
        ]
        step.next_cursor = str(index + 1)
        step.exhausted = (index + 1) >= len(urls)
        step.note = f"Directory listed {len(step.candidates)} company websites on {url}."
        return step
    except Exception as exc:
        step.next_cursor = str(index + 1)
        step.exhausted = (index + 1) >= len(urls)
        step.note = f"Directory page did not answer: {exc}"
        return step
    finally:
        if own:
            client.close()
