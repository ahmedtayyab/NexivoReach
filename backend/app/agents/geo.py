"""Extract and match geographic places from Discover prompts / ICP."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

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
    "united kingdom": ("uk", "britain", "england", "united kingdom"),
    "united arab emirates": ("uae", "dubai", "abu dhabi"),
    "canada": ("canada",),
    "germany": ("germany", "deutschland"),
    "pakistan": ("pakistan",),
}


def _word_hit(blob: str, term: str) -> bool:
    term = (term or "").strip().lower()
    if not term:
        return False
    if " " in term or len(term) > 3:
        return term in blob
    # short abbrev like nv, ca — word boundary
    return bool(re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", blob))


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
            if _word_hit(low, alias):
                return True
    return False


def extract_places_from_prompt(prompt: str) -> Tuple[List[str], bool]:
    """
    Pull state/city/country from Discover text.
    Returns (places, strict) — strict=True when user named a US state or specific city.
    """
    text = (prompt or "").strip()
    if not text:
        return [], False
    low = text.lower()
    found: List[str] = []
    strict = False

    # Multi-word states first
    for state in sorted(US_STATE_ALIASES.keys(), key=len, reverse=True):
        if _word_hit(low, state):
            found.append(state.title() if " " not in state else state.title())
            # normalize title case for multi-word
            found[-1] = " ".join(w.capitalize() for w in state.split())
            strict = True
            continue
        # abbrev only with clear context (in NV, , NV, Nevada)
        abbrev = US_STATE_ALIASES[state][0] if US_STATE_ALIASES[state] else ""
        if abbrev and re.search(rf"(?:in|near|,|\s){abbrev}\b", low):
            found.append(" ".join(w.capitalize() for w in state.split()))
            strict = True

    # Cities that map to states (if state not already added)
    for state, aliases in US_STATE_ALIASES.items():
        state_label = " ".join(w.capitalize() for w in state.split())
        for city in aliases[1:]:  # skip abbrev
            if _word_hit(low, city):
                if state_label not in found:
                    found.append(state_label)
                strict = True

    for country, aliases in COUNTRY_ALIASES.items():
        label = " ".join(w.capitalize() for w in country.split())
        if any(_word_hit(low, a) for a in (country, *aliases)):
            if label not in found and country not in {p.lower() for p in found}:
                # Don't add "United States" alone as strict city/state
                if country == "united states" and strict:
                    continue
                found.append(label)

    # Dedup preserving order
    seen = set()
    out = []
    for p in found:
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out[:4], strict
