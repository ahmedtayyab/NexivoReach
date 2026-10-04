"""Verify actual business location against the hunt/search place.

Search location must never be copied onto the lead. We extract presence evidence
from the site (and Maps address / phones), then compare to requested places.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.agents.geo import (
    COUNTRY_ALIASES,
    US_STATE_ALIASES,
    countries_from_phone_text,
    enrich_geo_blob,
    format_location_display,
    location_conflicts_with_targets,
    place_aliases,
    places_mentioned,
)


# Marketing / service-area copy — not a physical office.
_SERVICE_AREA_RE = re.compile(
    r"[^.!?\n]{0,40}\b("
    r"ship(?:s|ping)?\s+(?:\w+\s+){0,4}(?:to|worldwide|globally|internationally)|"
    r"deliver(?:s|y|ing)?\s+(?:\w+\s+){0,3}(?:to|worldwide|globally)|"
    r"serv(?:e|es|ing)\s+(?:customers?\s+)?(?:in|across|worldwide|globally)|"
    r"available\s+(?:in|worldwide|across)|"
    r"export(?:s|ing)?\s+to|"
    r"worldwide\s+(?:including|shipping|delivery)|"
    r"customers?\s+(?:in|across|worldwide)|"
    r"markets?\s+(?:in|across)|"
    r"distributes?\s+to|"
    r"including\s+(?:the\s+)?(?:us|u\.s\.|united states|new york|nyc)"
    r")\b[^.!?\n]{0,100}",
    re.I,
)

# Explicit physical presence near a place name.
_PRESENCE_CUE_RE = re.compile(
    r"\b("
    r"headquarters|headquartered|hq|"
    r"based\s+in|located\s+in|located\s+at|"
    r"our\s+office|office\s+in|office\s*:|"
    r"warehouse\s+in|showroom\s+in|facility\s+in|"
    r"visit\s+us|find\s+us|address\s*:|"
    r"new\s+york\s+office|ny\s+office|u\.?s\.?\s+office|"
    r"usa\s+office|united\s+states\s+office"
    r")\b",
    re.I,
)


def strip_service_area_language(text: str) -> str:
    """Remove 'ships to / serving / export to' clauses so they do not count as HQ."""
    if not text:
        return ""
    return _SERVICE_AREA_RE.sub(" ", text)


def _requested_label(places: List[str]) -> str:
    parts = [str(p).strip() for p in (places or []) if str(p).strip()]
    # Prefer city/state before country for display
    return ", ".join(parts[:3])


def is_hunt_place_stamp(value: str, places: List[str]) -> bool:
    """True when value is just the hunt place copied onto the lead."""
    v = (value or "").strip().lower()
    if not v or not places:
        return False
    cleaned = [str(p).strip().lower() for p in places if str(p).strip()]
    if not cleaned:
        return False
    joined = ", ".join(cleaned)
    if v == joined:
        return True
    if v in cleaned:
        return True
    # "New York, United States" vs places ["New York", "United States"]
    if all(p in v for p in cleaned) and len(v) <= len(joined) + 8:
        return True
    # Thin stamp: only hunt aliases + optional parent country words
    if places_mentioned(v, cleaned) is True and not location_conflicts_with_targets(v, cleaned):
        tokens = re.findall(r"[a-z]+", v)
        allowed: set[str] = set()
        for p in cleaned:
            allowed.update(re.findall(r"[a-z]+", p))
            for a in place_aliases(p):
                allowed.update(re.findall(r"[a-z]+", a.lower()))
        allowed.update(
            {
                "united", "states", "usa", "america", "of", "the",
                "kingdom", "arab", "emirates",
            }
        )
        if tokens and all(t in allowed for t in tokens) and len(v) < 60:
            return True
    return False


def has_local_office_presence(text: str, places: List[str]) -> bool:
    """True when copy claims an office/HQ/address in a requested place."""
    blob = text or ""
    if not blob.strip() or not places:
        return False
    low = blob.lower()
    # Window around presence cues
    for m in _PRESENCE_CUE_RE.finditer(low):
        window = low[m.start() : min(len(low), m.end() + 80)]
        if places_mentioned(window, places) is True:
            return True
    # "New York Office" / "NYC Warehouse" style without cue regex catch-all
    for place in places:
        for alias in place_aliases(place):
            a = (alias or "").strip().lower()
            if len(a) < 3:
                continue
            if re.search(
                rf"\b{re.escape(a)}\s+(office|hq|headquarters|warehouse|showroom|branch|location)\b",
                low,
            ):
                return True
            if re.search(
                rf"\b(office|hq|headquarters|warehouse|showroom|branch)\s+(?:in\s+)?{re.escape(a)}\b",
                low,
            ):
                return True
    return False


def _is_country_place(place: str) -> bool:
    """True for country names/aliases, not for a US state or city."""
    low = (place or "").strip().lower()
    if not low:
        return False
    if low in US_STATE_ALIASES:
        return False
    for _state, aliases in US_STATE_ALIASES.items():
        if low == _state or low in aliases:
            return False
    if low in COUNTRY_ALIASES:
        return True
    for aliases in COUNTRY_ALIASES.values():
        if low in aliases:
            return True
    return False


def _locality_places(places: List[str]) -> List[str]:
    """City/state tokens. Drops parent countries like United States."""
    return [p.strip() for p in (places or []) if p and str(p).strip() and not _is_country_place(str(p))]


def _strip_parent_countries(location: str, places: List[str]) -> str:
    """Remove hunt-country words so 'Los Angeles, United States' still conflicts with New York."""
    text = location or ""
    for country in _target_countries(places):
        tokens = [country, *COUNTRY_ALIASES.get(country, ())]
        for token in tokens:
            if len(token) < 3:
                continue
            text = re.sub(rf"(?<![a-z]){re.escape(token)}(?![a-z])", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" ,")


def _target_countries(places: List[str]) -> set[str]:
    out: set[str] = set()
    for p in places or []:
        low = (p or "").strip().lower()
        if not low:
            continue
        if low in COUNTRY_ALIASES or any(low == a for aliases in COUNTRY_ALIASES.values() for a in aliases):
            for country, aliases in COUNTRY_ALIASES.items():
                if low == country or low in aliases:
                    out.add(country)
                    break
            continue
        # US city/state hunt implies United States
        if low in US_STATE_ALIASES:
            out.add("united states")
            continue
        for state, aliases in US_STATE_ALIASES.items():
            if low == state or low in aliases:
                out.add("united states")
                break
    return out


def _target_states(places: List[str]) -> set[str]:
    """US states explicitly requested (empty when hunt is country-only)."""
    out: set[str] = set()
    for p in places or []:
        low = (p or "").strip().lower()
        if not low:
            continue
        if low in US_STATE_ALIASES:
            out.add(low)
            continue
        for state, aliases in US_STATE_ALIASES.items():
            if low in aliases and low not in ("usa", "u.s.", "u.s.a."):
                # city alias → that state
                if low != US_STATE_ALIASES[state][0]:  # not just postal abbrev alone as place name
                    out.add(state)
                elif low == US_STATE_ALIASES[state][0]:
                    out.add(state)
    # If places only named a country (United States) with no state/city, return empty
    countries_only = True
    for p in places or []:
        low = (p or "").strip().lower()
        if low in US_STATE_ALIASES:
            countries_only = False
            break
        for state, aliases in US_STATE_ALIASES.items():
            if low == state or (low in aliases[1:] if len(aliases) > 1 else False):
                countries_only = False
                break
            if low == (aliases[0] if aliases else ""):
                countries_only = False
                break
        if not countries_only:
            break
    if countries_only:
        return set()
    return out


def _country_in_text(blob: str) -> List[str]:
    low = (blob or "").lower()
    found: List[str] = []
    for country, aliases in COUNTRY_ALIASES.items():
        for a in (country, *aliases):
            if len(a) > 2 and re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", low):
                if country not in found:
                    found.append(country)
                break
    return found


def _classify_mismatch(business_loc: str, places: List[str], *, serving_only: bool = False) -> str:
    if serving_only:
        return "foreign_business_serving_target_area"
    loc = (business_loc or "").lower()
    targets_c = _target_countries(places)
    targets_s = _target_states(places)

    for country in _country_in_text(loc):
        if targets_c and country not in targets_c:
            return "location_mismatch_country"

    if targets_s:
        for state, aliases in US_STATE_ALIASES.items():
            if state in targets_s:
                continue
            if state in loc or any(a in loc for a in aliases[1:] if len(a) > 3):
                return "location_mismatch_state"
            abbrev = aliases[0] if aliases else ""
            if abbrev and re.search(rf",\s*{re.escape(abbrev)}\b", loc):
                return "location_mismatch_state"
        # Known foreign city without US state
        for country in _country_in_text(loc):
            if country != "united states":
                return "location_mismatch_country"
        return "location_mismatch_city"

    if targets_c:
        for country in _country_in_text(loc):
            if country not in targets_c:
                return "location_mismatch_country"
    return "location_mismatch_country"


def verify_business_location(
    *,
    requested_places: List[str],
    site_text: str = "",
    title: str = "",
    snippet: str = "",
    row_location: str = "",
    phones: Optional[List[str]] = None,
    website: str = "",
) -> Dict[str, Any]:
    """
    Independently determine business location and compare to hunt places.

    Returns keys: match (bool|None), should_reject, business_location,
    requested_location, confidence, evidence, reject_reason.
    """
    places = [str(p).strip() for p in (requested_places or []) if str(p).strip()]
    requested = _requested_label(places)
    phone_list = [str(p) for p in (phones or []) if p]

    localities = _locality_places(places)
    city_hunt = bool(localities)
    result: Dict[str, Any] = {
        "match": None,
        "should_reject": False,
        "business_location": "",
        "requested_location": requested,
        "confidence": "low",
        "evidence": [],
        "reject_reason": "",
        "location_verdict": "UNCERTAIN",
    }

    if not places:
        # No geo hunt — nothing to verify
        blob = enrich_geo_blob(
            site_text=site_text, title=title, snippet=snippet, phones=phone_list
        )
        loc = format_location_display(blob, prefer_places=None)
        result["business_location"] = loc
        result["match"] = True
        result["location_verdict"] = "MATCH"
        result["confidence"] = "medium" if loc else "low"
        return result

    raw_blob = "\n".join(
        [
            title or "",
            snippet or "",
            site_text or "",
            " ".join(phone_list),
        ]
    )
    # Address extraction must not include phone digits (+92 → fake "Pakistan" site address).
    text_for_extract = strip_service_area_language(
        "\n".join([title or "", snippet or "", site_text or ""])
    )
    # City hunts: office evidence must name the city/state, not only the country.
    office_places = localities if city_hunt else places
    # Detect local office on stripped copy so "ships to New York" is not counted as HQ.
    local_office = has_local_office_presence(text_for_extract, office_places)
    # Explicit "New York Office" phrases; also check raw for office/HQ labels.
    if not local_office:
        aliases = [a for p in office_places for a in place_aliases(p) if len(a) > 2]
        if aliases:
            local_office = bool(
                re.search(
                    r"\b("
                    + "|".join(re.escape(a) for a in aliases)
                    + r")\s+(office|hq|headquarters|warehouse|showroom|branch)\b",
                    raw_blob,
                    re.I,
                )
            )

    # Maps / SERP address — ignore if it is just the hunt place stamp
    maps_loc = (row_location or "").strip()
    if maps_loc and is_hunt_place_stamp(maps_loc, places):
        maps_loc = ""

    evidence: List[str] = []
    business_loc = ""

    if maps_loc and len(maps_loc) >= 3:
        business_loc = maps_loc[:120]
        evidence.append(f"address:{business_loc}")

    presence_blob = enrich_geo_blob(
        site_text=text_for_extract,
        title="",
        snippet="",
        phones=None,
    )
    # Do NOT pass prefer_places — that biased extraction toward the hunt city.
    extracted = format_location_display(presence_blob, prefer_places=None)
    if extracted and not business_loc:
        business_loc = extracted[:120]
        evidence.append(f"site:{extracted}")
    elif extracted and extracted.lower() not in business_loc.lower():
        evidence.append(f"site:{extracted}")
        if len(extracted) > len(business_loc) + 4:
            business_loc = extracted[:120]

    dial_countries = countries_from_phone_text(raw_blob + "\n" + " ".join(phone_list))
    for c in dial_countries:
        evidence.append(f"phone:{c}")

    claimed_locality = ""
    if local_office and city_hunt:
        for place in localities:
            if places_mentioned(text_for_extract, [place]) is True:
                claimed_locality = place
                break
    if local_office:
        evidence.append("local_office_claimed")
        # Name the office from text that actually mentions it. Do not copy the hunt place.
        if city_hunt and claimed_locality and places_mentioned(business_loc or "", localities) is not True:
            if business_loc:
                business_loc = f"{claimed_locality} office ({business_loc})"[:120]
            else:
                business_loc = claimed_locality[:120]
        elif not city_hunt and places_mentioned(business_loc or "", places) is not True and business_loc:
            if location_conflicts_with_targets(business_loc, places):
                office_label = requested.split(",")[0].strip() or requested
                business_loc = f"{office_label} office ({business_loc})"[:120]

    result["business_location"] = business_loc
    result["evidence"] = evidence[:8]

    def _match(confidence: str) -> Dict[str, Any]:
        result["match"] = True
        result["should_reject"] = False
        result["location_verdict"] = "MATCH"
        result["confidence"] = confidence
        result["reject_reason"] = ""
        return result

    def _wrong(reason: str) -> Dict[str, Any]:
        result["match"] = False
        result["should_reject"] = True
        result["location_verdict"] = "WRONG_LOCATION"
        result["reject_reason"] = reason
        result["confidence"] = "high"
        return result

    def _uncertain(reason: str = "uncertain_location") -> Dict[str, Any]:
        result["match"] = None
        result["location_verdict"] = "UNCERTAIN"
        result["reject_reason"] = reason
        result["confidence"] = "low"
        # No proof of the city is not the same as the wrong city.
        # Keep the business and do not copy the hunt place onto it.
        result["should_reject"] = False
        return result

    # --- Match decision ---
    if local_office and (not city_hunt or claimed_locality or places_mentioned(business_loc or "", localities) is True):
        return _match("high")

    if city_hunt:
        if business_loc and places_mentioned(business_loc, localities) is True:
            return _match("high" if maps_loc else "medium")
        geo_for_conflict = _strip_parent_countries(business_loc, places) if business_loc else ""
        if geo_for_conflict and location_conflicts_with_targets(geo_for_conflict, localities):
            serving_only = (
                places_mentioned(raw_blob, localities) is True
                and places_mentioned(text_for_extract, localities) is not True
            )
            return _wrong(_classify_mismatch(business_loc, localities, serving_only=serving_only))
        if business_loc and places_mentioned(business_loc, places) is True:
            # Country words only (United States) do not satisfy a city hunt.
            return _uncertain("country_only")
        return _uncertain("uncertain_location" if not business_loc else "city_not_confirmed")

    if business_loc and location_conflicts_with_targets(business_loc, places):
        serving_only = (
            places_mentioned(raw_blob, places) is True
            and places_mentioned(text_for_extract, places) is not True
        )
        return _wrong(_classify_mismatch(business_loc, places, serving_only=serving_only))

    target_countries = _target_countries(places)
    foreign_phones = [c for c in dial_countries if c.lower() not in target_countries]
    local_phones = [c for c in dial_countries if c.lower() in target_countries]

    if foreign_phones and not local_phones and not business_loc:
        result["business_location"] = foreign_phones[0][:80]
        evidence.append("phone_only_foreign")
        result["evidence"] = evidence[:8]
        return _uncertain("uncertain_location")

    if business_loc and places_mentioned(business_loc, places) is True:
        return _match("high" if maps_loc else "medium")

    # Country-only hunts still keep uncertain leads (no city was requested).
    result["match"] = None
    result["location_verdict"] = "UNCERTAIN"
    result["confidence"] = "low"
    result["reject_reason"] = "uncertain_location" if not business_loc else ""
    result["should_reject"] = False
    return result


def apply_location_verification(
    q: Dict[str, Any],
    verification: Dict[str, Any],
    *,
    company_name: str = "",
) -> Dict[str, Any]:
    """Mutate qualify result with location fields; reject on mismatch."""
    name = company_name or "This company"
    fb = q.setdefault("fitBreakdown", {})
    fb["requestedLocation"] = verification.get("requested_location") or ""
    fb["businessLocation"] = verification.get("business_location") or ""
    fb["locationMatch"] = verification.get("match")
    fb["locationVerdict"] = verification.get("location_verdict") or ""
    fb["locationConfidence"] = verification.get("confidence") or "low"
    fb["locationEvidence"] = list(verification.get("evidence") or [])
    if verification.get("reject_reason"):
        fb["locationRejectReason"] = verification["reject_reason"]

    # Always store verified business location (never hunt stamp)
    q["location"] = (verification.get("business_location") or "")[:200]

    if verification.get("should_reject"):
        reason = verification.get("reject_reason") or "location_mismatch"
        q["shouldPersist"] = False
        q["priority"] = "reject"
        q["fitSummary"] = "low"
        q["icpFit"] = "low"
        q["whyThisProspect"] = (
            f"{name}: skipped — {reason.replace('_', ' ')} "
            f"(business: {verification.get('business_location') or 'unknown'}; "
            f"requested: {verification.get('requested_location') or 'n/a'})."
        )
        q["recommendedApproach"] = "Do not contact — business location does not match the hunt."
    return q
