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

    badge_ids = set(user_badge_awards(username))
    return {
        "2FA": two_factor,
        "Badges (speaker / organiser / attendee)": "".join(
            "✅" if badge_id in badge_ids else "❌"
            for badge_id in (BADGE_MEETUP_SPEAKER, BADGE_MEETUP_ORGANIZER, BADGE_MEETUP_ATTENDEE)
        ),
        "Account created": _as_text(user.get("created_at")),
        "Last seen": _as_text(user.get("last_seen_at")),
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
