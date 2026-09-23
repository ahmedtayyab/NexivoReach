"""Tests for category-safe outreach template selection."""

from app.agents.template_selector import (
    build_lead_signals,
    select_outreach_template,
    fill_outreach_template,
)


BOXING = {
    "id": "1",
    "name": "Boxing intro",
    "category": "Boxing",
    "tags": ["boxing", "mma", "gloves", "hand wraps"],
    "subject": "Intro — {{seller}}",
    "body": "Hey {{company}},\n\n{{specialize}}\n",
    "specializeLines": ["Boxing gloves", "MMA gloves"],
}

LIFTING = {
    "id": "2",
    "name": "Weightlifting intro",
    "category": "Weightlifting",
    "tags": ["weightlifting", "straps", "belts", "lifting"],
    "subject": "Intro — {{seller}}",
    "body": "Hey {{company}},\n\n{{specialize}}\n",
    "specializeLines": ["Weight lifting straps", "Belts"],
}


def test_boxing_lead_gets_boxing_not_lifting():
    signals = build_lead_signals(
        company_name="Bell Ringer Boxing",
        industry="Martial arts retail",
        why_prospect="Boxing gloves buyer and wholesaler",
        product_fit=[{"productName": "Boxing gloves", "fitLevel": "High", "reasoning": "sells gloves"}],
        catalog_products=[
            {"name": "Boxing gloves", "category": "Boxing"},
            {"name": "Lifting straps", "category": "Weightlifting"},
        ],
    )
    picked = select_outreach_template([BOXING, LIFTING], signals)
    assert picked is not None
    assert picked["id"] == "1"
    assert picked["category"] == "Boxing"


def test_lifting_lead_gets_lifting_not_boxing():
    signals = build_lead_signals(
        company_name="Awaken Fitness",
        industry="Gym",
        why_prospect="Sourcing weightlifting belts and straps",
        product_fit=[{"productName": "Lifting straps", "fitLevel": "High"}],
        catalog_products=[
            {"name": "Boxing gloves", "category": "Boxing"},
            {"name": "Lifting straps", "category": "Weightlifting"},
        ],
    )
    picked = select_outreach_template([BOXING, LIFTING], signals)
    assert picked is not None
    assert picked["category"] == "Weightlifting"


def test_no_safe_match_returns_none():
    signals = build_lead_signals(
        company_name="Valve Co",
        industry="Industrial valves",
        why_prospect="OEM hydraulic valves",
        product_fit=[{"productName": "Ball valves", "fitLevel": "High"}],
        catalog_products=[{"name": "Ball valves", "category": "Industrial Equipment"}],
    )
    picked = select_outreach_template([BOXING, LIFTING], signals)
    assert picked is None


def test_fill_placeholders():
    subject, body = fill_outreach_template(
        subject="Hi {{company}} — {{seller}}",
        body="Hey {{company}},\n\n{{specialize}}\nProduct: {{product}}",
        specialize_lines=["Gloves", "Wraps"],
        vars={"company": "Bell Ringer", "seller": "Alwasi", "product": "Boxing gloves"},
    )
    assert "Bell Ringer" in subject
    assert "Alwasi" in subject
    assert "We specialize in:" in body
    assert "• Gloves" in body
    assert "Boxing gloves" in body
