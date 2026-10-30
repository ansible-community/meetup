# Add a city

Adding a city establishes the Forum space, organiser access, and Pretix team used for local events. The Pretix auth plugin is city agnostic: a new city does not require edits or a release in `pretix-discourse-auth`.

## Before changing the registry

- Confirm the local organiser contact and city display name. The city slug must equal the normalized Pretix team display-name suffix: apply Unicode NFKD, discard every character except ASCII letters, then lowercase. For example, `New York` uses `newyork` and `São Paulo` uses `saopaulo`. Avoid display names that normalize to the same slug; ambiguous matches deny login.
- Agree a stable city slug containing lowercase ASCII letters only (`^[a-z]+$`) and a time zone.
- Confirm that organisers understand the [role](../organisers/role.md) and can enable two-factor authentication where required.
- Review the Forum group and Pretix team naming contract in the [auth plugin specification](../reference/pretix-discourse-auth-specification.md).

## Procedure

1. Add the city to `tools/common/ansible_event_cities.py` with its display name, matching normalized city slug, and time zone, following the [tooling specification](../reference/tooling-specification.md).
2. Review the diff, run the repository checks, and merge and deploy through the normal pull request workflow.
3. [Provision the environment](provisioning.md) and verify the city category, `meetup-organisers-{city}` Forum group, and `Ansible Meetup Organisers - {city display name}` Pretix team. The auth plugin requires a unique matching city team under its configured Pretix organizer.
4. Add the agreed organisers using [Managing organiser access](managing-organisers.md).
5. Confirm the Forum topic is visible and that an organiser can access the correct Pretix dashboard.

For example, add a Meetup Pro city to `MEETUP_PRO_CITIES` as a `CityInfo` entry, keeping the section sorted by region, country, and city:

```python
CityInfo("Asia Pacific", "Australia", "cairns", "Cairns", "Australia/Brisbane"),
```

Keep credentials and attendee data out of source control and pull request discussions.
