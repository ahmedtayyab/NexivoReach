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
    graded = website_relevance(
        product=product,
        buyer_type=buyer_type,
        company_name=company_name,
        title=title,
        snippet=snippet,
        site_text=site_text,
        categories=categories,
    )
    level = graded.get("level") or "irrelevant"
    if level == "irrelevant":
        return {
            "relevant": False,
            "confidence": float(graded.get("confidence") or 0.8),
            "reason": str(graded.get("reason") or "Not relevant."),
            "level": level,
        }
    return {
        "relevant": True,
        "confidence": float(graded.get("confidence") or 0.55),
        "reason": str(graded.get("reason") or "Relevant."),
        "level": level,
        "evidence": graded.get("evidence") or "",
    }


B2B_SIGNAL_RE = re.compile(
    r"\b("
    r"wholesale|wholesaler|wholesalers|distributor|distributors|distribution|"
    r"dealer|dealers|importer|importers|b2b|bulk\s*orders?|trade\s*only|"
    r"wholesale\s*program|become\s+a\s+(?:dealer|distributor)|for\s+retailers|"
    r"stockist|reseller|dealer\s+network|distribute\s+to"
    r")\b",
    re.I,
)
RETAIL_SIGNAL_RE = re.compile(
    r"\b(add\s+to\s+cart|buy\s+now|shop\s+now|free\s+shipping|your\s+cart|"
    r"checkout|retail\s+price|customer\s+reviews?)\b",
    re.I,
)
CHANNEL_BUYERS = {"distributor", "distributors", "wholesaler", "wholesalers", "importer", "importers", "dealer", "dealers"}


def website_relevance(
    *,
    product: str,
    buyer_type: str,
    company_name: str,
    title: str,
    snippet: str,
    site_text: str,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Stage-2 relevance after website inspection.
    Levels: high | medium | low | irrelevant
    Email is NOT part of this decision.
    """
    cats = list(categories or [])
    if product and product not in cats:
        cats = [product, *cats]
    blob = f"{company_name}\n{title}\n{snippet}\n{site_text or ''}"
    role = (buyer_type or "").strip().lower().rstrip("s")
    role_hit = bool(role and re.search(rf"\b{re.escape(role)}s?\b", blob, re.I))
    b2b = bool(B2B_SIGNAL_RE.search(blob))
    retail = bool(RETAIL_SIGNAL_RE.search(blob))
    channel_hunt = (buyer_type or "").strip().lower() in CHANNEL_BUYERS or role in {
        "distributor", "wholesaler", "importer", "dealer",
    }

    if looks_unrelated_business(blob, cats):
        return {
            "level": "irrelevant",
            "relevant": False,
            "confidence": 0.88,
            "reason": "Unrelated industry (jewelry, medical, industrial, etc.).",
            "evidence": "",
        }
    offer = page_matches_specific_products(blob, cats) if cats else "unknown"
    if offer == "low":
        return {
            "level": "irrelevant",
            "relevant": False,
            "confidence": 0.85,
            "reason": "Wrong-industry product collision (cargo straps, crane hooks, etc.).",
            "evidence": "",
        }

    product_label = product or (cats[0] if cats else "product")
    if offer in ("high", "medium") and b2b:
        return {
            "level": "high",
            "relevant": True,
            "confidence": 0.88 if offer == "high" else 0.78,
            "reason": f"Lists “{product_label}” with wholesale/distributor signals.",
            "evidence": f"Product match={offer}; B2B language present.",
        }
    if offer in ("high", "medium") and role_hit:
        return {
            "level": "high" if offer == "high" else "medium",
            "relevant": True,
            "confidence": 0.8 if offer == "high" else 0.68,
            "reason": f"Product overlap and buyer-type language (“{role}”).",
            "evidence": f"Product match={offer}; role mention.",
        }
    if offer in ("high", "medium") and channel_hunt and retail and not b2b:
        return {
            "level": "low",
            "relevant": True,
            "confidence": 0.5,
            "reason": f"Sells “{product_label}” but looks retail-only (no wholesale/B2B evidence).",
            "evidence": "Retail checkout signals; no B2B language.",
        }
    if offer in ("high", "medium"):
        return {
            "level": "medium",
            "relevant": True,
            "confidence": 0.7 if offer == "high" else 0.6,
            "reason": f"Website overlaps hunt product “{product_label}”.",
            "evidence": f"Product match={offer}.",
        }
    if has_related_trade_context(blob, cats) and b2b:
        return {
            "level": "medium",
            "relevant": True,
            "confidence": 0.68 if role_hit else 0.6,
            "reason": "Fitness/sports trade context with wholesale/distributor signals.",
            "evidence": "Related trade + B2B.",
        }
    if has_related_trade_context(blob, cats):
        return {
            "level": "low",
            "relevant": True,
            "confidence": 0.52,
            "reason": "Sports/fitness trade context; exact SKU not confirmed on inspected pages.",
            "evidence": "Related trade context.",
        }
    # Site fetched but thin — still keep if Google returned it for the exact query
    if (snippet or title) and (site_text or "").strip():
        return {
            "level": "low",
            "relevant": True,
            "confidence": 0.4,
            "reason": "Thin site evidence; kept because Google returned it for this hunt query.",
            "evidence": "SERP match; weak page text.",
        }
    if snippet or title:
        return {
            "level": "low",
            "relevant": True,
            "confidence": 0.38,
            "reason": "Could not load useful page text; SERP still matched the hunt query.",
            "evidence": "SERP-only.",
        }
    return {
        "level": "irrelevant",
        "relevant": False,
        "confidence": 0.55,
        "reason": "No usable site or SERP evidence of commercial relevance.",
        "evidence": "",
    }


def serp_triage(
    row: Dict[str, Any],
    *,
    categories: Optional[List[str]] = None,
    buyers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Trust Google organic results. Only drop clearly wrong industries.
    Everything else that survived the junk-host filter is kept as a lead.
    """
    cats = list(categories or [])
    name = (row.get("company_name") or "").strip()
    title = (row.get("title") or "").strip()
    snippet = (row.get("snippet") or "").strip()
    dq = (row.get("discovery_query") or "").strip()
    product, role, _place = parse_discovery_query(dq)
    if product and product not in cats:
        cats = [product, *cats]

    blob = f"{name}\n{title}\n{snippet}"
    # Hard rejects only — keyword "smarts" were not beating Google and still let junk through
    if looks_unrelated_business(blob, cats):
        return {
            "verdict": "reject",
            "confidence": 0.9,
            "reason": "Obviously unrelated industry (jewelry, medical, real estate…).",
        }
    offer = page_matches_specific_products(blob, cats) if cats else "unknown"
    if offer == "low":
        return {
            "verdict": "reject",
            "confidence": 0.85,
            "reason": "Wrong industry product collision (cargo straps, crane/rigging hooks…).",
        }
    # Default: keep — this company appeared in Google for the exact hunt query
    conf = 0.55
    reason = "Google organic result for this exact product×buyer search."
    if offer in ("high", "medium"):
        conf = 0.8 if offer == "high" else 0.65
        reason = f"SERP matches hunt product “{product or (cats[0] if cats else 'product')}”."
    elif has_related_trade_context(blob, cats):
        conf = 0.7
        reason = "Fitness/sports trade language in Google result."
    return {
        "verdict": "keep",
        "confidence": conf,
        "reason": reason,
    }


def qualify_from_fast_decision(
    *,
    row: Dict[str, Any],
    profile: SellerProfile,
    products: List[Dict[str, Any]],
    triage: Dict[str, Any],
    site_text: str = "",
) -> Dict[str, Any]:
    """Build a qualify-shaped result from SERP triage (or a quick homepage heuristic)."""
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
    url = row.get("website") or ""
    location = _resolve_location(row, site_text, profile)
    dq = (row.get("discovery_query") or "")
    product, role, _place = parse_discovery_query(dq)
    if not product:
        product = (profile.categories[0] if profile.categories else "") or ""
    if not role:
        role = (profile.buyers[0] if profile.buyers else "distributors") or "distributors"

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
            "whyThisProspect": f"{name}: skipped — address conflicts with hunt location.",
            "whyNow": "No timing evidence.",
            "fitScore": 20,
            "fitBreakdown": {
                "aiRelevant": False,
                "aiReason": "Contradictory location.",
                "discoveryQuery": dq,
                "huntProduct": product,
                "huntBuyerType": role,
                "huntMatches": _hunt_matches(row),
                "triage": triage.get("verdict"),
            },
            "buyingSignals": [],
            "productFit": [],
            "shouldPersist": False,
            "recommendedApproach": "Do not contact — wrong geography.",
            "location": location,
            "industry": _industry_label(f"{name}\n{snippet}", profile),
        }

    # If we fetched a page, score high/medium/low/irrelevant from site content
    if site_text.strip():
        graded = website_relevance(
            product=product,
            buyer_type=role,
            company_name=name,
            title=title,
            snippet=snippet,
            site_text=site_text,
            categories=list(profile.categories or []),
        )
        relevant = bool(graded.get("relevant"))
        conf = float(graded.get("confidence") or 0.5)
        reason = str(graded.get("reason") or "")
        level = str(graded.get("level") or ("medium" if relevant else "irrelevant"))
        evidence_note = str(graded.get("evidence") or "")
    else:
        relevant = triage.get("verdict") == "keep"
        conf = float(triage.get("confidence") or 0.5)
        reason = str(triage.get("reason") or "")
        level = "medium" if relevant else "irrelevant"
        evidence_note = ""

    if not relevant:
        return {
            "icpFit": "low",
            "offerFit": "low",
            "motionFit": "unknown",
            "fitSummary": "low",
            "intent": "none",
            "confidence": round(conf, 2),
            "priority": "reject",
            "evidence": [],
            "whyThisProspect": f"{name}: {reason}",
            "whyNow": "No timing evidence.",
            "fitScore": 25,
            "fitBreakdown": {
                "aiRelevant": False,
                "aiReason": reason,
                "relevance": level if site_text.strip() else "irrelevant",
                "discoveryQuery": dq,
                "huntProduct": product,
                "huntBuyerType": role,
                "huntMatches": _hunt_matches(row),
                "matchedSearchIntents": list(row.get("discovery_queries") or ([dq] if dq else [])),
                "triage": triage.get("verdict"),
            },
            "buyingSignals": [],
            "productFit": [],
            "shouldPersist": False,
            "recommendedApproach": "Not a fit.",
            "location": location,
            "industry": _industry_label(f"{name}\n{snippet}\n{site_text}", profile),
        }

    offer = level if level in ("high", "medium", "low") else ("high" if conf >= 0.7 else "medium")
    icp = "high" if level == "high" else ("medium" if level == "medium" else "low")
    fit_summary = offer
    priority = "priority" if level == "high" else ("nurture" if level == "medium" else "review")
    text = f"{name}\n{snippet}\n{site_text or ''}"
    intents = [
        q for q in list(row.get("discovery_queries") or [])
        if (q or "").strip()
    ]
    if dq and dq not in intents:
        intents.insert(0, dq)
    evidence = [{
        "claim": "offer",
        "statement": reason,
        "quote": (evidence_note or reason)[:160],
        "url": url,
        "sourceType": "homepage" if site_text else "serp",
        "confidence": conf,
    }]
    score = _fit_score_only(
        icp=icp,
        offer="high" if offer == "high" else ("medium" if offer == "medium" else "low"),
        motion="unknown",
        location=location,
        profile=profile,
        source_type="homepage" if site_text else "serp",
        evidence_count=1,
        site_text=site_text or "",
        seed_key=f"{name}|{url}",
    )
    return {
        "icpFit": icp,
        "offerFit": offer,
        "motionFit": "unknown",
        "fitSummary": fit_summary,
        "intent": "none",
        "confidence": round(conf, 2),
        "priority": priority,
        "evidence": evidence,
        "whyThisProspect": f"{name}: {reason}" if reason else f"{name}: Fast SERP match.",
        "whyNow": "No timing evidence; treat as a fit-based account, not a hot inbound.",
        "fitScore": score["total_score"],
        "fitBreakdown": {
            **score["breakdown"],
            "icpFit": icp,
            "offerFit": offer,
            "motionFit": "unknown",
            "fitSummary": fit_summary,
            "intent": "none",
            "confidence": round(conf, 2),
            "priority": priority,
            "relevance": level,
            "entityType": row.get("entity_type") or "company",
            "discoveryPool": row.get("discovery_pool") or "",
            "discoveryQuery": dq,
            "huntProduct": _hunt_product_label(text, profile, dq) or product,
            "huntBuyerType": _hunt_buyer_label(text, profile, dq) or role,
            "huntMatches": _hunt_matches(row),
            "matchedSearchIntents": intents[:12],
            "aiRelevant": True,
            "aiReason": reason,
            "triage": triage.get("verdict") or "keep",
            "evidence": evidence,
        },
        "buyingSignals": [],
        "productFit": offer_ev_as_matches(
            "high" if offer == "high" else ("medium" if offer == "medium" else "low"),
            products,
            text,
            name,
        ),
        "shouldPersist": True,
        "recommendedApproach": _approach(profile, name, fit_summary, "none"),
        "location": location,
        "industry": _industry_label(text, profile),
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
