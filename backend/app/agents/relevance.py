"""AI business-relevance check for hunt leads (search literally, qualify intelligently)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.agents.geo import (
    has_related_trade_context,
    location_conflicts_with_targets,
    looks_unrelated_business,
    page_matches_specific_products,
    parse_discovery_query,
)
from app.agents.search_planner import SellerProfile
from app.providers.base import AIProvider


RELEVANCE_PROMPT = """You are qualifying B2B export leads.

A human searched Google for a specific product + buyer type + location.
Your job: decide whether this company is a legitimate potential lead for that exact search intent.

Would it make commercial sense for a company exporting this specific product to contact this business as a potential buyer/distributor/wholesaler/importer?

Rules:
- Search used the exact product phrase. Do NOT broaden the product yourself.
- The company need NOT list the exact product SKU on the homepage. A fitness/sports/gym equipment distributor is often relevant for weightlifting accessories (straps, belts, wraps, sleeves, lifting hooks, martial arts belts).
- Reject clearly unrelated industries (jewelry, medical/dental, automotive, construction, restaurants, real estate, industrial crane/rigging hardware, cargo/truck straps, etc.) when they are not also a sports/fitness business.
- Industrial "lifting hooks" / rigging / crane / shackles are NOT fitness lifting hooks.
- Missing location on the website is NOT a reason to reject — Google already applied the place to the search. Only reject for a clear contradictory address in a different city/region when that conflicts with the hunt location.
- Keep the answer simple. Do not score sales potential or invent ICP dimensions.

Return ONLY JSON:
{{"relevant": true|false, "confidence": 0.0-1.0, "reason": "one short sentence"}}

Seller / exporter context (helps interpret the product category; do not replace the search):
{seller_brief}

Search intent:
- Product: {product}
- Buyer type: {buyer_type}
- Location: {location}
- Search query: {search_query}

Company:
- Name: {company_name}
- SERP title: {title}
- SERP snippet: {snippet}
- Website: {website}

Website text (homepage and any catalog excerpt):
{site_text}
"""


def _normalize_ai_result(parsed: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(parsed, dict):
        return None
    if "relevant" not in parsed:
        return None
    relevant = parsed.get("relevant")
    if isinstance(relevant, str):
        relevant = relevant.strip().lower() in ("true", "yes", "1")
    else:
        relevant = bool(relevant)
    try:
        confidence = float(parsed.get("confidence") if parsed.get("confidence") is not None else 0.5)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    reason = str(parsed.get("reason") or "").strip()[:280]
    return {"relevant": relevant, "confidence": confidence, "reason": reason or ("Relevant." if relevant else "Not relevant.")}


def heuristic_relevance(
    *,
    product: str,
    buyer_type: str,
    location: str,
    company_name: str,
    title: str,
    snippet: str,
    site_text: str,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Cheap fallback when no LLM is configured — still softer than the old pipeline."""
    cats = list(categories or [])
    if product and product not in cats:
        cats = [product, *cats]
    blob = f"{company_name}\n{title}\n{snippet}\n{site_text or ''}"
    if looks_unrelated_business(blob, cats):
        return {
            "relevant": False,
            "confidence": 0.85,
            "reason": "Appears to be an unrelated industry (jewelry, medical, industrial, etc.).",
        }
    offer = page_matches_specific_products(blob, cats) if cats else "unknown"
    if offer == "low":
        return {
            "relevant": False,
            "confidence": 0.8,
            "reason": "Product mention looks like a different industry (e.g. cargo straps or crane hooks).",
        }
    if offer in ("high", "medium"):
        return {
            "relevant": True,
            "confidence": 0.75 if offer == "high" else 0.6,
            "reason": f"Site overlaps hunt product “{product or cats[0]}”.",
        }
    if has_related_trade_context(blob, cats):
        role = (buyer_type or "").rstrip("s")
        role_hit = bool(role and re.search(rf"\b{re.escape(role)}s?\b", blob, re.I))
        return {
            "relevant": True,
            "confidence": 0.65 if role_hit else 0.55,
            "reason": "Sports/fitness/gym trade context; exact SKU not required on homepage.",
        }
    # Thin evidence — keep for human review when SERP already matched the query
    if snippet or title:
        return {
            "relevant": True,
            "confidence": 0.4,
            "reason": "Thin site text; kept because Google returned it for the exact hunt query.",
        }
    return {
        "relevant": False,
        "confidence": 0.55,
        "reason": "No usable site or SERP evidence of commercial relevance.",
    }


async def ask_relevance(
    provider: AIProvider,
    *,
    product: str,
    buyer_type: str,
    location: str,
    search_query: str,
    company_name: str,
    title: str = "",
    snippet: str = "",
    website: str = "",
    site_text: str = "",
    seller_brief: str = "",
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    try:
        result = await provider.qualify_business_relevance(
            product=product,
            buyer_type=buyer_type,
            location=location,
            search_query=search_query,
            company_name=company_name,
            title=title,
            snippet=snippet,
            website=website,
            site_text=(site_text or "")[:6000],
            seller_brief=(seller_brief or "")[:1200],
        )
        normalized = _normalize_ai_result(result)
        if normalized:
            return normalized
    except Exception:
        pass
    return heuristic_relevance(
        product=product,
        buyer_type=buyer_type,
        location=location,
        company_name=company_name,
        title=title,
        snippet=snippet,
        site_text=site_text,
        categories=categories,
    )


def _geo_contradicts(location: str, places: List[str], site_text: str, row: Dict[str, Any]) -> bool:
    """Reject only when we have an explicit address that conflicts with the hunt place."""
    if not places:
        return False
    loc = (location or row.get("location") or "").strip()
    if loc and location_conflicts_with_targets(loc, places):
        return True
    return False


async def qualify_account_with_ai(
    *,
    row: Dict[str, Any],
    site_text: str,
    profile: SellerProfile,
    products: List[Dict[str, Any]],
    page_url: str = "",
    provider: AIProvider,
    seller_brief: str = "",
) -> Dict[str, Any]:
    """
    AI-first qualification. Regex is only used for contradictory geo and as LLM fallback.
    """
    from app.agents.qualify import (
        _approach,
        _fit_score_only,
        _hunt_buyer_label,
        _hunt_matches,
        _hunt_product_label,
        _industry_label,
        _resolve_location,
        offer_ev_as_matches,
    )

    name = row.get("company_name") or "This company"
    snippet = row.get("snippet") or ""
    title = row.get("title") or ""
    url = page_url or (row.get("website") or "")
    location = _resolve_location(row, site_text, profile)
    dq = (row.get("discovery_query") or "")
    product, role, _place = parse_discovery_query(dq)
    if not product:
        product = (profile.categories[0] if profile.categories else "") or ""
    if not role:
        role = (profile.buyers[0] if profile.buyers else "distributors") or "distributors"

    # Soft geo: only reject when address clearly contradicts the hunt place.
    if _geo_contradicts(location, list(profile.places or []), site_text or "", row):
        return {
            "icpFit": "low",
            "offerFit": "low",
            "motionFit": "unknown",
            "fitSummary": "low",
            "intent": "none",
            "confidence": 0.8,
            "priority": "reject",
            "evidence": [],
            "whyThisProspect": (
                f"{name}: skipped — address conflicts with "
                f"{', '.join((profile.places or [])[:2])}."
            ),
            "whyNow": "No timing evidence.",
            "fitScore": 20,
            "fitBreakdown": {
                "icpFit": "low",
                "offerFit": "low",
                "motionFit": "unknown",
                "fitSummary": "low",
                "intent": "none",
                "confidence": 0.8,
                "priority": "reject",
                "entityType": row.get("entity_type") or "company",
                "discoveryPool": row.get("discovery_pool") or "",
                "discoveryQuery": dq,
                "huntProduct": product,
                "huntBuyerType": role,
                "huntMatches": _hunt_matches(row),
                "aiRelevant": False,
                "aiReason": "Contradictory location vs hunt place.",
                "evidence": [],
            },
            "buyingSignals": [],
            "productFit": [],
            "shouldPersist": False,
            "recommendedApproach": "Do not contact — wrong geography.",
            "location": location,
            "industry": _industry_label(f"{name}\n{snippet}\n{site_text}", profile),
        }

    brief = seller_brief
    if not brief and products:
        bits = [str(p.get("name") or "") for p in products[:8] if p.get("name")]
        brief = "Seller catalog: " + ", ".join(bits)

    ai = await ask_relevance(
        provider,
        product=product,
        buyer_type=role,
        location=(profile.places[0] if profile.places else "") or "",
        search_query=dq or f"{product} {role}",
        company_name=name,
        title=title,
        snippet=snippet,
        website=url,
        site_text=site_text or "",
        seller_brief=brief,
        categories=list(profile.categories or []),
    )

    relevant = bool(ai.get("relevant"))
    conf = float(ai.get("confidence") or 0.5)
    reason = str(ai.get("reason") or "")

    if not relevant:
        fit_summary = "low"
        priority = "reject"
        persist = False
        offer = "low"
        icp = "low"
    else:
        offer = "high" if conf >= 0.7 else "medium"
        icp = "high" if conf >= 0.65 else "medium"
        fit_summary = "high" if conf >= 0.7 else "medium"
        priority = "nurture" if conf >= 0.7 else "review"
        persist = True

    evidence = [{
        "claim": "offer",
        "statement": reason,
        "quote": reason[:160],
        "url": url,
        "sourceType": "ai" if site_text else "serp",
        "confidence": conf,
    }]
    text = f"{name}\n{snippet}\n{site_text or ''}"
    score = _fit_score_only(
        icp=icp,
        offer=offer,
        motion="unknown",
        location=location,
        profile=profile,
        source_type="homepage" if site_text else "serp",
        evidence_count=1 if relevant else 0,
        site_text=site_text or "",
        seed_key=f"{name}|{url}",
    )
    why = f"{name}: {reason}" if reason else f"{name}: AI relevance check."
    return {
        "icpFit": icp,
        "offerFit": offer,
        "motionFit": "unknown",
        "fitSummary": fit_summary,
        "intent": "none",
        "confidence": round(conf, 2),
        "priority": priority,
        "evidence": evidence,
        "whyThisProspect": why,
        "whyNow": "No timing evidence; treat as a fit-based account, not a hot inbound.",
        "fitScore": score["total_score"] if relevant else min(35, score["total_score"]),
        "fitBreakdown": {
            **score["breakdown"],
            "icpFit": icp,
            "offerFit": offer,
            "motionFit": "unknown",
            "fitSummary": fit_summary,
            "intent": "none",
            "confidence": round(conf, 2),
            "priority": priority,
            "entityType": row.get("entity_type") or "company",
            "discoveryPool": row.get("discovery_pool") or row.get("pool") or "",
            "discoveryQuery": dq,
            "huntProduct": _hunt_product_label(text, profile, dq) or product,
            "huntBuyerType": _hunt_buyer_label(text, profile, dq) or role,
            "huntMatches": _hunt_matches(row),
            "aiRelevant": relevant,
            "aiReason": reason,
            "whyNow": "No timing evidence; treat as a fit-based account, not a hot inbound.",
            "evidence": evidence,
        },
        "buyingSignals": [],
        "productFit": offer_ev_as_matches(offer, products, text, name),
        "shouldPersist": persist,
        "recommendedApproach": _approach(profile, name, fit_summary, "none"),
        "location": location,
        "industry": _industry_label(text, profile),
    }
