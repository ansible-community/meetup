#!/usr/bin/env python3
"""Export group membership counts from the Ansible Meetup Pro Network."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import logging
from pathlib import Path
from typing import Any

from tools.common.reporting import MEETUP_GROUP_SNAPSHOT_PATH, write_private_text
from tools.meetup_pro.meetup_pro_lib import (
    PRO_NETWORK,
    MeetupGraphQLClient,
    get_access_token,
    logger,
    pre_flight_checks,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_JSON_OUTPUT = MEETUP_GROUP_SNAPSHOT_PATH
GROUP_FIELDNAMES = ["id", "name", "urlname", "city", "country", "members", "timezone"]


def fetch_all_groups(client: MeetupGraphQLClient) -> list[dict[str, Any]]:
    """Fetch every group in the configured Meetup Pro network.

    Args:
        client: Authenticated Meetup GraphQL client.

    Returns:
        Group records with location, membership, and timezone data.
    """
    query = """
    query ($urlname: ID!, $cursor: String) {
      proNetwork(urlname: $urlname) {
        groupsSearch(input: { first: 200, after: $cursor, filter: {} }) {
          totalCount
          pageInfo { endCursor hasNextPage }
          edges { node {
            id name urlname
            city country
            memberships { totalCount }
            timezone
          } }
        }
      }
    }
    """
    groups: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        data = client.graphql(query, {"urlname": PRO_NETWORK, "cursor": cursor})
        network = data.get("data", {}).get("proNetwork")
        if network is None:
            raise RuntimeError(f"Meetup Pro Network '{PRO_NETWORK}' was not found or is not accessible")
        search = network.get("groupsSearch")
        if search is None:
            raise RuntimeError("Meetup did not return a group search result")

        for edge in search.get("edges", []):
            node = edge.get("node", {})
            if not isinstance(node, dict):
                raise RuntimeError("Meetup returned a group without a valid group record")
            name = node.get("name")
            memberships = node.get("memberships")
            member_count = memberships.get("totalCount") if isinstance(memberships, dict) else None
            if not isinstance(name, str) or not name:
                raise RuntimeError("Meetup returned a group without a valid name")
            if not isinstance(member_count, int) or isinstance(member_count, bool) or member_count < 0:
                raise RuntimeError(f"Meetup returned an invalid member count for group {name!r}")
            groups.append(
                {
                    "id": node.get("id", ""),
                    "name": name,
                    "urlname": node.get("urlname", ""),
                    "city": node.get("city") or "",
                    "country": node.get("country") or "",
                    "members": member_count,
                    "timezone": node.get("timezone") or "",
                }
            )

        page_info = search.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info.get("endCursor")
            if not cursor:
                raise RuntimeError("Meetup indicated another group page but returned no cursor")
        else:
            break

    if not groups:
        raise RuntimeError(f"No groups were returned for Pro Network '{PRO_NETWORK}'; check network access and name")

    return groups


def main() -> None:
    """Fetch Meetup Pro groups and write a private CSV and aggregate JSON snapshot."""
    parser = argparse.ArgumentParser(description="Export groups in the Ansible Meetup Pro network")
    parser.add_argument("--output", type=Path, default=Path("tmp/meetup-groups.csv"), help="CSV output path")
    parser.add_argument(
        "--json-output", type=Path, default=DEFAULT_JSON_OUTPUT, help="JSON snapshot path used by community reports"
    )
    args = parser.parse_args()
    if args.output.resolve() == args.json_output.resolve():
        parser.error("--output and --json-output must refer to different files")

    pre_flight_checks()

    logger.info("Authenticating with Meetup API...")
    client = MeetupGraphQLClient(get_access_token())

    logger.info("Fetching groups from Pro Network '%s'...", PRO_NETWORK)
    groups = fetch_all_groups(client)
    logger.info("Found %d groups", len(groups))

    csv_output = io.StringIO(newline="")
    writer = csv.DictWriter(csv_output, fieldnames=GROUP_FIELDNAMES)
    writer.writeheader()
    for group in sorted(groups, key=lambda g: g["name"]):
        writer.writerow(group)
    write_private_text(csv_output.getvalue(), args.output, overwrite=True)
    logger.info("Wrote groups CSV to %s", args.output)

    snapshot = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "network": PRO_NETWORK,
        "groups": sorted(groups, key=lambda group: group["name"].casefold()),
    }
    json_content = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    write_private_text(json_content, args.json_output, overwrite=True)
    logger.info("Wrote Meetup Pro JSON snapshot to %s", args.json_output)


if __name__ == "__main__":
    main()
