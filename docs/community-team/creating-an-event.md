# Create an event

The Community Team creates the Forum event topic and matching Pretix registration. The Forum topic is the canonical event information page; Pretix stores a backlink to it. Event details do not synchronize between services.

## Gather details

Ask the organiser for the city, title, date, start/end time and time zone, format, venue or access details, capacity, description, initial agenda, and organiser account. Confirm that the event is free and approved for publication.

## Create and review

1. Confirm that the city has been [provisioned](adding-a-city.md) and the organiser has access.
2. Configure `PRETIX_URL=https://rsvp.ansible.com` for production, then run the event creation module from the repository root. Replace the example values with the approved event details:

   ```console
   uv run python -m tools.events.create_event --city london --date 2026-10-31T18:00:00 --capacity 100 --organiser FORUM_USERNAME
   ```

   See the [tooling specification](../reference/tooling-specification.md) for all options and validation rules.
3. Review the created Forum topic, event widget, Pretix registration page, and backlink.
4. Check that the Forum topic's RSVP link opens the matching Pretix event and that the Pretix event links back to the topic.
5. Give the organiser the Forum topic URL and appropriate dashboard access; ask them to complete the topic and verify public-facing details before promotion.

Do not rely on changes in one service appearing in the other. Update the Forum topic and Pretix settings separately when required.
