# Community reports

The combined HTML report provides a point-in-time audit of organiser security and Meetup attendee group growth. Run it from the `meetup-report-hosts` directory with an authorized `DISCOURSE_API_KEY` configured.

## Generate all reports

Generate both report sections in one HTML file:

```console
uv run python -m tools.reports.generate_all
```

The command writes one private HTML file under `tools/output/`, with a timestamp in its filename. Choose another output path with `--output`:

```console
uv run python -m tools.reports.generate_all --output tools/output/community-audit.html
```

Generated reports under `tools/output/` are ignored by Git and created with owner-only permissions. The HTML page has a table of contents, paperclip anchor links beside headings, and sorted bullet lists for group names and event locations.

## Organiser accounts

The organiser report includes every member of a `meetup-organisers-{city}` group, their 2FA status, Meetup badge status, account creation date, last seen timestamp, event locations, and other non-system group memberships. The badge column shows speaker, organiser, and attendee badge status in that order using ticks and crosses. “Last seen” is the timestamp Discourse exposes and may differ from the precise time of the user's last login. Missing profile values are shown as `Unknown`. Follow up on rows marked `Not enabled` because organisers are required to use 2FA.

## Attendee groups

The attendee report includes a `meetup-migrated-attendees` summary table followed by one row for each `meetup-attendee-{city}` group. Both tables show member count; cumulative account creation counts for rolling UTC windows of 1, 2, 3, 4, 5, and 10 days; and the count and percentage of members recorded as having redeemed a Forum invite link created by `gundalow`. These Forum invite links are the indicator used to track people joining from Meetup Pro. Empty groups show `N/A` for the percentage. Missing account creation timestamps are excluded from the age counts and reported as a warning.

The attendee badges table follows the attendee group table. It counts Meetup attendee and migrated badge awards for the migrated group and each attendee city group.
