from app.agents.geo import (
    extract_places_from_prompt,
    places_mentioned,
    extract_buyers_from_prompt,
    extract_offer_terms_from_prompt,
    format_location_display,
)
from app.agents.search_planner import (
    apply_prompt_focus,
    apply_prompt_geo,
    apply_prompt_roles,
    infer_seller_profile,
    plan_wave1,
)
from app.agents.serp_classifier import classify_serp_row


def test_extract_nevada_from_prompt():
    places, strict = extract_places_from_prompt(
        "martial arts belt importers in Nevada"
    )
    assert strict is True
    assert any("nevada" in p.lower() for p in places)


def test_in_preposition_is_not_indiana():
    """'importers in New jersey' must not invent Indiana from the word 'in'."""
    places, strict = extract_places_from_prompt("fleece hood importers in New jersey")
    assert strict is True
    assert any("new jersey" in p.lower() for p in places)
    assert not any("indiana" in p.lower() for p in places)


def test_extract_offer_terms_fleece_hood():
    terms = extract_offer_terms_from_prompt("fleece hood importers in New jersey")
    assert terms
    assert "fleece" in terms[0]
    assert "hood" in terms[0]


def test_extract_importers_from_prompt():
    buyers = extract_buyers_from_prompt("martial arts belt importers in Nevada")
    assert buyers[0] == "importers"


def test_format_location_las_vegas():
    loc = format_location_display("Importer based in Las Vegas, NV 89101", prefer_places=["Nevada"])
    assert "Las Vegas" in loc
    assert "Nevada" in loc


def test_places_mentioned_aliases():
    assert places_mentioned("Warehouse in Las Vegas, NV", ["Nevada"]) is True
    assert places_mentioned("Based in Texas", ["Nevada"]) is False
    # Preposition 'in' must not count as Indiana
    assert places_mentioned("Importer based in New Jersey", ["Indiana"]) is False
    assert places_mentioned("Importer based in New Jersey", ["New Jersey"]) is True


def test_prompt_geo_replaces_icp_when_strict():
    profile = infer_seller_profile(
        products=[{"name": "Belts", "category": "Martial arts"}],
        icp={"targetBuyerTypes": ["importers"], "targetCountries": ["United Arab Emirates", "Germany"]},
        business={"description": "Martial arts gear wholesale", "primaryCategories": ["Martial arts"]},
    )
    profile = apply_prompt_geo(profile, "Find martial arts belt importers in Nevada")
    assert profile.strict_geo is True
    assert any("nevada" in p.lower() for p in profile.places)
    assert not any("emirates" in p.lower() or "germany" in p.lower() for p in profile.places)
    assert profile.use_maps is True


def test_prompt_focus_leads_categories_and_queries():
    profile = infer_seller_profile(
        products=[{"name": "Fleece Ladies Hoodies", "category": "Apparel"}],
        icp={"targetBuyerTypes": ["Distributors"], "targetCountries": ["United Arab Emirates"]},
        business={"description": "apparel", "primaryCategories": ["Apparel"], "targetMarkets": ["United Arab Emirates"]},
    )
    prompt = "fleece hood importers in New jersey"
    profile = apply_prompt_focus(
        apply_prompt_roles(apply_prompt_geo(profile, prompt), prompt),
        prompt,
    )
    assert profile.categories[0].lower().startswith("fleece")
    assert profile.places == ["New Jersey"]
    assert profile.buyers[0] == "importers"
    queries = plan_wave1(profile, prompt)
    joined = " ".join(q.query.lower() for q in queries)
    assert "fleece" in joined
    assert "new jersey" in joined
    assert "fleece" in queries[0].query.lower()


def test_prompt_roles_prioritize_importers():
    profile = infer_seller_profile(
        products=[{"name": "Belts", "category": "Martial arts"}],
        icp={"targetBuyerTypes": ["retailers", "gyms"], "targetCountries": ["United States"]},
        business={"description": "Martial arts gear", "primaryCategories": ["Martial arts"]},
    )
    profile = apply_prompt_roles(
        apply_prompt_geo(profile, "Find martial arts belt importers in Nevada"),
        "Find martial arts belt importers in Nevada",
    )
    assert profile.buyers[0] == "importers"
    assert profile.pools.get("importer_distributor") == "primary"
    assert profile.sales_motion == "wholesale"


def test_strict_geo_rejects_serp_without_location():
    row = classify_serp_row(
        {
            "company_name": "Global Belt Co",
            "website": "https://globalbelts.example/",
            "snippet": "Importer of martial arts supplies worldwide",
            "source": "web",
        },
        hunting_buyers=True,
        target_places=["Nevada"],
        strict_geo=True,
    )
    assert row["reject"] is True
    assert row["entity_type"] == "wrong_geo"


def test_strict_geo_keeps_nevada_snippet():
    row = classify_serp_row(
        {
            "company_name": "Desert Martial Supply",
            "website": "https://desertmartial.example/",
            "snippet": "Martial arts belt importer based in Las Vegas, Nevada",
            "source": "web",
        },
        hunting_buyers=True,
        target_places=["Nevada"],
        strict_geo=True,
    )
    assert row["reject"] is False
    assert row["geo_mentioned"] is True


def test_strict_geo_rejects_uae_when_hunting_nj():
    row = classify_serp_row(
        {
            "company_name": "Dubai Apparel Trading",
            "website": "https://dubaiapparel.example/",
            "snippet": "Importer of hoodies and fleece in Dubai, UAE",
            "source": "web",
        },
        hunting_buyers=True,
        target_places=["New Jersey"],
        strict_geo=True,
    )
    assert row["reject"] is True
    assert row["entity_type"] == "wrong_geo"
