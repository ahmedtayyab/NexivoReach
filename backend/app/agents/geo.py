"""Extract and match geographic places from Discover prompts / ICP."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

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
        if line.lower().startswith("buyer types:"):
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
            continue
        # Product-only hunt lines (roles selected separately in Buyer types)
        if (
            len(cleaned.split()) >= 2
            and not re.search(r"\b(location|priority|search each|exactly|buyer types)\b", cleaned, re.I)
        ):
            _add(cleaned)
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
        if low.startswith("buyer types:"):
            continue
        # Skip short section titles
        if len(line.split()) <= 3 and "/" in line:
            continue
        if not re.search(
            r"\b(distributor|wholesaler|importer|retailer|buyer|dealer|gym|clinic|brand)s?\b",
            line,
            re.I,
        ):
            # Still keep product-ish lines with 2+ words (roles come from Buyer types chips)
            if len(line.split()) < 2:
                continue
            # Skip meta / instruction lines without a buyer role
            if re.search(r"\b(location|priority|search each|exactly|buyer types)\b", low):
                continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= 24:
            break
    return out


def line_has_buyer_role(line: str) -> bool:
    return bool(
        re.search(
            r"\b(distributors?|wholesalers?|importers?|retailers?|buyers?|dealers?|"
            r"gyms?|clinics?|brands?|hotels?|restaurants?|salons?)\b",
            line or "",
            re.I,
        )
    )


def normalize_buyer_query_term(buyer: str) -> str:
    """Map 'Regional distributors' → 'distributors' for SERP queries."""
    b = re.sub(r"\s+", " ", (buyer or "").strip().lower())
    if not b:
        return ""
    for label, forms in BUYER_ROLE_FORMS:
        if b == label or any(re.search(rf"\b{re.escape(f)}\b", b) for f in forms):
            return label
    b = re.sub(r"\b(regional|national|local|global|online|b2b)\b", "", b).strip()
    b = re.sub(r"\s+", " ", b).strip()
    return b


def expand_product_buyer_lines(detail_lines: List[str], buyers: List[str]) -> List[str]:
    """
    Product-only lines × selected buyer types → concrete SERP angles.
    Round-robins across products so straps don't dominate the first N queries.
    Lines that already include a buyer role are kept as-is.
    """
    roles = []
    seen_roles = set()
    for raw in buyers or []:
        form = normalize_buyer_query_term(raw)
        if not form:
            continue
        key = form.rstrip("s")
        if key in seen_roles:
            continue
        seen_roles.add(key)
        roles.append(form)
    if not roles:
        roles = ["distributors"]

    product_only: List[str] = []
    full_lines: List[str] = []
    seen_products = set()
    for line in detail_lines or []:
        line = re.sub(r"\s+", " ", (line or "").strip())
        if not line:
            continue
        if line_has_buyer_role(line):
            key = line.lower()
            if key not in seen_products:
                seen_products.add(key)
                full_lines.append(line)
            continue
        key = line.lower()
        if key in seen_products:
            continue
        seen_products.add(key)
        product_only.append(line)

    # Per-product role lists, then zip so query order is:
    # p1+role1, p2+role1, p3+role1, … then p1+role2, …
    # Actually prefer product fairness first: p1r1, p2r1, p3r1… then p1r2…
    out: List[str] = []
    seen = set()

    def _add(stem: str) -> None:
        key = stem.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(stem)

    for role in roles:
        for product in product_only:
            _add(f"{product} {role}")
            if len(out) >= 48:
                return out
    for line in full_lines:
        _add(line)
        if len(out) >= 48:
            break
    return out


# Ambiguous product headwords — alone they match truck straps, seat belts, etc.
AMBIGUOUS_PRODUCT_HEADS = frozenset({
    "straps", "strap", "belts", "belt", "wraps", "wrap", "sleeves", "sleeve",
    "hooks", "hook", "bands", "band", "pads", "pad", "bags", "bag", "gloves", "glove",
})

# Fitness / combat context that validates an ambiguous headword on a page
PRODUCT_CONTEXT_WORDS = frozenset({
    "weight", "weightlifting", "lifting", "gym", "fitness", "workout", "training",
    "powerlifting", "bodybuilding", "crossfit", "martial", "karate", "bjj", "jiu",
    "knee", "wrist", "ankle", "deadlift", "barbell", "dumbbell", "strength",
})

# SERP negatives when hunting products whose headword collides with other industries
PRODUCT_HEAD_NEGATIVES: dict[str, tuple[str, ...]] = {
    "straps": ("-truck", "-cargo", "-ratchet"),
    "strap": ("-truck", "-cargo", "-ratchet"),
    "belts": ("-seatbelt", "-conveyor"),
    "belt": ("-seatbelt", "-conveyor"),
    "hooks": ("-crane", "-towing"),
    "hook": ("-crane", "-towing"),
    "sleeves": ("-pipe", "-cable"),
    "sleeve": ("-pipe", "-cable"),
}

# Soft synonyms so "lifting straps" still matches hunt "weightlifting straps"
PRODUCT_MOD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "weightlifting": ("weightlifting", "weight lifting", "lifting", "powerlifting"),
    "wrist": ("wrist", "forearm"),
    "knee": ("knee",),
    "martial": ("martial", "karate", "bjj", "jiu-jitsu", "jiujitsu", "taekwondo"),
    "lifting": ("lifting", "weightlifting", "deadlift"),
}

_CHANNEL_SERP_RE = re.compile(
    r"\b(distributor|distributors|wholesale|wholesaler|importer|importers|dealer|b2b)\b",
    re.I,
)


def split_product_and_role(line: str) -> tuple[str, str]:
    """Split 'weightlifting straps distributors' → ('weightlifting straps', 'distributors')."""
    text = re.sub(r"\s+", " ", (line or "").strip())
    if not text:
        return "", ""
    m = re.search(
        r"^(?P<product>.+?)\s+(?P<role>distributors?|wholesalers?|importers?|retailers?|"
        r"buyers?|dealers?|gyms?|clinics?|brands?)\s*$",
        text,
        re.I,
    )
    if m:
        return m.group("product").strip(), m.group("role").strip().lower()
    return text, ""


def _singular_token(word: str) -> str:
    w = (word or "").strip().lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def secondary_product_phrases(product: str) -> List[str]:
    """
    Broader discovery phrases used ONLY after exact-product searches are exhausted.
    Never reduce a specific product to its headword (straps, belts) or to 'fitness equipment'.
    """
    p = re.sub(r"\s+", " ", (product or "").strip().lower())
    if p in ("martial arts belts", "martial arts belt"):
        return ["martial arts equipment"]
    return []


def interpret_hunt_intent(
    products: List[str],
    buyers: List[str],
    location: str,
) -> Dict[str, Any]:
    """
    Query-intent interpreter: exact product × selected buyer type × location.
    Primary queries are the searches that must run first.
    Volume queries keep the same product meaning (quotes / singular).
    Secondary queries are optional broader discovery and must not replace primaries.
    """
    place = re.sub(r"\s+", " ", (location or "").strip())
    roles: List[str] = []
    seen_roles = set()
    for raw in buyers or []:
        form = normalize_buyer_query_term(raw)
        if not form:
            continue
        key = form.rstrip("s")
        if key in seen_roles:
            continue
        seen_roles.add(key)
        roles.append(form)
    if not roles:
        roles = ["distributors"]

    exact_products: List[str] = []
    seen_p = set()
    for raw in products or []:
        product, role_on_line = split_product_and_role(re.sub(r"\s+", " ", (raw or "").strip()))
        product = re.sub(r"\s+", " ", product).strip().lower()
        if not product or len(product.split()) < 1:
            continue
        key = product.lower()
        if key in seen_p:
            continue
        seen_p.add(key)
        exact_products.append(product)
        if role_on_line:
            form = normalize_buyer_query_term(role_on_line)
            if form and form.rstrip("s") not in seen_roles:
                seen_roles.add(form.rstrip("s"))
                roles.append(form)

    primary: List[str] = []
    volume: List[str] = []
    secondary: List[str] = []
    seen_q = set()

    def _add(bucket: List[str], q: str) -> None:
        qn = re.sub(r"\s+", " ", (q or "").strip())
        if not qn or qn.lower() in seen_q:
            return
        seen_q.add(qn.lower())
        bucket.append(qn)

    # Fair order: each product gets every selected buyer before the next role pass repeats.
    for role in roles:
        for product in exact_products:
            if place:
                _add(primary, f"{product} {role} in {place}")
            else:
                _add(primary, f"{product} {role}")

    for role in roles:
        singular_role = _singular_token(role) if role.endswith("s") else role
        for product in exact_products:
            words = product.split()
            singular_product = " ".join(words[:-1] + [_singular_token(words[-1])]) if words else product
            if place:
                _add(volume, f'"{product}" {role} in {place}')
                if singular_product.lower() != product.lower() or singular_role != role:
                    _add(volume, f'"{singular_product}" {singular_role} {place}')
            else:
                _add(volume, f'"{product}" {role}')

    for product in exact_products:
        for broader in secondary_product_phrases(product):
            for role in roles[:2]:
                if place:
                    _add(secondary, f"{broader} {role} in {place}")
                else:
                    _add(secondary, f"{broader} {role}")

    return {
        "products": exact_products,
        "buyers": roles,
        "location": place,
        "primary_queries": primary,
        "volume_queries": volume,
        "secondary_queries": secondary,
    }


def format_precise_hunt_query(line: str, place: str = "", *, force_unquoted: bool = False) -> str:
    """
    Keep multi-word products intact for SERP and add industry negatives.
    Quote only ambiguous heads (straps/belts/…) so engines don't drift to cargo straps,
    while still allowing enough recall for volume.
    """
    product, role = split_product_and_role(line)
    if not product:
        return ""
    words = product.lower().split()
    head = words[-1] if words else ""
    use_quotes = (
        not force_unquoted
        and len(words) >= 2
        and head in AMBIGUOUS_PRODUCT_HEADS
    )
    core = f'"{product}"' if use_quotes else product
    parts = [core]
    if role:
        parts.append(role)
    q = " ".join(parts)
    if place and place.lower() not in q.lower():
        q = f"{q} in {place}"
    negs = PRODUCT_HEAD_NEGATIVES.get(head, ())
    if negs:
        q = f"{q} {' '.join(negs)}"
    return re.sub(r"\s+", " ", q).strip()


def parse_discovery_query(query: str) -> tuple[str, str, str]:
    """
    Recover product, buyer role, and place from a precise hunt query.
    '"weightlifting straps" distributors in California -truck' →
      ('weightlifting straps', 'distributors', 'California')
    """
    raw = re.sub(r"\s+", " ", (query or "").strip())
    if not raw:
        return "", "", ""
    # Drop SERP negatives
    raw = re.sub(r"\s+-\S+", "", raw).strip()
    place = ""
    m_place = re.search(r"\bin\s+(.+)$", raw, re.I)
    if m_place:
        place = m_place.group(1).strip().rstrip(",.")
        raw = raw[: m_place.start()].strip()
    m_q = re.match(r'^"([^"]+)"\s*(.*)$', raw)
    if m_q:
        product = m_q.group(1).strip()
        role = normalize_buyer_query_term(m_q.group(2) or "") or (m_q.group(2) or "").strip()
        return product, role, place
    product, role = split_product_and_role(raw)
    return product, (normalize_buyer_query_term(role) or role), place


def product_phrases_from_profile_categories(categories: List[str]) -> List[str]:
    """Multi-word hunt products that must stay faithful in matching."""
    out: List[str] = []
    seen = set()
    for c in categories or []:
        p = re.sub(r"\s+", " ", (c or "").strip().lower())
        if len(p.split()) < 2:
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def serp_blob_matches_products(blob: str, categories: List[str]) -> bool:
    """
    True when SERP title/snippet is plausible for hunt products.
    Rejects clear cargo/truck collisions and generic gym stores with zero product nouns.
    Thin distributor snippets are allowed through for homepage qualify.
    """
    text = (blob or "").lower()
    if not text.strip():
        return True
    phrases = product_phrases_from_profile_categories(categories)
    if not phrases:
        return True
    if any(p in text for p in phrases):
        return True

    wrong = (
        "truck", "cargo", "ratchet", "tow", "tie-down", "tiedown", "lashing",
        "pallet", "seat belt", "seatbelt", "conveyor", "crane",
    )

    def _mod_hit(mods: List[str]) -> bool:
        for m in mods:
            if re.search(rf"\b{re.escape(m)}\b", text):
                return True
            for syn in PRODUCT_MOD_SYNONYMS.get(m, ()):
                if syn in text:
                    return True
        return False

    for phrase in phrases:
        words = [w for w in phrase.split() if len(w) > 2]
        if len(words) < 2:
            continue
        head, mods = words[-1], words[:-1]
        head_hit = bool(re.search(rf"\b{re.escape(head)}\b", text))
        if head in AMBIGUOUS_PRODUCT_HEADS:
            if head_hit and _mod_hit(mods):
                return True
            # Channel SERP: "straps distributor" / "knee sleeve wholesaler" — keep for qualify
            if head_hit and _CHANNEL_SERP_RE.search(text) and not any(w in text for w in wrong):
                return True
        else:
            hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text))
            if hits >= min(2, len(words)):
                return True

    heads = {p.split()[-1] for p in phrases}
    amb_heads = heads & AMBIGUOUS_PRODUCT_HEADS
    if amb_heads and any(re.search(rf"\b{re.escape(h)}\b", text) for h in amb_heads):
        if any(w in text for w in wrong):
            return False
        # Ambiguous head alone, no wholesale cue — weak; allow only if not clearly retail gym
        if any(c in text for c in ("gym", "fitness store", "sports store")) and not _CHANNEL_SERP_RE.search(text):
            return False
        return True  # e.g. thin "Straps wholesaler California" snippet

    # Generic fitness retail with no hunt product nouns
    if any(c in text for c in ("gym", "fitness", "sports store")) and not _CHANNEL_SERP_RE.search(text):
        product_tokens = set()
        for p in phrases:
            product_tokens.update(w for w in p.split() if len(w) > 3)
        if not any(re.search(rf"\b{re.escape(t)}\b", text) for t in product_tokens):
            return False
    return True


def page_matches_specific_products(blob: str, categories: List[str]) -> str:
    """
    Offer fidelity for scraped pages.
    Returns 'high' | 'medium' | 'low' | 'unknown'.
    """
    text = (blob or "").lower()
    phrases = product_phrases_from_profile_categories(categories)
    if not phrases:
        return "unknown"
    if not text.strip():
        return "unknown"
    if any(p in text for p in phrases):
        return "high"
    for phrase in phrases:
        words = [w for w in phrase.split() if len(w) > 2]
        if len(words) < 2:
            continue
        head, mods = words[-1], words[:-1]
        mod_hit = any(re.search(rf"\b{re.escape(m)}\b", text) for m in mods)
        head_hit = bool(re.search(rf"\b{re.escape(head)}\b", text))
        ctx = any(c in text for c in PRODUCT_CONTEXT_WORDS)
        if head in AMBIGUOUS_PRODUCT_HEADS:
            if head_hit and mod_hit:
                return "high"
            if head_hit and ctx:
                return "medium"
            if mod_hit and ctx:
                return "medium"
            if head_hit and not mod_hit and not ctx:
                return "low"  # bare 'straps' / truck straps
        else:
            hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text))
            if hits >= len(words):
                return "high"
            if hits >= 2 or (hits >= 1 and ctx):
                return "medium"
    return "unknown"


def extract_buyers_from_prompt(prompt: str) -> List[str]:
    """Pull buyer roles the user named (e.g. importers) so search prioritizes them."""
    text = prompt or ""
    if not text:
        return []
    found: List[str] = []
    # Prefer explicit "Buyer types:" header from composeHuntPrompt
    for raw in text.splitlines():
        low = raw.strip().lower()
        if low.startswith("buyer types:"):
            chunk = raw.split(":", 1)[-1]
            for part in re.split(r"[,;/|]+", chunk):
                form = normalize_buyer_query_term(part)
                if form and form not in found:
                    found.append(form)
            if found:
                return found[:8]
    low = text.lower()
    for label, forms in BUYER_ROLE_FORMS:
        if any(re.search(rf"\b{re.escape(f)}\b", low) for f in forms):
            if label not in found:
                found.append(label)
    return found[:8]


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
