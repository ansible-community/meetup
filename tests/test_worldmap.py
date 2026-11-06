from __future__ import annotations

import json
import re
import pytest

from tools.common.ansible_event_cities import CITIES, CityInfo
from tools.website.generate_worldmap import MAP_MARKER_COLOR, OUTPUT, normalise_region, render_page


def test_registry_has_coordinates_for_every_location() -> None:
    assert CITIES
    assert all(city.latitude is not None and city.longitude is not None for city in CITIES)
    assert all(-90 <= city.latitude <= 90 and -180 <= city.longitude <= 180 for city in CITIES)  # type: ignore[operator]


@pytest.mark.parametrize(
    ("slug", "latitude_range", "longitude_range"),
    [
        ("mclean", (38.5, 39.5), (-78.0, -76.0)),
        ("pisa", (43.6, 43.8), (10.3, 10.5)),
        ("nova", (38.5, 39.3), (-77.6, -76.9)),
        ("sfbay", (36.7, 38.8), (-123.5, -121.3)),
    ],
)
def test_ambiguous_location_coordinates_are_in_the_expected_region(
    slug: str,
    latitude_range: tuple[float, float],
    longitude_range: tuple[float, float],
) -> None:
    city = next(city for city in CITIES if city.slug == slug)
    assert city.latitude is not None and city.longitude is not None
    assert latitude_range[0] < city.latitude < latitude_range[1]
    assert longitude_range[0] < city.longitude < longitude_range[1]


def test_city_coordinates_must_be_a_pair() -> None:
    with pytest.raises(ValueError, match="both latitude and longitude"):
        CityInfo("Europe", "UK", "london", "London", "Europe/London", latitude=51.5)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (-91, 0), (0, 181), (0, -181), (float("nan"), 0), (0, float("inf"))],
)
def test_city_coordinates_must_be_finite_and_in_range(latitude: float, longitude: float) -> None:
    with pytest.raises(ValueError, match="Invalid (latitude|longitude)"):
        CityInfo("Europe", "UK", "london", "London", "Europe/London", latitude, longitude)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Europe", "Europe, Middle East and Africa"),
        ("EMEA", "Europe, Middle East and Africa"),
        ("NA", "Americas"),
        ("LATAM", "Latin America"),
    ],
)
def test_normalise_region(source: str, expected: str) -> None:
    assert normalise_region(source) == expected


def test_rendered_page_uses_ansible_theme_and_map_controls() -> None:
    page = render_page(
        [
            {
                "slug": "london",
                "city": "<script>alert(1)</script>",
                "country": "UK",
                "region": "Europe",
                "timezone": "Europe/London",
                "lat": 51.5,
                "lon": -0.1,
            }
        ],
        "2026-11-06 10:00 UTC",
    )
    match = re.search(r'<script id="meetup-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    data = json.loads(match.group(1))
    assert data["locations"][0]["city"] == "<script>alert(1)</script>"
    assert data["locations"][0]["timezone"] == "Europe/London"
    assert r"\u003cscript\u003e" in match.group(1)
    assert "events" not in data
    assert "maplibre-gl@^5" in page
    assert "assets/stylesheets/ansible.css" in page
    assert "Red+Hat+Display" in page
    assert "#5bbdbf" in page
    assert MAP_MARKER_COLOR == "#5bbdbf"
    assert f"'circle-color': '{MAP_MARKER_COLOR}'" in page
    assert "new maplibregl.FullscreenControl()" in page
    assert "map.on('click', 'meetup-cluster-count', expandCluster)" in page
    assert OUTPUT.name == "map.html"
    assert 'placeholder="Search city, country, or region"' in page
    assert "location.region" in page and "location.timezone" in page
    assert "timezone.textContent = formatTimezone(location.timezone)" in page
    assert "window.matchMedia('(max-width: 760px)').matches" in page
    assert "map.flyTo({center: [location.lon, location.lat], zoom: 8}" in page
    assert "document.body.dataset.mobileView = 'list'" in page
    assert "scrollIntoView({block: 'nearest'" in page
    assert ".maplibregl-popup-content { color: var(--ink) !important; background: var(--surface) !important;" in page
    assert "America/Argentina/Buenos_Aires" not in page
    assert '<br>${esc(location.country)}<br><a class="subscribe"' in page
    assert "Upcoming events" not in page
    assert "Location subscriptions are managed" not in page
    assert 'id="meetup-data"' in page
    assert "--surface: #202428" in page
    assert "prefers-color-scheme: dark" in page
    assert "tile.openstreetmap.org" not in page
    assert "OpenMapTiles" in page and "OpenStreetMap contributors" in page
