"""Extract and match geographic places from Discover prompts / ICP."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# 2-letter codes that are also English words / common tokens — never match as bare "in"/"or"/…
# Use postal-style context only: ", IN" or "IN 46201".
AMBIGUOUS_STATE_ABBREVS = frozenset({
    "in", "or", "me", "hi", "ok", "id", "la", "ma", "md", "mt", "ne", "pa",
    "co", "de", "al", "ar", "ga", "ia", "ms", "mo", "wa", "va", "oh", "mi",
    "nh", "ri", "ut", "wy", "ak", "as", "ca", "fl", "ny", "tx", "nc", "sc",
    "nd", "sd", "ct", "vt", "ky", "tn", "ks", "mn", "wi", "il", "az", "nm",
    "nv", "nj", "wv", "dc",
})

# Full name → aliases (abbrev + major cities) for US states commonly used in B2B hunts.
US_STATE_ALIASES: dict[str, tuple[str, ...]] = {
    "alabama": ("al",),
    "alaska": ("ak",),
    "arizona": ("az", "phoenix", "tucson"),
    "arkansas": ("ar",),
    "california": ("ca", "los angeles", "san francisco", "san diego", "oakland"),
    "colorado": ("co", "denver"),
    "connecticut": ("ct",),
    "delaware": ("de",),
    "florida": ("fl", "miami", "orlando", "tampa"),
    "georgia": ("ga", "atlanta"),
    "hawaii": ("hi", "honolulu"),
    "idaho": ("id",),
    "illinois": ("il", "chicago"),
    "indiana": ("in", "indianapolis"),
    "iowa": ("ia",),
    "kansas": ("ks",),
    "kentucky": ("ky", "louisville"),
    "louisiana": ("la", "new orleans"),
    "maine": ("me",),
    "maryland": ("md", "baltimore"),
    "massachusetts": ("ma", "boston"),
    "michigan": ("mi", "detroit"),
    "minnesota": ("mn", "minneapolis"),
    "mississippi": ("ms",),
    "missouri": ("mo", "st louis", "kansas city"),
    "montana": ("mt",),
    "nebraska": ("ne", "omaha"),
    "nevada": ("nv", "las vegas", "reno", "henderson"),
    "new hampshire": ("nh",),
    "new jersey": ("nj",),
    "new mexico": ("nm", "albuquerque"),
    "new york": ("ny", "nyc", "brooklyn", "buffalo"),
    "north carolina": ("nc", "charlotte", "raleigh"),
    "north dakota": ("nd",),
    "ohio": ("oh", "columbus", "cleveland", "cincinnati"),
    "oklahoma": ("ok",),
    "oregon": ("or", "portland"),
    "pennsylvania": ("pa", "philadelphia", "pittsburgh"),
    "rhode island": ("ri",),
    "south carolina": ("sc", "charleston"),
    "south dakota": ("sd",),
    "tennessee": ("tn", "nashville", "memphis"),
    "texas": ("tx", "houston", "dallas", "austin", "san antonio"),
    "utah": ("ut", "salt lake city"),
    "vermont": ("vt",),
    "virginia": ("va", "richmond"),
    "washington": ("wa", "seattle", "spokane"),
    "west virginia": ("wv",),
    "wisconsin": ("wi", "milwaukee"),
    "wyoming": ("wy",),
}

COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "united states": ("usa", "u.s.", "u.s.a.", "united states", "america"),
    "united kingdom": ("uk", "britain", "england", "scotland", "wales", "united kingdom"),
    "united arab emirates": ("uae", "dubai", "abu dhabi", "sharjah"),
    "saudi arabia": ("saudi", "ksa", "riyadh", "jeddah", "dammam"),
    "canada": ("canada", "toronto", "vancouver", "montreal"),
    "germany": ("germany", "deutschland", "berlin", "munich", "hamburg"),
    "france": ("france", "paris", "lyon"),
    "netherlands": ("netherlands", "holland", "amsterdam", "rotterdam"),
    "australia": ("australia", "sydney", "melbourne"),
    "india": ("india", "mumbai", "delhi", "bangalore", "chennai"),
    "pakistan": ("pakistan", "karachi", "lahore", "islamabad"),
    "qatar": ("qatar", "doha"),
    "singapore": ("singapore",),
    "malaysia": ("malaysia", "kuala lumpur"),
    "turkey": ("turkey", "istanbul", "ankara"),
    "south africa": ("south africa", "johannesburg", "cape town"),
    "spain": ("spain", "madrid", "barcelona"),
    "italy": ("italy", "milan", "rome"),
    "mexico": ("mexico", "guadalajara", "monterrey"),
    "brazil": ("brazil", "são paulo", "sao paulo", "rio de janeiro"),
}

# E.164 country calling codes → canonical country label (longest prefix wins).
# +1 is North America — treated as United States unless Canada evidence is stronger.
PHONE_DIAL_TO_COUNTRY: dict[str, str] = {
    "971": "United Arab Emirates",
    "966": "Saudi Arabia",
    "974": "Qatar",
    "92": "Pakistan",
    "91": "India",
    "90": "Turkey",
    "86": "China",
    "81": "Japan",
    "82": "South Korea",
    "65": "Singapore",
    "60": "Malaysia",
    "61": "Australia",
    "64": "New Zealand",
    "55": "Brazil",
    "52": "Mexico",
    "49": "Germany",
    "48": "Poland",
    "47": "Norway",
    "46": "Sweden",
    "45": "Denmark",
    "44": "United Kingdom",
    "43": "Austria",
    "41": "Switzerland",
    "40": "Romania",
    "39": "Italy",
    "34": "Spain",
    "33": "France",
    "32": "Belgium",
    "31": "Netherlands",
    "27": "South Africa",
    "20": "Egypt",
    "7": "Russia",
    "1": "United States",
}


def _word_hit(blob: str, term: str) -> bool:
    term = (term or "").strip().lower()
    if not term:
        return False
    if " " in term or len(term) > 3:
        return term in blob
    # short abbrev like nv, ca — word boundary (ambiguous codes use _abbrev_hit)
    return bool(re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", blob))


def _abbrev_hit(blob: str, abbrev: str) -> bool:
    """
    Match US state postal codes without treating English words as places.
    'importers in New Jersey' must NOT match Indiana via the preposition 'in'.
    """
    a = (abbrev or "").strip().lower()
    if not a or len(a) != 2:
        return False
    low = (blob or "").lower()
    # Postal / list style: ", nj" / ", nj " / "nj 07001"
    if re.search(rf",\s*{re.escape(a)}\b", low):
        return True
    if re.search(rf"\b{re.escape(a)}\s+\d{{5}}\b", low):
        return True
    if a in AMBIGUOUS_STATE_ABBREVS:
        # Require explicit "in XX" / "near XX" where XX is the code — but NOT when
        # the code itself is the English word forming the preposition (Indiana "in").
        if a == "in":
            # Only ", in" / "in 46xxx" already covered; bare "in" is never enough
            return False
        # "in or" / "near or" still too noisy for Oregon — require comma or zip only
        if a in ("or", "me", "hi", "ok", "id", "la", "ma", "md", "mt", "ne", "pa", "co", "de"):
            return False
        return bool(re.search(rf"(?:in|near)\s+{re.escape(a)}\b", low))
    return bool(re.search(rf"(?:in|near|,|\s){re.escape(a)}\b", low))


def place_aliases(place: str) -> List[str]:
    p = (place or "").strip().lower()
    if not p:
        return []
    out = [p]
    if p in US_STATE_ALIASES:
        out.extend(US_STATE_ALIASES[p])
    elif p in COUNTRY_ALIASES:
        out.extend(COUNTRY_ALIASES[p])
    else:
        # reverse lookup city → state
        for state, aliases in US_STATE_ALIASES.items():
            if p == state or p in aliases:
                out.append(state)
                out.extend(aliases)
                break
    # unique
    seen = set()
    uniq = []
    for a in out:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq


def places_mentioned(blob: str, places: List[str]) -> Optional[bool]:
    """True if any target place (or alias) appears; False if none; None if no places."""
    if not places:
        return None
    low = (blob or "").lower()
    for place in places:
        for alias in place_aliases(place):
            a = (alias or "").strip().lower()
            if not a:
                continue
            if len(a) == 2 and a.isalpha():
                if _abbrev_hit(low, a):
                    return True
                continue
            if _word_hit(low, a):
                return True
    return False


def location_conflicts_with_targets(location: str, places: List[str]) -> bool:
    """
    True when an address/location string names a different US state or country than the hunt.
    'Edison, NJ' conflicts with Massachusetts; 'ships to Boston' alone is not a location.
    """
    loc = (location or "").strip()
    if not loc or not places:
        return False
    if places_mentioned(loc, places) is True:
        return False
    low = loc.lower()
    target_keys = {p.lower() for p in places}
    for p in places:
        target_keys.update(a.lower() for a in place_aliases(p))

    for state, aliases in US_STATE_ALIASES.items():
        if state in target_keys:
            continue
        if _word_hit(low, state):
            return True
        abbrev = aliases[0] if aliases else ""
        if abbrev and _abbrev_hit(low, abbrev):
            return True
        for city in aliases[1:]:
            if _word_hit(low, city):
                return True

    # Country-level conflict (must match when hunt named a country)
    for country, aliases in COUNTRY_ALIASES.items():
        if country in target_keys or any(a in target_keys for a in aliases):
            continue
        if _word_hit(low, country):
            return True
        for a in aliases:
            if len(a) > 2 and _word_hit(low, a):
                return True
    return False


def countries_from_phone_text(text: str) -> List[str]:
    """Infer countries from +dial / 00-dial phone numbers in page text."""
    blob = text or ""
    if not blob.strip():
        return []
    found: List[str] = []
    seen = set()
    # +971 50… / +1-702-… / 00 44 …
    for match in re.finditer(r"(?:\+|00)\s*(\d{1,3})[\s\-.]?\d", blob):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if not digits:
            continue
        country = None
        for length in (3, 2, 1):
            prefix = digits[:length]
            if prefix in PHONE_DIAL_TO_COUNTRY:
                country = PHONE_DIAL_TO_COUNTRY[prefix]
                break
        if not country:
            continue
        key = country.lower()
        if key in seen:
            continue
        # +1 Canada vs US: if "canada" appears near the number, prefer Canada
        if key == "united states":
            window = blob[max(0, match.start() - 40) : match.end() + 40].lower()
            if "canada" in window or "toronto" in window or "vancouver" in window:
                country = "Canada"
                key = "canada"
                if key in seen:
                    continue
        seen.add(key)
        found.append(country)
    return found[:4]


def social_location_hints(text: str) -> str:
    """
    Pull location cues near Facebook / Instagram mentions and common 'based in' lines.
    Does not invent places — only returns text windows that may contain geo for format_location_display.
    """
    blob = text or ""
    if not blob.strip():
        return ""
    chunks: List[str] = []
    low = blob.lower()
    for needle in (
        "facebook.com",
        "fb.com",
        "instagram.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "based in",
        "located in",
        "headquartered in",
        "hq in",
        "our office",
        "visit us",
        "find us",
        "contact us",
    ):
        start = 0
        while True:
            idx = low.find(needle, start)
            if idx < 0:
                break
            window = blob[max(0, idx - 80) : idx + len(needle) + 120]
            chunks.append(window)
            start = idx + len(needle)
            if len(chunks) >= 8:
                break
        if len(chunks) >= 8:
            break
    return "\n".join(chunks)


def enrich_geo_blob(
    *,
    site_text: str = "",
    title: str = "",
    snippet: str = "",
    phones: Optional[List[str]] = None,
) -> str:
    """Combine page copy, social windows, and phone dial-code countries for geo checks."""
    phone_blob = " ".join(p for p in (phones or []) if p)
    dial_countries = countries_from_phone_text(f"{site_text}\n{phone_blob}")
    social = social_location_hints(site_text)
    return "\n".join(
        [
            title or "",
            snippet or "",
            site_text or "",
            social,
            phone_blob,
            " ".join(dial_countries),
        ]
    )


def extract_places_from_prompt(prompt: str) -> Tuple[List[str], bool]:
    """
    Pull state/city/country from Discover text.
    Returns (places, strict) — strict=True when user named a place that must match.
    """
    text = (prompt or "").strip()
    if not text:
        return [], False
    low = text.lower()
    found: List[str] = []
    strict = False

    # Explicit "in <place>" / "near <place>" → always treat as strict hunt geo
    if re.search(r"\b(?:in|near|around|within)\s+[a-z]", low):
        strict = True

    # Multi-word states first
    for state in sorted(US_STATE_ALIASES.keys(), key=len, reverse=True):
        if _word_hit(low, state):
            found.append(" ".join(w.capitalize() for w in state.split()))
            strict = True
            continue
        abbrev = US_STATE_ALIASES[state][0] if US_STATE_ALIASES[state] else ""
        if abbrev and _abbrev_hit(low, abbrev):
            found.append(" ".join(w.capitalize() for w in state.split()))
            strict = True

    for state, aliases in US_STATE_ALIASES.items():
        state_label = " ".join(w.capitalize() for w in state.split())
        for city in aliases[1:]:
            if _word_hit(low, city):
                if state_label not in found:
                    found.append(state_label)
                strict = True

    for country, aliases in COUNTRY_ALIASES.items():
        label = " ".join(w.capitalize() for w in country.split())
        if any(_word_hit(low, a) for a in (country, *aliases)):
            if label not in found and country not in {p.lower() for p in found}:
                if country == "united states" and any(
                    p.lower() in US_STATE_ALIASES for p in found
                ):
                    # State already set — country is redundant, keep strict from state
                    continue
                found.append(label)
                strict = True  # country hunts must match country

    seen = set()
    out = []
    for p in found:
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out[:4], strict


# Canonical buyer role → surface forms in Discover prompts / site copy
BUYER_ROLE_FORMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("importers", ("importers", "importer", "importing", "import company")),
    ("distributors", ("distributors", "distributor", "distribution")),
    ("wholesalers", ("wholesalers", "wholesaler", "wholesale")),
    ("retailers", ("retailers", "retailer", "retail chain", "retail store")),
    ("brands", ("brands", "brand", "private label brand", "clothing brand")),
    ("gyms", ("gyms", "gym", "fitness club", "fitness center")),
    ("clinics", ("clinics", "clinic", "hospitals", "hospital")),
    ("hotels", ("hotels", "hotel", "hospitality")),
    ("restaurants", ("restaurants", "restaurant", "cafes", "cafe")),
    ("salons", ("salons", "salon", "spas", "spa")),
)

_PROMPT_FILLER = frozenset({
    "find", "looking", "search", "hunt", "need", "needs", "want", "wants",
    "get", "for", "the", "a", "an", "and", "or", "of", "to", "with", "that",
    "who", "may", "might", "could", "please", "help", "me", "us", "our",
    "in", "from", "within", "across", "into", "onto",
    "companies", "company", "businesses", "business", "firms", "firm",
    "prospects", "leads", "buyers", "buyer", "customers", "customer",
    "near", "around", "based", "located", "area", "region", "state",
})


def extract_offer_terms_from_prompt(prompt: str) -> List[str]:
    """
    Product / offer nouns left after stripping buyer roles and places.
    Also pulls product stems from multi-line hunt descriptions
    ('weightlifting straps distributors' → 'weightlifting straps').
    """
    text = (prompt or "").strip()
    if not text:
        return []

    phrases: List[str] = []
    seen = set()

    def _add(phrase: str) -> None:
        p = re.sub(r"\s+", " ", (phrase or "").strip().lower())
        if not p or p in seen or len(p) < 3:
            return
        seen.add(p)
        phrases.append(p)

    # Multi-line product×buyer angles (client hunt description)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("priority hunt"):
            continue
        if line.lower().startswith("target location:") or line.lower().startswith("context:"):
            continue
        # Drop emoji / short section headers like "Fitness / Bodybuilding"
        cleaned = re.sub(r"^[^\w]+", "", line).strip()
        if "/" in cleaned and len(cleaned.split()) <= 4 and not re.search(
            r"\b(distributor|wholesaler|importer|retailer|buyer)s?\b", cleaned, re.I
        ):
            continue
        m = re.match(
            r"^(.+?)\s+(distributors?|wholesalers?|importers?|retailers?|buyers?|dealers?)\s*$",
            cleaned,
            re.I,
        )
        if m:
            _add(m.group(1))
            continue
        if re.search(r"\b(distributor|wholesaler|importer|retailer)s?\b", cleaned, re.I):
            # "X distributors in Texas" style
            stem = re.sub(
                r"\b(distributors?|wholesalers?|importers?|retailers?|buyers?|dealers?)\b.*$",
                "",
                cleaned,
                flags=re.I,
            ).strip()
            stem = re.sub(r"\b(in|near|around|within)\s+.+$", "", stem, flags=re.I).strip()
            if stem:
                for part in re.split(r"\s+and\s+", stem, flags=re.I):
                    _add(part.strip())

    # When multi-line hunt description already gave product stems, stop — avoid
    # turning "Target location / Priority hunt lines" into fake categories.
    if phrases:
        return phrases[:10]

    low = text.lower()
    low = re.sub(r"target location\s*:", " ", low)
    low = re.sub(r"priority hunt lines?[^\n]*", " ", low)
    low = re.sub(r"context\s*:", " ", low)

    # Drop known places (longest first)
    for state in sorted(US_STATE_ALIASES.keys(), key=len, reverse=True):
        low = re.sub(rf"\b{re.escape(state)}\b", " ", low)
        for alias in US_STATE_ALIASES[state]:
            if len(alias) <= 2:
                continue
            low = re.sub(rf"\b{re.escape(alias)}\b", " ", low)
    for country, aliases in COUNTRY_ALIASES.items():
        low = re.sub(rf"\b{re.escape(country)}\b", " ", low)
        for a in aliases:
            if len(a) > 2:
                low = re.sub(rf"\b{re.escape(a)}\b", " ", low)

    for _label, forms in BUYER_ROLE_FORMS:
        for f in sorted(forms, key=len, reverse=True):
            low = re.sub(rf"\b{re.escape(f)}\b", " ", low)

    # Keep multi-product prompts as separate categories ("X and Y")
    chunks = re.split(r"\s+and\s+|," , low)
    for chunk in chunks:
        tokens = [
            t for t in re.findall(r"[a-z0-9]+(?:'[a-z]+)?", chunk)
            if t not in _PROMPT_FILLER and len(t) > 1
        ]
        if not tokens:
            continue
        phrase = " ".join(tokens[:4]).strip()
        _add(phrase)
    return phrases[:8]


def extract_hunt_detail_lines(prompt: str) -> List[str]:
    """Concrete one-line hunt angles from a multi-line description."""
    out: List[str] = []
    seen = set()
    for raw in (prompt or "").splitlines():
        line = re.sub(r"^[^\w]+", "", raw.strip()).strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("priority hunt"):
            continue
        if low.startswith("target location:") or low.startswith("context:"):
            continue
        # Skip short section titles
        if len(line.split()) <= 3 and "/" in line:
            continue
        if not re.search(
            r"\b(distributor|wholesaler|importer|retailer|buyer|dealer|gym|clinic|brand)s?\b",
            line,
            re.I,
        ):
            # Still keep product-ish lines with 2+ words
            if len(line.split()) < 2:
                continue
            # Skip meta / instruction lines without a buyer role
            if re.search(r"\b(location|priority|search each|exactly)\b", low):
                continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= 24:
            break
    return out


def extract_buyers_from_prompt(prompt: str) -> List[str]:
    """Pull buyer roles the user named (e.g. importers) so search prioritizes them."""
    low = (prompt or "").lower()
    if not low:
        return []
    found: List[str] = []
    for label, forms in BUYER_ROLE_FORMS:
        if any(_word_hit(low, f) or f in low for f in forms):
            # Prefer exact word hits over substring for short forms like "brand"
            if any(re.search(rf"\b{re.escape(f)}\b", low) for f in forms):
                found.append(label)
    return found[:4]


def format_location_display(text: str, prefer_places: Optional[List[str]] = None) -> str:
    """
    Build a short human location string from SERP/site text.
    Prefers city + state when possible; never invents a place not present in text.
    """
    blob = text or ""
    if not blob.strip():
        return ""
    low = blob.lower()
    prefer = [p.lower() for p in (prefer_places or []) if p]

    # City + state pairs first (Las Vegas, Nevada)
    city_hits: List[Tuple[str, str]] = []
    for state, aliases in US_STATE_ALIASES.items():
        state_label = " ".join(w.capitalize() for w in state.split())
        for city in aliases[1:]:
            if _word_hit(low, city):
                city_label = " ".join(w.capitalize() for w in city.split())
                city_hits.append((city_label, state_label))

    if city_hits:
        # Prefer cities in requested states
        if prefer:
            for city, state in city_hits:
                if any(p in state.lower() or state.lower() in p for p in prefer):
                    return f"{city}, {state}"[:80]
        city, state = city_hits[0]
        return f"{city}, {state}"[:80]

    # Named US state
    for state in sorted(US_STATE_ALIASES.keys(), key=len, reverse=True):
        state_label = " ".join(w.capitalize() for w in state.split())
        if _word_hit(low, state):
            if prefer and not any(p in state or state in p for p in prefer):
                # Still return if it's the only geo we found
                pass
            return state_label[:80]
        abbrev = US_STATE_ALIASES[state][0]
        if abbrev and _abbrev_hit(low, abbrev):
            return state_label[:80]

    # Countries / major hubs from COUNTRY_ALIASES
    for country, aliases in COUNTRY_ALIASES.items():
        label = " ".join(w.capitalize() for w in country.split())
        for a in (country, *aliases):
            if _word_hit(low, a):
                # Prefer city alias when that's what matched (Dubai not UAE)
                if a != country and " " not in a and len(a) > 3:
                    return a.title()[:80]
                return label[:80]

    # Common non-US hubs still useful in B2B
    for hub in (
        "Dubai", "Abu Dhabi", "Riyadh", "Jeddah", "Doha", "Singapore",
        "London", "Berlin", "Toronto", "Sydney", "Karachi", "Lahore",
    ):
        if _word_hit(low, hub.lower()):
            return hub[:80]

    return ""


def split_city_country(location: str) -> Tuple[str, str]:
    """
    Split a display location into (city, country) for Sheets columns.
    Uses commas when present; maps US states to United States; never invents.
    """
    text = (location or "").strip()
    if not text:
        return "", ""

    low = text.lower()
    parts = [p.strip() for p in re.split(r"\s*,\s*", text) if p.strip()]

    # Known US city + state → city, United States
    for state, aliases in US_STATE_ALIASES.items():
        state_label = " ".join(w.capitalize() for w in state.split())
        abbrev = aliases[0] if aliases else ""
        for city in aliases[1:]:
            city_label = " ".join(w.capitalize() for w in city.split())
            if _word_hit(low, city) and (
                _word_hit(low, state) or (abbrev and _abbrev_hit(low, abbrev))
            ):
                return city_label[:80], "United States"
        # "Boston, Massachusetts" / "Boston, MA" style without city in alias list
        if len(parts) >= 2:
            tail = parts[-1].lower()
            if tail == state or (abbrev and tail == abbrev):
                city = ", ".join(parts[:-1]).strip()
                return city[:80], "United States"
        if len(parts) == 1 and (_word_hit(low, state) or (abbrev and _abbrev_hit(low, abbrev))):
            # State-only → no city
            if low.strip() == state or (abbrev and low.strip() == abbrev):
                return "", "United States"

    # Country alias match — city may be a known hub alias
    country_shorts = frozenset({
        "uae", "uk", "usa", "u.s.", "u.s.a.", "ksa", "america", "britain",
        "holland", "deutschland",
    })
    for country, aliases in COUNTRY_ALIASES.items():
        country_label = " ".join(w.capitalize() for w in country.split())
        hub_aliases = [
            a for a in aliases
            if a != country and a not in country_shorts and " " not in a and len(a) > 2
        ]
        for hub in hub_aliases:
            if not _word_hit(low, hub):
                continue
            # Lone hub ("Dubai", "Toronto") → city + country
            if len(parts) == 1:
                return hub.title()[:80], country_label
            if (
                _word_hit(low, country)
                or any(_word_hit(low, a) for a in aliases if a in country_shorts or a == country)
                or len(parts) >= 2
            ):
                return hub.title()[:80], country_label
        if any(_word_hit(low, a) for a in (country, *aliases)):
            if len(parts) >= 2:
                tail = parts[-1].lower()
                if (
                    tail == country
                    or tail in aliases
                    or country in tail
                    or any(tail == a for a in aliases)
                ):
                    city = ", ".join(parts[:-1]).strip()
                    return city[:80], country_label
            # Country-only (no hub city in the string)
            if not any(_word_hit(low, h) for h in hub_aliases):
                return "", country_label

    # Generic "City, Region/Country"
    if len(parts) >= 2:
        return ", ".join(parts[:-1])[:80], parts[-1][:80]

    # Single token — unknown; leave as city, blank country
    return text[:80], ""
