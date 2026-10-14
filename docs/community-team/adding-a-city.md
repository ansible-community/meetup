# Add a city

Adding a city establishes the Forum space, organiser access, and Pretix team used for local events.

## Before changing the registry

- Confirm the local organiser contact and city display name.
- Agree a stable lowercase city slug and time zone.
- Confirm that organisers understand the [role](../organisers/role.md) and can enable two-factor authentication where required.
- Review any matching city mapping needed by the auth plugin specification.

## Procedure

1. Add the city to the tooling's city registry and associated Pretix team mapping, following the [tooling specification](../reference/tooling-specification.md).
2. Update the auth plugin's city-to-team mapping in its own repository and coordinate deployment with the plugin maintainer.
3. Review the diff, run the repository checks, and merge through the normal pull request workflow.
4. Provision the environment and verify the city category, organiser group, and Pretix team.
5. Add the agreed organisers using [Managing organiser access](managing-organisers.md).
6. Confirm the Forum topic is visible and that an organiser can access the correct Pretix dashboard.

Keep credentials and attendee data out of source control and pull request discussions.
