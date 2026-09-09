import pytest
from app.agents.outreach_strategy import (
    build_outreach_brief,
    heuristic_quality_check,
    render_fallback_email,
)
from app.providers.fallback import FallbackProvider


def test_brief_prefers_expansion_signal_over_weak_copy():
    brief = build_outreach_brief(
        company_name="ABC Fitness",
        why_prospect="ABC Fitness is a gym chain that may buy commercial equipment.",
        why_now="Opening two new locations in Texas this quarter.",
        signals=[
            {
                "signal": "Opening two new locations in Texas",
                "whyItMatters": "intent",
            }
        ],
        matched_products=[
            {
                "productName": "Commercial treadmills",
                "fitLevel": "High",
                "reasoning": "Fits multi-location fitness outfitting.",
            }
        ],
        seller_name="Alwasi",
        intent="high",
        fit_summary="high",
    )
    assert brief["signal_confidence"] in ("high", "medium")
    assert brief["angle"] in ("expansion", "trigger", "product_fit")
    assert "Texas" in brief["primary_signal"] or "Texas" in brief["why_now"]
    assert brief["matched_product"] == "Commercial treadmills"
    assert "may" in brief["pain_hypothesis"].lower() or "can" in brief["pain_hypothesis"].lower()


def test_low_confidence_does_not_fabricate_timing():
    brief = build_outreach_brief(
        company_name="Quiet Co",
        why_prospect="Appears related to apparel wholesale.",
        why_now="",
        signals=[],
        matched_products=[{"productName": "Hoodies", "fitLevel": "Medium", "reasoning": "Category overlap."}],
        seller_name="Alwasi",
        intent="none",
    )
    assert brief["signal_confidence"] == "low"
    draft = render_fallback_email(brief)
    low = draft["body"].lower()
    assert "you recently" not in low
    assert "new locations you're opening" not in low
    assert draft["outreachRationale"]["signal_confidence"] == "low"
    ok, issues = heuristic_quality_check(draft, brief)
    assert ok, issues


def test_qc_rejects_banned_opener_and_fake_timing():
    brief = build_outreach_brief(
        company_name="Acme",
        why_prospect="Possible distributor.",
        seller_name="Seller",
    )
    bad = {
        "subject": "Hello",
        "body": (
            "I hope you're doing well.\n\n"
            "You recently opened new locations across Texas and we can help.\n\n"
            "Best,\nSeller"
        ),
    }
    ok, issues = heuristic_quality_check(bad, brief)
    assert ok is False
    assert any("banned_opener" in i or i == "fabricated_timing" or i == "too_short" for i in issues)


@pytest.mark.asyncio
async def test_fallback_personalized_is_commercially_structured():
    draft = await FallbackProvider().generate_personalized_outreach(
        company_name="Summit Gyms",
        why_prospect="Summit Gyms runs commercial fitness clubs and buys equipment in volume.",
        why_now="Expanding with a new facility in Denver.",
        signals=[{"signal": "New facility in Denver", "whyItMatters": "intent"}],
        matched_products=[
            {"productName": "Power racks", "fitLevel": "High", "reasoning": "Commercial gym fit."}
        ],
        seller_name="Alwasi Gear",
        intent="high",
        fit_summary="high",
    )
    assert draft["subject"]
    assert "Summit Gyms" in draft["body"]
    assert "Alwasi Gear" in draft["body"]
    assert draft.get("outreachRationale", {}).get("matched_product") == "Power racks"
    words = len(draft["body"].split())
    assert words >= 70
    assert "I hope you're doing well" not in draft["body"]
