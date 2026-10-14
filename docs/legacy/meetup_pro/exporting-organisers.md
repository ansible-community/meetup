# Temporary: Export Meetup Pro organisers

> This page documents a migration utility only. Remove it with the other Meetup Pro migration material when the transition is complete.

The organiser export utility produces a report to help identify existing Meetup Pro organisers during migration. It does not provision access to the Forum or Pretix.

From the repository root, run the current module command:

```console
uv run python -m tools.meetup_pro.meetup_list_organisers
```

Verify export access and handling with the Community Team; reports may contain personal information. Manage current organiser permissions using [Managing organiser access](../../community-team/managing-organisers.md).
