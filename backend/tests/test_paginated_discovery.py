"""Tests for paginated Google research / discovery memory."""

from __future__ import annotations

from app.services.paginated_discovery import (
    HuntBudget,
    _build_intents_from_prompt,
    _fingerprint,
    should_fetch_intent_page,
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


def test_page_budget_is_per_run_not_absolute_page_number():
    # Cursor already at page 11, this run has not fetched yet → still fetch.
    assert should_fetch_intent_page(pages_processed_this_run=0, pages_per_run=10) is True
    assert should_fetch_intent_page(pages_processed_this_run=0, pages_per_run=5) is True
    # Five new pages consumed this run (e.g. 11–15) → stop until the next hunt.
    assert should_fetch_intent_page(pages_processed_this_run=5, pages_per_run=5) is False
    assert should_fetch_intent_page(pages_processed_this_run=4, pages_per_run=5) is True


def test_one_blank_page_does_not_finish_the_search():
    from app.services.paginated_discovery import should_exhaust_after_gaps

    assert should_exhaust_after_gaps(1, 2) is False
    assert should_exhaust_after_gaps(3, 4) is False
    assert should_exhaust_after_gaps(3, 8) is True


def test_leads_split_evenly_across_hunt_lines():
    from app.services.app_settings import leads_per_intent_share

    assert leads_per_intent_share(40, 5) == 8
    assert leads_per_intent_share(40, 15) == 3
    assert leads_per_intent_share(30, 5) == 6
    assert leads_per_intent_share(40, 1) == 40
