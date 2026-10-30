#!/usr/bin/env python3
"""Generate the combined community audit as one HTML file."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from tools.common.ansible_events_lib import ATTENDEE_GROUP_PREFIX, MIGRATED_GROUP_NAME, logger, pre_flight_checks
from tools.common.reporting import (
    ReportSection,
    ReportRow,
    group_members_by_name,
    list_discourse_groups,
    MEETUP_GROUP_SNAPSHOT_PATH,
    render_html_report,
    report_output_path,
    write_private_html,
)
from tools.meetup_pro.meetup_pro_lib import PRO_NETWORK
from tools.reports.audit_attendees import BADGE_FIELDNAMES, FIELDNAMES as ATTENDEE_FIELDNAMES
from tools.reports.audit_attendees import (
    attendee_group_names,
    build_badges_report,
    build_report as build_attendee_report,
    invite_link_redemptions,
)
from tools.reports.audit_organisers import FIELDNAMES as ORGANISER_FIELDNAMES
from tools.reports.audit_organisers import build_report as build_organiser_report

LATEST_REPORT_PATH = Path("tools/output/community-audit.html")
MEETUP_GROUP_FIELDNAMES = [
    "Meetup Pro group",
    "City",
    "Country",
    "Members",
    "Forum attendee group",
    "Forum group members",
    "Current members who redeemed city link",
]
INVITE_FIELDNAMES = [
    "Invite",
    "Created (UTC)",
    "Expires (UTC)",
    "Groups",
    "Link status (API)",
    "Group / role check",
    "Redemptions / limit",
    "Remaining uses",
    "Unique redemptions",
]


def read_meetup_group_snapshot(path: Path = MEETUP_GROUP_SNAPSHOT_PATH) -> dict[str, Any]:
    """Read the tracked Meetup Pro group-count snapshot used by this report."""
    if not path.exists():
        raise FileNotFoundError(
            f"Meetup Pro group snapshot not found at {path}; "
            "run `uv run python -m tools.meetup_pro.meetup_list_groups` first"
        )
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read Meetup Pro group snapshot at {path}") from exc
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("groups"), list):
        raise ValueError(f"Meetup Pro group snapshot at {path} has an invalid structure")
    if not isinstance(snapshot.get("generated_at"), str):
        raise ValueError(f"Meetup Pro group snapshot at {path} is missing generated_at")
    if snapshot.get("network") != PRO_NETWORK:
        raise ValueError(f"Meetup Pro group snapshot at {path} is not for network {PRO_NETWORK!r}")
    return snapshot


def meetup_group_rows(
    snapshot: dict[str, Any],
    attendee_groups: list[str],
    members_by_group: dict[str, set[str]],
    invite_users_by_group: dict[str, set[str]],
) -> list[ReportRow]:
    """Join raw Meetup Pro group counts to matching Forum attendee groups."""
    attendee_prefix = f"{ATTENDEE_GROUP_PREFIX}-"
    forum_groups_by_slug = {name.removeprefix(attendee_prefix): name for name in attendee_groups}
    rows: list[ReportRow] = []
    for source_group in snapshot["groups"]:
        if not isinstance(source_group, dict):
            raise ValueError("Meetup Pro group snapshot contains an invalid group")
        name = source_group.get("name")
        city = source_group.get("city")
        country = source_group.get("country")
        count = source_group.get("members")
        if not isinstance(name, str) or not isinstance(city, str) or not isinstance(country, str):
            raise ValueError("Meetup Pro group snapshot contains invalid group names or locations")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"Meetup Pro group {name!r} has an invalid member count")
        city_slug = "".join(char for char in city.casefold() if char.isascii() and char.isalpha())
        forum_group = forum_groups_by_slug.get(city_slug)
        if forum_group is None:
            forum_members = 0
            invite_members = 0
            forum_group_label = "No matching city group"
        else:
            forum_members = len(members_by_group[forum_group])
            invite_usernames = {username.casefold() for username in invite_users_by_group.get(forum_group, set())}
            invite_members = sum(username.casefold() in invite_usernames for username in members_by_group[forum_group])
            forum_group_label = forum_group
        rows.append(
            {
                "Meetup Pro group": name,
                "City": city,
                "Country": country,
                "Members": str(count),
                "Forum attendee group": forum_group_label,
                "Forum group members": str(forum_members),
                "Current members who redeemed city link": str(invite_members),
            }
        )
    return sorted(
        rows,
        key=lambda row: (str(row["City"]).casefold(), str(row["Meetup Pro group"]).casefold()),
    )


def generate_all_reports(output_path: Path | None = None) -> Path:
    """Build each report separately and write both sections to one private HTML file."""
    generated_at = dt.datetime.now().astimezone()
    destination = output_path or report_output_path("community-audit", now=generated_at)
    is_latest_report = destination.resolve() == LATEST_REPORT_PATH.resolve()
    if destination.exists() and not is_latest_report:
        raise FileExistsError(f"Refusing to overwrite existing report: {destination}")

    meetup_snapshot = read_meetup_group_snapshot()
    groups = list_discourse_groups()
    organiser_rows = build_organiser_report(groups)
    attendee_group_list = attendee_group_names(groups)
    badge_group_names = list(dict.fromkeys([MIGRATED_GROUP_NAME, *attendee_group_list]))
    members_by_group = group_members_by_name(badge_group_names)
    invite_users_by_group, invite_rows = invite_link_redemptions(badge_group_names, now=generated_at)
    migrated_rows = build_attendee_report(
        [MIGRATED_GROUP_NAME], invite_users_by_group, now=generated_at, members_by_group=members_by_group
    )
    attendee_rows = build_attendee_report(
        attendee_group_list, invite_users_by_group, now=generated_at, members_by_group=members_by_group
    )
    badge_rows = build_badges_report(badge_group_names, members_by_group=members_by_group)
    meetup_rows = meetup_group_rows(meetup_snapshot, attendee_group_list, members_by_group, invite_users_by_group)
    snapshot_timestamp = meetup_snapshot["generated_at"]
    sections = [
        ReportSection("Organiser accounts", "organiser-accounts", ORGANISER_FIELDNAMES, organiser_rows),
        ReportSection(
            f"Meetup Pro source groups (snapshot {snapshot_timestamp})",
            "meetup-pro-source-groups",
            MEETUP_GROUP_FIELDNAMES,
            meetup_rows,
        ),
        ReportSection(
            "Invite-link redemptions",
            "invite-link-redemptions",
            INVITE_FIELDNAMES,
            invite_rows,
        ),
        ReportSection("Migrated attendees", "migrated-attendees", ATTENDEE_FIELDNAMES, migrated_rows),
        ReportSection("Attendee groups", "attendee-groups", ATTENDEE_FIELDNAMES, attendee_rows),
        ReportSection("Attendee badges", "attendee-badges", BADGE_FIELDNAMES, badge_rows),
    ]
    content = render_html_report("Community Meetup audit", sections, generated_at=generated_at)
    write_private_html(content, destination, overwrite=is_latest_report)
    logger.info("Wrote community audit report to %s", destination.resolve())
    if not is_latest_report:
        write_private_html(content, LATEST_REPORT_PATH, overwrite=True)
    logger.info("Updated latest community audit report at %s", LATEST_REPORT_PATH.resolve())
    return destination


def main() -> None:
    """Generate and save the combined community audit report."""
    parser = argparse.ArgumentParser(description="Generate the combined HTML Meetup audit report")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path (default: timestamped tools/output file; also updates community-audit.html)",
    )
    args = parser.parse_args()
    pre_flight_checks(require_discourse=True, require_pretix=False)
    generate_all_reports(args.output)


if __name__ == "__main__":
    main()
