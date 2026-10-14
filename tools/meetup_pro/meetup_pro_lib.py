"""Shared client for the Meetup Pro Network GraphQL API (JWT OAuth2)."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import jwt
import requests

from tools.common.ansible_events_lib import HTTP_USER_AGENT

logger = logging.getLogger("meetup_export")

PRO_NETWORK = "ansible"


class RequestsClient:
    """A configured requests.Session with a base URL and default timeout."""

    def __init__(self, base_url: str, timeout: int, headers: dict[str, str] | None = None) -> None:
        """Create a session with shared defaults.

        Args:
            base_url: Root URL for requests made by this client.
            timeout: Default request timeout in seconds.
            headers: Optional headers to add to each request.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(headers or {})
        self.session.headers["User-Agent"] = HTTP_USER_AGENT

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        """POST to a path relative to the configured base URL."""
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("allow_redirects", False)
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self.session.post(url, **kwargs)


TOKEN_CLIENT = RequestsClient("https://secure.meetup.com/oauth2", timeout=10)


class MeetupGraphQLClient:
    """GraphQL client that reuses one configured requests session."""

    def __init__(self, token: str) -> None:
        """Create an authenticated Meetup GraphQL client.

        Args:
            token: OAuth2 access token for the Meetup API.
        """
        self.http = RequestsClient(
            "https://api.meetup.com",
            timeout=30,
            headers={"Authorization": f"Bearer {token}"},
        )

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query with rate limit handling."""
        resp = self.http.post("gql-ext", json={"query": query, "variables": variables or {}})
        if resp.status_code == 429:
            wait = 60
            logger.warning("Rate limited, waiting %ds...", wait)
            time.sleep(wait)
            return self.graphql(query, variables)
        if resp.status_code != 200:
            logger.error("GraphQL request failed: HTTP %d", resp.status_code)
            return {}
        return resp.json()


def pre_flight_checks() -> None:
    """Validate required Meetup API environment variables."""
    required = ["MEETUP_CLIENT_KEY", "MEETUP_SIGNING_KEY_ID", "MEETUP_MEMBER_ID", "MEETUP_PRIVATE_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    key_path = os.environ["MEETUP_PRIVATE_KEY"]
    if not Path(key_path).exists():
        logger.error("Private key file not found: %s", key_path)
        sys.exit(1)


def get_access_token() -> str:
    """Authenticate with Meetup OAuth2 and return an access token."""
    client_key = os.environ["MEETUP_CLIENT_KEY"]
    signing_key_id = os.environ["MEETUP_SIGNING_KEY_ID"]
    member_id = os.environ["MEETUP_MEMBER_ID"]
    private_key = Path(os.environ["MEETUP_PRIVATE_KEY"]).read_text()

    signed_jwt = jwt.encode(
        {"sub": member_id, "iss": client_key, "aud": "api.meetup.com", "exp": int(time.time()) + 120},
        private_key,
        algorithm="RS256",
        headers={"kid": signing_key_id, "typ": "JWT", "alg": "RS256"},
    )

    resp = TOKEN_CLIENT.post(
        "access",
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": signed_jwt},
    )
    if resp.status_code != 200:
        logger.error("Meetup auth failed: HTTP %d", resp.status_code)
        sys.exit(1)

    token = resp.json().get("access_token")
    if not token:
        logger.error("No access_token in response")
        sys.exit(1)
    return token
