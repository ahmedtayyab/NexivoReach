"""Work out what a hunt is really after, so one niche line becomes hundreds of businesses.

A hunt line such as "BFR training bands distributors Canada" finds a handful of
sites, because few businesses use those exact words. The buyers are physiotherapy
suppliers, sports-medicine clinics, gyms, sporting-goods shops, and so on, each
under its own name, in dozens of cities. This module asks the AI model (or falls
back to rules) for those business TYPES, the words such a business uses on its
site, and the cities to cover. The hunt then searches `type x city` after the
exact lines have run.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)


@dataclass
class IntentExpansion:
    buyer_types: List[str] = field(default_factory=list)
    terms: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    osm_families: List[str] = field(default_factory=list)
    source: str = "rules"

    def usable(self) -> bool:
        return bool(self.buyer_types)


# ---------------------------------------------------------------------------
# Cities per market. The AI model supplies these too; this keeps the sweep
# alive when no AI key answers.
# ---------------------------------------------------------------------------
COUNTRY_CITIES: Dict[str, List[str]] = {
    "united states": ["New York", "Los Angeles", "Chicago", "Houston", "Dallas", "Phoenix", "Philadelphia", "Atlanta", "Miami", "Seattle", "Denver", "Boston", "San Diego", "Las Vegas", "Minneapolis", "Detroit", "Charlotte", "Austin"],
    "canada": ["Toronto", "Vancouver", "Montreal", "Calgary", "Edmonton", "Ottawa", "Winnipeg", "Mississauga", "Hamilton", "Quebec City", "Halifax", "Surrey", "Brampton", "Saskatoon", "Victoria"],
    "united kingdom": ["London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Liverpool", "Bristol", "Sheffield", "Edinburgh", "Cardiff", "Newcastle", "Nottingham", "Leicester", "Belfast", "Southampton"],
    "australia": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Gold Coast", "Canberra", "Newcastle", "Wollongong", "Hobart"],
    "new zealand": ["Auckland", "Wellington", "Christchurch", "Hamilton", "Tauranga", "Dunedin"],
    "ireland": ["Dublin", "Cork", "Galway", "Limerick", "Waterford"],
    "united arab emirates": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Al Ain", "Ras Al Khaimah"],
    "saudi arabia": ["Riyadh", "Jeddah", "Dammam", "Mecca", "Medina", "Khobar"],
    "qatar": ["Doha", "Al Rayyan", "Al Wakrah"],
    "germany": ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart", "Düsseldorf", "Leipzig", "Dortmund", "Essen"],
    "france": ["Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Bordeaux", "Lille", "Strasbourg"],
    "netherlands": ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven"],
    "spain": ["Madrid", "Barcelona", "Valencia", "Seville", "Bilbao", "Malaga", "Zaragoza"],
    "italy": ["Milan", "Rome", "Naples", "Turin", "Bologna", "Florence", "Genoa"],
    "india": ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat", "Ludhiana", "Jalandhar"],
    "pakistan": ["Karachi", "Lahore", "Islamabad", "Faisalabad", "Rawalpindi", "Sialkot", "Multan", "Peshawar"],
    "singapore": ["Singapore"],
    "malaysia": ["Kuala Lumpur", "Penang", "Johor Bahru", "Petaling Jaya", "Shah Alam"],
    "south africa": ["Johannesburg", "Cape Town", "Durban", "Pretoria", "Port Elizabeth"],
    "mexico": ["Mexico City", "Guadalajara", "Monterrey", "Puebla", "Tijuana"],
    "brazil": ["São Paulo", "Rio de Janeiro", "Brasília", "Belo Horizonte", "Curitiba", "Porto Alegre"],
    "turkey": ["Istanbul", "Ankara", "Izmir", "Bursa", "Antalya"],
}


# ---------------------------------------------------------------------------
# Rule fallback: topic -> business types, site words, OSM families.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Rule:
    name: str
    pattern: re.Pattern
    types: Tuple[str, ...]
    terms: Tuple[str, ...]
    osm: Tuple[str, ...]


def _rule(name: str, pattern: str, types: Sequence[str], terms: Sequence[str], osm: Sequence[str]) -> _Rule:
    return _Rule(name, re.compile(pattern, re.I), tuple(types), tuple(terms), tuple(osm))


_RULES: List[_Rule] = [
    _rule(
        "rehab",
        r"\b(bfr|blood flow|occlusion|kaatsu|rehab\w*|physio\w*|therap\w*|recover\w*|compression|brace|bracing|orthop\w*|mobility|massage|injury)\b",
        [
            "physiotherapy supply stores", "rehabilitation equipment suppliers", "sports medicine clinics",
            "orthopedic supply stores", "chiropractic clinics", "sports therapy equipment stores",
            "medical supply stores", "athletic training facilities",
        ],
        [
            "physiotherapy", "physio", "rehabilitation", "rehab", "sports medicine", "orthopedic",
            "chiropractic", "therapy equipment", "medical supply", "athletic training", "recovery",
        ],
        ["rehab", "gym"],
    ),
    _rule(
        "combat",
        r"\b(box\w*|mma|muay|martial|karate|judo|taekwondo|bjj|jiu|combat|kickbox\w*|punch\w*|gloves?|sparring|wrestl\w*)\b",
        [
            "boxing equipment stores", "martial arts supply stores", "MMA gyms", "boxing gyms",
            "martial arts schools", "combat sports shops",
        ],
        [
            "boxing", "mma", "martial arts", "muay thai", "karate", "judo", "taekwondo",
            "combat sports", "kickboxing", "sparring", "fight gear",
        ],
        ["club", "retail"],
    ),
    _rule(
        "gym",
        r"\b(gym|gyms|fitness|weight\w*|lift\w*|barbell|dumbbell|kettlebell|strength|crossfit|powerlifting|resistance|yoga|pilates|strap|straps|hooks?|belts?|workout|exercise|training|athletic|bands?)\b",
        [
            "fitness equipment stores", "gym equipment suppliers", "gym equipment wholesalers",
            "crossfit gyms", "strength training stores", "health clubs",
            "sports nutrition stores", "personal training studios",
        ],
        [
            "fitness", "gym", "strength training", "weightlifting", "crossfit", "powerlifting",
            "workout", "exercise equipment", "training equipment", "barbell", "dumbbell",
        ],
        ["gym", "retail"],
    ),
    _rule(
        "apparel",
        r"\b(team\w*|jerseys?|uniforms?|apparel|sportswear|activewear|clothing|garments?)\b",
        ["sportswear stores", "team uniform suppliers", "sports clubs", "athletic apparel retailers"],
        ["sportswear", "apparel", "teamwear", "uniform", "athletic wear", "activewear", "jersey"],
        ["retail", "club"],
    ),
]

_SPORTS_BASE = _rule(
    "sports",
    r".",
    ["sporting goods stores", "sports equipment wholesalers", "sports equipment distributors"],
    ["sporting goods", "sports equipment", "sports store", "athletic"],
    ["retail"],
)

_CHANNEL_WORDS = re.compile(r"\b(distribut\w*|wholesal\w*|import\w*|supplier\w*|stockist\w*)\b", re.I)
_TYPE_BAD = re.compile(r"\b(blog|news|forum|article|review|wiki|pdf|download|job|jobs|career)\b", re.I)
_TYPE_TOO_GENERIC = {
    "business", "businesses", "company", "companies", "store", "stores", "shop", "shops",
    "supplier", "suppliers", "retailers", "wholesalers", "distributors", "buyers",
}


def _clean_list(values: Iterable[Any], *, max_words: int, limit: int, min_len: int = 3) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in values or []:
        text = re.sub(r"\s+", " ", str(raw or "").strip().strip(".,;:\"'"))
        if len(text) < min_len or len(text) > 70:
            continue
        if "http" in text.lower() or len(text.split()) > max_words:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def osm_families_for_types(types: Iterable[str]) -> List[str]:
    blob = " ".join(types).lower()
    fams: List[str] = []
    if re.search(r"physio|rehab|medical|orthop|chiropract|sports medicine|therap", blob):
        fams.append("rehab")
    if re.search(r"\bgym|fitness|health club|studio|crossfit|training", blob):
        fams.append("gym")
    if re.search(r"\bshop|store|retail|sporting goods|stockist", blob):
        fams.append("retail")
    if re.search(r"\bclub|academy|school|team", blob):
        fams.append("club")
    if re.search(r"martial|boxing|\bmma\b|muay|karate|judo|taekwondo|combat|kickbox|jiu", blob):
        fams.append("combat")
    return fams


def rules_expansion(
    lines: Sequence[str],
    seller_categories: Sequence[str],
    *,
    channel: bool,
) -> IntentExpansion:
    topic = " ".join(lines) + " " + " ".join(seller_categories or [])
    matched = [r for r in _RULES if r.pattern.search(topic)]
    types: List[str] = []
    terms: List[str] = []
    osm: List[str] = []

    if matched:
        pools = [list(r.types) for r in matched] + [list(_SPORTS_BASE.types)]
        # Round robin so every matched topic contributes its best types first.
        for rank in range(max(len(p) for p in pools)):
            for pool in pools:
                if rank < len(pool) and pool[rank] not in types:
                    types.append(pool[rank])
        for r in matched + [_SPORTS_BASE]:
            terms.extend(r.terms)
            osm.extend(r.osm)
    else:
        cats = _clean_list(seller_categories, max_words=4, limit=4)
        for cat in cats:
            low = cat.lower()
            for suffix in ("stores", "wholesalers", "distributors", "suppliers"):
                types.append(f"{low} {suffix}")
            terms.extend(w for w in re.findall(r"[a-z]{4,}", low))
        osm = ["retail"]

    if channel:
        types.sort(key=lambda t: 0 if _CHANNEL_WORDS.search(t) else 1)
    return IntentExpansion(
        buyer_types=_clean_list(types, max_words=6, limit=14),
        terms=_clean_list(terms, max_words=3, limit=24),
        locations=[],
        osm_families=list(dict.fromkeys(osm)),
        source="rules",
    )


# ---------------------------------------------------------------------------
# AI expansion
# ---------------------------------------------------------------------------
def _prompt(lines: Sequence[str], seller_brief: str, place: str, country_level: bool) -> str:
    where = (
        f"the whole country ({place}); list the main cities"
        if country_level
        else f"{place}; list this place first, then the nearby cities, districts and suburbs"
    )
    listed = "\n".join(f"- {ln}" for ln in lines[:10])
    return (
        "You help an exporter/manufacturer find BUYERS.\n"
        f"The seller makes: {seller_brief or 'sports and fitness products'}.\n"
        f"The user typed these search lines:\n{listed}\n"
        f"Target market: {where}.\n\n"
        "A single phrase finds few businesses because buyers use many different names. "
        "Work out WHAT KINDS of real businesses would buy or stock these products "
        "(shops, wholesalers, distributors, clinics, gyms, clubs, studios, suppliers...).\n"
        "Return ONLY JSON:\n"
        "{\n"
        '  "buyer_types": [8 to 12 searchable business types, plural, 2-5 words each, like "physiotherapy supply stores"],\n'
        '  "relevance_terms": [12 to 20 single words or short phrases that appear on such a business\'s own website],\n'
        '  "locations": [12 to 16 cities or regions to search, biggest first]\n'
        "}\n"
        "Rules: types must be businesses (never articles, blogs, jobs, directories); "
        "stay inside the seller's product world; no brand names."
    )


def _ai_text(provider: Any, prompt: str) -> str:
    if not getattr(provider, "available", False):
        return ""
    try:
        if hasattr(provider, "_complete"):
            return str(provider._complete(prompt) or "")
        if hasattr(provider, "_generate"):
            return str(provider._generate(prompt) or "")
    except Exception as exc:
        log.warning("Intent expansion AI call failed: %s", exc)
    return ""


def ai_expansion(
    provider: Any,
    lines: Sequence[str],
    seller_brief: str,
    place: str,
    country_level: bool,
) -> Optional[IntentExpansion]:
    from app.providers.json_util import parse_json_payload

    raw = _ai_text(provider, _prompt(lines, seller_brief, place, country_level))
    if not raw:
        return None
    data = parse_json_payload(raw)
    if not isinstance(data, dict):
        return None
    types = [
        t for t in _clean_list(data.get("buyer_types") or [], max_words=6, limit=14)
        if t.lower() not in _TYPE_TOO_GENERIC and not _TYPE_BAD.search(t)
    ]
    terms = _clean_list(data.get("relevance_terms") or [], max_words=3, limit=24)
    locations = _clean_list(data.get("locations") or [], max_words=4, limit=18)
    if len(types) < 3:
        return None
    return IntentExpansion(
        buyer_types=types,
        terms=terms,
        locations=locations,
        osm_families=osm_families_for_types(types),
        source="ai",
    )


def expand_hunt_intent(
    provider: Any,
    *,
    lines: Sequence[str],
    seller_brief: str,
    seller_categories: Sequence[str],
    place: str,
    country_name: str,
    city: str,
    channel: bool,
) -> IntentExpansion:
    """AI first, rules to fill what it did not give. Never raises."""
    country_level = not city
    rules = rules_expansion(lines, seller_categories, channel=channel)
    ai: Optional[IntentExpansion] = None
    try:
        ai = ai_expansion(provider, lines, seller_brief, place, country_level)
    except Exception as exc:
        log.warning("Intent expansion failed: %s", exc)

    if ai:
        types = _clean_list(ai.buyer_types + rules.buyer_types, max_words=6, limit=16)
        terms = _clean_list(ai.terms + rules.terms, max_words=3, limit=32)
        locations = list(ai.locations)
        source = "ai"
    else:
        types, terms, locations, source = rules.buyer_types, rules.terms, [], "rules"

    cities = COUNTRY_CITIES.get((country_name or "").lower(), [])
    if country_level:
        locations = _clean_list(locations + cities, max_words=4, limit=20)
        if not locations and place:
            locations = [place]
    else:
        # The AI sometimes names far-away big cities. A city hunt stays near its city.
        far = {c.lower() for c in COUNTRY_CITIES.get((country_name or "").lower(), [])} - {city.lower()}
        near = [loc for loc in locations if loc.lower() not in far]
        locations = _clean_list([city] + near, max_words=4, limit=10)

    fams = list(dict.fromkeys((ai.osm_families if ai else []) + rules.osm_families))
    return IntentExpansion(
        buyer_types=types,
        terms=terms,
        locations=locations,
        osm_families=fams,
        source=source,
    )


# ---------------------------------------------------------------------------
# Query building and matching
# ---------------------------------------------------------------------------
def build_category_queries(
    exp: IntentExpansion,
    *,
    country_name: str,
    country_level: bool,
    max_queries: int,
    skip: Iterable[str] = (),
) -> List[Dict[str, str]]:
    """`type x city` search lines, spread so early lines cover many types AND many cities."""
    skipped = {re.sub(r"\s+", " ", s.lower()).strip() for s in skip}
    country_label = (country_name or "").title()
    pairs: List[Tuple[int, int, str, str]] = []
    types = exp.buyer_types[:12]
    locations = exp.locations[:16] or [""]
    for j, loc in enumerate(locations):
        for i, btype in enumerate(types):
            pairs.append((i + j, j, btype, loc))
    pairs.sort(key=lambda p: (p[0], p[1]))

    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for _score, _j, btype, loc in pairs:
        label = loc
        if loc and country_label and country_label.lower() not in loc.lower():
            label = f"{loc}, {country_label}"
        query = f"{btype} {label}".strip()
        key = query.lower()
        if key in seen or key in skipped:
            continue
        seen.add(key)
        out.append({"search_intent": f"{btype} · {loc or country_label}".strip(" ·"), "location": label, "query": query})
        if len(out) >= max_queries:
            break
    return out


def category_term_hits(text: str, terms: Iterable[str]) -> List[str]:
    """Distinct category terms found in `text` (whole words / phrases)."""
    low = (text or "").lower()
    if not low:
        return []
    found: List[str] = []
    for term in terms or []:
        t = (term or "").strip().lower()
        if len(t) < 3 or t in found:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", low):
            found.append(t)
    return found
