from app.agents.search_planner import infer_seller_profile, plan_wave1
from app.agents.serp_classifier import classify_serp_row
from app.agents.qualify import qualify_account
from app.tools.score_calculator import ScoreCalculatorTool
from app.tools.web_search import results_to_companies, WebSearchTool
from app.agents.prospecting_agent import ProspectingAgent
import pytest


def test_score_calculator_does_not_pad_empty_signals():
    calc = ScoreCalculatorTool()
    res = calc.calculate_fit_score(
        company_industry="Hospital network",
        company_location="Berlin, Germany",
        target_countries=["Germany"],
        target_buyer_types=["Hospital groups", "Healthcare providers"],
        buying_signals=[],
        product_matches=[],
        research_text="Helios is a hospital group in Berlin.",
    )
    assert res["breakdown"]["buyingSignals"] == 0
    assert res["breakdown"]["productMatch"] == 0
    assert res["breakdown"]["locationFit"] == 20


def test_score_calculator_uses_icp_not_vertical():
    calc = ScoreCalculatorTool()
    res = calc.calculate_fit_score(
        company_industry="Hospital network",
        company_location="Berlin, Germany",
        target_countries=["Germany"],
        target_buyer_types=["Hospital groups", "Healthcare providers"],
        buying_signals=[{"signal": "New surgical wing", "weight": 20}],
        product_matches=[
            {"productName": "Surgical lights", "fitLevel": "High"},
            {"productName": "Stainless cabinets", "fitLevel": "High"},
        ],
        research_text="Helios is expanding a hospital campus in Berlin.",
    )
    assert res["total_score"] >= 80
    assert res["breakdown"]["industryFit"] >= 20
    assert res["breakdown"]["locationFit"] == 20


def test_search_results_skip_directories():
    companies = results_to_companies([
        {"title": "Wikipedia", "href": "https://en.wikipedia.org/wiki/Steel", "body": "Steel is an alloy."},
        {"title": "Guide to Surgical Lights for Operating Rooms", "href": "https://www.steris.com/healthcare/knowledge-center/surgical-equipment/complete-guide-to-surgical-lights", "body": "A buyer guide."},
        {"title": "Helios Kliniken | Hospitals in Germany", "href": "https://www.helios-gesundheit.de/", "body": "Hospital group expanding in Berlin."},
        {"title": "Fake Co", "href": "https://example.com/fake", "body": "demo"},
    ], target_location="Germany")
    assert [c["company_name"] for c in companies][0] == "Helios Kliniken"
    assert all("wikipedia" not in c["website"] for c in companies)
    assert all("example.com" not in c["website"] for c in companies)


def test_planner_uses_oem_pools_not_retailer_clones():
    profile = infer_seller_profile(
        products=[{"name": "Leggings", "category": "Activewear", "moq": "300"}],
        icp={"targetBuyerTypes": ["brands", "importers"], "targetCountries": ["United States"]},
        business={"description": "Private label gymwear manufacturer in Pakistan", "primaryCategories": ["Activewear"]},
    )
    assert profile.sales_motion == "oem_private_label"
    assert profile.use_maps is False
    assert profile.pools["oem_private_label"] == "primary"
    queries = plan_wave1(profile)
    blobs = " ".join(q.query.lower() for q in queries)
    assert "private label" in blobs
    assert len(queries) <= 6


def test_planner_saas_skips_maps_and_importers():
    profile = infer_seller_profile(
        products=[{"name": "Inventory OS", "category": "Operations software"}],
        icp={"targetBuyerTypes": ["mid-market operations teams"], "targetCountries": ["United States"]},
        business={"description": "B2B SaaS platform for inventory visibility"},
    )
    assert profile.sales_motion == "saas"
    assert profile.use_maps is False
    assert profile.pools["importer_distributor"] == "off"


def test_classifier_rejects_listicles_and_factories():
    listed = classify_serp_row(
        {
            "company_name": "Top 10 Sportswear Companies in the US",
            "website": "https://somelist.com/best",
            "snippet": "best companies",
        },
        hunting_buyers=True,
        target_places=["United States"],
    )
    assert listed["reject"] is True
    factory = classify_serp_row(
        {
            "company_name": "Lahore Knit Factory",
            "website": "https://lahoreknit.pk/",
            "snippet": "OEM manufacturer of sportswear",
        },
        hunting_buyers=True,
        target_places=["United States"],
    )
    assert factory["reject"] is True
    assert factory["entity_type"] == "manufacturer"


def test_qualify_does_not_treat_category_overlap_as_intent():
    profile = infer_seller_profile(
        products=[{"name": "Hoodies", "category": "Sportswear"}],
        icp={"targetBuyerTypes": ["brands"], "targetCountries": ["United States"]},
        business={"description": "Private label apparel manufacturer", "primaryCategories": ["Sportswear"]},
    )
    q = qualify_account(
        row={
            "company_name": "North Peak",
            "website": "https://northpeak.example/",
            "snippet": "Sportswear brand",
            "entity_type": "company",
        },
        site_text="North Peak is an American apparel brand. We design sportswear for retailers. Wholesale inquiries welcome.",
        profile=profile,
        products=[{"name": "Hoodies", "category": "Sportswear"}],
        page_url="https://northpeak.example/",
    )
    assert q["intent"] == "none"
    assert "No timing" in q["whyNow"]
    assert q["fitBreakdown"]["buyingSignals"] == 0
    assert q["shouldPersist"] is True


def test_qualify_rejects_peer_manufacturer_as_buyer():
    profile = infer_seller_profile(
        products=[{"name": "Hoodies", "category": "Sportswear"}],
        icp={"targetBuyerTypes": ["brands"], "targetCountries": ["United States"]},
        business={"description": "Private label manufacturer", "primaryCategories": ["Sportswear"]},
    )
    q = qualify_account(
        row={
            "company_name": "KnitCo",
            "website": "https://knitco.example/",
            "snippet": "factory",
            "entity_type": "company",
        },
        site_text="We are a leading manufacturer. Our factory produces sportswear OEM for global buyers.",
        profile=profile,
        products=[{"name": "Hoodies", "category": "Sportswear"}],
        page_url="https://knitco.example/",
    )
    assert q["icpFit"] == "low"
    assert q["shouldPersist"] is False


def test_qualify_detects_real_intent():
    profile = infer_seller_profile(
        products=[{"name": "Hoodies", "category": "Sportswear"}],
        icp={"targetBuyerTypes": ["brands"], "targetCountries": ["United States"]},
        business={"description": "Private label manufacturer", "primaryCategories": ["Sportswear"]},
    )
    q = qualify_account(
        row={
            "company_name": "Summit Wear",
            "website": "https://summit.example/",
            "snippet": "brand",
            "entity_type": "company",
            "location": "United States",
        },
        site_text="Summit Wear is a US brand. We are seeking a manufacturer for our 2026 private label program. Sportswear wholesale.",
        profile=profile,
        products=[{"name": "Hoodies", "category": "Sportswear"}],
        page_url="https://summit.example/",
    )
    assert q["intent"] == "high"
    assert q["fitScore"] >= 70


def test_fit_score_spreads_thin_vs_strong():
    profile = infer_seller_profile(
        products=[{"name": "Hoodies", "category": "Sportswear"}],
        icp={"targetBuyerTypes": ["brands"], "targetCountries": ["United States"]},
        business={"description": "Private label apparel manufacturer", "primaryCategories": ["Sportswear"]},
    )
    thin = qualify_account(
        row={
            "company_name": "Random Co",
            "website": "https://random.example/",
            "snippet": "sportswear",
            "entity_type": "company",
        },
        site_text="",
        profile=profile,
        products=[{"name": "Hoodies", "category": "Sportswear"}],
    )
    strong = qualify_account(
        row={
            "company_name": "Peak Brand",
            "website": "https://peak.example/",
            "snippet": "activewear brand",
            "entity_type": "company",
            "location": "Austin, United States",
        },
        site_text=(
            "Peak Brand designs sportswear for retailers. "
            "Wholesale and private label programs available. "
            "We sell hoodies and activewear across the United States."
        ),
        profile=profile,
        products=[{"name": "Hoodies", "category": "Sportswear"}],
        page_url="https://peak.example/",
    )
    assert thin["fitScore"] <= 52
    assert strong["fitScore"] >= 70
    assert strong["fitScore"] - thin["fitScore"] >= 20
    assert strong["fitScore"] != 77



@pytest.mark.asyncio
async def test_ai_provider_parses_description():
    from app.providers.factory import get_ai_provider
    provider = get_ai_provider()
    profile = await provider.extract_business_profile(
        "Nordic Valves manufactures industrial valves and exports to Germany and the United Kingdom."
    )
    assert "name" in profile
    assert isinstance(profile.get("name"), str)


@pytest.mark.asyncio
async def test_agent_execution(monkeypatch):
    async def fake_hunt(self, queries, target_location="", exclude_domains=None, limit=40, use_maps=False):
        return [{
            "company_name": "Helios Kliniken",
            "website": "https://www.helios-gesundheit.de/",
            "location": "Berlin, Germany",
            "industry": "Hospital groups",
            "snippet": "Hospital group in Germany operating clinics.",
            "source": "web",
            "discovery_pool": "direct_icp",
        }]

    async def fake_home(self, url, limit=8000):
        return {
            "ok": True,
            "url": url,
            "title": "Helios Kliniken",
            "text": "Helios Kliniken is a hospital group in Germany. We operate clinics and hospitals. Wholesale medical equipment procurement.",
        }

    monkeypatch.setattr(WebSearchTool, "hunt_leads", fake_hunt)
    monkeypatch.setattr(WebSearchTool, "scrape_homepage", fake_home)

    agent = ProspectingAgent()
    res = await agent.execute_discovery_goal(
        user_prompt="Find hospital groups in Germany that may need surgical lighting.",
        products=[{"name": "Surgical Lighting Mast", "category": "Medical equipment"}],
        icp={"targetCountries": ["Germany"], "targetBuyerTypes": ["Hospital groups"]},
        business={"name": "Nordic MedTech", "description": "Surgical lighting for hospitals"},
    )
    assert res["prospects"]
    prospect = res["prospects"][0]
    assert prospect["companyName"] == "Helios Kliniken"
    assert prospect["intent"] in ("none", "low", "high")
    assert "Fitness" not in prospect["companyName"]
    assert len(res["agent_log"]["decisions"]) >= 4
