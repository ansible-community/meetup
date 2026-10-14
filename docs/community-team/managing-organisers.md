# Manage organiser access

Organiser access is scoped to a city. Add only people who need to manage that city's Meetup activity, and remove access when it is no longer needed.

1. Confirm the person's Forum account and city role with the existing organiser contact.
2. The Ansible Community Team manually updates the city's Forum group, named `meetup-organisers-{city}` (for example, `meetup-organisers-london`). Do not create a different spelling or pluralization; the group name is part of the access contract.
3. Ensure the account meets the authentication requirements in the [Pretix authentication specification](../reference/pretix-discourse-auth-specification.md), including two-factor authentication where enforced.
4. Pretix organiser-team membership is synchronized from the Forum group at login. The auth plugin resolves the city team dynamically under its configured Pretix organizer; ensure the city has been [provisioned](adding-a-city.md) with a unique matching team. Ask the organiser to sign in to Pretix after a group change, then verify access is limited to the intended city events.
5. Tell the organiser how to access the Forum topic and Pretix dashboard without sharing credentials or attendee data.

See [Troubleshooting](troubleshooting.md) if authentication or permissions do not work as expected.
