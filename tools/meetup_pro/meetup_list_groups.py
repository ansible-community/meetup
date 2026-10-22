#!/usr/bin/env python3
"""List all groups in the Ansible Meetup Pro Network. Outputs CSV to stdout."""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
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
            groups.append(
                {
                    "id": node.get("id", ""),
                    "name": node.get("name", ""),
                    "urlname": node.get("urlname", ""),
                    "city": node.get("city", ""),
                    "country": node.get("country", ""),
                    "members": node.get("memberships", {}).get("totalCount", 0),
                    "timezone": node.get("timezone", ""),
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
    """Fetch Meetup Pro groups and write them as a private CSV file."""
    parser = argparse.ArgumentParser(description="Export groups in the Ansible Meetup Pro network")
    parser.add_argument("--output", type=Path, default=Path("tmp/meetup-groups.csv"), help="CSV output path")
    args = parser.parse_args()

    pre_flight_checks()

    logger.info("Authenticating with Meetup API...")
    client = MeetupGraphQLClient(get_access_token())

    logger.info("Fetching groups from Pro Network '%s'...", PRO_NETWORK)
    groups = fetch_all_groups(client)
    logger.info("Found %d groups", len(groups))

    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with args.output.open("w", newline="", encoding="utf-8") as output_file:
        args.output.chmod(0o600)
        writer = csv.DictWriter(
            output_file, fieldnames=["id", "name", "urlname", "city", "country", "members", "timezone"]
        )
        writer.writeheader()
        for group in sorted(groups, key=lambda g: g["name"]):
            writer.writerow(group)
    logger.info("Wrote groups CSV to %s", args.output)


if __name__ == "__main__":
    main()
