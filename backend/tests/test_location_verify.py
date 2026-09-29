"""Business location must be verified independently of the hunt/search place."""

from __future__ import annotations

from app.agents.location_verify import (
    has_local_office_presence,
    is_hunt_place_stamp,
    strip_service_area_language,
    verify_business_location,
)
from app.agents.relevance import qualify_from_fast_decision
from app.agents.search_planner import apply_prompt_focus, apply_prompt_geo, apply_prompt_roles, infer_seller_profile


NY = ["New York", "United States"]


def _ny_profile():
    prompt = (
        "weightlifting straps distributors\n"
        "Target location: New York, United States"
    )
    base = infer_seller_profile(
        products=[{"name": "Weightlifting straps", "category": "Weightlifting straps"}],
        icp={
            "targetBuyerTypes": ["distributors", "wholesalers"],
            "targetCountries": ["United States"],
            "targetRegions": ["New York"],
        },
        business={
            "description": "Manufacturer of weightlifting straps",
            "primaryCategories": ["Weightlifting straps"],
        },
    )
    return apply_prompt_focus(apply_prompt_roles(apply_prompt_geo(base, prompt), prompt), prompt)


def test_hunt_place_stamp_detected():
    assert is_hunt_place_stamp("New York, United States", NY) is True
    assert is_hunt_place_stamp("New York", NY) is True
    assert is_hunt_place_stamp("350 Fifth Ave, New York, NY 10118", NY) is False


def test_pass_new_york_business():
    v = verify_business_location(
        requested_places=NY,
        site_text="Empire Fitness Supply, 350 Fifth Avenue, New York, NY 10118. Call +1 212-555-0100.",
        title="Empire Fitness Supply",
        snippet="Wholesale gym belts distributor in New York",
        phones=["+1 212-555-0100"],
    )
    assert v["should_reject"] is False
    assert v["match"] is True
    assert "new york" in (v["business_location"] or "").lower() or "ny" in (
        v["business_location"] or ""
    ).lower()


def test_fail_lahore_pakistan():
    v = verify_business_location(
        requested_places=NY,
        site_text="Based in Lahore, Pakistan. Phone +92 42 111 222 333. OEM gym belts exporter.",
        title="Sialkot Gear Works",
        snippet="Manufacturer of gym belts",
        row_location="New York, United States",  # stamped hunt place — must be ignored
        phones=["+92 42 111 222 333"],
    )
    assert v["should_reject"] is True
    assert v["reject_reason"] == "location_mismatch_country"
    assert "pakistan" in (v["business_location"] or "").lower() or "lahore" in (
        v["business_location"] or ""
    ).lower()
    assert "new york" not in (v["business_location"] or "").lower()


def test_fail_los_angeles_vs_new_york():
    v = verify_business_location(
        requested_places=NY,
        site_text="West Coast Fitness Wholesale, Los Angeles, California. Serving gyms nationwide.",
        title="West Coast Fitness",
        snippet="LA distributor",
        phones=["+1 310-555-0199"],
    )
    assert v["should_reject"] is True
    assert v["reject_reason"] in (
        "location_mismatch_state",
        "location_mismatch_city",
        "location_mismatch_country",
    )


def test_fail_ships_to_new_york_from_pakistan():
    text = "Based in Lahore, Pakistan. Ships products to New York."
    stripped = strip_service_area_language(text)
    assert "new york" not in stripped.lower() or "lahore" in stripped.lower()
    v = verify_business_location(
        requested_places=NY,
        site_text=text,
        title="Premier Straps Co",
        snippet="Exporter",
    )
    assert v["should_reject"] is True
    assert v["reject_reason"] in (
        "location_mismatch_country",
        "foreign_business_serving_target_area",
    )


def test_pass_pakistan_hq_with_new_york_office():
    v = verify_business_location(
        requested_places=NY,
        site_text=(
            "HQ: Lahore, Pakistan. New York Office: 350 Fifth Avenue, New York, NY. "
            "US sales +1 212-555-0144. Pakistan HQ +92 42 111 000."
        ),
        title="Global Strap Partners",
        snippet="Distributor with US office",
        phones=["+1 212-555-0144", "+92 42 111 000"],
    )
    assert has_local_office_presence(
        "HQ: Lahore, Pakistan. New York Office: 350 Fifth Avenue, New York, NY.",
        NY,
    )
    assert v["should_reject"] is False
    assert v["match"] is True


def test_phone_alone_does_not_hard_reject():
    v = verify_business_location(
        requested_places=NY,
        site_text="Wholesale fitness accessories. Contact us for catalogs.",
        title="Mystery Supply Co",
        snippet="B2B gym gear",
        phones=["+92 300 1234567"],
    )
    assert v["should_reject"] is False
    assert v["match"] is None


def test_qualify_rejects_stamped_pakistan_lead():
    profile = _ny_profile()
    q = qualify_from_fast_decision(
        row={
            "company_name": "Sialkot Gear Works",
            "website": "https://sialkotgear.example/",
            "title": "Sialkot Gear Works",
            "snippet": "Manufacturer of gym belts",
            "location": "New York, United States",
            "discovery_query": "weightlifting belts distributors New York, United States",
            "phone": "+92 52 3555555",
        },
        profile=profile,
        products=[{"name": "Weightlifting belts", "category": "Weightlifting belts"}],
        triage={"verdict": "keep", "confidence": 0.7, "reason": "serp"},
        site_text=(
            "Sialkot Gear Works is based in Sialkot, Pakistan. "
            "Our factory produces weightlifting belts. Call +92 52 3555555."
        ),
    )
    assert q["shouldPersist"] is False
    assert (q.get("fitBreakdown") or {}).get("locationRejectReason") == "location_mismatch_country"
    assert "new york" not in (q.get("location") or "").lower()
    assert (q.get("fitBreakdown") or {}).get("requestedLocation")
