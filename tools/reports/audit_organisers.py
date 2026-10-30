#!/usr/bin/env python3
"""Build the authentication and profile report for Discourse Meetup organisers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import quote

from tools.common.ansible_events_lib import (
    BADGE_MEETUP_ATTENDEE,
    BADGE_MEETUP_ORGANIZER,
    BADGE_MEETUP_SPEAKER,
    ApiError,
    ORGANIZERS_GROUP_RE,
    USER_CITY_FIELD_ID,
    USER_CITY_FIELD_NAME,
)
from tools.common.reporting import (
    ReportRow,
    discourse_get_json as get_json,
    group_member_usernames,
    user_badge_awards,
)

SYSTEM_GROUPS = {
    "everyone",
    "admins",
    "moderators",
    "staff",
    *(f"trust_level_{level}" for level in range(5)),
}

FIELDNAMES = [
    "Username",
    "Organiser groups",
    "2FA",
    "Badges (speaker / organiser / attendee)",
    "Account created",
    "Last seen",
    "Event locations",
    "Other groups",
]


def organizer_memberships(groups: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Map each organiser username to all matching organiser group names."""
    memberships: dict[str, set[str]] = defaultdict(set)
    for group in groups:
        name = group.get("name")
        if not isinstance(name, str) or not ORGANIZERS_GROUP_RE.fullmatch(name):
            continue
        if group.get("user_count") == 0:
            continue
        for username in group_member_usernames(name):
            memberships[username].add(name)
    return memberships


def other_group_memberships(groups: list[dict[str, Any]], organiser_usernames: set[str]) -> dict[str, set[str]]:
    """Map organiser users to additional non-system group names."""
    memberships: dict[str, set[str]] = defaultdict(set)
    if not organiser_usernames:
        return memberships
    for group in groups:
        name = group.get("name")
        if not isinstance(name, str) or name in SYSTEM_GROUPS or ORGANIZERS_GROUP_RE.fullmatch(name):
            continue
        if group.get("user_count") == 0:
            continue
        for username in group_member_usernames(name) & organiser_usernames:
            memberships[username].add(name)
    return memberships


def _as_text(value: Any) -> str:
    """Convert an optional text value to display text."""
    if isinstance(value, str):
        return value.strip() or "Unknown"
    return "Unknown"


def _as_list(value: Any) -> list[str]:
    """Convert a custom field value into a sorted list for HTML bullets."""
    if isinstance(value, str):
        values = [value.strip()] if value.strip() else []
    elif isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
    else:
        values = []
    return sorted(values, key=str.casefold)


def _event_location_value(user: dict[str, Any], admin_user: dict[str, Any]) -> Any:
    """Find the city custom field across Discourse's serialized field shapes."""
    field_id = str(USER_CITY_FIELD_ID)
    field_key = f"user_field_{field_id}"
    candidates: list[Any] = []
    for record in (admin_user, user):
        custom_fields = record.get("custom_fields")
        if isinstance(custom_fields, dict):
            candidates.extend(
                [
                    custom_fields.get(USER_CITY_FIELD_NAME),
                    custom_fields.get(field_key),
                    custom_fields.get(field_id),
                    custom_fields.get(USER_CITY_FIELD_ID),
                ]
            )
        user_fields = record.get("user_fields")
        if isinstance(user_fields, dict):
            candidates.extend(
                [user_fields.get(field_id), user_fields.get(field_key), user_fields.get(USER_CITY_FIELD_ID)]
            )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value):
            return value
    return None


def user_profile(username: str) -> dict[str, Any]:
    """Fetch one profile and return the audit fields needed for its report row."""
    endpoint = f"u/{quote(username, safe='')}.json"
    data = get_json(endpoint)
    user = data.get("user")
    if not isinstance(user, dict) or user.get("username") != username:
        raise ApiError(f"Discourse profile response for {username!r} has invalid identity data")
    user_id = user.get("id")
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ApiError(f"Discourse profile response for {username!r} has an invalid user ID")

    admin_response = get_json(f"admin/users/{user_id}.json")
    admin_user = admin_response.get("user", admin_response)
    if not isinstance(admin_user, dict):
        raise ApiError(f"Discourse admin profile response for {username!r} is invalid")
    admin_username = admin_user.get("username")
    if admin_username is not None and admin_username != username:
        raise ApiError(f"Discourse admin profile response for {username!r} has mismatched identity data")

    second_factor = user.get("second_factor_enabled")
    if second_factor is True:
        two_factor = "Enabled"
    elif second_factor is False:
        two_factor = "Not enabled"
    else:
        two_factor = "Unknown"

    event_locations = _event_location_value(user, admin_user)
    badge_ids = set(user_badge_awards(username))
    return {
        "2FA": two_factor,
        "Badges (speaker / organiser / attendee)": "".join(
            "✅" if badge_id in badge_ids else "❌"
            for badge_id in (BADGE_MEETUP_SPEAKER, BADGE_MEETUP_ORGANIZER, BADGE_MEETUP_ATTENDEE)
        ),
        "Account created": _as_text(user.get("created_at")),
        "Last seen": _as_text(user.get("last_seen_at")),
        "Event locations": _as_list(event_locations),
    }


def build_report(groups: list[dict[str, Any]]) -> list[ReportRow]:
    """Build one audit row per member across all matching organiser groups."""
    organisers = organizer_memberships(groups)
    usernames = set(organisers)
    other_groups = other_group_memberships(groups, usernames)

    rows: list[ReportRow] = []
    for username in sorted(usernames, key=str.casefold):
        profile = user_profile(username)
        rows.append(
            {
                "Username": username,
                "Organiser groups": sorted(organisers[username], key=str.casefold),
                **profile,
                "Other groups": sorted(other_groups.get(username, set()), key=str.casefold),
            }
        )
    return rows
