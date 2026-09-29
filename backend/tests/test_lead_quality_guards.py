"""Lead quality guards: channel-buyer hunts must not keep peer factories or false hunt geo."""

from __future__ import annotations

from app.agents.qualify import _resolve_location
from app.agents.relevance import qualify_from_fast_decision
from app.agents.search_planner import infer_seller_profile
from app.agents.serp_classifier import classify_serp_row


def _channel_profile():
    from app.agents.search_planner import apply_prompt_focus, apply_prompt_geo, apply_prompt_roles

    prompt = (
        "weightlifting straps distributors\n"
        "weightlifting straps wholesalers\n"
        "Target location: New York, United States"
    )
    base = infer_seller_profile(
        products=[{"name": "Weightlifting straps", "category": "Weightlifting straps"}],
        icp={
            "targetBuyerTypes": ["distributors", "wholesalers", "importers"],
            "targetCountries": ["United States"],
            "targetRegions": ["New York"],
        },
        business={
            "description": "Manufacturer of weightlifting straps and belts",
            "primaryCategories": ["Weightlifting straps", "Weightlifting belts"],
        },
    )
    return apply_prompt_focus(apply_prompt_roles(apply_prompt_geo(base, prompt), prompt), prompt)


def test_channel_hunt_rejects_manufacturer_serp():
    profile = _channel_profile()
    row = classify_serp_row(
        {
            "company_name": "Sialkot Strap Factory",
            "website": "https://sialkotstraps.example/",
            "snippet": "OEM manufacturer and factory of weightlifting straps",
            "discovery_query": "weightlifting straps distributors New York, United States",
        },
        hunting_buyers=True,
        target_places=profile.places,
        strict_geo=True,
    )
    assert row["reject"] is True
    assert row["entity_type"] == "manufacturer"


def test_channel_hunt_rejects_pakistan_tld_for_ny():
    profile = _channel_profile()
    row = classify_serp_row(
        {
            "company_name": "Karachi Fitness Trading",
            "website": "https://karachifitness.pk/",
            "snippet": "Wholesale fitness accessories exporter",
            "discovery_query": "weightlifting belts wholesalers New York, United States",
        },
        hunting_buyers=True,
        target_places=profile.places,
        strict_geo=True,
    )
    assert row["reject"] is True
    assert row["entity_type"] == "wrong_geo"


def test_resolve_location_ignores_hunt_place_stamp():
    profile = _channel_profile()
    loc = _resolve_location(
        {
            "location": "New York, United States",
            "title": "Premier Straps Co",
            "snippet": "Exporter based in Lahore, Pakistan",
        },
        site_text="Premier Straps Co. Factory in Lahore, Pakistan. OEM weightlifting straps.",
        profile=profile,
    )
    assert "new york" not in (loc or "").lower()
    assert "pakistan" in (loc or "").lower() or "lahore" in (loc or "").lower()


def test_fast_qualify_rejects_false_ny_pakistan_company():
    profile = _channel_profile()
    q = qualify_from_fast_decision(
        row={
            "company_name": "Sialkot Gear Works",
            "website": "https://sialkotgear.pk/",
            "title": "Sialkot Gear Works",
            "snippet": "Manufacturer of gym belts",
            # Bug reproduction: hunt place was wrongly stamped here
            "location": "New York, United States",
            "discovery_query": "weightlifting belts distributors New York, United States",
        },
        profile=profile,
        products=[{"name": "Weightlifting belts", "category": "Weightlifting belts"}],
        triage={"verdict": "keep", "confidence": 0.7, "reason": "serp"},
        site_text=(
            "Sialkot Gear Works is a leading manufacturer based in Sialkot, Pakistan. "
            "Our factory produces weightlifting belts and straps for export."
        ),
    )
    assert q["shouldPersist"] is False
    assert "new york" not in (q.get("location") or "").lower()


def test_fast_qualify_rejects_peer_manufacturer_on_channel_hunt():
    profile = _channel_profile()
    q = qualify_from_fast_decision(
        row={
            "company_name": "East Coast Strap Mfg",
            "website": "https://eastcoaststraps.example/",
            "title": "East Coast Strap Mfg",
            "snippet": "Factory producing weightlifting straps",
            "discovery_query": "weightlifting straps wholesalers New York, United States",
        },
        profile=profile,
        products=[{"name": "Weightlifting straps", "category": "Weightlifting straps"}],
        triage={"verdict": "keep", "confidence": 0.7, "reason": "serp"},
        site_text=(
            "East Coast Strap Mfg is an OEM manufacturer. Our factory makes weightlifting straps. "
            "No wholesale distribution program."
        ),
    )
    assert q["shouldPersist"] is False
    assert "manufacturer" in (q.get("whyThisProspect") or "").lower()
