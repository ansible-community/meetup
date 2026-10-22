#!/usr/bin/env python3
"""Export non-basic members from Ansible Meetup Pro groups as a private CSV."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from pathlib import Path

from tools.meetup_pro.meetup_pro_lib import (
    PRO_NETWORK,
    MeetupGraphQLClient,
    get_access_token,
    logger,
    pre_flight_checks,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


SCHEMA_QUERY = """
query MeetupOrganiserSchema($typeName: String!) {
  type: __type(name: $typeName) {
    name
    fields {
      name
      args { name type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
      type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
    }
  }
}
"""


def write_schema_report(client: MeetupGraphQLClient, output_path: Path) -> None:
    """Write the live Meetup fields relevant to group membership to JSON."""
    # Meetup rejects introspection operations that request __type more than once.
    # Query each type separately, then combine the responses in the report.
    schema: dict[str, object] = {}
    for type_name in ("Group", "Member", "Membership"):
        result = client.graphql(SCHEMA_QUERY, {"typeName": type_name})
        schema[type_name] = result.get("data", {}).get("type")

    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    output_path.chmod(0o600)
    logger.info("Wrote Meetup schema report to %s", output_path)


def fetch_group_urlnames(client: MeetupGraphQLClient) -> list[dict[str, str]]:
    """Fetch names and URL names for every group in the Meetup Pro network.

    Args:
        client: Authenticated Meetup GraphQL client.

    Returns:
        Group name and URL name records.
    """
    query = """
    query ($urlname: ID!, $cursor: String) {
      proNetwork(urlname: $urlname) {
        groupsSearch(input: { first: 200, after: $cursor, filter: {} }) {
          totalCount
          pageInfo { endCursor hasNextPage }
          edges { node { name urlname } }
        }
      }
    }
    """
    groups: list[dict[str, str]] = []
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
            groups.append({"name": node.get("name", ""), "urlname": node.get("urlname", "")})

        page_info = search.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info.get("endCursor")
            if not cursor:
                raise RuntimeError("Meetup indicated another group page but returned no cursor")
        else:
            break

    return groups


def fetch_group_organisers(client: MeetupGraphQLClient, group_urlname: str) -> list[dict[str, str]]:
    """Fetch organiser membership records for a Meetup group.

    Args:
        client: Authenticated Meetup GraphQL client.
        group_urlname: URL name identifying the group.

    Returns:
        Non-basic membership role, identity, and email records.
    """
    query = """
    query ($urlname: String!, $cursor: String) {
      groupByUrlname(urlname: $urlname) {
        memberships(first: 200, after: $cursor, filter: {}) {
          pageInfo { endCursor hasNextPage }
          edges { node {
            id
            name
            email
            highestCurrentRole
            isLeader
            isOrganizer
          } }
        }
      }
    }
    """
    organisers: list[dict[str, str]] = []
    cursor: str | None = None

    while True:
        data = client.graphql(query, {"urlname": group_urlname, "cursor": cursor})
        group = data.get("data", {}).get("groupByUrlname")
        if group is None:
            raise RuntimeError(f"Meetup group '{group_urlname}' was not found or is not accessible")

        memberships = group.get("memberships")
        if memberships is None:
            raise RuntimeError(f"Meetup did not return memberships for '{group_urlname}'")
        for edge in memberships.get("edges", []):
            node = edge.get("node", {})
            role = node.get("highestCurrentRole")
            is_leader = node.get("isLeader", False)
            is_organiser = node.get("isOrganizer", False)
            if (not role or role == "MEMBER") and not is_leader and not is_organiser:
                continue
            if not role or role == "MEMBER":
                role = "ORGANIZER" if is_organiser else "LEADER"
            organisers.append(
                {
                    "role": role,
                    "full_name": node.get("name", ""),
                    "email": node.get("email", ""),
                }
            )

        page_info = memberships.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info.get("endCursor")
            if not cursor:
                raise RuntimeError(f"Meetup indicated another membership page for '{group_urlname}' but returned no cursor")
        else:
            break

    return organisers


def main() -> None:
    """Fetch non-basic Meetup group members and write them as a private CSV file."""
    parser = argparse.ArgumentParser(description="Export non-basic members from Ansible Meetup Pro groups")
    parser.add_argument("--output", type=Path, default=Path("tmp/meetup-organisers.csv"), help="CSV output path")
    parser.add_argument(
        "--inspect-schema",
        action="store_true",
        help="write the live Group, Member, and Membership GraphQL fields to JSON, then exit",
    )
    parser.add_argument(
        "--schema-output",
        type=Path,
        default=Path("tmp/meetup-organisers-schema.json"),
        help="schema report path used with --inspect-schema",
    )
    args = parser.parse_args()

    pre_flight_checks()

    logger.info("Authenticating with Meetup API...")
    client = MeetupGraphQLClient(get_access_token())

    if args.inspect_schema:
        write_schema_report(client, args.schema_output)
        return

    logger.info("Fetching groups from Pro Network '%s'...", PRO_NETWORK)
    groups = fetch_group_urlnames(client)
    logger.info("Found %d groups", len(groups))

    fieldnames = ["group_name", "group_urlname", "role", "full_name", "email"]
    rows: list[dict[str, str]] = []
    for group in sorted(groups, key=lambda g: g["name"]):
        logger.info("Fetching organisers for %s...", group["urlname"])
        organisers = fetch_group_organisers(client, group["urlname"])
        rows.extend(
            {
                "group_name": group["name"],
                "group_urlname": group["urlname"],
                **organiser,
            }
            for organiser in organisers
        )
        time.sleep(0.5)

    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with args.output.open("w", newline="", encoding="utf-8") as output_file:
        args.output.chmod(0o600)
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Wrote organisers CSV to %s", args.output)
    logger.info("Done.")


if __name__ == "__main__":
    main()
