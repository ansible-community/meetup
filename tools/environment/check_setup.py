#!/usr/bin/env python3
"""Read-only diagnostics for the shared Pretix and Forum setup."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from tools.common import ansible_events_lib as api
from tools.common.ansible_events_lib import (
    ANSIBLE_PRIMARY_COLOR,
    CITIES,
    CODE_OF_CONDUCT_URL,
    DEFAULT_ITEM_NAME,
    DEFAULT_ITEM_PRICE,
    DEFAULT_QUOTA_NAME,
    DISCOURSE_URL,
    EVENTS_FORUM_URL,
    ORGANISER_PERMISSIONS,
    ORGANIZER_SLUG,
    PASSBOOK_BACKFIELD_DEFAULT,
    PASSBOOK_BACKFIELD_PROPERTY,
    PRIVACY_POLICY_URL,
    STAFF_TEAM_NAME,
    TEMPLATE_SLUG,
    ApiError,
    discourse_req,
    pretix_list_all,
    pretix_req,
)

FORUM_USERNAME = "gundalow"
CHECKOUT_SSO_SETTING = "pretix_discourse_auth_require_checkout_sso"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One operator-facing diagnostic result."""

    status: str
    name: str
    target: str
    detail: str
    next_step: str


class SetupChecker:
    """Collect independent read-only checks and retain partial results on API errors."""

    def __init__(self) -> None:
        self.results: list[CheckResult] = []
        self.pretix_available = False
        self.forum_available = False
        self.pretix_teams_readable = False
        self.pretix_teams: list[dict[str, Any]] = []
        self.pretix_events: list[dict[str, Any]] = []
        self.forum_user: dict[str, Any] | None = None
        self.forum_admin_user: dict[str, Any] | None = None
        self.forum_groups: list[dict[str, Any]] = []

    def add(self, status: str, name: str, target: str, detail: str, next_step: str) -> None:
        self.results.append(CheckResult(status, name, target, detail, next_step))

    @staticmethod
    def sanitized_api_failure(system: str, target: str, exc: Exception) -> str:
        """Avoid printing response bodies or exception strings that could contain secrets."""
        return f"{system} request failed ({type(exc).__name__}); response details were suppressed."

    def check_local_configuration(self) -> None:
        missing = []
        if not api.PRETIX_API_TOKEN:
            missing.append("PRETIX_API_TOKEN")
        if not api.DISCOURSE_API_KEY:
            missing.append("DISCOURSE_API_KEY")
        parsed = urlparse(api.PRETIX_URL)
        local_host = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        valid_url = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
        )
        secure_url = valid_url and (parsed.scheme == "https" or (parsed.scheme == "http" and local_host))
        if not secure_url:
            missing.append("PRETIX_URL (HTTPS required outside localhost/loopback)")
        if missing:
            self.add(
                "FAIL",
                "Local API configuration",
                "PRETIX_API_TOKEN, DISCOURSE_API_KEY, PRETIX_URL",
                "Missing or invalid: " + ", ".join(missing),
                "Set the required credentials and a valid Pretix URL; secret values are never displayed.",
            )
        else:
            self.add(
                "PASS",
                "Local API configuration",
                "PRETIX_API_TOKEN, DISCOURSE_API_KEY, PRETIX_URL",
                "Required credentials are present and Pretix URL meets the transport requirement.",
                "None.",
            )
        self.pretix_available = bool(api.PRETIX_API_TOKEN and secure_url)
        self.forum_available = bool(api.DISCOURSE_API_KEY)

    def check_pretix(self) -> None:
        if not self.pretix_available:
            self.add(
                "FAIL",
                "Pretix API access",
                f"GET {api.PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/settings/",
                "Skipped because Pretix credentials or URL are unavailable.",
                "Set valid Pretix configuration and rerun.",
            )
            return

        self._check_pretix_settings()
        self._check_pretix_teams_and_events()
        self._check_pretix_meta_property()
        self._check_template()

    def _check_pretix_settings(self) -> None:
        target = f"GET organizers/{ORGANIZER_SLUG}/settings"
        desired = {
            "primary_color": ANSIBLE_PRIMARY_COLOR,
            "imprint_url": {"en": CODE_OF_CONDUCT_URL},
            "privacy_url": {"en": PRIVACY_POLICY_URL},
            "organizer_homepage_text": {
                "en": (
                    "Welcome to Ansible Community Meetups! "
                    f"Browse upcoming events and RSVP, or visit [the forum]({EVENTS_FORUM_URL}) "
                    "for discussions, talk proposals, and community."
                )
            },
        }
        try:
            actual = pretix_req("GET", "settings")
        except Exception as exc:
            self.add(
                "FAIL",
                "Pretix API access and organizer settings",
                target,
                self.sanitized_api_failure("Pretix", target, exc),
                "Check the token, organizer access, and Pretix API availability.",
            )
            return
        self._compare(
            "Pretix organizer settings",
            target,
            desired,
            actual,
            "Run the Pretix environment provisioner to reconcile these settings.",
        )

    def _check_pretix_teams_and_events(self) -> None:
        try:
            self.pretix_teams = pretix_list_all("teams")
            self.pretix_teams_readable = True
        except Exception as exc:
            target = "GET teams (paginated)"
            self.add(
                "FAIL",
                "Pretix API permission: organizer.teams:write",
                target,
                self.sanitized_api_failure("Pretix", target, exc) + "; this endpoint requires organizer.teams:write.",
                "Check API-token team assignment, organizer.teams:write, and Pretix availability.",
            )
        else:
            self.add(
                "PASS",
                "Pretix API permission: organizer.teams:write",
                "GET teams (paginated)",
                "Pretix accepted the team-list request, which is permission-gated by organizer.teams:write.",
                "None.",
            )

        events_error: Exception | None = None
        try:
            self.pretix_events = pretix_list_all("events")
        except Exception as exc:
            events_error = exc
        if events_error is not None:
            target = "GET events (paginated)"
            self.add(
                "FAIL",
                "Pretix events inventory access",
                target,
                self.sanitized_api_failure("Pretix", target, events_error),
                "Check organizer API access and Pretix availability.",
            )
            return

        self.add(
            "PASS",
            "Pretix events inventory access",
            "GET events (paginated)",
            "The organizer event inventory is readable.",
            "None.",
        )
        if not self.pretix_teams_readable:
            return
        teams_by_name: dict[str, list[dict[str, Any]]] = {}
        for team in self.pretix_teams:
            name = team.get("name")
            if isinstance(name, str):
                teams_by_name.setdefault(name, []).append(team)
        all_event_slugs = [event.get("slug") for event in self.pretix_events]
        desired_teams: list[tuple[str, dict[str, Any]]] = [
            (
                STAFF_TEAM_NAME,
                {
                    "name": STAFF_TEAM_NAME,
                    "require_2fa": False,
                    "all_events": True,
                    "limit_events": [],
                    "all_event_permissions": True,
                    "limit_event_permissions": [],
                    "all_organizer_permissions": False,
                    "limit_organizer_permissions": [],
                },
            )
        ]
        for city in CITIES:
            invalid_city_slugs = [
                slug
                for slug in all_event_slugs
                if isinstance(slug, str) and slug.startswith(f"{city.slug}-") and not api.EVENT_SLUG_RE.fullmatch(slug)
            ]
            if invalid_city_slugs:
                self.add(
                    "FAIL",
                    f"Pretix event slug inventory: {city.city}",
                    "GET events",
                    f"Found {len(invalid_city_slugs)} invalid event slug(s) for this city.",
                    "Rename or remove invalid event slugs, then rerun the environment provisioner.",
                )
            city_slugs = sorted(
                slug
                for slug in all_event_slugs
                if isinstance(slug, str) and slug.startswith(f"{city.slug}-") and api.EVENT_SLUG_RE.fullmatch(slug)
            )
            desired_teams.append(
                (
                    city.team_name,
                    {
                        "name": city.team_name,
                        "require_2fa": False,
                        "all_events": False,
                        "all_event_permissions": False,
                        "limit_event_permissions": ORGANISER_PERMISSIONS,
                        "all_organizer_permissions": False,
                        "limit_organizer_permissions": [],
                        "limit_events": city_slugs,
                    },
                )
            )

        for name, desired in desired_teams:
            target = f"GET teams (expected exact name: {name})"
            matches = teams_by_name.get(name, [])
            if len(matches) != 1:
                count_detail = "missing" if not matches else f"duplicate ({len(matches)} matches)"
                self.add(
                    "FAIL",
                    f"Pretix team: {name}",
                    target,
                    f"Expected exactly one team; found {count_detail}.",
                    "Run the Pretix environment provisioner, then investigate duplicate teams if present.",
                )
                continue
            self._compare(
                f"Pretix team: {name}",
                target,
                desired,
                matches[0],
                "Run the Pretix environment provisioner to reconcile team permissions and event scope.",
            )

    def _check_pretix_meta_property(self) -> None:
        target = "GET event_meta_properties"
        try:
            properties = pretix_list_all("event_meta_properties")
        except Exception as exc:
            self.add(
                "FAIL",
                "Pretix forum_topic_url metadata access",
                target,
                self.sanitized_api_failure("Pretix", target, exc),
                "Check token access to organizer event metadata.",
            )
            return
        matches = [p for p in properties if p.get("name") == "forum_topic_url"]
        if len(matches) != 1:
            self.add(
                "FAIL",
                "Pretix forum_topic_url metadata property",
                target,
                f"Expected exactly one property; found {len(matches)}.",
                "Run the Pretix environment provisioner and remove duplicates if needed.",
            )
            return
        desired = {
            "name": "forum_topic_url",
            "default": EVENTS_FORUM_URL,
            "choices": None,
            "required": False,
            "protected": True,
        }
        self._compare(
            "Pretix forum_topic_url metadata property",
            target,
            desired,
            matches[0],
            "Run the Pretix environment provisioner to reconcile the metadata property.",
        )

    def _check_template(self) -> None:
        event_target = f"GET events/{TEMPLATE_SLUG}"
        matches = [event for event in self.pretix_events if event.get("slug") == TEMPLATE_SLUG]
        if len(matches) != 1:
            self.add(
                "FAIL",
                "Pretix template event",
                event_target,
                f"Expected exactly one template; found {len(matches)}.",
                "Run the Pretix environment provisioner and check for duplicate template slugs.",
            )
            return
        event = matches[0]
        if not all(field in event for field in ("live", "is_public", "timezone")):
            try:
                event = pretix_req("GET", f"events/{TEMPLATE_SLUG}")
            except Exception as exc:
                self.add(
                    "FAIL",
                    "Pretix template event",
                    event_target,
                    self.sanitized_api_failure("Pretix", event_target, exc),
                    "Check access to the template event.",
                )
                return
        self._compare(
            "Pretix template event",
            event_target,
            {"live": False, "is_public": False, "timezone": "UTC"},
            event,
            "Run the Pretix environment provisioner to reconcile the template event.",
        )

        settings_target = f"GET events/{TEMPLATE_SLUG}/settings"
        try:
            settings = pretix_req("GET", f"events/{TEMPLATE_SLUG}/settings")
        except Exception as exc:
            self.add(
                "FAIL",
                "Pretix template settings API access",
                settings_target,
                self.sanitized_api_failure("Pretix", settings_target, exc),
                "Check token access to template settings and confirm the auth plugin exposes its event setting.",
            )
        else:
            expected_settings = {
                "max_items_per_order": 1,
                "invoice_address_asked": False,
                "attendee_names_asked": True,
                "attendee_names_required": True,
                "attendee_emails_asked": False,
                "name_scheme": "full",
                "order_email_asked_twice": False,
                "payment_term_last": None,
                "meta_noindex": True,
                CHECKOUT_SSO_SETTING: True,
            }
            self._compare(
                "Pretix template settings",
                settings_target,
                expected_settings,
                settings,
                (
                    "Reconcile the template settings; if the checkout SSO field is absent, "
                    "confirm the plugin setting hook is loaded."
                ),
            )

        self._check_template_item_and_quota()

    def _check_template_item_and_quota(self) -> None:
        self._check_template_passbook_property()
        items_target = f"GET events/{TEMPLATE_SLUG}/items"
        quotas_target = f"GET events/{TEMPLATE_SLUG}/quotas"
        try:
            items = pretix_list_all(f"events/{TEMPLATE_SLUG}/items")
        except Exception as exc:
            self.add(
                "FAIL",
                "Pretix template items API access",
                items_target,
                self.sanitized_api_failure("Pretix", items_target, exc),
                "Check token access to template items.",
            )
            return
        item_matches = [
            item for item in items if isinstance(item.get("name"), dict) and item["name"].get("en") == DEFAULT_ITEM_NAME
        ]
        if len(item_matches) != 1:
            self.add(
                "FAIL",
                "Pretix template RSVP item",
                items_target,
                f"Expected exactly one {DEFAULT_ITEM_NAME!r} item; found {len(item_matches)}.",
                "Run the Pretix environment provisioner and investigate duplicate RSVP items.",
            )
            return
        item = item_matches[0]
        self._compare(
            "Pretix template RSVP item",
            items_target,
            {"name": {"en": DEFAULT_ITEM_NAME}, "default_price": DEFAULT_ITEM_PRICE, "active": True, "admission": True},
            item,
            "Run the Pretix environment provisioner to reconcile the RSVP item.",
        )
        item_id = item.get("id")
        if not isinstance(item_id, int):
            self.add(
                "FAIL",
                "Pretix template RSVP item ID",
                items_target,
                "The RSVP item has no valid numeric ID.",
                "Inspect the Pretix template item and rerun provisioning.",
            )
            return
        try:
            quotas = pretix_list_all(f"events/{TEMPLATE_SLUG}/quotas")
        except Exception as exc:
            self.add(
                "FAIL",
                "Pretix template quotas API access",
                quotas_target,
                self.sanitized_api_failure("Pretix", quotas_target, exc),
                "Check token access to template quotas.",
            )
            return
        quota_matches = [quota for quota in quotas if quota.get("name") == DEFAULT_QUOTA_NAME]
        if len(quota_matches) != 1:
            self.add(
                "FAIL",
                "Pretix template capacity quota",
                quotas_target,
                f"Expected exactly one {DEFAULT_QUOTA_NAME!r} quota; found {len(quota_matches)}.",
                "Run the Pretix environment provisioner and investigate duplicate capacity quotas.",
            )
            return
        self._compare(
            "Pretix template capacity quota",
            quotas_target,
            {"name": DEFAULT_QUOTA_NAME, "size": 100, "items": [item_id]},
            quota_matches[0],
            "Run the Pretix environment provisioner to reconcile the template quota.",
        )

    def _check_template_passbook_property(self) -> None:
        target = f"GET events/{TEMPLATE_SLUG}/item_meta_properties"
        try:
            properties = pretix_list_all(f"events/{TEMPLATE_SLUG}/item_meta_properties")
        except Exception as exc:
            self.add(
                "FAIL",
                "Pretix template wallet-pass item property API access",
                target,
                self.sanitized_api_failure("Pretix", target, exc),
                "Check token access to template item metadata properties.",
            )
            return
        matches = [prop for prop in properties if prop.get("name") == PASSBOOK_BACKFIELD_PROPERTY]
        if len(matches) != 1:
            self.add(
                "FAIL",
                "Pretix template wallet-pass item property",
                target,
                f"Expected exactly one {PASSBOOK_BACKFIELD_PROPERTY!r} item metadata property; found {len(matches)}.",
                "Run the Pretix environment provisioner to add or reconcile the template property. "
                "Existing events need the property added separately; template changes affect future clones.",
            )
            return
        self._compare(
            "Pretix template wallet-pass item property",
            target,
            {
                "name": PASSBOOK_BACKFIELD_PROPERTY,
                "default": PASSBOOK_BACKFIELD_DEFAULT,
                "required": False,
                "allowed_values": None,
            },
            matches[0],
            "Run the Pretix environment provisioner to reconcile the template property.",
        )

    def check_forum(self) -> None:
        if not self.forum_available:
            self.add(
                "FAIL",
                "Forum API access",
                f"GET {DISCOURSE_URL}/",
                "Skipped because DISCOURSE_API_KEY is unavailable.",
                "Set DISCOURSE_API_KEY and rerun.",
            )
            return
        try:
            groups = []
            page = 0
            while True:
                response = discourse_req("GET", f"groups.json?page={page}")
                batch = response.get("groups")
                if not isinstance(batch, list):
                    raise ApiError("invalid group listing")
                groups.extend(group for group in batch if isinstance(group, dict))
                if not batch:
                    break
                page += 1
            self.forum_groups = groups
            profile_target = f"GET u/{FORUM_USERNAME}.json"
            profile_response = discourse_req("GET", f"u/{FORUM_USERNAME}.json")
            profile = profile_response.get("user")
            profile_id = profile.get("id") if isinstance(profile, dict) else None
            if (
                not isinstance(profile, dict)
                or not isinstance(profile_id, int)
                or isinstance(profile_id, bool)
                or profile_id < 1
                or str(profile.get("username", "")).casefold() != FORUM_USERNAME.casefold()
            ):
                raise ApiError("invalid forum profile")
            self.forum_user = profile
            self.add(
                "PASS",
                "Forum API access and user profile",
                profile_target,
                f"Forum API responded and {FORUM_USERNAME} profile resolved to user ID {profile['id']}.",
                "None.",
            )
        except Exception as exc:
            target = f"GET groups.json and u/{FORUM_USERNAME}.json"
            self.add(
                "FAIL",
                "Forum API access and user profile",
                target,
                self.sanitized_api_failure("Forum", target, exc),
                "Check the Forum API key, API username permissions, and Forum availability.",
            )
            return

        self._check_forum_user_admin_record()
        self._check_forum_city_groups()

    def _check_forum_user_admin_record(self) -> None:
        if self.forum_user is None:
            return
        external_id = self.forum_user["id"]
        target = f"GET admin/users/{external_id}.json"
        try:
            response = discourse_req("GET", f"admin/users/{external_id}.json")
        except Exception as exc:
            self.add(
                "FAIL",
                f"Forum Admin API identity: {FORUM_USERNAME}",
                target,
                self.sanitized_api_failure("Forum", target, exc),
                "Check that the configured Forum API identity can read Admin API user records.",
            )
            return
        # Discourse returns the Admin API account as the top-level object.
        record = response
        self.forum_admin_user = record
        username_matches = (
            record.get("id") == external_id and str(record.get("username", "")).casefold() == FORUM_USERNAME.casefold()
        )
        email = record.get("email")
        email_parts = email.rsplit("@", maxsplit=1) if isinstance(email, str) else []
        email_present = isinstance(email, str) and bool(email)
        valid_email = (
            isinstance(email, str)
            and len(email_parts) == 2
            and bool(email_parts[0])
            and bool(email_parts[1])
            and not email.casefold().endswith("@anonymized.invalid")
        )
        anonymized_email = isinstance(email, str) and email.casefold().endswith("@anonymized.invalid")
        safe_status = not bool(record.get("suspended_till")) and not bool(record.get("silenced_till"))
        if username_matches and safe_status and not email_present:
            self.add(
                "MANUAL",
                f"Forum Admin API identity: {FORUM_USERNAME}",
                target,
                "Forum ID, username, and account status are valid, but this response omitted the email field.",
                "This does not show that Discourse lacks an email; verify it in the Forum Admin interface "
                "or through an approved email-visible API.",
            )
        elif username_matches and valid_email and safe_status:
            self.add(
                "PASS",
                f"Forum Admin API identity: {FORUM_USERNAME}",
                target,
                "Forum ID and username match, email is usable, and account is not suspended or silenced.",
                "None.",
            )
        else:
            issues = []
            if not username_matches:
                issues.append("username mismatch")
            if not valid_email:
                issues.append("email anonymized" if anonymized_email else "email invalid")
            if not safe_status:
                issues.append("account suspended or silenced")
            self.add(
                "FAIL",
                f"Forum Admin API identity: {FORUM_USERNAME}",
                target,
                "; ".join(issues),
                "Review the Forum account in the Admin interface.",
            )

    def _check_forum_city_groups(self) -> None:
        group_names = [group.get("name") for group in self.forum_groups if isinstance(group.get("name"), str)]
        for city in CITIES:
            group_name = city.organiser_group
            target = f"GET groups/{group_name}/members.json"
            if group_names.count(group_name) != 1:
                self.add(
                    "FAIL",
                    f"Forum organiser group: {group_name}",
                    "GET groups.json",
                    f"Expected exactly one group; found {group_names.count(group_name)}.",
                    "Run the Forum provisioner and investigate duplicate or missing groups.",
                )
                continue
            target_mapping = f"{group_name} → {city.team_name}"
            if not self.pretix_teams_readable:
                self.add(
                    "MANUAL",
                    f"Forum/Pretix mapping: {city.city}",
                    target_mapping,
                    "Could not compare the mapping because Pretix teams were unavailable.",
                    "Resolve Pretix API access and rerun the checker.",
                )
            else:
                team_names = [team.get("name") for team in self.pretix_teams if isinstance(team.get("name"), str)]
                mapped = city.team_name in team_names
                self.add(
                    "PASS" if mapped else "FAIL",
                    f"Forum/Pretix mapping: {city.city}",
                    target_mapping,
                    "Forum group maps to the configured Pretix city team."
                    if mapped
                    else "Expected Pretix city team is not present.",
                    "Reconcile the Pretix city team and retain the matching Forum group name.",
                )
            try:
                response = discourse_req("GET", f"groups/{group_name}/members.json")
            except Exception as exc:
                self.add(
                    "FAIL",
                    f"Forum group membership: {group_name}",
                    target,
                    self.sanitized_api_failure("Forum", target, exc),
                    "Check Forum API permission to read group members.",
                )
                continue
            members = response.get("members")
            if not isinstance(members, list):
                self.add(
                    "FAIL",
                    f"Forum group membership: {group_name}",
                    target,
                    "Response did not contain a members list.",
                    "Check the Forum group members API response.",
                )
            elif any(
                isinstance(member, dict) and str(member.get("username", "")).casefold() == FORUM_USERNAME.casefold()
                for member in members
            ):
                self.add(
                    "PASS", f"Forum group membership: {group_name}", target, f"{FORUM_USERNAME} is a member.", "None."
                )
            else:
                self.add(
                    "FAIL",
                    f"Forum group membership: {group_name}",
                    target,
                    f"{FORUM_USERNAME} is not listed as a member.",
                    f"Add {FORUM_USERNAME} to {group_name}, then rerun.",
                )

    def add_manual_checks(self) -> None:
        manual = (
            (
                "Pretix auth plugin installed/enabled/version",
                "Confirm the expected plugin version is installed and enabled in Pretix.",
            ),
            (
                "Pretix server-side auth configuration",
                "Review [discourse_auth] configuration, including Forum URL, SSO secret, API key/username, "
                "organizer slug, and timeout. Do not copy secrets into reports.",
            ),
            ("Pretix workers restarted", "Confirm Pretix workers restarted after plugin or pretix.cfg changes."),
            (
                "Pretix bootstrap account state",
                f"Verify {FORUM_USERNAME}'s Pretix user is linked to the Forum user ID and has the required "
                "is_staff value in the Pretix Users interface.",
            ),
            (
                "Pretix API permission: organizer.settings.general:write",
                "Required to reconcile organizer settings and event metadata. Verify the API token's team "
                "has this permission; no write request is made.",
            ),
            (
                "Pretix API permission: organizer.events:create",
                "Required to create meetup events and the template. Verify the API token's team has this "
                "permission; no event is created as a probe.",
            ),
            (
                "Pretix API permission: event.settings.general:write",
                "Required to update template/event settings and publish the completed event. Verify the "
                "API token's team has this permission; no setting is changed as a probe.",
            ),
            (
                "Pretix API permission: event.items:write",
                "Required to reconcile RSVP items and quotas. Verify the API token's team has this "
                "permission; no item or quota is changed as a probe.",
            ),
            (
                "Forum API write permissions",
                "Required to create, update, and roll back meetup topics and to reconcile Forum groups and "
                "categories. Verify the configured API key can perform those actions; no write is attempted.",
            ),
            (
                "Live end-to-end checkout and SSO",
                "Use a controlled disposable event to verify checkout SSO, cart preservation, cancellation "
                "behavior, privileged login, and template-clone inheritance.",
            ),
        )
        for name, next_step in manual:
            self.add(
                "MANUAL",
                name,
                "Not safely observable through the available remote read APIs",
                "Requires server-side inspection or a controlled human verification.",
                next_step,
            )

    @staticmethod
    def _same(actual: Any, expected: Any, *, field: str | None = None) -> bool:
        if field == "allowed_values" and actual in (None, []) and expected in (None, []):
            return True
        if isinstance(expected, list) and isinstance(actual, list):
            return sorted(actual, key=repr) == sorted(expected, key=repr)
        return actual == expected

    def _compare(
        self, name: str, target: str, expected: Mapping[str, Any], actual: Mapping[str, Any], next_step: str
    ) -> None:
        differences = [
            key
            for key, value in expected.items()
            if key not in actual or not self._same(actual[key], value, field=key)
        ]
        if differences:
            self.add("FAIL", name, target, "Values differ or are missing for: " + ", ".join(differences), next_step)
        else:
            self.add("PASS", name, target, f"All {len(expected)} expected fields match.", "None.")

    def run(self) -> list[CheckResult]:
        self.check_local_configuration()
        self.check_pretix()
        self.check_forum()
        self.add_manual_checks()
        return self.results


def print_results(results: list[CheckResult]) -> bool:
    """Print sanitized results and return whether any diagnostic failed."""
    for result in results:
        marker = "🔴 " if result.status == "FAIL" else ""
        print(f"{marker}{result.status}: {result.name}")
        print(f"  Target: {result.target}")
        print(f"  Result: {result.detail}")
        print(f"  Next: {result.next_step}")
    counts = {status: sum(result.status == status for result in results) for status in ("PASS", "FAIL", "MANUAL")}
    print(f"Summary: {counts['PASS']} PASS, {counts['FAIL']} FAIL, {counts['MANUAL']} MANUAL")
    return counts["FAIL"] > 0


def main() -> None:
    failed = print_results(SetupChecker().run())
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
