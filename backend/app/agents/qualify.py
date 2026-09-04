"""Evidence-backed Fit vs Intent qualification. Does not treat keyword retrieval as intent."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.agents.search_planner import SellerProfile


LEVELS = ("unknown", "low", "medium", "high")
LEVEL_RANK = {k: i for i, k in enumerate(LEVELS)}

MFR_SELF = re.compile(
    r"\b(we (are|'re) (a |an )?(leading )?(manufacturer|factory)|our factory|our manufacturing|oem factory)\b",
    re.I,
)
BUYER_SELF = re.compile(
    r"\b(our brands?|we (design|sell|retail|distribute|import)|private label|wholesale|b2b|for retailers|stockist)\b",
    re.I,
)
MOTION_OEM = re.compile(r"\b(private[\s-]?label|white[\s-]?label|oem|odm|custom (brand|manufactur))\b", re.I)
MOTION_WHOLESALE = re.compile(r"\b(wholesale|bulk order|distributors?|importers?|trade only|b2b portal)\b", re.I)
MOTION_SAAS = re.compile(r"\b(sign in|request a demo|start free|saas|subscription|platform)\b", re.I)

# Intent must be specific. Category words are NOT intent.
INTENT_STRONG = (
    (r"seeking (a )?(manufacturer|supplier|factory)", "Seeking a manufacturer/supplier"),
    (r"looking for (a )?(manufacturer|supplier|oem)", "Looking for a supplier"),
    (r"now sourcing", "Now sourcing"),
    (r"private label program", "Private-label program"),
    (r"new (collection|line|facility|warehouse|store|location|plant) .{0,20}(20\d{2}|this year|upcoming)", "Dated expansion/launch"),
    (r"(opening|opened|launching) .{0,40}(20\d{2}|store|warehouse|facility)", "Opening/launch"),
    (r"\brfp\b|\btender\b|request for (proposal|quote)", "Procurement / RFP"),
    (r"expanding (distribution|into|our (line|range|network))", "Distribution/line expansion"),
)
INTENT_WEAK = (
    (r"we('re| are) hiring (a )?(sourc|procur|buyer|merchandis|category)", "Hiring a buying-side role"),
    (r"new collection\b", "Mentions a new collection (undated)"),
    (r"become a (supplier|vendor)|supplier (registration|portal)|vendor (application|registration)", "Supplier/vendor program"),
    (r"now accepting (new )?(suppliers|vendors|partners)", "Accepting new suppliers"),
)
VANITY_SKIP = re.compile(
    r"\b(cashier|barista|receptionist|we're hiring|we are hiring|award[- ]winning|since \d{4})\b",
    re.I,
)


def _level_min(a: str, b: str) -> str:
    return a if LEVEL_RANK.get(a, 0) <= LEVEL_RANK.get(b, 0) else b


def _excerpt(text: str, pattern: str, span: int = 140) -> str:
    m = re.search(pattern, text or "", re.I)
    if not m:
        return ""
    start = max(0, m.start() - 40)
    end = min(len(text), m.end() + span)
    return re.sub(r"\s+", " ", text[start:end]).strip()[:200]


def _evidence(claim: str, statement: str, quote: str, url: str, source_type: str, confidence: float) -> Dict[str, Any]:
    return {
        "claim": claim,
        "statement": statement,
        "quote": (quote or "")[:200],
        "url": url or "",
        "sourceType": source_type,
        "sourceQuality": "primary_site" if source_type in ("homepage", "about") else source_type,
        "confidence": round(confidence, 2),
    }


def _token_hits(needles: List[str], text: str) -> List[str]:
    blob = (text or "").lower()
    hits = []
    for raw in needles:
        tokens = [t for t in re.split(r"[^a-z0-9]+", (raw or "").lower()) if len(t) > 3]
        if not tokens:
            continue
        if raw.lower() in blob or sum(1 for t in tokens if t in blob) >= min(2, len(tokens)):
            hits.append(raw)
    return hits


def qualify_account(
    *,
    row: Dict[str, Any],
    site_text: str,
    profile: SellerProfile,
    products: List[Dict[str, Any]],
    page_url: str = "",
) -> Dict[str, Any]:
    url = page_url or (row.get("website") or "")
    name = row.get("company_name") or "This company"
    snippet = row.get("snippet") or ""
    location = (row.get("location") or "").strip()
    text = f"{name}\n{snippet}\n{site_text or ''}"
    evidence: List[Dict[str, Any]] = []
    source_type = "homepage" if site_text else "serp"

    icp, icp_ev = _icp_fit(text, snippet, location, profile, url, source_type)
    evidence.extend(icp_ev)
    motion, motion_ev = _motion_fit(text, profile, url, source_type)
    evidence.extend(motion_ev)
    offer, offer_ev = _offer_fit(text, products, profile, url, source_type, site_text)
    evidence.extend(offer_ev)
    intent, intent_ev, why_now = _intent(text, url, source_type, site_text)
    evidence.extend(intent_ev)

    # Fit is not intent. Unknown is not medium.
    if icp == "low" or motion == "low":
        fit_summary = "low"
    elif icp == "unknown" and motion == "unknown":
        fit_summary = "low"
    else:
        # unknown dims pull the summary down toward medium/low, never invent high.
        icp_for_summary = "medium" if icp == "unknown" else icp
        motion_for_summary = "low" if motion == "unknown" else motion
        offer_for_summary = "medium" if offer == "unknown" else offer
        fit_summary = _level_min(icp_for_summary, motion_for_summary)
        if offer_for_summary == "low" and site_text:
            if fit_summary == "high":
                fit_summary = "medium"
            elif fit_summary == "medium":
                fit_summary = "low"

    confidence = 0.28 if not site_text else 0.58
    if evidence:
        confidence = min(0.9, confidence + 0.08 * min(3, len(evidence)))
    if intent == "none":
        # honest: no timing
        pass

    why_this = _why_this(name, icp, offer, motion, evidence, profile)
    if intent == "none":
        why_now = why_now or "No timing evidence; treat as a fit-based account, not a hot inbound."

    if fit_summary == "high" and intent in ("high",):
        priority = "priority"
    elif fit_summary == "high":
        priority = "nurture"
    elif fit_summary == "medium" and intent == "high":
        priority = "review"
    elif fit_summary == "medium" and source_type == "homepage":
        priority = "low"
    else:
        priority = "reject"

    score = _fit_score_only(
        icp=icp,
        offer=offer,
        motion=motion,
        location=location,
        profile=profile,
        source_type=source_type,
        evidence_count=len([e for e in evidence if e.get("claim") in ("icp", "offer", "motion")]),
    )
    persist = (
        priority != "reject"
        and fit_summary != "low"
        and not (source_type == "serp" and icp == "unknown" and motion == "unknown")
    )
    if (
        not persist
        and (row.get("source") == "maps")
        and (row.get("phone") or "")
        and profile.use_maps
        and fit_summary != "low"
        and icp != "low"
        and motion != "low"
    ):
        persist = True
        if priority == "reject":
            priority = "low"
        if not why_this:
            why_this = f"{name} is a local Maps listing matching the ICP buyer type; website evidence is still thin."
    return {
        "icpFit": icp,
        "offerFit": offer,
        "motionFit": motion,
        "fitSummary": fit_summary,
        "intent": intent,
        "confidence": round(confidence, 2),
        "priority": priority,
        "evidence": evidence,
        "whyThisProspect": why_this,
        "whyNow": why_now,
        "fitScore": score["total_score"],
        "fitBreakdown": {
            **score["breakdown"],
            "icpFit": icp,
            "offerFit": offer,
            "motionFit": motion,
            "fitSummary": fit_summary,
            "intent": intent,
            "confidence": round(confidence, 2),
            "priority": priority,
            "entityType": row.get("entity_type") or "company",
            "discoveryPool": row.get("discovery_pool") or row.get("pool") or "",
            "discoveryQuery": row.get("discovery_query") or "",
            "whyNow": why_now,
            "evidence": evidence,
        },
        "buyingSignals": [
            {
                "signal": e["statement"],
                "whyItMatters": e["claim"],
                "sourceUrl": e.get("url") or "",
                "sourceExcerpt": e.get("quote") or "",
            }
            for e in evidence if e.get("claim") == "intent"
        ],
        "productFit": offer_ev_as_matches(offer, products, text, name),
        "shouldPersist": persist,
        "recommendedApproach": _approach(profile, name, fit_summary, intent),
        "location": location,
        "industry": _industry_label(text, profile),
    }


def _icp_fit(
    text: str,
    snippet: str,
    location: str,
    profile: SellerProfile,
    url: str,
    source_type: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    ev = []
    hits = _token_hits(profile.buyers, text)
    geo_ok = _geo_ok(location + " " + text, profile.places)

    if MFR_SELF.search(text) and profile.hunting_buyers:
        quote = _excerpt(text, MFR_SELF.pattern)
        ev.append(_evidence(
            "icp",
            f"Self-describes as a manufacturer; ICP is hunting buyers, not peer factories.",
            quote, url, source_type, 0.75,
        ))
        return "low", ev

    if hits and geo_ok is not False:
        ev.append(_evidence(
            "icp",
            f"Buyer-type language matches ICP ({', '.join(hits[:3])}).",
            _excerpt(text, re.escape(hits[0])) or (snippet[:160] if snippet else ""),
            url, source_type, 0.7 if source_type == "homepage" else 0.4,
        ))
        return ("high" if source_type == "homepage" else "medium"), ev

    if hits and geo_ok is False:
        ev.append(_evidence("icp", "Buyer-type language present but geography does not match ICP markets.", snippet[:160], url, source_type, 0.5))
        return "low", ev

    cat_hits = _token_hits(profile.categories, text)
    if cat_hits and source_type == "homepage":
        ev.append(_evidence("icp", f"Category overlap ({cat_hits[0]}) without a clear buyer-type match.", _excerpt(text, re.escape(cat_hits[0])), url, source_type, 0.45))
        return "medium", ev

    if source_type == "serp":
        return "unknown", ev
    return "low", ev


def _motion_fit(text: str, profile: SellerProfile, url: str, source_type: str) -> Tuple[str, List[Dict[str, Any]]]:
    ev = []
    motion = profile.sales_motion
    if motion == "oem_private_label":
        if MFR_SELF.search(text) and profile.hunting_buyers:
            ev.append(_evidence("motion", "They manufacture; they are unlikely to buy private-label production from you.", _excerpt(text, MFR_SELF.pattern), url, source_type, 0.75))
            return "low", ev
        if MOTION_OEM.search(text) or BUYER_SELF.search(text):
            ev.append(_evidence("motion", "Language consistent with brands/wholesale/private-label buying.", _excerpt(text, MOTION_OEM.pattern) or _excerpt(text, BUYER_SELF.pattern), url, source_type, 0.7))
            return "high" if source_type == "homepage" else "medium", ev
        # No free medium — absence of factory language is not proof they buy OEM.
        return "unknown", ev

    if motion == "wholesale":
        if MOTION_WHOLESALE.search(text) or BUYER_SELF.search(text):
            ev.append(_evidence("motion", "Wholesale/import/distribution language present.", _excerpt(text, MOTION_WHOLESALE.pattern), url, source_type, 0.65))
            return "high" if source_type == "homepage" else "medium", ev
        return "unknown", ev

    if motion == "saas":
        if MOTION_SAAS.search(text):
            ev.append(_evidence("motion", "Software/commercial motion language present.", _excerpt(text, MOTION_SAAS.pattern), url, source_type, 0.6))
            return "medium", ev
        return "unknown", ev

    if motion == "local":
        if source_type == "serp":
            return "unknown", ev
        # Local listings with a phone/address are weak-positive motion only.
        return "medium", ev

    if BUYER_SELF.search(text):
        return "medium", ev
    return "unknown", ev


def _offer_fit(
    text: str,
    products: List[Dict[str, Any]],
    profile: SellerProfile,
    url: str,
    source_type: str,
    site_text: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    ev = []
    if not site_text:
        return "unknown", ev
    # Prefer category tokens over long SKU names full of noise words.
    cats = [c for c in profile.categories if c]
    product_tokens: List[str] = []
    for p in (products or [])[:20]:
        for part in (p.get("name"), p.get("category")):
            if not part:
                continue
            for tok in re.split(r"[^a-zA-Z0-9]+", str(part)):
                t = tok.lower()
                if len(t) >= 4 and t not in {
                    "with", "from", "that", "this", "padded", "training", "quick", "kind",
                }:
                    product_tokens.append(t)
    blob = (text or "").lower()
    cat_hits = _token_hits(cats, text)
    unique_tokens = sorted(set(product_tokens), key=len, reverse=True)
    token_hits = [t for t in unique_tokens[:40] if re.search(rf"\b{re.escape(t)}\b", blob)]
    strong = len(cat_hits) + (1 if len(token_hits) >= 3 else 0) + (1 if len(token_hits) >= 6 else 0)

    if strong >= 2 or (cat_hits and len(token_hits) >= 2):
        label = ", ".join((cat_hits + token_hits)[:4])
        ev.append(_evidence("offer", f"Site text overlaps catalog terms: {label}.", _excerpt(text, re.escape(cat_hits[0] if cat_hits else token_hits[0])), url, source_type, 0.65))
        return "high", ev
    if cat_hits or len(token_hits) >= 2:
        label = cat_hits[0] if cat_hits else token_hits[0]
        ev.append(_evidence("offer", f"Partial catalog overlap ({label}); not proof they buy this SKU.", _excerpt(text, re.escape(label)), url, source_type, 0.45))
        return "medium", ev
    if token_hits:
        ev.append(_evidence("offer", f"Weak catalog token overlap ({token_hits[0]}).", token_hits[0], url, source_type, 0.3))
        return "low", ev
    return "low", ev


def _intent(text: str, url: str, source_type: str, site_text: str) -> Tuple[str, List[Dict[str, Any]], str]:
    """Intent is independent of Fit. SERP category overlap is not intent."""
    if not site_text:
        return "none", [], "No timing evidence; homepage was not inspected or had no dated buying signal."
    if VANITY_SKIP.search(text) and not any(re.search(p, text, re.I) for p, _ in INTENT_STRONG):
        # hiring cashiers etc. is not intent
        pass
    for pattern, label in INTENT_STRONG:
        if re.search(pattern, text, re.I):
            quote = _excerpt(text, pattern)
            ev = [_evidence("intent", label, quote, url, source_type, 0.7)]
            return "high", ev, f"{label}: “{quote}”"
    for pattern, label in INTENT_WEAK:
        if re.search(pattern, text, re.I):
            quote = _excerpt(text, pattern)
            ev = [_evidence("intent", label + " (weak)", quote, url, source_type, 0.4)]
            return "low", ev, f"Weak timing signal ({label}). Confirm before treating as urgent."
    return "none", [], "No timing evidence; treat as a fit-based account, not a hot inbound."


def _geo_ok(blob: str, places: List[str]) -> Optional[bool]:
    if not places:
        return None
    low = blob.lower()
    aliases = {
        "united states": ["usa", "u.s.", "united states", "america"],
        "united kingdom": ["uk", "britain", "england"],
        "united arab emirates": ["uae", "dubai"],
    }
    for place in places:
        p = place.lower().strip()
        if p and p in low:
            return True
        for a in aliases.get(p, []):
            if a in low:
                return True
    # location empty → unknown, not a fail
    if len(low.strip()) < 8:
        return None
    return None


def _why_this(
    name: str,
    icp: str,
    offer: str,
    motion: str,
    evidence: List[Dict[str, Any]],
    profile: SellerProfile,
) -> str:
    bits = [e["statement"] for e in evidence if e.get("claim") in ("icp", "offer", "motion")]
    if bits:
        return f"{name}: " + " ".join(bits[:3])
    return (
        f"{name} was retrieved as a possible {profile.buyers[0] if profile.buyers else 'buyer'} "
        f"for {profile.categories[0]}. Fit is {icp}/{offer}/{motion} (ICP/offer/motion) and still needs evidence."
    )


def _approach(profile: SellerProfile, name: str, fit: str, intent: str) -> str:
    seller_motion = profile.sales_motion.replace("_", " ")
    if fit == "low":
        return "Do not treat as a qualified buyer until ICP/motion evidence improves."
    if intent == "high":
        return f"Lead with the current timing signal. Pitch {seller_motion} supply, not a generic catalog dump."
    return f"Fit-based outreach to {name}: confirm they buy via {seller_motion} before a full pitch. No urgency claimed."


def _industry_label(text: str, profile: SellerProfile) -> str:
    for b in profile.buyers:
        if b.lower() in text.lower():
            return b[:80]
    return (profile.categories[0] if profile.categories else "Company")[:80]


def _fit_score_only(
    icp: str,
    offer: str,
    motion: str,
    location: str,
    profile: SellerProfile,
    source_type: str = "serp",
    evidence_count: int = 0,
) -> Dict[str, Any]:
    """
    Composite Fit score only (Intent excluded).

    Designed to spread scores:
    - SERP-only / thin evidence → usually < 55
    - Homepage with clear ICP+motion → 65–82
    - Strong ICP+offer+motion+geo → 83–95
    Unknown levels score near zero — no free "medium" padding.
    """
    level_pts = {
        "high": (28, 26, 24),      # icp, offer, motion
        "medium": (18, 14, 14),
        "unknown": (4, 2, 2),
        "low": (0, 0, 0),
    }
    icp_pts, offer_pts, motion_pts = (
        level_pts.get(icp, (0, 0, 0))[0],
        level_pts.get(offer, (0, 0, 0))[1],
        level_pts.get(motion, (0, 0, 0))[2],
    )

    geo_pts = 0
    if location and profile.places:
        blob = location.lower()
        aliases = {
            "united states": ["usa", "u.s.", "united states", "america"],
            "united kingdom": ["uk", "britain", "england"],
            "united arab emirates": ["uae", "dubai", "abu dhabi"],
        }
        for place in profile.places:
            p = place.lower().strip()
            if p and p in blob:
                geo_pts = 12
                break
            for a in aliases.get(p, []):
                if a in blob:
                    geo_pts = 12
                    break
            if geo_pts:
                break

    evidence_bonus = 0
    if source_type == "homepage":
        evidence_bonus += 6
    evidence_bonus += min(6, evidence_count * 2)

    total = icp_pts + offer_pts + motion_pts + geo_pts + evidence_bonus

    # Hard caps so thin evidence cannot look like a strong lead.
    if source_type != "homepage":
        total = min(total, 52)
    if icp in ("unknown", "low") and motion in ("unknown", "low"):
        total = min(total, 40)
    if offer == "low" and source_type == "homepage":
        total = min(total, 72)
    if icp == "low" or motion == "low":
        total = min(total, 35)

    total = max(0, min(100, total))

    # Breakdown mirrors the same components (scaled to legacy UI maxes).
    return {
        "total_score": total,
        "breakdown": {
            "industryFit": min(25, int(round(icp_pts * 25 / 28))) if icp_pts else 0,
            "locationFit": min(20, int(round(geo_pts * 20 / 12))) if geo_pts else 0,
            "productMatch": min(20, int(round(offer_pts * 20 / 26))) if offer_pts else 0,
            "buyingSignals": 0,
            "companyFit": min(15, int(round((motion_pts + evidence_bonus) * 15 / 30))) if (motion_pts or evidence_bonus) else 0,
        },
    }


def offer_ev_as_matches(
    offer: str,
    products: List[Dict[str, Any]],
    text: str,
    company_name: str,
) -> List[Dict[str, Any]]:
    if offer == "unknown":
        return []
    matches = []
    blob = text.lower()
    for p in (products or [])[:6]:
        name = p.get("name") or ""
        cat = p.get("category") or ""
        tokens = [t for t in f"{name} {cat}".lower().split() if len(t) > 3]
        hits = sum(1 for t in tokens if t in blob)
        if hits >= 2:
            level = "High"
            reason = f"Site text overlaps {name}."
        elif hits == 1:
            level = "Medium"
            reason = f"Partial overlap with {name}; not proof of demand."
        else:
            level = "Low"
            reason = f"No site evidence that {company_name} uses or sells {name}."
        matches.append({"productName": name or cat, "fitLevel": level, "reasoning": reason})
    order = {"High": 0, "Medium": 1, "Low": 2}
    matches.sort(key=lambda r: order.get(r["fitLevel"], 9))
    if offer == "low":
        return matches[:3]
    return [m for m in matches if m["fitLevel"] != "Low"][:3] or matches[:2]
