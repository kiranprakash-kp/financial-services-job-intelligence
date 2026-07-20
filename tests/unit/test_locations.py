"""Location parsing edge cases — the exact set required by the spec, plus the
structured-field path used by adapters that already split city/state/country.
"""

from __future__ import annotations

from job_intelligence.processing.locations import (
    normalize_structured_location,
    parse_location_text,
)


def test_city_state_two_letter() -> None:
    [loc] = parse_location_text("New York, NY")
    assert loc.is_us and loc.city == "New York" and loc.state == "NY"


def test_city_state_two_letter_jersey_city() -> None:
    [loc] = parse_location_text("Jersey City, NJ")
    assert loc.is_us and loc.state == "NJ"


def test_remote_united_states() -> None:
    [loc] = parse_location_text("Remote - United States")
    assert loc.is_us and loc.is_remote


def test_bare_united_states() -> None:
    [loc] = parse_location_text("United States")
    assert loc.is_us and not loc.is_remote


def test_multi_location_slash_separated() -> None:
    locs = parse_location_text("New York / London")
    assert len(locs) == 2
    ny, london = locs
    assert ny.is_us and ny.state == "NY"
    assert not london.is_us


def test_multi_location_semicolon_separated() -> None:
    locs = parse_location_text("Dallas, TX; Bengaluru, India")
    assert len(locs) == 2
    dallas, bengaluru = locs
    assert dallas.is_us and dallas.state == "TX"
    assert not bengaluru.is_us and bengaluru.country == "India"


def test_washington_dc() -> None:
    [loc] = parse_location_text("Washington, DC")
    assert loc.is_us and loc.state == "DC" and loc.city == "Washington"


def test_multiple_locations_placeholder_is_not_resolved() -> None:
    [loc] = parse_location_text("Multiple Locations")
    assert not loc.is_us
    assert loc.location_text == "Multiple Locations"


def test_empty_and_malformed_input_never_raises() -> None:
    assert parse_location_text("") == []
    assert parse_location_text(None) == []
    [loc] = parse_location_text("   ,,  ")
    assert not loc.is_us


def test_structured_location_full_state_name() -> None:
    loc = normalize_structured_location(
        city="CHARLOTTE", state="North Carolina", country="United States of America"
    )
    assert loc.is_us and loc.state == "NC" and loc.city == "Charlotte"
    assert loc.country == "United States"


def test_structured_location_non_us() -> None:
    loc = normalize_structured_location(
        city="TAGUIG CITY", state="National Capital Region (Manila)", country="Philippines"
    )
    assert not loc.is_us
    assert loc.country == "Philippines"


def test_structured_location_dc() -> None:
    loc = normalize_structured_location(
        city="WASHINGTON", state="District of Columbia", country="United States of America"
    )
    assert loc.is_us and loc.state == "DC"
