"""Motion-aware search planning: seller profile → discovery pools → query families."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


OEM_HINTS = (
    "private label", "private-label", "privatelabel", "oem", "odm",
    "white label", "white-label", "contract manufactur", "made for brands",
)
WHOLESALE_HINTS = ("wholesale", "bulk", "distributor", "importer", "b2b", "moq")
SAAS_HINTS = ("saas", "software", "platform", "subscription", "cloud app", "api")
SERVICE_HINTS = ("consulting", "agency", "professional service", "managed service")
LOCAL_BUYERS = (
    "gym", "clinic", "hotel", "restaurant", "salon", "spa", "contractor",
    "workshop", "school", "hospital", "studio", "club",
)
MANUFACTURER_HINTS = ("manufacturer", "factory", "manufacturing", "plant")
NEGATIVE_BASE = ("-jobs", "-wikipedia", "-pdf", "-salary", "-career")

DIRECTORY_JUNK = ("directory", "listicle", "top 10", "best companies")


def _uniq(items: List[str], limit: int = 8) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in items:
        key = re.sub(r"\s+", " ", (raw or "").strip())
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
        if len(out) >= limit:
            break
    return out


def _blob(*parts: Any) -> str:
    chunks: List[str] = []
    for part in parts:
        if isinstance(part, list):
            chunks.extend(str(x) for x in part if x)
        elif part:
            chunks.append(str(part))
    return " ".join(chunks).lower()


def _contains_any(text: str, needles: tuple[str, ...] | List[str]) -> bool:
    return any(n in text for n in needles)


def _contains_word(text: str, needles: tuple[str, ...] | List[str]) -> bool:
    return any(re.search(rf"\b{re.escape(n)}s?\b", text) for n in needles)


@dataclass
class PlannedQuery:
    query: str
    family: str
    pool: str
    use_maps: bool = False
    wave: int = 1


@dataclass
class SellerProfile:
    offer_class: str
    sales_motion: str
    hunting_buyers: bool
    geo_mode: str
    categories: List[str]
    buyers: List[str]
    places: List[str]
    use_maps: bool
    pools: Dict[str, str]
    exclude_terms: List[str] = field(default_factory=list)
    intent_examples: List[str] = field(default_factory=list)


def infer_seller_profile(
    products: List[Dict[str, Any]],
    icp: Dict[str, Any],
    business: Dict[str, Any],
) -> SellerProfile:
    categories = _uniq([
        *(business.get("primaryCategories") or business.get("primary_categories") or []),
        *[p.get("category") for p in products if p.get("category") and p.get("category") != "Uncategorized"],
        *[p.get("name") for p in products if p.get("name")],
    ], limit=6)
    cats = [c for c in categories if c][:4] or ["wholesale"]

    buyers = _uniq(list(icp.get("targetBuyerTypes") or icp.get("target_buyer_types") or []), 6)
    if not buyers:
        buyers = ["distributors", "retailers", "wholesalers", "importers"]

    countries = list(icp.get("targetCountries") or icp.get("target_countries") or [])
    markets = list(business.get("targetMarkets") or business.get("target_markets") or [])
    places = _uniq([p for p in countries + markets if p], 4)

    text = _blob(
        business.get("description"),
        business.get("name"),
        cats,
        buyers,
        [p.get("description") for p in products],
        [p.get("moq") for p in products],
    )
    buyer_blob = " ".join(buyers).lower()

    if _contains_any(text, SAAS_HINTS) and not _contains_any(text, OEM_HINTS):
        offer_class = "software"
    elif _contains_any(text, SERVICE_HINTS) and not cats:
        offer_class = "services"
    else:
        offer_class = "goods"

    if offer_class == "software":
        sales_motion = "saas"
    elif _contains_any(text, OEM_HINTS) or (any(p.get("moq") for p in products) and "label" in text):
        sales_motion = "oem_private_label"
    elif _contains_word(buyer_blob, LOCAL_BUYERS) or _contains_word(text, LOCAL_BUYERS):
        sales_motion = "local"
    elif _contains_any(text, WHOLESALE_HINTS) or any(
        b in buyer_blob for b in ("distributor", "importer", "wholesaler", "wholesale")
    ):
        sales_motion = "wholesale"
    else:
        sales_motion = "brand_retail"

    hunting_buyers = not any(
        k in buyer_blob for k in ("manufacturer", "factory", "plant", "oem supplier")
    )
    if sales_motion == "saas":
        hunting_buyers = True

    seller_in_target = False
    if places:
        seller_in_target = any(p.lower() in text for p in places)
    geo_mode = "local" if sales_motion == "local" else ("domestic" if seller_in_target else "export")

    use_maps = sales_motion == "local" or _contains_word(buyer_blob, LOCAL_BUYERS)

    pools = {
        "direct_icp": "primary",
        "importer_distributor": "off",
        "oem_private_label": "off",
        "retail_brand": "off",
        "competitor_customer": "off",
        "ecommerce": "off",
        "maps_local": "off",
        "intent_overlay": "sample",
    }
    if sales_motion == "oem_private_label":
        pools["oem_private_label"] = "primary"
        pools["importer_distributor"] = "primary" if offer_class == "goods" else "off"
        pools["retail_brand"] = "primary"
        pools["competitor_customer"] = "sample"
        pools["ecommerce"] = "sample"
    elif sales_motion == "wholesale":
        pools["importer_distributor"] = "primary"
        pools["retail_brand"] = "sample"
        pools["competitor_customer"] = "sample"
    elif sales_motion == "brand_retail":
        pools["retail_brand"] = "primary"
        pools["ecommerce"] = "sample"
    elif sales_motion == "local":
        pools["maps_local"] = "primary"
        pools["direct_icp"] = "sample"
    elif sales_motion == "saas":
        pools["direct_icp"] = "primary"
        pools["intent_overlay"] = "sample"

    if offer_class != "goods":
        pools["importer_distributor"] = "off"
        pools["oem_private_label"] = "off"

    exclude_terms = list(NEGATIVE_BASE)
    if hunting_buyers and sales_motion in ("oem_private_label", "wholesale", "brand_retail"):
        exclude_terms.extend(["-manufacturer", "-factory", "-wholesale market"])

    intent_examples = []
    if sales_motion == "oem_private_label":
        intent_examples = ["seeking manufacturer", "private label program", "now sourcing"]
    elif sales_motion == "wholesale":
        intent_examples = ["new distribution", "expanding product line", "importer of"]
    elif sales_motion == "saas":
        intent_examples = ["implementing", "replacing software", "hiring operations"]
    elif sales_motion == "local":
        intent_examples = ["new location", "grand opening", "renovation"]

    return SellerProfile(
        offer_class=offer_class,
        sales_motion=sales_motion,
        hunting_buyers=hunting_buyers,
        geo_mode=geo_mode,
        categories=cats,
        buyers=buyers[:4],
        places=places,
        use_maps=use_maps,
        pools=pools,
        exclude_terms=exclude_terms,
        intent_examples=intent_examples,
    )


def _neg(profile: SellerProfile) -> str:
    return " ".join(profile.exclude_terms)


def _place(profile: SellerProfile, index: int = 0) -> str:
    return profile.places[index] if profile.places else ""


def plan_wave1(profile: SellerProfile, user_prompt: str = "") -> List[PlannedQuery]:
    queries: List[PlannedQuery] = []
    cat = profile.categories[0]
    cat2 = profile.categories[1] if len(profile.categories) > 1 else cat
    place = _place(profile)
    buyer = profile.buyers[0]
    neg = _neg(profile)

    if user_prompt.strip():
        queries.append(PlannedQuery(user_prompt.strip(), "user", "direct_icp", False, 1))

    def add(q: str, family: str, pool: str, maps: bool = False) -> None:
        q = re.sub(r"\s+", " ", q).strip()
        if not q:
            return
        if any(x.query.lower() == q.lower() for x in queries):
            return
        queries.append(PlannedQuery(q, family, pool, maps and profile.use_maps, 1))

    if profile.pools.get("direct_icp") in ("primary", "sample"):
        add(f"{buyer} {cat} {place} {neg}", "icp_retrieval", "direct_icp")

    if profile.pools.get("oem_private_label") == "primary":
        add(f"private label {cat} brand {place} {neg}", "motion_oem", "oem_private_label")
        add(f"seeking {cat} manufacturer {place} -jobs", "motion_oem", "oem_private_label")

    if profile.pools.get("importer_distributor") == "primary":
        add(f"{cat} importer distributor {place} {neg}", "channel", "importer_distributor")
        add(f"{cat} wholesale distributor {place} {neg}", "channel", "importer_distributor")

    if profile.pools.get("retail_brand") in ("primary", "sample"):
        add(f"{cat} brand {place} wholesale {neg}", "retail_brand", "retail_brand")
        if cat2 != cat:
            add(f"{cat2} clothing brand {place} {neg}" if "wear" in cat2.lower() or "apparel" in cat.lower()
                else f"{cat2} brand {place} {neg}", "retail_brand", "retail_brand")

    if profile.pools.get("ecommerce") == "sample":
        add(f"{cat} DTC brand {place} {neg}", "ecommerce", "ecommerce")

    if profile.pools.get("competitor_customer") == "sample":
        add(f"{cat} stockists {place} -directory", "competitor_customer", "competitor_customer")

    if profile.use_maps:
        maps_q = f"{buyer} {cat}" if buyer else cat
        add(f"{maps_q} {place}".strip(), "maps_local", "maps_local", maps=True)

    if profile.sales_motion == "saas":
        add(f"{buyer} {cat} software {place} {neg}", "icp_retrieval", "direct_icp")

    # Cap wave 1: diverse families, not clones
    out: List[PlannedQuery] = []
    seen_family: Dict[str, int] = {}
    for item in queries:
        n = seen_family.get(item.family, 0)
        if n >= 2 and item.family != "user":
            continue
        seen_family[item.family] = n + 1
        out.append(item)
        if len(out) >= 6:
            break
    return out or queries[:6]


def plan_wave2(
    profile: SellerProfile,
    wave1_stats: Dict[str, Any],
    learned_terms: Optional[List[str]] = None,
) -> List[PlannedQuery]:
    """Follow-up searches from SERP inspection — not synonym clones."""
    cat = profile.categories[0]
    place = _place(profile)
    neg = _neg(profile)
    extra_neg = []
    queries: List[PlannedQuery] = []

    junk_ratio = float(wave1_stats.get("junk_ratio") or 0)
    mfr_ratio = float(wave1_stats.get("manufacturer_ratio") or 0)
    geo_miss = float(wave1_stats.get("wrong_geo_ratio") or 0)
    relevant = int(wave1_stats.get("relevant_count") or 0)

    if junk_ratio >= 0.5:
        extra_neg.extend(["-list", "-directory", "-top 10"])
    if mfr_ratio >= 0.4 and profile.hunting_buyers:
        extra_neg.extend(["-manufacturer", "-factory", "-OEM"])
    if geo_miss >= 0.4 and place:
        extra_neg.append(f'"{place}"')

    neg2 = " ".join([neg, *extra_neg])

    if junk_ratio >= 0.5:
        queries.append(PlannedQuery(
            f"{profile.buyers[0]} {cat} company {place} {neg2}".strip(),
            "refine_junk", "direct_icp", False, 2,
        ))

    if mfr_ratio >= 0.4 and profile.hunting_buyers:
        queries.append(PlannedQuery(
            f"{cat} brand {place} -manufacturer -factory {neg}".strip(),
            "refine_buyers", "retail_brand", False, 2,
        ))

    for term in (learned_terms or [])[:3]:
        term = (term or "").strip()
        if len(term) < 4:
            continue
        queries.append(PlannedQuery(
            f"{term} {place} {neg2}".strip(),
            "learned_term", "direct_icp", False, 2,
        ))

    for name in (wave1_stats.get("competitor_names") or [])[:2]:
        queries.append(PlannedQuery(
            f'"{name}" customers OR stockists OR clients {cat}',
            "competitor_customer", "competitor_customer", False, 2,
        ))

    if relevant >= 3 and not queries:
        queries.append(PlannedQuery(
            f"{cat} {profile.buyers[0]} {place} independent {neg}".strip(),
            "expand_relevant", "direct_icp", False, 2,
        ))

    # Dedup
    seen = set()
    out = []
    for q in queries:
        key = q.query.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 4:
            break
    return out


def profile_to_dict(profile: SellerProfile) -> Dict[str, Any]:
    return {
        "offerClass": profile.offer_class,
        "salesMotion": profile.sales_motion,
        "huntingBuyers": profile.hunting_buyers,
        "geoMode": profile.geo_mode,
        "categories": profile.categories,
        "buyers": profile.buyers,
        "places": profile.places,
        "useMaps": profile.use_maps,
        "pools": profile.pools,
    }
