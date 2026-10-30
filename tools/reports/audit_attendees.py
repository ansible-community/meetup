#!/usr/bin/env python3
"""Build the attendee group membership, account age, and invite-link report."""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import quote

from tools.common.ansible_events_lib import (
    ATTENDEE_GROUP_PREFIX,
    BADGE_MEETUP_ATTENDEE,
    BADGE_MEETUP_MIGRATED,
    INVITE_API_USERNAME,
    ApiError,
    logger,
)
from tools.common.reporting import (
    ReportRow,
    discourse_get_json as get_json,
    group_members_by_name,
    response_records,
    usernames_for_groups,
    user_badge_awards,
)

ACCOUNT_AGE_DAYS = (1, 2, 3, 4, 5, 10)

FIELDNAMES = [
    "Attendee group",
    "Members",
    *(f"Accounts created in past {days} day(s)" for days in ACCOUNT_AGE_DAYS),
    "Forum invite-link members",
    "Forum invite-link members (%)",
]

BADGE_FIELDNAMES = [
    "Group",
    "Members",
    "Meetup attendee badge awards",
    "Meetup migrated badge awards",
]


def attendee_group_names(groups: list[dict[str, Any]]) -> list[str]:
    """Select every group named meetup-attendee-<lowercase-city>."""
    names: set[str] = set()
    prefix = f"{ATTENDEE_GROUP_PREFIX}-"
    for group in groups:
        name = group.get("name")
        if isinstance(name, str) and name.startswith(prefix):
            slug = name.removeprefix(prefix)
            if slug and slug.isascii() and slug.isalpha() and slug.islower():
                names.add(name)
    return sorted(names)


def invite_link_usernames() -> set[str]:
    """List users who redeemed Forum invite links created by the Meetup account."""
    usernames: set[str] = set()
    offset = 0
    while True:
        endpoint = f"u/{INVITE_API_USERNAME}/invited/redeemed.json"
        data = get_json(endpoint, run_as=INVITE_API_USERNAME, offset=offset)
        invites = response_records(data, "invites", endpoint)
        for invite in invites:
            if invite.get("invite_source") != "link":
                continue
            user = invite.get("user")
            username = user.get("username") if isinstance(user, dict) else None
            if not isinstance(username, str) or not username:
                raise ApiError("Discourse redeemed invite response contains a link invite without a username")
            usernames.add(username)
        if not invites:
            return usernames
        offset += len(invites)


def parse_created_at(value: Any) -> dt.datetime | None:
    """Parse a Discourse account timestamp and normalize it to UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        created_at = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=dt.UTC)
    return created_at.astimezone(dt.UTC)


def account_created_at(username: str) -> dt.datetime | None:
    """Fetch a user's account creation time, returning None if the field is absent."""
    endpoint = f"u/{quote(username, safe='')}.json"
    data = get_json(endpoint, skip_track_visit="true")
    user = data.get("user")
    if not isinstance(user, dict) or user.get("username") != username:
        raise ApiError(f"Discourse profile response for {username!r} has invalid identity data")
    return parse_created_at(user.get("created_at"))


def _account_age_counts(
    usernames: set[str], created_at_by_username: dict[str, dt.datetime | None], *, now: dt.datetime
) -> tuple[dict[int, int], int]:
    """Count members created within each rolling UTC window and count unknown dates."""
    cutoffs = {days: now - dt.timedelta(days=days) for days in ACCOUNT_AGE_DAYS}
    counts = {days: 0 for days in ACCOUNT_AGE_DAYS}
    unknown = 0
    for username in sorted(usernames, key=str.casefold):
        created_at = created_at_by_username.get(username)
        if created_at is None:
            unknown += 1
            continue
        if created_at > now:
            continue
        for days, cutoff in cutoffs.items():
            if created_at >= cutoff:
                counts[days] += 1
    return counts, unknown


def build_report(
    groups: list[str],
    invite_link_users: set[str],
    *,
    now: dt.datetime | None = None,
    members_by_group: dict[str, set[str]] | None = None,
) -> list[ReportRow]:
    """Build one aggregate row for each attendee group."""
    report_time = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    if members_by_group is None:
        members_by_group = group_members_by_name(groups)
    all_usernames = usernames_for_groups(groups, members_by_group)
    created_at_by_username = {
        username: account_created_at(username) for username in sorted(all_usernames, key=str.casefold)
    }

    rows: list[ReportRow] = []
    for group_name in groups:
        usernames = members_by_group[group_name]
        ages, unknown_dates = _account_age_counts(usernames, created_at_by_username, now=report_time)
        member_count = len(usernames)
        invite_link_count = len(usernames & invite_link_users)
        invite_link_percentage = f"{invite_link_count / member_count * 100:.1f}%" if member_count else "N/A"
        row = {
            "Attendee group": [group_name],
            "Members": str(member_count),
            **{f"Accounts created in past {days} day(s)": str(ages[days]) for days in ACCOUNT_AGE_DAYS},
            "Forum invite-link members": str(invite_link_count),
            "Forum invite-link members (%)": invite_link_percentage,
        }
        if unknown_dates:
            logger.warning("%s: %d member account creation date(s) unavailable", group_name, unknown_dates)
        rows.append(row)
    return rows


def build_badges_report(groups: list[str], *, members_by_group: dict[str, set[str]] | None = None) -> list[ReportRow]:
    """Count attendee and migrated badge awards among members of each group."""
    if members_by_group is None:
        members_by_group = group_members_by_name(groups)
    all_usernames = usernames_for_groups(groups, members_by_group)
    badge_awards_by_username = {
        username: user_badge_awards(username) for username in sorted(all_usernames, key=str.casefold)
    }

    rows: list[ReportRow] = []
    for group_name in groups:
        usernames = members_by_group[group_name]
        rows.append(
            {
                "Group": [group_name],
                "Members": str(len(usernames)),
                "Meetup attendee badge awards": str(
                    sum(badge_awards_by_username[username].count(BADGE_MEETUP_ATTENDEE) for username in usernames)
                ),
                "Meetup migrated badge awards": str(
                    sum(badge_awards_by_username[username].count(BADGE_MEETUP_MIGRATED) for username in usernames)
                ),
            }
        )
    return rows
