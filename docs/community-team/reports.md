# Community reports

The combined HTML report provides a point-in-time audit of organiser security and Meetup attendee group growth. Run it from the `meetup-report-hosts` directory with an authorized `DISCOURSE_API_KEY` configured.

## Generate all reports

Refresh the Meetup Pro group-count snapshot first, then generate the combined report. The Meetup exporter requires the Meetup Pro credentials listed in the [group export guide](../legacy/meetup_pro/exporting-groups.md).

```console
uv run python -m tools.meetup_pro.meetup_list_groups
```

The exporter writes `tools/output/meetup-groups.json`. The combined report reads that snapshot and includes its collection timestamp and raw Meetup Pro group member counts.

The report also uses Data Explorer query **34** to attribute invite redemptions by `invite_key`. The query must return columns named `invitee`, `inviter`, and `invite_key`; the report looks up `gundalow`'s pending and expired invite records at runtime to map keys to their descriptions and groups. The configured Forum API key must be allowed to run the query. The report shows an invite-level table of unique redeemers, descriptions, and target groups without exposing invite keys. Unused matching links appear with zero redemptions.

Generate the report in one HTML file:

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

The attendee report includes a `meetup-migrated-attendees` summary table followed by one row for each `meetup-attendee-{city}` group. Both tables show member count; cumulative account creation counts for rolling UTC windows of 1, 2, 3, 4, 5, and 10 days; and the count and percentage of members who redeemed a `gundalow` invite whose configured groups include that row's group. Invite-key metadata is read at report time and invite keys are not written into the report. Empty groups show `N/A` for the percentage. Missing account creation timestamps are excluded from the age counts and reported as a warning.

The Meetup Pro source-groups table compares raw source member counts with the matching Forum attendee group and city-link redemptions where a city group exists. Meetup Pro groups can overlap in their membership, so do not sum their counts as unique people. Invite links reused across campaigns provide cumulative redemptions; capture a fresh source snapshot for each reporting point and use separate links if you need campaign-level attribution.

The attendee badges table follows the attendee group table. It counts Meetup attendee and migrated badge awards for the migrated group and each attendee city group.
