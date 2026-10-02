"""Tests for paginated Google research / discovery memory."""

from __future__ import annotations

import asyncio

from app.services.paginated_discovery import (
    HuntBudget,
    _build_intents_from_prompt,
    _fingerprint,
    update_barren_streak,
)


def test_build_intents_one_per_hunt_line_with_location():
    prompt = (
        "Target location: Dallas, United States\n\n"
        "Priority hunt lines:\n"
        "weightlifting straps distributors\n"
        "weightlifting straps wholesalers\n"
        "weightlifting belts distributors\n"
    )
    intents = _build_intents_from_prompt(prompt, "Dallas, United States")
    assert len(intents) >= 3
    queries = [i["query"].lower() for i in intents]
    assert any("weightlifting straps distributors" in q and "dallas" in q for q in queries)
    assert any("weightlifting straps wholesalers" in q and "dallas" in q for q in queries)
    assert any("weightlifting belts distributors" in q and "dallas" in q for q in queries)
    # Exact products — no generic fitness rewrite
    assert not any("fitness equipment" in q for q in queries)
    # Client format: no forced "in" between role and location
    assert any(q.endswith("dallas, united states") or "dallas, united states" in q for q in queries)


def test_build_intents_preserves_all_fifteen_lines():
    lines = [
        "weightlifting straps distributors",
        "weightlifting straps wholesalers",
        "weightlifting straps importers",
        "weightlifting belts distributors",
        "weightlifting belts wholesalers",
        "weightlifting belts importers",
        "wrist wraps distributors",
        "wrist wraps wholesalers",
        "knee sleeves distributors",
        "knee sleeves wholesalers",
        "lifting hooks distributors",
        "lifting hooks wholesalers",
        "martial arts belts distributors",
        "martial arts belts wholesalers",
        "martial arts belts importers",
    ]
    prompt = "\n".join(lines)
    intents = _build_intents_from_prompt(prompt, "Dallas, United States")
    assert len(intents) == 15
    assert len({i["query"] for i in intents}) == 15


def test_fingerprint_detects_repeated_pages():
    a = _fingerprint(["a.com", "b.com", "c.com"])
    b = _fingerprint(["c.com", "a.com", "b.com"])
    c = _fingerprint(["a.com", "b.com", "d.com"])
    assert a == b
    assert a != c


def test_hunt_budget_defaults_are_safety_not_lead_caps():
    b = HuntBudget()
    assert b.max_pages_per_intent >= 5
    assert b.max_total_pages >= 50
    assert b.leads_per_run >= 5
    # Barren early-stop stays off by default.
    assert b.barren_pages_stop == 0


def test_leads_split_evenly_across_hunt_lines():
    from app.services.app_settings import leads_per_intent_share

    assert leads_per_intent_share(40, 5) == 8
    assert leads_per_intent_share(40, 15) == 3
    assert leads_per_intent_share(30, 5) == 6
    assert leads_per_intent_share(40, 1) == 40


def test_barren_streak_stops_after_n_empty_pages():
    streak, stop = update_barren_streak(0, 0, 3)
    assert streak == 1 and stop is False
    streak, stop = update_barren_streak(streak, 0, 3)
    assert streak == 2 and stop is False
    streak, stop = update_barren_streak(streak, 0, 3)
    assert streak == 3 and stop is True


def test_barren_streak_disabled_when_limit_zero():
    streak, stop = update_barren_streak(0, 0, 0)
    assert streak == 0 and stop is False
    streak, stop = update_barren_streak(99, 0, 0)
    assert streak == 0 and stop is False


def test_barren_streak_resets_when_new_domains_found():
    streak, stop = update_barren_streak(2, 4, 3)
    assert streak == 0 and stop is False


def test_enrich_website_light_skips_discover_contacts(monkeypatch):
    """Light pass must not call discover_contacts / Hunter."""
    import app.services.enrichment as enrich_mod

    called = {"discover": 0, "hunter": 0}

    async def fake_scrape(self, website, limit=8000, keep_html=True):
        return {
            "text": "Wholesale gym gear New York",
            "html": "<html/>",
            "emails": [],
            "location": "New York, NY",
        }

    async def fake_discover(**kwargs):
        called["discover"] += 1
        return {"email": "", "phone": "", "contacts": []}

    async def fake_hunter(domain):
        called["hunter"] += 1
        return {"email": "", "contacts": []}

    monkeypatch.setattr(enrich_mod.WebSearchTool, "scrape_homepage", fake_scrape)
    monkeypatch.setattr(enrich_mod, "discover_contacts", fake_discover)
    monkeypatch.setattr(enrich_mod, "hunter_domain_search", fake_hunter)

    out = asyncio.run(
        enrich_mod.enrich_website(
            "https://example.com",
            use_hunter=True,
            deep_contacts=False,
        )
    )
    assert called["discover"] == 0
    assert called["hunter"] == 0
    assert "New York" in (out.get("site_text") or "")
