# Pretix–Discourse authentication specification

**Status:** Maintained technical specification
**Audience:** Maintainers of the standalone Pretix authentication plugin and Meetup platform  

---

## 1. Terminology

These terms are used consistently throughout this document.

| Term | Definition |
|------|-----------|
| **Consumer** | The application that delegates authentication to an external identity provider. In this system, **pretix** (via this plugin) is the consumer. Sometimes called "client" or "relying party." |
| **Provider** | The application that authenticates users and asserts their identity. In this system, **Discourse** (`forum.ansible.com`) is the provider. Sometimes called "identity provider" or "IdP." |
| **DiscourseConnect** | The SSO protocol used between consumer and provider. Formerly called "Discourse SSO." Uses HMAC-SHA256 signed payloads exchanged via browser redirects. |
| **SSO payload** | The base64-encoded, HMAC-signed query string exchanged between consumer and provider. Contains identity fields (`external_id`, `email`, `groups`, etc.). |
| **Privileged user** | A user with an exact `meetup-organisers-[a-z]+` claim, membership in a city organiser team, membership in the Pretix team `Ansible Meetup Staff`, or Pretix-owned `is_staff=true`. DiscourseConnect must attest that the required 2FA challenge succeeded before Pretix creates the session. |
| **Enrichment** | A server-to-server call from pretix to Discourse's Admin API to retrieve security metadata (silenced, suspended status) not available in the SSO payload. |
| **RTBF** | Right To Be Forgotten. Refers to a Discourse user whose account has been anonymized. Discourse replaces the email with `{username}@anonymized.invalid`, changes the username to `anon{digits}`, and destroys all auth records. |
| **Pretix staff** | A Pretix account whose `is_staff` permission is granted by Pretix administrator configuration. The plugin never reads a Forum staff group or changes this flag. |
| **Organiser group** | A Discourse group whose name fully matches `^meetup-organisers-([a-z]+)$`. Only this exact shape grants city-scoped team access. |
| **Managed team** | A Pretix Team named `Ansible Meetup Organisers - {City}`. The tooling provisioner creates and reconciles teams; the auth plugin only manages user membership. |
| **Staff team** | The Pretix-only team `Ansible Meetup Staff`. The provisioner creates it with access to all meetup events; Pretix admins alone manage its members. No Forum group maps to it. |
| **Fail secure** | When a security check cannot be completed (API error, missing config, ambiguous state), deny access rather than allow it. This is the default posture for all decisions in this system. |

### Design principle: fail secure

This system prioritizes security over availability. When in doubt:

- Missing or invalid configuration **blocks the auth backend from appearing** (not a silent degradation).
- API errors during enrichment **block login** (not a silent pass-through).
- Unknown state (e.g., 2FA status unverifiable) is treated as **failing the check**.
- It is acceptable to block a legitimate user who must then retry or contact an admin. It is **not acceptable** to allow access due to misconfiguration, transient errors, or ambiguous state.

---

## 2. Executive Summary

### What it does

A pretix plugin that replaces pretix's built-in username/password login for the **pretix control panel** (the admin/organizer interface) with Single Sign-On via a Discourse forum — specifically `forum.ansible.com`.

When an operator clicks "Log in with Discourse," they are redirected to Discourse, authenticate there, and are redirected back. The plugin then:

1. Verifies the cryptographic SSO payload.
2. Provisions or updates a pretix user account.
3. Requires DiscourseConnect's signed `confirmed_2fa=true` assertion for privileged users and checks moderation status through the Discourse Admin API.
4. Syncs only exact organiser-group claims (e.g., `meetup-organisers-berlin`) to Pretix team assignments (e.g., `Ansible Meetup Organisers - Berlin`).

### Core value proposition

Any valid Forum user can sign in to Pretix as an attendee. Only users with an exact city organiser group claim receive membership in the matching Pretix team and its event permissions. Pretix staff access remains controlled by Pretix administrators.

### Trust model

Discourse is the **provider** and **source of truth** for:
- User identity (email, username, display name)
- Group memberships (which cities an organiser manages)
- Moderation status (silenced, suspended)
- 2FA challenge completion (via DiscourseConnect's signed `confirmed_2fa` assertion)

Pretix is the **consumer**. It accepts any valid Forum identity as an attendee, uses exact organiser claims only for city-team membership, and uses the Admin API for moderation status. Pretix staff access is granted only by Pretix administrators; the plugin does not use Forum groups to grant or revoke `is_staff`.

---

## 3. Core Workflows

### 3.1 Login Initiation (pretix → Discourse)

**Trigger:** User clicks the "Log in with Discourse" button on the pretix control panel login page.

**Steps:**

1. The plugin's auth backend generates a cryptographically random nonce (32 bytes, URL-safe base64).
2. The nonce and a timestamp (`time.time()`) are stored in the Django session under keys `discourse_sso_nonce` and `discourse_sso_nonce_created`.
3. A payload string is constructed: `nonce=<nonce>&return_sso_url=<callback_url>&require_2fa=true`.
4. The payload is base64-encoded.
5. An HMAC-SHA256 signature is computed over the base64 payload using the shared SSO secret.
6. The user's browser is redirected to `{DISCOURSE_URL}/session/sso_provider?sso={payload_b64}&sig={sig}`.

**`require_2fa=true`:** Always sent and is not configurable. For organiser claims and members of the Pretix staff team, Pretix requires the signed callback field `confirmed_2fa=true`. Missing or false is a fatal login rejection. DiscourseConnect is the sole authority for whether the challenge was completed; the Admin API is not used to infer 2FA from account configuration.

**Callback URL format:** `https://{pretix_host}/_discourse/login/return/` (resolved via Django's `reverse()` using the named URL `plugins:pretix_discourse_auth:return`).

### 3.2 SSO Callback (Discourse → pretix)

**Trigger:** Discourse redirects the user's browser back to pretix's callback URL with `?sso=...&sig=...` query parameters.

**Steps (executed sequentially — each failure redirects to the login page with an error message):**

All rejection scenarios are consolidated in the [Rejection Matrix](#34-rejection-matrix) below.

#### Step 1: Parameter validation
- Verify both `sso` and `sig` GET parameters are present.

#### Step 2: Signature verification
- Compute HMAC-SHA256 over the **raw** `sso` parameter value using the shared secret. **Do not strip whitespace** — the value may contain a trailing newline that is part of the signed content (see [Appendix A](#appendix-a-discourseconnect-protocol-reference)).
- Compare against the provided `sig` using constant-time comparison (`hmac.compare_digest`).

#### Step 3: Payload decoding
- Base64-decode the `sso` parameter.
- Parse as a URL query string into key-value pairs.
- If the payload contains `failed=true`, reject (user cancelled or Discourse denied).

#### Step 4: Nonce verification (replay protection)
- Pop `discourse_sso_nonce` and `discourse_sso_nonce_created` from the session, then atomically claim a shared cache key for the nonce; a second or concurrent callback is rejected.
- Compare the payload's `nonce` against the saved nonce using constant-time comparison.
- Verify the nonce timestamp is numeric, finite, not in the future, and less than **10 minutes** old. Reject malformed or stale data.

#### Step 5: Identity extraction
Extract from the strictly base64-decoded and query-parsed payload. Duplicate parameters, invalid UTF-8, non-string claims, malformed email/username/ID fields, and invalid group claim shapes fail before any API or database writes.

| Payload field    | Required | Processing                        | Maps to               |
|------------------|----------|-----------------------------------|-----------------------|
| `external_id`    | Yes      | Used as-is (Discourse `user.id`)  | Auth backend identifier |
| `email`          | Yes      | Lowercased                        | User email            |
| `username`       | No       | Lowercased                        | RTBF heuristic input  |
| `name`           | No       | Falls back to `username` if empty | User fullname         |
| `groups`         | No       | Comma-separated string            | Exact organiser group claims only |
| `confirmed_2fa` | Required for privileged users | `"true"` only after the DiscourseConnect challenge succeeds | Positive 2FA assertion |

The Discourse `admin` flag and all Forum staff groups are ignored. Pretix administrators own `is_staff`.

If `external_id` or `email` is missing/empty, reject.

#### Step 6: Group parsing
- Ignore all group claims except names fully matching `^meetup-organisers-([a-z]+)$`; malformed names using the organiser prefix reject the callback.
- The city slug must contain lowercase ASCII letters only; hyphens, spaces, and numbers are not accepted.
- Resolve the slug through the explicit `CITY_TEAM_NAME_BY_SLUG` mapping and require exactly one team with that canonical display name; do not infer names with title casing or normalization.
- A user is privileged when they have a valid exact city claim, already belong to a city organiser team or `Ansible Meetup Staff`, or already have Pretix-owned `is_staff=true`. The Forum cannot grant staff-team membership or alter the Pretix staff flag.

#### Step 7: Positive 2FA assertion

For every organizer claim, existing city organiser-team member, Pretix staff-team member, or Pretix `is_staff` user, require `confirmed_2fa=true` from the HMAC-verified DiscourseConnect response. Reject when the field is missing or not exactly `"true"`. Do not use `no_2fa_methods`, Pretix team configuration, or Admin API account configuration as substitutes for proof that the current authentication passed the challenge.

#### Step 8: RTBF detection

**Constant:** `RTBF_EMAIL_SUFFIX = "@anonymized.invalid"`

A user is flagged as RTBF if their email ends with `@anonymized.invalid`. This is the email suffix Discourse assigns during anonymization (verified in source: `UserAnonymizer::EMAIL_SUFFIX = "@anonymized.invalid"`).

Username and display name heuristics are **not used** — they produce false positives for legitimate usernames. The email domain is sufficient: Discourse destroys all auth records during anonymization, so an anonymized user cannot reach this point in practice. This check is defense-in-depth.

#### Step 9: Security enrichment (Discourse Admin API)

**Precondition:** `API_KEY` must be configured. If not configured, the auth backend refuses to register at startup (see [Section 5.1 Config Validation](#51-configuration-validation)).

- Call `GET {DISCOURSE_URL}/admin/users/{external_id}.json` with headers `Api-Key` and `Api-Username`.
- Timeout: 10 seconds by default (`api_timeout`, valid range 1–60).
- Use a configured `requests.Session` client that stores the Discourse base URL, API headers, and timeout together. Disable redirects so the API key cannot be forwarded to another URL.
- Set the User-Agent to `Ansible-pretix-discourse-auth/0.1.0 (+https://github.com/ansible-community/meetup-pretix-discourse-auth)` on every outbound API request.
- Parse response JSON once, store in a local variable. The Discourse Admin API returns the user object directly (`root: false`), so `api_data = raw_data` — no `raw_data.get('user', raw_data)` wrapper needed.

**On HTTP 200, validate identity and extract moderation status:** The response must contain the requested `id` and a non-empty `username`. `silenced_till` and `suspended_till` are optional; each must be a string or `null` when present. Missing moderation fields mean the user is not in that state, as Discourse omits them for ordinary users. An empty object, mismatched identity, or invalid field type is an API response failure and blocks login.

| API field | Type | Interpretation |
|-----------|------|----------------|
| `silenced_till` | datetime or absent | **Present only when user is silenced.** If the key exists and is non-null, the user is silenced. If absent, the user is not silenced. |
| `suspended_till` | datetime or absent | **Present only when user is suspended.** If the key exists and is non-null, the user is suspended. Note: suspended users cannot complete SSO (Discourse blocks login), so this is defense-in-depth. |

**Critical implementation note:** The Discourse Admin API does **not** return boolean `silenced` or `suspended` fields. It returns `silenced_till` and `suspended_till` as datetime values only when the user is silenced/suspended. Validate the response identity and field types first, then check the presence and non-null value of these keys:

```
is_silenced = bool(api_data.get('silenced_till'))
is_suspended = bool(api_data.get('suspended_till'))
```

**On any error (network, timeout, non-200, invalid JSON):** Fail secure — reject login with "Could not verify security status with Discourse." All API errors are treated identically: the enrichment check cannot be completed, so access is denied. There is no distinction between network errors and HTTP errors. See [Rejection Matrix R9](#34-rejection-matrix).

#### Step 10: Policy enforcement

Evaluated in order; first match blocks login:

| Condition | Error message |
|-----------|---------------|
| User is silenced (from enrichment) | "Account blocked: Moderation (silenced)." |
| User is suspended (from enrichment, defense-in-depth) | "Account blocked: Moderation (suspended)." |
| User is flagged RTBF (from Step 8) | "Account blocked: Anonymized account." |

2FA has already been decided from the signed DiscourseConnect assertion in Step 7. The Admin API is used only for moderation status.

#### Step 11: User provisioning

Before creating or updating a pretix user, resolve every claimed organiser group to exactly one Pretix team under the configured organizer. If the organizer configuration is missing/invalid or a claimed team is missing/ambiguous, reject that organiser login. Do not silently skip a city or grant partial organiser access. A valid attendee with no organiser claims may still log in.

- Call pretix's `User.objects.get_or_create_for_backend('discourse', external_id, email, set_always={'fullname': name}, set_on_creation={})`.
  - The method matches on `('discourse', external_id)`, not email.
  - On every login: updates `fullname` and **email** (the email update is hardcoded in pretix's `get_or_create_for_backend` — it always sets `email` via `set_always`).
  - On first creation: no additional fields set.
- **On `EmailAddressTakenError`:** Reject with "Email conflict: Another user with this email exists on a different auth backend." This is raised when the user's Discourse email matches an existing pretix user linked to a different auth backend. The email update cannot be skipped — it is hardcoded in pretix's `get_or_create_for_backend`. Admin intervention is required to resolve the conflict.

#### Step 12: Pretix staff permission ownership

The plugin never reads a Forum staff group and never writes `User.is_staff`. Pretix administrators grant and revoke site-wide staff access through Pretix configuration. Discourse group claims cannot grant or remove this permission.


#### Step 13: Team sync (within a database transaction)

All team membership changes happen inside `transaction.atomic()`:

**Important: Team is scoped per-organizer.** Pretix's `Team` model has a ForeignKey to `Organizer`. Team names are **not globally unique** — two organizers can have identically-named teams. All team queries **must** be scoped to the configured `ORGANIZER` (see [Section 4.4 Configuration](#44-configuration)):

```
Team.objects.filter(organizer=ORGANIZER, name__in=expected_team_names)
```

**Add to teams:**
- For each regex-captured city slug, resolve the exact canonical team name from `CITY_TEAM_NAME_BY_SLUG` and require exactly one team with that name.
- Reject the organizer login before user provisioning if the organizer setting is missing/invalid or any group has no unique Pretix team.
- Query pretix for teams matching those exact names **within the configured organizer**.
- Add the user to each found team (idempotent — `team.members` is a simple M2M; `add()` is safe to call repeatedly).
- A missing claimed team rejects login before user provisioning; no partial city access is granted.

**Remove from stale teams:**
- Managed teams use the fixed name prefix `Ansible Meetup Organisers - `; membership in matching city teams is reconciled on login.
  - Example: `"Ansible Meetup Organisers - {city}"` → prefix `"Ansible Meetup Organisers -"`
- Find all teams the user belongs to **within the configured organizer** whose name starts with that prefix.
- Remove the user from any of those teams that are NOT in the expected set.

**Result:** On each login, the user's pretix team membership is made consistent with their current Discourse group membership, scoped to managed teams within the configured organizer.

#### Step 14: Login

- Call pretix's `process_login(request, user, keep_logged_in=False)`.
- The session cookie is browser-scoped (expires on browser close). Pretix enforces its configured relative idle timeout and absolute session limit independently.
- Post-login redirect: `process_login` calls `backend.get_next_url(request)` which uses `request.GET.get("next")`. Pretix validates this against `url_has_allowed_host_and_scheme(next_url, allowed_hosts=None)`, which restricts to the current host — **no open redirect risk** (verified in pretix source).

### 3.3 Backend Visibility

The "Log in with Discourse" button appears on pretix's login page **only if** all of the following are true:
- `DISCOURSE_URL` is configured and uses HTTPS, or HTTP for localhost/loopback development.
- `DISCOURSE_SECRET` is configured (non-empty) and at least 32 characters.
- `API_KEY` is configured (non-empty).

If any condition is not met, the backend is invisible — pretix falls through to its other configured auth backends. This is the fail-secure posture: misconfiguration results in the plugin being **disabled**, not silently degraded.

### 3.4 Rejection Matrix

Every rejection scenario in the callback flow, consolidated in one table. Authentication and policy rejections redirect to the login page with the specified user-facing message. Rate-limit responses use HTTP 429, and rate-limiter service failures use HTTP 503. Log fields never include secrets, nonces, or full SSO payloads.

| ID | Step | Condition | User message | Log level | Log fields |
|----|------|-----------|-------------|-----------|------------|
| R1 | 1 | Missing `sso` or `sig` parameter | "Invalid response from Discourse." | WARNING | Client IP |
| R2 | 2 | HMAC signature mismatch | "Signature mismatch. Authentication failed." | WARNING | Client IP, truncated `sig` |
| R3 | 3 | Invalid base64 or UTF-8 in payload | "Could not decode Discourse response." | WARNING | Client IP |
| R4 | 3 | Payload contains `failed=true` | "Discourse authentication failed or was cancelled." | INFO | Client IP |
| R5a | 4 | Nonce missing from session (session expired or new browser) | "Session expired or invalid nonce. Please try again." | WARNING | Client IP, cause: "missing" |
| R5b | 4 | Nonce mismatch (possible replay or tampering) | "Session expired or invalid nonce. Please try again." | WARNING | Client IP, cause: "mismatch" |
| R5c | 4 | Nonce expired (age > 10 min) | "Session expired or invalid nonce. Please try again." | WARNING | Client IP, nonce age in seconds, max age |
| R6 | 5 | Missing `external_id` or `email` | "Incomplete identity data received." | WARNING | Client IP |
| R7 | 7 | Privileged user without signed `confirmed_2fa=true` | "Discourse did not confirm two-factor authentication." | WARNING | `external_id` |
| R8 | 8 | Email ends with `@anonymized.invalid` | "Account blocked: Anonymized account detected." | WARNING | `external_id` |
| R9 | 9 | Enrichment API error (network, timeout, non-200, invalid JSON, malformed identity/field data) | "Could not verify security status with Discourse. Please try again later." | ERROR | Exception type, URL (no API key), HTTP status if available |
| R10 | 10 | User is silenced (`silenced_till` present and non-null) | "Account blocked: Moderation (silenced)." | WARNING | `external_id` |
| R11 | 10 | User is suspended (`suspended_till` present and non-null) | "Account blocked: Moderation (suspended)." | WARNING | `external_id` |
| R12 | 11 | Claimed organiser group has no matching team | "Could not verify organiser access with Pretix. Please contact an administrator." | ERROR | Missing team names, organizer slug |
| R13 | 11 | `EmailAddressTakenError` during user provisioning | "Email conflict: Another user with this email exists. Please contact an administrator." | WARNING | `external_id`, email |
| R14 | 9 | API returns 401/403 (bad/revoked API key) | Same as R9 | **ERROR** | Additionally: "API key may be invalid or revoked" |
| R15 | 1 | More than 10 weighted callback attempts from one client IP in 60 seconds | HTTP 429: "Too many login attempts. Please try again later." | WARNING | No IP or authentication payload data |
| R16 | 1 | Shared cache rate limiter unavailable | HTTP 503: "Login is temporarily unavailable." | ERROR | Exception type |

**Design principle:** Every rejection is logged. Every API/config error fails secure (denies access). There is no "silently continue with defaults" path — if a security check cannot be completed, access is denied.

---

## 4. Technical Architecture

### 4.1 System context

```
                                         ┌──────────────────────┐
                                         │  Discourse           │
                                         │  (forum.ansible.com) │
                                         │                      │
                                    SSO  │  /session/sso_provider│
    ┌────────────┐   redirect      ◄─────┤                      │
    │            │──────────────────►     │  /admin/users/:id    │
    │  Browser   │                       │  (Admin API)         │
    │            │◄──────────────────►    └──────────────────────┘
    └────────────┘   redirect            
         │                               
         │ HTTPS                         
         ▼                               
    ┌────────────────────────────────┐   
    │  Pretix                        │   
    │  ┌──────────────────────────┐  │   
    │  │ pretix-discourse-auth    │  │   
    │  │  - DiscourseAuthBackend  │  │   
    │  │  - return_view           │  │   
    │  └──────────────────────────┘  │   
    │  ┌──────────────────────────┐  │   
    │  │ Django ORM               │  │   
    │  │  - User                  │  │   
    │  │  - Team                  │  │   
    │  │  - Session               │  │   
    │  └──────────────────────────┘  │   
    └────────────────────────────────┘   
```

### 4.2 Tech stack

| Component           | Technology                     | Notes                                                    |
|---------------------|--------------------------------|----------------------------------------------------------|
| Runtime             | Python 3.9+                    | Match pretix's supported Python versions                 |
| Web framework       | Django (via pretix)            | Plugin does not choose the Django version; pretix does    |
| HTTP client         | `requests`                     | For Discourse Admin API calls                            |
| Cryptography        | Python stdlib `hmac`, `hashlib`, `secrets`, `base64` | No third-party crypto dependencies |
| Plugin framework    | pretix plugin system           | `BaseAuthBackend`, `pretix.cfg` config, entry points     |
| Build system        | setuptools + `pretix-plugin-build` | Via `pyproject.toml`                                 |

### 4.3 Plugin structure

```
pretix_discourse_auth/
    __init__.py          # Version, default_app_config
    apps.py              # Django AppConfig + PretixPluginMeta
    backend.py           # DiscourseAuthBackend (login initiation)
    views.py             # return_view (SSO callback + all business logic)
    urls.py              # Single route: _discourse/login/return/
    signals.py           # Empty (placeholder for future signal receivers)
    locale/              # i18n translation files (de, de_Informal)
    static/              # Empty (placeholder)
    templates/           # Empty (placeholder)
```

### 4.4 Configuration

All configuration is read from pretix's `pretix.cfg` file (INI format) under the `[discourse_auth]` section. Values are loaded once at module import time. Config changes require a process restart.

| Key                      | Required | Default              | Description                                      |
|--------------------------|----------|----------------------|--------------------------------------------------|
| `url`                    | Yes      | —                    | Discourse instance base URL. **Must be HTTPS** (HTTP is allowed only for localhost/loopback development). |
| `sso_secret`             | Yes      | —                    | Shared secret for DiscourseConnect HMAC signing. **Minimum 32 characters.** |
| `api_key`                | Yes      | —                    | Discourse Admin API key for moderation enrichment. **Required and must work** — missing credentials hide the backend; API request failures reject login. |
| `api_username`           | No       | `system`             | Discourse username for API requests.             |
| `organizer`              | Required for organiser claims | — | Pretix organizer slug. Team queries are scoped to this organizer. Attendee login does not require organizer team configuration. |
| `api_timeout`            | No       | `10`                 | Timeout in seconds for Discourse Admin API calls; must be an integer from 1 to 60. |

Example `pretix.cfg` section:

```ini
[discourse_auth]
url = https://forum.ansible.com
sso_secret = <shared-secret-from-discourse-admin-min-32-chars>
api_key = <discourse-admin-api-key>
api_username = system
organizer = ansible-meetups
```

Group policy is fixed in code: only exact `^meetup-organisers-([a-z]+)$` claims present in `CITY_TEAM_NAME_BY_SLUG` map to city teams. The active mapping currently contains `london` and `barcelona`; it duplicates the tooling repo's `CITIES` registry and is a release contract. Add every new city slug and exact canonical Pretix team name in both repositories before provisioning. The hardcoded Pretix-only team `Ansible Meetup Staff` is the other privileged class; its membership is never synchronized from Discourse. `require_2fa=true` is always sent and cannot be disabled.

### 4.5 Data model

The plugin **does not define its own database models**. It operates on pretix's existing models:

| Model          | How used | Verified details |
|----------------|----------|------------------|
| `User`         | Created/updated via `get_or_create_for_backend()`. Fields: `email`, `fullname`, Pretix-owned `is_staff`, auth backend linkage (`discourse` + `external_id`). | `is_staff` is never changed by this plugin. |
| `Team`         | Looked up by city slug **scoped to an organizer** (`ForeignKey` to `Organizer`). User added/removed via M2M `members` relation. The tooling provisioner creates and reconciles teams. | Team names are not globally unique. |
| `Organizer`    | Looked up by slug from config `organizer` key for organizer claims. | Missing/invalid configuration blocks organizer claims only. |
| Django Session/cache | The session stores nonce and timestamp; a shared Django cache backend atomically prevents nonce replay across concurrent callbacks. Production deployments must use a cache shared by all Pretix workers. | |

### 4.6 URL routing

| Method | Path                           | View           | Name     |
|--------|--------------------------------|----------------|----------|
| GET    | `/_discourse/login/return/`    | `return_view`  | `return` |

The URL is registered under the `plugins:pretix_discourse_auth` namespace.

### 4.7 External API calls

| Endpoint                                     | Method | Auth headers                          | When called    | Timeout |
|----------------------------------------------|--------|---------------------------------------|----------------|---------|
| `{DISCOURSE_URL}/session/sso_provider`       | GET    | None (HMAC in query params)           | Login initiation (browser redirect) | N/A |
| `{DISCOURSE_URL}/admin/users/{external_id}.json` | GET | `Api-Key`, `Api-Username`            | Every SSO callback | Configurable (`api_timeout`, default 10s) |

---

## 5. Non-Functional Requirements

These are requirements that the prototype either skipped entirely or handled minimally. The rebuild must address them.

### 5.1 Configuration validation

The backend reads one validated settings object at module import time. Invalid Discourse URL, SSO secret, API credentials, or API timeout hides the backend. Missing or invalid Pretix organizer configuration blocks only organizer claims; valid attendee logins remain available when the Discourse security check succeeds.

| Requirement | Behavior on failure |
|---|---|
| `url` must be HTTPS (or loopback HTTP for local development) | Backend invisible. Log ERROR with the invalid setting. |
| `sso_secret` must be ≥ 32 characters | Backend invisible. Log ERROR: "SSO secret too short (minimum 32 characters)." |
| `api_key` missing | Backend invisible and an error is logged. |
| Organizer setting missing/invalid or configured organizer does not exist | Reject organizer claims before user provisioning; attendee claims may proceed. |
| `api_timeout` is not an integer from 1 through 60 | Backend invisible. |
| Admin API credentials rejected or unavailable | Login rejected; no user provisioning or session creation occurs. |
| Privileged callback lacks `confirmed_2fa=true` | Login rejected before user provisioning. |
| Claimed organiser city has no matching Pretix team | Login rejected before user provisioning. |

### 5.2 Logging

| Event                        | Level   | Required fields                                              |
|------------------------------|---------|--------------------------------------------------------------|
| Login initiated              | INFO    | Return URL                                                   |
| SSO callback received        | DEBUG   | (No PII — just "callback received")                         |
| Rejection (any R1-R14)       | Per [Rejection Matrix](#34-rejection-matrix) | Per matrix |
| Identity extracted           | INFO    | `external_id`, username, organizer group count |
| Enrichment API call          | DEBUG   | URL (without API key), response status code                  |
| User provisioned (new)       | INFO    | `external_id`, email                                         |
| User updated (existing)      | DEBUG   | `external_id`, fields changed                                |
| Team added                   | INFO    | `external_id`, team name                                     |
| Team removed                 | INFO    | `external_id`, team name                                     |
| Team not found or ambiguous  | ERROR   | Claimed city slugs and configured organizer                  |
| Config validation             | ERROR or WARNING | Per [Section 5.1](#51-configuration-validation)         |

**PII handling:** Log `external_id` and `username` freely (they are public Discourse identifiers). Log `email` only on user creation. Never log the SSO payload, nonces, secrets, or API keys.

**Note:** Rejection logging details are defined in the [Rejection Matrix](#34-rejection-matrix) and are not duplicated here.

### 5.3 Testing

The rebuild must include:

**Unit tests (mocked external dependencies):**
- Signature verification: valid, tampered payload, tampered signature, empty, missing, trailing whitespace.
- Nonce: valid, missing from session, mismatched, already consumed (replay), expired (>10 min), and future-dated.
- Payload decoding: valid, invalid base64, invalid UTF-8, missing fields, `failed=true`.
- Group parsing: exact `meetup-organisers-london`, malformed suffixes, unrelated groups, mixed case, and automatic Discourse groups.
- City/team mapping: lowercase slug resolves through the explicit constant to exactly one provisioned Pretix team; unknown, missing, or duplicate team rejects organizer login; no `.title()` derivation.
- 2FA enforcement: exact positive `confirmed_2fa=true` for city organisers and existing Pretix staff-team members; missing/false claim rejected.
- RTBF detection: email ending with `@anonymized.invalid`, normal email, edge cases.
- Enrichment API: HTTP 200 with correct fields, 200 with missing fields, 401, 403, 500, timeout, invalid JSON.
- Enrichment field parsing: `silenced_till` present vs absent and `suspended_till` present vs absent; each moderation reason is shown to the user and recorded distinctly in logs; malformed field values fail closed.
- Policy enforcement: each condition independently, combined conditions, privileged vs non-privileged.
- Team sync: add to matching city team, idempotent re-add, remove stale city teams, missing team rejects organizer login, organizer scoping; Pretix staff-team membership remains admin-managed.
- Pretix `is_staff` remains unchanged for every Forum group claim; existing members of `Ansible Meetup Staff` require the signed 2FA assertion.
- Rate limiting: the callback allows at most 10 requests per client IP in a 60-second window; signature and nonce failures have double weight; cache errors fail closed.
- Session policy: callback login disables Pretix's persistent-session option and uses a browser-session cookie; Pretix's configured relative and absolute session limits remain in force.
- UTF-8: signed payloads with non-ASCII display names are preserved; invalid UTF-8 payloads are rejected.
- Email conflict handling.
- Config validation: each validation rule independently.

**Integration tests (with a real or stubbed Discourse):**
- Full round-trip: initiation → Discourse redirect → callback → logged in.
- Changed email between logins.
- Changed groups between logins.
- Concurrent logins (two tabs).

**Test framework:** `pytest` + `pytest-django` (matches pretix's own test setup). Use `responses` or `requests-mock` for HTTP mocking.

### 5.4 Rate limiting

- Apply a fixed-window rate limit to the SSO callback: at most 10 weighted attempts per client IP per 60 seconds.
- Every callback request counts once. Signature mismatch and invalid, expired, future-dated, or replayed nonce checks count twice in total.
- Obtain the client IP through Pretix's trusted proxy-aware `get_client_ip()` helper; do not trust arbitrary forwarded headers.
- Store counters in the shared Django cache used by Pretix workers. If the cache is unavailable, fail closed with a temporary service error. Production deployments must use a cache backend with atomic increment support shared by every worker.
- Return HTTP 429 with `Retry-After` when the limit is exceeded.

### 5.5 Internationalization

- Wrap all user-facing error messages in `gettext_lazy()` (`_(...)`).
- Provide English strings as the base.
- Include translation stubs for German (`de`) and informal German (`de_Informal`).

### 5.6 Dependency management

| Dependency    | Required action                     |
|---------------|-------------------------------------|
| `requests`    | Declared in `pyproject.toml` for the Discourse Admin API client. |
| `pretix`      | Do not add — it's the host application. Document the minimum supported pretix version. |

---

## 6. Assumptions and Edge Cases

### 6.1 Verified assumptions

These assumptions have been verified against Discourse and pretix source code.

| Assumption | Verification |
|---|---|
| **`external_id` in SSO provider mode is the Discourse user's internal database ID.** | Confirmed: `sso.external_id = current_user.id.to_s` in `discourse_connect_provider.rb:80`. |
| **`groups` payload is comma-separated group names.** | Confirmed: `current_user.groups.pluck(:name).join(",")` in `discourse_connect_provider.rb:83`. |
| **`groups` includes automatic Discourse groups.** | Confirmed: includes `trust_level_0`, `staff`, `everyone`, `admins`, etc. The plugin retains only full regex matches for `meetup-organisers-[a-z]+`. |
| **Suspended users cannot complete SSO.** | Confirmed: `current_user` returns `nil` for suspended users in `default_current_user_provider.rb`. The SSO provider redirects to login — they never reach pretix. |
| **Silenced users CAN complete SSO.** | Confirmed: silencing restricts posting, not authentication. The enrichment API check for `silenced_till` is the only defense. |
| **Anonymized users cannot complete SSO.** | Confirmed: `UserAnonymizer` destroys `single_sign_on_record`, `oauth2_user_infos`, `user_associated_accounts`, `api_keys`, `user_auth_tokens`. The user cannot log in to Discourse at all. |
| **Anonymized email domain is `@anonymized.invalid`.** | Confirmed: `EMAIL_SUFFIX = "@anonymized.invalid"` in `user_anonymizer.rb:6`. |
| **Anonymized username pattern is `anon` + digits.** | Confirmed: `anon#{(SecureRandom.random_number * 100_000_000).to_i}` in `user_anonymizer.rb:108`. |
| **`team.members` is a simple M2M.** | Confirmed: `members = models.ManyToManyField(User, related_name="teams")` in pretix `organizer.py:377`. No through table. `add()`/`remove()` are idempotent. |
| **Team is scoped per-organizer, NOT globally unique by name.** | Confirmed: `Team` has `ForeignKey` to `Organizer`. No unique constraint on `name`. Two organizers can have identically-named teams. |
| **`get_or_create_for_backend` always force-updates email.** | Confirmed: `set_always.update({'email': email})` is hardcoded in pretix `auth.py:136`. Cannot be skipped by the caller. |
| **`is_staff` grants site-wide admin access.** | Confirmed: gates the `staff_member_required` decorator in pretix `permissions.py:153`. |
| **`process_login` validates `next` parameter.** | Confirmed: uses `url_has_allowed_host_and_scheme(next_url, allowed_hosts=None)` which restricts to the current host. No open redirect risk. |
| **`require_2fa=true` works in SSO provider mode.** | Confirmed: DiscourseConnect returns `confirmed_2fa=true` after a successful challenge. Privileged pretix login requires that signed positive assertion. |

### 6.2 Remaining assumptions (not yet verified)

| Assumption | Risk if wrong |
|---|---|
| **The provisioner owns group/team creation.** | The tooling script creates and reconciles them from the registered city list; the auth plugin only validates and synchronizes membership. |
| **`pretix.cfg` is the only config source.** Module-level `config.get()` reads from the INI file. | Environment variable overrides or secrets managers are not supported. |
| **One Discourse instance per pretix deployment.** Config is global. | Multi-tenant deployments are not supported (by design — see Q4). |
| **The `return_sso_url` in the SSO payload is trusted by Discourse.** | Discourse must be configured to accept redirects to the pretix domain. |

### 6.3 Edge cases

| Edge case | Behavior | Risk level |
|---|---|---|
| **User changes email in Discourse between logins.** | `get_or_create_for_backend` matches on `('discourse', external_id)`, not email. Email is force-updated. If the new email is already claimed by another pretix user, `EmailAddressTakenError` blocks login (R13). | MEDIUM — user is locked out until an admin resolves the conflict. Cannot be changed without patching pretix. |
| **User's display name is empty and username is also empty.** | `name` falls back to `username`, which is `''`. User is created with empty `fullname`. | LOW — cosmetic. |
| **Discourse returns duplicate group names.** | Groups are collected into a `set`; duplicates are eliminated. | NONE — handled. |
| **Two users log in simultaneously, both added to the same team.** | `team.members.add()` is idempotent. No conflict. | NONE — handled. |
| **Privileged SSO response omits `confirmed_2fa`.** | Login is rejected before user provisioning. | NONE — fail-closed. |
| **Discourse API returns 200 but `silenced_till` or `suspended_till` is absent.** | Missing moderation fields mean the user is not in that moderation state. The response must still include a matching user ID and a non-empty username; malformed identity or field types block login. | NONE — follows the Admin API response shape while rejecting malformed responses. |
| **Team is renamed in pretix after user was added.** | On next login, old team name won't match expected; removal happens for the old name. The renamed team (no longer matching managed prefix) keeps the user as orphaned membership. | LOW — edge case during team administration. |
| **Team with same name exists in a different organizer.** | Team queries are scoped to the configured `organizer`. No cross-organizer match. | NONE — handled by organizer scoping. |
| **A matching organiser group exists without a Pretix team.** | Login is rejected before creating/updating the Pretix user. | NONE — fail-closed. |

### 6.4 Known limitations

#### 6.4.1 No session invalidation on status change

If a user is silenced in Discourse, their existing pretix sessions remain valid. The block only applies on next login attempt. A silenced user with an active session continues to have full access until the session expires.

**Future improvement:** On each enrichment check that detects silenced status, invalidate the user's active sessions via Django's session framework. Alternatively, implement a middleware that periodically re-checks status.

#### 6.4.2 Login-time-only sync

Group → team sync only happens at login. If a user is removed from a Discourse group, they retain pretix team membership until their next login.

**Future improvement:** Subscribe to Discourse webhook events for user/group changes, or implement a periodic sync management command.

#### 6.4.3 Email conflict requires admin intervention

When `get_or_create_for_backend` raises `EmailAddressTakenError`, the user is locked out. The email update is hardcoded in pretix and cannot be skipped by the plugin. Resolution requires an admin to either change the conflicting user's email in pretix or merge accounts.

---

## 7. Risks

### 7.1 Operational risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Discourse outage blocks all pretix logins | Medium | High — no organizer can log in | Both the SSO flow and the enrichment API depend on Discourse. Document this dependency. Consider a break-glass local admin account. |
| Discourse API key is rotated without updating pretix config | Medium | High — enrichment fails, all users fail-closed (R9) | Monitoring/alerting on enrichment API errors (R14 specifically). Document the key rotation procedure. |
| SSO secret mismatch after rotation | Low | High — all logins fail with signature mismatch (R2) | Coordinate secret rotation procedure. Consider supporting dual secrets during rotation. |
| Pretix team missing or duplicated for a claimed city | High | High — login is rejected before user provisioning | Provisioning creates/reconciles every registered city team. The auth plugin fails closed if an organizer claim has no unique mapped team. |
| Config changes require process restart | Guaranteed | Low | Document clearly. |

### 7.2 Security risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SSO payload logged in web server access logs (GET params contain PII) | High | Medium — email/username in access logs | Inherent to the DiscourseConnect protocol (GET-based). Configure web server to avoid logging query strings for the callback URL. Ensure log rotation and access controls. |
| Unapproved organiser group claim | Low | Medium — access to a matching city team | Forum admins manage organiser membership; the plugin requires an exact group name and a unique corresponding team. |
| Silenced user accesses pretix between silencing and next login | Medium | Low — silenced users have limited Discourse permissions but may still have pretix team access | Acceptable given login-time-only sync. Future: session invalidation or webhook-driven sync. |

---

## 8. Design Decisions

All design decisions are resolved. No open questions remain.

### Q1: Pretix staff permissions — DECIDED

Pretix administrators alone grant or revoke `is_staff` through Pretix configuration and manage membership of the Pretix-only `Ansible Meetup Staff` team. The Discourse auth plugin does not consume a Forum staff group, does not inspect Discourse's `admin` flag, and does not mutate Pretix staff status. Members of the staff team must pass DiscourseConnect's signed 2FA assertion. Create a Pretix break-glass administrator before enabling the SSO backend.

---

### Q2: API failure mode — DECIDED

**Decision:** Fail secure for all users (option a).

When the Discourse Admin API enrichment call fails for any reason (network error, timeout, non-200 HTTP status, invalid JSON, or malformed identity/field data), **reject the login for all users**. This API check verifies silenced and suspended status; privileged 2FA is independently enforced through DiscourseConnect's signed `confirmed_2fa=true` assertion.

**Rationale:** The "fail secure" principle takes precedence over availability. With `require_2fa` handled at the protocol layer (Step 7), the enrichment call's primary remaining purpose is the silenced/suspended check. A silenced user who gains pretix access during an API outage could access personal data (names, emails) of event attendees. This risk outweighs the inconvenience of temporary login unavailability during a Discourse API outage.

**Mitigation for availability:** Maintain a break-glass local admin account (created via `python manage.py createsuperuser`) that does not use Discourse SSO. This provides emergency access during Discourse outages.

---

### Q3: Team provisioning — DECIDED

The tooling provisioning script creates and reconciles Forum groups, categories, city teams, and the Pretix-only `Ansible Meetup Staff` team. For a new city, operators must update both the tooling repo's explicit `CITIES` record and this repo's `CITY_TEAM_NAME_BY_SLUG` mapping, deploy both, then run provisioning. The script owns team permissions and event scope; Pretix admins alone manage staff-team members. The auth plugin rejects organizer claims unless the corresponding city team exists under the configured Pretix organizer. Attendee logins do not require a city team.

---

### Q4: Multi-tenancy — DECIDED

**Decision:** Single pretix instance, single Discourse instance.

All configuration is global in `pretix.cfg`. Team queries are scoped to a single configured organizer. Per-organizer configuration is out of scope.

---

### Q5: RTBF detection — DECIDED

**Decision:** Email-domain heuristic only, as defense-in-depth.

**Constant:** `RTBF_EMAIL_SUFFIX = "@anonymized.invalid"`

RTBF detection checks only whether the user's email ends with `@anonymized.invalid` — the email suffix Discourse assigns during anonymization (verified in source: `UserAnonymizer::EMAIL_SUFFIX`).

Username and display name heuristics are **not used** — they produce false positives for legitimate usernames (`anonym`, `anondale`, users named "Anonymous").

**Rationale:** Discourse's anonymization process destroys all auth records (SSO records, OAuth tokens, API keys, auth tokens — verified in `user_anonymizer.rb`). An anonymized user **cannot log in to Discourse** at all, which means they cannot complete the SSO flow. The email-domain check is therefore pure defense-in-depth — it catches the theoretically impossible case where an anonymized user somehow reaches pretix's callback. The single strongest signal (email domain) is sufficient for this purpose. Zero false positives for legitimate users.

---

## 9. Deployment Checklist (Human-in-the-Loop)

These items require human decisions or actions before the plugin can be deployed. They cannot be resolved by code alone.

### 9.1 Discourse configuration (forum admin must complete)

- [ ] **Enable DiscourseConnect Provider** in Discourse admin → Settings → Login. The site setting `enable_discourse_connect_provider` must be `true`.
- [ ] **Set the SSO secret** in Discourse to match the `sso_secret` in `pretix.cfg`. Minimum 32 characters, cryptographically random.
- [ ] **Restrict group creation** to Discourse admins. A user who can create a matching organiser group for an existing Pretix team can claim that team's access.
- [ ] Run the tooling provisioner to create Forum groups and Pretix teams from its explicit city registry.
- [ ] **Generate a Discourse Admin API key** with "All Users" scope. Record it for `pretix.cfg`.
- [ ] **Verify `groups` is in the DiscourseConnect provider claims.** In Discourse admin → Settings → DiscourseConnect, check that `discourse_connect_provider_claims` includes `groups`. Without this, the SSO payload will not include group memberships and team sync will silently produce no matches.

### 9.2 Pretix configuration (pretix admin must complete)

- [ ] **Create a break-glass local admin account** via `python manage.py createsuperuser`. This provides emergency access if Discourse is unavailable.
- [ ] **Determine the organizer slug** — run `Organizer.objects.values_list('slug', flat=True)` in the pretix shell to list available organizers. Set this as `organizer` in `pretix.cfg`.
- [ ] Confirm the tooling provisioner created the city teams and scoped their permissions.
- [ ] **Configure `pretix.cfg`** with all required values. See [Appendix C](#appendix-c-config-quick-reference).
- [ ] **Restart pretix** after config changes (config is loaded at module import time).

### 9.3 Verification steps

- [ ] Confirm the "Log in with Discourse" button appears on the pretix login page. If it doesn't, check `pretix.log` for ERROR-level config validation messages.
- [ ] Confirm Pretix admin configuration controls `is_staff` and only Pretix admins manage membership in `Ansible Meetup Staff`.
- [ ] Test login with a user in `meetup-organisers-london` — verify team membership.
- [ ] Test a matching organiser group without a Pretix team — login must fail before user provisioning.
- [ ] Test a privileged response without `confirmed_2fa=true` — login must be rejected.
- [ ] Verify the Discourse Admin API key works by checking for ERROR-level "API key may be invalid" messages in logs.

### 9.4 Web server configuration

- [ ] **Configure the web server to suppress query string logging** for the callback URL (`/_discourse/login/return/`). The `sso` GET parameter contains base64-encoded PII (email, username, group memberships). This is inherent to the DiscourseConnect protocol and cannot be changed.
- [ ] **Ensure HTTPS** is enforced for the pretix domain (TLS termination at the proxy/load balancer).

### 9.5 Open security considerations for operator review

These are security tradeoffs the operator should understand and accept:

1. **Fail-secure posture:** If the Discourse Admin API is unreachable (network issues, Discourse downtime, API key rotation), **all logins are blocked**. This is by design — security over availability. The break-glass local admin account provides emergency access. If this tradeoff is unacceptable, the code must be modified.

2. **Pretix staff ownership:** `is_staff` is controlled in Pretix configuration only. This plugin never grants or revokes it based on Forum claims.

3. **Email conflict lockout:** If a user changes their Discourse email to one already claimed by another pretix user on a different auth backend, they are locked out (`EmailAddressTakenError`). This is a pretix limitation — the email update is hardcoded and cannot be skipped by the plugin. Resolution requires admin intervention.

4. **Login-time-only sync:** Organizer team membership syncs at login. A user removed from an organizer group retains team access until their next login or manual removal in Pretix. Pretix staff-team and `is_staff` membership remain administrator-managed.

5. **Session lifetime:** Discourse SSO sessions use a three-hour idle timeout and disable Pretix's "keep me logged in" behavior. The current Pretix version also enforces a 12-hour absolute limit in Pretix core. The organizer API used by `provision_environment.py` cannot change that server-side limit; changing it requires a Pretix server override.

6. **Silenced users with active sessions:** A user silenced in Discourse after their last pretix login retains their pretix session. The silenced check only runs during the enrichment call at login time. Same future improvement as item 4.

---

## Appendix A: DiscourseConnect Protocol Reference

This plugin implements the **consumer** side of the DiscourseConnect protocol. Discourse is the **provider** (identity provider). See [Section 1 (Terminology)](#1-terminology) for definitions.

**Protocol flow:**
1. The consumer (pretix) constructs a `nonce` + `return_sso_url` payload, base64-encodes it, HMAC-signs it, and redirects the user's browser to Discourse.
2. The provider (Discourse) authenticates the user, constructs a response payload with identity data, base64-encodes it, HMAC-signs it, and redirects the user's browser back to `return_sso_url`.
3. The consumer verifies the signature, decodes the payload, and extracts the identity.

**Request payload fields (consumer → provider):**

| Field | Description |
|-------|-------------|
| `nonce` | Single-use random token for replay protection |
| `return_sso_url` | Callback URL for Discourse to redirect to |
| `require_2fa` | If `true`, Discourse prompts the user for 2FA before redirecting back |

**Response payload fields (provider → consumer):**

| Field | Type | Description |
|-------|------|-------------|
| `nonce` | string | Echoed from request |
| `external_id` | string | Discourse internal user ID (`user.id`). Verified in source: `sso.external_id = current_user.id.to_s` |
| `email` | string | User's email |
| `username` | string | User's handle |
| `name` | string | Display name |
| `admin` | string | `"true"` if Discourse admin (not used by this plugin) |
| `moderator` | string | `"true"` if Discourse moderator |
| `groups` | string | Comma-separated group names. **Includes all groups** — custom groups AND automatic groups (`trust_level_0`, `staff`, `everyone`, etc.). Verified in source: `current_user.groups.pluck(:name).join(",")` |
| `confirmed_2fa` | string | `"true"` if user passed 2FA challenge (only present when `require_2fa=true` was sent) |
| `no_2fa_methods` | string | `"true"` if user has no 2FA methods configured (only present when `require_2fa=true` was sent) |
| `avatar_url` | string | CDN URL for avatar |

**Key protocol properties:**
- All data transits via browser redirects (GET parameters).
- Integrity is protected by HMAC-SHA256 with a pre-shared secret.
- Confidentiality depends on HTTPS — the payload is base64-encoded, **not encrypted**.
- Replay protection depends on the consumer implementing nonce verification.
- Discourse expires nonces after **30 minutes** on its side.

**Implementation note:** The `sso` query parameter value received by Django may contain a trailing newline. **Do not strip whitespace** from `request.GET.get('sso')` before HMAC computation — doing so breaks signature verification.

**References:**
- DiscourseConnect protocol: https://meta.discourse.org/t/discourseconnect-official-single-sign-on-for-discourse-sso/13045
- Discourse as provider: https://meta.discourse.org/t/use-discourse-as-an-identity-provider-sso-discourseconnect/32974

## Appendix B: Pretix Plugin System Reference

Verified against pretix source code.

**Registration:** Plugins are registered via `pyproject.toml` entry points under `pretix.plugin`. The entry point value points to the `PretixPluginMeta` class.

**Auth backends (`pretix.base.auth.BaseAuthBackend`):** Required overrides: `identifier` (property/string), `verbose_name` (property/string). Optional: `visible` (property, default `True`), `login_form_fields`, `form_authenticate`, `request_authenticate`, `authentication_url(request)` (returns redirect URL or `None`), `get_next_url(request)`.

**Config:** `pretix.settings.config` is a `ConfigParser` instance reading from `pretix.cfg`.

**User creation (`pretix.base.models.auth`):**
`User.objects.get_or_create_for_backend(backend, identifier, email, set_always={}, set_on_creation={})` — matches on `(backend, identifier)`. Always force-updates `email` via `set_always` (hardcoded at line 136). Raises `EmailAddressTakenError` if the new email collides with a user on a different backend.

**Team model (`pretix.base.models.organizer`):**
`Team` has a `ForeignKey` to `Organizer` (line 375). `name` is `CharField(max_length=190)` with **no uniqueness constraint**. `members = ManyToManyField(User, related_name="teams")` — simple M2M, no through table.

**Login (`pretix.control.views.auth`):**
`process_login(request, user, keep_logged_in=bool)` — establishes Django session. Redirects to `backend.get_next_url(request)`, which defaults to `request.GET.get("next")`, validated by `url_has_allowed_host_and_scheme(next_url, allowed_hosts=None)`.

**Staff access (`pretix.base.models.auth`):**
`is_staff = BooleanField(default=False, verbose_name='Is site admin')`. Gates `staff_member_required` decorator (line 153 in `permissions.py`). Grants access to site-wide admin views across all organizers.

## Appendix C: Config quick-reference

```ini
[discourse_auth]
# REQUIRED — backend will not appear on login page if any are missing
url = https://forum.ansible.com
sso_secret = <shared-secret-from-discourse-admin-minimum-32-chars>
api_key = <discourse-admin-api-key>
organizer = ansible-meetups

# OPTIONAL (defaults shown)
api_username = system
api_timeout = 10
```


## Canonical documentation location

This specification is maintained in the Ansible Meetup documentation repository. The plugin remains an independent Python package in [ansible-community/meetup-pretix-discourse-auth](https://github.com/ansible-community/meetup-pretix-discourse-auth); its code and release process are not part of this documentation project.
