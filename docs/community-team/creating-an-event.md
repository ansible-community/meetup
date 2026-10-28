# Create an event

The Community Team creates the Pretix registration by default. Add `--forum` to also create a Forum topic and link the two services. Event details do not synchronize between services.

## Gather details

Ask the organiser for the city, title, date, start/end time and time zone, format, venue or access details, capacity, description, and initial agenda. If creating a Forum topic, also collect the Forum organiser account. Confirm that the event is free and approved for publication.

## Create and review

1. Confirm that the city has been [provisioned](adding-a-city.md) and the organiser has access.
2. Configure `PRETIX_URL=https://rsvp.ansible.com` for production, then run the event creation module from the repository root. Replace the example values with the approved event details:

   ```console
   uv run python -m tools.events.create_event --city london --date 2026-10-31T18:00:00 --capacity 100 --forum --organiser FORUM_USERNAME
   ```

   Without `--forum`, the command creates only the Pretix event and does not require Forum credentials or `--organiser`. See the [tooling specification](../reference/tooling-specification.md) for all options and validation rules.
3. Review the Pretix registration page and, when `--forum` was used, the Forum topic and backlinks.
4. When a Forum topic was created, check that its RSVP link opens the matching Pretix event and that the Pretix event links back to the topic.
5. Give the organiser the relevant event URL and appropriate dashboard access; ask them to verify public-facing details before promotion.

Do not rely on changes in one service appearing in the other. Update the Forum topic and Pretix settings separately when required.
