"""Tests for paginated Google research / discovery memory."""

from __future__ import annotations

import pytest

from app.services.paginated_discovery import (
    HuntBudget,
    _build_intents_from_prompt,
    _fingerprint,
    should_fetch_intent_page,
)


def test_duckduckgo_more_results_form_is_kept():
    from app.tools.web_search import parse_duckduckgo_html

    html = """
    <div class="result">
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fmidwestsportsupply.com%2Fknee">Midwest</a>
      <a class="result__snippet">Knee sleeves</a>
    </div>
    <form action="/html/" method="post">
      <input type="hidden" name="q" value="knee sleeves ohio">
      <input type="hidden" name="s" value="10">
      <input type="hidden" name="dc" value="11">
      <input type="hidden" name="vqd" value="4-token">
      <input type="submit" value="More results">
    </form>
    """
    parsed = parse_duckduckgo_html(html)
    assert parsed["hits"][0]["href"] == "https://midwestsportsupply.com/knee"
    assert parsed["next_form"]["vqd"] == "4-token"
    assert parsed["next_form"]["s"] == "10"


def test_domain_country_iso_reads_cctld_not_com():
    from app.services.paginated_discovery import domain_country_iso

    assert domain_country_iso("physiostore.ca") == "CA"
    assert domain_country_iso("www.fitnessnutrition.ca") == "CA"
    assert domain_country_iso("shop.co.uk") == "GB"
    assert domain_country_iso("gym.com.au") == "AU"
    assert domain_country_iso("example.com") == ""
    assert domain_country_iso("nordiclifting.com") == ""


def test_listing_matches_hunt_country_uses_cctld_or_snippet():
    from app.services.paginated_discovery import listing_matches_hunt_country

    assert listing_matches_hunt_country(
        "physiostore.ca",
        "Knee Sleeves in Canada | Physio Store",
        "",
        "Canada",
    )
    assert listing_matches_hunt_country(
        "xtcfitness.ca",
        "Sling Shot | STrong Knee Sleeves",
        "",
        "Canada",
    )
    assert listing_matches_hunt_country(
        "someshop.com",
        "Gym shop Toronto",
        "Weightlifting gear in Canada",
        "Canada",
    )
    assert not listing_matches_hunt_country(
        "randomshop.com",
        "Knee sleeves for sale",
        "Free shipping",
        "Canada",
    )


def test_geo_targeted_dotcom_listing_is_keepable_in_a_new_country():
    from app.services.paginated_discovery import listing_is_keepable_for_hunt

    # UAE / Mexico / Singapore shops mostly use .com and do not say the country
    # in the snippet. The hunt query already named the country.
    assert listing_is_keepable_for_hunt(
        "dubaigymgear.com",
        "Dubai Gym Gear — knee sleeves",
        "Wholesale lifting gear",
        "United Arab Emirates",
        categories=["knee sleeves"],
    )
    assert listing_is_keepable_for_hunt(
        "tiendafitness.mx",
        "Tienda Fitness",
        "Rodilleras y straps",
        "Mexico",
        categories=["knee sleeves"],
    )
    # A German ccTLD is not a Canadian buyer.
    assert not listing_is_keepable_for_hunt(
        "shop.de",
        "Kniebandagen",
        "Versand in Deutschland",
        "Canada",
        categories=["knee sleeves"],
    )
    assert not listing_is_keepable_for_hunt(
        "jeweler.com",
        "Diamond rings and gold",
        "Jewelry store",
        "United Arab Emirates",
        categories=["knee sleeves"],
    )


def test_backup_ladder_keeps_the_product_words():
    from app.services.paginated_discovery import backup_query_ladder, resume_backup_query

    knee = backup_query_ladder("fitness knee sleeves importers Ohio", "Ohio")
    assert knee[0] == "fitness knee sleeves importers Ohio"
    assert "fitness knee sleeves importer Ohio" in knee
    assert all("Ohio" in item for item in knee)
    assert "fitness knee sleeves importers" not in knee
    assert "knee sleeves importers" not in knee
    hooks = backup_query_ladder(
        "weightlifting hooks distributors United Kingdom",
        "United Kingdom",
    )
    assert "hooks distributors" not in [item.lower() for item in hooks]
    assert all("weightlifting" in item.lower() for item in hooks)
    assert all("united kingdom" in item.lower() for item in hooks)
    wraps = backup_query_ladder("wrist wraps weightlifting distributors Ohio", "Ohio")
    assert wraps[0] == "wrist wraps weightlifting distributors Ohio"
    assert all("Ohio" in item for item in wraps)
    assert "wrist wraps weightlifting distributors" not in wraps
    assert "wraps weightlifting distributors" not in [item.lower() for item in wraps]
    canada = backup_query_ladder("gym knee sleeves wholesale Canada", "Canada")
    assert all(item.endswith("Canada") for item in canada)
    assert resume_backup_query("straps distributors", hooks) == 0
    assert resume_backup_query(hooks[0], hooks) == 0
    # An old cursor that dropped the country starts the kept-place ladder over.
    assert resume_backup_query("fitness knee sleeves importers", knee) == 0


def test_saved_more_results_cursor_resumes_the_next_batch():
    from app.services.paginated_discovery import _ddg_cursor_json, _parse_ddg_cursor

    raw = _ddg_cursor_json(fields={"q": "knee", "vqd": "4-token", "s": "10"}, batch=2)
    state = _parse_ddg_cursor(raw)
    assert state["batch"] == 2
    assert state["fields"]["vqd"] == "4-token"
    assert state["exhausted"] is False


def test_duckduckgo_stops_after_the_first_empty_later_page():
    from app.services.paginated_discovery import should_stop_backup_after_empty

    assert should_stop_backup_after_empty(had_results=True, page=2) is True
    assert should_stop_backup_after_empty(had_results=False, page=2) is True
    assert should_stop_backup_after_empty(had_results=False, page=1) is False


def test_backup_page_stops_when_most_companies_are_already_known():
    from app.services.paginated_discovery import backup_page_mostly_known

    assert backup_page_mostly_known(9, 10) is True
    assert backup_page_mostly_known(8, 10) is False
    assert backup_page_mostly_known(4, 10) is False
    assert backup_page_mostly_known(5, 5) is False  # too few results to judge
    # A page with new companies to open must keep paginating the same query.


def test_sheet_company_is_skipped_and_new_details_stay_on_that_row():
    from app.integrations.sheets import merge_existing_lead_row
    from app.services.paginated_discovery import lead_already_in_sheet

    assert lead_already_in_sheet("gymreapers.com", "Other Co", {"gymreapers.com"}, set())
    assert lead_already_in_sheet("", "Acme Inc.", set(), {"acme"})
    assert lead_already_in_sheet("new-wholesale.com", "New Wholesale", {"gymreapers.com"}, {"acme"}) is False

    existing = [""] * 20
    existing[1] = "Acme"
    existing[10] = "Contacted"
    existing[17] = "said no"
    incoming = [""] * 20
    incoming[1] = "Acme"
    incoming[3] = "buyer@acme.com"
    incoming[10] = "To contact"
    incoming[19] = "2026-10-04"
    merged = merge_existing_lead_row(existing, incoming)
    assert merged[3] == "buyer@acme.com"
    assert merged[10] == "Contacted"
    assert merged[17] == "said no"


def test_sheet_sent_status_skips_only_emailed_rows():
    from app.integrations.sheets import is_sent_sheet_status

    assert is_sent_sheet_status("Contacted") is True
    assert is_sent_sheet_status("Replied") is True
    assert is_sent_sheet_status("To contact") is False
    assert is_sent_sheet_status("") is False


def test_backup_uses_yahoo_when_duckduckgo_returns_nothing():
    from app.tools.web_search import WebSearchTool

    tool = WebSearchTool()
    calls = {"ddg": 0, "yahoo_pages": []}

    def _ddg(query, form=None):
        calls["ddg"] += 1
        return {
            "hits": [],
            "next_form": None,
            "provider": "duckduckgo",
            "error": "DuckDuckGo search failed: timed out",
            "fallback": True,
            "html_down": True,
        }

    def _yahoo(query, page):
        calls["yahoo_pages"].append(page)
        return [{"title": "RDX", "href": "https://wholesale.rdxsports.com/knee", "body": "wholesale"}]

    tool._duckduckgo_more = _ddg  # type: ignore[method-assign]
    tool._yahoo_hits = _yahoo  # type: ignore[method-assign]
    report = tool.search_backup_page("gym knee sleeves distributors Ohio")
    assert report["provider"] == "yahoo"
    assert report["error"] == ""
    assert report["hits"][0]["href"] == "https://wholesale.rdxsports.com/knee"
    assert report["next_form"]["page"] == "2"
    again = tool.search_backup_page("fitness knee sleeves importers Ohio")
    assert again["provider"] == "yahoo"
    assert calls["ddg"] == 1
    assert calls["yahoo_pages"] == [1, 1]
    continued = tool.search_backup_page(
        "gym knee sleeves distributors Ohio",
        form={"engine": "yahoo", "page": "2"},
    )
    assert calls["yahoo_pages"] == [1, 1, 2]
    assert continued["next_form"]["page"] == "3"


def test_yahoo_region_follows_the_hunt_country():
    from app.tools.web_search import yahoo_region_for_iso

    assert yahoo_region_for_iso("GB") == "uk-en"
    assert yahoo_region_for_iso("AU") == "au-en"
    assert yahoo_region_for_iso("CA") == "ca-en"
    assert yahoo_region_for_iso("US") == "us-en"
    assert yahoo_region_for_iso("") == "us-en"


@pytest.mark.asyncio
async def test_call_with_deadline_moves_on_when_a_task_hangs():
    import asyncio

    from app.services.paginated_discovery import call_with_deadline

    async def hang():
        await asyncio.sleep(30)
        return "done"

    started = asyncio.get_event_loop().time()
    result = await call_with_deadline(hang(), 0.2, "skipped")
    elapsed = asyncio.get_event_loop().time() - started
    assert result == "skipped"
    assert elapsed < 2.0


def test_running_hunt_is_stale_after_silence():
    from datetime import datetime, timedelta, timezone

    from app.api.discovery import hunt_job_is_stale

    now = datetime(2026, 10, 27, 18, 20, tzinfo=timezone.utc)
    fresh = (now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - timedelta(minutes=13)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert hunt_job_is_stale(fresh, now=now) is False
    assert hunt_job_is_stale(old, now=now) is True
    assert hunt_job_is_stale("", now=now) is False


def test_serper_out_of_credits_is_detected():
    from app.tools.web_search import serper_out_of_credits

    assert serper_out_of_credits("Serper Google search failed: Serper 400: Not enough credits")
    assert serper_out_of_credits("not enough credits") is True
    assert serper_out_of_credits("Serper 400: Query is required") is False


def test_serper_failure_includes_response_message():
    from app.tools.web_search import serper_failure_message

    msg = serper_failure_message(400, '{"message":"Not enough credits","statusCode":400}')
    assert "Not enough credits" in msg
    assert msg.startswith("Serper 400:")


def test_serper_includes_sponsored_businesses():
    from app.tools.web_search import serper_hits

    hits = serper_hits(
        {
            "organic": [
                {
                    "title": "Martin Sports Wholesale",
                    "link": "https://www.martinsports.com/",
                    "snippet": "Team and equipment bags",
                }
            ],
            "ads": [
                {
                    "title": "Wholesale and B2B – Zumer Sport",
                    "link": "https://www.zumersport.com/",
                    "snippet": "Bulk orders for resale",
                },
                {
                    "title": "Martin Sports again",
                    "link": "https://www.martinsports.com",
                    "snippet": "duplicate of organic",
                },
            ],
        }
    )
    hrefs = [h["href"] for h in hits]
    assert "https://www.martinsports.com/" in hrefs
    assert "https://www.zumersport.com/" in hrefs
    assert len(hits) == 2


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


def test_funnel_counts_each_drop():
    from app.services.paginated_discovery import HuntStats, _bump_funnel, funnel_report

    stats = HuntStats()
    _bump_funnel(stats, "sports bags distributors", "serp_results", 10)
    _bump_funnel(stats, "sports bags distributors", "junk_filtered", 2)
    _bump_funnel(stats, "sports bags distributors", "already_seen", 3)
    _bump_funnel(stats, "sports bags distributors", "leads_created", 4)
    report = funnel_report(stats)
    assert "Google results: 10" in report
    assert "Filtered directories/marketplaces/news: 2" in report
    assert "Already seen: 3" in report
    assert "New leads created: 4" in report
    assert stats.funnel_by_intent["sports bags distributors"]["leads_created"] == 4


def test_leads_split_evenly_across_hunt_lines():
    from app.services.app_settings import leads_per_intent_share

    assert leads_per_intent_share(40, 5) == 8
    assert leads_per_intent_share(40, 15) == 3
    assert leads_per_intent_share(30, 5) == 6
    assert leads_per_intent_share(40, 1) == 40


def test_manual_leads_match_by_website_and_name():
    from app.integrations.sheets import _lead_match_keys

    websites, names = _lead_match_keys([
        {"company_name": "Acme Supply", "website": "https://acme.example", "stage": "Manual"},
    ])
    assert websites == {"https://acme.example"}
    assert names == {"acme supply"}


def test_running_hunt_does_not_say_it_stopped_before_searching():
    from app.services.paginated_discovery import HuntStats, _stop_summary, _telemetry_payload

    stats = HuntStats()
    payload = _telemetry_payload(stats, [], "")
    assert payload["stopSummary"] == ""
    assert _stop_summary(stats) == "The hunt stopped before any search ran."


def test_google_search_gives_up_when_it_does_not_answer(monkeypatch):
    import asyncio
    import time

    from app.tools import web_search

    monkeypatch.setattr(web_search, "SERPER_WAIT_SEC", 0.2)

    def hang(self, query, page, num):
        del self, query, page, num
        time.sleep(5)
        return {"hits": [], "provider": "serper", "error": ""}

    monkeypatch.setattr(web_search.WebSearchTool, "_search_sync_paged", hang)
    started = time.time()
    report = asyncio.run(web_search.WebSearchTool().search_organic_page("straps distributors Michigan"))
    assert report["timed_out"] is True
    assert time.time() - started < 2
