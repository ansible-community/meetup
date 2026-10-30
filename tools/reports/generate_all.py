#!/usr/bin/env python3
"""Generate the combined community audit as one HTML file."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from tools.common.ansible_events_lib import MIGRATED_GROUP_NAME, logger, pre_flight_checks
from tools.common.reporting import (
    ReportSection,
    group_members_by_name,
    list_discourse_groups,
    render_html_report,
    report_output_path,
    write_private_html,
)
from tools.reports.audit_attendees import BADGE_FIELDNAMES, FIELDNAMES as ATTENDEE_FIELDNAMES
from tools.reports.audit_attendees import (
    attendee_group_names,
    build_badges_report,
    build_report as build_attendee_report,
    invite_link_usernames,
)
from tools.reports.audit_organisers import FIELDNAMES as ORGANISER_FIELDNAMES
from tools.reports.audit_organisers import build_report as build_organiser_report


def generate_all_reports(output_path: Path | None = None) -> Path:
    """Build each report separately and write both sections to one private HTML file."""
    generated_at = dt.datetime.now().astimezone()
    destination = output_path or report_output_path("community-audit", now=generated_at)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing report: {destination}")

    groups = list_discourse_groups()
    organiser_rows = build_organiser_report(groups)
    attendee_group_list = attendee_group_names(groups)
    badge_group_names = list(dict.fromkeys([MIGRATED_GROUP_NAME, *attendee_group_list]))
    members_by_group = group_members_by_name(badge_group_names)
    invite_users = invite_link_usernames()
    migrated_rows = build_attendee_report(
        [MIGRATED_GROUP_NAME], invite_users, now=generated_at, members_by_group=members_by_group
    )
    attendee_rows = build_attendee_report(
        attendee_group_list, invite_users, now=generated_at, members_by_group=members_by_group
    )
    badge_rows = build_badges_report(badge_group_names, members_by_group=members_by_group)
    sections = [
        ReportSection("Organiser accounts", "organiser-accounts", ORGANISER_FIELDNAMES, organiser_rows),
        ReportSection("Migrated attendees", "migrated-attendees", ATTENDEE_FIELDNAMES, migrated_rows),
        ReportSection("Attendee groups", "attendee-groups", ATTENDEE_FIELDNAMES, attendee_rows),
        ReportSection("Attendee badges", "attendee-badges", BADGE_FIELDNAMES, badge_rows),
    ]
    content = render_html_report("Community Meetup audit", sections, generated_at=generated_at)
    write_private_html(content, destination)
    logger.info("Wrote community audit report to %s", destination.resolve())
    return destination


def main() -> None:
    """Generate and save the combined community audit report."""
    pre_flight_checks(require_discourse=True, require_pretix=False)
    parser = argparse.ArgumentParser(description="Generate the combined HTML Meetup audit report")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path (default: timestamped tools/output file)",
    )
    args = parser.parse_args()
    generate_all_reports(args.output)


if __name__ == "__main__":
    main()
