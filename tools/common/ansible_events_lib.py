from __future__ import annotations

import logging
import os
import re
import sys
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

# External request types are supplied by the `types-requests` development dependency.
import requests  # type: ignore[reportMissingModuleSource]

if TYPE_CHECKING:
    from tools.common.ansible_event_cities import CityInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ansible_meetups")
logging.getLogger("urllib3").setLevel(logging.WARNING)


class ApiError(RuntimeError):
    """An API request failed or returned an unexpected response."""


def run_cli(action: Callable[[], None]) -> None:
    """Run a CLI action and translate API failures into one friendly error."""
    try:
        action()
    except ApiError as exc:
        logger.error("API request failed: %s", exc)
        raise SystemExit(1) from exc


# --- Secrets (from environment) ---
# Production: https://rsvp.ansible.com
PRETIX_URL = os.environ.get("PRETIX_URL", "http://localhost:8000")
PRETIX_API_TOKEN = os.environ.get("PRETIX_API_TOKEN")
DISCOURSE_API_KEY = os.environ.get("DISCOURSE_API_KEY")

# --- Ansible Community constants ---
DISCOURSE_URL = "https://forum.ansible.com"
DISCOURSE_API_USER = "system"
HTTP_USER_AGENT = (
    "Ansible-pretix-discourse-auth/0.1.0 (+https://github.com/ansible-community/meetup-pretix-discourse-auth)"
)
ORGANIZER_SLUG = "ansible-meetups"
CONTACT_EMAIL = "ansible-community-events@redhat.com"
ANSIBLE_PRIMARY_COLOR = "#EE0000"
CODE_OF_CONDUCT_URL = "https://docs.ansible.com/ansible/devel/community/code_of_conduct.html"
PRIVACY_POLICY_URL = f"{DISCOURSE_URL}/privacy"
EVENTS_FORUM_URL = f"{DISCOURSE_URL}/c/events/8"

# --- Discourse IDs ---
DISCOURSE_PARENT_CATEGORY_ID = 8

# --- Naming ---
EVENT_NAME_PREFIX = "Ansible Meetup"
ORGANISER_TEAM_PREFIX = "Ansible Meetup Organisers"
ORGANISERS_GROUP_PREFIX = "meetup-organisers"
INVITE_API_USERNAME = "gundalow"
MEETUP_INVITE_DESCRIPTION_PREFIX = "Join Ansible "
BADGE_MEETUP_SPEAKER = 123
BADGE_MEETUP_ORGANIZER = 124
BADGE_MEETUP_ATTENDEE = 127
BADGE_MEETUP_MIGRATED = 165
STAFF_TEAM_NAME = "Ansible Meetup Staff"
GROUP_VISIBILITY_OWNERS_ONLY = 4
GROUP_VISIBILITY_STAFF_ONLY = 3
MIGRATED_GROUP_NAME = "meetup-migrated-attendees"
CITY_SLUG_RE = re.compile(r"^[a-z]+$")
ORGANIZERS_GROUP_RE = re.compile(r"^meetup-organisers-([a-z]+)$")
MONTH_SLUGS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
EVENT_SLUG_RE = re.compile(rf"^([a-z]+)-({'|'.join(MONTH_SLUGS)})-[0-9]{{4}}$")
API_REQUEST_TIMEOUT_SECONDS = 10
DISCOURSE_429_MAX_RETRIES = 3

# --- Pretix template ---
TEMPLATE_SLUG = "ansible-meetup-template-v6"
DEFAULT_ITEM_NAME = "RSVP"
DEFAULT_ITEM_PRICE = "0.00"
DEFAULT_QUOTA_NAME = "Capacity"
PASSBOOK_BACKFIELD_PROPERTY = "pretix_passbook_backfield"
PASSBOOK_BACKFIELD_DEFAULT = ""
ORGANISER_PERMISSIONS: list[str] = [
    "event.orders:read",
    "event.orders:checkin",
]

# --- Discourse user field ---
USER_CITY_FIELD_NAME = "user_event_cities"
USER_CITY_FIELD_ID = 4

# --- Security ---
RTBF_EMAIL_SUFFIX = "@anonymized.invalid"


class ApiClient:
    """Reusable Requests session with shared API URL, headers, and timeout."""

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str | None],
        timeout: int,
        *,
        append_trailing_slash: bool = True,
    ) -> None:
        """Initialize a reusable API session.

        Args:
            base_url: Root URL used to resolve relative endpoint paths.
            headers: Default headers; entries with `None` values are omitted.
            timeout: Request timeout in seconds.
            append_trailing_slash: Whether to ensure relative endpoint paths end in `/`.
        """
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.append_trailing_slash = append_trailing_slash
        self.session = requests.Session()
        self.session.headers.update({key: value for key, value in headers.items() if value is not None})
        self.session.headers["User-Agent"] = HTTP_USER_AGENT

    def request(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        """Send a request with the client's URL, headers, and timeout defaults.

        Args:
            method: HTTP method to use.
            endpoint: Relative API path or absolute URL.
            **kwargs: Additional keyword arguments passed to Requests.

        Returns:
            The HTTP response.
        """
        if urlparse(endpoint).scheme:
            url = endpoint
        else:
            path, separator, query = endpoint.partition("?")
            path = path.rstrip("/")
            if self.append_trailing_slash and path:
                path += "/"
            url = urljoin(self.base_url, path.lstrip("/"))
            if separator:
                url = f"{url}?{query}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("allow_redirects", False)
        return self.session.request(method, url, **kwargs)


PRETIX_CLIENT = ApiClient(
    f"{PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/",
    {"Authorization": f"Token {PRETIX_API_TOKEN}" if PRETIX_API_TOKEN else None, "Content-Type": "application/json"},
    API_REQUEST_TIMEOUT_SECONDS,
    append_trailing_slash=True,
)
DISCOURSE_CLIENT = ApiClient(
    DISCOURSE_URL,
    {
        "Api-Key": DISCOURSE_API_KEY,
        "Api-Username": DISCOURSE_API_USER,
        "Content-Type": "application/json",
        "Accept": "application/json",
    },
    API_REQUEST_TIMEOUT_SECONDS,
    append_trailing_slash=False,
)


def get_city(name: str) -> CityInfo | None:
    """Look up a registered city slug. Returns None for malformed or unknown names."""
    if not CITY_SLUG_RE.fullmatch(name):
        return None
    from tools.common.ansible_event_cities import CITIES

    for c in CITIES:
        if c.slug == name:
            return c
    return None


def __getattr__(name: str) -> Any:
    """Keep the former city-registry exports available to existing callers."""
    if name in {"ATTENDEE_GROUP_PREFIX", "CITIES", "CityInfo"}:
        from tools.common import ansible_event_cities

        return getattr(ansible_event_cities, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def discourse_user_exists(username: str) -> bool:
    """Check whether a Discourse user exists by username."""
    resp = discourse_req("GET", f"u/{username}.json")
    return resp is not None and isinstance(resp, dict)


def discourse_user_in_group(username: str, group_name: str) -> bool:
    """Check whether a Discourse user is a member of a specific group."""
    resp = discourse_req("GET", f"u/{username}.json")
    if not resp or not isinstance(resp, dict):
        return False
    user_data = resp.get("user", {})
    groups = user_data.get("groups", [])
    return any(g.get("name") == group_name for g in groups)


def discourse_categories() -> list[dict[str, Any]]:
    """Fetch all visible Discourse categories, including nested subcategories."""
    response = discourse_req("GET", "categories.json?include_subcategories=true")
    category_list = response.get("category_list")
    if not isinstance(category_list, dict):
        raise ApiError("Discourse categories response is missing category_list")
    roots = category_list.get("categories")
    if not isinstance(roots, list):
        raise ApiError("Discourse categories response is missing categories")

    categories: list[dict[str, Any]] = []

    def flatten(rows: list[Any]) -> None:
        """Append categories and nested subcategories to the result list."""
        for row in rows:
            if not isinstance(row, dict):
                raise ApiError("Discourse categories response contains an invalid category")
            categories.append(row)
            children = row.get("subcategory_list", row.get("subcategories", []))
            if children is not None:
                if not isinstance(children, list):
                    raise ApiError("Discourse categories response contains invalid subcategories")
                flatten(children)

    flatten(roots)
    return categories


def discourse_city_category_id(city_name: str) -> int:
    """Resolve the registered city's Events subcategory, failing on missing or ambiguous state."""
    categories = discourse_categories()
    matches = [
        category
        for category in categories
        if category.get("name", "").casefold() == city_name.casefold()
        and category.get("parent_category_id") == DISCOURSE_PARENT_CATEGORY_ID
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
        raise ApiError(f"Expected exactly one Events subcategory for {city_name!r}; found {len(matches)}")
    return matches[0]["id"]


def pre_flight_checks(*, require_discourse: bool = True, require_pretix: bool = True) -> None:
    """Validate required API environment variables are set.

    Args:
        require_discourse: When False, skip the DISCOURSE_API_KEY check
            (for scripts that only use Pretix).
        require_pretix: When False, skip the Pretix token and URL checks
            (for scripts that only use Discourse).
    """
    missing = []
    if require_pretix and not PRETIX_API_TOKEN:
        missing.append("PRETIX_API_TOKEN")
    if require_discourse and not DISCOURSE_API_KEY:
        missing.append("DISCOURSE_API_KEY")
    if require_pretix:
        parsed = urlparse(PRETIX_URL)
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            logger.error("PRETIX_URL must use HTTPS outside localhost/loopback")
            missing.append("secure PRETIX_URL")
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


def pretix_req(method: str, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated Pretix API request.

    Returns parsed JSON on success. Raises ApiError on every failure.
    """
    try:
        resp = PRETIX_CLIENT.request(method, endpoint, json=payload)
    except requests.RequestException as exc:
        raise ApiError(f"Pretix {method} {endpoint} connection error: {exc}") from exc
    if resp.status_code not in (200, 201, 204):
        raise ApiError(f"Pretix {method} {endpoint} failed: {resp.status_code} {resp.text[:200]}")
    if not resp.text:
        if method.upper() in {"GET", "POST"}:
            raise ApiError(f"Pretix {method} {endpoint} returned an empty response body")
        return {}
    try:
        data = resp.json()
    except ValueError as exc:
        raise ApiError(f"Pretix {method} {endpoint} returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ApiError(f"Pretix {method} {endpoint} returned non-object JSON")
    return data


def discourse_req(
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    run_as: str | None = None,
) -> dict[str, Any]:
    """Make an authenticated Discourse API request.

    Args:
        run_as: Override the API username for this request (e.g. to post
            on behalf of a specific user).

    Returns parsed JSON on success. Raises ApiError on every failure.
    """
    resp: requests.Response | None = None
    for attempt in range(DISCOURSE_429_MAX_RETRIES + 1):
        try:
            headers = {"Api-Username": run_as} if run_as else None
            resp = DISCOURSE_CLIENT.request(method, endpoint, json=payload, headers=headers)
        except requests.RequestException as exc:
            raise ApiError(f"Discourse {method} {endpoint} connection error: {exc}") from exc
        if resp.status_code != 429:
            break
        if attempt == DISCOURSE_429_MAX_RETRIES:
            raise ApiError(f"Discourse {method} {endpoint} failed after rate-limit retries: 429 {resp.text[:200]}")

        retry_after = resp.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after is not None else None
        except ValueError:
            delay = None
        if delay is None:
            try:
                error_body = resp.json()
            except ValueError:
                error_body = {}
            extras = error_body.get("extras") if isinstance(error_body, dict) else None
            wait_seconds = extras.get("wait_seconds") if isinstance(extras, dict) else None
            delay = (
                float(wait_seconds)
                if isinstance(wait_seconds, (int, float)) and not isinstance(wait_seconds, bool) and wait_seconds >= 0
                else float(2**attempt)
            )

        logger.warning(
            "Discourse rate limit for %s %s; retrying in %.1f seconds (%d/%d)",
            method,
            endpoint,
            delay,
            attempt + 1,
            DISCOURSE_429_MAX_RETRIES,
        )
        time.sleep(delay)

    if resp is None:
        raise ApiError(f"Discourse {method} {endpoint} did not make a request")
    if resp.status_code not in (200, 201, 204):
        raise ApiError(f"Discourse {method} {endpoint} failed: {resp.status_code} {resp.text[:200]}")
    if not resp.text:
        if method.upper() in {"GET", "POST"}:
            raise ApiError(f"Discourse {method} {endpoint} returned an empty response body")
        return {}
    try:
        data = resp.json()
    except ValueError as exc:
        raise ApiError(f"Discourse {method} {endpoint} returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ApiError(f"Discourse {method} {endpoint} returned non-object JSON")
    return data


def pretix_list_all(endpoint: str) -> list[dict[str, Any]]:
    """Fetch all results from a paginated Pretix list endpoint."""
    results: list[dict[str, Any]] = []
    resp = pretix_req("GET", endpoint)
    configured_url = urlparse(PRETIX_URL)
    api_base = urljoin(
        f"{PRETIX_URL.rstrip('/')}/",
        f"api/v1/organizers/{ORGANIZER_SLUG}/",
    )
    expected_path_prefix = f"{configured_url.path.rstrip('/')}/api/v1/organizers/{ORGANIZER_SLUG}/"

    def checked_next_url(next_url: str) -> str:
        """Validate a pagination URL stays within the configured API origin."""
        resolved = urlparse(urljoin(api_base, next_url))
        try:
            configured_port = configured_url.port or (443 if configured_url.scheme == "https" else 80)
            resolved_port = resolved.port or (443 if resolved.scheme == "https" else 80)
        except ValueError as exc:
            raise ApiError("Pretix pagination returned an invalid URL") from exc
        if (
            resolved.scheme != configured_url.scheme
            or resolved.hostname != configured_url.hostname
            or resolved_port != configured_port
            or resolved.username is not None
            or resolved.password is not None
            or not resolved.path.startswith(expected_path_prefix)
        ):
            raise ApiError("Pretix pagination URL is outside the configured organizer API")
        return resolved.geturl()

    while True:
        batch = resp.get("results")
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            raise ApiError("Pretix list response contains invalid results")
        results.extend(batch)
        next_url = resp.get("next")
        if next_url is None:
            break
        if not isinstance(next_url, str) or not next_url:
            raise ApiError("Pretix pagination returned an invalid next URL")
        page_url = checked_next_url(next_url)
        try:
            page_resp = PRETIX_CLIENT.request("GET", page_url)
            if page_resp.status_code != 200:
                raise ApiError(f"Pretix pagination failed: {page_resp.status_code}")
            resp = page_resp.json()
            if not isinstance(resp, dict):
                raise ApiError("Pretix pagination returned non-object JSON")
        except (requests.RequestException, ValueError) as exc:
            raise ApiError("Pretix pagination request failed") from exc
    return results


def check_event_exists(slug: str) -> bool:
    """Check for a slug in the events visible to the configured API token.

    Pretix returns 403 for a detail lookup when an event is missing as well as
    when the token cannot view it. The organizer event list is the safe
    read-only inventory for this check; it only establishes visibility to this
    token, not global non-existence.
    """
    try:
        events = pretix_list_all("events")
    except ApiError as exc:
        raise ApiError(
            f"Cannot check Pretix event {slug!r}: GET events/ failed, so its existence "
            f"cannot be established for this API token. Confirm the token can list "
            f"organizer events and check its team permissions. Details: {exc}"
        ) from exc
    return any(event.get("slug") == slug for event in events)
