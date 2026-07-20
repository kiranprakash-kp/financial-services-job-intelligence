"""Location normalization and US validation.

Two entry points:
- `normalize_structured_location` — a source already gives separate city/state/
  country fields (Wells Fargo's feed, Goldman Sachs' GraphQL `locations{}`).
- `parse_location_text` — only a combined free-text string is available (e.g.
  BNY's `PrimaryLocation` "Lake Mary, FL, United States", or a generic fallback).
  Handles multi-location strings, "Remote - United States", "Multiple
  Locations", and malformed input without raising.

Never rely solely on a source's own country/URL filter — every record is
validated here after extraction.
"""

from __future__ import annotations

import re

from ..domain.models import NormalizedLocation

US_STATE_NAME_TO_ABBR: dict[str, str] = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District Of Columbia": "DC",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
    "Puerto Rico": "PR",
}
US_STATE_ABBRS: frozenset[str] = frozenset(US_STATE_NAME_TO_ABBR.values())

_US_COUNTRY_ALIASES = {
    "united states",
    "united states of america",
    "usa",
    "u.s.",
    "u.s.a.",
    "us",
}
_MULTI_SEPARATORS = re.compile(r"\s*;\s*|\s+/\s+")


def _normalize_country(country: str | None) -> str | None:
    if not country:
        return None
    cleaned = country.strip()
    return "United States" if cleaned.lower() in _US_COUNTRY_ALIASES else cleaned


def normalize_structured_location(
    city: str | None,
    state: str | None,
    country: str | None,
    is_primary: bool = True,
) -> NormalizedLocation:
    """Build a NormalizedLocation from a source's own separate fields."""
    country_norm = _normalize_country(country)
    is_us = country_norm == "United States"

    state_abbr = None
    if state:
        stripped = state.strip()
        if stripped.upper() in US_STATE_ABBRS:
            state_abbr = stripped.upper()
        elif stripped.title() in US_STATE_NAME_TO_ABBR:
            state_abbr = US_STATE_NAME_TO_ABBR[stripped.title()]
        if state_abbr:
            is_us = True
            country_norm = "United States"

    city_norm = city.strip().title() if city and city.strip() else None
    text = ", ".join(p for p in [city_norm, state_abbr or state, country_norm] if p) or "Unknown"

    return NormalizedLocation(
        location_text=text,
        city=city_norm,
        state=state_abbr,
        country=country_norm,
        is_us=is_us,
        is_remote=False,
        is_primary=is_primary,
    )


def _parse_single(part: str) -> NormalizedLocation:
    part = part.strip()
    if not part:
        return NormalizedLocation(location_text=part, is_us=False)

    lower = part.lower()

    if lower == "multiple locations":
        # Ambiguous placeholder text; preserved verbatim, not resolved to a country.
        return NormalizedLocation(location_text=part, is_us=False, is_remote=False)

    if "remote" in lower and any(alias in lower for alias in _US_COUNTRY_ALIASES):
        return NormalizedLocation(
            location_text=part, is_us=True, is_remote=True, country="United States"
        )

    if lower in _US_COUNTRY_ALIASES:
        return NormalizedLocation(location_text=part, is_us=True, country="United States")

    segments = [s.strip() for s in part.split(",") if s.strip()]
    city = state_abbr = country = None

    if len(segments) >= 2:
        city = segments[0]
        candidate = segments[1]
        if candidate.upper() in US_STATE_ABBRS:
            state_abbr = candidate.upper()
            country = "United States"
        elif candidate.title() in US_STATE_NAME_TO_ABBR:
            state_abbr = US_STATE_NAME_TO_ABBR[candidate.title()]
            country = "United States"
        else:
            country = candidate
        if len(segments) >= 3:
            country = _normalize_country(segments[2]) or country
    elif segments:
        # A bare single segment that is itself a full US state name (e.g. "New
        # York" split off "New York / London") is treated as that US state.
        candidate = segments[0]
        if candidate.upper() in US_STATE_ABBRS:
            state_abbr = candidate.upper()
            country = "United States"
            city = candidate
        elif candidate.title() in US_STATE_NAME_TO_ABBR:
            state_abbr = US_STATE_NAME_TO_ABBR[candidate.title()]
            country = "United States"
            city = candidate
        else:
            city = candidate

    country = _normalize_country(country)
    is_us = state_abbr is not None or country == "United States"

    return NormalizedLocation(
        location_text=part,
        city=city,
        state=state_abbr,
        country=country,
        is_us=is_us,
    )


def parse_location_text(text: str | None) -> list[NormalizedLocation]:
    """Parse a free-text location string, possibly containing multiple locations."""
    if not text or not text.strip():
        return []
    parts = _MULTI_SEPARATORS.split(text.strip())
    return [_parse_single(p) for p in parts if p.strip()]
