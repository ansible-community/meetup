#!/usr/bin/env python3
"""List all groups in the Ansible Meetup Pro Network. Outputs CSV to stdout."""

from __future__ import annotations

import csv
import logging
import sys
from typing import Any

from tools.meetup_pro.meetup_pro_lib import (
    PRO_NETWORK,
    MeetupGraphQLClient,
    get_access_token,
    logger,
    pre_flight_checks,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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
            memberships { count }
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
        search = data.get("data", {}).get("proNetwork", {}).get("groupsSearch", {})

        for edge in search.get("edges", []):
            node = edge.get("node", {})
            groups.append(
                {
                    "id": node.get("id", ""),
                    "name": node.get("name", ""),
                    "urlname": node.get("urlname", ""),
                    "city": node.get("city", ""),
                    "country": node.get("country", ""),
                    "members": node.get("memberships", {}).get("count", 0),
                    "timezone": node.get("timezone", ""),
                }
            )

        page_info = search.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info["endCursor"]
        else:
            break

    return groups


def main() -> None:
    """Fetch Meetup Pro groups and write them as CSV to stdout."""
    pre_flight_checks()

    logger.info("Authenticating with Meetup API...")
    client = MeetupGraphQLClient(get_access_token())

    logger.info("Fetching groups from Pro Network '%s'...", PRO_NETWORK)
    groups = fetch_all_groups(client)
    logger.info("Found %d groups", len(groups))

    writer = csv.DictWriter(sys.stdout, fieldnames=["id", "name", "urlname", "city", "country", "members", "timezone"])
    writer.writeheader()
    for group in sorted(groups, key=lambda g: g["name"]):
        writer.writerow(group)


if __name__ == "__main__":
    main()
