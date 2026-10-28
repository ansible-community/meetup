# Future read-only Pretix diagnostics endpoint

`tools.environment.check_setup` runs from an operator workstation and can only
inspect state exposed by Pretix and Forum APIs. It deliberately does not call
`POST /api/v1/organizers/ansible-meetups/discourse/bootstrap-users/`: that
endpoint creates or updates Pretix users. Plugin installation details,
`pretix.cfg` values, loaded worker state, and Pretix bootstrap-user records are
therefore reported as `MANUAL` today.

If those checks need to become automated, add a narrowly scoped **GET-only**
diagnostics endpoint to the Pretix auth plugin and deploy it before relying on
those results. Candidate route:

```text
GET /api/v1/organizers/ansible-meetups/discourse/diagnostics/
```

The route should use the same authorization boundary as the bootstrap-users
endpoint. It should return only the configured bootstrap usernames and
non-secret diagnostic state, such as:

- Plugin version and whether the plugin is registered/enabled.
- Boolean validity flags for the Forum URL, SSO secret, Admin API credentials,
  organizer slug, and timeout. Never return secret values, lengths, hashes, or
  fragments.
- The configured organizer slug and whether that organizer and template can
  be resolved.
- For each configured bootstrap Forum identity: Forum user ID, Pretix user ID
  if linked, identity-link match, and the Pretix `is_staff` value. Do not return
  email addresses or names.
- Whether the route is running in a process that loaded the current plugin
  configuration. A deployment timestamp or config fingerprint should be
  omitted unless it can be generated without exposing or enabling inference of
  secrets.

## Endpoint verification ideas

- Assert the route accepts only `GET`; unsupported methods must not mutate
  accounts, settings, teams, sessions, or other data.
- Verify authorization rejects anonymous users and insufficiently scoped API
  tokens, and permits the intended Pretix administrator/token classes.
- Exercise healthy, missing, malformed, and mismatched plugin configuration.
  Responses must expose validity only, never raw secret material.
- Exercise missing Forum users, Forum ID changes, missing Pretix links, email
  conflicts, and both `is_staff` values. Diagnostics must not create, update,
  or delete a Pretix user.
- Verify organizer/template lookup failures are reported without triggering
  provisioning or exposing internal exception text.
- Confirm the response remains useful when the Forum API is unavailable, and
  distinguishes unavailable evidence from a confirmed misconfiguration.
- Add integration coverage proving this route invokes no account bootstrap
  helper and performs no writes.
- Update the checker only after the endpoint is deployed; retain `MANUAL`
  output for any state that the endpoint does not directly verify.

Treat this as a proposed interface, not an existing route. Do not point the
checker at it until the plugin implements and deploys it.
