"""
Lead quality gate and business list sources.

The gate: a junk page is never saved, a company blog post never blocks the
company, a foreign address is a reject, an unread site stays open.
The sources: Google Places, Companies House, and OpenStreetMap payloads turn
into company candidates; registry names resolve only to their own website;
the Places ledger stops under the free allowance.
"""

from __future__ import annotations

import json

import pytest

from app.agents.serp_classifier import classify_page, classify_serp_row, extract_directory_companies
from app.services import business_sources as bs
from app.services.paginated_discovery import lead_save_decision


# --------------------------------------------------------------------------- gate


@pytest.mark.parametrize(
    "url",
    [
        "https://www.pinterest.com/pin/weightlifting-straps-ideas/",
        "https://onlyfans.com/someone",
        "https://github.com/someone/lifting-app",
        "https://www.amazon.co.uk/dp/B0XYZ",
        "https://www.researchgate.net/publication/123_grip_strength",
        "https://www.strath.ac.uk/sport/strength-and-conditioning/",
        "https://sportsci.edu.au/papers/grip.pdf",
        "https://www.madeinchina.com/product/knee-sleeve.html",
    ],
)
def test_non_business_hosts_are_never_companies(url):
    page = classify_page(url, "Weightlifting straps")
    assert page["page_kind"] == "article"


@pytest.mark.parametrize(
    "url",
    [
        "https://travel.gc.ca/",
        "https://www.canada.ca/en.html",
        "https://www.gov.uk/guidance/importing",
        "https://www.service-public.fr/",
        "https://www.gob.mx/",
        "https://www.mofa.go.jp/",
        "https://www.overheid.nl/",
        "https://www.moe.gov.cn/",
        "https://www.usa.gov/",
        "https://www.booking.com/hotel/ca/example.html",
        "https://www.eventbrite.fr/e/salon",
        "https://www.ticketmaster.de/",
        "https://www.tagvenue.com/venues/london",
        "https://www.agoda.com/",
    ],
)
def test_governments_and_booking_platforms_are_never_companies(url):
    page = classify_page(url, "Directory")
    assert page["page_kind"] == "article"
    assert page["burn_domain"] is True


def test_documents_are_skipped_without_burning_the_host():
    page = classify_page("https://www.liftingco.co.uk/catalogue-2026.pdf", "Catalogue")
    assert page["page_kind"] == "article"
    assert page["burn_domain"] is False


def test_directory_page_is_recognised():
    page = classify_page("https://www.europages.co.uk/companies/united%20kingdom/wholesaler/sport.html", "Sport Wholesaler UK")
    assert page["page_kind"] == "directory"
    assert page["burn_domain"] is False


def test_company_homepage_is_a_company():
    assert classify_page("https://www.primegearsports.co.uk/", "Prime Gear Sports")["page_kind"] == "company"
    assert classify_page("https://www.tiendafitness.mx/", "Tienda Fitness")["page_kind"] == "company"
    assert classify_page("https://www.liftingshop.co.jp/", "Lifting Shop")["page_kind"] == "company"


def test_industry_giant_homepage_is_skipped_and_burned():
    page = classify_page("https://www.gymreapers.com/", "Gymreapers")
    assert page["page_kind"] == "article"
    assert page["burn_domain"] is True
    assert "giant" in page["reason"].lower()


def test_giant_stockist_page_is_a_directory_not_a_lead():
    page = classify_page("https://www.sbdapparel.com/pages/stockists", "SBD Stockists")
    assert page["page_kind"] == "directory"
    assert page["burn_domain"] is False


def test_directory_extraction_skips_show_page_chrome():
    html = """
    <header><a href="https://www.eventbrite.com/e/elevate">Tickets</a></header>
    <a href="https://www.primegearsports.co.uk/">Prime Gear Sports</a>
    <footer>
      <a href="https://travel.gc.ca/">Travel.gc.ca</a>
      <a href="https://www.tagvenue.com/">Tagvenue</a>
      <a href="https://www.accommodationcanada.com/">Hotels</a>
    </footer>
    """
    links = extract_directory_companies(
        html, "https://www.elevatearena.com/london/exhibitors/2026-exhibitors",
    )
    assert links == ["https://www.primegearsports.co.uk/"]


def test_directory_links_skip_industry_giants():
    html = """
    <a href="https://www.gymreapers.com/">Gymreapers</a>
    <a href="https://www.localgymshop.co.uk/">Local Gym Shop</a>
    <a href="https://www.roguefitness.com/store-locator">Rogue</a>
    """
    links = extract_directory_companies(html, "https://sbdapparel.com/pages/stockists")
    assert links == ["https://www.localgymshop.co.uk/"]


def test_classify_serp_row_marks_pinterest_as_junk_and_burns_it():
    row = classify_serp_row(
        {
            "website": "https://www.pinterest.com/pin/1234/",
            "title": "Lifting straps ideas",
            "snippet": "Pins",
            "discovery_query": "weightlifting straps distributors United Kingdom",
        },
        hunting_buyers=True,
        target_places=["United Kingdom"],
    )
    assert row["reject"] is True
    assert row["burn_domain"] is True
    assert row["page_kind"] == "article"


def test_save_decision_never_turns_a_negative_into_a_save():
    assert lead_save_decision(relevant=True, should_reject=False, page_loaded=True) == "QUALIFIED_BUSINESS"
    assert lead_save_decision(relevant=True, should_reject=True, page_loaded=True) == "REJECT_WRONG_LOCATION"
    assert lead_save_decision(relevant=False, should_reject=False, page_loaded=True) == "REJECT_UNRELATED_BUSINESS"
    assert lead_save_decision(relevant=True, should_reject=False, page_loaded=False) == "UNCERTAIN_REQUIRES_MORE_EVIDENCE"


def test_unloaded_site_is_uncertain_not_a_lead():
    from app.agents.relevance import website_relevance

    # A matching snippet alone used to be saved as "SERP-only". The gate now
    # holds it back until the site has been read.
    graded = website_relevance(
        product="weightlifting straps",
        buyer_type="distributors",
        company_name="Some Co",
        title="Some Co",
        snippet="weightlifting straps distributors",
        site_text="",
        categories=["weightlifting straps"],
    )
    decision = lead_save_decision(
        relevant=bool(graded["relevant"]), should_reject=False, page_loaded=False,
    )
    assert decision == "UNCERTAIN_REQUIRES_MORE_EVIDENCE"

    bare = website_relevance(
        product="weightlifting straps",
        buyer_type="distributors",
        company_name="Some Co",
        title="Some Co",
        snippet="",
        site_text="",
        categories=["weightlifting straps"],
    )
    assert bare["relevant"] is False
    assert bare["decision"] == "UNCERTAIN_REQUIRES_MORE_EVIDENCE"


def test_loaded_page_with_no_trade_evidence_is_rejected():
    from app.agents.relevance import website_relevance

    graded = website_relevance(
        product="weightlifting straps",
        buyer_type="distributors",
        company_name="City Council",
        title="City Council",
        snippet="",
        site_text="Council tax, bins and recycling, planning applications, parking permits.",
        categories=["weightlifting straps"],
    )
    assert graded["relevant"] is False
    assert graded["decision"] == "REJECT_UNRELATED_BUSINESS"


def test_retail_shop_in_the_trade_is_still_kept_as_low():
    from app.agents.relevance import website_relevance

    graded = website_relevance(
        product="weightlifting straps",
        buyer_type="distributors",
        company_name="Gym Shop",
        title="Gym Shop",
        snippet="",
        site_text="Weightlifting straps and lifting belts. Add to cart. Free UK delivery.",
        categories=["weightlifting straps"],
    )
    assert graded["relevant"] is True
    assert graded["level"] == "low"


def test_directory_links_exclude_the_directory_and_social_hosts():
    html = """
    <a href="https://www.europages.co.uk/CI-SPORT/GBR1.html">CI Sport profile</a>
    <a href="https://www.cisport.co.uk/">Website</a>
    <a href="https://www.facebook.com/cisport">Facebook</a>
    <a href="https://ultrasporteu.com/about">Ultra Sport Europe</a>
    <a href="/companies/page/2">Next</a>
    <a href="https://www.cisport.co.uk/products">Products</a>
    """
    links = extract_directory_companies(html, "https://www.europages.co.uk/companies/sport.html")
    hosts = [link.split("/")[2] for link in links]
    assert hosts == ["www.cisport.co.uk", "ultrasporteu.com"]


# --------------------------------------------------------------------------- planning


def test_hunt_country_and_city():
    assert bs.hunt_country("Manchester, United Kingdom") == ("united kingdom", "GB")
    assert bs.hunt_country("UK") == ("united kingdom", "GB")
    assert bs.hunt_country("Texas") == ("united states", "US")
    assert bs.hunt_city("Manchester, United Kingdom", "united kingdom") == "Manchester"
    assert bs.hunt_city("United Kingdom", "united kingdom") == ""


def test_source_plan_uses_companies_house_only_for_uk(monkeypatch):
    monkeypatch.setattr(bs.settings, "COMPANIES_HOUSE_API_KEY", "key")
    monkeypatch.setattr(bs.settings, "GOOGLE_PLACES_API_KEY", "")
    monkeypatch.setattr(bs.settings, "OSM_SOURCE_ENABLED", True)
    monkeypatch.setattr(bs.settings, "DIRECTORY_SOURCE_ENABLED", True)
    monkeypatch.setattr(bs.settings, "STOCKIST_SOURCE_ENABLED", True)
    monkeypatch.setattr(bs.settings, "EXHIBITOR_SOURCE_ENABLED", True)
    uk = bs.source_plan_for_intent("weightlifting straps distributors Manchester, United Kingdom", "Manchester, United Kingdom")
    assert uk["product"] == "weightlifting straps"
    assert uk["role"] == "distributors"
    assert uk["sources"] == ["stockists", "exhibitors", "companies_house", "directory"]
    us = bs.source_plan_for_intent("weightlifting straps distributors Texas", "Texas")
    assert "companies_house" not in us["sources"]
    assert us["sources"] == ["stockists", "exhibitors", "directory"]


def test_source_plan_uses_osm_for_shops_and_gyms(monkeypatch):
    monkeypatch.setattr(bs.settings, "COMPANIES_HOUSE_API_KEY", "")
    monkeypatch.setattr(bs.settings, "GOOGLE_PLACES_API_KEY", "")
    monkeypatch.setattr(bs.settings, "OSM_SOURCE_ENABLED", True)
    monkeypatch.setattr(bs.settings, "DIRECTORY_SOURCE_ENABLED", True)
    monkeypatch.setattr(bs.settings, "STOCKIST_SOURCE_ENABLED", True)
    monkeypatch.setattr(bs.settings, "EXHIBITOR_SOURCE_ENABLED", True)
    plan = bs.source_plan_for_intent("boxing gloves retailers Leeds, United Kingdom", "Leeds, United Kingdom")
    assert plan["family"] == "retail"
    assert plan["sources"] == ["stockists", "exhibitors", "osm", "directory"]
    gyms = bs.source_plan_for_intent("boxing gyms London, United Kingdom", "London, United Kingdom")
    assert gyms["family"] == "gym"


def test_places_is_opt_in(monkeypatch):
    monkeypatch.setattr(bs.settings, "GOOGLE_PLACES_API_KEY", "")
    monkeypatch.setattr(bs.settings, "COMPANIES_HOUSE_API_KEY", "")
    monkeypatch.setattr(bs.settings, "DIRECTORY_SOURCE_ENABLED", True)
    monkeypatch.setattr(bs.settings, "STOCKIST_SOURCE_ENABLED", True)
    monkeypatch.setattr(bs.settings, "EXHIBITOR_SOURCE_ENABLED", True)
    plan = bs.source_plan_for_intent("weightlifting straps distributors United Kingdom", "United Kingdom")
    assert "places" not in plan["sources"]
    assert plan["sources"] == ["stockists", "exhibitors", "directory"]
    monkeypatch.setattr(bs.settings, "GOOGLE_PLACES_API_KEY", "key")
    plan = bs.source_plan_for_intent("weightlifting straps distributors United Kingdom", "United Kingdom")
    assert plan["sources"][0] == "places"


# --------------------------------------------------------------------------- Google Places


def test_places_payload_keeps_only_open_businesses_with_websites():
    payload = {
        "places": [
            {"id": "a", "displayName": {"text": "Lift Supply Ltd"}, "formattedAddress": "1 Mill St, Leeds, UK",
             "websiteUri": "https://liftsupply.co.uk/", "businessStatus": "OPERATIONAL"},
            {"id": "b", "displayName": {"text": "No Site Gym"}, "formattedAddress": "Leeds", "businessStatus": "OPERATIONAL"},
            {"id": "c", "displayName": {"text": "Closed Co"}, "formattedAddress": "Leeds",
             "websiteUri": "https://closed.co.uk/", "businessStatus": "CLOSED_PERMANENTLY"},
        ],
        "nextPageToken": "tok2",
    }
    cands, token, skipped = bs.parse_places_payload(payload)
    assert [c.name for c in cands] == ["Lift Supply Ltd"]
    assert cands[0].address == "1 Mill St, Leeds, UK"
    assert token == "tok2"
    assert skipped == 1


def test_places_cap_stops_under_the_free_allowance():
    assert bs.places_budget_allows(0, cap=900) is True
    assert bs.places_budget_allows(899, cap=900) is True
    assert bs.places_budget_allows(900, cap=900) is False
    assert bs.places_budget_allows(5, cap=0) is False


def test_places_step_sends_exact_query_and_region(monkeypatch):
    sent = {}

    class _Res:
        status_code = 200
        text = ""

        def json(self):
            return {"places": [], "nextPageToken": ""}

    class _Client:
        def post(self, url, headers=None, json=None):
            sent["url"] = url
            sent["body"] = json
            sent["mask"] = headers["X-Goog-FieldMask"]
            return _Res()

    step = bs.places_step(
        "weightlifting straps distributors Manchester, United Kingdom", "",
        region_code="GB", api_key="k", client=_Client(),
    )
    assert sent["body"]["textQuery"] == "weightlifting straps distributors Manchester, United Kingdom"
    assert sent["body"]["regionCode"] == "gb"
    assert "places.websiteUri" in sent["mask"]
    assert step.exhausted is True
    assert step.requests_used == 1


# --------------------------------------------------------------------------- Companies House


def test_company_name_words_follow_the_trade():
    assert bs.company_name_words("boxing gloves", "distributors")[:2] == ["boxing", "fight"]
    assert bs.company_name_words("weightlifting straps", "wholesalers")[0] == "wrap"
    assert "sleeve" in bs.company_name_words("gym knee sleeves", "distributors")
    assert "sport" in bs.company_name_words("cricket bats", "importers")


def test_registry_items_become_candidates_with_uk_address():
    payload = {
        "items": [
            {"company_name": "PRIME GEAR SPORTS LTD", "company_number": "123",
             "registered_office_address": {"address_line_1": "5 High St", "locality": "Croydon", "postal_code": "CR2 6AA"}},
            {"company_name": "", "company_number": "x"},
        ]
    }
    items = bs.parse_ch_items(payload)
    assert len(items) == 1
    assert items[0].name == "PRIME GEAR SPORTS LTD"
    assert items[0].address.endswith("United Kingdom")
    assert items[0].ref == "123"


def test_company_website_match_rejects_registries_and_strangers():
    assert bs.website_matches_company("Prime Gear Sports Ltd", "https://www.primegearsports.co.uk/")
    assert bs.website_matches_company("CI Sport Ltd", "https://cisport.co.uk/about")
    assert bs.website_matches_company("Ultra Sport Europe Ltd", "https://ultrasporteu.com/", "Ultra Sport Europe - Distributor")
    assert not bs.website_matches_company("Prime Gear Sports Ltd", "https://find-and-update.company-information.service.gov.uk/company/123")
    assert not bs.website_matches_company("Prime Gear Sports Ltd", "https://www.endole.co.uk/company/123/prime-gear-sports-ltd")
    assert not bs.website_matches_company("Prime Gear Sports Ltd", "https://www.linkedin.com/company/prime-gear-sports")
    assert not bs.website_matches_company("Prime Gear Sports Ltd", "https://www.bbc.co.uk/news/sport")
    # Listing sites print the company name in the title. The title is not evidence.
    assert not bs.website_matches_company("Ultra Sport Europe Ltd", "https://ukbizdb.co.uk/company/ultra", "ULTRA SPORT EUROPE LTD - UK Biz DB")
    assert not bs.website_matches_company("Thomas Sports Equipment Ltd", "https://www.yorkshire.com/business/thomas", "Thomas Sports Equipment Ltd | Yorkshire")
    # Generic words alone do not make a match.
    assert not bs.website_matches_company("Thomas Sports Equipment Ltd", "https://www.sportsequipment.co.uk/")
    assert bs.website_matches_company("Thomas Sports Equipment Ltd", "https://www.thomassports.co.uk/")


def test_resolve_company_website_takes_the_first_matching_hit():
    hits = [
        {"title": "PRIME GEAR SPORTS LTD - Companies House", "href": "https://find-and-update.company-information.service.gov.uk/company/123"},
        {"title": "Prime Gear Sports | Boxing gear", "href": "https://www.primegearsports.co.uk/collections/boxing"},
    ]
    no_probe = lambda name: ""  # noqa: E731 — keep the test offline
    site = bs.resolve_company_website("Prime Gear Sports Ltd", lambda q: hits, prober=no_probe)
    assert site == "https://www.primegearsports.co.uk/"
    assert bs.resolve_company_website("Prime Gear Sports Ltd", lambda q: hits[:1], prober=no_probe) == ""
    # A direct domain answer wins before any search is made.
    site = bs.resolve_company_website("Prime Gear Sports Ltd", lambda q: (_ for _ in ()).throw(AssertionError("no search")), prober=lambda n: "https://primegearsports.co.uk/")
    assert site == "https://primegearsports.co.uk/"


def test_domain_guesses_and_probe():
    guesses = bs.domain_guesses("Kukri Sports Ltd")
    assert guesses[:3] == ["kukrisports.co.uk", "kukrisports.com", "kukrisports.uk"]
    assert "ultrasport.co.uk" in bs.domain_guesses("Ultra Sport Europe Ltd")
    assert "thomas.co.uk" not in bs.domain_guesses("Thomas Sports Equipment Ltd")

    def fetch(url):
        if url == "https://kukrisports.co.uk/":
            raise ConnectionError("no such host")
        if url == "https://kukrisports.com/":
            return 200, "https://www.kukrisports.com/", "<html><title>Kukri Sports - teamwear</title></html>"
        return 404, url, ""

    assert bs.probe_domain_guesses("Kukri Sports Ltd", fetch=fetch) == "https://www.kukrisports.com/"

    def parked(url):
        return 200, url, "<html>This domain is for sale. Buy this domain.</html>"

    assert bs.probe_domain_guesses("Kukri Sports Ltd", fetch=parked) == ""

    def redirect_to_registry(url):
        return 200, "https://www.endole.co.uk/company/1", "<html>Kukri Sports Ltd</html>"

    assert bs.probe_domain_guesses("Kukri Sports Ltd", fetch=redirect_to_registry) == ""


def test_companies_house_step_pages_and_resolves(monkeypatch):
    calls = {}

    class _Res:
        status_code = 200
        text = ""

        def json(self):
            return {"items": [
                {"company_name": f"FITNESS SUPPLY {n} LTD", "company_number": str(n),
                 "registered_office_address": {"locality": "Leeds", "country": "United Kingdom"}}
                for n in range(bs.CH_PAGE)
            ]}

    class _Client:
        def get(self, url, params=None, auth=None):
            calls["params"] = params
            calls["auth"] = auth
            return _Res()

    def searcher(q):
        name = q.strip('"').split('"')[0]
        n = name.split()[2]
        return [{"title": name, "href": f"https://fitnesssupply{n}.co.uk/"}]

    step = bs.companies_house_step(
        product="weightlifting straps", role="distributors", city="Leeds", cursor="",
        searcher=searcher, api_key="k", client=_Client(), pause_sec=0, prober=lambda n: "",
    )
    assert calls["auth"] == ("k", "")
    assert calls["params"]["company_name_includes"] == "wrap"
    assert calls["params"]["location"] == "Leeds"
    assert "46499" in calls["params"]["sic_codes"]
    assert len(step.candidates) == bs.CH_PAGE
    assert step.candidates[0].website == "https://fitnesssupply0.co.uk/"
    assert step.exhausted is False
    assert bs.parse_ch_cursor(step.next_cursor) == {"word": 0, "start": bs.CH_PAGE}


def test_companies_house_short_page_moves_to_the_next_name_word():
    class _Res:
        status_code = 200
        text = ""

        def json(self):
            return {"items": [{"company_name": "GYM CO LTD", "company_number": "1", "registered_office_address": {}}]}

    class _Client:
        def get(self, url, params=None, auth=None):
            return _Res()

    step = bs.companies_house_step(
        product="weightlifting straps", role="distributors", city="", cursor=bs.ch_cursor_json(0, 30),
        searcher=lambda q: [], api_key="k", client=_Client(), pause_sec=0, prober=lambda n: "",
    )
    assert step.candidates == []
    assert step.skipped_without_website == 1
    assert bs.parse_ch_cursor(step.next_cursor) == {"word": 1, "start": 0}


def test_companies_house_error_does_not_finish_the_source():
    class _Res:
        status_code = 401
        text = "unauthorized"

    class _Client:
        def get(self, url, params=None, auth=None):
            return _Res()

    step = bs.companies_house_step(
        product="gym knee sleeves", role="distributors", city="", cursor="",
        searcher=lambda q: [], api_key="k", client=_Client(), pause_sec=0, prober=lambda n: "",
    )
    assert step.exhausted is False
    assert step.candidates == []
    assert "rejected the key" in step.note


# --------------------------------------------------------------------------- OpenStreetMap


def test_overpass_query_for_a_city_and_a_country():
    city = bs.overpass_query("retail", bbox=(53.69, -1.80, 53.95, -1.29))
    assert '["shop"="sports"]["website"](53.69000,-1.80000,53.95000,-1.29000);' in city
    assert '["shop"="fitness"]["contact:website"]' in city
    assert "area[" not in city
    assert "~" not in city  # exact values keep Overpass on its index
    country = bs.overpass_query("gym", iso="GB")
    assert 'area["ISO3166-1"="GB"]["admin_level"="2"]' in country
    assert '["leisure"="fitness_centre"]["website"](area.a);' in country
    assert bs.overpass_query("channel", bbox=(53.69, -1.80, 53.95, -1.29)) == ""
    assert bs.overpass_query("retail") == ""


def test_overpass_payload_to_candidates():
    payload = {"elements": [
        {"type": "node", "id": 1, "tags": {"name": "Leeds Boxing Store", "shop": "sports",
                                             "website": "leedsboxingstore.co.uk", "addr:city": "Leeds"}},
        {"type": "way", "id": 2, "tags": {"name": "Nameless", "shop": "sports"}},
        {"type": "node", "id": 3, "tags": {"name": "Dup", "contact:website": "https://www.leedsboxingstore.co.uk/"}},
    ]}
    cands = bs.parse_overpass_payload(payload, "United Kingdom")
    assert len(cands) == 1
    assert cands[0].website == "https://leedsboxingstore.co.uk"
    assert cands[0].address == "Leeds, United Kingdom"
    assert cands[0].ref == "node/1"


def test_gym_in_the_product_is_not_the_buyer_role():
    from app.agents.geo import parse_discovery_query

    product, role, place = parse_discovery_query("wrist wraps gym wholesalers United Kingdom")
    assert role == "wholesalers"
    assert "wraps" in product
    assert "united kingdom" in place.lower()
    gyms = parse_discovery_query("boxing gyms London, United Kingdom")
    assert gyms[1] == "gyms"


def test_source_cursor_key_is_shared_across_similar_hunt_lines():
    from app.services.paginated_discovery import source_cursor_key

    plan = {"iso": "GB", "family": "channel", "product": "gym knee sleeves", "role": "distributors"}
    other = {"iso": "GB", "family": "channel", "product": "weightlifting knee sleeves", "role": "wholesalers"}
    boxing = {"iso": "GB", "family": "channel", "product": "boxing gloves", "role": "distributors"}
    assert source_cursor_key("companies_house", "q1", plan) == source_cursor_key("companies_house", "q2", other)
    assert source_cursor_key("directory", "q1", plan) == source_cursor_key("directory", "q2", other)
    assert source_cursor_key("stockists", "q1", plan) == source_cursor_key("stockists", "q2", other)
    assert source_cursor_key("stockists", "q1", plan) != source_cursor_key("stockists", "q2", boxing)
    assert source_cursor_key("exhibitors", "q1", plan) == source_cursor_key("exhibitors", "q2", boxing)


def test_ch_cursor_roundtrip():
    assert bs.parse_ch_cursor("") == {"word": 0, "start": 0}
    assert bs.parse_ch_cursor(json.dumps({"word": 2, "start": 45})) == {"word": 2, "start": 45}
    assert bs.parse_ch_cursor("not json") == {"word": 0, "start": 0}


# --------------------------------------------------------------------------- directories


def test_directory_urls_keep_the_product_trade_and_country():
    plan = {
        "product": "weightlifting straps",
        "family": "channel",
        "country": "united kingdom",
        "iso": "GB",
    }
    urls = bs.directory_urls_for_plan(plan)
    assert any("united%20kingdom/wholesaler/fitness" in u for u in urls)
    assert any("europages.co.uk/companies/fitness.html" in u for u in urls)
    assert any("esources.co.uk" in u for u in urls)
    boxing = bs.directory_urls_for_plan({
        "product": "boxing gloves", "family": "channel",
        "country": "united states", "iso": "US",
    })
    assert any("united%20states/wholesaler/boxing" in u for u in boxing)
    assert not any("esources.co.uk" in u for u in boxing)


def test_directory_step_extracts_companies_and_pages():
    html = """
    <a href="https://www.europages.co.uk/CI-SPORT/GBR1.html">profile</a>
    <a href="https://www.cisport.co.uk/">Website</a>
    <a href="https://www.facebook.com/cisport">Facebook</a>
    """

    class _Res:
        status_code = 200
        text = html
        url = "https://www.europages.co.uk/companies/united%20kingdom/wholesaler/sport.html"

    class _Client:
        def get(self, url):
            return _Res()

    urls = [
        "https://www.europages.co.uk/companies/united%20kingdom/wholesaler/sport.html",
        "https://www.europages.co.uk/companies/sport.html",
    ]
    step = bs.directory_step(urls=urls, cursor="0", client=_Client())
    assert [c.website for c in step.candidates] == ["https://www.cisport.co.uk/"]
    assert step.next_cursor == "1"
    assert step.exhausted is False
    done = bs.directory_step(urls=urls, cursor="2", client=_Client())
    assert done.exhausted is True
    assert done.candidates == []


# --------------------------------------------------------------------------- stockists / exhibitors


def test_stockist_step_keeps_independent_shops_and_skips_the_brand():
    from app.services.buyer_lists import stockist_brands, stockist_step

    assert "SBD" in stockist_brands("knee sleeves")
    html = """
    <a href="https://www.gymreapers.com/">Gymreapers</a>
    <a href="https://www.localgymshop.co.uk/">Local Gym Shop</a>
    <a href="https://www.facebook.com/local">Facebook</a>
    """

    def searcher(q):
        assert "SBD" in q
        assert "United Kingdom" in q
        return [{"title": "SBD Stockists", "href": "https://sbdapparel.com/pages/stockists"}]

    step = stockist_step(
        product="knee sleeves",
        place="United Kingdom",
        cursor="0",
        searcher=searcher,
        fetch_html=lambda _url: html,
    )
    sites = [c.website for c in step.candidates]
    assert sites == ["https://www.localgymshop.co.uk/"]
    assert step.next_cursor == "1"
    assert step.exhausted is False


def test_stockist_search_also_keeps_a_shop_hit():
    from app.services.buyer_lists import stockist_step

    def searcher(_q):
        return [
            {"title": "North Strength", "href": "https://www.northstrength.co.uk/"},
            {"title": "Gymreapers", "href": "https://www.gymreapers.com/"},
        ]

    step = stockist_step(
        product="wrist wraps",
        place="United Kingdom",
        cursor="0",
        searcher=searcher,
        fetch_html=lambda _url: "",
    )
    sites = [c.website for c in step.candidates]
    assert "https://www.northstrength.co.uk/" in sites
    assert not any("gymreapers" in s for s in sites)


def test_exhibitor_step_extracts_company_sites_and_names():
    from app.services.buyer_lists import exhibitor_step, extract_exhibitor_names

    html = """
    <h3>Prime Gear Sports</h3>
    <a href="https://www.primegearsports.co.uk/">Website</a>
    <h3>Exhibitors</h3>
    """
    assert "Prime Gear Sports" in extract_exhibitor_names(html)

    def searcher(_q):
        return []

    step = exhibitor_step(
        urls=["https://www.elevatearena.com/london/exhibitors/2026-exhibitors", "https://example.com/2"],
        cursor="0",
        searcher=searcher,
        fetch_html=lambda _url: html,
        resolve_limit=0,
    )
    assert [c.website for c in step.candidates] == ["https://www.primegearsports.co.uk/"]
    assert step.next_cursor == "1"
    assert step.exhausted is False
