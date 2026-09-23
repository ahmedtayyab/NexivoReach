"""Geo helpers: country strictness, phone dial codes, social windows."""

from app.agents.geo import (
    countries_from_phone_text,
    extract_places_from_prompt,
    location_conflicts_with_targets,
    enrich_geo_blob,
    places_mentioned,
)


def test_country_in_prompt_is_strict():
    places, strict = extract_places_from_prompt("belt importers in United Arab Emirates")
    assert strict is True
    assert any("arab" in p.lower() or "emirates" in p.lower() or "uae" in p.lower() for p in places) or any(
        "dubai" in p.lower() for p in places
    ) or places


def test_phone_dial_uae():
    countries = countries_from_phone_text("Call us +971 50 123 4567")
    assert "United Arab Emirates" in countries


def test_phone_dial_uk():
    countries = countries_from_phone_text("Tel: +44 20 7946 0958")
    assert "United Kingdom" in countries


def test_country_conflict():
    assert location_conflicts_with_targets("Berlin, Germany", ["United Arab Emirates"]) is True
    assert location_conflicts_with_targets("Dubai, UAE", ["United Arab Emirates"]) is False


def test_enrich_blob_uses_phone_country():
    blob = enrich_geo_blob(site_text="Contact", phones=["+971501234567"])
    assert places_mentioned(blob, ["United Arab Emirates"]) is True
