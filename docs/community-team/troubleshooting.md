# Troubleshoot event tooling and access

Start by identifying which part is failing: Forum content or permissions, Pretix registration or dashboard access, or the provisioning tooling.

## Forum or organiser access

- Confirm the account can sign in to the Forum and has completed any required security challenge.
- Check the person is in the correct city organiser group and the city category permissions are reconciled.
- Compare the intended group and category names with the [tooling specification](../reference/tooling-specification.md).

## Pretix login or RSVP

- Verify the Pretix event is public, free, and has available capacity.
- Check the Forum-to-Pretix RSVP link and the Pretix-to-Forum backlink independently.
- Confirm the auth plugin configuration and authentication requirements in its [specification](../reference/pretix-discourse-auth-specification.md).
- For an organiser login failure, verify the `meetup-organisers-{city}` claim resolves to exactly one city team under the configured Pretix organizer. Missing or ambiguous teams deny login; reconcile provisioning and naming. Adding a city does not require an auth plugin edit or release.

## Provisioning failure

- Check the target environment URL and required API credentials without exposing secrets in logs or issues.
- Review the first reported API error and whether a previous run partially created resources.
- Resolve partial state before retrying; do not create duplicate events.
- Capture the command, sanitized error, and affected city/event when escalating to maintainers.
