# Temporary: Export Meetup Pro groups

> This page documents a migration utility only. Remove it with the other Meetup Pro migration material when the transition is complete.

The group export utility produces a report of Meetup Pro groups for migration planning. It is not used to create or manage current Forum events.

From the repository root, run the current module command:

```console
uv run python -m tools.meetup_pro.meetup_list_groups
```

Use the export only for the migration task, store it in the approved location, and limit access because it may contain personal information. For current community processes, start at [Ansible Meetups](../../index.md).
