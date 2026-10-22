#!/usr/bin/env python3
"""Reconcile meetup-attendee-* group membership from the user_event_cities custom field.

Field values look like "Europe:UK:London" and map to a group named
"meetup-attendee-london". Designed to run hourly/daily via cron.

- Full-state reconciliation: self-heals drift on every run.
- Additive by default (no pruning). Use --prune to also remove
  users who deselected a city.
- Fails gracefully: values that map to nonexistent groups are skipped.

Usage:
  uv run python -m tools.attendees.sync_city_groups --dry-run
  uv run python -m tools.attendees.sync_city_groups --apply
  uv run python -m tools.attendees.sync_city_groups --apply --prune
"""

from __future__ import annotations

import argparse
import logging
import time
from collections import defaultdict
from typing import Any

import requests

from tools.common.ansible_events_lib import (
    ATTENDEE_GROUP_PREFIX,
    CITIES,
    DISCOURSE_CLIENT,
    USER_CITY_FIELD_NAME,
    CityInfo,
    logger,
    pre_flight_checks,
)

CITY_BY_VALUE: dict[str, CityInfo] = {c.field_value: c for c in CITIES}

API_PAUSE = 0.15


def _get(path: str, **params: Any) -> Any:
    """Fetch JSON from the Discourse API.

    Args:
        path: API path relative to the configured Discourse URL.
        **params: Query parameters for the request.

    Returns:
        The decoded JSON response.
    """
    time.sleep(API_PAUSE)
    resp = DISCOURSE_CLIENT.request("GET", path, params=params)
    if not 200 <= resp.status_code < 300:
        raise requests.HTTPError(f"Discourse GET {path} failed: HTTP {resp.status_code}", response=resp)
    resp.raise_for_status()
    return resp.json()


def _put(path: str, payload: dict[str, Any]) -> None:
    """Send a JSON update to the Discourse API.

    Args:
        path: API path relative to the configured Discourse URL.
        payload: JSON object to send.
    """
    time.sleep(API_PAUSE)
    resp = DISCOURSE_CLIENT.request("PUT", path, json=payload)
    if not 200 <= resp.status_code < 300:
        raise requests.HTTPError(f"Discourse PUT {path} failed: HTTP {resp.status_code}", response=resp)
    resp.raise_for_status()


def _delete(path: str, payload: dict[str, Any]) -> None:
    """Delete Discourse group members using a JSON request body.

    Args:
        path: API path relative to the configured Discourse URL.
        payload: JSON object describing the members to remove.
    """
    time.sleep(API_PAUSE)
    resp = DISCOURSE_CLIENT.request("DELETE", path, json=payload)
    if not 200 <= resp.status_code < 300:
        raise requests.HTTPError(f"Discourse DELETE {path} failed: HTTP {resp.status_code}", response=resp)
    resp.raise_for_status()


def attendee_group_for_value(value: str) -> str | None:
    """Map 'region:country:city' to 'meetup-attendee-{slug}'."""
    if value in CITY_BY_VALUE:
        return CITY_BY_VALUE[value].attendee_group
    logger.warning("Unregistered city field value %r; add the city to CITIES before syncing", value)
    return None


def list_attendee_groups() -> dict[str, int]:
    """Return {name: id} for all meetup-attendee-* groups."""
    groups: dict[str, int] = {}
    page = 0
    while True:
        data = _get("admin/groups.json", page=page)
        batch: list[dict[str, Any]] = data.get("groups") or [] if isinstance(data, dict) else []
        for g in batch:
            name = g.get("name", "")
            if name.startswith(ATTENDEE_GROUP_PREFIX):
                groups[name] = g["id"]
        if not batch:
            break
        page += 1
    return groups


def group_members(group_id: int) -> set[str]:
    """Return all usernames in a Discourse group.

    Args:
        group_id: Discourse group identifier.

    Returns:
        Usernames across all paginated member results.
    """
    members: set[str] = set()
    offset = 0
    while True:
        data = _get(f"admin/groups/{group_id}/members.json", offset=offset, limit=200)
        batch: list[dict[str, Any]] = data.get("members") or [] if isinstance(data, dict) else []
        members.update(m["username"] for m in batch)
        if len(batch) < 200:
            break
        offset += 200
    return members


def iter_users_with_field() -> list[tuple[str, list[str]]]:
    """Return (username, [field_values]) for all active users with city selections."""
    results: list[tuple[str, list[str]]] = []
    page = 0
    while True:
        data = _get("admin/users/list/active.json", page=page)
        users: list[dict[str, Any]] = (
            data if isinstance(data, list) else data.get("users", []) if isinstance(data, dict) else []
        )
        for row in users:
            username = row.get("username", "")
            user_id = row.get("id")
            if not username or not user_id:
                continue
            detail = _get(f"admin/users/{user_id}.json")
            user_data = detail.get("user", detail) if isinstance(detail, dict) else {}
            cf = user_data.get("custom_fields") or {} if isinstance(user_data, dict) else {}
            raw = cf.get(USER_CITY_FIELD_NAME)
            if raw is None:
                continue
            if isinstance(raw, str):
                values = [v.strip() for v in raw.split(",") if v.strip()]
            elif isinstance(raw, list):
                values = [str(v).strip() for v in raw if str(v).strip()]
            else:
                continue
            if values:
                results.append((username, values))
        if not users:
            break
        page += 1
    return results


def reconcile(*, apply: bool, prune: bool) -> int:
    """Plan or apply attendee-group membership from user city selections.

    Args:
        apply: Whether to write membership changes; false performs a dry run.
        prune: Whether to remove members whose city selection was cleared.

    Returns:
        Number of planned or applied membership changes.
    """
    existing_groups = list_attendee_groups()
    logger.info("Found %d attendee group(s)", len(existing_groups))

    logger.info("Fetching user field values (this may take a while)...")
    user_values = iter_users_with_field()
    logger.info("Found %d user(s) with city subscriptions", len(user_values))

    desired_by_group: dict[str, set[str]] = defaultdict(set)
    for username, values in user_values:
        for value in values:
            group = attendee_group_for_value(value)
            if group and group in existing_groups:
                desired_by_group[group].add(username)

    total_changes = 0
    for group_name, group_id in sorted(existing_groups.items()):
        current = group_members(group_id)
        desired = desired_by_group.get(group_name, set())
        to_add = desired - current
        to_remove = (current - desired) if prune else set()

        if not to_add and not to_remove:
            logger.info("%-35s ok (%d members)", group_name, len(current))
            continue

        total_changes += len(to_add) + len(to_remove)
        logger.info("%-35s members=%d  +%d / -%d", group_name, len(current), len(to_add), len(to_remove))

        if not apply:
            if to_add:
                logger.info("  would add: %s", ", ".join(sorted(to_add)))
            if to_remove:
                logger.info("  would remove: %s", ", ".join(sorted(to_remove)))
            continue

        if to_add:
            _put(f"admin/groups/{group_id}/members.json", {"usernames": sorted(to_add)})
            logger.info("  added %d user(s)", len(to_add))
        if to_remove:
            _delete(f"admin/groups/{group_id}/members.json", {"usernames": sorted(to_remove)})
            logger.info("  removed %d user(s)", len(to_remove))

    mode = "planned (dry-run)" if not apply else "applied"
    logger.info("Done. %d membership change(s) %s.", total_changes, mode)
    return total_changes


def main() -> None:
    """Parse CLI options and reconcile attendee group membership."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    pre_flight_checks(require_discourse=True, require_pretix=False)

    parser = argparse.ArgumentParser(description="Reconcile meetup-attendee-* groups from user_event_cities field")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show what would change without making changes")
    mode.add_argument("--apply", action="store_true", help="Actually make membership changes")
    parser.add_argument(
        "--prune", action="store_true", help="Remove users who deselected a city (default: additive only)"
    )
    args = parser.parse_args()

    reconcile(apply=args.apply, prune=args.prune)


if __name__ == "__main__":
    main()
