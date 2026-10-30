# Community reports

The combined HTML report provides a point-in-time audit of organiser security and Meetup attendee group growth. Run it from the `meetup-report-hosts` directory with an authorized `DISCOURSE_API_KEY` configured.

## Generate all reports

The checked-in Meetup Pro group-count snapshot is the denominator for the comparison and changes infrequently. Refresh it when planning a new migration wave or when the Meetup Pro groups are known to have changed; the report records the snapshot timestamp. The exporter requires the Meetup Pro credentials listed in the [group export guide](../legacy/meetup_pro/exporting-groups.md).

```console
uv run python -m tools.meetup_pro.meetup_list_groups
```

The exporter writes `tools/output/meetup-groups.json`. The combined report reads that snapshot and includes its collection timestamp and raw Meetup Pro group member counts.

The report also uses Data Explorer query **34** to attribute invite redemptions by `invite_key`. The query must return columns named `invitee`, `inviter`, and `invite_key`; the report looks up `gundalow`'s pending and expired link records at runtime. The configured Forum API key must be allowed to run the query and read those invite records. The invite table reports link state, expiry, redemptions, remaining uses, configured groups, role-grant flags, and unique redeemers. It does not expose invite keys. Unused matching links appear with zero redemptions. Rows without matching pending/expired metadata are called out; this can happen when a link is exhausted because Discourse omits exhausted links from those lists.

“Active (API)” means the link is listed as pending, has a future expiry, and has redemptions remaining. Discourse's invite serializer does not expose its invalidation flag, so the report cannot detect a link manually invalidated while it still appears pending. For final go-live validation, open each production link in a private browser window and confirm the invite page loads before distributing it. Opening the page does not redeem the invite; do not submit the signup or acceptance form unless performing an approved test.

“Group / role check” passes only when the link grants exactly one registered `meetup-attendee-{city}` group and `meetup-migrated-attendees`, its description matches that city, and it does not grant admin or moderator access. Any cross mark or unknown value needs investigation before sending the link.

Generate the report in one HTML file:

```console
uv run python -m tools.reports.generate_all
```

The command writes a private timestamped HTML report under `tools/output/` and updates `tools/output/community-audit.html` with the same report, replacing the previous copy. Use the stable filename for links or bookmarks. Choose another path for the timestamped copy with `--output`:

```console
uv run python -m tools.reports.generate_all --output tools/output/community-audit.html
```

Generated reports under `tools/output/` are ignored by Git and created with owner-only permissions. The HTML page has a table of contents, paperclip anchor links beside headings, sorted bullet lists for group names and event locations, and a generation timestamp at the bottom.

## Organiser accounts

The organiser report includes every member of a `meetup-organisers-{city}` group, their 2FA status, Meetup badge status, account creation date, last seen timestamp, event locations, and other non-system group memberships. The badge column shows speaker, organiser, and attendee badge status in that order using ticks and crosses. “Last seen” is the timestamp Discourse exposes and may differ from the precise time of the user's last login. Missing profile values are shown as `Unknown`. Follow up on rows marked `Not enabled` because organisers are required to use 2FA.

## Attendee groups

The attendee report includes a `meetup-migrated-attendees` summary table followed by one row for each `meetup-attendee-{city}` group. Both tables show member count; cumulative account creation counts for rolling UTC windows of 1, 2, 3, 4, 5, and 10 days; and the count and percentage of members who redeemed a `gundalow` invite whose configured groups include that row's group. Invite-key metadata is read at report time and invite keys are not written into the report. Empty groups show `N/A` for the percentage. Missing account creation timestamps are excluded from the age counts and reported as a warning.

The Meetup Pro source-groups table compares raw source member counts with the matching Forum attendee group and city-link redemptions where a city group exists. Meetup Pro groups can overlap in their membership, so do not sum their counts as unique people. Invite links reused across campaigns provide cumulative redemptions; use separate links if you need campaign-level attribution. The report measures redemptions and current group membership, not link clicks or how far someone got through signup.

The attendee badges table follows the attendee group table. It counts Meetup attendee and migrated badge awards for the migrated group and each attendee city group.
