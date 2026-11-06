from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from tools.common.ansible_event_cities import CITIES, CityInfo
from tools.website.generate_worldmap import attendance_format, fetch_events, normalise_region, render_page


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


def test_fetch_events_uses_feed_dates_and_post_event_details(monkeypatch: pytest.MonkeyPatch) -> None:
    future_start = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)
    past_start = (datetime.now(UTC) - timedelta(days=3)).replace(microsecond=0)
    feed = {
        "topic_list": {
            "topics": [
                {
                    "id": 12,
                    "slug": "london-meetup",
                    "title": "London Community Meetup",
                    "event_starts_at": future_start.isoformat(),
                    "event_timezone": "Europe/London",
                },
                {"id": 11, "slug": "past", "title": "Past event", "event_starts_at": past_start.isoformat()},
                {"id": 10, "slug": "no-date", "title": "No event date"},
            ]
        }
    }
    event = {"timezone": "Europe/London", "location": "London office", "recurrence": "FREQ=WEEKLY"}
    raw = (
        '<script type="application/ld+json">'
        '{"eventAttendanceMode":"https://schema.org/OfflineEventAttendanceMode"}'
        "</script>"
    )
    feed_response = Mock()
    feed_response.json.return_value = feed
    detail_response = Mock()
    detail_response.json.return_value = {"post_stream": {"posts": [{"event": event, "raw": raw}]}}
    request = Mock(side_effect=[feed_response, detail_response])
    monkeypatch.setattr("tools.website.generate_worldmap.requests.get", request)

    events = fetch_events()

    assert len(events) == 1
    assert events[0]["title"] == "London Community Meetup"
    assert events[0]["start"] == future_start.isoformat()
    assert events[0]["timezone"] == "Europe/London"
    assert events[0]["format"] == "In person"
    assert events[0]["repeating"] is True
    assert request.call_count == 2


def test_explicit_attendance_mode_takes_precedence() -> None:
    online = {"eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode"}
    offline = {"eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode"}
    assert attendance_format(online, "", "In-person meetup", "London office") == "Online"
    assert attendance_format(offline, "", "Online meetup", "London office") == "In person"


def test_rendered_json_is_script_safe_and_map_uses_openfreemap() -> None:
    page = render_page(
        [{"slug": "london", "city": "London", "country": "UK", "region": "Europe", "lat": 51.5, "lon": -0.1}],
        [{"title": "<script>alert(1)</script>", "url": "https://forum.ansible.com/t/example/1", "start": "2027-01-01T10:00:00+00:00", "timezone": "UTC", "location": "", "format": "Online", "repeating": False}],
        "2026-11-06 10:00 UTC",
    )
    match = re.search(r'<script id="meetup-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    data = json.loads(match.group(1))
    assert data["events"][0]["title"] == "<script>alert(1)</script>"
    assert r"\u003cscript" in match.group(1)
    assert "maplibre-gl@^5" in page
    assert "tiles.openfreemap.org/styles/liberty" in page
    assert 'rel="icon"' in page
    assert "Ansible-Community-Mark-Pool.png" in page
    assert "clusterRadius:48" in page
    assert "circle-color':'#5BBCBF" in page
    assert "Current meetup" not in page
    assert "Previous location" not in page
    assert "countryRows.sort((a,b)=>a.city.localeCompare(b.city))" in page
    assert "details.open=Boolean(q||r)" in page
    assert "countryRows.length" in page
    assert "grid-template-columns:minmax(0,1fr) auto" in page
    assert "tile.openstreetmap.org" not in page
    assert "OpenMapTiles" in page and "OpenStreetMap contributors" in page
