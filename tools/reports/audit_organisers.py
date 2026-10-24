#!/usr/bin/env python3
"""Report authentication and profile details for Discourse Meetup organisers.

Run from the meetup-report-hosts directory with:

    uv run python -m tools.reports.audit_organisers
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from tools.common.ansible_events_lib import (
    ApiError,
    ORGANIZERS_GROUP_RE,
    USER_CITY_FIELD_ID,
    USER_CITY_FIELD_NAME,
    discourse_req,
    logger,
    pre_flight_checks,
)

PAGE_SIZE = 200
OUTPUT_DIRECTORY = Path("tools/output")
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
    "Account created",
    "Last seen",
    "Event locations",
    "Other groups",
]


def get_json(endpoint: str, **params: Any) -> dict[str, Any]:
    """Fetch a JSON object from Discourse and raise on malformed responses."""
    query = urlencode(params)
    request_path = f"{endpoint}?{query}" if query else endpoint
    return discourse_req("GET", request_path)


def _list_field(data: dict[str, Any], key: str, endpoint: str) -> list[dict[str, Any]]:
    """Validate and return a list of object records from an API response."""
    value = data.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ApiError(f"Discourse response from {endpoint} is missing a valid {key} list")
    return value


def list_groups() -> list[dict[str, Any]]:
    """Fetch the complete Discourse group directory."""
    groups: list[dict[str, Any]] = []
    page = 0
    while True:
        # The admin endpoint accepts writes but does not return a JSON listing
        # for GET; use Discourse's paginated group directory instead.
        endpoint = "groups.json"
        data = get_json(endpoint, page=page)
        batch = _list_field(data, "groups", endpoint)
        groups.extend(batch)
        if not batch:
            return groups
        page += 1


def group_members(group_name: str) -> set[str]:
    """Return every username in a group, following offset pagination."""
    members: set[str] = set()
    offset = 0
    while True:
        endpoint = f"groups/{quote(group_name, safe='')}/members.json"
        data = get_json(endpoint, offset=offset, limit=PAGE_SIZE)
        batch = _list_field(data, "members", endpoint)
        usernames: list[str] = []
        for member in batch:
            username = member.get("username")
            if not isinstance(username, str) or not username:
                raise ApiError(f"Discourse group {group_name!r} returned a member without a username")
            usernames.append(username)
        members.update(usernames)
        if len(batch) < PAGE_SIZE:
            return members
        offset += PAGE_SIZE


def organizer_memberships(groups: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Map each organiser username to all matching organiser group names."""
    memberships: dict[str, set[str]] = defaultdict(set)
    for group in groups:
        name = group.get("name")
        if not isinstance(name, str) or not ORGANIZERS_GROUP_RE.fullmatch(name):
            continue
        if group.get("user_count") == 0:
            continue
        for username in group_members(name):
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
        for username in group_members(name) & organiser_usernames:
            memberships[username].add(name)
    return memberships


def _as_text(value: Any) -> str:
    """Convert a scalar or list field to a readable value, or Unknown."""
    if isinstance(value, str):
        return value.strip() or "Unknown"
    if isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
        return "; ".join(values) if values else "Unknown"
    return "Unknown"


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
    return next(
        (
            value
            for value in candidates
            if isinstance(value, str)
            and value.strip()
            or isinstance(value, list)
            and any(isinstance(item, str) and item.strip() for item in value)
        ),
        None,
    )


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
    return {
        "2FA": two_factor,
        "Account created": _as_text(user.get("created_at")),
        "Last seen": _as_text(user.get("last_seen_at")),
        "Event locations": _as_text(event_locations),
    }


def build_report(groups: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build one audit row per member across all matching organiser groups."""
    organisers = organizer_memberships(groups)
    usernames = set(organisers)
    other_groups = other_group_memberships(groups, usernames)

    rows: list[dict[str, str]] = []
    for username in sorted(usernames, key=str.casefold):
        profile = user_profile(username)
        rows.append(
            {
                "Username": username,
                "Organiser groups": "; ".join(sorted(organisers[username])),
                **profile,
                "Other groups": "; ".join(sorted(other_groups.get(username, set()))) or "None",
            }
        )
    return rows


def default_output_path() -> Path:
    """Return a timestamped report path in the local output directory."""
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return OUTPUT_DIRECTORY / f"organiser-audit-{timestamp}.csv"


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    """Write a private CSV report, refusing to overwrite an existing file."""
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(output_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise


def print_table(rows: list[dict[str, str]]) -> None:
    """Print the report fields as a readable terminal table."""
    widths = {field: max([len(field), *(len(row[field]) for row in rows)]) for field in FIELDNAMES}
    separator = "+-" + "-+-".join("-" * widths[field] for field in FIELDNAMES) + "-+\n"

    def line(values: dict[str, str]) -> str:
        return "| " + " | ".join(values[field].ljust(widths[field]) for field in FIELDNAMES) + " |\n"

    sys.stdout.write(separator)
    sys.stdout.write(line({field: field for field in FIELDNAMES}))
    sys.stdout.write(separator)
    for row in rows:
        sys.stdout.write(line(row))
    sys.stdout.write(separator)


def main() -> None:
    """Generate and save the organiser audit report."""
    pre_flight_checks(require_discourse=True, require_pretix=False)
    parser = argparse.ArgumentParser(description="Audit Discourse Meetup organiser accounts and group memberships")
    parser.add_argument(
        "--output", type=Path, default=None, help="CSV output path (default: timestamped tools/output file)"
    )
    args = parser.parse_args()

    groups = list_groups()
    rows = build_report(groups)
    output_path = args.output or default_output_path()
    write_csv(rows, output_path)
    print_table(rows)
    logger.info("Wrote %d organiser audit row(s) to %s", len(rows), output_path)


if __name__ == "__main__":
    main()
