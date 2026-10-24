# Audit organiser accounts

Use the audit report to review every member of a Forum group matching `meetup-organisers-{city}`. Organisers are required to enable two-factor authentication (2FA); the report highlights accounts where 2FA is not enabled so the Community Team can follow up.

## Run the report

From the `meetup-report-hosts` directory, with an authorized `DISCOURSE_API_KEY` configured, run:

```console
uv run python -m tools.reports.audit_organisers
```

The command prints a table and writes a CSV to `tools/output/organiser-audit-<timestamp>.csv`. Generated files in `tools/output/` are ignored by Git and created with owner-only permissions. To choose a different path:

```console
uv run python -m tools.reports.audit_organisers --output tools/output/organiser-audit.csv
```

The command is read-only. It reports one row per user, including all matching organiser groups, 2FA status, account creation date, last seen timestamp, event locations, and other non-system group memberships. “Last seen” is the timestamp Discourse exposes and may differ from the precise time of the user's last login. Missing API values are shown as `Unknown`; the report stops on API errors rather than saving partial results.

Review rows marked `Not enabled` and follow up with the relevant organiser. Other groups excludes Discourse's default `everyone`, `admins`, `moderators`, `staff`, and `trust_level_0` through `trust_level_4` groups.
