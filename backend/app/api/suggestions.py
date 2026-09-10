"""
Light AI suggestion expansion.

Categories/buyers are inferred from the seller's free-text description via the
active LLM — not from a fixed industry dictionary. Local taxonomy is only a
thin fallback when the model is unavailable.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List

from app.api.deps import AuthUser, get_current_user
from app.providers.factory import get_ai_provider
from app.providers.fallback import FallbackProvider
from app.providers.json_util import parse_json_payload

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


class ExpandRequest(BaseModel):
    field: str  # categories | buyers | markets | discover
    query: str = ""
    description: str = ""
    catalogCategories: List[str] = []


@router.post("/expand")
async def expand_suggestions(req: ExpandRequest, _user: AuthUser = Depends(get_current_user)):
    field = (req.field or "categories").strip().lower()
    description = (req.description or "").strip()
    query = (req.query or "").strip()
    catalog = [c.strip() for c in (req.catalogCategories or []) if str(c).strip()]
    context = " ".join(part for part in [description, query, ", ".join(catalog)] if part).strip()

    local = _local_suggestions(field, context)
    if not context or len(context) < 3:
        return {"suggestions": local[:8], "source": "taxonomy"}

    provider = get_ai_provider()
    try:
        suggestions = await _ai_expand(provider, field, description, query, catalog)
        if suggestions:
            # AI is source of truth for open-ended fields — don't dilute with wrong packs
            if field in {"categories", "buyers"}:
                merged = _unique(suggestions + catalog)[:8]
            else:
                merged = _unique(suggestions + local)[:8]
            return {"suggestions": merged, "source": "ai"}
    except Exception:
        pass

    # Heuristic / catalog fallback
    if field == "categories" and catalog:
        return {"suggestions": _unique(catalog + local)[:8], "source": "catalog"}
    return {"suggestions": local[:8], "source": "taxonomy"}


async def _ai_expand(
    provider,
    field: str,
    description: str,
    query: str,
    catalog: List[str],
) -> List[str]:
    """Ask the active model for free-form labels inferred from the seller brief."""
    context = " ".join(part for part in [description, query] if part).strip()
    if not context:
        return []

    if field == "categories":
        prompt = (
            "You help a B2B seller describe what they sell.\n"
            "From the business brief below, invent 5-8 short product CATEGORY labels "
            "a salesperson would use (not SKU names).\n"
            "Rules:\n"
            "- Infer freely from the text — do NOT limit yourself to any fixed industry list.\n"
            "- Prefer concrete retail/wholesale categories (e.g. Greeting Cards, Hydraulic Valves).\n"
            "- If they sell gifts/cards, say so — never invent industrial/OEM categories.\n"
            "- If a website catalog hint is given, stay consistent with it.\n"
            "- Return ONLY JSON: {\"suggestions\": [\"...\"]}\n\n"
            f"Brief:\n{context[:2500]}\n"
            f"Catalog hints: {', '.join(catalog) or 'none'}"
        )
        parsed = _llm_json(provider, prompt)
        if parsed:
            return parsed

    if field == "buyers":
        prompt = (
            "You help a B2B seller name who buys from them.\n"
            "From the brief, return 5-8 short buyer-type labels "
            "(e.g. Gift retailers, Corporate HR buyers, Hospital groups).\n"
            "Infer freely — no fixed industry list. Return ONLY JSON "
            "{\"suggestions\": [\"...\"]}\n\n"
            f"Brief:\n{context[:2500]}"
        )
        parsed = _llm_json(provider, prompt)
        if parsed:
            return parsed

    if field == "markets":
        prompt = (
            "From the brief, return 5-8 target countries or regions the seller sells into.\n"
            "Use common country names. Return ONLY JSON {\"suggestions\": [\"...\"]}\n\n"
            f"Brief:\n{context[:2500]}"
        )
        parsed = _llm_json(provider, prompt)
        if parsed:
            return parsed

    if field == "discover":
        prompt = (
            "Write 4-6 one-sentence B2B lead-hunt queries tailored to this seller.\n"
            "Return ONLY JSON {\"suggestions\": [\"...\"]}\n\n"
            f"Brief:\n{context[:2500]}\n"
            f"Catalog: {', '.join(catalog) or 'their products'}"
        )
        parsed = _llm_json(provider, prompt)
        if parsed:
            return parsed

    # Legacy path: profile extraction (often weak if name missing)
    if field in {"categories", "markets"}:
        profile = await provider.extract_business_profile(context)
        if field == "categories":
            return list(profile.get("primary_categories") or profile.get("primaryCategories") or [])[:8]
        return list(profile.get("target_markets") or profile.get("targetMarkets") or [])[:8]

    if field == "buyers":
        return await _ai_buyers_via_fallback(FallbackProvider(), context)

    return []


def _llm_json(provider, prompt: str) -> List[str]:
    raw = ""
    try:
        if hasattr(provider, "_complete") and getattr(provider, "available", False):
            raw = provider._complete(prompt)
        elif hasattr(provider, "_generate") and getattr(provider, "available", False):
            raw = provider._generate(prompt)
        elif hasattr(provider, "_chat_json"):
            # rare path
            return []
    except Exception:
        return []
    data = parse_json_payload(raw)
    if isinstance(data, dict) and isinstance(data.get("suggestions"), list):
        return [str(s).strip() for s in data["suggestions"] if str(s).strip()][:8]
    if isinstance(data, list):
        return [str(s).strip() for s in data if str(s).strip()][:8]
    return []


async def _ai_buyers_via_fallback(_fallback: FallbackProvider, context: str) -> List[str]:
    text = context.lower()
    pairs = [
        (["gift", "greeting", "stationery", "mug", "notebook"], ["Gift retailers", "Corporate buyers", "E-commerce sellers", "Wholesalers"]),
        (["gym", "fitness", "sport"], ["Gyms & fitness clubs", "Sports retailers", "Fitness brands"]),
        (["food", "restaurant", "beverage"], ["Restaurants & cafes", "Grocery chains", "Food distributors"]),
        (["saas", "software", "cloud"], ["Mid-market companies", "Enterprises", "IT teams"]),
        (["medical", "hospital", "clinic"], ["Hospitals", "Clinics", "Medical distributors"]),
        (["industrial", "oem", "machinery", "valve"], ["Manufacturers", "OEMs", "Engineering firms"]),
        (["beauty", "cosmetic", "salon"], ["Salons & spas", "Retailers", "Beauty distributors"]),
        (["construction", "building"], ["Contractors", "Developers", "Facility managers"]),
        (["logistic", "freight", "warehouse"], ["Importers & exporters", "E-commerce brands", "Manufacturers"]),
    ]
    for keys, buyers in pairs:
        if any(k in text for k in keys):
            return buyers
    return ["Distributors", "Wholesalers", "Retailers", "Corporate buyers"]


def _local_suggestions(field: str, context: str) -> List[str]:
    text = (context or "").lower()
    packs = [
        (
            ["gift", "gifting", "greeting", "stationery", "mug", "notebook", "souvenir", "personalized", "personalised", "gift basket", "corporate gift"],
            {
                "categories": [
                    "Greeting Cards",
                    "Personalized Gifts",
                    "Gift Baskets",
                    "Mugs & Drinkware",
                    "Wall Art & Frames",
                    "Stationery",
                    "Corporate Gifts",
                ],
                "buyers": ["Gift retailers", "Corporate buyers", "E-commerce sellers", "Wholesalers"],
                "markets": ["Pakistan", "United Kingdom", "United Arab Emirates", "United States", "India"],
                "discover": [
                    "Find gift retailers expanding personalized product lines",
                    "Find corporate buyers sourcing greeting cards and gift baskets",
                ],
            },
        ),
        (
            ["gym", "fitness", "sport", "glove", "hoodie"],
            {
                "categories": ["Sportswear", "Fitness & Bodybuilding", "Gloves", "Teamwear"],
                "buyers": ["Gyms & fitness clubs", "Sports retailers", "Distributors"],
                "markets": ["United Arab Emirates", "Saudi Arabia", "United States", "United Kingdom"],
                "discover": [
                    "Find sportswear distributors expanding in the GCC",
                    "Find commercial gyms opening new locations",
                ],
            },
        ),
        (
            ["industrial", "valve", "oem", "machinery", "cnc", "hydraulic", "factory"],
            {
                "categories": ["Industrial Equipment", "OEM Components", "Machinery Parts"],
                "buyers": ["Manufacturers", "OEMs", "Engineering firms", "Distributors"],
                "markets": ["Germany", "United States", "Netherlands", "United Arab Emirates"],
                "discover": [
                    "Find industrial distributors stocking OEM components in Europe",
                    "Find manufacturers expanding production capacity",
                ],
            },
        ),
        (
            ["food", "restaurant", "beverage", "fmcg"],
            {
                "categories": ["Food Ingredients", "Packaged Foods", "Beverages"],
                "buyers": ["Restaurants & cafes", "Grocery chains", "Food distributors"],
                "markets": ["United Arab Emirates", "United Kingdom", "Singapore"],
                "discover": [
                    "Find food importers expanding grocery assortments in the GCC",
                    "Find restaurant groups seeking ingredient suppliers",
                ],
            },
        ),
        (
            ["saas", "software", "cloud", "crm"],
            {
                "categories": ["SaaS", "B2B Software", "Automation"],
                "buyers": ["Mid-market companies", "Enterprises", "IT teams"],
                "markets": ["United States", "United Kingdom", "Germany", "Canada"],
                "discover": [
                    "Find mid-market companies needing workflow automation",
                    "Find agencies looking for white-label SaaS tools",
                ],
            },
        ),
        (
            ["beauty", "cosmetic", "skincare", "salon"],
            {
                "categories": ["Skincare", "Cosmetics", "Personal Care", "Salon Products"],
                "buyers": ["Salons & spas", "Retailers", "Beauty distributors"],
                "markets": ["United Arab Emirates", "United Kingdom", "United States", "France"],
                "discover": [
                    "Find salon chains seeking product suppliers",
                    "Find beauty retailers expanding private-label lines",
                ],
            },
        ),
    ]
    for keys, data in packs:
        if any(k in text for k in keys):
            return list(data.get(field, data.get("categories", [])))

    defaults = {
        "categories": ["Consumer Goods", "Private Label", "Wholesale", "Export Goods"],
        "buyers": ["Distributors", "Wholesalers", "Retailers", "Importers"],
        "markets": ["United States", "United Kingdom", "United Arab Emirates", "Germany", "India"],
        "discover": [
            "Find distributors expanding in my target markets",
            "Find retailers launching private-label lines in my category",
            "Find companies that recently raised funding and match my ICP",
        ],
    }
    return list(defaults.get(field, defaults["categories"]))


def _unique(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out
