"""
Light AI / taxonomy suggestion expansion.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional

from app.api.deps import AuthUser, get_current_user
from app.providers.factory import get_ai_provider
from app.providers.fallback import FallbackProvider

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


class ExpandRequest(BaseModel):
    field: str  # categories | buyers | markets | discover
    query: str = ""
    description: str = ""
    catalogCategories: List[str] = []


@router.post("/expand")
async def expand_suggestions(req: ExpandRequest, _user: AuthUser = Depends(get_current_user)):
    field = (req.field or "categories").strip().lower()
    context = " ".join(
        part for part in [req.query, req.description, ", ".join(req.catalogCategories)] if part
    ).strip()

    # Fast local path when the user typed almost nothing
    local = _local_suggestions(field, context)
    if not context or len(context) < 3:
        return {"suggestions": local, "source": "taxonomy"}

    provider = get_ai_provider()
    try:
        suggestions = await _ai_expand(provider, field, context, req.catalogCategories)
        if suggestions:
            # Prefer AI, then fill remaining slots from taxonomy
            merged = _unique(suggestions + local)[:8]
            return {"suggestions": merged, "source": "ai"}
    except Exception:
        pass

    return {"suggestions": local[:8], "source": "taxonomy"}


async def _ai_expand(provider, field: str, context: str, catalog: List[str]) -> List[str]:
    """Ask the active AI provider for short suggestion labels; fall back gracefully."""
    fallback = FallbackProvider()
    prompt_field = {
        "categories": "product categories the seller offers",
        "buyers": "ideal buyer / customer types",
        "markets": "target countries or regions",
        "discover": "full discovery search queries (one sentence each)",
    }.get(field, "suggestions")

    # Prefer provider-specific freeform if available via extract_business_profile style
    # Use a tiny dedicated prompt through the same JSON helpers where possible.
    if hasattr(provider, "_chat_json"):
        system = (
            "You help B2B sellers fill targeting fields. "
            "Return ONLY a JSON object {\"suggestions\": [\"...\"]} with 5-8 short phrases. "
            "No gym bias — infer industry from the user context."
        )
        user = (
            f"Field: {prompt_field}\n"
            f"Context: {context}\n"
            f"Catalog categories already known: {', '.join(catalog) or 'none'}\n"
            "Return industry-appropriate suggestions only."
        )
        data = await provider._chat_json(system, user)  # type: ignore[attr-defined]
        if isinstance(data, dict) and isinstance(data.get("suggestions"), list):
            return [str(s).strip() for s in data["suggestions"] if str(s).strip()][:8]

    # Generic path: reuse business profile extraction for categories/markets
    if field in {"categories", "markets", "buyers"}:
        profile = await provider.extract_business_profile(context)
        if field == "categories":
            return list(profile.get("primary_categories") or profile.get("primaryCategories") or [])[:8]
        if field == "markets":
            return list(profile.get("target_markets") or profile.get("targetMarkets") or [])[:8]
        if field == "buyers":
            # Fallback provider won't have buyers; use taxonomy-ish from description
            return await _ai_buyers_via_fallback(fallback, context)

    if field == "discover":
        cats = ", ".join(catalog) if catalog else "their products"
        return [
            f"Find distributors expanding in markets that buy {cats}",
            f"Find retailers launching private-label lines related to {cats}",
            f"Find companies hiring buyers or expanding facilities that need {cats}",
        ]

    return []


async def _ai_buyers_via_fallback(_fallback: FallbackProvider, context: str) -> List[str]:
    text = context.lower()
    pairs = [
        (["gym", "fitness", "sport"], ["Gyms & fitness clubs", "Sports retailers", "Fitness brands"]),
        (["food", "restaurant", "beverage"], ["Restaurants & cafes", "Grocery chains", "Food distributors"]),
        (["saas", "software", "cloud"], ["Mid-market companies", "Enterprises", "IT teams"]),
        (["medical", "hospital", "clinic"], ["Hospitals", "Clinics", "Medical distributors"]),
        (["industrial", "manufactur", "oem"], ["Manufacturers", "OEMs", "Engineering firms"]),
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
            ["industrial", "valve", "manufactur", "oem", "machinery"],
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
