from app.services.intent_expansion import (
    IntentExpansion,
    ai_expansion,
    build_category_queries,
    category_term_hits,
    expand_hunt_intent,
    rules_expansion,
)


class _FakeAI:
    available = True

    def __init__(self, text):
        self.text = text

    def _complete(self, prompt):
        self.prompt = prompt
        return self.text


def test_rules_read_a_bfr_line_as_rehab_and_gym_buyers():
    exp = rules_expansion(
        ["BFR training bands distributors Canada"],
        ["Fitness equipment"],
        channel=True,
    )
    joined = " ".join(exp.buyer_types).lower()
    assert "physiotherapy" in joined
    assert "gym" in joined or "fitness" in joined
    assert "sporting goods" in joined
    assert "rehab" in exp.osm_families
    assert "physiotherapy" in exp.terms
    # a channel hunt puts wholesale / distributor types first
    assert any(w in exp.buyer_types[0].lower() for w in ("wholesal", "distribut", "supplier"))


def test_rules_use_the_seller_categories_for_a_non_sports_hunt():
    exp = rules_expansion(["greeting cards wholesalers Spain"], ["Greeting cards"], channel=True)
    assert exp.buyer_types
    assert all("greeting cards" in t for t in exp.buyer_types)
    assert exp.osm_families == ["retail"]


def test_ai_answer_is_cleaned_and_merged_with_rules_and_cities():
    reply = (
        '{"buyer_types": ["Physiotherapy supply stores", "sports medicine clinics", '
        '"blog about bands", "stores", "MMA gyms"], '
        '"relevance_terms": ["physiotherapy", "rehab", "sports medicine"], '
        '"locations": ["Toronto", "Calgary"]}'
    )
    exp = expand_hunt_intent(
        _FakeAI(reply),
        lines=["BFR training bands distributors Canada"],
        seller_brief="BFR bands",
        seller_categories=["Fitness"],
        place="Canada",
        country_name="canada",
        city="",
        channel=True,
    )
    assert exp.source == "ai"
    assert "Physiotherapy supply stores" in exp.buyer_types
    assert "blog about bands" not in exp.buyer_types
    assert "stores" not in [t.lower() for t in exp.buyer_types]
    assert exp.locations[:2] == ["Toronto", "Calgary"]
    assert "Vancouver" in exp.locations  # topped up from the built-in city list
    assert "rehab" in exp.terms


def test_no_ai_answer_falls_back_to_rules():
    exp = expand_hunt_intent(
        _FakeAI(""),
        lines=["boxing gloves distributors United Kingdom"],
        seller_brief="",
        seller_categories=[],
        place="United Kingdom",
        country_name="united kingdom",
        city="",
        channel=True,
    )
    assert exp.source == "rules"
    assert "London" in exp.locations
    assert any("boxing" in t.lower() for t in exp.buyer_types)


def test_a_city_hunt_stays_inside_that_city():
    exp = expand_hunt_intent(
        _FakeAI('{"buyer_types": ["gyms", "boxing gyms", "martial arts schools"], "locations": ["Brampton"]}'),
        lines=["boxing gloves stockists Toronto, Canada"],
        seller_brief="",
        seller_categories=[],
        place="Toronto, Canada",
        country_name="canada",
        city="Toronto",
        channel=False,
    )
    assert exp.locations[0] == "Toronto"
    assert "Vancouver" not in exp.locations


def test_bad_ai_json_returns_none():
    assert ai_expansion(_FakeAI("not json"), ["x"], "", "Canada", True) is None
    assert ai_expansion(_FakeAI('{"buyer_types": ["a"]}'), ["x"], "", "Canada", True) is None


def test_category_queries_spread_types_and_cities_and_skip_exact_lines():
    exp = IntentExpansion(
        buyer_types=["gym equipment stores", "MMA gyms", "physiotherapy supply stores"],
        locations=["Toronto", "Calgary", "Montreal"],
    )
    queries = build_category_queries(
        exp,
        country_name="canada",
        country_level=True,
        max_queries=5,
        skip=["gym equipment stores Toronto, Canada"],
    )
    lines = [q["query"] for q in queries]
    assert len(lines) == 5
    assert "gym equipment stores Toronto, Canada" not in lines
    assert all(line.endswith("Canada") for line in lines)
    # diagonal sweep: more than one city and more than one type in the first five
    assert len({q["location"] for q in queries}) >= 3
    assert len({q["search_intent"].split(" · ")[0] for q in queries}) >= 2


def test_category_term_hits_counts_whole_words_once():
    hits = category_term_hits(
        "Calgary Physiotherapy Supply — rehab braces and sports medicine",
        ["physiotherapy", "rehab", "medicine", "physio", "rehab"],
    )
    assert hits == ["physiotherapy", "rehab", "medicine"]
    assert category_term_hits("anti-physiotherapist", ["physiotherapy"]) == []


def test_website_relevance_accepts_a_buyer_category_shop_without_the_product():
    from app.agents.relevance import website_relevance

    page = (
        "Calgary Physio Supply. Physiotherapy and rehab equipment, braces and "
        "sports medicine supplies. Visit our store or order online."
    )
    kwargs = dict(
        product="bfr training bands",
        buyer_type="distributors",
        company_name="Calgary Physio Supply",
        title="Calgary Physio Supply",
        snippet="",
        site_text=page,
        categories=["bfr training bands"],
    )
    assert website_relevance(**kwargs)["relevant"] is False
    graded = website_relevance(**kwargs, category_terms=["physiotherapy", "rehab", "sports medicine"])
    assert graded["relevant"] is True
    assert graded["tier"] == "category"


def test_category_tier_still_rejects_a_page_with_no_commerce_or_one_term():
    from app.agents.relevance import website_relevance

    base = dict(
        product="bfr training bands",
        buyer_type="distributors",
        company_name="Daily Fitness News",
        title="Daily Fitness News",
        snippet="",
        categories=["bfr training bands"],
        category_terms=["fitness", "gym", "workout"],
    )
    one_term = website_relevance(**base, site_text="Fitness tips for your morning routine.")
    assert one_term["relevant"] is False
    no_shop = website_relevance(**base, site_text="Fitness and gym workout stories from our editors.")
    assert no_shop["relevant"] is False


def test_serp_listing_score_opens_category_listings_but_not_noise():
    from app.services.paginated_discovery import serp_listing_score

    cats = ["bfr training bands"]
    terms = ["physiotherapy", "rehab", "sports medicine"]
    assert serp_listing_score(
        "calgaryphysio.example", "Calgary Physio Clinic", "Rehab and sports medicine", "Calgary, Canada",
        categories=cats,
    ) == "NOISE"
    assert serp_listing_score(
        "calgaryphysio.example", "Calgary Physio Clinic", "Rehab and sports medicine", "Calgary, Canada",
        categories=cats, category_terms=terms,
    ) == "WARM"
    assert serp_listing_score(
        "weather.example", "Weather in Calgary", "Rain tomorrow", "Calgary, Canada",
        categories=cats, category_terms=terms,
    ) == "NOISE"


def test_medical_supplier_is_not_thrown_out_as_unrelated_when_it_uses_buyer_terms():
    from app.agents.geo import looks_unrelated_business

    text = "Remington Medical Calgary — physiotherapy supplies and braces"
    assert looks_unrelated_business(text, ["bfr training bands"]) is True
    assert looks_unrelated_business(text, ["bfr training bands"], ["physiotherapy"]) is False
