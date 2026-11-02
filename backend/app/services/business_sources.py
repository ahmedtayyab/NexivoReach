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
    email: str = ""


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
    if settings.WIKIDATA_SOURCE_ENABLED and family == "channel" and iso:
        sources.append("wikidata")
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
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
OVERPASS_TIMEOUT_SEC = 60.0
# Exact tag values only. A regex filter makes Overpass scan every object in the area.
_OSM_SELECTORS: Dict[str, Tuple[str, ...]] = {
    "retail": (
        '["shop"="sports"]',
        '["shop"="fitness"]',
        '["shop"="outdoor"]',
        '["shop"="bicycle"]',
        '["shop"="martial_arts"]',
        '["shop"="hunting"]',
    ),
    "gym": (
        '["leisure"="fitness_centre"]',
        '["leisure"="sports_centre"]',
        '["amenity"="gym"]',
    ),
    "club": (
        '["club"="sport"]',
        '["leisure"="sports_centre"]',
    ),
    "rehab": (
        '["shop"="medical_supply"]',
        '["healthcare"="physiotherapist"]',
        '["healthcare"="rehabilitation"]',
    ),
}
OSM_GRID_N = 3
OSM_TILE_LIMIT = 80


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api/"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_PAGE = 40
_OSM_CLOSED = ("disused", "abandoned", "demolished", "razed", "removed", "closed")


def geocode_bbox(city: str, iso: str = "", client: Optional[httpx.Client] = None) -> Tuple[float, float, float, float]:
    """(south, west, north, east) for a city. Nominatim first, Photon if that misses."""
    if not (city or "").strip():
        return (0.0, 0.0, 0.0, 0.0)
    own = client is None
    client = client or httpx.Client(timeout=12.0, headers={"User-Agent": USER_AGENT})
    try:
        box = _nominatim_bbox(city, iso, client)
        if any(box):
            return box
        return _photon_bbox(city, iso, client)
    finally:
        if own:
            client.close()


def _nominatim_bbox(city: str, iso: str, client: httpx.Client) -> Tuple[float, float, float, float]:
    params: Dict[str, Any] = {"q": city, "format": "json", "limit": 1}
    if iso:
        params["countrycodes"] = iso.lower()
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


def _photon_bbox(city: str, iso: str, client: httpx.Client) -> Tuple[float, float, float, float]:
    q = f"{city}, {iso}" if iso else city
    try:
        res = client.get(PHOTON_URL, params={"q": q, "limit": 1})
        if res.status_code != 200:
            return (0.0, 0.0, 0.0, 0.0)
        feats = (res.json() or {}).get("features") or []
        if not feats:
            return (0.0, 0.0, 0.0, 0.0)
        props = feats[0].get("properties") or {}
        ext = props.get("extent") or []
        if len(ext) == 4:
            west, north, east, south = (float(v) for v in ext)
            if south < north and west < east:
                return (south, west, north, east)
        coords = (feats[0].get("geometry") or {}).get("coordinates") or []
        if len(coords) >= 2:
            lon, lat = float(coords[0]), float(coords[1])
            return (lat - 0.09, lon - 0.14, lat + 0.09, lon + 0.14)
        return (0.0, 0.0, 0.0, 0.0)
    except Exception as exc:
        log.warning("Photon lookup failed for %s: %s", city, exc)
        return (0.0, 0.0, 0.0, 0.0)


def osm_grid_cells(
    bbox: Tuple[float, float, float, float],
    n: int = OSM_GRID_N,
) -> List[Tuple[float, float, float, float]]:
    """Split a Nominatim city box into n×n tiles (south, west, north, east)."""
    south, west, north, east = bbox
    if n <= 1 or not any(bbox) or south >= north or west >= east:
        return [bbox]
    dlat = (north - south) / n
    dlon = (east - west) / n
    cells: List[Tuple[float, float, float, float]] = []
    for i in range(n):
        for j in range(n):
            cells.append((
                south + i * dlat,
                west + j * dlon,
                south + (i + 1) * dlat,
                west + (j + 1) * dlon,
            ))
    return cells


def _osm_cursor_payload(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw or "")
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


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
        if _osm_is_closed(tags):
            continue
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
        email = str(tags.get("email") or tags.get("contact:email") or "").strip()
        out.append(BusinessCandidate(
            name=name,
            website=website,
            address=address,
            source="osm",
            ref=f"{el.get('type', '')}/{el.get('id', '')}",
            email=email,
        ))
    return out


def _osm_is_closed(tags: Dict[str, Any]) -> bool:
    if any(str(tags.get(k) or "").lower() in {"yes", "true", "1"} for k in _OSM_CLOSED):
        return True
    if any(k.startswith("disused:") or k.startswith("abandoned:") for k in tags):
        return True
    return False


def osm_step(
    *,
    family: str,
    city: str,
    iso: str,
    country_label: str,
    cursor: str = "",
    client: Optional[httpx.Client] = None,
) -> SourceStep:
    """One Overpass query. City hunts walk an n×n bbox grid via HuntSourceCursor."""
    step = SourceStep(source="osm", query=f"{family} in {city or iso}", exhausted=True)
    own = client is None
    client = client or httpx.Client(timeout=OVERPASS_TIMEOUT_SEC, headers={"User-Agent": USER_AGENT})
    try:
        payload = _osm_cursor_payload(cursor)
        tile_index = 0
        tile_count = 1
        place_label = city or country_label or iso
        if city:
            bbox_raw = payload.get("bbox")
            if isinstance(bbox_raw, list) and len(bbox_raw) == 4:
                try:
                    bbox = tuple(float(v) for v in bbox_raw)
                except (TypeError, ValueError):
                    bbox = (0.0, 0.0, 0.0, 0.0)
            else:
                bbox = geocode_bbox(city, iso, client=client)
            if not any(bbox):
                step.note = f"OpenStreetMap could not place “{city}” on the map."
                return step
            n = int(payload.get("n") or OSM_GRID_N)
            n = max(1, min(n, 4))
            tiles = osm_grid_cells(bbox, n)
            tile_count = len(tiles)
            try:
                tile_index = int(payload.get("i") or 0)
            except (TypeError, ValueError):
                tile_index = 0
            if tile_index < 0 or tile_index >= tile_count:
                step.note = "OpenStreetMap city grid finished."
                return step
            ql = overpass_query(family, bbox=tiles[tile_index], iso="", limit=OSM_TILE_LIMIT)
            next_i = tile_index + 1
            if next_i < tile_count:
                pending_cursor = json.dumps({"i": next_i, "n": n, "bbox": list(bbox)})
                pending_exhausted = False
            else:
                pending_cursor = ""
                pending_exhausted = True
        else:
            bbox = (0.0, 0.0, 0.0, 0.0)
            ql = overpass_query(family, bbox=bbox, iso=iso)
            pending_cursor = ""
            pending_exhausted = True
        if not ql:
            step.note = "OpenStreetMap: nothing to ask for this kind of buyer."
            step.exhausted = True
            step.next_cursor = ""
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
                step.next_cursor = pending_cursor
                step.exhausted = pending_exhausted
                if city:
                    step.note = (
                        f"OpenStreetMap tile {tile_index + 1}/{tile_count} listed "
                        f"{len(cands)} mapped {family} businesses with websites in {place_label}."
                    )
                else:
                    step.note = (
                        f"OpenStreetMap listed {len(cands)} mapped {family} businesses "
                        f"with websites in {place_label}."
                    )
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
# Wikidata SPARQL (no key). Channel hunts — OSM does not map wholesalers.
# ---------------------------------------------------------------------------

_WIKIDATA_TRADE = (
    "distributor", "wholesale", "wholesaler", "importer", "import",
    "supplier", "dealer",
)
_WIKIDATA_SKIP_HOSTS = (
    "wikipedia.org", "wikimedia.org", "wikidata.org",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com",
    "linkedin.com", "crunchbase.com",
)


def _wikidata_product_tokens(product: str) -> List[str]:
    out: List[str] = []
    for word in re.findall(r"[A-Za-z]{3,}", product or ""):
        low = word.lower()
        if low not in _WIKIDATA_TRADE and low not in out:
            out.append(low)
    return out[:8]


def wikidata_sparql(product: str, iso: str, offset: int = 0, limit: int = WIKIDATA_PAGE) -> str:
    """Official website (P856) + country ISO (P297). No P31/P279* — that times out."""
    iso2 = (iso or "").strip().upper()
    tokens = _wikidata_product_tokens(product)
    if not iso2 or not tokens:
        return ""
    prod = "|".join(re.escape(t) for t in tokens)
    trade = "|".join(re.escape(t) for t in _WIKIDATA_TRADE)
    off = max(0, int(offset or 0))
    lim = max(1, min(int(limit or WIKIDATA_PAGE), 80))
    return (
        "SELECT DISTINCT ?item ?itemLabel ?website WHERE {\n"
        "  ?item wdt:P856 ?website .\n"
        "  ?item wdt:P17 ?country .\n"
        f'  ?country wdt:P297 "{iso2}" .\n'
        "  ?item rdfs:label ?itemLabel .\n"
        '  FILTER(LANG(?itemLabel) = "en")\n'
        f'  FILTER(REGEX(?itemLabel, "({prod})", "i"))\n'
        f'  FILTER(REGEX(?itemLabel, "({trade})", "i"))\n'
        "}\n"
        f"LIMIT {lim} OFFSET {off}"
    )


def parse_wikidata_bindings(payload: Dict[str, Any], country_label: str = "") -> List[BusinessCandidate]:
    bindings = ((payload or {}).get("results") or {}).get("bindings") or []
    out: List[BusinessCandidate] = []
    seen: set[str] = set()
    for row in bindings:
        website = str(((row.get("website") or {}).get("value") or "")).strip()
        name = _clean(str(((row.get("itemLabel") or {}).get("value") or "")))
        if not website or not name:
            continue
        if not website.lower().startswith("http"):
            website = f"https://{website}"
        host = _host(website)
        if not host or host in seen or _host_in(host, _WIKIDATA_SKIP_HOSTS):
            continue
        seen.add(host)
        item = str(((row.get("item") or {}).get("value") or "")).strip()
        out.append(BusinessCandidate(
            name=name,
            website=website,
            address=country_label,
            source="wikidata",
            ref=item.rsplit("/", 1)[-1] if item else "",
        ))
    return out


def _wikidata_offset(cursor: str) -> int:
    if not (cursor or "").strip():
        return 0
    try:
        data = json.loads(cursor)
        if isinstance(data, dict):
            return max(0, int(data.get("o") or 0))
    except Exception:
        pass
    try:
        return max(0, int(cursor))
    except (TypeError, ValueError):
        return 0


def wikidata_step(
    *,
    product: str,
    iso: str,
    country_label: str,
    cursor: str = "",
    client: Optional[httpx.Client] = None,
) -> SourceStep:
    """One SPARQL page of companies in this country whose English label matches the trade."""
    step = SourceStep(source="wikidata", query=f"{product} in {iso}", exhausted=True)
    ql = wikidata_sparql(product, iso, _wikidata_offset(cursor))
    if not ql:
        step.note = "Wikidata: no country on this hunt line."
        return step
    own = client is None
    client = client or httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT})
    try:
        res = client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": ql, "format": "json"},
            headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        )
        step.requests_used = 1
        if res.status_code in (429, 502, 503, 504):
            step.note = f"Wikidata answered {res.status_code}."
            return step
        if res.status_code >= 400:
            step.note = f"Wikidata answered {res.status_code}."
            return step
        cands = parse_wikidata_bindings(res.json(), country_label)
        offset = _wikidata_offset(cursor)
        if len(cands) >= WIKIDATA_PAGE:
            step.next_cursor = json.dumps({"o": offset + len(cands)})
            step.exhausted = False
        else:
            step.next_cursor = ""
            step.exhausted = True
        step.candidates = cands
        step.note = (
            f"Wikidata listed {len(cands)} companies with websites in "
            f"{country_label or iso}."
        )
        return step
    except Exception as exc:
        step.note = f"Wikidata did not answer: {exc}"
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


# ---------------------------------------------------------------------------
# Overture Maps places (free, no key)
# ---------------------------------------------------------------------------
# Overture publishes tens of millions of businesses worldwide as open parquet
# files. Every record has a category, and most have a website; many have an
# email. One query by city box + category lists the businesses of that kind in
# the city, which is what a search engine cannot do.

OVERTURE_STAC_URL = "https://stac.overturemaps.org/catalog.json"
OVERTURE_FALLBACK_RELEASE = "2026-10-21.0"
OVERTURE_PAGE = 40
OVERTURE_CACHE_TTL_SEC = 7 * 86400
OVERTURE_MIN_CONFIDENCE = 0.2
_OVERTURE_CLOSED = ("closed", "permanently_closed", "temporarily_closed")
_OVERTURE_SOCIAL_HOSTS = (
    "facebook.com", "instagram.com", "linktr.ee", "twitter.com", "x.com", "youtube.com",
    "linkedin.com", "tiktok.com", "pinterest.com", "yelp.com", "yelp.ca", "google.com",
    "goo.gl", "g.page", "wa.me", "whatsapp.com", "eventbrite.com", "meetup.com",
)

# Overture taxonomy names for the trades this product sells into.
OVERTURE_GROUPS: Dict[str, Tuple[str, ...]] = {
    "gym": (
        "gym", "fitness_trainer", "yoga_studio", "pilates_studio", "boot_camp",
        "health_and_wellness_club", "sport_or_fitness_facility", "gymnastics_center",
        "crossfit_gym", "personal_trainer",
    ),
    "combat": (
        "martial_arts_club", "boxing_gym", "boxing_class", "kickboxing_club", "muay_thai_club",
        "chinese_martial_arts_club", "fencing_club", "judo_club", "karate_club",
        "taekwondo_club", "wrestling_club", "jiu_jitsu_club",
    ),
    "rehab": (
        "physical_therapy", "chiropractic", "sports_medicine", "rehabilitation_center",
        "occupational_therapy", "orthopedics", "massage_therapy", "medical_supply_store",
        "b2b_hospital_equipment_and_supplies", "orthopedic_shoe_store",
    ),
    "retail": (
        "sporting_goods_store", "fitness_exercise_store", "sportswear_store", "outdoor_store",
        "hunting_and_fishing_store", "uniform_store",
    ),
    "club": (
        "sports_school", "sport_or_recreation_club", "amateur_sport_team", "school_sport_team",
        "sport_league", "amateur_sport_league", "adventure_sports_center",
    ),
}
_OVERTURE_GENERIC_WORDS = {
    "store", "stores", "shop", "shops", "service", "services", "supplier", "suppliers",
    "supply", "supplies", "wholesaler", "wholesalers", "distributor", "distributors",
    "retailer", "retailers", "equipment", "center", "centers", "centre", "centres",
    "clinic", "clinics", "studio", "studios", "business", "businesses", "company",
    "companies", "and", "the", "for", "stockist", "stockists", "importer", "importers",
}

_overture_release_cache: Dict[str, Any] = {}
_overture_mem_cache: Dict[str, List[Dict[str, Any]]] = {}


def overture_release() -> str:
    """Latest Overture release (older ones are removed from the bucket)."""
    cached = _overture_release_cache.get("v")
    if cached and time.time() - float(_overture_release_cache.get("t") or 0) < 6 * 3600:
        return str(cached)
    release = OVERTURE_FALLBACK_RELEASE
    try:
        res = httpx.get(OVERTURE_STAC_URL, timeout=10.0, headers={"User-Agent": USER_AGENT})
        if res.status_code == 200:
            release = str(res.json().get("latest") or release)
    except Exception as exc:
        log.warning("Overture release lookup failed: %s", exc)
    _overture_release_cache.update({"v": release, "t": time.time()})
    return release


def _overture_all_categories() -> List[str]:
    from pathlib import Path

    path = Path(__file__).with_name("data") / "overture_categories.txt"
    try:
        return [ln.strip() for ln in path.read_text(encoding="utf8").splitlines() if ln.strip()]
    except Exception:
        return []


def overture_categories_for(families: List[str], buyer_types: List[str], limit: int = 40) -> List[str]:
    """Overture category names for the trades named by the hunt."""
    out: List[str] = []
    for fam in families or []:
        for cat in OVERTURE_GROUPS.get(fam, ()):
            if cat not in out:
                out.append(cat)
    if out:
        return out[:limit]
    # Not a sports seller: match the buyer-type words to category names.
    words: List[str] = []
    for text in buyer_types or []:
        for w in re.findall(r"[a-z]{4,}", text.lower()):
            w = w[:-1] if w.endswith("s") and len(w) > 4 else w
            if w not in _OVERTURE_GENERIC_WORDS and w not in words:
                words.append(w)
    for cat in _overture_all_categories():
        parts = [p[:-1] if p.endswith("s") and len(p) > 4 else p for p in cat.split("_")]
        if any(w in parts for w in words) and cat not in out:
            out.append(cat)
        if len(out) >= limit:
            break
    return out


def _overture_cache_path(release: str, bbox: Tuple[float, float, float, float], categories: List[str]):
    import hashlib
    import tempfile
    from pathlib import Path

    key = hashlib.md5(
        ("v2" + release + json.dumps([round(v, 4) for v in bbox]) + ",".join(sorted(categories))).encode()
    ).hexdigest()[:16]
    folder = Path(tempfile.gettempdir()) / "nexivo_overture"
    folder.mkdir(parents=True, exist_ok=True)
    return key, folder / f"{key}.json"


def _overture_query(release: str, bbox: Tuple[float, float, float, float], categories: List[str]) -> List[Dict[str, Any]]:
    import duckdb

    south, west, north, east = bbox
    cats = ",".join("'" + c.replace("'", "") + "'" for c in categories)
    path = f"s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"
    con = duckdb.connect()
    try:
        con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2'; SET threads=4;")
        con.execute("SET memory_limit='600MB';")
        closed = ",".join(f"'{c}'" for c in _OVERTURE_CLOSED)
        base = f"""
            SELECT names.primary AS name, {{CAT}} AS cat, websites[1] AS website, emails[1] AS email,
                   phones[1] AS phone, addresses[1].freeform AS street, addresses[1].locality AS city,
                   addresses[1].region AS region, confidence, id
            FROM read_parquet('{path}', hive_partitioning=1)
            WHERE bbox.xmin BETWEEN {west} AND {east} AND bbox.ymin BETWEEN {south} AND {north}
              AND {{CAT}} IN ({cats})
              AND websites[1] IS NOT NULL
              AND brand.names.primary IS NULL
              AND coalesce(operating_status, 'open') NOT IN ({closed})
              AND coalesce(confidence, 0) >= {OVERTURE_MIN_CONFIDENCE}
        """
        try:
            return _overture_rows(con.execute(base.replace("{CAT}", "taxonomy.primary")).fetchall())
        except duckdb.BinderException:
            # Older releases name the field categories.primary.
            return _overture_rows(con.execute(base.replace("{CAT}", "categories.primary")).fetchall())
    finally:
        con.close()


def _overture_rows(rows: List[tuple]) -> List[Dict[str, Any]]:
    return [
        {
            "name": r[0] or "", "cat": r[1] or "", "website": r[2] or "", "email": r[3] or "",
            "phone": r[4] or "", "street": r[5] or "", "city": r[6] or "", "region": r[7] or "",
            "confidence": float(r[8] or 0), "id": r[9] or "",
        }
        for r in rows
    ]


_TWO_PART_TLDS = {"co.uk", "org.uk", "com.au", "co.nz", "co.za", "com.br", "com.mx", "co.in", "com.sg", "com.my", "com.tr", "ae.org"}


def _registrable(host: str) -> str:
    """locations.sportinglife.ca -> sportinglife.ca, so one chain counts once."""
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _TWO_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def overture_candidates(
    bbox: Tuple[float, float, float, float],
    categories: List[str],
    country_label: str = "",
) -> List[BusinessCandidate]:
    """Every listed business of these kinds in the box, best first. Cached on disk."""
    release = overture_release()
    key, cache_file = _overture_cache_path(release, bbox, categories)
    rows = _overture_mem_cache.get(key)
    if rows is None and cache_file.exists() and time.time() - cache_file.stat().st_mtime < OVERTURE_CACHE_TTL_SEC:
        try:
            rows = json.loads(cache_file.read_text(encoding="utf8"))
        except Exception:
            rows = None
    if rows is None:
        rows = _overture_query(release, bbox, categories)
        try:
            cache_file.write_text(json.dumps(rows), encoding="utf8")
        except Exception as exc:
            log.warning("Overture cache write failed: %s", exc)
    _overture_mem_cache[key] = rows

    # One row per website. Rows with an email first, then the surest records.
    rows = sorted(rows, key=lambda r: (0 if r.get("email") else 1, -float(r.get("confidence") or 0)))
    out: List[BusinessCandidate] = []
    seen: set[str] = set()
    for r in rows:
        website = str(r.get("website") or "").strip()
        host = _host(website)
        if not host or any(host == h or host.endswith("." + h) for h in _OVERTURE_SOCIAL_HOSTS):
            continue
        company = _registrable(host)
        if company in seen:
            continue
        seen.add(company)
        parts = [r.get("street"), r.get("city"), r.get("region"), country_label]
        out.append(BusinessCandidate(
            name=_clean(str(r.get("name") or "")),
            website=website,
            address=", ".join(str(p) for p in parts if p),
            source="overture",
            ref=str(r.get("id") or ""),
            email=str(r.get("email") or "").strip(),
        ))
    return out


def overture_step(
    *,
    city: str,
    iso: str,
    country_label: str,
    categories: List[str],
    cursor: str = "",
    client: Optional[httpx.Client] = None,
) -> SourceStep:
    """One page of businesses of these kinds in one city."""
    step = SourceStep(source="overture", query=f"{', '.join(categories[:3])} in {city or iso}", exhausted=True)
    if not categories:
        step.note = "Overture Maps: no matching business categories for this hunt."
        return step
    payload = _osm_cursor_payload(cursor)
    bbox_raw = payload.get("bbox")
    bbox = (0.0, 0.0, 0.0, 0.0)
    if isinstance(bbox_raw, list) and len(bbox_raw) == 4:
        try:
            bbox = tuple(float(v) for v in bbox_raw)  # type: ignore[assignment]
        except (TypeError, ValueError):
            bbox = (0.0, 0.0, 0.0, 0.0)
    if not any(bbox):
        bbox = geocode_bbox(city, iso, client=client)
        if not any(bbox):
            step.note = f"Overture Maps could not place “{city}” on the map."
            return step
        s, w, n, e = bbox
        pad_lat, pad_lon = (n - s) * 0.1, (e - w) * 0.1
        bbox = (s - pad_lat, w - pad_lon, n + pad_lat, e + pad_lon)
    try:
        offset = max(0, int(payload.get("o") or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        cands = overture_candidates(bbox, categories, country_label)
    except Exception as exc:
        step.note = f"Overture Maps did not answer: {exc}"
        return step
    page = cands[offset:offset + OVERTURE_PAGE]
    new_offset = offset + len(page)
    step.candidates = page
    step.exhausted = new_offset >= len(cands)
    step.next_cursor = "" if step.exhausted else json.dumps({"o": new_offset, "bbox": list(bbox)})
    step.note = (
        f"Overture Maps lists {len(cands)} businesses with websites in {city or iso}; "
        f"reading {offset + 1}–{new_offset}."
    )
    return step
