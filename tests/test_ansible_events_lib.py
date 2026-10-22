from __future__ import annotations

import importlib
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest

from tools.common.ansible_event_cities import (
    CITIES,
    CityInfo,
    MEETUP_PRO_CITIES,
    PREVIOUS_CITIES,
)
from tools.common.ansible_events_lib import (
    CITY_SLUG_RE,
    DISCOURSE_URL,
    EVENT_NAME_PREFIX,
    ORGANISER_TEAM_PREFIX,
    ORGANIZER_SLUG,
    PRETIX_URL,
    get_city,
)


class TestCityInfoSlug:
    def test_lowercase(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.slug == "london"

    def test_mixed_case(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="newyork", city="New York", timezone="America/New_York")
        assert city.slug == "newyork"

    def test_invalid_slug_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            CityInfo(region="Europe", country="UK", slug="new-york", city="New York", timezone="Europe/London")


class TestCityInfoFieldValue:
    def test_standard_format(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.field_value == "Europe:UK:London"

    def test_multi_word_values(self) -> None:
        city = CityInfo(region="Americas", country="US", slug="newyork", city="New York", timezone="America/New_York")
        assert city.field_value == "Americas:US:New York"

    def test_preserves_original_case(self) -> None:
        city = CityInfo(region="EMEA", country="India", slug="pune", city="Pune", timezone="Asia/Kolkata")
        assert city.field_value == "EMEA:India:Pune"


class TestCityInfoFrozen:
    def test_cannot_modify_city(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        with pytest.raises(AttributeError):
            city.city = "Manchester"  # type: ignore[misc]

    def test_cannot_modify_region(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        with pytest.raises(AttributeError):
            city.region = "Americas"  # type: ignore[misc]


class TestGetCity:
    def test_lowercase_slug_match(self) -> None:
        result = get_city("london")
        assert result is not None
        assert result.city == "London"

    def test_rejects_non_lowercase_input(self) -> None:
        assert get_city("London") is None
        assert get_city("LONDON") is None
        assert get_city("lOnDoN") is None

    def test_not_found(self) -> None:
        assert get_city("atlantis") is None

    def test_empty_string(self) -> None:
        assert get_city("") is None

    def test_partial_match_does_not_work(self) -> None:
        assert get_city("Lond") is None

    def test_leading_trailing_spaces_no_match(self) -> None:
        assert get_city(" london ") is None

    def test_returns_full_city_info(self) -> None:
        result = get_city("barcelona")
        assert result is not None
        assert result.region == "Europe"
        assert result.country == "Spain"
        assert result.timezone == "Europe/Madrid"

    def test_unregistered_city_does_not_match(self) -> None:
        assert get_city("valencia") is None


class TestCitiesRegistry:
    expected_countries = frozenset(
        {
            "Argentina",
            "Australia",
            "Brazil",
            "Bulgaria",
            "Canada",
            "China",
            "Colombia",
            "Czech Republic",
            "Denmark",
            "Finland",
            "France",
            "Germany",
            "Greece",
            "Hong Kong",
            "India",
            "Indonesia",
            "Ireland",
            "Israel",
            "Italy",
            "Japan",
            "Kenya",
            "Latvia",
            "Lebanon",
            "Mexico",
            "Netherlands",
            "New Zealand",
            "Peru",
            "Poland",
            "Portugal",
            "Romania",
            "Russia",
            "Saudi Arabia",
            "Singapore",
            "South Africa",
            "South Korea",
            "Spain",
            "Sweden",
            "Switzerland",
            "Taiwan",
            "Thailand",
            "UK",
            "USA",
            "Vietnam",
        }
    )

    def test_all_cities_are_cityinfo(self) -> None:
        for city in CITIES:
            assert isinstance(city, CityInfo)

    @pytest.mark.parametrize("city", CITIES, ids=lambda city: city.slug)
    def test_every_city_loads_with_valid_country_and_timezone(self, city: CityInfo) -> None:
        assert get_city(city.slug) == city
        assert CITY_SLUG_RE.fullmatch(city.slug)
        assert city.region.strip()
        assert city.city.strip()
        assert city.country in self.expected_countries
        assert ZoneInfo(city.timezone)

    def test_registry_covers_expected_countries(self) -> None:
        assert {city.country for city in CITIES} == self.expected_countries

    @pytest.mark.parametrize(
        ("slug", "city_name", "region", "country", "timezone"),
        [
            ("boise", "Boise", "NA", "USA", "America/Boise"),
            ("brisbane", "Brisbane", "APAC", "Australia", "Australia/Brisbane"),
            ("bucharest", "Bucharest", "EMEA", "Romania", "Europe/Bucharest"),
            ("dhahran", "Dhahran", "APAC", "Saudi Arabia", "Asia/Riyadh"),
            ("nova", "NOVA", "NA", "USA", "America/New_York"),
            ("sfbay", "SF Bay", "NA", "USA", "America/Los_Angeles"),
        ],
    )
    def test_corrected_locations_have_expected_country_and_timezone(
        self, slug: str, city_name: str, region: str, country: str, timezone: str
    ) -> None:
        city = get_city(slug)
        assert city is not None
        assert city.city == city_name
        assert city.region == region
        assert city.country == country
        assert city.timezone == timezone

    def test_city_sections_are_sorted_by_region_country_and_city(self) -> None:
        for cities in (MEETUP_PRO_CITIES, PREVIOUS_CITIES):
            keys = [(city.region.casefold(), city.country.casefold(), city.city.casefold()) for city in cities]
            assert keys == sorted(keys)

    @pytest.mark.parametrize(
        ("slug", "city"),
        [
            ("saopaulo", "São Paulo"),
            ("montreal", "Montréal"),
            ("medellin", "Medellín"),
            ("munchen", "München"),
            ("mexicocity", "Mexico City"),
            ("bogota", "Bogotá"),
            ("hanoi", "Hà Nội"),
            ("brasilia", "Brasília"),
            ("krakow", "Kraków"),
            ("torun", "Toruń"),
            ("zurich", "Zürich"),
        ],
    )
    def test_accepted_unicode_city_spellings_are_preserved(self, slug: str, city: str) -> None:
        result = get_city(slug)
        assert result is not None
        assert result.city == city

    def test_unicode_display_name_is_used_for_api_labels_with_ascii_slug(self) -> None:
        city = get_city("saopaulo")
        assert city is not None
        assert city.event_name == "Ansible Meetup São Paulo"
        assert city.team_name == "Ansible Meetup Organisers - São Paulo"
        assert city.organiser_group == "meetup-organisers-saopaulo"

    def test_no_duplicate_city_names(self) -> None:
        names = [c.city for c in CITIES]
        assert len(names) == len(set(names)), f"Duplicate city names: {names}"

    def test_timezones_contain_slash(self) -> None:
        for city in CITIES:
            assert "/" in city.timezone, f"Invalid timezone for {city.city}: {city.timezone}"

    def test_registry_is_immutable(self) -> None:
        assert isinstance(CITIES, tuple)


class TestPretixReqUrlBuilding:
    """Test URL construction logic without making real HTTP calls."""

    def _build_url(self, endpoint: str) -> str:
        url = f"{PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/{endpoint}"
        if "?" in url:
            base, query = url.split("?", 1)
            if not base.endswith("/"):
                base += "/"
            url = f"{base}?{query}"
        else:
            if not url.endswith("/"):
                url += "/"
        return url

    def test_simple_endpoint(self) -> None:
        url = self._build_url("events")
        assert url.endswith("/events/")

    def test_trailing_slash_preserved(self) -> None:
        url = self._build_url("events/")
        assert url.endswith("/events/")
        assert not url.endswith("//")

    def test_nested_endpoint(self) -> None:
        url = self._build_url("events/my-event/items")
        assert url.endswith("/events/my-event/items/")

    def test_double_slash_not_added(self) -> None:
        url = self._build_url("events/my-event/items/")
        assert "//" not in url.split("://", 1)[1]

    def test_query_string_preserved(self) -> None:
        url = self._build_url("events?page=2")
        assert url.endswith("events/?page=2")

    def test_query_string_with_trailing_slash(self) -> None:
        url = self._build_url("events/?page=2")
        assert url.endswith("events/?page=2")

    def test_empty_endpoint(self) -> None:
        url = self._build_url("")
        assert url.endswith(f"{ORGANIZER_SLUG}/")

    def test_endpoint_with_spaces(self) -> None:
        url = self._build_url("events/my event")
        assert "my event" in url


class TestDiscourseReqUrlBuilding:
    """Test URL construction logic without making real HTTP calls."""

    def _build_url(self, endpoint: str) -> str:
        return f"{DISCOURSE_URL.rstrip('/')}/{endpoint}"

    def test_simple_endpoint(self) -> None:
        url = self._build_url("posts.json")
        assert url == f"{DISCOURSE_URL}/posts.json"

    def test_strips_trailing_slash_from_base(self) -> None:
        base = "https://forum.example.com/"
        url = f"{base.rstrip('/')}/posts.json"
        assert "//" not in url.split("://", 1)[1]

    def test_nested_endpoint(self) -> None:
        url = self._build_url("t/123.json")
        assert url.endswith("/t/123.json")

    def test_admin_endpoint(self) -> None:
        url = self._build_url("admin/groups.json")
        assert url.endswith("/admin/groups.json")

    def test_json_endpoint_has_no_trailing_slash(self, monkeypatch):
        from tools.common import ansible_events_lib

        client = ansible_events_lib.ApiClient("https://forum.example", {}, timeout=7, append_trailing_slash=False)
        request = Mock(return_value=Mock(status_code=200))
        monkeypatch.setattr(client.session, "request", request)

        client.request("POST", "posts.json")

        assert request.call_args.args == ("POST", "https://forum.example/posts.json")

    def test_client_can_preserve_trailing_slash_for_pretix(self, monkeypatch):
        from tools.common import ansible_events_lib

        client = ansible_events_lib.ApiClient(
            "https://pretix.example/api/v1/organizers/ansible-meetups/",
            {},
            timeout=7,
            append_trailing_slash=True,
        )
        request = Mock(return_value=Mock(status_code=200))
        monkeypatch.setattr(client.session, "request", request)

        client.request("GET", "events")

        assert request.call_args.args == (
            "GET",
            "https://pretix.example/api/v1/organizers/ansible-meetups/events/",
        )


class TestPreFlightChecks:
    @patch.dict("os.environ", {"PRETIX_API_TOKEN": "test", "DISCOURSE_API_KEY": "test"})
    def test_passes_with_both_vars(self) -> None:
        from tools.common import ansible_events_lib

        importlib.reload(ansible_events_lib)
        ansible_events_lib.pre_flight_checks()

    @patch.dict("os.environ", {"PRETIX_API_TOKEN": "test"}, clear=True)
    def test_exits_without_discourse_key(self) -> None:
        from tools.common import ansible_events_lib

        importlib.reload(ansible_events_lib)
        with pytest.raises(SystemExit):
            ansible_events_lib.pre_flight_checks()

    @patch.dict("os.environ", {"PRETIX_API_TOKEN": "test"}, clear=True)
    def test_passes_without_discourse_key_when_not_required(self) -> None:
        from tools.common import ansible_events_lib

        importlib.reload(ansible_events_lib)
        ansible_events_lib.pre_flight_checks(require_discourse=False)

    @patch.dict("os.environ", {"DISCOURSE_API_KEY": "test"}, clear=True)
    def test_passes_without_pretix_credentials_when_not_required(self) -> None:
        from tools.common import ansible_events_lib

        importlib.reload(ansible_events_lib)
        ansible_events_lib.pre_flight_checks(require_pretix=False)


class TestCityInfoDerivedProperties:
    def test_event_name(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.event_name == f"{EVENT_NAME_PREFIX} London"

    def test_team_name(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.team_name == f"{ORGANISER_TEAM_PREFIX} - London"

    def test_organiser_group(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.organiser_group == "meetup-organisers-london"

    def test_attendee_group(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.attendee_group == "meetup-attendee-london"

    def test_organiser_group_with_spaces(self) -> None:
        city = CityInfo(region="Americas", country="US", slug="newyork", city="New York", timezone="America/New_York")
        assert city.organiser_group == "meetup-organisers-newyork"

    def test_team_name_preserves_case(self) -> None:
        city = CityInfo(region="Europe", country="Spain", slug="valencia", city="Valencia", timezone="Europe/Madrid")
        assert city.team_name == f"{ORGANISER_TEAM_PREFIX} - Valencia"


class TestPretixApiContract:
    def test_api_client_applies_base_url_headers_timeout_and_no_redirects(self, monkeypatch):
        from tools.common import ansible_events_lib

        client = ansible_events_lib.ApiClient("https://api.example/v1", {"Api-Key": "secret"}, timeout=7)
        response = Mock(status_code=200)
        request = Mock(return_value=response)
        monkeypatch.setattr(client.session, "request", request)

        assert client.request("GET", "users") is response

        request.assert_called_once_with(
            "GET",
            "https://api.example/v1/users/",
            timeout=7,
            allow_redirects=False,
        )
        assert client.session.headers["Api-Key"] == "secret"
        assert client.session.headers["User-Agent"] == (
            "Ansible-pretix-discourse-auth/0.1.0 (+https://github.com/ansible-community/meetup-pretix-discourse-auth)"
        )

    def test_discourse_request_uses_explicit_run_as_identity(self, monkeypatch):
        from tools.common import ansible_events_lib

        monkeypatch.setattr(ansible_events_lib, "DISCOURSE_API_KEY", "test-api-key")
        monkeypatch.setitem(ansible_events_lib.DISCOURSE_CLIENT.session.headers, "Api-Key", "test-api-key")
        response = Mock(status_code=200, text='{"ok":true}')
        response.json.return_value = {"ok": True}
        request = Mock(return_value=response)
        monkeypatch.setattr(ansible_events_lib.requests.Session, "request", request)

        assert ansible_events_lib.discourse_req("POST", "posts.json", {"raw": "event"}, run_as="organiser") == {
            "ok": True
        }
        assert ansible_events_lib.DISCOURSE_CLIENT.session.headers["Api-Key"] == "test-api-key"
        assert request.call_args.kwargs["headers"]["Api-Username"] == "organiser"

    def test_discourse_request_retries_rate_limit_using_wait_seconds(self, monkeypatch):
        from tools.common import ansible_events_lib

        monkeypatch.setattr(ansible_events_lib, "DISCOURSE_API_KEY", "test-api-key")
        limited = Mock(status_code=429, text='{"extras":{"wait_seconds":31}}', headers={})
        limited.json.return_value = {"extras": {"wait_seconds": 31}}
        success = Mock(status_code=200, text='{"groups":[]}', headers={})
        success.json.return_value = {"groups": []}
        request = Mock(side_effect=[limited, success])
        sleep = Mock()
        monkeypatch.setattr(ansible_events_lib.requests.Session, "request", request)
        monkeypatch.setattr(ansible_events_lib.time, "sleep", sleep)

        assert ansible_events_lib.discourse_req("GET", "c/43/show.json") == {"groups": []}

        assert request.call_count == 2
        sleep.assert_called_once_with(31.0)

    def test_discourse_request_rate_limit_retries_are_bounded(self, monkeypatch):
        from tools.common import ansible_events_lib

        limited = Mock(status_code=429, text="rate limited", headers={})
        limited.json.return_value = {}
        request = Mock(return_value=limited)
        sleep = Mock()
        monkeypatch.setattr(ansible_events_lib.requests.Session, "request", request)
        monkeypatch.setattr(ansible_events_lib.time, "sleep", sleep)

        with pytest.raises(ansible_events_lib.ApiError, match="failed after rate-limit retries"):
            ansible_events_lib.discourse_req("GET", "c/43/show.json")

        assert request.call_count == ansible_events_lib.DISCOURSE_429_MAX_RETRIES + 1
        assert sleep.call_count == ansible_events_lib.DISCOURSE_429_MAX_RETRIES

    def test_city_category_lookup_requests_nested_categories(self, monkeypatch):
        from tools.common import ansible_events_lib

        requests = []

        def request(method, endpoint):
            requests.append((method, endpoint))
            return {
                "category_list": {
                    "categories": [
                        {
                            "id": 8,
                            "name": "Events",
                            "subcategory_list": [
                                {"id": 11, "name": "London", "parent_category_id": 8},
                            ],
                        }
                    ]
                }
            }

        monkeypatch.setattr(ansible_events_lib, "discourse_req", request)

        assert ansible_events_lib.discourse_city_category_id("London") == 11
        assert requests == [("GET", "categories.json?include_subcategories=true")]

    def test_category_lookup_requires_unique_events_subcategory(self, monkeypatch):
        from tools.common import ansible_events_lib

        monkeypatch.setattr(
            ansible_events_lib,
            "discourse_req",
            lambda *_args: {
                "category_list": {
                    "categories": [
                        {
                            "id": 8,
                            "name": "Events",
                            "subcategory_list": [
                                {"id": 11, "name": "London", "parent_category_id": 8},
                                {"id": 12, "name": "London", "parent_category_id": 8},
                            ],
                        }
                    ]
                }
            },
        )

        with pytest.raises(ansible_events_lib.ApiError, match="found 2"):
            ansible_events_lib.discourse_city_category_id("London")

    def test_check_event_exists_uses_visible_event_inventory(self, monkeypatch):
        from tools.common import ansible_events_lib

        monkeypatch.setattr(
            ansible_events_lib,
            "pretix_list_all",
            lambda endpoint: [{"slug": "london-oct-2026"}] if endpoint == "events" else [],
        )
        assert ansible_events_lib.check_event_exists("london-oct-2026") is True
        assert ansible_events_lib.check_event_exists("barcelona-oct-2026") is False

        def unavailable(_endpoint):
            raise ansible_events_lib.ApiError("Pretix events list returned 503")

        monkeypatch.setattr(ansible_events_lib, "pretix_list_all", unavailable)
        with pytest.raises(ansible_events_lib.ApiError, match="existence cannot be established"):
            ansible_events_lib.check_event_exists("london-oct-2026")

    def test_pretix_request_rejects_non_object_json(self, monkeypatch):
        from tools.common import ansible_events_lib

        response = Mock(status_code=200, text="[]")
        response.json.return_value = []
        monkeypatch.setattr(ansible_events_lib.requests.Session, "request", Mock(return_value=response))
        with pytest.raises(ansible_events_lib.ApiError, match="non-object JSON"):
            ansible_events_lib.pretix_req("GET", "events")

    def test_pagination_rejects_external_host_before_sending_token(self, monkeypatch):
        from tools.common import ansible_events_lib

        monkeypatch.setattr(ansible_events_lib, "PRETIX_URL", "https://tickets.example")
        monkeypatch.setattr(
            ansible_events_lib,
            "pretix_req",
            lambda *_args: {
                "results": [{"slug": "london-oct-2026"}],
                "next": "https://attacker.example/steal?token=1",
            },
        )
        next_request = Mock()
        monkeypatch.setattr(ansible_events_lib.requests.Session, "request", next_request)
        with pytest.raises(ansible_events_lib.ApiError, match="outside the configured organizer API"):
            ansible_events_lib.pretix_list_all("events")
        next_request.assert_not_called()

    def test_pagination_collects_all_pages_inside_organizer(self, monkeypatch):
        from tools.common import ansible_events_lib

        monkeypatch.setattr(ansible_events_lib, "PRETIX_URL", "https://tickets.example")
        monkeypatch.setattr(
            ansible_events_lib.PRETIX_CLIENT,
            "base_url",
            "https://tickets.example/api/v1/organizers/meetups/",
        )
        monkeypatch.setattr(ansible_events_lib, "ORGANIZER_SLUG", "meetups")
        monkeypatch.setattr(ansible_events_lib, "PRETIX_API_TOKEN", "secret-token")
        monkeypatch.setitem(ansible_events_lib.PRETIX_CLIENT.session.headers, "Authorization", "Token secret-token")
        monkeypatch.setattr(
            ansible_events_lib,
            "pretix_req",
            lambda *_args: {
                "results": [{"slug": "london-oct-2026"}],
                "next": "/api/v1/organizers/meetups/events/?page=2",
            },
        )
        response = MockResponse(200, {"results": [{"slug": "barcelona-nov-2026"}], "next": None})
        next_request = Mock(return_value=response)
        monkeypatch.setattr(ansible_events_lib.requests.Session, "request", next_request)
        result = ansible_events_lib.pretix_list_all("events")
        assert [event["slug"] for event in result] == ["london-oct-2026", "barcelona-nov-2026"]
        assert next_request.call_args.args[1] == ("https://tickets.example/api/v1/organizers/meetups/events/?page=2")
        assert ansible_events_lib.PRETIX_CLIENT.session.headers["Authorization"] == "Token secret-token"


class MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.text = "{}"
        self._payload = payload

    def json(self):
        return self._payload


class TestProvisioningPermissions:
    def test_attendee_invites_reuse_matches_and_create_only_missing_city(self, monkeypatch):
        from tools.environment import provision_environment

        london = next(city for city in provision_environment.CITIES if city.slug == "london")
        barcelona = next(city for city in provision_environment.CITIES if city.slug == "barcelona")
        monkeypatch.setattr(provision_environment, "CITIES", (london, barcelona))
        requests = []

        def request(method, endpoint, payload=None, *, run_as=None):
            requests.append((method, endpoint, payload, run_as))
            if method == "GET":
                return {
                    "invites": [
                        {
                            "description": f"Join Ansible {london.city}",
                            "groups": [
                                {"name": london.attendee_group},
                                {"name": provision_environment.MIGRATED_GROUP_NAME},
                            ],
                        },
                        {
                            "description": f"Join Ansible {barcelona.city}",
                            "groups": [{"name": london.attendee_group}],
                        },
                    ]
                }
            return {"link": "https://forum.example/invites/barcelona"}

        monkeypatch.setattr(provision_environment, "discourse_req", request)

        provision_environment.reconcile_attendee_invites()

        assert requests == [
            ("GET", "u/gundalow/invited/pending.json", None, "gundalow"),
            *[
                (
                    "POST",
                    "invites.json",
                    {
                        "skip_email": True,
                        "description": f"Join Ansible {city.city}",
                        "group_names": f"{city.attendee_group},{provision_environment.MIGRATED_GROUP_NAME}",
                        "max_redemptions_allowed": 5_000,
                        "expires_at": "2030-01-01",
                    },
                    "gundalow",
                )
                for city in provision_environment.CITIES[1:]
            ],
        ]

    def test_attendee_invites_fail_on_malformed_pending_response_before_creation(self, monkeypatch):
        from tools.environment import provision_environment

        requests = []

        def request(method, endpoint, payload=None, *, run_as=None):
            requests.append((method, endpoint, payload, run_as))
            return {"invites": [{"description": "Join Ansible London", "groups": "not-a-list"}]}

        monkeypatch.setattr(provision_environment, "discourse_req", request)

        with pytest.raises(provision_environment.ApiError, match="invalid description or groups"):
            provision_environment.reconcile_attendee_invites()

        assert requests == [("GET", "u/gundalow/invited/pending.json", None, "gundalow")]

    def test_discourse_group_listing_uses_paginated_directory_endpoint(self, monkeypatch):
        from tools.environment import provision_environment

        requests = []

        def request(method, endpoint):
            requests.append((method, endpoint))
            if endpoint == "groups.json?page=0":
                return {"groups": [{"name": "meetup-organisers-london"}]}
            if endpoint == "groups.json?page=1":
                return {"groups": []}
            raise AssertionError(f"Unexpected Discourse request: {method} {endpoint}")

        monkeypatch.setattr(provision_environment, "discourse_req", request)

        groups = provision_environment.list_discourse_groups()

        assert groups == [{"name": "meetup-organisers-london"}]
        assert requests == [
            ("GET", "groups.json?page=0"),
            ("GET", "groups.json?page=1"),
        ]

    def test_template_settings_patch_only_differences(self, monkeypatch):
        from tools.environment import provision_environment

        settings = {"name_scheme": "full", "attendee_names_asked": False}
        requests = []

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            if method == "PATCH":
                settings.update(payload)
            return settings.copy()

        monkeypatch.setattr(provision_environment, "pretix_req", request)
        provision_environment.reconcile_pretix_event_settings(
            "template",
            {"name_scheme": "full", "attendee_names_asked": True},
        )

        assert requests == [
            ("GET", "events/template/settings", None),
            ("PATCH", "events/template/settings", {"attendee_names_asked": True}),
        ]

    def test_template_settings_noop_does_not_patch(self, monkeypatch):
        from tools.environment import provision_environment

        requests = []
        settings = {"name_scheme": "full"}

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            return settings.copy()

        monkeypatch.setattr(provision_environment, "pretix_req", request)
        provision_environment.reconcile_pretix_event_settings("template", {"name_scheme": "full"})

        assert requests == [
            ("GET", "events/template/settings", None),
        ]

    def test_template_name_scheme_is_patched_before_settings_read(self, monkeypatch):
        from tools.environment import provision_environment

        settings = {"name_scheme": "given_family", "attendee_names_asked": True}
        requests = []

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            if method == "PATCH":
                settings.update(payload)
            return settings.copy()

        monkeypatch.setattr(provision_environment, "pretix_req", request)
        provision_environment.reconcile_pretix_event_settings(
            "template",
            {"name_scheme": "full", "attendee_names_asked": True},
            ("name_scheme",),
        )

        assert requests == [
            ("PATCH", "events/template/settings", {"name_scheme": "full"}),
            ("GET", "events/template/settings", None),
        ]

    def test_template_name_scheme_redundant_patch_uses_readback(self, monkeypatch):
        from tools.common.ansible_events_lib import ApiError
        from tools.environment import provision_environment

        requests = []
        settings = {"name_scheme": "full", "attendee_names_asked": True}

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            if method == "PATCH":
                raise ApiError(
                    "Pretix PATCH events/template/settings failed: 400 "
                    '{"name_scheme":["\\"full\\" is not a valid choice."]}'
                )
            return settings.copy()

        monkeypatch.setattr(provision_environment, "pretix_req", request)
        provision_environment.reconcile_pretix_event_settings(
            "template",
            {"name_scheme": "full", "attendee_names_asked": True},
            ("name_scheme",),
        )

        assert requests == [
            ("PATCH", "events/template/settings", {"name_scheme": "full"}),
            ("GET", "events/template/settings", None),
        ]

    def test_template_name_scheme_mismatch_after_rejection_fails(self, monkeypatch):
        from tools.common.ansible_events_lib import ApiError
        from tools.environment import provision_environment

        settings = {"name_scheme": "given_family"}

        def request(method, endpoint, payload=None):
            if method == "PATCH":
                raise ApiError(
                    "Pretix PATCH events/template/settings failed: 400 "
                    '{"name_scheme":["\\"full\\" is not a valid choice."]}'
                )
            return settings.copy()

        monkeypatch.setattr(provision_environment, "pretix_req", request)
        with pytest.raises(ApiError, match="current value still differs"):
            provision_environment.reconcile_pretix_event_settings(
                "template",
                {"name_scheme": "full"},
                ("name_scheme",),
            )

    def test_template_creation_uses_only_public_event_api_fields(self, monkeypatch):
        from tools.environment import provision_environment

        requests = []

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            return {**payload, "slug": provision_environment.TEMPLATE_SLUG}

        monkeypatch.setattr(provision_environment, "pretix_req", request)
        monkeypatch.setattr(provision_environment, "reconcile_pretix_event_settings", lambda *_: None)
        monkeypatch.setattr(provision_environment, "reconcile_template_ticket", lambda: None)
        monkeypatch.setattr(provision_environment, "reconcile_template_item_meta_property", lambda: None)

        provision_environment.reconcile_pretix_template([])

        assert len(requests) == 1
        method, endpoint, payload = requests[0]
        assert (method, endpoint) == ("POST", "events")
        assert payload["live"] is False
        assert payload["is_public"] is False
        assert payload["timezone"] == "UTC"
        assert "is_template" not in payload

    def test_existing_template_does_not_require_api_unsupported_marker(self, monkeypatch):
        from tools.environment import provision_environment

        def unexpected_request(*_args, **_kwargs):
            raise AssertionError("Matching template should not require a detail read or patch")

        monkeypatch.setattr(provision_environment, "pretix_req", unexpected_request)
        monkeypatch.setattr(provision_environment, "reconcile_pretix_event_settings", lambda *_: None)
        monkeypatch.setattr(provision_environment, "reconcile_template_ticket", lambda: None)
        monkeypatch.setattr(provision_environment, "reconcile_template_item_meta_property", lambda: None)

        provision_environment.reconcile_pretix_template(
            [
                {
                    "slug": provision_environment.TEMPLATE_SLUG,
                    "live": False,
                    "is_public": False,
                    "timezone": "UTC",
                }
            ]
        )

    def test_pretix_teams_do_not_require_pretix_two_factor_authentication(self, monkeypatch):
        from tools.environment import provision_environment

        requests = []
        created_teams = {}
        next_id = 1

        def list_all(endpoint):
            if endpoint == "teams":
                return []
            if endpoint == "events":
                return []
            raise AssertionError(f"Unexpected Pretix list endpoint: {endpoint}")

        def request(method, endpoint, payload=None):
            nonlocal next_id
            requests.append((method, endpoint, payload))
            if method == "POST" and endpoint == "teams":
                team = {**payload, "id": next_id}
                created_teams[next_id] = team
                next_id += 1
                return team
            if method == "GET" and endpoint.startswith("teams/"):
                return created_teams[int(endpoint.split("/")[1])]
            raise AssertionError(f"Unexpected Pretix request: {method} {endpoint}")

        monkeypatch.setattr(provision_environment, "pretix_list_all", list_all)
        monkeypatch.setattr(provision_environment, "pretix_req", request)

        provision_environment.reconcile_pretix_teams()

        team_creations = [payload for method, endpoint, payload in requests if method == "POST" and endpoint == "teams"]
        assert len(team_creations) == len(provision_environment.CITIES) + 1
        assert all(team["require_2fa"] is False for team in team_creations)

    def test_template_ticket_reconciles_item_and_quota_drift(self, monkeypatch):
        from tools.environment import provision_environment

        requests = []
        item = {
            "id": 7,
            "name": {"en": provision_environment.DEFAULT_ITEM_NAME},
            "default_price": "2.00",
            "active": False,
            "admission": False,
        }
        quota = {"id": 9, "name": provision_environment.DEFAULT_QUOTA_NAME, "size": 50, "items": []}

        def list_all(endpoint):
            if endpoint == f"events/{provision_environment.TEMPLATE_SLUG}/items":
                return [item.copy()]
            if endpoint == f"events/{provision_environment.TEMPLATE_SLUG}/quotas":
                return [quota.copy()]
            raise AssertionError(f"Unexpected Pretix list endpoint: {endpoint}")

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            if method == "PATCH" and endpoint.endswith("/items/7"):
                item.update(payload)
                return item.copy()
            if method == "PATCH" and endpoint.endswith("/quotas/9"):
                quota.update(payload)
                return quota.copy()
            raise AssertionError(f"Unexpected Pretix request: {method} {endpoint}")

        monkeypatch.setattr(provision_environment, "pretix_list_all", list_all)
        monkeypatch.setattr(provision_environment, "pretix_req", request)

        provision_environment.reconcile_template_ticket()

        assert [request[0:2] for request in requests] == [
            ("PATCH", f"events/{provision_environment.TEMPLATE_SLUG}/items/7"),
            ("PATCH", f"events/{provision_environment.TEMPLATE_SLUG}/quotas/9"),
        ]
        assert item["default_price"] == provision_environment.DEFAULT_ITEM_PRICE
        assert item["active"] is True
        assert item["admission"] is True
        assert quota["size"] == 100
        assert quota["items"] == [7]

    def test_pretix_empty_metadata_choices_accepts_null_and_empty_list(self, monkeypatch):
        from tools.environment import provision_environment

        assert provision_environment.same_configuration_value("choices", None, [])
        assert provision_environment.same_configuration_value("choices", [], None)

        requests = []
        prop = {
            "id": 4,
            "name": "forum_topic_url",
            "default": "https://old.example/events",
            "choices": None,
            "required": False,
            "protected": False,
        }

        def list_all(endpoint):
            assert endpoint == "event_meta_properties"
            return [prop.copy()]

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            assert method == "PATCH"
            prop.update(payload)
            return prop.copy()

        monkeypatch.setattr(provision_environment, "pretix_list_all", list_all)
        monkeypatch.setattr(provision_environment, "pretix_req", request)

        provision_environment.reconcile_pretix_meta_property()

        assert len(requests) == 1
        assert "choices" not in requests[0][2]
        assert prop["choices"] is None
        assert prop["protected"] is True

    def test_city_plans_are_built_from_registered_cities(self):
        from tools.environment import provision_environment

        plans = provision_environment.build_city_forum_plans()

        assert [plan.city for plan in plans] == list(provision_environment.CITIES)
        london_plan = next(plan for plan in plans if plan.city.slug == "london")
        assert london_plan.organiser_group_name == "meetup-organisers-london"
        assert london_plan.attendee_group_name == "meetup-attendee-london"

    def test_group_reconciliation_updates_tracking_with_one_read(self, monkeypatch):
        from tools.environment import provision_environment

        requests = []

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            if method == "GET":
                return {"group": {"tracking_category_ids": []}}
            if method == "PUT":
                return {"group": {"tracking_category_ids": [42]}}
            raise AssertionError(f"Unexpected Discourse request: {method} {endpoint}")

        monkeypatch.setattr(provision_environment, "discourse_req", request)
        provision_environment.reconcile_discourse_group(
            "meetup-organisers-london",
            12,
            {"tracking_category_ids": [42]},
        )

        assert requests == [
            ("GET", "groups/by-id/12.json", None),
            (
                "PUT",
                "groups/12.json",
                {"group": {"tracking_category_ids": [42]}, "update_existing_users": "true"},
            ),
        ]

    def test_group_reconciliation_noop_uses_one_read(self, monkeypatch):
        from tools.environment import provision_environment

        requests = []

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            return {"group": {"tracking_category_ids": [42]}}

        monkeypatch.setattr(provision_environment, "discourse_req", request)
        provision_environment.reconcile_discourse_group(
            "meetup-organisers-london",
            12,
            {"tracking_category_ids": [42]},
        )

        assert requests == [("GET", "groups/by-id/12.json", None)]

    def test_resource_status_lists_changed_and_already_correct_fields(self, caplog):
        import logging

        from tools.environment import provision_environment

        caplog.set_level(logging.INFO, logger=provision_environment.logger.name)
        provision_environment.log_resource_status(
            "meetup-organisers-london",
            {"visibility_level": 1, "members_visibility_level": 2},
            {"visibility_level": 0, "members_visibility_level": 2},
        )

        assert "meetup-organisers-london: Updated | visibility: Changed, member visibility: OK" in caplog.text

    def test_resource_status_marks_created_fields_as_verified(self, caplog):
        import logging

        from tools.environment import provision_environment

        caplog.set_level(logging.INFO, logger=provision_environment.logger.name)
        provision_environment.log_resource_status(
            "meetup-attendee-london",
            {"visibility_level": 3, "members_visibility_level": 3},
            None,
        )

        assert "meetup-attendee-london: Created | visibility: OK, member visibility: OK" in caplog.text

    def test_city_category_uses_reply_only_default_and_city_organiser_access(self, monkeypatch):
        from tools.environment import provision_environment
        from tools.common.ansible_events_lib import get_city

        current = {
            "id": 51,
            "name": "London",
            "parent_category_id": provision_environment.DISCOURSE_PARENT_CATEGORY_ID,
            "color": "000000",
            "text_color": "FFFFFF",
            "description": "Old description",
            "moderating_group_ids": [],
            "group_permissions": [{"group_id": 0, "group_name": "everyone", "permission_type": 1}],
        }
        plan = provision_environment.CityForumPlan(city=get_city("london"), organiser_group_id=9, category_id=51)
        requests = []

        def request(method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            if method == "GET" and endpoint == "c/51/show.json":
                return {"category": current.copy()}
            if method == "PUT" and endpoint == "categories/51.json":
                current.update({key: value for key, value in payload.items() if key != "permissions"})
                if "permissions" in payload:
                    current["group_permissions"] = [
                        {
                            "group_id": 0 if name == "everyone" else 9,
                            "group_name": name,
                            "permission_type": permission,
                        }
                        for name, permission in payload["permissions"].items()
                    ]
                return {"category": current.copy()}
            raise AssertionError(f"Unexpected Discourse request: {method} {endpoint}")

        monkeypatch.setattr(provision_environment, "discourse_req", request)
        provision_environment.reconcile_city_category_access(
            [current.copy()],
            {51: plan},
            {"meetup-organisers-london": {"id": 9}},
        )

        update = next(payload for method, _, payload in requests if method == "PUT")
        assert update["permissions"] == {
            "everyone": provision_environment.CATEGORY_PERMISSION_CREATE_POST,
            "meetup-organisers-london": provision_environment.CATEGORY_PERMISSION_FULL,
        }
        assert update["moderating_group_ids"] == [9]
        assert sum(method == "GET" for method, _, _ in requests) == 2

    def test_organizer_access_is_removed_everywhere_except_own_subcategory(self, monkeypatch):
        from tools.environment import provision_environment
        from tools.common.ansible_events_lib import get_city

        categories = [
            {"id": 11},
            {"id": 12},
        ]
        current = {
            11: {
                "moderating_group_ids": [9, 10],
                "group_permissions": [
                    {"group_id": 0, "group_name": "everyone", "permission_type": 2},
                    {"group_id": 9, "group_name": "meetup-organisers-london", "permission_type": 1},
                    {"group_id": 10, "group_name": "meetup-organisers-barcelona", "permission_type": 1},
                ],
            },
            12: {
                "moderating_group_ids": [10, 15],
                "group_permissions": [
                    {"group_id": 0, "group_name": "everyone", "permission_type": 2},
                    {"group_id": 9, "group_name": "meetup-organisers-london", "permission_type": 1},
                    {"group_id": 10, "group_name": "meetup-organisers-barcelona", "permission_type": 1},
                ],
            },
        }
        london = provision_environment.CityForumPlan(city=get_city("london"), organiser_group_id=9, category_id=11)

        def request(method, endpoint, payload=None):
            if method == "GET" and endpoint.startswith("c/") and endpoint.endswith("/show.json"):
                category_id = int(endpoint.split("/")[1])
                return {"category": current[category_id].copy()}
            if method == "PUT" and endpoint.startswith("categories/"):
                category_id = int(endpoint.split("/")[1].split(".")[0])
                current[category_id].update({key: value for key, value in payload.items() if key != "permissions"})
                if "permissions" in payload:
                    current[category_id]["group_permissions"] = [
                        {
                            "group_id": 0 if name == "everyone" else (9 if name.endswith("london") else 15),
                            "group_name": name,
                            "permission_type": permission,
                        }
                        for name, permission in payload["permissions"].items()
                    ]
                return {}
            raise AssertionError(f"Unexpected Discourse request: {method} {endpoint}")

        monkeypatch.setattr(provision_environment, "discourse_req", request)
        provision_environment.reconcile_city_category_access(
            categories,
            {11: london},
            {
                "meetup-organisers-london": {"id": 9},
                "meetup-organisers-barcelona": {"id": 10},
            },
        )

        assert current[11]["moderating_group_ids"] == [9]
        assert current[11]["group_permissions"] == [
            {"group_id": 0, "group_name": "everyone", "permission_type": 2},
            {"group_id": 9, "group_name": "meetup-organisers-london", "permission_type": 1},
        ]
        assert current[12]["moderating_group_ids"] == [15]
        assert current[12]["group_permissions"] == [{"group_id": 0, "group_name": "everyone", "permission_type": 2}]
