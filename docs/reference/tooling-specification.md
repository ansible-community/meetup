# Meetup tooling specification

---

## 1. Executive Summary

The Ansible Community events tooling supports community-owned Meetups using two external systems. Meetup Pro migration utilities are temporary and documented separately under [Legacy Meetup Pro migration](../legacy/meetup_pro/member-migration.md).

- **Pretix** (self-hosted, open-source): Event ticketing, RSVP, QR code generation, check-in, and attendee management. Pretix stores no passwords and has no native user registration.
- **Discourse** (`forum.ansible.com`): Identity provider (SSO), community discussion, event agenda hosting, group permissions, and moderation. Discourse is the single source of truth for user identity.

The platform provides:

1. **Zero-friction RSVP** for free community meetups via Discourse SSO into Pretix.
2. **Regional isolation** so local organizers can only see their own city's attendee data.
3. **Template-driven consistency** so every meetup worldwide has identical checkout settings, branding, and QR code delivery.
4. **Community-first event pages** where the Forum topic is the canonical event information page and Pretix handles RSVP and attendee management.
5. **Automated social media promotion** with ready-to-paste copy for 6 platforms.

The system is operated by the Ansible Community Team via CLI scripts. Local organizers interact only through the Discourse forum (to manage event content) and the Pretix dashboard (to view attendees and check in at the door).

---

## 2. System Context

### External Systems

| System | Role | API | Auth |
|---|---|---|---|
| **Pretix** | Event ticketing, RSVP, QR codes, check-in | REST API v1 (`/api/v1/`) | Token-based (`Authorization: Token {token}`) |
| **Discourse** | Identity (SSO), forum, group permissions, event content | REST API (`/posts.json`, `/admin/groups.json`, etc.) | Global API key (`Api-Key` + `Api-Username` headers) |

The Forum/Pretix tools use reusable Requests clients with shared base URLs, headers, and 10-second timeouts. Redirects are disabled so credentials are not forwarded to another URL. Meetup Pro OAuth uses a separate 10-second client; Meetup GraphQL uses a 30-second client. Discourse retries HTTP 429 responses up to three times (four attempts total), honoring `Retry-After` or Discourse wait metadata and otherwise using exponential backoff. Meetup GraphQL waits 60 seconds after HTTP 429 and retries indefinitely until the response is no longer 429. Other non-200 Meetup GraphQL responses are logged and returned as an empty object without retrying.

### Trust Model

- Discourse is the **single source of truth** for identity. Pretix's `NativeAuthBackend` is disabled.
- All user authentication flows through DiscourseConnect (HMAC-SHA256 SSO). Pretix stores the Discourse `external_id` as the identity key.
- API tokens (`PRETIX_API_TOKEN`, `DISCOURSE_API_KEY`) are operator secrets. They are never embedded in URLs, logged in error output, or exposed to end users.
- The Discourse API key has global admin scope. The `Api-Username` header determines which user the action is performed as (impersonation via `run_as`).

### Operator Model

| Actor | Access | How |
|---|---|---|
| **Ansible Community Team** | Full: create events, manage templates, run all scripts | CLI scripts + API tokens |
| **Local Organizer** | Scoped: view attendees + check in for their city only | Discourse SSO → Pretix dashboard (mapped via `meetup-organisers-{city}` group → Pretix Team) |
| **Attendee** | RSVP only: register for events, receive QR code | Discourse SSO → Pretix checkout |

### Configuration: environment variables and constants

The Forum/Pretix tools read these environment variables in `tools/common/ansible_events_lib.py`; the event, provisioning, and attendee scripts import that shared configuration:

| Variable | Required | Default | Used for |
|---|---|---|---|
| `PRETIX_URL` | No | `http://localhost:8000` | Pretix base URL. Non-local URLs must use HTTPS. Production: `https://rsvp.ansible.com`. |
| `PRETIX_API_TOKEN` | Yes | None | Pretix API authentication. |
| `DISCOURSE_API_KEY` | For Forum operations | None | Discourse API authentication. |

`tools/attendees/sync_city_groups` requires only the Forum key; it does not call Pretix. `DISCOURSE_URL=https://forum.ansible.com`, `DISCOURSE_API_USER=system`, the API timeout, and the User-Agent are constants in the shared library, not environment variables.

The Meetup Pro export tools use a separate set of credentials, required only by `tools/meetup_pro/meetup_list_groups` and `tools/meetup_pro/meetup_list_organisers`:

| Variable | Required | Purpose |
|---|---|---|
| `MEETUP_CLIENT_KEY` | Yes | OAuth client key. |
| `MEETUP_SIGNING_KEY_ID` | Yes | Key identifier used in the signed OAuth assertion. |
| `MEETUP_MEMBER_ID` | Yes | Meetup member ID used as the assertion subject. |
| `MEETUP_PRIVATE_KEY` | Yes | Path to the private key file used to sign the OAuth assertion. |

Do not put credentials or private keys in source control, documentation, terminal transcripts, or exported reports.

---

## 3. Data Models

### 3.1 CityInfo

A frozen, slotted dataclass representing a meetup city.

**Fields:**

| Field | Type | Example | Description |
|---|---|---|---|
| `region` | `str` | `"Europe"` | Geographic region |
| `country` | `str` | `"UK"` | Country name or code |
| `slug` | `str` | `"london"` | Explicit lowercase ASCII identifier matching `^[a-z]+$` |
| `city` | `str` | `"London"` | Display name of the city |
| `timezone` | `str` | `"Europe/London"` | IANA timezone identifier |

**Properties:**

| Property | Derivation | Example |
|---|---|---|
| `field_value` | `f"{region}:{country}:{city}"` | `"Europe:UK:London"` |

**Current Registry (immutable tuple):**

| Slug | Region | Country | City | Timezone |
|---|---|---|---|---|
| london | Europe | UK | London | Europe/London |
| barcelona | Europe | Spain | Barcelona | Europe/Madrid |

**Constraints:**
- The registry is an immutable `tuple[CityInfo, ...]`. Slugs and display names must be unique.
- Each slug must match `^[a-z]+$`; each timezone must resolve through Python's IANA `zoneinfo` database.
- CityInfo instances are frozen — no attribute mutation after construction.

### 3.2 API Results and Errors

`pretix_req` and `discourse_req` return `dict[str, Any]` for JSON responses and `{}` for successful empty responses. Network errors, non-success status codes, invalid JSON, and non-object JSON raise `ApiError`; they are never represented as `None` or `False`. The CLI boundary catches `ApiError`, reports a concise failure, and exits non-zero. `check_event_exists` returns a boolean only for confirmed HTTP `200` or `404` responses.

### 3.3 Master Template

A hidden Pretix event (`ansible-meetup-template-v6`) that is never published. All new meetup events are cloned from it via the Pretix API's `clone_from` parameter.

**Template Settings (enforced on every run of day0):**

| Setting | Value | Purpose |
|---|---|---|
| `max_items_per_order` | `1` | One RSVP per person |
| `invoice_address_asked` | `False` | Free events — no billing |
| `attendee_names_asked` | `True` | Collect real name at checkout |
| `attendee_names_required` | `True` | Name is mandatory |
| `attendee_emails_asked` | `False` | Email comes from SSO |
| `name_scheme` | `"full"` | Single name field (not given/family) |
| `order_email_asked_twice` | `False` | No email confirmation step |
| `payment_term_last` | `null` | No payment deadline (free) |

**Template Event Properties:**

| Property | Value |
|---|---|
| Slug | `ansible-meetup-template-v6` |
| Name | `TEMPLATE: Standard Meetup` |
| Live | `False` (never published) |
| Public listing | `False` |
| Timezone | `UTC` |
| Currency | `USD` |
| Plugins | Inherit Pretix's configured default plugins; provisioning does not override the plugin set |
| Default Item | `RSVP` — price `0.00`, `active: True`, `admission: True` |
| Default Quota | `Capacity` — size `100`, linked to RSVP item |

### 3.4 Naming Conventions

| Entity | Pattern | Example |
|---|---|---|
| Discourse organiser group | `meetup-organisers-{slug}` | `meetup-organisers-london` |
| Discourse attendee group | `meetup-attendee-{slug}` | `meetup-attendee-london` |
| Discourse category | City name under parent category | `London` (child of Events, ID 8) |
| Pretix team | `Ansible Meetup Organisers - {City}` | `Ansible Meetup Organisers - London` |
| Pretix staff team | `Ansible Meetup Staff` | `Ansible Meetup Staff` |
| Pretix event slug | `{slug}-{mon}-{yyyy}` | `london-oct-2026` |
| Forum topic title | `Ansible Meetup: {City} - {Month Year}` | `Ansible Meetup: London - October 2026` |

### 3.5 Constants

| Constant | Value | Purpose |
|---|---|---|
| `ORGANIZER_SLUG` | `ansible-meetups` | Pretix organizer path segment |
| `TEMPLATE_SLUG` | `ansible-meetup-template-v6` | Template event identifier |
| `CONTACT_EMAIL` | `ansible-community-events@redhat.com` | Organizer contact email |
| `DISCOURSE_PARENT_CATEGORY_ID` | `8` | Parent category for regional subcategories |
| `STAFF_TEAM_NAME` | `Ansible Meetup Staff` | Pretix event-access team populated only by Pretix admins |

---

## 4. Core Workflows

### 4.1 Environment Reconciliation (`tools.environment.provision_environment`)

**Purpose:** Reconcile Pretix and Discourse resources to desired state. Resources are resolved by stable name, created if absent, and updated when security-relevant settings drift.

**Prerequisites:** Set the API credential for each selected phase: `PRETIX_API_TOKEN` for `--pretix` and `DISCOURSE_API_KEY` for `--forum`. Discourse's `enable_category_group_moderation` setting must be enabled for the Forum phase; provisioning fails before changing Forum resources if it is disabled or cannot be read.

Run it from the repository root after configuring the environment:

```console
uv run python -m tools.environment.provision_environment --pretix --forum
```

Pass `--pretix`, `--forum`, or both to select the reconciliation phases. At least one is required; running without either prints the help text. When both are selected, provisioning completes Pretix setup before reconciling Discourse groups and categories. Each phase checks only its own API credentials, and the Forum phase validates the full meetup-named Discourse group inventory before making changes.

**Phase 1: Pretix Global Settings**

1. Configure organizer settings:
   - `PATCH /api/v1/organizers/ansible-meetups/`
   - Payload: `{"timezone": "UTC", "contact_mail": "ansible-community-events@redhat.com", "settings": {"organizer_team_creation": false}}`

**Phase 2: Pretix Teams and Metadata**

2. Reconcile regional teams with Pretix `require_2fa=false`:
   - Fetch all teams using `pretix_list_all("teams")` (paginated).
   - For each city, create a missing team or reconcile its `all_events`, `all_event_permissions`, `limit_event_permissions`, and `limit_events`. The desired event list is rebuilt from all Pretix events whose slug exactly matches `{city-slug}-{three-letter-month}-{four-digit-year}`; stale and cross-city assignments are removed.
3. Reconcile the Pretix staff team `Ansible Meetup Staff` with access to all events and all event permissions in the meetup organizer, also with `require_2fa=false`. The provisioner never changes its membership; Pretix admins add and remove staff members. No Forum group grants staff-team membership.
4. Ensure `forum_topic_url` meta property exists:
   - `GET /api/v1/organizers/ansible-meetups/event_meta_properties/`
   - If no property named `forum_topic_url` in results:
     - `POST /api/v1/organizers/ansible-meetups/event_meta_properties/`
     - Payload: `{"name": "forum_topic_url", "default": "https://forum.ansible.com/c/events/8", "choices": []}`
**Phase 3: Pretix Template**

5. Create or reconcile template event:
   - Find the exact template slug in the paginated event list.
   - If absent:
     - `POST /api/v1/organizers/ansible-meetups/events/`
     - Payload sets the name, slug, `live=false`, `is_public=false`, `timezone="UTC"`, currency, and start date.
   - On every run, reconcile `live=false`, `is_public=false`, and `timezone="UTC"`.
   - Do not send or verify `is_template`: Pretix's public event API does not expose that field. The private event is used as the clone source by its stable slug through `clone_from`.
   - Reconcile `pretix_passbook_backfield` through `events/{template}/item_meta_properties/`. This is separate from the organizer-level `forum_topic_url` event metadata property.

6. Enforce template settings:
   - `PATCH /api/v1/organizers/ansible-meetups/events/ansible-meetup-template-v6/settings/`
   - Payload: See "Master Template Settings" in Section 3.3.

7. Ensure template has a default item + quota:
   - `GET /api/v1/organizers/ansible-meetups/events/ansible-meetup-template-v6/items/`
   - If no items:
     - `POST .../items/` → `{"name": {"en": "RSVP"}, "default_price": "0.00", "active": true, "admission": true}`
     - `POST .../quotas/` → `{"name": "Capacity", "size": 100, "items": [item_id]}`

**Phase 4: Discourse Groups**

8. Fetch the paginated Discourse group directory, retaining only groups whose name contains `meetup` (case-insensitive). Before any mutations, fail if a name in the `meetup-organisers` namespace does not match `^meetup-organisers-[a-z]+$`.
9. Reconcile organiser group `meetup-organisers-{slug}` by exact name; set group and member-list visibility level 4 (group owners only), disable public admission and membership requests, clear automatic email-domain membership and group owners, and update its description. Forum admins manage membership.
10. Reconcile attendee group `meetup-attendee-{slug}` by exact name; force group and member-list visibility level 3 (staff only).
11. Reconcile the migration tracking group `meetup-migrated-attendees` with staff-only visibility (level 3).
12. Fetch `u/gundalow/invited/pending.json` once as `gundalow`. For each city, reuse a pending invite only when its description is `Join Ansible {city display name}` and its groups include both `meetup-attendee-{slug}` and `meetup-migrated-attendees`. Create missing links with email delivery disabled, both groups, a 5,000-redemption limit, and `expires_at` set to `2030-01-01`. Invalid response data stops invite creation.

**Phase 5: Discourse Subcategories and Access**

13. For each city in the `CITIES` registry, reconcile its regional subcategory by parent and name. Set `everyone` to `create_post` (level 2: view and reply, but no new topics), and grant `full` (level 1) only to that city's organiser group. Do not grant category permissions to attendee groups; they are used for notifications. Set `moderating_group_ids` to that city's organiser group. Then remove registered organiser permissions and moderator assignments from every other category, considering only meetup-named groups. Set each organiser group's default notification level to Tracking for its own subcategory and apply that default to existing group members. Add missing city options to the Discourse user field.

#### Read-only Setup Diagnostics (`tools.environment.check_setup`)

Run `uv run python -m tools.environment.check_setup` to inspect local credentials, Pretix and Forum API access, managed resources, template configuration, and `gundalow`'s Forum identity/group membership. The command performs read requests only, reports `PASS`, `FAIL`, or `MANUAL` per check, and exits non-zero when any check fails.

The Pretix `GET teams` endpoint is permission-gated by `organizer.teams:write`, so a successful request verifies that permission for the configured API token. Required write permissions that cannot be established without mutation are listed by name as `MANUAL`: `organizer.settings.general:write`, `organizer.events:create`, `event.settings.general:write`, and `event.items:write`. Forum write access is also `MANUAL`; the checker never probes write endpoints.

Pretix teams do not require Pretix-managed 2FA. Privileged SSO logins require Forum 2FA through the signed DiscourseConnect assertion, independently of Pretix team settings.

### 4.2 Event Creation (`tools.events.create_event`)

**Purpose:** Provision a complete meetup: Discourse topic + Pretix event + social media copy. City input must be a registered lowercase ASCII slug.

Run it from the repository root. The command below is an example; choose a registered city, local date/time, capacity, and Forum username for the event:

```console
uv run python -m tools.events.create_event --city london --date 2026-10-31T18:00:00 --capacity 100 --organiser FORUM_USERNAME
```

**CLI Arguments:**

| Argument | Required | Type | Validation | Example |
|---|---|---|---|---|
| `--city` | Yes | string | `^[a-z]+$`; must resolve in `CITIES` | `london` |
| `--date` | Yes | string | Event local time, ISO-8601 parsed by `datetime.fromisoformat` | `2026-10-31T18:00:00` |
| `--capacity` | Yes | int | `argparse type=int` enforcement | `100` |
| `--organiser` | Yes | string | Discourse username; must be a member of the registered city's organiser group | `gundalow` |

**Derived Values:**

| Value | Derivation |
|---|---|
| `event_timezone` | Registered `get_city(city).timezone`; unknown city is rejected before API calls |
| `end_dt` | `dt + 3 hours` |
| `start_str` | `dt.strftime("%Y-%m-%dT%H:%M:%S")` (no Z suffix — local time) |
| `end_str` | `end_dt.strftime("%Y-%m-%dT%H:%M:%S")` (no Z suffix — local time) |
| `event_name` | `f"Ansible Meetup {city_info.city}"` |
| `target_slug` | `f"{city_info.slug}-{month_slug}-{year}"` (e.g., `manchester-oct-2026`) |

**Phase 0: Validation and Pre-flight**

- Reject city names outside `^[a-z]+$` and names absent from `CITIES` before API calls.
- Parse local date and validate positive capacity and organiser username before API calls. Verify organiser, exact organiser-group membership, template, Pretix team, and API availability before mutations.
- `check_event_exists` returns `True`/`False` only for confirmed `200`/`404`; other statuses and network failures raise `ApiError`.
- Require HTTPS for `PRETIX_URL` except localhost and loopback development endpoints.

- Check if `target_slug` already exists in Pretix via `check_event_exists(target_slug)`.
- If it exists, **abort** (exit 1) with a clear error. API failures are not interpreted as absence.

**Phase 1: Create Discourse Topic**

- `POST /posts.json`
- Headers: `Api-Username: {organiser}` (impersonation)
- Resolve the exact city subcategory under parent category `8` by name. Abort if missing or ambiguous.
- Payload: `{"title": "Ansible Meetup: {City} - {Month Year}", "raw": {initial_markdown}, "category": {city_category_id}}`
- **MUST abort** (exit 1) if this fails. No Pretix event should be created without a forum topic.
- Extract `post_id`, `topic_slug`, and `topic_id` from response.
- Construct `forum_url = f"{DISCOURSE_URL}/t/{topic_slug}/{topic_id}"`

**Phase 2: Create Pretix Event**

- `POST /api/v1/organizers/ansible-meetups/events/`
- Payload: `{"name": {"en": event_name}, "slug": target_slug, "date_from": date, "date_to": end_date, "timezone": event_timezone, "clone_from": "ansible-meetup-template-v6", "meta_data": {"forum_topic_url": forum_url}}`
- **MUST abort** (exit 1) if this fails.
- If event creation fails after topic creation, attempt to delete the topic. If the result has no ID or cleanup fails, report that the operator must inspect and remove any orphan before retrying.
- Extract `final_slug` from response (may differ from `target_slug` if Pretix appends a suffix).
- Construct `pretix_public_url = f"{PRETIX_URL}/{ORGANIZER_SLUG}/{final_slug}/"`

**Phase 3: Update Discourse Post**

- Replace placeholder URL in event block: `url="https://link-pending.local"` → `url="{forum_url}"`
- Replace RSVP placeholder: `*[RSVP link pending...]*` → `**[Click here to RSVP via Pretix]({pretix_public_url})**`
- Replace the share placeholder with the forum topic URL and set the JSON-LD event URL to the forum topic and its Offer URL to the Pretix event.
- `PUT /posts/{post_id}.json`
- Payload: `{"post": {"raw": final_markdown}}`
- Headers: `Api-Username: {organiser}` (impersonation)
- `ApiError` aborts the workflow; request failures do not become false success values.

**Phase 4: Adjust Quota**

- `GET /api/v1/organizers/ansible-meetups/events/{slug}/quotas/`
- If quota exists (inherited from template): `PATCH .../quotas/{id}/` → `{"size": capacity}`
- If no quota:
  - `GET .../items/` to find existing items
  - If no items: create one (`POST .../items/` → `{"name": {"en": "RSVP"}, "default_price": "0.00", "active": true, "admission": true}`)
  - `POST .../quotas/` → `{"name": "Capacity", "size": capacity, "items": [item_id]}`

**Phase 5: Publish**

- `PATCH /api/v1/organizers/ansible-meetups/events/{slug}/` → `{"live": true}`

**Phase 6: Assign Team**

- Fetch all teams using `pretix_list_all("teams")` (paginated).
- Find team named `Ansible Meetup Organisers - {City}`.
- The provisioner derives each city's complete `limit_events` list from the paginated Pretix event inventory using the exact canonical event-slug pattern. It replaces the current list, removing stale or cross-city event grants.
- Event creation adds its new slug to the matching team's list; the provisioner later recomputes that list from event slugs.
- `PATCH /api/v1/organizers/ansible-meetups/teams/{id}/` → `{"limit_events": [...], "all_event_permissions": false, "limit_event_permissions": ["event.orders:read", "event.orders:checkin"]}`

**Phase 7: Social Media Copy**

- Print to stdout (not file, not API).
- See Section 8 for full specification.

### 4.3 SSO Authentication

Authentication is provided by the separate `meetup-pretix-discourse-auth` plugin. This repository provisions the Forum and Pretix resources used by that plugin; it does not implement or diagnose the SSO flow.

---

## 5. API Integration Contracts

### 5.1 Pretix API

**Base URL Construction:**

```
{PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/{endpoint}
```

Trailing slash rules:
- If URL has no query string: ensure it ends with `/`.
- If URL has a query string: split on first `?`, ensure the base ends with `/`, rejoin.
- Never produce double slashes (except in `://`).

**Authentication:** `Authorization: Token {PRETIX_API_TOKEN}` header on every request.

**Content-Type:** `application/json` on every request.

**Timeout:** 10 seconds on all requests.

**Response Handling:**

| Status | Behavior |
|---|---|
| 200, 201, 204 | Success. Return JSON object, or `{}` for an empty body. |
| Any other | Raise `ApiError` with status and bounded response excerpt. |
| Connection error | Raise `ApiError`; never infer resource absence. |
| Invalid/non-object JSON | Raise `ApiError`. |

**Endpoints Used:**

| Method | Endpoint | Purpose |
|---|---|---|
| `PATCH` | *(empty — targets organizer)* | Update organizer settings |
| `GET` | `event_meta_properties` | List meta properties |
| `POST` | `event_meta_properties` | Create `forum_topic_url` property |
| `GET` | `events/{slug}/item_meta_properties` | List event item metadata properties |
| `POST` | `events/{slug}/item_meta_properties` | Create template wallet-pass back-field property |
| `GET` | `events` | Check existence among events visible to the configured API token |
| `POST` | `events` | Create event (or clone from template) |
| `PATCH` | `events/{slug}` | Update event (publish, set name) |
| `PATCH` | `events/{slug}/settings` | Update template checkout settings |
| `GET` | `events/{slug}/items` | List ticket items |
| `POST` | `events/{slug}/items` | Create ticket item |
| `GET` | `events/{slug}/quotas` | List quotas |
| `POST` | `events/{slug}/quotas` | Create quota |
| `PATCH` | `events/{slug}/quotas/{id}` | Update quota size |
| `GET` | `teams` | List all teams (paginated via `pretix_list_all`) |
| `GET` | `events` | Paginated inventory used to reconcile city team event scope |
| `POST` | `teams` | Create team |
| `PATCH` | `teams/{id}` | Update team permissions/event limits |

### 5.2 Discourse API

**Base URL Construction:**

```
{DISCOURSE_URL.rstrip('/')}/{endpoint}
```

No trailing slash appended (Discourse endpoints include their own suffixes like `.json`).

**Authentication:** `Api-Key: {DISCOURSE_API_KEY}` + `Api-Username: {run_as or DISCOURSE_API_USER}` headers.

**Content-Type:** `application/json`.

**Timeout:** 10 seconds.

**Response Handling:**

Same typed contract as Pretix. Duplicate creation errors are not swallowed; provisioning first resolves resources by name and updates them.

**Endpoints Used:**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `admin/groups.json` | Create Discourse group |
| `POST` | `categories.json` | Create regional subcategory |
| `GET` | `u/gundalow/invited/pending.json` | List pending invites for reconciliation |
| `POST` | `invites.json` | Create city attendee invite link |
| `POST` | `posts.json` | Create forum topic |
| `PUT` | `posts/{id}.json` | Update post content |

**SSO Toolkit Additional Endpoints (urllib):**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/admin/users/{external_id}.json` | Fetch moderation/status data; 2FA is asserted by signed DiscourseConnect response |
| `GET` | `/user-badges/{username}.json` | Fetch user badges |

---

## 6. Security Requirements

### Input Validation

| Input | Rule | Enforcement Point |
|---|---|---|
| `--city` | `^[a-z]+$`, registered in `CITIES` | Reject before API calls or mutations |
| `--date` | Valid ISO-8601 | `datetime.fromisoformat()` — raises `ValueError` |
| `--capacity` | Integer | `argparse type=int` — rejects non-integers |
| `--organiser` | Discourse username | Membership-checked, then used as the Discourse `Api-Username` |

### SSO Security

The separate `meetup-pretix-discourse-auth` plugin owns SSO signature, nonce, rate-limit, and session security.

### Log Sanitization

- API error response bodies truncated to 200 characters: `resp.text[:200]`.
- API tokens are in headers only, never in URLs or log messages.
- Requests exception messages do not include request headers.

### Attack and Misconfiguration Model

- A Pretix lookup returning an error or unknown status is never treated as proof that an event does not exist; the operation stops with `ApiError`.
- A city slug must match `^[a-z]+$`, be registered in `CITIES`, and equal its Pretix team display-name suffix normalized with Unicode NFKD, retaining only ASCII letters and lowercasing (`New York` → `newyork`, `São Paulo` → `saopaulo`). Update and deploy this tooling registry before provisioning or event creation. The auth plugin is city agnostic and resolves existing city teams dynamically; adding a city requires no edits or release in `pretix-discourse-auth`.
- The auth plugin accepts only exact `^meetup-organisers-([a-z]+)$` Forum group claims for city access. Staff privileges come only from Pretix's `Ansible Meetup Staff` team or Pretix-managed `is_staff`; Forum claims cannot grant them. Organizer, staff-team, and Pretix staff accounts require a signed `confirmed_2fa=true` assertion. Every claimed organiser group must resolve to a unique Pretix team or that organizer login is denied; missing teams, duplicate teams, and normalization collisions fail closed.
- The auth callback limits requests to 10 weighted attempts per client IP per 60 seconds; signature and nonce failures count twice. Rate-limit state uses the shared Pretix cache and fails closed if the cache is unavailable.
- Discourse groups are reconciled by name on every provisioning run. Organiser groups are hidden (level 4), have staff-only member lists (level 3), and are managed by Forum admins; attendee groups and their member lists are staff-only (level 3). Organiser group permissions and moderator assignments are removed from every category except that group's own city subcategory. City Pretix teams are reconciled to the exact canonical event slug pattern; the Pretix-only staff team retains access to all events and is never populated by Forum claims. Provisioning errors are fatal.
- Non-local `PRETIX_URL` values must use HTTPS so API tokens are not sent over cleartext HTTP.
- Pretix session expiry is controlled by Pretix core, not its organizer API. The auth plugin disables “keep me logged in” and sets a browser-session cookie; Pretix core enforces its configured relative idle timeout (three hours in this deployment) and 12-hour absolute limit. Changing the absolute limit requires a Pretix server override, so `provision_environment.py` does not attempt to set an unsupported API field.

### Known Accepted Risks

1. **`run_as` scope:** `create_event.py --organiser` impersonates the selected Discourse user when posting. Membership is validated first; API key scope remains important.

---

## 7. Forum Post Template

The forum post created by `create_event.py` has two distinct zones separated by a horizontal rule (`---`):

**Zone 1: Event Widget**

```markdown
[event start="{start_str}" end="{end_str}" timezone="{event_timezone}" minimal="true" name="{event_name}" url="https://link-pending.local"]
[/event]
```

- `minimal="true"`: Shows compact event widget without Interested/Attending buttons.
- No `status="public"`: Prevents RSVP buttons (RSVP is handled by Pretix).
- `url` is initially a placeholder; replaced with the forum topic URL in Phase 3.

**Zone 2: Forum Event Content**

```markdown
## Welcome to Ansible Meetup {City}!

Join us for an evening of automation, collaboration, and community! ...

### What to Expect
- **Engaging Talks**: ...
- **Networking**: ...
- **Q&A**: ...
- **Community**: ...

### Location
**Venue details will be announced soon!** ...

### Agenda
* *Speaker 1: TBD*
* *Speaker 2: TBD*
*(Want to give a talk? Reply below with your proposal!)*

### RSVP
**[Click here to RSVP via Pretix]({pretix_public_url})**
**Please note:** To help us manage venue capacity ...

### Connect
Have questions? Want to propose a talk? ...
```

**Placeholder Replacements (Phase 3):**

| Placeholder | Replacement |
|---|---|
| `url="https://link-pending.local"` | `url="{forum_url}"` |
| RSVP and share placeholders | Link to the Pretix event and forum topic, respectively |

The forum post remains the event content source. Pretix stores `forum_topic_url` as a backlink and does not receive a copy of the forum content.

---

## 8. Social Media Copy Specification

Generated after successful event provisioning. Printed to stdout for manual copy-paste.

| Platform | Char Limit | Hashtags | Link Target | Fallback |
|---|---|---|---|---|
| **X / Twitter** | 280 | `#Ansible #Meetup #OpenSource` | Forum URL | Shorter text if over limit |
| **Bluesky** | 300 | `#Ansible #DevOps #Automation` | Forum URL | Shorter text if over limit |
| **Mastodon** | 500 | `#Ansible #Meetup #DevOps #Automation #OpenSource #InfrastructureAsCode` | Forum URL | None (always fits) |
| **LinkedIn** | None | `#Ansible #DevOps #Automation #InfrastructureAsCode #CommunityMeetup` | Forum URL | None |
| **Reddit** | None | None (markdown) | Forum URL | None |
| **Hacker News** | None | None | Forum URL | Title only, link on separate line |

All platforms link to the **forum URL**, not the Pretix URL. The forum is the community hub.

X and Bluesky include a fallback mechanism: if the primary text exceeds the character limit, a shorter version is used. Character count is printed after each payload.

---

## 9. Non-Functional Requirements

### HTTP

- **Timeout:** 10 seconds on all Pretix/Discourse API calls and urllib calls. Meetup Pro OAuth uses 10 seconds; GraphQL uses 30 seconds.
- **Rate-limit retries:** Discourse requests allow at most three retries after the initial request (four attempts total) for HTTP 429, using `Retry-After`, Discourse wait metadata, or exponential backoff. Meetup GraphQL requests wait 60 seconds and retry indefinitely while HTTP 429 continues. Pretix and Discourse wrapper errors stop the CLI; Meetup GraphQL logs other non-200 responses and returns an empty object without retrying.
- **Connection pooling:** Reusable `requests.Session` clients pool connections across API requests.

### Logging

- Python `logging` module, logger name `ansible_meetups`.
- Level: `INFO` by default.
- Format: `%(asctime)s - %(levelname)s - %(message)s`.
- Error responses: log at `ERROR` with status code + truncated body (200 chars max).
- Failures where script can continue: log at `WARNING`.

### Type Safety

- `from __future__ import annotations` in all files.
- Full type annotations on all function signatures (parameters + return types, including `-> None`).
- API wrappers return JSON objects and raise `ApiError` on failure; create/read operations require a JSON object response.
- Pyright with `typeCheckingMode = "standard"` (must pass with zero errors).
- Frozen slotted dataclasses for data models.

### Code Quality

- **Formatter:** `ruff format` (line-length 120).
- **Linter:** `ruff check` with rules `E`, `F`, `B`, `S`, `T20`, `DTZ`, `UP`, `SIM`, and `G`.
- **Per-file ignores:** test assertions (`S101`); event social-copy output and long lines (`T201`, `E501`); the Meetup Pro credential example (`S105`); and long organiser export output (`E501`).
- **Import ordering:** CI does not run a separate isort check.

### Testing

- **Framework:** pytest with `testpaths = ["tests"]`.
- **Organization:** Class-based (`Test<Feature>`), methods named `test_<verb>_<condition>`.
- **Coverage areas (66 test methods):**
  - `CityInfo.slug`: lowercase, spaces→hyphens, multiple spaces, empty, leading/trailing, tabs, unicode.
  - `CityInfo.field_value`: standard, multi-word, case preservation.
  - `CityInfo` frozen: immutability enforcement.
  - `get_city`: exact match, case-insensitive, not-found, partial match rejection, empty string, leading/trailing spaces.
  - `CITIES` registry: all CityInfo instances, no duplicates, valid timezones, tuple immutability.
  - Pretix URL building: trailing slashes, query strings, double slashes, empty endpoint.
  - Discourse URL building: slash stripping, nested paths.
  - `pre_flight_checks`: both vars set, missing discourse key, `require_discourse=False`.

### Dependencies

- **Runtime:** `requests>=2.32` and `PyJWT[crypto]>=2.10` (used by the temporary Meetup Pro OAuth exporters).
- **Development group:** `pyright>=1.1`, `pytest>=8`, `ruff>=0.11`, and `types-requests>=2.32`.
- **Documentation group:** `mkdocs>=1.6` and `mkdocs-ansible>=0.1`.
- **Package manager and lock:** uv with `uv.lock`; `tool.uv.package = false`, so this tools-and-docs repository is not built as an installable Python package.
- **Python:** `>=3.13`.
- **CLI layout:** Active tools are Python modules under `tools/common/`, `tools/events/`, `tools/environment/`, `tools/attendees/`, and `tools/meetup_pro/`. The existing `tools/cfgmgmtcamp/` utility is separate from the Meetup tool workflows.
- **Docstrings:** Python functions and methods should use Google-style docstrings where appropriate; CI does not run a docstring-specific checker.
- **Discourse theme component:** Event JSON-LD source and metadata are maintained in this repository at `discourse-theme/event-jsonld/`.

### Continuous integration

GitHub Actions uses `astral-sh/setup-uv@v5` to select Python 3.13, then runs `uv sync --locked --all-groups`. On pull requests and pushes to `main` or `master`, it runs `pytest`, Ruff lint and format checks on the Meetup tool modules and tests, Pyright on `tools/common/ansible_events_lib.py` and `tools/environment/provision_environment.py`, and `mkdocs build --strict`. CI does not build a Python wheel and does not include `tools/cfgmgmtcamp/` in its Python checks.

---

## 10. Checkout Experience Configuration

The Pretix checkout flow for authenticated attendees is:

1. User clicks RSVP link → Pretix redirects to Discourse SSO.
2. User authenticates on Discourse → redirect back to Pretix with signed payload.
3. SSO plugin pre-fills email from payload. Name pre-filled if available.
4. Checkout page shows: event name, single "Name" field (pre-filled, editable), RSVP button.
5. No email confirmation step, no payment step, no invoice address, no copy-answers button.
6. User submits → receives confirmation email with QR code and ICS calendar attachment.

**Name Behavior:**
- Pre-populated from Discourse SSO `name` field during login.
- User CAN edit their name during Pretix checkout.
- Edits are stored ONLY in Pretix. The Discourse profile is NEVER modified.
- Uses `name_scheme: "full"` — single text field, not given/family split.

**The checkout settings are enforced on the template and inherited by cloned events; see the master template table in Section 3.3. The event creation workflow also adjusts the event quota to the requested capacity.**

---

## 11. Implicit Assumptions & Shortcuts

### Retry boundaries

Pretix requests and non-429 Forum/Meetup failures are not retried. Forum API requests retry HTTP 429 at most three times after the initial attempt; if rate limiting persists, the command fails. Meetup GraphQL waits 60 seconds and retries HTTP 429 indefinitely; other non-200 responses are logged and produce an empty object. There is no general retry queue or circuit breaker.

### Recovery after Partial Failure

`create_event.py` validates configuration and remote prerequisites before mutation. If Pretix event creation fails after the Discourse topic was created, it attempts to delete that topic. If cleanup fails, an operator must remove the orphan before retrying. Later API failures can still leave a partially configured event and must be resolved before announcing it.

The script aborts on API errors. Review the event and forum topic before announcing it; later mutations can leave partially configured resources that require operator repair.

### Partial Pagination

The `teams` list endpoint is paginated via `pretix_list_all`. Other list endpoints (`items`, `quotas`, `event_meta_properties`) still assume results fit in a single page (<50 results). At scale, these may need migration to `pretix_list_all`.

### Template Must Exist Before Event Creation

`create_event.py` uses `clone_from: ansible-meetup-template-v6`. It checks that the template exists before mutation. Run `provision_environment.py` to create or reconcile it.

### Hardcoded Cities Registry

The `CITIES` tuple is defined in source code. Adding a new city requires a code change and deployment in this repo, followed by provisioning of its Forum group and Pretix team. The auth plugin resolves city teams dynamically and requires no city-specific code change or release. There is no database, config file, or API for dynamic city management.

### Social Media Output

Social media copy is printed to stdout. There is no file output, clipboard integration, or API posting. The operator manually copies and pastes into each platform.

### Event Duration Fixed at 3 Hours

`create_event.py` hardcodes `end_dt = dt + timedelta(hours=3)`. There is no CLI argument for event duration.

### Currency

All events use `"currency": "USD"` (inherited from the template). No per-city currency configuration exists. Since all events are free, this only affects display on confirmation emails.

---

## 12. Open Questions & Clarifications

### Q1: Partial Failure Compensation

The script attempts compensating cleanup if Pretix event creation fails. If the cleanup API call also fails, delete the topic manually before retrying. Unknown Pretix event state is fatal and never treated as absence.

### Q2: Scale & Pagination

**How many cities will this system support at maturity?** The current implementation performs sequential reconciliation. See “Partial Pagination” above for list-endpoint limits to consider as the city count grows.

### Q3: Cities Registry Storage

Who adds new cities? Should the registry be:
- **Hardcoded** (current) — requires code deployment for each new city.
- **Config file** (YAML/JSON) — editable without code changes.
- **Discourse-driven** — auto-discover cities from existing `meetup-organisers-*` groups.
- **Database** — for API-managed CRUD.

### Q5: Event Duration

Event duration is hardcoded at 3 hours. **Should the rebuild accept a `--duration` CLI argument?** Most meetups are 2-3 hours, but unconferences or all-day workshops may need longer.

### Q6: Pretix staff team

The provisioner creates `Ansible Meetup Staff` with access to all meetup events. Only Pretix admins manage its membership. The Forum contains no `meetup-admin` or `meetup-staff` groups, and the auth plugin never maps Forum groups to this team.

### Q7: Pretix API Rate Limits

What are the Pretix instance's API rate limits? `provision_environment.py` makes multiple API calls per city during reconciliation. At 50 cities, that's hundreds of sequential requests. **Do we need request throttling or backoff?** What about the Discourse API rate limits?


## Canonical documentation

This specification is maintained in the Ansible Meetup documentation repository. The Forum event topic is the canonical event information page. It links to Pretix for RSVP, and Pretix stores a backlink to the Forum topic; event details do not synchronize between the systems.
