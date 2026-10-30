#!/usr/bin/env python3
"""Build the attendee group membership, account age, and invite-link report."""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import quote, urlparse

from tools.common.ansible_events_lib import (
    ATTENDEE_GROUP_PREFIX,
    BADGE_MEETUP_ATTENDEE,
    BADGE_MEETUP_MIGRATED,
    CITIES,
    INVITE_API_USERNAME,
    MIGRATED_GROUP_NAME,
    MEETUP_INVITE_DESCRIPTION_PREFIX,
    ApiError,
    discourse_req,
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
INVITE_REDEMPTIONS_QUERY_ID = 34
INVITE_QUERY_RESULT_LIMIT = 10_000

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


def _invite_key(invite: dict[str, Any]) -> str | None:
    """Get an invite key from an invite record, without exposing it in output."""
    key = invite.get("invite_key")
    if isinstance(key, str) and key:
        return key
    link = invite.get("link")
    if isinstance(link, str):
        path_parts = [part for part in urlparse(link).path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[-2] == "invites":
            return path_parts[-1]
    return None


def invite_metadata_by_key() -> dict[str, dict[str, Any]]:
    """Look up gundalow's pending and expired invite links by key."""
    metadata_by_key: dict[str, dict[str, Any]] = {}
    for status in ("pending", "expired"):
        offset = 0
        endpoint = f"u/{INVITE_API_USERNAME}/invited/{status}.json"
        while True:
            data = get_json(endpoint, run_as=INVITE_API_USERNAME, offset=offset)
            invites = response_records(data, "invites", endpoint)
            for invite in invites:
                if invite.get("email"):
                    # Email-targeted invites are not reusable campaign links.
                    continue
                key = _invite_key(invite)
                if key is None:
                    # Email invitations do not have a reusable invite key.
                    continue
                raw_groups = invite.get("groups")
                if not isinstance(raw_groups, list):
                    raise ApiError("Discourse invite response is missing its group list")
                group_names: set[str] = set()
                for group in raw_groups:
                    name = group.get("name") if isinstance(group, dict) else group
                    if not isinstance(name, str) or not name:
                        raise ApiError("Discourse invite response contains an invalid group")
                    group_names.add(name)
                description = invite.get("description")
                if key in metadata_by_key:
                    raise ApiError("Discourse returned a duplicate invite key")
                metadata_by_key[key] = {
                    "description": description if isinstance(description, str) else "Unnamed invite",
                    "groups": group_names,
                    "list_status": status,
                    "created_at": parse_created_at(invite.get("created_at")),
                    "expires_at": parse_created_at(invite.get("expires_at")),
                    "max_redemptions_allowed": invite.get("max_redemptions_allowed"),
                    "redemption_count": invite.get("redemption_count"),
                    "expired": invite.get("expired"),
                    "grants_admin": invite.get("grants_admin"),
                    "grants_moderator": invite.get("grants_moderator"),
                }
            if not invites:
                break
            offset += len(invites)
    return metadata_by_key


def invite_link_redemptions(
    group_names: list[str],
    *,
    now: dt.datetime | None = None,
) -> tuple[dict[str, set[str]], list[ReportRow]]:
    """Attribute redemptions and validate gundalow's attendee invite links."""
    report_time = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    endpoint = f"admin/plugins/explorer/queries/{INVITE_REDEMPTIONS_QUERY_ID}/run.json"
    result = discourse_req(
        "POST",
        endpoint,
        {"params": "{}", "limit": INVITE_QUERY_RESULT_LIMIT},
    )
    if result.get("success") is not True or result.get("errors"):
        errors = result.get("errors")
        raise ApiError(f"Discourse Data Explorer query {INVITE_REDEMPTIONS_QUERY_ID} failed: {errors!r}")

    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or any(not isinstance(column, str) for column in columns):
        raise ApiError("Discourse invite-redemption query returned invalid columns")
    if not isinstance(rows, list):
        raise ApiError("Discourse invite-redemption query returned invalid rows")
    required_columns = ("invitee", "inviter", "invite_key")
    if any(column not in columns for column in required_columns):
        raise ApiError("Discourse invite-redemption query must return invitee, inviter, and invite_key")
    result_count = result.get("result_count")
    if isinstance(result_count, int) and not isinstance(result_count, bool) and result_count > len(rows):
        raise ApiError(
            f"Discourse invite-redemption query returned {len(rows)} of {result_count} rows; "
            "increase its result limit or paginate the query"
        )

    indices = {column: columns.index(column) for column in required_columns}
    link_metadata = invite_metadata_by_key()
    wanted_groups = set(group_names)
    users_by_group = {group_name: set() for group_name in group_names}
    users_by_invite: dict[str, set[str]] = {}
    unmatched_invites = 0
    inviter_name = INVITE_API_USERNAME.casefold()
    for row in rows:
        if not isinstance(row, list) or len(row) < len(columns):
            raise ApiError("Discourse invite-redemption query returned a malformed row")
        invitee = row[indices["invitee"]]
        inviter = row[indices["inviter"]]
        invite_key = row[indices["invite_key"]]
        if not all(isinstance(value, str) for value in (invitee, inviter, invite_key)):
            raise ApiError("Discourse invite-redemption query returned invalid invite data")
        if inviter.casefold() != inviter_name:
            continue
        metadata = link_metadata.get(invite_key)
        if metadata is None:
            unmatched_invites += 1
            continue
        users_by_invite.setdefault(invite_key, set()).add(invitee.casefold())
        invite_groups = metadata["groups"]
        for group_name in wanted_groups.intersection(invite_groups):
            users_by_group[group_name].add(invitee.casefold())

    if unmatched_invites:
        logger.warning("%d redeemed invite record(s) had no active or expired invite metadata", unmatched_invites)

    invite_rows: list[ReportRow] = []
    city_by_slug = {city.slug: city for city in CITIES}
    for invite_key, metadata in link_metadata.items():
        all_invite_groups = sorted(metadata["groups"], key=str.casefold)
        if not wanted_groups.intersection(all_invite_groups):
            continue

        max_uses = metadata["max_redemptions_allowed"]
        used = metadata["redemption_count"]
        usage_valid = (
            isinstance(max_uses, int)
            and not isinstance(max_uses, bool)
            and max_uses > 0
            and isinstance(used, int)
            and not isinstance(used, bool)
            and 0 <= used <= max_uses
        )
        remaining = max_uses - used if usage_valid else None
        expires_at = metadata["expires_at"]
        if (
            metadata["list_status"] == "expired"
            or metadata["expired"] is True
            or (expires_at is not None and expires_at <= report_time)
        ):
            link_status = "✗ Expired"
        elif not usage_valid:
            link_status = "✗ Usage limit unavailable"
        elif remaining == 0:
            link_status = "✗ No uses remaining"
        elif metadata["list_status"] == "pending" and expires_at is not None:
            link_status = "✓ Active (API)"
        else:
            link_status = "✗ Expiry unavailable"

        # Migration links should add exactly the city's attendee group and the
        # migration tracking group, with no staff role grants.
        attendee_groups = [name for name in all_invite_groups if name.startswith(f"{ATTENDEE_GROUP_PREFIX}-")]
        expected_description = None
        if len(attendee_groups) == 1:
            city_slug = attendee_groups[0].removeprefix(f"{ATTENDEE_GROUP_PREFIX}-")
            city = city_by_slug.get(city_slug)
            if city is not None:
                expected_description = f"{MEETUP_INVITE_DESCRIPTION_PREFIX}{city.city}"
        configuration_valid = (
            len(attendee_groups) == 1
            and set(all_invite_groups) == {attendee_groups[0], MIGRATED_GROUP_NAME}
            and metadata["description"] == expected_description
            and metadata["grants_admin"] is False
            and metadata["grants_moderator"] is False
        )
        invite_rows.append(
            {
                "Invite": metadata["description"],
                "Created (UTC)": metadata["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                if metadata["created_at"] is not None
                else "Unknown",
                "Expires (UTC)": expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at is not None else "Unknown",
                "Groups": all_invite_groups,
                "Link status (API)": link_status,
                "Group / role check": "✓ Correct" if configuration_valid else "✗ Check configuration",
                "Redemptions / limit": f"{used} / {max_uses}" if usage_valid else "Unknown",
                "Remaining uses": str(remaining) if remaining is not None else "Unknown",
                "Unique redemptions": str(len(users_by_invite.get(invite_key, set()))),
            }
        )
    invite_rows.sort(key=lambda row: (str(row["Invite"]).casefold(), str(row["Created (UTC)"])))
    if unmatched_invites:
        invite_rows.append(
            {
                "Invite": "Unmatched redemption rows (link may be exhausted or unavailable)",
                "Created (UTC)": "—",
                "Expires (UTC)": "Unknown",
                "Groups": ["Unknown"],
                "Link status (API)": "? Not validated",
                "Group / role check": "? Not validated",
                "Redemptions / limit": "Unknown",
                "Remaining uses": "Unknown",
                "Unique redemptions": str(unmatched_invites),
            }
        )
    return users_by_group, invite_rows


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
    invite_link_users: set[str] | dict[str, set[str]],
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
        if isinstance(invite_link_users, dict):
            invite_users = {username.casefold() for username in invite_link_users.get(group_name, set())}
            invite_link_count = sum(username.casefold() in invite_users for username in usernames)
        else:
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
