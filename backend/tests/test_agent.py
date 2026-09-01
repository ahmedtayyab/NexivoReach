import pytest
import asyncio
from app.providers.factory import get_ai_provider
from app.tools.score_calculator import ScoreCalculatorTool
from app.agents.prospecting_agent import ProspectingAgent

def test_score_calculator():
    calc = ScoreCalculatorTool()
    res = calc.calculate_fit_score(
        company_industry="Commercial Fitness Club",
        company_location="Dubai, UAE",
        target_countries=["United Arab Emirates"],
        buying_signals=[{"signal": "New Location Opening", "weight": 20}],
        product_matches=[{"productName": "Power Rack", "fitLevel": "High"}, {"productName": "Cable Crossover", "fitLevel": "High"}]
    )
    assert res["total_score"] >= 80
    assert res["breakdown"]["industryFit"] == 25
    assert res["breakdown"]["locationFit"] == 20

@pytest.mark.asyncio
async def test_ai_provider():
    provider = get_ai_provider()
    profile = await provider.extract_business_profile("We manufacture gym equipment in Pakistan.")
    assert "name" in profile
    assert profile["extracted_by_ai"] is True

@pytest.mark.asyncio
async def test_agent_execution():
    agent = ProspectingAgent()
    res = await agent.execute_discovery_goal(
        user_prompt="Find commercial gyms in UAE needing power racks.",
        products=[{"name": "Commercial Power Rack"}],
        icp={"targetCountries": ["United Arab Emirates"]}
    )
    assert "prospect" in res
    assert res["prospect"]["fitScore"] >= 80
    assert len(res["agent_log"]["decisions"]) == 6
