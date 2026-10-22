# Temporary: Export Meetup Pro groups

> This page documents a migration utility only. Remove it with the other Meetup Pro migration material when the transition is complete.

The group export utility produces a report of Meetup Pro groups for migration planning. It is not used to create or manage current Forum events.

Before running the export, obtain authorization and configure these Meetup Pro OAuth values through the approved secret-management process:

- `MEETUP_CLIENT_KEY`
- `MEETUP_SIGNING_KEY_ID`
- `MEETUP_MEMBER_ID`
- `MEETUP_PRIVATE_KEY` (path to the private key file; keep the file access-restricted)

The exporter requires all four values. Do not paste secrets into shell history, commit credentials or private keys, or attach raw exports to public issues. Use the minimum necessary access and store the output only in the approved location.

From the repository root, run the current module command:

```console
uv run python -m tools.meetup_pro.meetup_list_groups
```

The command writes `tmp/meetup-groups.csv` by default. Pass `--output PATH` to choose another destination. The file is created with owner-only permissions.

Use the export only for the migration task, store it in the approved location, and limit access because it may contain personal information. For current community processes, start at [Ansible Meetups](../../index.md).
