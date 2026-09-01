import pytest
from app.providers.factory import get_ai_provider
from app.tools.score_calculator import ScoreCalculatorTool
from app.tools.web_search import results_to_companies, WebSearchTool
from app.agents.prospecting_agent import ProspectingAgent


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


@pytest.mark.asyncio
async def test_ai_provider_parses_description():
    provider = get_ai_provider()
    profile = await provider.extract_business_profile(
        "Nordic Valves manufactures industrial valves and exports to Germany and the United Kingdom."
    )
    assert "name" in profile
    assert isinstance(profile.get("name"), str)


@pytest.mark.asyncio
async def test_agent_execution(monkeypatch):
    async def fake_search(self, query, target_location=""):
        return [{
            "company_name": "Helios Kliniken",
            "website": "https://www.helios-gesundheit.de/",
            "location": "Berlin, Germany",
            "industry": "Hospital groups",
            "snippet": "Helios is opening a new surgical wing in Berlin and reviewing equipment suppliers.",
        }]

    async def fake_scrape(self, url):
        return "Helios Kliniken is expanding its Berlin hospital campus with a new surgical wing and procurement of medical equipment."

    monkeypatch.setattr(WebSearchTool, "search_companies", fake_search)
    monkeypatch.setattr(WebSearchTool, "scrape_site_content", fake_scrape)

    agent = ProspectingAgent()
    res = await agent.execute_discovery_goal(
        user_prompt="Find hospital groups in Germany that may need surgical lighting.",
        products=[{"name": "Surgical Lighting Mast", "category": "Medical equipment"}],
        icp={"targetCountries": ["Germany"], "targetBuyerTypes": ["Hospital groups"]},
        business={"name": "Nordic MedTech"},
    )
    assert res["prospect"] is not None
    assert res["prospect"]["companyName"] == "Helios Kliniken"
    assert "Fitness" not in res["prospect"]["companyName"]
    assert res["prospect"]["fitScore"] >= 70
    assert len(res["agent_log"]["decisions"]) >= 6
    assert "Nordic MedTech" in (
        res["prospect"]["outreachDraft"]["body"] + res["prospect"]["outreachDraft"]["subject"]
    )
