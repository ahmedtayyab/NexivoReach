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


def test_product_lines_cross_buyer_types_and_location():
    """Product-only hunt lines × selected buyer chips × location → individual SERP queries."""
    details = (
        "weightlifting straps\n"
        "martial arts belts"
    )
    prompt = (
        "Target location: California, United States\n"
        "Buyer types: Distributors, Importers\n\n"
        "Priority hunt lines (each product line × buyer types below):\n"
        f"{details}"
    )
    profile = infer_seller_profile(
        products=[],
        icp={
            "targetBuyerTypes": ["Distributors", "Importers"],
            "targetCountries": ["California, United States"],
        },
        business={"name": "Demo", "description": ""},
    )
    profile = apply_prompt_focus(
        apply_prompt_roles(apply_prompt_geo(profile, prompt), prompt),
        prompt,
    )
    queries = [q.query.lower() for q in plan_wave1(profile, prompt)]
    assert len(queries) >= 4
    assert queries[0] == "weightlifting straps distributors in california"
    assert "martial arts belts distributors in california" in queries
    assert "weightlifting straps importers in california" in queries
    assert "martial arts belts importers in california" in queries
    # Exact phrase stays intact — never reduced to belts/straps/fitness
    assert not any(q.strip() in {"straps distributors in california", "belts distributors in california"} for q in queries)
    assert not any(q.startswith("fitness ") for q in queries)
    assert not any(q == "weightlifting straps in california" for q in queries)


def test_intent_keeps_exact_product_and_defers_broader_terms():
    from app.agents.geo import interpret_hunt_intent

    martial = interpret_hunt_intent(
        ["Martial arts belts"],
        ["Importers", "Distributors"],
        "Los Angeles",
    )
    assert martial["primary_queries"] == [
        "martial arts belts importers in Los Angeles",
        "martial arts belts distributors in Los Angeles",
    ]
    assert all("martial arts belts" in q for q in martial["primary_queries"])
    assert not any(q.strip() == "belts importers in Los Angeles" for q in martial["primary_queries"] + martial["volume_queries"])
    assert any("martial arts equipment" in q for q in martial["secondary_queries"])
    assert not any("martial arts equipment" in q for q in martial["primary_queries"])

    straps = interpret_hunt_intent(
        ["Weightlifting straps"],
        ["Importers", "Distributors"],
        "New York",
    )
    assert "weightlifting straps importers in New York" in straps["primary_queries"]
    assert "weightlifting straps distributors in New York" in straps["primary_queries"]
    joined = " ".join(straps["primary_queries"] + straps["volume_queries"] + straps["secondary_queries"])
    assert "fitness equipment" not in joined
    assert not any(q.startswith("straps ") for q in straps["primary_queries"])


def test_product_query_order_interleaves_products():
    """First queries should cover every product for the first buyer role — not all straps."""
    from app.agents.geo import expand_product_buyer_lines

    lines = expand_product_buyer_lines(
        [
            "weightlifting straps",
            "weightlifting belts",
            "wrist wraps",
            "knee sleeves",
            "lifting hooks",
            "martial arts belts",
        ],
        ["distributors", "wholesalers"],
    )
    first6 = [l.lower() for l in lines[:6]]
    assert any("wrist wraps" in l for l in first6)
    assert any("knee sleeves" in l for l in first6)
    assert any("martial arts belts" in l for l in first6)
    # Must not be four straps queries first
    assert sum(1 for l in first6 if "weightlifting straps" in l) <= 2


def test_rejects_generic_fitness_store_serp():
    from app.agents.serp_classifier import classify_serp_row

    row = classify_serp_row(
        {
            "company_name": "Bay Area Fitness Superstore",
            "website": "https://bayareafitness.example/",
            "title": "Gym Equipment & Fitness Store California",
            "snippet": "Shop treadmills, racks, and training gear. Free shipping.",
            "source": "web",
            "discovery_query": '"weightlifting straps" distributors in California',
        },
        hunting_buyers=True,
        target_places=["California"],
        offer_categories=[
            "weightlifting straps",
            "knee sleeves",
            "wrist wraps",
        ],
    )
    assert row["reject"] is True


def test_rejects_shopify_product_page_for_distributor_hunt():
    from app.agents.serp_classifier import classify_serp_row

    row = classify_serp_row(
        {
            "company_name": "Weightlifting Straps",
            "website": "https://californiastrength.store/products/weightlifting-straps",
            "title": "Weightlifting Straps – California Strength",
            "snippet": "Buy weightlifting straps. Add to cart. Free shipping.",
            "source": "web",
            "discovery_query": '"weightlifting straps" distributors in California',
        },
        hunting_buyers=True,
        target_places=["California"],
        offer_categories=["weightlifting straps"],
    )
    assert row["reject"] is True
    assert row["entity_type"] == "retail_storefront"


def test_accepts_lifting_straps_serp():
    from app.agents.serp_classifier import classify_serp_row

    row = classify_serp_row(
        {
            "company_name": "Iron Grip Supply",
            "website": "https://irongripsupply.example/",
            "title": "Weightlifting Straps Wholesaler California",
            "snippet": "Distributor of lifting straps and gym accessories",
            "source": "web",
        },
        hunting_buyers=True,
        target_places=["California"],
        offer_categories=["weightlifting straps"],
    )
    assert row["reject"] is False


def test_qualify_rejects_bare_straps_page():
    from app.agents.qualify import qualify_account
    from app.agents.search_planner import SellerProfile

    profile = SellerProfile(
        offer_class="goods",
        sales_motion="wholesale",
        hunting_buyers=True,
        geo_mode="local",
        categories=["weightlifting straps"],
        buyers=["distributors"],
        places=["California"],
        use_maps=False,
        pools={"direct_icp": "primary"},
        strict_geo=True,
    )
    q = qualify_account(
        row={
            "company_name": "Pacific Cargo Gear",
            "website": "https://paccargo.example/",
            "snippet": "Straps distributor",
            "source": "web",
            "location": "Los Angeles, CA",
        },
        site_text="We sell heavy duty cargo straps and ratchet tie-downs for trucks.",
        profile=profile,
        products=[],
        page_url="https://paccargo.example/",
    )
    assert q["offerFit"] == "low"
    assert q["shouldPersist"] is False


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


def test_maps_nj_rejected_when_hunting_massachusetts():
    row = classify_serp_row(
        {
            "company_name": "WOLDORF USA, INC",
            "website": "https://woldorf.example/",
            "location": "68 Mayfield Ave, Edison, NJ 08837",
            "snippet": "Wholesale supplies near Massachusetts",
            "source": "maps",
        },
        hunting_buyers=True,
        target_places=["Massachusetts"],
        strict_geo=True,
    )
    assert row["reject"] is True
    assert row["entity_type"] == "wrong_geo"


def test_maps_ma_kept_when_hunting_massachusetts():
    row = classify_serp_row(
        {
            "company_name": "Newbury Supply",
            "website": "https://newbury.example/",
            "location": "390 Main St, Woburn, MA 01801",
            "snippet": "Industrial supply",
            "source": "maps",
        },
        hunting_buyers=True,
        target_places=["Massachusetts"],
        strict_geo=True,
    )
    assert row["reject"] is False
    assert row["geo_mentioned"] is True


def test_directory_buyers_importers_title_rejected():
    row = classify_serp_row(
        {
            "company_name": "Martial Arts Belts Buyers & Importers",
            "website": "https://somedir.example/martial",
            "snippet": "Find buyers in Massachusetts",
            "source": "web",
        },
        hunting_buyers=True,
        target_places=["Massachusetts"],
        strict_geo=True,
    )
    assert row["reject"] is True
    assert row["entity_type"] == "directory"


def test_multi_product_offer_terms():
    terms = extract_offer_terms_from_prompt(
        "elastic wrist straps and ankle strap importers in Massachusetts"
    )
    assert len(terms) >= 2
    assert "wrist" in terms[0]
    assert "ankle" in terms[1]


def test_qualify_rejects_nj_address_despite_boston_on_site():
    from app.agents.qualify import qualify_account
    from app.agents.search_planner import SellerProfile

    profile = SellerProfile(
        offer_class="goods",
        sales_motion="wholesale",
        hunting_buyers=True,
        geo_mode="local",
        categories=["elastic wrist straps"],
        buyers=["importers"],
        places=["Massachusetts"],
        use_maps=True,
        pools={"direct_icp": "primary"},
        strict_geo=True,
    )
    q = qualify_account(
        row={
            "company_name": "WOLDORF USA",
            "website": "https://woldorf.example/",
            "location": "Edison, NJ 08837",
            "snippet": "Importer",
            "source": "maps",
            "phone": "555-0100",
        },
        site_text="We ship nationwide including Boston and New York.",
        profile=profile,
        products=[{"name": "Wrist straps", "category": "Gear"}],
        page_url="https://woldorf.example/",
    )
    assert q["shouldPersist"] is False
