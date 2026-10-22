#!/usr/bin/env python3
"""Reconcile Discourse groups/categories and Pretix template/teams to desired state.

Safe to run repeatedly. Designed for both initial setup and ongoing maintenance
as new cities are added to the CITIES registry.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tools.common.ansible_event_cities import CITIES, CityInfo
from tools.common.ansible_events_lib import (
    ANSIBLE_PRIMARY_COLOR,
    ApiError,
    EVENT_SLUG_RE,
    CODE_OF_CONDUCT_URL,
    DEFAULT_ITEM_NAME,
    DEFAULT_ITEM_PRICE,
    DEFAULT_QUOTA_NAME,
    DISCOURSE_PARENT_CATEGORY_ID,
    EVENTS_FORUM_URL,
    MIGRATED_GROUP_NAME,
    ORGANIZERS_GROUP_RE,
    ORGANISERS_GROUP_PREFIX,
    ORGANISER_PERMISSIONS,
    STAFF_TEAM_NAME,
    GROUP_VISIBILITY_OWNERS_ONLY,
    GROUP_VISIBILITY_STAFF_ONLY,
    PRIVACY_POLICY_URL,
    TEMPLATE_SLUG,
    USER_CITY_FIELD_ID,
    discourse_req,
    discourse_categories,
    logger,
    pre_flight_checks,
    pretix_list_all,
    pretix_req,
    run_cli,
)

CATEGORY_PERMISSION_FULL = 1
CATEGORY_PERMISSION_CREATE_POST = 2
INVITE_API_USERNAME = "gundalow"
INVITE_PENDING_ENDPOINT = f"u/{INVITE_API_USERNAME}/invited/pending.json"
INVITE_MAX_REDEMPTIONS = 5_000
INVITE_EXPIRES_AT = "2030-01-01"


@dataclass(slots=True)
class CityForumPlan:
    """Desired Discourse resources for one registered city."""

    city: CityInfo
    organiser_group_id: int | None = None
    attendee_group_id: int | None = None
    category_id: int | None = None
    organiser_group_created: bool = False
    attendee_group_created: bool = False
    category_created: bool = False

    @property
    def organiser_group_name(self) -> str:
        """Return this city's organiser group name."""
        return self.city.organiser_group

    @property
    def attendee_group_name(self) -> str:
        """Return this city's attendee group name."""
        return self.city.attendee_group

    def organiser_group_settings(self) -> dict[str, Any]:
        """Build the desired security and notification settings for the organiser group."""
        settings: dict[str, Any] = {
            "name": self.organiser_group_name,
            "full_name": f"Ansible Meetup Organisers - {self.city.city}",
            "bio_raw": (
                f"Organisers for Ansible Community Meetups in {self.city.city}.\n\n"
                "**Requirements:** Members must have 2FA enabled on their forum account "
                "and be approved by the Community Engineering lead.\n\n"
                "This group grants Category Moderator rights on the "
                f"{self.city.city} Events subcategory and scoped access to the "
                "Pretix event dashboard (attendee list + check-in)."
            ),
            "visibility_level": GROUP_VISIBILITY_OWNERS_ONLY,
            "members_visibility_level": GROUP_VISIBILITY_OWNERS_ONLY,
            "public_admission": False,
            "allow_membership_requests": False,
            "automatic_membership_email_domains": "",
            "owner_usernames": "",
        }
        if self.category_id is not None:
            settings["tracking_category_ids"] = [self.category_id]
        return settings

    def attendee_group_settings(self) -> dict[str, Any]:
        """Build the desired privacy and notification settings for the attendee group."""
        return {
            "name": self.attendee_group_name,
            "full_name": f"Ansible Meetup Attendees - {self.city.city}",
            "bio_raw": (
                "Notification subscription group for Ansible Meetup events in "
                f"{self.city.city}.\n\n"
                "Members receive notifications when new events are posted. "
                "Membership is hidden (visible to forum admins only) to protect location privacy."
            ),
            "visibility_level": GROUP_VISIBILITY_STAFF_ONLY,
            "members_visibility_level": GROUP_VISIBILITY_STAFF_ONLY,
        }

    def category_settings(self) -> dict[str, Any]:
        """Build desired category permissions and presentation settings."""
        if self.organiser_group_id is None:
            raise ApiError(f"Organiser group ID is missing for city {self.city.slug!r}")
        return {
            "name": self.city.city,
            "parent_category_id": DISCOURSE_PARENT_CATEGORY_ID,
            "color": "EE0000",
            "text_color": "FFFFFF",
            "description": (
                f"Ansible Community Meetup events in {self.city.city}. "
                "Free, in-person meetups for automation enthusiasts — "
                "talks, networking, and community. "
                f"RSVP to upcoming Ansible Meetup {self.city.city} events below."
            ),
            # Everyone can read and reply; only this city's organisers can create topics.
            "permissions": {
                "everyone": CATEGORY_PERMISSION_CREATE_POST,
                self.organiser_group_name: CATEGORY_PERMISSION_FULL,
            },
            "moderating_group_ids": [self.organiser_group_id],
        }


def build_city_forum_plans() -> list[CityForumPlan]:
    """Build the full city-level desired state from the central CITIES registry."""
    return [CityForumPlan(city=city) for city in CITIES]


def pending_invites_by_description(response: Mapping[str, Any]) -> set[tuple[str, str]]:
    """Validate pending invite data and return (description, group name) pairs."""
    invites = response.get("invites")
    if not isinstance(invites, list):
        raise ApiError("Discourse pending invites response is missing an invites list")

    invite_targets: set[tuple[str, str]] = set()
    for index, invite in enumerate(invites):
        if not isinstance(invite, dict):
            raise ApiError(f"Discourse pending invites response contains an invalid invite at index {index}")
        description = invite.get("description")
        groups = invite.get("groups")
        if not isinstance(description, str) or not isinstance(groups, list):
            raise ApiError(f"Discourse pending invite at index {index} has invalid description or groups")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("name"), str):
                raise ApiError(f"Discourse pending invite at index {index} contains an invalid group")
            invite_targets.add((description, group["name"]))
    return invite_targets


def reconcile_attendee_invites() -> None:
    """Create missing city invite links for their attendee groups."""
    response = discourse_req("GET", INVITE_PENDING_ENDPOINT, run_as=INVITE_API_USERNAME)
    invite_targets = pending_invites_by_description(response)

    for city in CITIES:
        description = f"Join Ansible {city.city}"
        target = (description, city.attendee_group)
        if target in invite_targets:
            logger.info("Invite for %s already exists", city.city)
            continue

        payload = {
            "skip_email": True,
            "description": description,
            "group_names": city.attendee_group,
            "max_redemptions_allowed": INVITE_MAX_REDEMPTIONS,
            "expires_at": INVITE_EXPIRES_AT,
        }
        created = discourse_req("POST", "invites.json", payload, run_as=INVITE_API_USERNAME)
        logger.info("Created invite for %s: %s", city.city, created.get("link", "link unavailable"))


def list_discourse_groups() -> list[dict]:
    """Fetch meetup groups and reject malformed organiser group names.

    Returns:
        All groups whose name contains `meetup`, case-insensitively.

    Raises:
        ApiError: If a group in the organiser namespace does not match the
            canonical lowercase city-slug format.
    """
    groups: list[dict] = []
    page = 0
    while True:
        # The admin endpoint handles group creation but does not return a JSON
        # listing on GET. The group directory exposes the paginated JSON list.
        response = discourse_req("GET", f"groups.json?page={page}")
        batch = response.get("groups")
        if not isinstance(batch, list):
            raise ApiError("Discourse groups response is missing groups")
        if any(not isinstance(group, dict) for group in batch):
            raise ApiError("Discourse groups response contains an invalid group")
        for group in batch:
            name = group.get("name")
            if not isinstance(name, str):
                continue
            if name.casefold().startswith(ORGANISERS_GROUP_PREFIX.casefold()) and not ORGANIZERS_GROUP_RE.fullmatch(
                name
            ):
                raise ApiError(f"Discourse organiser group name {name!r} must match meetup-organisers-<lowercase-city>")
            if "meetup" in name.casefold():
                groups.append(group)
        if not batch:
            return groups
        page += 1


GROUP_RECONCILE_FIELDS = (
    "name",
    "full_name",
    "bio_raw",
    "visibility_level",
    "members_visibility_level",
    "public_admission",
    "allow_membership_requests",
    "automatic_membership_email_domains",
    "tracking_category_ids",
)

FIELD_LABELS: dict[str, str] = {
    "full_name": "full name",
    "bio_raw": "description",
    "visibility_level": "visibility",
    "members_visibility_level": "member visibility",
    "public_admission": "public admission",
    "allow_membership_requests": "membership requests",
    "automatic_membership_email_domains": "automatic membership domains",
    "owner_usernames": "group owners",
    "permissions": "permissions",
    "moderating_group_ids": "moderator groups",
    "tracking_category_ids": "tracking categories",
    "all_events": "all events",
    "all_event_permissions": "all event permissions",
    "limit_event_permissions": "event permissions",
    "all_organizer_permissions": "all organizer permissions",
    "limit_organizer_permissions": "organizer permissions",
    "limit_events": "event scope",
    "require_2fa": "2FA required",
    "is_public": "public listing",
}
UNORDERED_FIELDS: set[str] = {
    "limit_event_permissions",
    "limit_organizer_permissions",
    "limit_events",
    "moderating_group_ids",
    "tracking_category_ids",
}


def same_configuration_value(field: str, current: Any, desired: Any) -> bool:
    """Compare configuration values while accounting for unordered API lists.

    Args:
        field: Name of the configuration field.
        current: Value currently returned by the API.
        desired: Value required by provisioning.

    Returns:
        Whether the values represent the same configuration.
    """
    if field == "choices" and current in (None, []) and desired in (None, []):
        # Pretix represents an unrestricted metadata property as either null or [].
        return True
    if field in UNORDERED_FIELDS and isinstance(current, list) and isinstance(desired, list):
        return set(current) == set(desired)
    return current == desired


def log_resource_status(
    resource: str,
    desired: Mapping[str, Any],
    before: Mapping[str, Any] | None,
    extra_status: Mapping[str, str] | None = None,
) -> None:
    """Log whether each desired field was already correct or had to change."""
    statuses = {
        FIELD_LABELS.get(field, field.replace("_", " ")): (
            "OK"
            if before is None or (field in before and same_configuration_value(field, before[field], value))
            else "Changed"
        )
        for field, value in desired.items()
    }
    statuses.update(extra_status or {})
    if before is None:
        state = "Created"
    elif any(status == "Changed" for status in statuses.values()):
        state = "Updated"
    else:
        state = "Already configured"
    details = ", ".join(f"{field}: {status}" for field, status in statuses.items())
    logger.info("%s: %s | %s", resource, state, details)


def reconcile_pretix_event_settings(event_slug: str, desired: Mapping[str, Any]) -> None:
    """Patch only event settings that differ, then verify Pretix accepted them."""
    endpoint = f"events/{event_slug}/settings"
    before = pretix_req("GET", endpoint)
    changes = {
        field: value
        for field, value in desired.items()
        if field not in before or not same_configuration_value(field, before[field], value)
    }
    if not changes:
        log_resource_status(f"Template {event_slug} settings", desired, before)
        return

    after = pretix_req("PATCH", endpoint, changes)
    if not all(
        field in after and same_configuration_value(field, after[field], value) for field, value in desired.items()
    ):
        after = pretix_req("GET", endpoint)
    for field, value in desired.items():
        if field not in after or not same_configuration_value(field, after[field], value):
            raise ApiError(f"Pretix event {event_slug!r} did not reconcile setting {field!r}")
    log_resource_status(f"Template {event_slug} settings", desired, before)


def reconcile_pretix_mapping(
    endpoint: str,
    resource: str,
    desired: Mapping[str, Any],
    before: Mapping[str, Any],
) -> dict[str, Any]:
    """Patch a resource's changed fields and verify the response (or read it back)."""
    changes = {
        field: value
        for field, value in desired.items()
        if field not in before or not same_configuration_value(field, before[field], value)
    }
    if not changes:
        log_resource_status(resource, desired, before)
        return dict(before)

    after = pretix_req("PATCH", endpoint, changes)
    if not all(
        field in after and same_configuration_value(field, after[field], value) for field, value in desired.items()
    ):
        after = pretix_req("GET", endpoint)
    for field, value in desired.items():
        if field not in after or not same_configuration_value(field, after[field], value):
            raise ApiError(f"Pretix resource {resource!r} did not reconcile field {field!r}")
    log_resource_status(resource, desired, before)
    return after


def reconcile_pretix_teams() -> list[dict[str, Any]]:
    """Reconcile the staff and city teams from one teams/events snapshot."""
    all_teams = pretix_list_all("teams")
    all_events = pretix_list_all("events")
    teams_by_name: dict[str, list[dict[str, Any]]] = {}
    for team in all_teams:
        name = team.get("name")
        if not isinstance(name, str):
            raise ApiError("Pretix teams response contains a team without a valid name")
        teams_by_name.setdefault(name, []).append(team)

    desired_teams = [
        (
            STAFF_TEAM_NAME,
            {
                "name": STAFF_TEAM_NAME,
                "require_2fa": True,
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
        if any(
            isinstance(event.get("slug"), str)
            and event["slug"].startswith(f"{city.slug}-")
            and not EVENT_SLUG_RE.fullmatch(event["slug"])
            for event in all_events
        ):
            raise ApiError(f"Pretix has an invalid event slug for registered city {city.slug!r}")
        city_events = sorted(
            event["slug"]
            for event in all_events
            if isinstance(event.get("slug"), str)
            and (match := EVENT_SLUG_RE.fullmatch(event["slug"]))
            and match.group(1) == city.slug
        )
        desired_teams.append(
            (
                city.team_name,
                {
                    "name": city.team_name,
                    "require_2fa": True,
                    "all_events": False,
                    "all_event_permissions": False,
                    "limit_event_permissions": ORGANISER_PERMISSIONS,
                    "all_organizer_permissions": False,
                    "limit_organizer_permissions": [],
                    "limit_events": city_events,
                },
            )
        )

    for name, desired in desired_teams:
        existing = teams_by_name.get(name, [])
        if len(existing) > 1:
            raise ApiError(f"Multiple Pretix teams are named {name!r}")
        before = existing[0] if existing else None
        if before is None:
            created = pretix_req("POST", "teams", desired)
            team_id = created.get("id")
            if not isinstance(team_id, int):
                raise ApiError(f"Could not resolve Pretix team {name!r}")
            actual = pretix_req("GET", f"teams/{team_id}")
            log_resource_status(name, desired, None)
        else:
            team_id = before.get("id")
            if not isinstance(team_id, int):
                raise ApiError(f"Pretix team {name!r} has an invalid ID")
            actual = reconcile_pretix_mapping(f"teams/{team_id}", name, desired, before)
            if actual is before:
                continue
        for field, value in desired.items():
            if field not in actual or not same_configuration_value(field, actual[field], value):
                raise ApiError(f"Pretix team {name!r} did not reconcile field {field!r}")
    return all_events


def reconcile_pretix_meta_property() -> None:
    """Ensure the Forum event URL property exists and cannot be edited by organisers."""
    properties = pretix_list_all("event_meta_properties")
    if any(not isinstance(prop.get("name"), str) for prop in properties):
        raise ApiError("Pretix event metadata response contains a property without a valid name")
    matches = [prop for prop in properties if prop.get("name") == "forum_topic_url"]
    if len(matches) > 1:
        raise ApiError("Pretix has multiple event metadata properties named 'forum_topic_url'")
    desired = {
        "name": "forum_topic_url",
        "default": EVENTS_FORUM_URL,
        "choices": None,
        "required": False,
        "protected": True,
    }
    if not matches:
        created = pretix_req("POST", "event_meta_properties", desired)
        if any(created.get(field) != value for field, value in desired.items()):
            raise ApiError("Pretix Forum topic URL metadata property did not reconcile after creation")
        log_resource_status("forum_topic_url metadata property", desired, None)
        return
    prop = matches[0]
    property_id = prop.get("id")
    if not isinstance(property_id, int):
        raise ApiError("Pretix Forum topic URL metadata property has an invalid ID")
    reconcile_pretix_mapping(f"event_meta_properties/{property_id}", "forum_topic_url metadata property", desired, prop)


def reconcile_template_ticket() -> None:
    """Ensure the template has its standard RSVP item and a 100-ticket quota."""
    item_endpoint = f"events/{TEMPLATE_SLUG}/items"
    items = pretix_list_all(item_endpoint)
    item_matches = []
    for item in items:
        name = item.get("name")
        if not isinstance(name, dict) or not isinstance(name.get("en"), str):
            raise ApiError("Pretix template item response contains an invalid localized name")
        if name["en"] == DEFAULT_ITEM_NAME:
            item_matches.append(item)
    if len(item_matches) > 1:
        raise ApiError(f"Pretix template has multiple items named {DEFAULT_ITEM_NAME!r}")
    item_desired = {
        "name": {"en": DEFAULT_ITEM_NAME},
        "default_price": DEFAULT_ITEM_PRICE,
        "active": True,
        "admission": True,
    }
    if item_matches:
        item = item_matches[0]
        item_id = item.get("id")
        if not isinstance(item_id, int):
            raise ApiError(f"Pretix template item {DEFAULT_ITEM_NAME!r} has an invalid ID")
        item = reconcile_pretix_mapping(f"{item_endpoint}/{item_id}", DEFAULT_ITEM_NAME, item_desired, item)
    else:
        item = pretix_req("POST", item_endpoint, item_desired)
        item_id = item.get("id")
        if not isinstance(item_id, int):
            raise ApiError(f"Could not resolve Pretix template item {DEFAULT_ITEM_NAME!r}")
        log_resource_status(DEFAULT_ITEM_NAME, item_desired, None)
    if any(field not in item or item[field] != value for field, value in item_desired.items()):
        raise ApiError(f"Pretix template item {DEFAULT_ITEM_NAME!r} did not reconcile")

    quota_endpoint = f"events/{TEMPLATE_SLUG}/quotas"
    quotas = pretix_list_all(quota_endpoint)
    quota_matches = [quota for quota in quotas if quota.get("name") == DEFAULT_QUOTA_NAME]
    if len(quota_matches) > 1:
        raise ApiError(f"Pretix template has multiple quotas named {DEFAULT_QUOTA_NAME!r}")
    quota_desired = {"name": DEFAULT_QUOTA_NAME, "size": 100, "items": [item_id]}
    if quota_matches:
        quota = quota_matches[0]
        quota_id = quota.get("id")
        if not isinstance(quota_id, int):
            raise ApiError(f"Pretix template quota {DEFAULT_QUOTA_NAME!r} has an invalid ID")
        reconcile_pretix_mapping(f"{quota_endpoint}/{quota_id}", DEFAULT_QUOTA_NAME, quota_desired, quota)
    else:
        created = pretix_req("POST", quota_endpoint, quota_desired)
        if any(created.get(field) != value for field, value in quota_desired.items()):
            raise ApiError(f"Pretix template quota {DEFAULT_QUOTA_NAME!r} did not reconcile after creation")
        log_resource_status(DEFAULT_QUOTA_NAME, quota_desired, None)


def reconcile_pretix_template(events: list[dict[str, Any]]) -> None:
    """Create or reconcile the private clone source and its settings/ticket configuration."""
    matches = [event for event in events if event.get("slug") == TEMPLATE_SLUG]
    if len(matches) > 1:
        raise ApiError(f"Pretix has multiple events named {TEMPLATE_SLUG!r}")
    # is_template is not part of Pretix's public event API. The API can clone
    # from any event by slug, so the stable slug identifies this private source.
    desired_event = {"live": False, "is_public": False, "timezone": "UTC"}
    if matches:
        event = matches[0]
        if not all(field in event for field in desired_event):
            event = pretix_req("GET", f"events/{TEMPLATE_SLUG}")
        reconcile_pretix_mapping(f"events/{TEMPLATE_SLUG}", TEMPLATE_SLUG, desired_event, event)
    else:
        logger.info("Creating new master template (%s)...", TEMPLATE_SLUG)
        event = pretix_req(
            "POST",
            "events",
            {
                "name": {"en": "TEMPLATE: Standard Meetup"},
                "slug": TEMPLATE_SLUG,
                **desired_event,
                "currency": "USD",
                "date_from": "2026-12-31T18:00:00Z",
            },
        )
        if any(event.get(field) != value for field, value in desired_event.items()):
            raise ApiError(f"Pretix template {TEMPLATE_SLUG!r} did not reconcile after creation")
        log_resource_status(TEMPLATE_SLUG, desired_event, None)

    logger.info("Reconciling Pretix template settings...")
    reconcile_pretix_event_settings(
        TEMPLATE_SLUG,
        {
            "max_items_per_order": 1,
            "invoice_address_asked": False,
            "attendee_names_asked": True,
            "attendee_names_required": True,
            "attendee_emails_asked": False,
            "name_scheme": "full",
            "order_email_asked_twice": False,
            "payment_term_last": None,
            "meta_noindex": True,
        },
    )
    reconcile_template_ticket()


def group_id_from_response(response: Mapping[str, Any], resource: str) -> int:
    """Extract a newly-created Discourse group's ID from supported response shapes."""
    candidate = response.get("basic_group", response.get("group", response))
    group_id = candidate.get("id") if isinstance(candidate, dict) else None
    if not isinstance(group_id, int):
        raise ApiError(f"Could not resolve Discourse group ID for {resource!r}")
    return group_id


def ensure_group_exists(
    name: str,
    settings: Mapping[str, Any],
    groups_by_name: dict[str, dict[str, Any]],
) -> int:
    """Create a missing group and update the in-memory collection snapshot."""
    existing = groups_by_name.get(name)
    if existing is not None:
        group_id = existing.get("id")
        if not isinstance(group_id, int):
            raise ApiError(f"Discourse group {name!r} has an invalid ID")
        return group_id

    response = discourse_req("POST", "admin/groups.json", {"group": dict(settings)})
    group_id = group_id_from_response(response, name)
    groups_by_name[name] = {"id": group_id, "name": name}
    return group_id


def reconcile_discourse_group(
    name: str,
    group_id: int,
    desired: Mapping[str, Any],
    *,
    require_no_owners: bool = False,
    created: bool = False,
) -> None:
    """Read a group's settings once, update drift, and verify only after a write."""
    response = discourse_req("GET", f"groups/by-id/{group_id}.json")
    before = response.get("group")
    if not isinstance(before, dict):
        raise ApiError(f"Could not read current settings for Discourse group {name!r}")

    owners: list[Any] = []
    owners_changed = False
    if require_no_owners:
        owners_response = discourse_req("GET", f"groups/{name}/members.json")
        owners_value = owners_response.get("owners")
        if not isinstance(owners_value, list):
            raise ApiError(f"Could not read owners for Discourse group {name!r}")
        owners = owners_value
        owners_changed = bool(owners)

    changes = {
        field: value
        for field, value in desired.items()
        if field in GROUP_RECONCILE_FIELDS
        and (field not in before or not same_configuration_value(field, before[field], value))
    }
    if require_no_owners and owners:
        changes["owner_usernames"] = ""

    if changes:
        update_response = discourse_req(
            "PUT",
            f"groups/{group_id}.json",
            {"group": changes, "update_existing_users": "true"},
        )
        returned = update_response.get("group")
        if not isinstance(returned, dict) or any(
            field not in returned or not same_configuration_value(field, returned[field], value)
            for field, value in desired.items()
            if field in GROUP_RECONCILE_FIELDS
        ):
            verified_response = discourse_req("GET", f"groups/by-id/{group_id}.json")
            returned = verified_response.get("group")
        if not isinstance(returned, dict) or any(
            field not in returned or not same_configuration_value(field, returned[field], value)
            for field, value in desired.items()
            if field in GROUP_RECONCILE_FIELDS
        ):
            raise ApiError(f"Discourse group {name!r} did not reconcile to the requested settings")
        if require_no_owners:
            owners_response = discourse_req("GET", f"groups/{name}/members.json")
            owners_value = owners_response.get("owners")
            if not isinstance(owners_value, list):
                raise ApiError(f"Could not verify owners for Discourse group {name!r}")
            owners = owners_value
    elif any(
        field not in before or not same_configuration_value(field, before[field], value)
        for field, value in desired.items()
        if field in GROUP_RECONCILE_FIELDS
    ):
        raise ApiError(f"Discourse group {name!r} did not reconcile to the requested settings")

    if require_no_owners and (not isinstance(owners, list) or owners):
        raise ApiError(f"Discourse organiser group {name!r} must have no group owners")
    log_resource_status(
        name,
        {field: value for field, value in desired.items() if field in GROUP_RECONCILE_FIELDS},
        None if created else before,
        {"group owners": "Changed" if owners_changed else "OK"} if require_no_owners else None,
    )


def category_permission_map(category: Mapping[str, Any], category_id: int) -> dict[str, int]:
    """Read Discourse's serialized group_permissions into its API input form."""
    rows = category.get("group_permissions")
    if not isinstance(rows, list):
        raise ApiError(f"Discourse category {category_id} returned invalid group permissions")
    permissions: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ApiError(f"Discourse category {category_id} returned an invalid group permission")
        group_name = row.get("group_name")
        permission_type = row.get("permission_type")
        if (
            not isinstance(group_name, str)
            or not group_name
            or not isinstance(permission_type, int)
            or isinstance(permission_type, bool)
            or group_name in permissions
        ):
            raise ApiError(f"Discourse category {category_id} returned an invalid group permission")
        permissions[group_name] = permission_type
    return permissions


def index_groups_by_name(groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index the single paginated group snapshot by exact group name."""
    indexed: dict[str, dict[str, Any]] = {}
    for group in groups:
        name = group.get("name")
        if isinstance(name, str):
            if name in indexed:
                raise ApiError(f"Multiple Discourse groups are named {name!r}")
            indexed[name] = group
    return indexed


def city_category_matches(categories: list[dict[str, Any]], city_name: str) -> list[dict[str, Any]]:
    """Find direct child categories with the requested city name.

    Args:
        categories: Flattened Discourse category records.
        city_name: Canonical city display name.

    Returns:
        Matching city subcategory records.
    """
    return [
        category
        for category in categories
        if isinstance(category.get("name"), str)
        and category["name"].casefold() == city_name.casefold()
        and category.get("parent_category_id") == DISCOURSE_PARENT_CATEGORY_ID
    ]


def ensure_city_category_exists(plan: CityForumPlan, categories: list[dict[str, Any]]) -> bool:
    """Create a missing city category; return whether the collection needs refreshing."""
    matches = city_category_matches(categories, plan.city.city)
    if len(matches) > 1:
        raise ApiError(f"Multiple Discourse city categories are named {plan.city.city!r}")
    if matches:
        category_id = matches[0].get("id")
        if not isinstance(category_id, int):
            raise ApiError(f"Discourse category {plan.city.city!r} has an invalid ID")
        plan.category_id = category_id
        return False

    response = discourse_req("POST", "categories.json", plan.category_settings())
    category = response.get("category", response)
    category_id = category.get("id") if isinstance(category, dict) else None
    if isinstance(category_id, int):
        plan.category_id = category_id
    return True


def reconcile_city_category_access(
    categories: list[dict[str, Any]],
    plans_by_category_id: Mapping[int, CityForumPlan],
    groups_by_name: Mapping[str, dict[str, Any]],
) -> None:
    """Reconcile each category once, including global organiser access cleanup."""
    managed_group_ids = {
        group_id
        for name, group in groups_by_name.items()
        if ORGANIZERS_GROUP_RE.fullmatch(name) and isinstance((group_id := group.get("id")), int)
    }
    checked_categories = 0
    updated_categories: list[str] = []

    for category in categories:
        category_id = category.get("id")
        if not isinstance(category_id, int):
            raise ApiError("Discourse categories response contains an invalid category ID")
        checked_categories += 1
        details_response = discourse_req("GET", f"c/{category_id}/show.json")
        current = details_response.get("category", details_response)
        if not isinstance(current, dict):
            raise ApiError(f"Discourse category {category_id} returned invalid details")

        current_ids = current.get("moderating_group_ids")
        if not isinstance(current_ids, list) or any(not isinstance(group_id, int) for group_id in current_ids):
            raise ApiError(f"Discourse category {category_id} returned invalid moderator group IDs")
        current_permissions = category_permission_map(current, category_id)
        plan = plans_by_category_id.get(category_id)
        city_settings = plan.category_settings() if plan is not None else {}

        if plan is not None:
            desired_permissions = city_settings["permissions"]
            desired_ids = city_settings["moderating_group_ids"]
        else:
            desired_permissions = {
                name: level for name, level in current_permissions.items() if not ORGANIZERS_GROUP_RE.fullmatch(name)
            }
            desired_ids = [group_id for group_id in current_ids if group_id not in managed_group_ids]

        changes: dict[str, Any] = {}
        if desired_permissions != current_permissions:
            changes["permissions"] = desired_permissions
        if sorted(set(desired_ids)) != sorted(set(current_ids)):
            changes["moderating_group_ids"] = sorted(set(desired_ids))
        if plan is not None:
            changes.update(
                {
                    field: value
                    for field, value in city_settings.items()
                    if field not in {"permissions", "moderating_group_ids"}
                    and (field not in current or not same_configuration_value(field, current[field], value))
                }
            )

        if changes:
            discourse_req("PUT", f"categories/{category_id}.json", changes)
            updated_response = discourse_req("GET", f"c/{category_id}/show.json")
            updated = updated_response.get("category", updated_response)
            if not isinstance(updated, dict):
                raise ApiError(f"Discourse category {category_id} could not be verified after update")
            updated_permissions = category_permission_map(updated, category_id)
            expected_permissions = changes.get("permissions", current_permissions)
            expected_ids = changes.get("moderating_group_ids", current_ids)
            mismatched_fields = []
            if "permissions" in changes and updated_permissions != expected_permissions:
                mismatched_fields.append("permissions")
            if "moderating_group_ids" in changes and sorted(set(updated.get("moderating_group_ids", []))) != sorted(
                set(expected_ids)
            ):
                mismatched_fields.append("moderating_group_ids")
            mismatched_fields.extend(
                field
                for field, value in changes.items()
                if field not in {"permissions", "moderating_group_ids"}
                and not same_configuration_value(field, updated.get(field), value)
            )
            if mismatched_fields:
                raise ApiError(
                    f"Discourse category {category_id} failed reconciliation for: {', '.join(mismatched_fields)}"
                )
            if plan is None:
                updated_categories.append(f"{current.get('name', category_id)} ({category_id})")

        if plan is not None:
            log_resource_status(
                f"Events > {plan.city.city}",
                city_settings,
                None if plan.category_created else {**current, "permissions": current_permissions},
            )

    if updated_categories:
        logger.info(
            "Discourse organiser access: checked %d categories; updated %d: %s",
            checked_categories,
            len(updated_categories),
            ", ".join(updated_categories),
        )
    else:
        logger.info("Discourse organiser access: checked %d categories; no changes required", checked_categories)


def ensure_category_group_moderation_enabled() -> None:
    """Fail unless Discourse permits assigning groups as category moderators."""
    response = discourse_req(
        "GET",
        "admin/site_settings.json?names%5B%5D=enable_category_group_moderation",
    )
    settings = response.get("site_settings")
    if not isinstance(settings, list):
        raise ApiError("Could not verify Discourse category group moderation setting")
    setting = next(
        (item for item in settings if item.get("setting") == "enable_category_group_moderation"),
        None,
    )
    if not setting or str(setting.get("value")).lower() != "true":
        raise ApiError("Discourse enable_category_group_moderation must be enabled to assign city organisers")


def ensure_user_field_options() -> None:
    """Add any missing city options to the user_event_cities custom field (additive only)."""
    logger.info("Syncing user field options for city subscriptions...")

    # GET uses hyphenated path, PUT uses underscored path (Discourse routing)
    resp = discourse_req("GET", f"admin/config/user-fields/{USER_CITY_FIELD_ID}.json")
    if not resp:
        raise RuntimeError(f"Could not fetch user field {USER_CITY_FIELD_ID}")

    current_options = set(resp.get("user_field", {}).get("options", []))
    desired_options = {city.field_value for city in CITIES}
    missing = desired_options - current_options

    if not missing:
        logger.info("User field options up to date (%d options)", len(current_options))
        return

    updated_options = sorted(current_options | desired_options)
    logger.info("Adding %d new option(s): %s", len(missing), ", ".join(sorted(missing)))

    discourse_req(
        "PUT",
        f"admin/config/user_fields/{USER_CITY_FIELD_ID}.json",
        {"user_field": {"options": updated_options}},
    )


def reconcile_pretix_global_settings() -> None:
    """Reconcile Pretix organizer-wide settings."""
    organizer_settings = {
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
    current_settings = pretix_req("GET", "settings")
    reconcile_pretix_mapping(
        "settings",
        "Pretix organizer settings",
        organizer_settings,
        current_settings,
    )


def reconcile_discourse_environment(groups_by_name: dict[str, dict[str, Any]]) -> None:
    """Reconcile meetup groups, city subcategories, access, and user fields."""
    ensure_category_group_moderation_enabled()

    # Read each collection once. Subsequent create/update operations maintain
    # these snapshots so per-city work never triggers another full listing.
    categories = discourse_categories()
    plans = build_city_forum_plans()

    logger.info("Ensuring group %s...", MIGRATED_GROUP_NAME)
    migrated_settings = {
        "name": MIGRATED_GROUP_NAME,
        "full_name": "Ansible Meetup - Migrated from Meetup Pro",
        "bio_raw": (
            "People who have migrated from Meetup Pro (meetup.com/pro/ansible) "
            "to the community-owned meetup platform.\n\n"
            "This group is used for tracking migration progress. "
            "Membership is managed automatically via invite links."
        ),
        "visibility_level": 3,
    }
    migrated_created = MIGRATED_GROUP_NAME not in groups_by_name
    migrated_id = ensure_group_exists(MIGRATED_GROUP_NAME, migrated_settings, groups_by_name)
    reconcile_discourse_group(MIGRATED_GROUP_NAME, migrated_id, migrated_settings, created=migrated_created)

    for plan in plans:
        plan.organiser_group_created = plan.organiser_group_name not in groups_by_name
        plan.organiser_group_id = ensure_group_exists(
            plan.organiser_group_name,
            plan.organiser_group_settings(),
            groups_by_name,
        )
        plan.attendee_group_created = plan.attendee_group_name not in groups_by_name
        plan.attendee_group_id = ensure_group_exists(
            plan.attendee_group_name,
            plan.attendee_group_settings(),
            groups_by_name,
        )

    categories_created = False
    for plan in plans:
        plan.category_created = not city_category_matches(categories, plan.city.city)
        categories_created |= ensure_city_category_exists(plan, categories)

    # A single refresh resolves IDs for newly-created categories. Existing
    # categories keep using the initial collection snapshot.
    if categories_created:
        categories = discourse_categories()
    for plan in plans:
        matches = city_category_matches(categories, plan.city.city)
        if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
            raise ApiError(f"Expected exactly one Events subcategory for {plan.city.city!r}; found {len(matches)}")
        plan.category_id = matches[0]["id"]

    for plan in plans:
        if plan.organiser_group_id is None or plan.category_id is None:
            raise ApiError(f"Could not resolve Discourse resources for city {plan.city.slug!r}")
        reconcile_discourse_group(
            plan.organiser_group_name,
            plan.organiser_group_id,
            plan.organiser_group_settings(),
            require_no_owners=True,
            created=plan.organiser_group_created,
        )
        if plan.attendee_group_id is None:
            raise ApiError(f"Could not resolve attendee group for city {plan.city.slug!r}")
        reconcile_discourse_group(
            plan.attendee_group_name,
            plan.attendee_group_id,
            plan.attendee_group_settings(),
            created=plan.attendee_group_created,
        )

    reconcile_attendee_invites()

    plans_by_category_id = {plan.category_id: plan for plan in plans if plan.category_id is not None}
    reconcile_city_category_access(categories, plans_by_category_id, groups_by_name)

    ensure_user_field_options()


def reconcile_pretix() -> None:
    """Reconcile Pretix global settings, teams, metadata, and template."""
    pre_flight_checks(require_discourse=False, require_pretix=True)
    logger.info("--- PRETIX PROVISIONING ---")
    reconcile_pretix_global_settings()

    logger.info("Reconciling Pretix teams and metadata...")
    all_events = reconcile_pretix_teams()
    reconcile_pretix_meta_property()

    logger.info("Reconciling Pretix template...")
    reconcile_pretix_template(all_events)


def reconcile_forum() -> None:
    """Reconcile Discourse groups and categories."""
    pre_flight_checks(require_discourse=True, require_pretix=False)
    # Validate the complete meetup group inventory before making any changes.
    groups_by_name = index_groups_by_name(list_discourse_groups())
    logger.info("--- FORUM PROVISIONING ---")
    reconcile_discourse_environment(groups_by_name)


def main() -> None:
    """Run the selected Pretix and/or Forum reconciliation phases."""
    parser = argparse.ArgumentParser(description="Reconcile the meetup Pretix and Forum environment.")
    parser.add_argument("--pretix", action="store_true", help="reconcile Pretix settings and event template")
    parser.add_argument("--forum", action="store_true", help="reconcile Forum groups and categories")
    args = parser.parse_args()

    if not args.pretix and not args.forum:
        parser.print_help()
        raise SystemExit(2)

    if args.pretix:
        reconcile_pretix()
    if args.forum:
        reconcile_forum()

    logger.info("--- PROVISIONING COMPLETE ---")


if __name__ == "__main__":
    run_cli(main)
