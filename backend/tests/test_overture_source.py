import json

from app.services import business_sources as bs


def _rows():
    def row(name, site, cat="gym", email="", conf=0.8, i=1):
        return {"name": name, "cat": cat, "website": site, "email": email, "phone": "", "street": "1 Main St",
                "city": "Toronto", "region": "ON", "confidence": conf, "id": f"id{i}"}

    return [
        row("Alpha Gym", "https://alphagym.ca/", i=1),
        row("Beta Physio", "https://www.betaphysio.ca/about", cat="physical_therapy", email="hi@betaphysio.ca", conf=0.5, i=2),
        row("Beta Physio 2", "https://betaphysio.ca/", cat="physical_therapy", i=3),
        row("Social Only", "https://www.facebook.com/somegym", i=4),
        row("Linktree", "https://linktr.ee/gym", i=5),
        row("Gamma Boxing", "https://gammaboxing.ca/", cat="boxing_gym", conf=0.9, i=6),
    ]


def test_categories_follow_the_trade_families():
    cats = bs.overture_categories_for(["rehab", "combat"], [])
    assert "physical_therapy" in cats and "martial_arts_club" in cats
    assert "gym" not in cats


def test_non_sports_hunts_match_buyer_words_to_category_names():
    cats = bs.overture_categories_for([], ["gift shops", "greeting card stores"])
    assert "gift_shop" in cats


def test_candidates_dedupe_hosts_drop_social_and_put_emails_first(monkeypatch, tmp_path):
    monkeypatch.setattr(bs, "overture_release", lambda: "test")
    monkeypatch.setattr(bs, "_overture_query", lambda release, bbox, cats: _rows())
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    bs._overture_mem_cache.clear()
    cands = bs.overture_candidates((43.5, -79.6, 43.9, -79.1), ["gym"], "Canada")
    hosts = [bs._host(c.website) for c in cands]
    assert hosts[0] == "betaphysio.ca"  # the one with an email
    assert hosts.count("betaphysio.ca") == 1
    assert "facebook.com" not in hosts and "linktr.ee" not in hosts
    assert cands[0].email == "hi@betaphysio.ca"
    assert cands[0].address.endswith("Canada")
    assert all(c.source == "overture" for c in cands)


def test_step_pages_through_the_city_and_marks_the_end(monkeypatch, tmp_path):
    monkeypatch.setattr(bs, "overture_release", lambda: "test")
    big = []
    for n in range(95):
        big.append({"name": f"Biz {n}", "cat": "gym", "website": f"https://biz{n}.ca/", "email": "",
                    "phone": "", "street": "", "city": "Toronto", "region": "ON", "confidence": 0.9 - n / 1000, "id": f"i{n}"})
    monkeypatch.setattr(bs, "_overture_query", lambda release, bbox, cats: big)
    monkeypatch.setattr(bs, "geocode_bbox", lambda city, iso, client=None: (43.58, -79.64, 43.86, -79.12))
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    bs._overture_mem_cache.clear()

    first = bs.overture_step(city="Toronto", iso="CA", country_label="Canada", categories=["gym"])
    assert len(first.candidates) == bs.OVERTURE_PAGE
    assert first.exhausted is False
    assert json.loads(first.next_cursor)["o"] == bs.OVERTURE_PAGE

    cursor = first.next_cursor
    seen = len(first.candidates)
    for _ in range(5):
        step = bs.overture_step(city="Toronto", iso="CA", country_label="Canada", categories=["gym"], cursor=cursor)
        seen += len(step.candidates)
        cursor = step.next_cursor
        if step.exhausted:
            break
    assert seen == 95
    assert step.exhausted is True and step.next_cursor == ""


def test_step_without_a_map_position_or_categories_stops_cleanly(monkeypatch):
    monkeypatch.setattr(bs, "geocode_bbox", lambda city, iso, client=None: (0.0, 0.0, 0.0, 0.0))
    assert bs.overture_step(city="Nowhere", iso="", country_label="", categories=[]).exhausted is True
    step = bs.overture_step(city="Nowhere", iso="", country_label="", categories=["gym"])
    assert step.exhausted is True and "could not place" in step.note
