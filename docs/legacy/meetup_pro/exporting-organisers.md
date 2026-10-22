# Temporary: Export Meetup Pro organisers

> This page documents a migration utility only. Remove it with the other Meetup Pro migration material when the transition is complete.

The organiser export utility produces a report to help identify existing Meetup Pro organisers during migration. It does not provision access to the Forum or Pretix.

Before running the export, obtain authorization and configure these Meetup Pro OAuth values through the approved secret-management process:

- `MEETUP_CLIENT_KEY`
- `MEETUP_SIGNING_KEY_ID`
- `MEETUP_MEMBER_ID`
- `MEETUP_PRIVATE_KEY` (path to the private key file; keep the file access-restricted)

The exporter requires all four values. Do not paste secrets into shell history, commit credentials or private keys, or attach raw exports to public issues. Use the minimum necessary access and store the output only in the approved location.

From the repository root, run the current module command:

```console
uv run python -m tools.meetup_pro.meetup_list_organisers
```

Verify export access and handling with the Community Team; reports may contain personal information. Manage current organiser permissions using [Managing organiser access](../../community-team/managing-organisers.md).
